"""
Unit tests for ISO-TP and UDS protocol layers.
"""

import unittest
from isotp import ISOTPConfig, ISOTPSession
from uds_services import UDSServer


class TestISOTPAndUDS(unittest.TestCase):

    def setUp(self):
        self.config = ISOTPConfig(tx_id=0x7E0, rx_id=0x7E8)
        self.isotp = ISOTPSession(self.config)
        self.uds_server = UDSServer()

    def test_single_frame_encoding_decoding(self):
        payload = b"\x10\x03"  # Short UDS request
        frames = self.isotp.encode(payload)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["can_id"], 0x7E0)

        reconstructed = self.isotp.decode_stream(frames)
        self.assertEqual(reconstructed, payload)

    def test_multi_frame_segmentation_reassembly(self):
        # Create a payload longer than 7 bytes to force multi-frame ISO-TP
        payload = b"\x22\xF1\x90" + b"X" * 20  # ReadDataByIdentifier + long data
        frames = self.isotp.encode(payload)

        # Should be First Frame + multiple Consecutive Frames
        self.assertGreater(len(frames), 1)

        reconstructed = self.isotp.decode_stream(frames)
        self.assertEqual(reconstructed, payload)

    def test_uds_diagnostic_session_control(self):
        # Request Extended Diagnostic Session (0x10 0x03)
        req = b"\x10\x03"
        resp = self.uds_server.handle_request(req)

        self.assertEqual(resp, b"\x50\x03")
        self.assertEqual(self.uds_server.current_session, 0x03)

    def test_uds_read_data_by_identifier(self):
        # Read VIN (0x22 0xF1 0x90)
        req = b"\x22\xF1\x90"
        resp = self.uds_server.handle_request(req)

        self.assertEqual(resp[0], 0x62)  # Positive response SID
        self.assertEqual(resp[1:3], b"\xF1\x90")  # DID
        self.assertEqual(resp[3:], b"VIN-SIMULATOR-001")

    def test_uds_tester_present(self):
        req = b"\x3E\x00"
        resp = self.uds_server.handle_request(req)
        self.assertEqual(resp, b"\x7E\x00")


if __name__ == "__main__":
    unittest.main()
