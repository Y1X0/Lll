"""
ISO-TP (ISO 15765-2) Implementation for Automotive Research Platform.
Handles segmentation, reassembly, and flow control for UDS messages over CAN.
"""

from dataclasses import dataclass
from typing import List, Generator

# Frame Types
N_PCI_SF = 0x0  # Single Frame
N_PCI_FF = 0x1  # First Frame
N_PCI_CF = 0x2  # Consecutive Frame
N_PCI_FC = 0x3  # Flow Control

@dataclass
class ISOTPConfig:
    tx_id: int
    rx_id: int
    bs: int = 0  # Block Size (0 = no limit)
    st_min: int = 0  # Separation Time in ms


class ISOTPSession:
    def __init__(self, config: ISOTPConfig):
        self.config = config

    def encode(self, data: bytes) -> List[dict]:
        """Encodes a payload into ISO-TP CAN frames (Single Frame or Consecutive Frames)."""
        length = len(data)
        frames = []

        if length <= 7:
            # Single Frame
            payload = bytearray([N_PCI_SF << 4 | length]) + data
            # Pad with 0x00 up to 8 bytes if needed (classical CAN)
            while len(payload) < 8:
                payload.append(0x00)
            frames.append({
                "can_id": self.config.tx_id,
                "dlc": 8,
                "payload": bytes(payload),
                "is_extended": False
            })
        else:
            # First Frame + Consecutive Frames
            # FF: 2 bytes PCI (0x1 | high nibble of length, low nibble + rest of length)
            # For simplicity, supporting lengths up to 4095 bytes (12 bits)
            if length > 4095:
                raise ValueError("Payload too large for basic ISO-TP implementation.")

            ff_pci_0 = (N_PCI_FF << 4) | ((length >> 8) & 0x0F)
            ff_pci_1 = length & 0xFF

            ff_data = bytearray([ff_pci_0, ff_pci_1]) + data[0:6]
            while len(ff_data) < 8:
                ff_data.append(0x00)

            frames.append({
                "can_id": self.config.tx_id,
                "dlc": 8,
                "payload": bytes(ff_data),
                "is_extended": False
            })

            # Consecutive Frames
            data_offset = 6
            sn = 1
            while data_offset < length:
                chunk = data[data_offset:data_offset + 7]
                cf_pci = (N_PCI_CF << 4) | (sn & 0x0F)
                cf_data = bytearray([cf_pci]) + chunk
                while len(cf_data) < 8:
                    cf_data.append(0x00)

                frames.append({
                    "can_id": self.config.tx_id,
                    "dlc": 8,
                    "payload": bytes(cf_data),
                    "is_extended": False
                })

                data_offset += 7
                sn = (sn + 1) % 16

        return frames

    def decode_stream(self, raw_frames: List[dict]) -> bytes:
        """Reassembles a sequence of ISO-TP frames back into the original payload."""
        if not raw_frames:
            return b""

        first_frame = raw_frames[0]["payload"]
        pci_type = (first_frame[0] >> 4) & 0x0F

        if pci_type == N_PCI_SF:
            dlc = first_frame[0] & 0x0F
            return bytes(first_frame[1:1 + dlc])

        elif pci_type == N_PCI_FF:
            total_length = ((first_frame[0] & 0x0F) << 8) | first_frame[1]
            reconstructed = bytearray(first_frame[2:8])

            # Append consecutive frames
            for frame in raw_frames[1:]:
                payload = frame["payload"]
                cf_type = (payload[0] >> 4) & 0x0F
                if cf_type == N_PCI_CF:
                    reconstructed.extend(payload[1:])

            return bytes(reconstructed[:total_length])

        else:
            raise ValueError(f"Unsupported or unexpected starting N_PCI type: {pci_type}")


# =====================================================================
# ISO-TP طبقة نقل واعية بالتحكّم في التدفّق (FC/BS) + التحقّق من تسلسل CF.
# إضافة غير مخرِّبة: ISOTPSession أعلاه يبقى كما هو (توافق خلفي كامل).
# =====================================================================

from collections import deque as _deque

# حالات Flow Control (النصف الأدنى من بايت FC)
FS_CTS = 0x0        # Continue To Send
FS_WAIT = 0x1
FS_OVERFLOW = 0x2


class ISOTPTransportError(Exception):
    pass


def _mk(can_id, data, pad=0x00):
    """يبني إطار CAN dict (نفس شكل ISOTPSession) مع حشو 8 بايت."""
    b = bytearray(data)
    while len(b) < 8:
        b.append(pad)
    return {"can_id": can_id, "dlc": 8, "payload": bytes(b), "is_extended": False}


class ISOTPSender:
    """يجزّئ رسالة ويحترم Flow Control (CTS/WAIT/OVERFLOW) و BlockSize و STmin."""

    def __init__(self, tx_id, rx_id, stmin=0, sleep_fn=None):
        self.tx_id, self.rx_id = tx_id, rx_id
        self.stmin = stmin
        self.sleep_fn = sleep_fn        # لاحترام STmin في نقل حقيقي (None = بلا انتظار)
        self.reset()

    def reset(self):
        self.payload = b""
        self.offset = 0
        self.seq = 1
        self.state = "INIT"             # INIT/WAIT_FC/SEND/DONE
        self.bs = 0
        self.block_left = -1

    def begin(self, payload: bytes):
        self.reset()
        self.payload = bytes(payload)

    def on_fc(self, fc_payload: bytes):
        if self.state != "WAIT_FC":
            return
        fs = fc_payload[0] & 0x0F
        if fs == FS_OVERFLOW:
            raise ISOTPTransportError("المستقبِل أبلغ Buffer Overflow")
        if fs == FS_WAIT:
            return
        self.bs = fc_payload[1]
        self.stmin = fc_payload[2]
        self.block_left = self.bs if self.bs > 0 else -1
        self.state = "SEND"

    def next_frame(self):
        """يعيد إطار CAN dict التالي أو None (منتظِر FC / منتهٍ)."""
        n = len(self.payload)
        if self.state == "INIT":
            if n <= 7:
                self.state = "DONE"
                return _mk(self.tx_id, bytes([(N_PCI_SF << 4) | n]) + self.payload)
            if n > 4095:
                raise ISOTPTransportError("الرسالة تتجاوز 4095 بايت")
            self.offset = 6
            self.state = "WAIT_FC"
            ff = bytes([(N_PCI_FF << 4) | ((n >> 8) & 0x0F), n & 0xFF]) + self.payload[:6]
            return _mk(self.tx_id, ff)
        if self.state == "SEND":
            if self.stmin and self.sleep_fn:
                self.sleep_fn(self.stmin / 1000.0)
            chunk = self.payload[self.offset:self.offset + 7]
            frame = _mk(self.tx_id, bytes([(N_PCI_CF << 4) | (self.seq & 0x0F)]) + chunk)
            self.offset += len(chunk)
            self.seq = (self.seq + 1) & 0x0F
            if self.offset >= n:
                self.state = "DONE"
            elif self.block_left > 0:
                self.block_left -= 1
                if self.block_left == 0:
                    self.state = "WAIT_FC"
            return frame
        return None

    @property
    def done(self):
        return self.state == "DONE"


class ISOTPReceiver:
    """يعيد تجميع الإطارات، يتحقّق من تسلسل CF، ويصدر FC حسب BlockSize."""

    def __init__(self, tx_id, rx_id, bs=0, stmin=0):
        self.tx_id, self.rx_id = tx_id, rx_id    # tx_id = عنوان إرسال FC
        self.bs, self.stmin = bs, stmin
        self.reset()

    def reset(self):
        self.buf = bytearray()
        self.expected = 0
        self.seq = 1
        self.state = "IDLE"
        self.block_count = 0
        self.message = None

    def _fc(self, fs=FS_CTS):
        return _mk(self.tx_id, bytes([(N_PCI_FC << 4) | fs, self.bs & 0xFF, self.stmin & 0xFF]))

    def on_frame(self, frame):
        """يستقبل إطار CAN dict. يعيد (message_or_None, fc_frame_or_None)."""
        data = frame["payload"]
        ptype = (data[0] >> 4) & 0x0F
        if ptype == N_PCI_SF:
            n = data[0] & 0x0F
            self.message = bytes(data[1:1 + n])
            self.state = "DONE"
            return self.message, None
        if ptype == N_PCI_FF:
            self.expected = ((data[0] & 0x0F) << 8) | data[1]
            self.buf = bytearray(data[2:8])
            self.seq = 1
            self.block_count = 0
            self.state = "RECV"
            return None, self._fc(FS_CTS)
        if ptype == N_PCI_CF:
            if self.state != "RECV":
                raise ISOTPTransportError("CF غير متوقّع (بلا First Frame)")
            sn = data[0] & 0x0F
            if sn != self.seq:
                raise ISOTPTransportError(
                    f"تسلسل CF خاطئ: متوقّع {self.seq} ورد {sn} (فقد/إعادة ترتيب إطار)")
            remaining = self.expected - len(self.buf)
            self.buf += data[1:1 + min(7, remaining)]
            self.seq = (self.seq + 1) & 0x0F
            if len(self.buf) >= self.expected:
                self.message = bytes(self.buf[:self.expected])
                self.state = "DONE"
                return self.message, None
            if self.bs > 0:
                self.block_count += 1
                if self.block_count >= self.bs:
                    self.block_count = 0
                    return None, self._fc(FS_CTS)     # نهاية الكتلة → اطلب التالية
            return None, None
        raise ISOTPTransportError(f"نوع PCI غير متوقّع: {ptype}")

    @property
    def done(self):
        return self.state == "DONE"


class ISOTPResult:
    def __init__(self, message, tx_frames, fc_frames):
        self.message = message
        self.tx_frames = tx_frames        # إطارات البيانات المُرسَلة (CAN dicts)
        self.fc_frames = fc_frames        # عدد إطارات Flow Control المتبادلة


def isotp_transfer(payload: bytes, tx_id: int, rx_id: int,
                   bs: int = 0, stmin: int = 0, sleep_fn=None) -> ISOTPResult:
    """
    ينقل payload كاملًا عبر ISO-TP (FF/CF + تفاوض FC/BS) في الذاكرة،
    ويتحقّق من تسلسل CF. يعيد ISOTPResult(message, tx_frames, fc_frames).
    """
    sender = ISOTPSender(tx_id, rx_id, stmin=stmin, sleep_fn=sleep_fn)
    receiver = ISOTPReceiver(tx_id=rx_id, rx_id=tx_id, bs=bs, stmin=stmin)
    sender.begin(payload)
    tx_frames = []
    fc_count = 0
    guard = 0
    while not (sender.done and receiver.done):
        guard += 1
        if guard > 100000:
            raise ISOTPTransportError("تجاوز حدّ الخطوات (deadlock محتمل)")
        frame = sender.next_frame()
        if frame is not None:
            tx_frames.append(frame)
            msg, fc = receiver.on_frame(frame)
            if fc is not None:
                fc_count += 1
                sender.on_fc(fc["payload"])
            continue
        # المُرسِل لا ينتج إطارًا: إمّا منتظِر FC (وصل أعلاه) أو منتهٍ
        if not sender.done:
            raise ISOTPTransportError("توقّف الإرسال بانتظار FC لم يصل")
    if not receiver.done:
        raise ISOTPTransportError("لم يكتمل التجميع")
    return ISOTPResult(receiver.message, tx_frames, fc_count)
