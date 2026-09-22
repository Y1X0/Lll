"""
مولّد التقرير الجنائي — 16 قسمًا، JSON وMarkdown.

يفصل صراحةً بين: OBSERVED FACT / INTERPRETATION / LIMITATION.
لا يدّعي اختراق جهاز ما لم تُثبِته الأدلّة. إن تعذّر الاقتناء يذكر ذلك صراحةً.
"""
from __future__ import annotations

import json
import uuid
from . import __version__
from . import models as M
from .custody import CustodyLog
from .metrics import evidence_metrics, timeline_metrics


TOOL_VERSIONS = {
    "mfaf": __version__,
    "python_note": "stdlib only (sqlite3, hashlib)",
}


class ReportGenerator:
    def __init__(self, db):
        self.db = db

    def collect(self, case_id) -> dict:
        case = self.db.get_case(case_id)
        examiner = self.db.conn.execute(
            "SELECT * FROM examiners WHERE examiner_id=?", (case["examiner_id"],)).fetchone()
        devices = [dict(r) for r in self.db.conn.execute(
            "SELECT * FROM devices WHERE case_id=?", (case_id,)).fetchall()]
        acqs = [dict(r) for r in self.db.conn.execute(
            "SELECT * FROM acquisitions WHERE case_id=?", (case_id,)).fetchall()]
        evidence = self.db.list_evidence(case_id)
        experiments = [dict(r) for r in self.db.conn.execute(
            "SELECT * FROM experiments WHERE case_id=?", (case_id,)).fetchall()]
        auth_events = []
        for x in experiments:
            auth_events.extend(self.db.list_auth_events(x["experiment_id"]))
        timeline = self.db.list_timeline(case_id)
        custody = CustodyLog(self.db)
        coc = custody.list_events(case_id=case_id)
        chain_status = custody.verify_chain()

        # نتائج التحقّق من التجزئة (حقيقة مرصودة)
        hash_results = [{"evidence_id": e["evidence_id"],
                         "integrity_status": e["integrity_status"],
                         "sha256": e["sha256"]} for e in evidence]

        findings = self._derive_findings(evidence, acqs, auth_events, chain_status)

        return {
            "report_id": f"RPT-{uuid.uuid4().hex[:12]}",
            "generated_at": M.utcnow(),
            "sections": {
                "1_case": case,
                "2_examiner": dict(examiner) if examiner else None,
                "3_devices": devices,
                "4_authorization": {"legal_authority": case.get("legal_authority"),
                                    "note": "مُدخَل يدويًا من الفاحص؛ المنصّة لا تخترع تفويضًا"},
                "5_acquisition_method": [{"provider": a["provider"], "status": a["status"],
                                          "reason": a["reason"]} for a in acqs],
                "6_acquisition_results": acqs,
                "7_authentication_experiment": {"experiments": experiments,
                                                "events": auth_events},
                "8_usb_events": [t for t in timeline if t["event_type"].startswith("DEVICE_")],
                "9_timeline": timeline,
                "10_evidence_inventory": evidence,
                "11_hash_verification": hash_results,
                "12_chain_of_custody": {"events": coc, "chain_integrity": chain_status},
                "13_findings": findings,
                "14_limitations": self._limitations(acqs),
                "15_reproducibility": {
                    "deterministic_mock": True,
                    "physical_device_required": False,
                    "note": "التجارب على المحاكي حتمية وقابلة للتكرار",
                },
                "16_tool_versions": TOOL_VERSIONS,
            },
            "metrics": {
                **evidence_metrics(evidence),
                **timeline_metrics(timeline),
                "authentication_event_count": len(auth_events),
                "chain_of_custody_valid": chain_status["valid"],
            },
        }

    def _derive_findings(self, evidence, acqs, auth_events, chain_status) -> list[dict]:
        f = []
        verified = sum(1 for e in evidence if e["integrity_status"] == "VERIFIED")
        f.append({"type": "OBSERVED_FACT",
                  "statement": f"{verified}/{len(evidence)} عنصر أدلّة تحقّقت سلامته (SHA-256)"})
        if any(a["status"] == "NOT_AVAILABLE" for a in acqs):
            reasons = [a["reason"] for a in acqs if a["status"] == "NOT_AVAILABLE"]
            f.append({"type": "OBSERVED_FACT",
                      "statement": "تعذّر الاقتناء على منصّة/حالة واحدة أو أكثر",
                      "detail": reasons})
        if any(e["lockout_state"] for e in auth_events):
            f.append({"type": "OBSERVED_FACT",
                      "statement": "لوحظ إغلاق (lockout) أثناء تجربة المصادقة المضبوطة"})
            f.append({"type": "INTERPRETATION",
                      "statement": "الضابط الأمني (الإغلاق) يعمل كما هو متوقّع على الهدف الاختباري"})
        f.append({"type": "LIMITATION",
                  "statement": "لم يُختبَر أي جهاز فعلي؛ النتائج على محاكي/مجموعات اصطناعية"})
        if not chain_status["valid"]:
            f.append({"type": "OBSERVED_FACT",
                      "statement": f"سلسلة العهدة مكسورة عند seq={chain_status['broken_at']}"})
        return f

    def _limitations(self, acqs) -> list[str]:
        lim = [
            "المنصّة لا تتجاوز أي ضابط أمني — تقيسه فقط",
            "الاقتناء يقتصر على المصادر المدعومة؛ غيرها يُسجَّل NOT_AVAILABLE",
            "لا يُدَّعى اختراق جهاز ما لم تُثبته الأدلّة",
        ]
        if any(a["provider"] in ("android", "ios") for a in acqs):
            lim.append("NOT VERIFIED — PHYSICAL DEVICE REQUIRED لمزوّدي Android/iOS الحقيقيين")
        return lim

    def render_json(self, case_id) -> str:
        return json.dumps(self.collect(case_id), indent=2, ensure_ascii=False)

    def render_markdown(self, case_id) -> str:
        d = self.collect(case_id)
        s = d["sections"]
        md = [f"# MFAF — Forensic Report", f"**Report ID:** {d['report_id']}  ",
              f"**Generated:** {d['generated_at']}", ""]
        c = s["1_case"]
        md += ["## 1. Case Information",
               f"- **Case:** {c['case_id']} — {c['title']}",
               f"- **Status:** {c['status']}", ""]
        ex = s["2_examiner"]
        md += ["## 2. Examiner", f"- {ex['name']} ({ex.get('organization') or '-'})" if ex else "- (none)", ""]
        md += ["## 3. Devices"]
        for dv in s["3_devices"]:
            md.append(f"- `{dv['device_id']}` {dv.get('manufacturer') or '?'}/"
                      f"{dv.get('model') or '?'} os={dv['os_family']} serial={dv['serial']}")
        md += ["", "## 4. Authorization / Reference",
               f"- {s['4_authorization']['legal_authority'] or '(not provided)'}",
               f"- _{s['4_authorization']['note']}_", ""]
        md += ["## 5–6. Acquisition"]
        for a in s["6_acquisition_results"]:
            md.append(f"- {a['provider']}: **{a['status']}**"
                      + (f" — {a['reason']}" if a["reason"] else ""))
        md += ["", "## 10. Evidence Inventory"]
        for e in s["10_evidence_inventory"]:
            md.append(f"- `{e['evidence_id']}` {e['original_filename']} "
                      f"({e['byte_size']} B) sha256={(e['sha256'] or '')[:16]}… "
                      f"[{e['integrity_status']}]")
        md += ["", "## 11. Hash Verification"]
        for h in s["11_hash_verification"]:
            md.append(f"- {h['evidence_id']}: **{h['integrity_status']}**")
        md += ["", "## 12. Chain of Custody",
               f"- events: {len(s['12_chain_of_custody']['events'])} | "
               f"integrity: **{'VALID' if s['12_chain_of_custody']['chain_integrity']['valid'] else 'BROKEN'}**"]
        md += ["", "## 13. Findings"]
        for f in s["13_findings"]:
            md.append(f"- **[{f['type']}]** {f['statement']}")
        md += ["", "## 14. Limitations"]
        for l in s["14_limitations"]:
            md.append(f"- {l}")
        md += ["", "## 15. Reproducibility",
               f"- physical_device_required: {s['15_reproducibility']['physical_device_required']}",
               f"- deterministic_mock: {s['15_reproducibility']['deterministic_mock']}"]
        md += ["", "## 16. Tool Versions",
               f"- mfaf {s['16_tool_versions']['mfaf']}"]
        md += ["", "## Metrics", "```json", json.dumps(d["metrics"], indent=2, ensure_ascii=False), "```"]
        return "\n".join(md)
