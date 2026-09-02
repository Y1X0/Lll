"""
Integration tests for UDS Evidence Storage in SQLite (Phase 4B).

مصحّح عن النسخة الأصلية: تُنشأ جلسة قبل الرسالة (FK مفعّل لسلامة الأدلّة)،
مع اختبارات إضافية: رفض اليتيم، CASCADE، عزل الجلسات، وتكامل BLOB.
لا تداخل مع جداول RF/CAN.
"""
import os
import time
import unittest

from database import UDSEvidenceDB


class TestUDSEvidenceStorage(unittest.TestCase):

    def setUp(self):
        self.db_file = "test_uds_evidence.db"
        if os.path.exists(self.db_file):
            os.remove(self.db_file)
        self.db = UDSEvidenceDB(self.db_file)

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_uds_message_persistence(self):
        # أنشئ جلسة أولًا (شرط FK)، ثم احفظ رسالة تشخيص
        session_id = self.db.start_session(ecu_address=0x7E0, session_type=0x03, source="test")
        msg_id = self.db.save_diagnostic_exchange(
            session_id=session_id, timestamp=time.time(), service_id=0x22,
            sub_function=None, payload=b"\x22\xF1\x90", direction="TX", response_code=None)
        self.assertGreater(msg_id, 0)

        row = self.db.get_message(msg_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["service_id"], 0x22)
        self.assertEqual(row["direction"], "TX")
        self.assertEqual(row["payload"], b"\x22\xF1\x90")

    def test_foreign_key_rejects_orphan_message(self):
        # رسالة بجلسة غير موجودة يجب أن تُرفض (سلامة الأدلّة)
        with self.assertRaises(Exception):
            self.db.save_diagnostic_exchange(
                session_id=9999, timestamp=1.0, service_id=0x22,
                sub_function=None, payload=b"\x22\xF1\x90", direction="TX")

    def test_request_response_pair(self):
        sid = self.db.start_session(0x7E0, 0x01, "sim")
        self.db.save_diagnostic_exchange(sid, time.time(), 0x22, None, b"\x22\xF1\x90", "TX")
        # ردّ إيجابي 0x62 + DID + VIN، response_code=None (إيجابي)
        self.db.save_diagnostic_exchange(sid, time.time(), 0x62, None,
                                         b"\x62\xF1\x90VIN-SIMULATOR-001", "RX", None)
        # ردّ سلبي مثال: response_code=NRC 0x31
        self.db.save_diagnostic_exchange(sid, time.time(), 0x7F, None,
                                         b"\x7F\x22\x31", "RX", 0x31)
        msgs = self.db.get_messages(sid)
        self.assertEqual(len(msgs), 3)
        self.assertEqual([m["direction"] for m in msgs], ["TX", "RX", "RX"])
        self.assertEqual(msgs[2]["response_code"], 0x31)

    def test_cascade_delete(self):
        sid = self.db.start_session(0x7E0, 0x01, "sim")
        self.db.save_diagnostic_exchange(sid, 1.0, 0x3E, 0x00, b"\x3E\x00", "TX")
        self.assertEqual(self.db.count("uds_messages"), 1)
        with self.db.conn:
            self.db.conn.execute("DELETE FROM uds_sessions WHERE id=?", (sid,))
        self.assertEqual(self.db.count("uds_messages"), 0, "CASCADE يحذف رسائل الجلسة")

    def test_session_isolation(self):
        s1 = self.db.start_session(0x7E0, 0x01, "sim")
        s2 = self.db.start_session(0x7E1, 0x03, "sim")
        self.db.save_diagnostic_exchange(s1, 1.0, 0x22, None, b"\x22\xF1\x90", "TX")
        self.db.save_diagnostic_exchange(s2, 1.0, 0x22, None, b"\x22\xF1\x87", "TX")
        self.db.save_diagnostic_exchange(s2, 1.0, 0x3E, 0x00, b"\x3E\x00", "TX")
        self.assertEqual(len(self.db.get_messages(s1)), 1)
        self.assertEqual(len(self.db.get_messages(s2)), 2)

    def test_direction_check_constraint(self):
        sid = self.db.start_session(0x7E0, 0x01, "sim")
        with self.assertRaises(Exception):
            self.db.conn.execute(
                "INSERT INTO uds_messages (session_id,timestamp,service_id,payload,direction) "
                "VALUES (?,?,?,?,?)", (sid, 1.0, 0x22, b"\x22", "XX"))  # اتجاه غير صالح


if __name__ == "__main__":
    unittest.main()
