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
