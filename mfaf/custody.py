"""
سلسلة العهدة (Chain of Custody) — append-only مع ربط تجزئة (hash chain).

كل حدث يحمل تجزئة الحدث السابق؛ أي تعديل تاريخي يكسر السلسلة ويُكتشَف عبر
verify_chain(). الواجهة العادية لا توفّر تعديلًا/حذفًا للأحداث التاريخية.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from . import models as M
from .errors import IntegrityError

CUSTODY_ACTIONS = (
    "EVIDENCE_CREATED", "EVIDENCE_IMPORTED", "EVIDENCE_COPIED", "EVIDENCE_HASHED",
    "EVIDENCE_VERIFIED", "EVIDENCE_EXPORTED", "EVIDENCE_ANALYZED", "REPORT_GENERATED",
    "CASE_CREATED", "DEVICE_IDENTIFIED", "ACQUISITION_STARTED", "ACQUISITION_COMPLETED",
    "ACQUISITION_NOT_AVAILABLE", "EXPERIMENT_RUN",
)


def _entry_hash(prev_hash, payload: dict) -> str:
    h = hashlib.sha256()
    h.update((prev_hash or "").encode())
    h.update(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()


class CustodyLog:
    def __init__(self, db):
        self.db = db

    def _tail_hash(self):
        r = self.db.conn.execute(
            "SELECT entry_hash FROM chain_of_custody_events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return r["entry_hash"] if r else None

    def append(self, actor: str, action: str, case_id=None, evidence_id=None,
               metadata=None) -> dict:
        if action not in CUSTODY_ACTIONS:
            raise IntegrityError(f"إجراء عهدة غير معروف: {action}")
        if not isinstance(actor, str) or not actor.strip():
            raise IntegrityError("actor مطلوب لحدث العهدة")
        event_id = str(uuid.uuid4())
        timestamp = M.utcnow()
        prev = self._tail_hash()
        payload = {
            "event_id": event_id, "case_id": case_id, "evidence_id": evidence_id,
            "actor": actor, "action": action, "metadata": metadata or {},
            "timestamp": timestamp,
        }
        eh = _entry_hash(prev, payload)
        with self.db.conn:
            self.db.conn.execute(
                "INSERT INTO chain_of_custody_events(event_id,case_id,evidence_id,actor,"
                "action,metadata,timestamp,prev_hash,entry_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                (event_id, case_id, evidence_id, actor, action,
                 json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                 timestamp, prev, eh))
        return {"event_id": event_id, "entry_hash": eh, "prev_hash": prev}

    def list_events(self, case_id=None, evidence_id=None) -> list[dict]:
        q = "SELECT * FROM chain_of_custody_events"
        conds, args = [], []
        if case_id:
            conds.append("case_id=?"); args.append(case_id)
        if evidence_id:
            conds.append("evidence_id=?"); args.append(evidence_id)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY seq"
        out = []
        for r in self.db.conn.execute(q, args).fetchall():
            d = dict(r)
            d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
            out.append(d)
        return out

    def verify_chain(self) -> dict:
        """يعيد {"valid": bool, "count": n, "broken_at": seq|None}."""
        rows = self.db.conn.execute(
            "SELECT * FROM chain_of_custody_events ORDER BY seq").fetchall()
        prev = None
        for r in rows:
            payload = {
                "event_id": r["event_id"], "case_id": r["case_id"],
                "evidence_id": r["evidence_id"], "actor": r["actor"],
                "action": r["action"],
                "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                "timestamp": r["timestamp"],
            }
            expected = _entry_hash(prev, payload)
            if r["prev_hash"] != prev or r["entry_hash"] != expected:
                return {"valid": False, "count": len(rows), "broken_at": r["seq"]}
            prev = r["entry_hash"]
        return {"valid": True, "count": len(rows), "broken_at": None}
