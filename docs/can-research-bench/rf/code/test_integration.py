"""
Phase 4B — اختبارات ISO-TP (FC/BS + تسلسل CF) ومسار التكامل
CAN → ISO-TP → UDS → SQLite Evidence.
"""
import os
import unittest

from isotp import (
    isotp_transfer, ISOTPReceiver, ISOTPSession, ISOTPConfig, ISOTPTransportError,
)
from diag_pipeline import DiagnosticPipeline
from uds_services import UDSServer


class TestISOTPFlowControl(unittest.TestCase):

    def test_single_frame(self):
        r = isotp_transfer(b"\x10\x03", 0x7E0, 0x7E8)
        self.assertEqual(r.message, b"\x10\x03")
        self.assertEqual(len(r.tx_frames), 1)

    def test_multiframe_no_blocksize(self):
        payload = bytes(range(40))
        r = isotp_transfer(payload, 0x7E0, 0x7E8, bs=0)
        self.assertEqual(r.message, payload)
        self.assertEqual(r.fc_frames, 1)          # CTS واحد بعد FF

    def test_multiframe_with_blocksize(self):
        payload = bytes(range(40))
        r = isotp_transfer(payload, 0x7E0, 0x7E8, bs=4)
        self.assertEqual(r.message, payload)      # تجميع سليم رغم تقطيع الكتل
        self.assertGreaterEqual(r.fc_frames, 2)   # FC عند كل حدّ كتلة

    def test_stmin_respected_via_sleep_fn(self):
        calls = []
        r = isotp_transfer(bytes(range(20)), 0x7E0, 0x7E8, bs=0, stmin=5,
                           sleep_fn=lambda s: calls.append(s))
        self.assertEqual(r.message, bytes(range(20)))
        self.assertTrue(all(abs(c - 0.005) < 1e-9 for c in calls))  # 5ms
        self.assertGreater(len(calls), 0)

    def test_cf_sequence_error_detected(self):
        sess = ISOTPSession(ISOTPConfig(0x7E0, 0x7E8))
        frames = sess.encode(b"\x22\xF1\x90" + b"X" * 20)
        frames[2]["payload"] = bytes([0x2F]) + frames[2]["payload"][1:]  # seq خاطئ
        rcv = ISOTPReceiver(tx_id=0x7E8, rx_id=0x7E0)
        with self.assertRaises(ISOTPTransportError):
            for f in frames:
                rcv.on_frame(f)

    def test_unexpected_cf_without_ff(self):
        rcv = ISOTPReceiver(tx_id=0x7E8, rx_id=0x7E0)
        cf = {"can_id": 0x7E8, "dlc": 8, "payload": bytes([0x21] + [0] * 7),
              "is_extended": False}
        with self.assertRaises(ISOTPTransportError):
            rcv.on_frame(cf)


class TestDiagnosticPipeline(unittest.TestCase):

    def setUp(self):
        self.db_file = "test_pipeline.db"
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def tearDown(self):
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_pipeline_single_frame_session_control(self):
        with DiagnosticPipeline(self.db_file) as p:
            res = p.request(b"\x10\x03")   # DiagnosticSessionControl extended
            self.assertTrue(res.positive)
            self.assertEqual(res.response, b"\x50\x03")
            self.assertEqual(res.tx_frames, 1)
            # سُجّلت رسالتان: TX + RX
            self.assertEqual(len(p.db.get_messages(res.session_id)), 2)

    def test_pipeline_multiframe_read_vin(self):
        # ردّ VIN: 0x62 + DID(2) + 17 = 20 بايت → متعدّد الإطارات
        with DiagnosticPipeline(self.db_file, bs=4) as p:
            res = p.request(b"\x22\xF1\x90")
            self.assertTrue(res.positive)
            self.assertEqual(res.response[0], 0x62)
            self.assertEqual(res.response[3:], b"VIN-SIMULATOR-001")
            self.assertGreater(res.rx_frames, 1)   # الردّ فعلًا متعدّد الإطارات
            msgs = p.db.get_messages(res.session_id)
            self.assertEqual([m["direction"] for m in msgs], ["TX", "RX"])

    def test_pipeline_negative_unsupported_did(self):
        with DiagnosticPipeline(self.db_file) as p:
            res = p.request(b"\x22\xDE\xAD")       # DID غير موجود
            self.assertFalse(res.positive)
            self.assertEqual(res.response_code, 0x31)   # requestOutOfRange
            # NRC مخزّن في الأدلّة
            rx = [m for m in p.db.get_messages(res.session_id) if m["direction"] == "RX"][0]
            self.assertEqual(rx["response_code"], 0x31)

    def test_pipeline_security_access_boundary(self):
        # 0x27 خارج النطاق → NRC 0x11، بلا أي منطق Seed
        with DiagnosticPipeline(self.db_file) as p:
            res = p.request(b"\x27\x01")
            self.assertFalse(res.positive)
            self.assertEqual(res.response_code, 0x11)   # serviceNotSupported

    def test_pipeline_evidence_persistence(self):
        with DiagnosticPipeline(self.db_file) as p:
            p.request(b"\x3E\x00")
            p.request(b"\x22\xF1\x90")
            sid = p.session_id
            self.assertEqual(len(p.db.get_messages(sid)), 4)   # جلستان × (TX+RX)
        # ثبات بعد إعادة الفتح
        from database import UDSEvidenceDB
        db2 = UDSEvidenceDB(self.db_file)
        self.assertEqual(db2.count("uds_messages"), 4)
        self.assertEqual(db2.count("uds_sessions"), 1)
        db2.close()

class TestDTCPipeline(unittest.TestCase):
    """0x19/0x14 عبر المسار الكامل CAN→ISO-TP→UDS→Evidence مع ExtendedUDSServer."""

    def setUp(self):
        self.db_file = "test_dtc_pipeline.db"
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def tearDown(self):
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_pipeline_read_dtc_multiframe(self):
        from uds_services import ExtendedUDSServer
        with DiagnosticPipeline(self.db_file, ecu=ExtendedUDSServer(), bs=2) as p:
            res = p.request(b"\x19\x02")            # reportDTCByStatusMask
            self.assertTrue(res.positive)
            self.assertEqual(res.response[0], 0x59)
            self.assertEqual(res.response[1], 0x02)
            self.assertGreater(res.rx_frames, 1)      # 11 بايت → متعدّد الإطارات
            # sub-function 0x19 سُجّل في الأدلّة
            rx = [m for m in p.db.get_messages(res.session_id) if m["direction"] == "RX"][0]
            self.assertEqual(rx["service_id"], 0x59)

    def test_pipeline_clear_dtc_then_read_empty(self):
        from uds_services import ExtendedUDSServer
        ecu = ExtendedUDSServer()
        with DiagnosticPipeline(self.db_file, ecu=ecu) as p:
            clr = p.request(b"\x14\xFF\xFF\xFF")   # ClearDiagnosticInformation
            self.assertTrue(clr.positive)
            self.assertEqual(clr.response, b"\x54")
            self.assertEqual(len(ecu.dtc_store), 0)
            # قراءة بعد المسح → ردّ إيجابي بلا DTCs (الترويسة فقط)
            rd = p.request(b"\x19\x02")
            self.assertTrue(rd.positive)
            self.assertEqual(rd.response, b"\x59\x02\x00")

    def test_pipeline_dtc_evidence_persistence(self):
        from uds_services import ExtendedUDSServer
        from database import UDSEvidenceDB
        with DiagnosticPipeline(self.db_file, ecu=ExtendedUDSServer()) as p:
            p.request(b"\x19\x02")
            p.request(b"\x14\xFF\xFF\xFF")
            sid = p.session_id
            self.assertEqual(len(p.db.get_messages(sid)), 4)   # جلستان × (TX+RX)
        db2 = UDSEvidenceDB(self.db_file)
        self.assertEqual(db2.count("uds_messages"), 4)
        db2.close()



if __name__ == "__main__":
    unittest.main()
