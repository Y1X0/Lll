#!/usr/bin/env python3
"""
can_interface.py — طبقة استقبال CAN: تحقّق، تحليل (parsing)، ابتلاع (ingestion)،
وتأطير USB (Phase 3B). Pure Python — بلا اعتماديات خارجية.

⚖️ مقعد اختبار/محاكاة معزول. لا ISO-TP ولا UDS ولا SecurityAccess (Phase 4+).
    هذه الطبقة تلتقط وتتحقّق وتخزّن الإطارات فقط.
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Optional


# ----------------------------------------------------------- حدود التحقّق
STD_ID_MAX = 0x7FF
EXT_ID_MAX = 0x1FFFFFFF
DLC_MAX = 8

START_BYTE = 0xAA
MAX_PACKET_PAYLOAD = 32  # حدّ تسلسل الإطار على السلك (Phase 3B)


@dataclass
class CanFrame:
    can_id: int
    dlc: int
    payload: bytes
    is_extended: bool = False
    direction: str = "RX"           # 'RX' | 'TX'
    interface: str = "sim0"
    timestamp: float = field(default_factory=time.time)

    def to_row(self, error_status: Optional[str] = None) -> dict:
        return {
            "timestamp": self.timestamp,
            "can_id": self.can_id,
            "is_extended": self.is_extended,
            "dlc": self.dlc,
            "payload": bytes(self.payload),
            "direction": self.direction,
            "interface": self.interface,
            "error_status": error_status,
        }


# ------------------------------------------------------------- التحقّق
def validate_frame(frame: CanFrame) -> Optional[str]:
    """يعيد None إن كان الإطار سليمًا، وإلا سلسلة سبب الرفض."""
    if frame.direction not in ("RX", "TX"):
        return "MALFORMED_FRAME"  # اتجاه غير صالح
    id_max = EXT_ID_MAX if frame.is_extended else STD_ID_MAX
    if not (0 <= frame.can_id <= id_max):
        return "MALFORMED_FRAME"  # معرّف خارج المدى
    if not (0 <= frame.dlc <= DLC_MAX):
        return "MALFORMED_FRAME"  # DLC خارج 0..8
    if len(frame.payload) != frame.dlc:
        return "MALFORMED_FRAME"  # طول الحمولة لا يطابق DLC
    return None


# ------------------------------------------------- CRC-16-CCITT (0x1021)
def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


# --------------------------------------------- تسلسل الإطار (Big-Endian)
# التنسيق المعبّأ:  >d I B B B  ثم payload (dlc بايت)
#   timestamp(64-bit float) · can_id(32-bit) · is_extended(8) · dlc(8) · direction(8: 0=RX,1=TX)
# ملاحظة deviation موثّقة: interface (سلسلة) لا يُدرج في إطار السلك للبقاء ضمن حدّ 32 بايت؛
#   interface خاصية جلسة الالتقاط (can_captures)، لا خاصية كل إطار على السلك.
_HDR = struct.Struct(">dIBBB")
_DIR_ENC = {"RX": 0, "TX": 1}
_DIR_DEC = {0: "RX", 1: "TX"}


def serialize_frame(frame: CanFrame) -> bytes:
    body = _HDR.pack(
        frame.timestamp, frame.can_id,
        1 if frame.is_extended else 0, frame.dlc,
        _DIR_ENC[frame.direction],
    ) + bytes(frame.payload)
    if len(body) > MAX_PACKET_PAYLOAD:
        raise ValueError("تسلسل الإطار يتجاوز حدّ 32 بايت")
    return body


def deserialize_frame(body: bytes, interface: str = "usb0") -> CanFrame:
    ts, can_id, ext, dlc, direction = _HDR.unpack_from(body, 0)
    payload = body[_HDR.size:_HDR.size + dlc]
    return CanFrame(
        can_id=can_id, dlc=dlc, payload=payload,
        is_extended=bool(ext), direction=_DIR_DEC.get(direction, "RX"),
        interface=interface, timestamp=ts,
    )


# --------------------------------------------- تأطير USB (Phase 3B)
def build_packet(frame: CanFrame) -> bytes:
    """[START][LEN_MSB][LEN_LSB][PAYLOAD][CRC_MSB][CRC_LSB] — LEN=طول PAYLOAD، CRC على PAYLOAD."""
    payload = serialize_frame(frame)
    crc = crc16_ccitt(payload)
    return bytes([START_BYTE]) + struct.pack(">H", len(payload)) + payload + struct.pack(">H", crc)


class PacketParser:
    """محلّل تدفّق بايتات مع إعادة مزامنة على 0xAA وتجاهل الإطارات الفاسدة."""

    def __init__(self, interface: str = "usb0"):
        self.buf = bytearray()
        self.interface = interface
        self.framing_errors = 0

    def feed(self, chunk: bytes) -> list[CanFrame]:
        """يبتلع بايتات ويعيد الإطارات المكتملة الصحيحة. الفاسد يُتجاهل مع إعادة مزامنة."""
        self.buf.extend(chunk)
        out: list[CanFrame] = []
        while True:
            # ابحث عن بايت البداية
            start = self.buf.find(START_BYTE)
            if start < 0:
                self.buf.clear()
                return out
            if start > 0:
                # بايتات قبل البداية = ضوضاء → أسقطها
                self.framing_errors += 1
                del self.buf[:start]
            if len(self.buf) < 3:
                return out  # ننتظر حقل الطول
            length = struct.unpack_from(">H", self.buf, 1)[0]
            total = 1 + 2 + length + 2
            if length > MAX_PACKET_PAYLOAD:
                # طول غير معقول → أعد المزامنة بعد أول 0xAA
                self.framing_errors += 1
                del self.buf[:1]
                continue
            if len(self.buf) < total:
                return out  # ننتظر بقية الرزمة
            payload = bytes(self.buf[3:3 + length])
            crc_rx = struct.unpack_from(">H", self.buf, 3 + length)[0]
            if crc16_ccitt(payload) != crc_rx:
                self.framing_errors += 1
                del self.buf[:1]  # تجاهل بايت البداية وأعد البحث
                continue
            try:
                out.append(deserialize_frame(payload, self.interface))
            except Exception:
                self.framing_errors += 1
            del self.buf[:total]


# ------------------------------------------------- محرّك الابتلاع
class CanInterface:
    """يستقبل إطارات، يتحقّق، ويخزّن دفعات في SQLite مع تتبّع المقاييس."""

    def __init__(self, db, capture_id: int, batch_size: int = 200,
                 max_queue: Optional[int] = None):
        self.db = db
        self.capture_id = capture_id
        self.batch_size = batch_size
        self.max_queue = max_queue           # None = بلا حدّ (لا إسقاط)
        self._pending: list[dict] = []
        # المقاييس
        self.received_frames = 0
        self.stored_frames = 0
        self.dropped_frames = 0
        self.invalid_frames = 0

    def ingest(self, frame: CanFrame) -> None:
        """يبتلع إطارًا واحدًا: تحقّق → تخزين (أو تعليم خطأ) دون كسر الحلقة."""
        self.received_frames += 1
        # محاكاة استنفاد المخزن المؤقّت (إن حُدّد حدّ)
        if self.max_queue is not None and len(self._pending) >= self.max_queue:
            self.dropped_frames += 1
            return
        err = validate_frame(frame)
        if err is not None:
            self.invalid_frames += 1
        self._pending.append(frame.to_row(error_status=err))
        if len(self._pending) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if self._pending:
            n = self.db.insert_frames(self.capture_id, self._pending)
            self.stored_frames += n
            self._pending.clear()

    def finalize(self) -> None:
        self.flush()
        self.db.update_counters(self.capture_id, self.dropped_frames, self.invalid_frames)

    def metrics(self) -> dict:
        return {
            "received_frames": self.received_frames,
            "stored_frames": self.stored_frames,
            "dropped_frames": self.dropped_frames,
            "invalid_frames": self.invalid_frames,
        }
