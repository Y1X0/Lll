"""
بروتوكول التحقّق (Validation Protocol) لـ MFAF — ينفّذ تجارب التحقّق V2..V5 فعليًا
على بيانات اصطناعية/المحاكي ويُخرج نتائج قابلة للقراءة آليًا (dataset).

V1 (Android فعلي) ليس هنا — يتطلّب جهازًا فعليًا؛ راجع docs/MFAF_VALIDATION_REPORT.md
للبروتوكول اليدوي. هذا الملف لا يدّعي أي نتيجة عتاد.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import shutil

from . import models as M, __version__
from .db import MFAFDatabase
from .custody import CustodyLog
from .timeline import Timeline
from .acquisition import (AcquisitionEngine, MockAcquisitionProvider,
                          UnavailableAcquisitionProvider, verify_evidence_integrity)
from .mock_device import MockMobileDevice, MockDeviceConfig
from .auth_harness import AuthenticationHarness
from .report import ReportGenerator


def _fresh():
    d = tempfile.mkdtemp(prefix="mfaf_val_")
    return MFAFDatabase(os.path.join(d, "mfaf.db")), d


def _seed(db, case="CASE-VAL"):
    db.add_examiner(M.Examiner("val-ex", "Validation Runner", "Lab"))
    db.add_case(M.Case(case, "Validation", "val-ex", legal_authority="LAB-VALIDATION"))
    db.add_device(M.Device("val-dev", case_id=case, os_family="android",
                           connection_mode="mock", serial=None))
    return case


# ------------------------------------------------------ V2 Evidence integrity
def v2_evidence_integrity() -> dict:
    db, d = _fresh()
    try:
        case = _seed(db)
        eng = AcquisitionEngine(db, CustodyLog(db), Timeline(db))
        r = eng.run(case, "val-dev", MockAcquisitionProvider(
            {"artifact.bin": b"CONTROLLED-TEST-ARTIFACT-v2"}), None,
            os.path.join(d, "store"), "val-ex")
        ev = db.get_evidence(r["evidence"][0]["evidence_id"])
        before = verify_evidence_integrity(db, ev["evidence_id"])
        # افساد نسخة الأدلّة عمدًا
        with open(ev["storage_path"], "ab") as f:
            f.write(b"\x00TAMPER")
        after = verify_evidence_integrity(db, ev["evidence_id"])
        # حالة الملف المفقود
        os.remove(ev["storage_path"])
        missing = verify_evidence_integrity(db, ev["evidence_id"])
        passed = (before == "VERIFIED" and after == "MISMATCH" and missing == "MISSING")
        return {"id": "V2", "name": "Evidence Integrity", "passed": passed,
                "sha256": ev["sha256"][:16] + "…",
                "results": {"pristine": before, "tampered": after, "removed": missing},
                "expected": {"pristine": "VERIFIED", "tampered": "MISMATCH", "removed": "MISSING"}}
    finally:
        db.close(); shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------ V3 Chain of custody
def v3_chain_of_custody() -> dict:
    db, d = _fresh()
    try:
        case = _seed(db)
        log = CustodyLog(db)
        for act in ("EVIDENCE_CREATED", "EVIDENCE_HASHED", "EVIDENCE_VERIFIED",
                    "EVIDENCE_ANALYZED", "REPORT_GENERATED"):
            log.append("val-ex", act, case_id=case, evidence_id="EV-V3")
        valid_before = log.verify_chain()
        # تعديل حدث تاريخي في نسخة اختبارية
        db.conn.execute("UPDATE chain_of_custody_events SET actor='tamperer' WHERE seq=2")
        db.conn.commit()
        valid_after = log.verify_chain()
        passed = (valid_before["valid"] and not valid_after["valid"]
                  and valid_after["broken_at"] == 2)
        return {"id": "V3", "name": "Chain of Custody Tamper-Evidence", "passed": passed,
                "results": {"before_tamper": valid_before, "after_tamper": valid_after}}
    finally:
        db.close(); shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------ V4 Repeatability
def _normalize_events(events):
    # استبعاد الحقول غير الحتمية (uuid/timestamp) لمقارنة المحتوى
    keys = ("attempt_number", "result", "response_time_ms", "target_state",
            "lockout_state", "rate_limit_state")
    return [tuple(e[k] for k in keys) for e in events]


def v4_repeatability(iterations=3) -> dict:
    runs = []
    for _ in range(iterations):
        db, d = _fresh()
        try:
            case = _seed(db)
            dev = MockMobileDevice(MockDeviceConfig(rate_limit_after=3, lockout_after=5))
            dev.connect()
            db.add_experiment(M.Experiment("EXP-R", case, dev.target_id, "EXP-010",
                                           "repeatability"))
            res = AuthenticationHarness(db).run_experiment(
                "EXP-R", dev, [f"SYNTH-WRONG-{i}" for i in range(6)])
            norm = _normalize_events(res["events"])
            digest = hashlib.sha256(json.dumps(norm, sort_keys=True).encode()).hexdigest()
            runs.append({
                "latency": [e["response_time_ms"] for e in res["events"]],
                "metrics": res["metrics"],
                "lockout": res["metrics"]["lockout_detected"],
                "digest": digest,
            })
        finally:
            db.close(); shutil.rmtree(d, ignore_errors=True)
    digests = {r["digest"] for r in runs}
    latencies_equal = all(r["latency"] == runs[0]["latency"] for r in runs)
    passed = (len(digests) == 1 and latencies_equal)
    return {"id": "V4", "name": "Repeatability (determinism)", "passed": passed,
            "iterations": iterations,
            "results": {"unique_result_digests": len(digests),
                        "latency_identical": latencies_equal,
                        "sample_latency": runs[0]["latency"],
                        "lockout_detected": runs[0]["lockout"]}}


# ------------------------------------------------------ V5 Report completeness
def v5_report_completeness() -> dict:
    db, d = _fresh()
    try:
        case = _seed(db)
        cust = CustodyLog(db); tl = Timeline(db)
        eng = AcquisitionEngine(db, cust, tl)
        eng.run(case, "val-dev", MockAcquisitionProvider(), None,
                os.path.join(d, "s"), "val-ex")
        eng.run(case, "val-dev", UnavailableAcquisitionProvider("locked, no authorized path"),
                None, os.path.join(d, "s2"), "val-ex")
        dev = MockMobileDevice(MockDeviceConfig(rate_limit_after=3, lockout_after=5))
        dev.connect()
        db.add_experiment(M.Experiment("EXP-5", case, dev.target_id, "EXP-006", "lockout"))
        AuthenticationHarness(db, cust).run_experiment(
            "EXP-5", dev, [f"SYNTH-WRONG-{i}" for i in range(6)])
        rep = ReportGenerator(db).collect(case)
        s = rep["sections"]
        required = {
            "Case": bool(s["1_case"]), "Examiner": bool(s["2_examiner"]),
            "Device": len(s["3_devices"]) > 0, "Authorization": s["4_authorization"] is not None,
            "Acquisition": len(s["6_acquisition_results"]) > 0,
            "Evidence": len(s["10_evidence_inventory"]) > 0,
            "Hash": len(s["11_hash_verification"]) > 0,
            "Timeline": len(s["9_timeline"]) > 0,
            "ChainOfCustody": len(s["12_chain_of_custody"]["events"]) > 0,
            "Experiment": len(s["7_authentication_experiment"]["events"]) > 0,
            "Limitations": len(s["14_limitations"]) > 0,
        }
        passed = all(required.values()) and s["12_chain_of_custody"]["chain_integrity"]["valid"]
        return {"id": "V5", "name": "Report Completeness", "passed": passed,
                "results": {"sections_present": required,
                            "chain_valid": s["12_chain_of_custody"]["chain_integrity"]["valid"],
                            "not_available_reported": any(
                                a["status"] == "NOT_AVAILABLE" for a in s["6_acquisition_results"])}}
    finally:
        db.close(); shutil.rmtree(d, ignore_errors=True)


def run_all() -> dict:
    checks = [v2_evidence_integrity(), v3_chain_of_custody(),
              v4_repeatability(), v5_report_completeness()]
    return {
        "platform": "MFAF", "version": __version__,
        "generated_at": M.utcnow(),
        "v1_physical_android": {
            "id": "V1", "name": "Physical Android field validation",
            "status": "NOT_VERIFIED",
            "executed": False,
            "measurements": {
                "device_identification": "NOT_VERIFIED",
                "usb_observation": "NOT_VERIFIED",
                "authorized_acquisition": "NOT_VERIFIED",
                "evidence_integrity": "NOT_VERIFIED",
                "timeline": "NOT_VERIFIED",
                "repeatability": "NOT_VERIFIED",
            },
            "metrics": {
                "device_identification_success": None,
                "usb_observation_success": None,
                "authorized_acquisition_available": None,
                "evidence_hash_verified": None,
                "timeline_reconstructed": None,
                "repeatability_runs": None,
                "repeatability_consistent": None,
                "unexpected_behavior": None,
            },
            "note": ("لا جهاز فعلي في بيئة التنفيذ. يُنفَّذ يدويًا عبر "
                     "docs/MFAF_V1_ANDROID_FIELD_PROTOCOL.md ثم `mfaf v1 import`. "
                     "null = لم يُرصد/لم يُقَس (ليست false)."),
        },
        "checks": checks,
        "summary": {
            "executed_checks": len(checks),
            "passed": sum(1 for c in checks if c["passed"]),
            "all_passed": all(c["passed"] for c in checks),
        },
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="MFAF Validation Protocol runner (V2..V5)")
    ap.add_argument("--out", default=None, help="مسار حفظ dataset النتائج (JSON)")
    args = ap.parse_args()
    results = run_all()
    text = json.dumps(results, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[+] dataset saved: {args.out}")
    print(text)
