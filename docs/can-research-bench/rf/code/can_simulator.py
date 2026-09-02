#!/usr/bin/env python3
"""
can_simulator.py — مولّد إطارات CAN برمجي + مقياس أداء (throughput harness).

Pure Python، بلا python-can. يولّد إطارات صحيحة (وعند الطلب فاسدة عمدًا لاختبار
عزل الأخطاء)، مع ضبط معدّل زمني اختياري (pacing) عبر time.monotonic().

⚖️ بيانات اصطناعية في الذاكرة فقط. لا اتصال بمركبة، لا ISO-TP/UDS.
"""
from __future__ import annotations

import random
import time
from typing import Iterator, Optional

from can_interface import CanFrame


class CanSimulator:
    """يولّد تدفّق إطارات اختبار قابل للتكرار (seed) بمعدّل مضبوط."""

    def __init__(self, interface: str = "sim0", seed: Optional[int] = None):
        self.interface = interface
        self.rng = random.Random(seed)
        self.generated_frames = 0

    def _make_frame(self, i: int, malformed: bool = False) -> CanFrame:
        ext = (i % 5 == 0)
        can_id = self.rng.randint(0, 0x1FFFFFFF if ext else 0x7FF)
        dlc = self.rng.randint(0, 8)
        payload = bytes(self.rng.getrandbits(8) for _ in range(dlc))
        if malformed:
            # اجعل طول الحمولة لا يطابق DLC (حالة MALFORMED_FRAME)
            payload = payload + b"\x00"
        return CanFrame(
            can_id=can_id, dlc=dlc, payload=payload, is_extended=ext,
            direction="RX", interface=self.interface, timestamp=time.time(),
        )

    def stream(self, count: int, rate_hz: Optional[float] = None,
               malformed_every: int = 0) -> Iterator[CanFrame]:
        """يولّد `count` إطارًا. rate_hz=معدّل مستهدف (None=أقصى سرعة).
        malformed_every=N ⇒ كل N إطارًا يكون فاسدًا (0=لا فاسد)."""
        interval = (1.0 / rate_hz) if rate_hz else 0.0
        next_t = time.monotonic()
        for i in range(count):
            if interval:
                now = time.monotonic()
                if now < next_t:
                    time.sleep(next_t - now)
                next_t += interval
            bad = bool(malformed_every) and (i % malformed_every == 0)
            self.generated_frames += 1
            yield self._make_frame(i, malformed=bad)


def benchmark(count: int, rate_hz: float, db, interface: str = "sim0",
              bitrate: int = 500000, batch_size: int = 200,
              malformed_every: int = 0, seed: int = 42) -> dict:
    """يشغّل جلسة كاملة (محاكاة → واجهة → قاعدة) ويعيد المقاييس والأداء الفعلي."""
    from can_interface import CanInterface  # تجنّب دورة استيراد

    sim = CanSimulator(interface=interface, seed=seed)
    cap_id = db.start_session(interface=interface, bitrate=bitrate, source="simulator")
    iface = CanInterface(db, cap_id, batch_size=batch_size)

    t0 = time.monotonic()
    prev_ts = None
    ordered = True
    for frame in sim.stream(count, rate_hz=rate_hz, malformed_every=malformed_every):
        if prev_ts is not None and frame.timestamp < prev_ts:
            ordered = False
        prev_ts = frame.timestamp
        iface.ingest(frame)
    iface.finalize()
    elapsed = time.monotonic() - t0

    m = iface.metrics()
    m.update({
        "capture_id": cap_id,
        "generated_frames": sim.generated_frames,
        "elapsed_s": elapsed,
        "achieved_fps": (sim.generated_frames / elapsed) if elapsed > 0 else float("inf"),
        "chronological_order": ordered,
    })
    return m


if __name__ == "__main__":
    import argparse
    from database import CanEvidenceDB

    ap = argparse.ArgumentParser(description="مقياس أداء محاكي CAN")
    ap.add_argument("--count", type=int, default=2000)
    ap.add_argument("--rate", type=float, default=500.0, help="إطار/ثانية مستهدف")
    ap.add_argument("--db", default="can_evidence.db")
    ap.add_argument("--malformed-every", type=int, default=0)
    args = ap.parse_args()

    with CanEvidenceDB(args.db) as db:
        res = benchmark(args.count, args.rate, db,
                        malformed_every=args.malformed_every)
    for k, v in res.items():
        print(f"  {k}: {v}")
