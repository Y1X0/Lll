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
