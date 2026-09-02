#!/usr/bin/env python3
"""
diag_pipeline.py — مسار تشخيص متكامل: CAN → ISO-TP → UDS → SQLite Evidence.

يربط الطبقات في مسار واحد متصل:
  1. طلب UDS يُجزّأ عبر ISO-TP (FF/CF + تفاوض FC/BS)
  2. كل إطار ISO-TP يُتحقّق منه عبر طبقة CAN (can_interface.validate_frame)
  3. محاكي ECU (UDSServer) يعيد تجميع الطلب ويعالجه
  4. الردّ يُجزّأ عبر ISO-TP ويُعاد تجميعه لدى العميل
  5. الطلب والردّ يُسجَّلان كأدلّة في UDSEvidenceDB

⚖️ محاكاة معزولة. لا عتاد، لا تجاوز حماية.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from isotp import isotp_transfer, ISOTPTransportError
from uds_services import UDSServer
from can_interface import CanFrame, validate_frame
from database import UDSEvidenceDB

SID_NEGATIVE = 0x7F
SUBFUNC_SERVICES = {0x10, 0x3E}   # خدمات تحمل sub-function في البايت الثاني


@dataclass
class DiagResult:
    request: bytes
    response: bytes
    positive: bool
    service_id: int
    response_code: int | None       # NRC إن كان سلبيًا
    tx_frames: int                  # عدد إطارات CAN للطلب
    rx_frames: int                  # عدد إطارات CAN للردّ
    session_id: int


def _validate_can_layer(frames, interface="diag0"):
    """يمرّر كل إطار ISO-TP عبر طبقة CAN للتحقّق — يثبت وصلة CAN→ISO-TP."""
    for f in frames:
        cf = CanFrame(can_id=f["can_id"], dlc=f["dlc"], payload=f["payload"],
                      is_extended=f["is_extended"], direction="TX", interface=interface)
        err = validate_frame(cf)
        if err is not None:
            raise ISOTPTransportError(f"إطار ISO-TP فشل تحقّق طبقة CAN: {err}")


class DiagnosticPipeline:
    """عميل تشخيص متكامل يتخاطب مع محاكي ECU ويسجّل الأدلّة."""

    def __init__(self, db_path: str, ecu: UDSServer | None = None,
                 client_id: int = 0x7E0, ecu_id: int = 0x7E8,
                 bs: int = 0, stmin: int = 0):
        self.ecu = ecu or UDSServer()
        self.client_id, self.ecu_id = client_id, ecu_id
        self.bs, self.stmin = bs, stmin
        self.db = UDSEvidenceDB(db_path)
        self.session_id = self.db.start_session(
            ecu_address=ecu_id, session_type=self.ecu.current_session, source="pipeline")

    @staticmethod
    def _sub_function(payload: bytes) -> int | None:
        sid = payload[0]
        if sid in SUBFUNC_SERVICES and len(payload) > 1:
            return payload[1]
        return None

    def request(self, uds_request: bytes) -> DiagResult:
        # 1) الطلب: عميل → ECU عبر ISO-TP (مع تحقّق طبقة CAN)
        tx = isotp_transfer(uds_request, self.client_id, self.ecu_id,
                            bs=self.bs, stmin=self.stmin)
        _validate_can_layer(tx.tx_frames)
        reassembled_req = tx.message
        if reassembled_req != uds_request:
            raise ISOTPTransportError("الطلب المُعاد تجميعه لا يطابق الأصل")

        # 2) سجّل الطلب (TX)
        self.db.save_diagnostic_exchange(
            session_id=self.session_id, timestamp=time.time(),
            service_id=reassembled_req[0], sub_function=self._sub_function(reassembled_req),
            payload=reassembled_req, direction="TX", response_code=None)

        # 3) ECU يعالج
        uds_response = self.ecu.handle_request(reassembled_req)

        # 4) الردّ: ECU → عميل عبر ISO-TP
        rx = isotp_transfer(uds_response, self.ecu_id, self.client_id,
                            bs=self.bs, stmin=self.stmin)
        _validate_can_layer(rx.tx_frames)
        reassembled_resp = rx.message
        if reassembled_resp != uds_response:
            raise ISOTPTransportError("الردّ المُعاد تجميعه لا يطابق الأصل")

        # 5) فكّ وتسجيل الردّ (RX)
        positive = reassembled_resp[0] != SID_NEGATIVE
        nrc = None if positive else (reassembled_resp[2] if len(reassembled_resp) > 2 else None)
        self.db.save_diagnostic_exchange(
            session_id=self.session_id, timestamp=time.time(),
            service_id=reassembled_resp[0],
            sub_function=self._sub_function(reassembled_resp),
            payload=reassembled_resp, direction="RX", response_code=nrc)

        return DiagResult(
            request=reassembled_req, response=reassembled_resp, positive=positive,
            service_id=reassembled_req[0], response_code=nrc,
            tx_frames=len(tx.tx_frames), rx_frames=len(rx.tx_frames),
            session_id=self.session_id)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
