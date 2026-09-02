"""
Unit tests for UDS DTC services (0x19 and 0x14).
"""

import unittest
from uds_services import ExtendedUDSServer


class TestUDSDTCServices(unittest.TestCase):

    def setUp(self):
        self.server = ExtendedUDSServer()

    def test_read_dtc_information(self):
        # Read DTCs by status mask (0x19 0x02)
        req = b"\x19\x02"
        resp = self.server.handle_request(req)
        self.assertEqual(resp[0], 0x59)  # Positive response (0x19 + 0x40)
        self.assertEqual(resp[1], 0x02)  # Sub-function echo
        self.assertGreater(len(resp), 2)

    def test_read_dtc_unsupported_subfunction(self):
        resp = self.server.handle_request(b"\x19\x0A")   # sub-func غير مدعوم
        self.assertEqual(resp[0], 0x7F)
        self.assertEqual(resp[2], 0x12)  # subFunctionNotSupported

    def test_clear_diagnostic_information(self):
        # Clear all DTCs (0x14 0xFF 0xFF 0xFF)
        req = b"\x14\xFF\xFF\xFF"
        resp = self.server.handle_request(req)
        self.assertEqual(resp, b"\x54")  # Positive response (0x14 + 0x40)
        self.assertEqual(len(self.server.dtc_store), 0)

    def test_clear_specific_group_out_of_range(self):
        resp = self.server.handle_request(b"\x14\x12\x34\x56")  # ليست 0xFFFFFF
        self.assertEqual(resp[0], 0x7F)
        self.assertEqual(resp[2], 0x31)  # requestOutOfRange

    def test_base_services_still_work(self):
        # التأكّد أن الوراثة لم تكسر الخدمات الأساسية
        self.assertEqual(self.server.handle_request(b"\x3E\x00"), b"\x7E\x00")
        self.assertEqual(self.server.handle_request(b"\x10\x03"), b"\x50\x03")
        # 0x27 يبقى مرفوضًا NRC 0x11 (الحدّ الأمني)
        self.assertEqual(self.server.handle_request(b"\x27\x01")[2], 0x11)


if __name__ == "__main__":
    unittest.main()
