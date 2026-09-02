#!/usr/bin/env python3
"""
serial_capture.py — الجسر الناقص: يقرأ منفذ ESP32 التسلسلي، يفكّ التأطير عبر
PacketParser، ويبتلع الإطارات إلى SQLite عبر CanInterface.

⚖️ مقعد معزول، عتاد مملوك. تنصّت فقط.

الاستخدام (على العتاد):
    python serial_capture.py --port /dev/ttyUSB0 --baud 2000000 --db can_evidence.db

اختبار المنطق بلا عتاد (يغذّي بايتات محاكاة عبر نفس دالة المعالجة):
    python serial_capture.py --selftest
"""
import argparse
import sys
import time

from can_interface import PacketParser, CanInterface, build_packet, CanFrame
from database import CanEvidenceDB


def process_stream(read_chunk, db, interface_name, bitrate, source,
                   idle_limit=None, on_metrics=None):
    """
    حلقة معالجة عامة: تستدعي read_chunk() للحصول على بايتات، تفكّ وتبتلع.
    read_chunk() تعيد bytes (قد تكون فارغة) أو None للإنهاء.
    idle_limit: ثوانٍ بلا بيانات قبل التوقّف (None = بلا حدّ).
    """
    parser = PacketParser(interface=interface_name)
    cap_id = db.start_session(interface=interface_name, bitrate=bitrate, source=source)
    iface = CanInterface(db, cap_id, batch_size=100)
    last_data = time.monotonic()
    try:
        while True:
            chunk = read_chunk()
            if chunk is None:
                break
            if chunk:
                last_data = time.monotonic()
                for frame in parser.feed(chunk):
                    iface.ingest(frame)
            elif idle_limit is not None and (time.monotonic() - last_data) > idle_limit:
                break
    finally:
        iface.finalize()
    m = iface.metrics()
    m["capture_id"] = cap_id
    m["framing_errors"] = parser.framing_errors
    if on_metrics:
        on_metrics(m)
    return m


def run_serial(port, baud, db_path, interface_name, bitrate, idle_limit):
    try:
        import serial  # pyserial
    except ImportError:
        sys.exit("pyserial غير مثبّتة. ثبّت: pip install pyserial")
    ser = serial.Serial(port, baud, timeout=0.1)

    def read_chunk():
        return ser.read(4096)  # يعيد b"" عند المهلة

    with CanEvidenceDB(db_path) as db:
        return process_stream(read_chunk, db, interface_name, bitrate,
                              source=f"esp32:{port}", idle_limit=idle_limit,
                              on_metrics=lambda m: print("[metrics]", m))


def _selftest():
    """يثبت أن حلقة القراءة/الفكّ/الابتلاع تعمل بلا عتاد، ببايتات محاكاة."""
    import io, os, tempfile
    # ابنِ تدفّق بايتات كما سيرسله ESP32 (عبر build_packet نفسه = نفس التنسيق)
    frames = [CanFrame(can_id=0x100 + i, dlc=(i % 9),
                       payload=bytes(range(i % 9)), direction="RX",
                       interface="usb0", timestamp=float(i))
              for i in range(20)]
    stream = io.BytesIO(b"".join(build_packet(f) for f in frames))

    def read_chunk():
        b = stream.read(7)      # أجزاء صغيرة لاختبار إعادة التجميع
        return b if b else None

    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.unlink(path)
    try:
        with CanEvidenceDB(path) as db:
            m = process_stream(read_chunk, db, "usb0", 500000, "selftest")
            assert m["stored_frames"] == 20, m
            assert m["dropped_frames"] == 0 and m["framing_errors"] == 0, m
            print("SELFTEST PASS:", m)
    finally:
        os.path.exists(path) and os.unlink(path)


def main():
    ap = argparse.ArgumentParser(description="جسر ESP32 التسلسلي → SQLite")
    ap.add_argument("--port", help="منفذ تسلسلي، مثل /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=2000000)
    ap.add_argument("--db", default="can_evidence.db")
    ap.add_argument("--interface", default="usb0")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--idle", type=float, default=None, help="توقّف بعد N ثانية بلا بيانات")
    ap.add_argument("--selftest", action="store_true", help="اختبار المنطق بلا عتاد")
    args = ap.parse_args()

    if args.selftest:
        _selftest(); return
    if not args.port:
        sys.exit("مرّر --port أو --selftest")
    run_serial(args.port, args.baud, args.db, args.interface, args.bitrate, args.idle)


if __name__ == "__main__":
    main()
