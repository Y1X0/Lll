"""
طبقة قاعدة بيانات MFAF على SQLite — تتبع نمط المستودع (اتصال دائم، row_factory،
PRAGMA foreign_keys=ON، DDL عبر executescript، context manager).

المخطّط يغطّي: examiners, cases, devices, acquisitions, experiments,
authentication_events, evidence, evidence_hashes, chain_of_custody_events,
timeline_events, reports.

المخطّط مُصمَّم append-oriented لأحداث العهدة (لا UPDATE/DELETE عبر الواجهة العادية).
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from .errors import IntegrityError, NotFoundError
from . import models as M
from . import validation as V

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS examiners (
    examiner_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    organization TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    case_id         TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    examiner_id     TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN','ACTIVE','CLOSED','ARCHIVED')),
    legal_authority TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (examiner_id) REFERENCES examiners(examiner_id)
);

CREATE TABLE IF NOT EXISTS devices (
    device_id       TEXT PRIMARY KEY,
    case_id         TEXT,
    manufacturer    TEXT,
    model           TEXT,
    os_family       TEXT NOT NULL DEFAULT 'unknown',
    os_version      TEXT,
    usb_vid         TEXT,
    usb_pid         TEXT,
    serial          TEXT,
    connection_mode TEXT NOT NULL DEFAULT 'unknown',
    transport       TEXT,
    is_test_target  INTEGER NOT NULL DEFAULT 1 CHECK (is_test_target IN (0,1)),
    detected_at     TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS acquisitions (
    acquisition_id TEXT PRIMARY KEY,
    case_id        TEXT NOT NULL,
    device_id      TEXT NOT NULL,
    provider       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'STARTED'
                   CHECK (status IN ('STARTED','COMPLETED','FAILED','NOT_AVAILABLE')),
    reason         TEXT,
    examiner_id    TEXT,
    manifest_path  TEXT,
    started_at     TEXT NOT NULL,
    completed_at   TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id      TEXT PRIMARY KEY,
    case_id          TEXT NOT NULL,
    source_device_id TEXT,
    acquisition_id   TEXT,
    evidence_type    TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_path     TEXT NOT NULL,
    byte_size        INTEGER NOT NULL CHECK (byte_size >= 0),
    sha256           TEXT,
    sha512           TEXT,
    examiner_id      TEXT,
    description      TEXT,
    integrity_status TEXT NOT NULL DEFAULT 'PENDING'
                     CHECK (integrity_status IN ('PENDING','VERIFIED','MISMATCH','MISSING','ERROR')),
    created_at       TEXT NOT NULL,
    acquired_at      TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (acquisition_id) REFERENCES acquisitions(acquisition_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS evidence_hashes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT NOT NULL,
    algorithm   TEXT NOT NULL,
    digest      TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE (evidence_id, algorithm, digest),
    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id   TEXT PRIMARY KEY,
    case_id         TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    definition_code TEXT NOT NULL,
    objective       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'DEFINED',
    notes           TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS authentication_events (
    event_id        TEXT PRIMARY KEY,
    experiment_id   TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    attempt_number  INTEGER NOT NULL,
    test_input_id   TEXT NOT NULL,
    result          TEXT NOT NULL,
    response_time_ms REAL NOT NULL,
    target_state    TEXT NOT NULL,
    lockout_state   INTEGER NOT NULL CHECK (lockout_state IN (0,1)),
    rate_limit_state INTEGER NOT NULL CHECK (rate_limit_state IN (0,1)),
    delay_before_ms REAL,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS timeline_events (
    event_id    TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    device_id   TEXT,
    evidence_id TEXT,
    source      TEXT NOT NULL DEFAULT 'mfaf',
    description TEXT,
    metadata    TEXT,
    confidence  TEXT NOT NULL DEFAULT 'OBSERVED',
    created_at  TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

-- سلسلة عهدة append-only مع ربط تجزئة (hash chain) لمنع التعديل الصامت
CREATE TABLE IF NOT EXISTS chain_of_custody_events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL UNIQUE,
    case_id     TEXT,
    evidence_id TEXT,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    metadata    TEXT,
    timestamp   TEXT NOT NULL,
    prev_hash   TEXT,
    entry_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id    TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL,
    format       TEXT NOT NULL,
    storage_path TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence(case_id);
CREATE INDEX IF NOT EXISTS idx_timeline_case ON timeline_events(case_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_auth_experiment ON authentication_events(experiment_id, attempt_number);
CREATE INDEX IF NOT EXISTS idx_coc_case ON chain_of_custody_events(case_id, seq);
"""


class MFAFDatabase:
    def __init__(self, path: str = "mfaf.db"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self._migrate()

    def _migrate(self):
        with self.conn:
            self.conn.executescript(SCHEMA)
            self.conn.execute(
                "INSERT OR IGNORE INTO schema_meta(key,value) VALUES('version',?)",
                (str(SCHEMA_VERSION),))

    # ---------------------------------------------------------- examiners
    def add_examiner(self, ex: M.Examiner) -> str:
        V.validate_identifier(ex.examiner_id, "examiner_id")
        V.clean_text(ex.name, "name")
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO examiners(examiner_id,name,organization,created_at) "
                    "VALUES(?,?,?,?)",
                    (ex.examiner_id, ex.name, ex.organization, ex.created_at))
        except sqlite3.IntegrityError as e:
            raise IntegrityError(f"examiner موجود مسبقًا: {ex.examiner_id}") from e
        return ex.examiner_id

    # ---------------------------------------------------------- cases
    def add_case(self, c: M.Case) -> str:
        V.validate_identifier(c.case_id, "case_id")
        V.clean_text(c.title, "title")
        V.validate_choice(c.status, M.CASE_STATUSES, "status")
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO cases(case_id,title,examiner_id,description,status,"
                    "legal_authority,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (c.case_id, c.title, c.examiner_id, c.description, c.status,
                     c.legal_authority, c.notes, c.created_at, c.updated_at))
        except sqlite3.IntegrityError as e:
            raise IntegrityError(f"case غير صالح/مكرّر: {c.case_id} ({e})") from e
        return c.case_id

    def get_case(self, case_id: str) -> dict:
        r = self.conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if not r:
            raise NotFoundError(f"case غير موجود: {case_id}")
        return dict(r)

    def list_cases(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM cases ORDER BY created_at").fetchall()]

    def set_case_status(self, case_id: str, status: str):
        V.validate_choice(status, M.CASE_STATUSES, "status")
        with self.conn:
            cur = self.conn.execute(
                "UPDATE cases SET status=?, updated_at=? WHERE case_id=?",
                (status, M.utcnow(), case_id))
            if cur.rowcount == 0:
                raise NotFoundError(f"case غير موجود: {case_id}")

    # ---------------------------------------------------------- devices
    def add_device(self, d: M.Device) -> str:
        V.validate_identifier(d.device_id, "device_id")
        V.validate_choice(d.os_family, M.OS_FAMILIES, "os_family")
        V.validate_choice(d.connection_mode, M.CONNECTION_MODES, "connection_mode")
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO devices(device_id,case_id,manufacturer,model,os_family,"
                    "os_version,usb_vid,usb_pid,serial,connection_mode,transport,"
                    "is_test_target,detected_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (d.device_id, d.case_id, d.manufacturer, d.model, d.os_family,
                     d.os_version, d.usb_vid, d.usb_pid, d.serial, d.connection_mode,
                     d.transport, 1 if d.is_test_target else 0, d.detected_at))
        except sqlite3.IntegrityError as e:
            raise IntegrityError(f"device غير صالح/مكرّر: {d.device_id} ({e})") from e
        return d.device_id

    def get_device(self, device_id: str) -> dict:
        r = self.conn.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
        if not r:
            raise NotFoundError(f"device غير موجود: {device_id}")
        return dict(r)

    def list_devices(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM devices ORDER BY detected_at").fetchall()]

    # ---------------------------------------------------------- acquisitions
    def add_acquisition(self, a: M.Acquisition) -> str:
        V.validate_identifier(a.acquisition_id, "acquisition_id")
        V.validate_choice(a.status, M.ACQUISITION_STATUSES, "status")
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO acquisitions(acquisition_id,case_id,device_id,provider,"
                    "status,reason,examiner_id,manifest_path,started_at,completed_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (a.acquisition_id, a.case_id, a.device_id, a.provider, a.status,
                     a.reason, a.examiner_id, a.manifest_path, a.started_at, a.completed_at))
        except sqlite3.IntegrityError as e:
            raise IntegrityError(f"acquisition غير صالح/مكرّر: {a.acquisition_id} ({e})") from e
        return a.acquisition_id

    def update_acquisition(self, acquisition_id: str, status: str,
                           reason: Optional[str] = None, manifest_path: Optional[str] = None):
        V.validate_choice(status, M.ACQUISITION_STATUSES, "status")
        with self.conn:
            self.conn.execute(
                "UPDATE acquisitions SET status=?, reason=?, manifest_path=?, completed_at=? "
                "WHERE acquisition_id=?",
                (status, reason, manifest_path, M.utcnow(), acquisition_id))

    # ---------------------------------------------------------- evidence
    def add_evidence(self, e: M.Evidence) -> str:
        V.validate_identifier(e.evidence_id, "evidence_id")
        V.validate_choice(e.evidence_type, M.EVIDENCE_TYPES, "evidence_type")
        V.validate_size(e.byte_size, "byte_size")
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO evidence(evidence_id,case_id,source_device_id,acquisition_id,"
                    "evidence_type,original_filename,storage_path,byte_size,sha256,sha512,"
                    "examiner_id,description,integrity_status,created_at,acquired_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (e.evidence_id, e.case_id, e.source_device_id, e.acquisition_id,
                     e.evidence_type, e.original_filename, e.storage_path, e.byte_size,
                     e.sha256, e.sha512, e.examiner_id, e.description, e.integrity_status,
                     e.created_at, e.acquired_at))
        except sqlite3.IntegrityError as ex:
            raise IntegrityError(f"evidence مكرّر/غير صالح: {e.evidence_id} ({ex})") from ex
        return e.evidence_id

    def get_evidence(self, evidence_id: str) -> dict:
        r = self.conn.execute("SELECT * FROM evidence WHERE evidence_id=?",
                              (evidence_id,)).fetchone()
        if not r:
            raise NotFoundError(f"evidence غير موجود: {evidence_id}")
        return dict(r)

    def list_evidence(self, case_id: Optional[str] = None) -> list[dict]:
        if case_id:
            rows = self.conn.execute(
                "SELECT * FROM evidence WHERE case_id=? ORDER BY created_at", (case_id,))
        else:
            rows = self.conn.execute("SELECT * FROM evidence ORDER BY created_at")
        return [dict(r) for r in rows.fetchall()]

    def set_evidence_integrity(self, evidence_id: str, status: str):
        V.validate_choice(status, M.INTEGRITY_STATES, "integrity_status")
        with self.conn:
            self.conn.execute("UPDATE evidence SET integrity_status=? WHERE evidence_id=?",
                              (status, evidence_id))

    def add_evidence_hash(self, evidence_id: str, algorithm: str, digest: str):
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO evidence_hashes(evidence_id,algorithm,digest,computed_at) "
                "VALUES(?,?,?,?)", (evidence_id, algorithm, digest, M.utcnow()))

    # ---------------------------------------------------------- experiments
    def add_experiment(self, x: M.Experiment) -> str:
        V.validate_identifier(x.experiment_id, "experiment_id")
        with self.conn:
            self.conn.execute(
                "INSERT INTO experiments(experiment_id,case_id,target_id,definition_code,"
                "objective,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (x.experiment_id, x.case_id, x.target_id, x.definition_code,
                 x.objective, x.status, x.notes, x.created_at))
        return x.experiment_id

    def add_auth_event(self, ev: M.AuthenticationEvent) -> str:
        with self.conn:
            self.conn.execute(
                "INSERT INTO authentication_events(event_id,experiment_id,target_id,"
                "attempt_number,test_input_id,result,response_time_ms,target_state,"
                "lockout_state,rate_limit_state,delay_before_ms,notes,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ev.event_id, ev.experiment_id, ev.target_id, ev.attempt_number,
                 ev.test_input_id, ev.result, ev.response_time_ms, ev.target_state,
                 1 if ev.lockout_state else 0, 1 if ev.rate_limit_state else 0,
                 ev.delay_before_ms, ev.notes, ev.created_at))
        return ev.event_id

    def list_auth_events(self, experiment_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM authentication_events WHERE experiment_id=? "
            "ORDER BY attempt_number", (experiment_id,)).fetchall()]

    # ---------------------------------------------------------- timeline
    def add_timeline_event(self, t: M.TimelineEvent) -> str:
        import json
        with self.conn:
            self.conn.execute(
                "INSERT INTO timeline_events(event_id,case_id,event_type,timestamp,device_id,"
                "evidence_id,source,description,metadata,confidence,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (t.event_id, t.case_id, t.event_type, t.timestamp, t.device_id,
                 t.evidence_id, t.source, t.description,
                 json.dumps(t.metadata, ensure_ascii=False) if t.metadata else None,
                 t.confidence, t.created_at))
        return t.event_id

    def list_timeline(self, case_id: str) -> list[dict]:
        import json
        rows = self.conn.execute(
            "SELECT * FROM timeline_events WHERE case_id=? ORDER BY timestamp, created_at",
            (case_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("metadata"):
                d["metadata"] = json.loads(d["metadata"])
            out.append(d)
        return out

    # ---------------------------------------------------------- reports
    def add_report(self, report_id: str, case_id: str, fmt: str, path: Optional[str]):
        with self.conn:
            self.conn.execute(
                "INSERT INTO reports(report_id,case_id,format,storage_path,created_at) "
                "VALUES(?,?,?,?,?)", (report_id, case_id, fmt, path, M.utcnow()))

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
