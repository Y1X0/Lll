"""
Unit tests for Unified Evidence Reporter (RF + CAN + UDS aggregation).
مصحّح: يستخدم أصناف القاعدة الحقيقية، وينشئ جلسة قبل رسالة UDS (FK).
"""
import json
import os
import unittest

from database import EvidenceDB, CanEvidenceDB, UDSEvidenceDB
from evidence_reporter import UnifiedEvidenceReporter


class TestEvidenceReporter(unittest.TestCase):

    def setUp(self):
        self.db_file = "test_unified_evidence.db"
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

        # RF: التقاط + نبضة
        rf = EvidenceDB(self.db_file)
        rf.save_analysis("sig.iq", 100000.0, "complex64", 600, "synthetic", [
            {"pulse_index": 0, "start_sample": 0, "end_sample": 99,
             "width_samples": 100, "width_seconds": 0.001, "gap_seconds": 0.001}])
        rf.close()

        # CAN: جلسة + إطار (payload BLOB)
        can = CanEvidenceDB(self.db_file)
        cid = can.start_session("sim0", 500000, "test")
        can.insert_frames(cid, [{
            "timestamp": 1.0, "can_id": 0x7E8, "is_extended": False, "dlc": 3,
            "payload": b"\x62\xF1\x90", "direction": "RX",
            "interface": "sim0", "error_status": None}])
        can.close()

        # UDS: جلسة + رسالة (بعد إنشاء الجلسة — FK)
        uds = UDSEvidenceDB(self.db_file)
        sid = uds.start_session(ecu_address=0x7E0, session_type=0x03, source="test")
        uds.save_diagnostic_exchange(
            session_id=sid, timestamp=1234567890.0, service_id=0x22,
            sub_function=None, payload=b"\x22\xF1\x90", direction="TX")
        uds.close()

    def tearDown(self):
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_reporter_json_output(self):
        rep = UnifiedEvidenceReporter(self.db_file)
        parsed = json.loads(rep.generate_report("json"))
        s = parsed["summary"]
        self.assertEqual(s["total_uds_messages"], 1)
        self.assertEqual(s["total_can_frames"], 1)
        self.assertEqual(s["total_rf_captures"], 1)
        self.assertEqual(parsed["evidence"]["uds_messages"][0]["service_id"], 0x22)
        # BLOB حُوّل إلى hex
        self.assertEqual(parsed["evidence"]["uds_messages"][0]["payload"], "22f190")
        self.assertEqual(parsed["evidence"]["can_frames"][0]["payload"], "62f190")

    def test_reporter_markdown_output(self):
        rep = UnifiedEvidenceReporter(self.db_file)
        md = rep.generate_report("markdown")
        self.assertIn("Forensic Evidence Report", md)
        self.assertIn("Total Uds Messages", md)
        self.assertIn("UDS Diagnostic Exchanges", md)
        self.assertIn("CAN Frames", md)

    def test_reporter_missing_db_raises(self):
        with self.assertRaises(FileNotFoundError):
            UnifiedEvidenceReporter("does_not_exist.db").generate_report()

    def test_reporter_partial_db(self):
        # قاعدة UDS فقط (بلا RF/CAN) — يجب ألا يفشل
        pdb = "test_partial.db"
        if os.path.exists(pdb):
            os.remove(pdb)
        try:
            u = UDSEvidenceDB(pdb)
            u.close()
            parsed = json.loads(UnifiedEvidenceReporter(pdb).generate_report("json"))
            self.assertEqual(parsed["summary"]["total_rf_captures"], 0)
            self.assertEqual(parsed["summary"]["total_can_frames"], 0)
        finally:
            os.path.exists(pdb) and os.remove(pdb)


if __name__ == "__main__":
    unittest.main()
