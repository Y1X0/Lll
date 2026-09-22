"""
إطار تجارب المصادقة المضبوطة — يقيس الضوابط الأمنية على هدف اختباري.

⚖️ ليس كاسر كلمات مرور. يشغّل سلسلة محاولات اصطناعية على AuthenticationTarget
(المحاكي أساسًا)، ويسجّل سلوك rate-limit وlockout والحالة وإعادة الإقلاع،
ويحسب مقاييس. لا يتجاوز أي ضابط — بل يقيسه ويوثّقه.
"""
from __future__ import annotations

import uuid
from . import models as M
from .metrics import summarize_auth_events


class AuthenticationHarness:
    def __init__(self, db, custody_log=None):
        self.db = db
        self.custody = custody_log

    def run_experiment(self, experiment_id: str, target, test_input_ids: list[str],
                       actor: str = "harness") -> dict:
        """
        يشغّل محاولات مضبوطة على الهدف. test_input_ids قائمة معرّفات اصطناعية.
        يعيد {"events": [...], "metrics": {...}}.
        """
        x = self.db.conn.execute(
            "SELECT * FROM experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
        if not x:
            from .errors import NotFoundError
            raise NotFoundError(f"experiment غير موجود: {experiment_id}")
        target_id = x["target_id"]

        events = []
        prev_state = target.get_state()
        for i, tin in enumerate(test_input_ids, start=1):
            before = target.get_state()
            resp = target.submit_controlled_test_attempt(tin)
            ev = M.AuthenticationEvent(
                event_id=str(uuid.uuid4()),
                experiment_id=experiment_id,
                target_id=target_id,
                attempt_number=i,
                test_input_id=tin,
                result=resp["result"],
                response_time_ms=float(resp["response_time_ms"]),
                target_state=resp["target_state"],
                lockout_state=bool(resp["lockout_state"]),
                rate_limit_state=bool(resp["rate_limit_state"]),
                delay_before_ms=None,
                notes=None,
            )
            self.db.add_auth_event(ev)
            events.append(M.to_dict(ev))
            prev_state = before

        metrics = summarize_auth_events(events)
        if self.custody:
            self.custody.append(actor, "EXPERIMENT_RUN", case_id=x["case_id"],
                                metadata={"experiment_id": experiment_id,
                                          "attempts": len(events)})
        return {"events": events, "metrics": metrics}

    def compare_reboot_state(self, target, test_input_ids_before: list[str]) -> dict:
        """
        EXP-007: يقارن الحالة قبل/بعد إعادة الإقلاع (قياس لا تجاوز).
        يعيد before/after وحالة الانتقال.
        """
        for tin in test_input_ids_before:
            target.submit_controlled_test_attempt(tin)
        before = target.get_state()
        target.reboot()
        after = target.get_state()
        return {
            "before_reboot": before,
            "after_reboot": after,
            "transition": f"{before['state']} -> {after['state']}",
            "attempts_cleared": after["failed_attempts"] < before["failed_attempts"],
        }
