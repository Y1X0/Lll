"""
UDS (ISO 14229) Services Implementation for Academic Automotive Research.
"""

# UDS Service IDs (Request / Response SID offset is +0x40)
SID_DIAGNOSTIC_SESSION_CONTROL = 0x10
SID_READ_DATA_BY_IDENTIFIER = 0x22
SID_TESTER_PRESENT = 0x3E

# Response Offset
RESPONSE_SID_OFFSET = 0x40

# Negative Response Code (NRC)
NRC_GENERAL_REJECT = 0x10
NRC_SERVICE_NOT_SUPPORTED = 0x11
NRC_SUB_FUNCTION_NOT_SUPPORTED = 0x12
NRC_CONDITIONS_NOT_CORRECT = 0x22


class UDSServer:
    def __init__(self):
        # Simulated Electronic Control Unit (ECU) Data Store
        self.data_store = {
            0xF190: b"VIN-SIMULATOR-001",
            0xF187: b"ECU-HW-REV-2.0",
            0xF188: b"SW-FIRMWARE-1.4"
        }
        self.current_session = 0x01  # Default session

    def handle_request(self, request_payload: bytes) -> bytes:
        """Parses and processes an incoming UDS request payload, returning the response."""
        if not request_payload:
            return bytes([0x7F, 0x00, NRC_GENERAL_REJECT])

        sid = request_payload[0]

        if sid == SID_DIAGNOSTIC_SESSION_CONTROL:
            return self._handle_session_control(request_payload)
        elif sid == SID_READ_DATA_BY_IDENTIFIER:
            return self._handle_read_data(request_payload)
        elif sid == SID_TESTER_PRESENT:
            return self._handle_tester_present(request_payload)
        else:
            return bytes([0x7F, sid, NRC_SERVICE_NOT_SUPPORTED])

    def _handle_session_control(self, payload: bytes) -> bytes:
        if len(payload) < 2:
            return bytes([0x7F, SID_DIAGNOSTIC_SESSION_CONTROL, NRC_CONDITIONS_NOT_CORRECT])

        sub_func = payload[1]
        if sub_func in (0x01, 0x02, 0x03):  # Default, Programming, Extended sessions
            self.current_session = sub_func
            return bytes([SID_DIAGNOSTIC_SESSION_CONTROL + RESPONSE_SID_OFFSET, sub_func])
        else:
            return bytes([0x7F, SID_DIAGNOSTIC_SESSION_CONTROL, NRC_SUB_FUNCTION_NOT_SUPPORTED])

    def _handle_read_data(self, payload: bytes) -> bytes:
        if len(payload) < 3:
            return bytes([0x7F, SID_READ_DATA_BY_IDENTIFIER, NRC_CONDITIONS_NOT_CORRECT])

        did = (payload[1] << 8) | payload[2]
        if did in self.data_store:
            data = self.data_store[did]
            response = bytearray([SID_READ_DATA_BY_IDENTIFIER + RESPONSE_SID_OFFSET, payload[1], payload[2]])
            response.extend(data)
            return bytes(response)
        else:
            # Request out of range or unsupported DID
            return bytes([0x7F, SID_READ_DATA_BY_IDENTIFIER, 0x31])

    def _handle_tester_present(self, payload: bytes) -> bytes:
        if len(payload) < 2:
            return bytes([0x7F, SID_TESTER_PRESENT, NRC_CONDITIONS_NOT_CORRECT])

        sub_func = payload[1]
        if sub_func == 0x00:
            return bytes([SID_TESTER_PRESENT + RESPONSE_SID_OFFSET, 0x00])
        else:
            return bytes([0x7F, SID_TESTER_PRESENT, NRC_SUB_FUNCTION_NOT_SUPPORTED])
