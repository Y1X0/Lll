#!/usr/bin/env python3
"""
test_can.py — اختبارات Phase 3: تحقّق CAN، تأطير USB، أداء المحاكي، ثبات القاعدة.

التشغيل:  python test_can.py   (أو python -m pytest test_can.py -v)
بيانات اصطناعية فقط — لا مركبة ولا مفاتيح حقيقية.
"""
import os
import tempfile

from can_interface import (
    CanFrame, validate_frame, crc16_ccitt,
    build_packet, PacketParser, serialize_frame, deserialize_frame,
    CanInterface, STD_ID_MAX, EXT_ID_MAX,
)
from can_simulator import CanSimulator, benchmark
from database import CanEvidenceDB


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd); os.unlink(path)
    return path


# ------------------------------------------------ 1) حدود التحقّق
def test_valid_standard_frame():
    f = CanFrame(can_id=0x7FF, dlc=3, payload=b"\x01\x02\x03")
    assert validate_frame(f) is None

def test_valid_extended_frame():
    f = CanFrame(can_id=EXT_ID_MAX, dlc=0, payload=b"", is_extended=True)
    assert validate_frame(f) is None

def test_standard_id_out_of_range():
    f = CanFrame(can_id=STD_ID_MAX + 1, dlc=1, payload=b"\x00")  # 0x800 على معرّف قياسي
    assert validate_frame(f) == "MALFORMED_FRAME"

def test_extended_id_out_of_range():
    f = CanFrame(can_id=EXT_ID_MAX + 1, dlc=0, payload=b"", is_extended=True)
    assert validate_frame(f) == "MALFORMED_FRAME"

def test_dlc_out_of_range():
    f = CanFrame(can_id=0x100, dlc=9, payload=b"\x00" * 9)
    assert validate_frame(f) == "MALFORMED_FRAME"

def test_payload_length_mismatch():
    f = CanFrame(can_id=0x100, dlc=4, payload=b"\x00\x00")  # 2 != 4
    assert validate_frame(f) == "MALFORMED_FRAME"


# ------------------------------------------------ 2) تأطير USB + CRC
def test_crc16_ccitt_known_vector():
    # متجه معياري: CRC-16/CCITT-FALSE على "123456789" = 0x29B1
    assert crc16_ccitt(b"123456789") == 0x29B1

def test_packet_roundtrip():
    f = CanFrame(can_id=0x1AB, dlc=5, payload=b"\xde\xad\xbe\xef\x01",
                 is_extended=False, direction="TX", interface="usb0", timestamp=123.5)
    pkt = build_packet(f)
    assert pkt[0] == 0xAA
    parser = PacketParser()
    frames = parser.feed(pkt)
    assert len(frames) == 1
    g = frames[0]
    assert g.can_id == 0x1AB and g.dlc == 5 and g.payload == b"\xde\xad\xbe\xef\x01"
    assert g.direction == "TX" and abs(g.timestamp - 123.5) < 1e-9

def test_parser_resync_after_garbage():
    f = CanFrame(can_id=0x321, dlc=2, payload=b"\xaa\xbb")
    pkt = build_packet(f)
    parser = PacketParser()
    # ضوضاء قبل الرزمة + بايت 0xAA زائف مضلّل
    frames = parser.feed(b"\x00\xff\xaa\x99" + pkt)
    assert any(x.can_id == 0x321 for x in frames)
    assert parser.framing_errors >= 1

def test_parser_crc_corruption_dropped():
    f = CanFrame(can_id=0x055, dlc=1, payload=b"\x7e")
    pkt = bytearray(build_packet(f))
    pkt[-1] ^= 0xFF  # أفسد CRC
    parser = PacketParser()
    frames = parser.feed(bytes(pkt))
    assert frames == []          # لا يُقبل إطار فاسد CRC
    assert parser.framing_errors >= 1

def test_parser_streaming_split():
    f = CanFrame(can_id=0x123, dlc=3, payload=b"\x11\x22\x33")
    pkt = build_packet(f)
    parser = PacketParser()
    # سلّم الرزمة على أجزاء
    assert parser.feed(pkt[:2]) == []
    assert parser.feed(pkt[2:5]) == []
    frames = parser.feed(pkt[5:])
    assert len(frames) == 1 and frames[0].can_id == 0x123


# ------------------------------------------------ 3) الأداء (500 f/s, zero loss)
def test_throughput_500fps_zero_loss():
    path = _tmp_db()
    try:
        db = CanEvidenceDB(path)
        # 600 إطارًا @500/s ≈ 1.2s — كافٍ لإثبات الاستدامة بلا إبطاء الاختبار
        res = benchmark(count=600, rate_hz=500.0, db=db)
        assert res["dropped_frames"] == 0, "يجب ألا يُفقد أي إطار"
        assert res["stored_frames"] == res["generated_frames"], "كل إطار يُخزَّن"
        assert res["chronological_order"] is True, "ترتيب زمني صحيح"
        assert res["achieved_fps"] >= 450, f"المعدّل الفعلي منخفض: {res['achieved_fps']:.0f}"
        assert db.count("can_frames") == res["generated_frames"]
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_malformed_isolation_does_not_stop_loop():
    path = _tmp_db()
    try:
        db = CanEvidenceDB(path)
        # كل 10 إطارات إطار فاسد — يجب أن تستمر الحلقة ويُعلَّم الفاسد
        res = benchmark(count=100, rate_hz=0 or 2000.0, db=db, malformed_every=10)
        assert res["invalid_frames"] > 0, "يجب اكتشاف إطارات فاسدة"
        assert res["stored_frames"] == res["generated_frames"], "الفاسد يُخزَّن مع error_status لا يُسقط الحلقة"
        # تحقّق أن الفاسد وُسم في القاعدة
        sess = db.get_session(res["capture_id"])
        assert sess["invalid_frames"] == res["invalid_frames"]
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


# ------------------------------------------------ 4) ثبات القاعدة + FK
def test_persistence_and_session_isolation():
    path = _tmp_db()
    try:
        db = CanEvidenceDB(path)
        r1 = benchmark(count=50, rate_hz=0 or 5000.0, db=db, seed=1)
        r2 = benchmark(count=70, rate_hz=0 or 5000.0, db=db, seed=2)
        assert r1["capture_id"] != r2["capture_id"]
        db.close()

        db2 = CanEvidenceDB(path)  # إعادة فتح
        assert db2.count("can_captures") == 2
        assert len(db2.get_frames(r1["capture_id"])) == 50
        assert len(db2.get_frames(r2["capture_id"])) == 70
        db2.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_foreign_key_rejects_orphan():
    path = _tmp_db()
    try:
        db = CanEvidenceDB(path)
        raised = False
        try:
            db.insert_frames(9999, [{
                "timestamp": 1.0, "can_id": 0x100, "is_extended": False,
                "dlc": 1, "payload": b"\x01", "direction": "RX",
                "interface": "sim0", "error_status": None}])
        except Exception:
            raised = True
        assert raised, "FK يجب أن يمنع إطارًا يتيمًا"
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_cascade_delete_frames():
    path = _tmp_db()
    try:
        db = CanEvidenceDB(path)
        r = benchmark(count=30, rate_hz=0 or 5000.0, db=db)
        assert db.count("can_frames") == 30
        with db.conn:
            db.conn.execute("DELETE FROM can_captures WHERE id=?", (r["capture_id"],))
        assert db.count("can_frames") == 0, "CASCADE يحذف الإطارات"
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)


def test_payload_blob_roundtrip():
    path = _tmp_db()
    try:
        db = CanEvidenceDB(path)
        cid = db.start_session("sim0", 500000, "test")
        db.insert_frames(cid, [{
            "timestamp": 9.9, "can_id": 0x7DF, "is_extended": False,
            "dlc": 8, "payload": bytes(range(8)), "direction": "RX",
            "interface": "sim0", "error_status": None}])
        got = db.get_frames(cid)[0]
        assert got["payload"] == bytes(range(8)) and isinstance(got["payload"], bytes)
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)

# ------------------------------------------------ 5) توافق فيرموير ESP32 (بايت-لبايت)
def _firmware_wire_bytes(can_id, is_extended, dlc, payload, direction_byte, ts):
    """يعيد بايتات PAYLOAD تمامًا كما يبنيها esp32_can_bridge.ino (Big-Endian)."""
    import struct
    body = b""
    body += struct.pack(">d", ts)              # timestamp double BE (كما يرسله الفيرموير)
    body += struct.pack(">I", can_id)          # can_id uint32 BE
    body += bytes([1 if is_extended else 0])   # is_extended
    body += bytes([dlc])                       # dlc
    body += bytes([direction_byte])            # direction (0=RX) — الحقل المُصحَّح
    body += bytes(payload)                     # payload
    return body


def test_firmware_wire_layout_parses_on_host():
    """يعيد بناء رزمة كما يرسلها الفيرموير المصحّح، ويتأكّد أن Host يفكّها صحيحة."""
    import struct
    from can_interface import START_BYTE, crc16_ccitt
    payload_bytes = b"\x11\x22\x33"
    body = _firmware_wire_bytes(0x2EF, False, 3, payload_bytes, 0, 12.5)
    assert len(body) == 15 + 3, "ترويسة 15 بايت + الحمولة (بعد إضافة direction)"
    crc = crc16_ccitt(body)
    packet = bytes([START_BYTE]) + struct.pack(">H", len(body)) + body + struct.pack(">H", crc)

    parser = PacketParser()
    frames = parser.feed(packet)
    assert len(frames) == 1, "يجب فكّ إطار واحد صحيح"
    f = frames[0]
    assert f.can_id == 0x2EF and f.dlc == 3 and f.payload == payload_bytes
    assert f.is_extended is False and f.direction == "RX"
    assert abs(f.timestamp - 12.5) < 1e-9, "timestamp يُفكّ كـ double صحيح"
    assert parser.framing_errors == 0


def test_firmware_wrong_layout_would_fail():
    """يثبت أن الأخطاء الثلاثة في فيرموير الـ Architect الأصلي تُنتج فكًّا خاطئًا."""
    import struct
    from can_interface import START_BYTE, crc16_ccitt
    # الخطأ: little-endian + timestamp uint64 + بلا direction (النسخة الأصلية)
    bad = b""
    bad += struct.pack("<Q", 1234567)          # ts كعدد صحيح little-endian
    bad += struct.pack("<I", 0x2EF)            # can_id little-endian
    bad += bytes([0, 3])                       # ext, dlc  (بلا direction)
    bad += b"\x11\x22\x33"
    crc = crc16_ccitt(bad)
    packet = bytes([START_BYTE]) + struct.pack(">H", len(bad)) + bad + struct.pack(">H", crc)
    parser = PacketParser()
    frames = parser.feed(packet)
    # سيُفكّ لكن بقيم خاطئة (can_id/dlc/payload مزاحة) — نثبت عدم التطابق
    if frames:
        assert not (frames[0].can_id == 0x2EF and frames[0].payload == b"\x11\x22\x33"), \
            "التنسيق الخاطئ يجب ألا يعطي القيم الصحيحة"


def test_serial_glue_selftest():
    """جسر الـ Host (process_stream) يبتلع بايتات محاكاة بلا عتاد."""
    import io, os, tempfile
    from serial_capture import process_stream
    from can_interface import build_packet, CanFrame
    frames = [CanFrame(can_id=0x300 + i, dlc=(i % 9), payload=bytes(range(i % 9)),
                       direction="RX", interface="usb0", timestamp=float(i))
              for i in range(25)]
    stream = io.BytesIO(b"".join(build_packet(f) for f in frames))
    def read_chunk():
        b = stream.read(5)
        return b if b else None
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.unlink(path)
    try:
        db = CanEvidenceDB(path)
        m = process_stream(read_chunk, db, "usb0", 500000, "selftest")
        assert m["stored_frames"] == 25 and m["dropped_frames"] == 0
        assert m["framing_errors"] == 0
        db.close()
    finally:
        os.path.exists(path) and os.unlink(path)



if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    raise SystemExit(0 if passed == len(tests) else 1)
