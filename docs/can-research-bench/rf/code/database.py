#!/usr/bin/env python3
"""
database.py — طبقة تخزين الأدلّة (Evidence Store) على SQLite لتحليلات RF.

مستقلّة تمامًا: تدير الاتصال، تنشئ الجداول تلقائيًا عبر DDL، وتنفّذ الإدخال
المعاملاتي (Transactions) لبيانات الالتقاط (captures) والنبضات (pulses).

مبادئ:
  - تفعيل مفاتيح الأجنبي (PRAGMA foreign_keys=ON) على كل اتصال — إلزامي في SQLite.
  - إدخال الالتقاط + نبضاته في معاملة واحدة (ذرّية: الكل أو لا شيء).
  - قابلة للاستخدام كسياق (context manager) لضمان الإغلاق النظيف.

⚖️ تخزين أدلّة تحليل إشارة مملوكة لأغراض بحثية/أكاديمية. لا يخزّن ولا يولّد
    أي محتوى إرسال — بيانات تحليل استقبال فقط.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    sample_rate REAL NOT NULL,
    sample_format TEXT NOT NULL,
    num_samples INTEGER NOT NULL,
    duration REAL NOT NULL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pulses_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id INTEGER NOT NULL,
    pulse_index INTEGER NOT NULL,
    start_sample INTEGER NOT NULL,
    end_sample INTEGER NOT NULL,
    width_samples INTEGER NOT NULL,
    width_seconds REAL NOT NULL,
    gap_seconds REAL,
    FOREIGN KEY (capture_id) REFERENCES captures (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pulses_capture ON pulses_analysis (capture_id);
"""


class EvidenceDB:
    """واجهة تخزين الأدلّة على SQLite."""

    def __init__(self, path: str = "rf_evidence.db"):
        self.path = path
        # check_same_thread=False يسمح بالاستخدام في اختبارات متعدّدة؛ الوصول متسلسل هنا
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA)

    # ----------------------------------------------------------- كتابة
    def insert_capture(
        self,
        file_path: str,
        sample_rate: float,
        sample_format: str,
        num_samples: int,
        source: str,
        timestamp: Optional[str] = None,
    ) -> int:
        """يُدخل سجلّ التقاط ويعيد معرّفه. المدّة تُحسب من العيّنات والمعدّل."""
        if sample_rate <= 0:
            raise ValueError("sample_rate يجب أن يكون موجبًا")
        if num_samples < 0:
            raise ValueError("num_samples لا يمكن أن يكون سالبًا")
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        duration = num_samples / sample_rate
        with self.conn:  # معاملة ذرّية
            cur = self.conn.execute(
                """INSERT INTO captures
                   (file_path, timestamp, sample_rate, sample_format,
                    num_samples, duration, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (file_path, ts, sample_rate, sample_format,
                 num_samples, duration, source),
            )
            return int(cur.lastrowid)

    def insert_pulses(self, capture_id: int, pulses: Iterable[dict]) -> int:
        """يُدخل نبضات مرتبطة بالتقاط، في معاملة واحدة. يعيد العدد المُدخل."""
        rows = []
        for p in pulses:
            rows.append((
                capture_id,
                int(p["pulse_index"]),
                int(p["start_sample"]),
                int(p["end_sample"]),
                int(p["width_samples"]),
                float(p["width_seconds"]),
                None if p.get("gap_seconds") is None else float(p["gap_seconds"]),
            ))
        with self.conn:  # ذرّية: الكل أو لا شيء
            self.conn.executemany(
                """INSERT INTO pulses_analysis
                   (capture_id, pulse_index, start_sample, end_sample,
                    width_samples, width_seconds, gap_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        return len(rows)

    def save_analysis(
        self, file_path: str, sample_rate: float, sample_format: str,
        num_samples: int, source: str, pulses: Iterable[dict],
        timestamp: Optional[str] = None,
    ) -> int:
        """يحفظ التقاطًا ونبضاته معًا ذرّيًا ويعيد capture_id."""
        cid = self.insert_capture(
            file_path, sample_rate, sample_format, num_samples, source, timestamp
        )
        self.insert_pulses(cid, pulses)
        return cid

    # ----------------------------------------------------------- قراءة
    def get_capture(self, capture_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_pulses(self, capture_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM pulses_analysis WHERE capture_id = ? ORDER BY pulse_index",
            (capture_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self, table: str) -> int:
        if table not in ("captures", "pulses_analysis"):
            raise ValueError("جدول غير معروف")
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    # ----------------------------------------------------------- دورة الحياة
    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "EvidenceDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


@contextmanager
def open_db(path: str = "rf_evidence.db"):
    db = EvidenceDB(path)
    try:
        yield db
    finally:
        db.close()


# ----------------------------------------------------- مساعد تحويل النبضات
def pulses_from_runs(runs, fs: float) -> list[dict]:
    """
    يحوّل مخرج run_lengths (قائمة (level, length)) إلى سجلّات نبضات عالية،
    مع حساب start/end/width والفجوة (gap) حتى النبضة العالية التالية.
    """
    pulses = []
    # ابنِ حدود العيّنات لكل عنقود
    pos = 0
    spans = []  # (level, start, end_inclusive, length)
    for level, ln in runs:
        spans.append((level, pos, pos + ln - 1, ln))
        pos += ln

    highs = [s for s in spans if s[0] == 1]
    for idx, (level, start, end, ln) in enumerate(highs):
        # الفجوة = المسافة من نهاية هذه النبضة إلى بداية النبضة العالية التالية
        gap_seconds = None
        if idx + 1 < len(highs):
            next_start = highs[idx + 1][1]
            gap_seconds = (next_start - (end + 1)) / fs
        pulses.append({
            "pulse_index": idx,
            "start_sample": start,
            "end_sample": end,
            "width_samples": ln,
            "width_seconds": ln / fs,
            "gap_seconds": gap_seconds,
        })
    return pulses


# =====================================================================
# CAN Evidence Storage (Phase 3) — معزول تمامًا عن جداول RF أعلاه.
# جداول captures/pulses_analysis تبقى دون أي مساس.
# =====================================================================

CAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS can_captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    interface TEXT NOT NULL,
    bitrate INTEGER NOT NULL,
    dropped_frames INTEGER NOT NULL DEFAULT 0,
    invalid_frames INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS can_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    can_id INTEGER NOT NULL,
    is_extended INTEGER NOT NULL CHECK (is_extended IN (0, 1)),
    dlc INTEGER NOT NULL CHECK (dlc BETWEEN 0 AND 8),
    payload BLOB NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('RX', 'TX')),
    interface TEXT NOT NULL,
    error_status TEXT,
    FOREIGN KEY (capture_id) REFERENCES can_captures (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_can_frames_capture_id ON can_frames(capture_id);
CREATE INDEX IF NOT EXISTS idx_can_frames_can_id ON can_frames(can_id);
"""


class CanEvidenceDB:
    """تخزين أدلّة CAN على SQLite — مستقلّ عن EvidenceDB (RF)، بنفس الملف أو ملف منفصل."""

    def __init__(self, path: str = "can_evidence.db"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        with self.conn:
            self.conn.executescript(CAN_SCHEMA)

    # --------------------------------------------------------- جلسة الالتقاط
    def start_session(self, interface: str, bitrate: int, source: str,
                      timestamp: Optional[str] = None) -> int:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO can_captures
                   (timestamp, interface, bitrate, dropped_frames, invalid_frames, source)
                   VALUES (?, ?, ?, 0, 0, ?)""",
                (ts, interface, int(bitrate), source),
            )
            return int(cur.lastrowid)

    def update_counters(self, capture_id: int, dropped: int, invalid: int) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE can_captures SET dropped_frames=?, invalid_frames=? WHERE id=?",
                (int(dropped), int(invalid), capture_id),
            )

    # --------------------------------------------------------- إدخال الإطارات
    def insert_frames(self, capture_id: int, frames: Iterable[dict]) -> int:
        """إدخال دفعة إطارات في معاملة واحدة. يعيد العدد المُدخَل.

        كل إطار dict: timestamp, can_id, is_extended(bool/0-1), dlc,
        payload(bytes), direction('RX'/'TX'), interface, error_status(اختياري).
        """
        rows = []
        for f in frames:
            rows.append((
                capture_id,
                float(f["timestamp"]),
                int(f["can_id"]),
                1 if f["is_extended"] else 0,
                int(f["dlc"]),
                bytes(f["payload"]),
                f["direction"],
                f["interface"],
                f.get("error_status"),
            ))
        with self.conn:  # ذرّية
            self.conn.executemany(
                """INSERT INTO can_frames
                   (capture_id, timestamp, can_id, is_extended, dlc,
                    payload, direction, interface, error_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        return len(rows)

    # --------------------------------------------------------- قراءة
    def get_session(self, capture_id: int) -> Optional[dict]:
        r = self.conn.execute(
            "SELECT * FROM can_captures WHERE id=?", (capture_id,)).fetchone()
        return dict(r) if r else None

    def get_frames(self, capture_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM can_frames WHERE capture_id=? ORDER BY id", (capture_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = bytes(d["payload"])  # BLOB → bytes
            out.append(d)
        return out

    def count(self, table: str) -> int:
        if table not in ("can_captures", "can_frames"):
            raise ValueError("جدول CAN غير معروف")
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "CanEvidenceDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# =====================================================================
# UDS Evidence Storage (Phase 4B) — معزول عن جداول RF/CAN أعلاه.
# الـ Schema حرفيًا كما اعتمده الـ Architect؛ التنفيذ موائم لنمط القاعدة
# (اتصال دائم + PRAGMA foreign_keys=ON + start_session) لضمان سلامة الأدلّة.
# =====================================================================

UDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS uds_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    ecu_address INTEGER NOT NULL,
    session_type INTEGER NOT NULL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS uds_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    service_id INTEGER NOT NULL,
    sub_function INTEGER,
    payload BLOB NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('TX', 'RX')),
    response_code INTEGER,
    FOREIGN KEY (session_id) REFERENCES uds_sessions (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_uds_messages_session_id ON uds_messages(session_id);
"""


class UDSEvidenceDB:
    """تخزين أدلّة جلسات UDS ورسائلها — مستقلّ، مع FK مفعّل (سلامة الأدلّة)."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        with self.conn:
            self.conn.executescript(UDS_SCHEMA)

    # --------------------------------------------------------- الجلسة
    def start_session(self, ecu_address: int, session_type: int, source: str,
                      timestamp: Optional[str] = None) -> int:
        """ينشئ جلسة تشخيص ويعيد معرّفها (شرط لأي رسالة — سلامة الأدلّة)."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO uds_sessions (timestamp, ecu_address, session_type, source)
                   VALUES (?, ?, ?, ?)""",
                (ts, int(ecu_address), int(session_type), source),
            )
            return int(cur.lastrowid)

    # --------------------------------------------------------- الرسائل
    def save_diagnostic_exchange(self, session_id: int, timestamp: float,
                                 service_id: int, sub_function, payload: bytes,
                                 direction: str, response_code=None) -> int:
        """يحفظ رسالة تشخيص (طلب/ردّ) مرتبطة بجلسة. يعيد معرّف الرسالة."""
        with self.conn:  # معاملة ذرّية
            cur = self.conn.execute(
                """INSERT INTO uds_messages
                   (session_id, timestamp, service_id, sub_function,
                    payload, direction, response_code)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (int(session_id), float(timestamp), int(service_id),
                 (None if sub_function is None else int(sub_function)),
                 bytes(payload), direction,
                 (None if response_code is None else int(response_code))),
            )
            return int(cur.lastrowid)

    # --------------------------------------------------------- قراءة
    def get_message(self, msg_id: int) -> Optional[dict]:
        r = self.conn.execute(
            "SELECT * FROM uds_messages WHERE id=?", (msg_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["payload"] = bytes(d["payload"])
        return d

    def get_messages(self, session_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM uds_messages WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["payload"] = bytes(d["payload"]); out.append(d)
        return out

    def count(self, table: str) -> int:
        if table not in ("uds_sessions", "uds_messages"):
            raise ValueError("جدول UDS غير معروف")
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "UDSEvidenceDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
