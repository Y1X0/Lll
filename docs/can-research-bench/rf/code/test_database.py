#!/usr/bin/env python3
"""
test_database.py — اختبارات أتمتة لطبقة تخزين الأدلّة SQLite.

يغطّي معايير القبول:
  - Synthetic OOK Validation (خطّ الفكّ ينتج نبضات تُخزَّن وتُسترجَع)
  - Database Schema & Tables Generation
  - Capture ↔ Pulses Foreign Key Relational Integrity (+ ON DELETE CASCADE)
  - Multiple Executions & Independent ID Isolation
  - Data Persistence Across Reconnections
  - JSON Output Compatibility

التشغيل:  python -m pytest test_database.py -v
أو بلا pytest:  python test_database.py
"""
import json
import os
import tempfile

import numpy as np

from database import EvidenceDB, pulses_from_runs
from ook_decode import envelope, adaptive_threshold, binarize, run_lengths


# ------------------------------------------------------- أدوات مساعدة
def _synthetic_ook(fs=100_000.0, sym=0.001, bits=(1, 0, 1, 0, 1, 0)):
    """يولّد IQ اصطناعية OOK بسيطة (نبضات مربّعة + حامل + ضوضاء خفيفة)."""
    sps = int(fs * sym)
    env = np.concatenate([np.full(sps, b, dtype=np.float32) for b in bits])
    t = np.arange(env.size) / fs
    iq = (env * np.exp(2j * np.pi * 5000.0 * t)).astype(np.complex64)
    iq += (0.01 * (np.random.randn(iq.size) + 1j * np.random.randn(iq.size))).astype(np.complex64)
    return iq, fs


def _decode_to_pulses(iq, fs):
    mag, fs2 = envelope(iq, fs)
    thr = adaptive_threshold(mag)
    binary = binarize(mag, thr)
    runs = run_lengths(binary)
    return pulses_from_runs(runs, fs2), fs2


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # نريد المسار فقط
    return path


# --------------------------------------------------------------- tests
def test_schema_generation():
    """Database Schema & Tables Generation: PASS متوقّع."""
    path = _tmp_db()
    try:
        db = EvidenceDB(path)
        names = {r[0] for r in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "captures" in names
        assert "pulses_analysis" in names
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_synthetic_ook_pipeline_and_store():
    """Synthetic OOK Validation: الفكّ ينتج نبضات تُخزَّن وتُسترجَع."""
    path = _tmp_db()
    try:
        iq, fs = _synthetic_ook()
        pulses, fs2 = _decode_to_pulses(iq, fs)
        assert len(pulses) >= 3, "يجب اكتشاف نبضات عالية متعدّدة"
        db = EvidenceDB(path)
        cid = db.save_analysis(
            "synthetic_demo", fs2, "complex64", iq.size, "synthetic", pulses)
        assert db.count("captures") == 1
        assert db.count("pulses_analysis") == len(pulses)
        got = db.get_pulses(cid)
        assert [p["pulse_index"] for p in got] == list(range(len(pulses)))
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_foreign_key_integrity():
    """Capture ↔ Pulses Foreign Key Relational Integrity: PASS متوقّع."""
    path = _tmp_db()
    try:
        db = EvidenceDB(path)
        # إدخال نبضة بمعرّف التقاط غير موجود يجب أن يُرفض
        raised = False
        try:
            db.insert_pulses(9999, [{
                "pulse_index": 0, "start_sample": 0, "end_sample": 9,
                "width_samples": 10, "width_seconds": 0.001, "gap_seconds": None}])
        except Exception:
            raised = True
        assert raised, "FK يجب أن يمنع نبضة يتيمة"
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_cascade_delete():
    """ON DELETE CASCADE: حذف الالتقاط يحذف نبضاته."""
    path = _tmp_db()
    try:
        db = EvidenceDB(path)
        cid = db.save_analysis("f", 100000.0, "complex64", 400, "synthetic", [
            {"pulse_index": 0, "start_sample": 0, "end_sample": 99,
             "width_samples": 100, "width_seconds": 0.001, "gap_seconds": 0.001}])
        assert db.count("pulses_analysis") == 1
        with db.conn:
            db.conn.execute("DELETE FROM captures WHERE id = ?", (cid,))
        assert db.count("pulses_analysis") == 0, "CASCADE يجب أن يحذف النبضات"
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_multiple_executions_independent_ids():
    """Multiple Executions & Independent ID Isolation: PASS متوقّع."""
    path = _tmp_db()
    try:
        db = EvidenceDB(path)
        ids = []
        for k in range(3):
            ids.append(db.save_analysis(
                f"run{k}", 100000.0, "complex64", 400, "synthetic", [
                    {"pulse_index": 0, "start_sample": 0, "end_sample": 99,
                     "width_samples": 100, "width_seconds": 0.001, "gap_seconds": None}]))
        assert ids == sorted(set(ids)), "المعرّفات يجب أن تكون فريدة ومتزايدة"
        assert db.count("captures") == 3
        # كل التقاط له نبضاته الخاصّة فقط
        for cid in ids:
            assert len(db.get_pulses(cid)) == 1
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_persistence_across_reconnections():
    """Data Persistence Across Reconnections: PASS متوقّع."""
    path = _tmp_db()
    try:
        db = EvidenceDB(path)
        cid = db.save_analysis("persist", 100000.0, "complex64", 400, "synthetic", [
            {"pulse_index": 0, "start_sample": 0, "end_sample": 99,
             "width_samples": 100, "width_seconds": 0.001, "gap_seconds": 0.001}])
        db.close()

        db2 = EvidenceDB(path)  # إعادة فتح
        cap = db2.get_capture(cid)
        assert cap is not None
        assert cap["file_path"] == "persist"
        assert db2.count("pulses_analysis") == 1
        db2.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_json_output_compatibility():
    """JSON Output Compatibility: السجلّات قابلة للتسلسل JSON."""
    path = _tmp_db()
    try:
        db = EvidenceDB(path)
        cid = db.save_analysis("jsontest", 100000.0, "complex64", 400, "synthetic", [
            {"pulse_index": 0, "start_sample": 0, "end_sample": 99,
             "width_samples": 100, "width_seconds": 0.001, "gap_seconds": 0.001}])
        cap = db.get_capture(cid)
        pulses = db.get_pulses(cid)
        s = json.dumps({"capture": cap, "pulses": pulses})
        back = json.loads(s)
        assert back["capture"]["id"] == cid
        assert back["pulses"][0]["width_samples"] == 100
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


# ---------------------------------------------- تشغيل مباشر بلا pytest


# ---------------------------------- JSON export (إغلاق فجوة Phase 2)
def test_json_export_and_db_consistency():
    """AnalysisResult يُصدَّر JSON ويتطابق مع صفوف SQLite لنفس الطابع الزمني."""
    from datetime import datetime, timezone
    from database import pulses_from_runs
    from ook_decode import build_analysis_result

    path = _tmp_db()
    jpath = path + ".json"
    try:
        iq, fs = _synthetic_ook()
        pulses, fs2 = _decode_to_pulses(iq, fs)
        # أعد اشتقاق مدخلات build كما في main
        mag, _ = envelope(iq, fs)
        thr = adaptive_threshold(mag)
        runs = run_lengths(binarize(mag, thr))
        ts = datetime.now(timezone.utc).isoformat()
        result = build_analysis_result(
            "synthetic_demo", "complex64", iq.size, "synthetic",
            fs2, thr, runs, None, [1, 0, 1], "NRZ (quantized)", -1,
            pulses_from_runs(runs, fs2), ts)

        # اكتب JSON واقرأه
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False)
        with open(jpath, encoding="utf-8") as fh:
            back = json.load(fh)
        assert back["capture"]["timestamp"] == ts
        assert back["capture"]["file_path"] == "synthetic_demo"
        assert "bits" in back["decode"]
        assert len(back["pulses"]) == len(result["pulses"])

        # خزّن في DB بنفس الطابع الزمني وتأكّد التطابق
        db = EvidenceDB(path)
        cap = result["capture"]
        cid = db.save_analysis(cap["file_path"], cap["sample_rate"],
                               cap["sample_format"], cap["num_samples"],
                               cap["source"], result["pulses"], timestamp=cap["timestamp"])
        row = db.get_capture(cid)
        assert row["timestamp"] == back["capture"]["timestamp"], "JSON و DB بنفس الطابع الزمني"
        assert row["file_path"] == back["capture"]["file_path"]
        assert db.count("pulses_analysis") == len(back["pulses"])
        db.close()
    finally:
        for p in (path, jpath):
            os.path.exists(p) and os.unlink(p)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    raise SystemExit(0 if passed == len(tests) else 1)
