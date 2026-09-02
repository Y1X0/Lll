#!/usr/bin/env python3
"""
evidence_reporter.py — مولّد تقرير أدلّة موحّد (RF + CAN + UDS).

يجمع مخرجات الطبقات الثلاث من قاعدة SQLite ويصيغها تقريرًا موحّدًا (JSON أو
Markdown) للتوثيق البحثي. متسامح مع غياب أي جدول (قاعدة جزئية).

⚖️ تجميع أدلّة محاكاة/بحث معزول. قراءة فقط — لا يعدّل القاعدة.

تصحيحات عن المسوّدة الأصلية:
- أسماء الجداول الحقيقية (captures/pulses_analysis، can_captures/can_frames،
  uds_sessions/uds_messages) بدل جدول rf_signals غير الموجود.
- تحويل كل حقول BLOB (payload) إلى hex قبل تسلسل JSON (كان يفشل على can_frames).
- إصلاح خطأ توليد Markdown القاتل (unary minus على نصّ).
- datetime.now(timezone.utc) بدل utcnow المهمَل.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone


class UnifiedEvidenceReporter:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _fetch(self, cursor, table: str) -> list[dict]:
        """يجلب صفوف جدول إن وُجد، محوّلًا BLOB→hex. يعيد [] إن غاب الجدول."""
        try:
            cursor.execute(f"SELECT * FROM {table}")
        except sqlite3.OperationalError:
            return []
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            for k, v in list(d.items()):
                if isinstance(v, (bytes, bytearray)):
                    d[k] = bytes(v).hex()          # BLOB → hex للتسلسل
            rows.append(d)
        return rows

    def collect(self) -> dict:
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"قاعدة الأدلّة غير موجودة: {self.db_path}")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            rf_captures = self._fetch(cur, "captures")
            rf_pulses = self._fetch(cur, "pulses_analysis")
            can_captures = self._fetch(cur, "can_captures")
            can_frames = self._fetch(cur, "can_frames")
            uds_sessions = self._fetch(cur, "uds_sessions")
            uds_messages = self._fetch(cur, "uds_messages")

        return {
            "metadata": {
                "platform": "Automotive Cybersecurity Research Platform (ACRP)",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "database_source": self.db_path,
            },
            "summary": {
                "total_rf_captures": len(rf_captures),
                "total_rf_pulses": len(rf_pulses),
                "total_can_captures": len(can_captures),
                "total_can_frames": len(can_frames),
                "total_uds_sessions": len(uds_sessions),
                "total_uds_messages": len(uds_messages),
            },
            "evidence": {
                "rf_captures": rf_captures,
                "rf_pulses": rf_pulses,
                "can_captures": can_captures,
                "can_frames": can_frames,
                "uds_sessions": uds_sessions,
                "uds_messages": uds_messages,
            },
        }

    def generate_report(self, output_format: str = "json") -> str:
        data = self.collect()
        if output_format.lower() == "json":
            return json.dumps(data, indent=4, ensure_ascii=False)
        return self._format_markdown(data)

    def _format_markdown(self, data: dict) -> str:
        md = []
        md.append("# ACRP — Forensic Evidence Report")
        md.append(f"**Generated At:** {data['metadata']['generated_at']}")
        md.append(f"**Source Database:** `{data['metadata']['database_source']}`\n")

        md.append("## Summary Statistics")
        for k, v in data["summary"].items():
            md.append(f"- **{k.replace('_', ' ').title()}:** {v}")   # ← الإصلاح
        md.append("")

        if data["evidence"]["can_frames"]:
            md.append("## CAN Frames")
            for f in data["evidence"]["can_frames"][:200]:
                md.append(f"- id=`0x{int(f['can_id']):X}` dlc={f['dlc']} "
                          f"dir={f['direction']} payload=`{f.get('payload','')}`")
            md.append("")

        if data["evidence"]["uds_messages"]:
            md.append("## UDS Diagnostic Exchanges")
            for m in data["evidence"]["uds_messages"]:
                nrc = m.get("response_code")
                nrc_s = f" nrc=`0x{int(nrc):02X}`" if nrc is not None else ""
                md.append(f"- session={m['session_id']} dir={m['direction']} "
                          f"sid=`0x{int(m['service_id']):02X}` "
                          f"payload=`{m.get('payload','')}`{nrc_s}")
            md.append("")

        return "\n".join(md)

    def save(self, out_path: str, output_format: str = "json") -> str:
        report = self.generate_report(output_format)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(report)
        return out_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="تقرير أدلّة موحّد RF+CAN+UDS")
    ap.add_argument("db")
    ap.add_argument("--format", choices=["json", "markdown"], default="json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    r = UnifiedEvidenceReporter(args.db)
    text = r.generate_report(args.format)
    if args.out:
        r.save(args.out, args.format); print(f"[+] حُفظ التقرير في {args.out}")
    else:
        print(text)
