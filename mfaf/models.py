"""
نماذج المجال (dataclasses) لـ MFAF. تمثيل صريح للحقول غير المتاحة عبر None.
لا تحتوي منطق تخزين — التخزين في db.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Any


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# القيم المسموحة (تُفرض عبر التحقّق و/أو قيود CHECK في القاعدة)
CASE_STATUSES = ("OPEN", "ACTIVE", "CLOSED", "ARCHIVED")
OS_FAMILIES = ("android", "ios", "other", "unknown")
CONNECTION_MODES = ("usb", "adb", "recovery", "fastboot", "dfu", "network",
                    "simulator", "mock", "unknown")
EVIDENCE_TYPES = ("dataset", "file", "image", "logical", "manifest", "mock", "other")
INTEGRITY_STATES = ("PENDING", "VERIFIED", "MISMATCH", "MISSING", "ERROR")
ACQUISITION_STATUSES = ("STARTED", "COMPLETED", "FAILED", "NOT_AVAILABLE")
TARGET_STATES = ("DISCONNECTED", "CONNECTED", "LOCKED", "UNLOCKED",
                 "RESTRICTED", "RATE_LIMITED", "LOCKOUT", "RECOVERY")
AUTH_RESULTS = ("SUCCESS", "FAIL", "RATE_LIMITED", "LOCKED_OUT", "ERROR")


@dataclass
class Examiner:
    examiner_id: str
    name: str
    organization: Optional[str] = None
    created_at: str = field(default_factory=utcnow)


@dataclass
class Case:
    case_id: str
    title: str
    examiner_id: str
    description: Optional[str] = None
    status: str = "OPEN"
    legal_authority: Optional[str] = None      # يُدخله الفاحص يدويًا — لا نخترع تفويضًا
    notes: Optional[str] = None
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)


@dataclass
class Device:
    device_id: str
    case_id: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    os_family: str = "unknown"
    os_version: Optional[str] = None
    usb_vid: Optional[str] = None
    usb_pid: Optional[str] = None
    serial: Optional[str] = None                # None = غير متاح شرعيًا (صريح)
    connection_mode: str = "unknown"
    transport: Optional[str] = None
    is_test_target: bool = True                 # حدّ المختبر
    detected_at: str = field(default_factory=utcnow)


@dataclass
class Acquisition:
    acquisition_id: str
    case_id: str
    device_id: str
    provider: str                               # mock / filesystem / android / ios
    status: str = "STARTED"
    reason: Optional[str] = None                # سبب NOT_AVAILABLE/FAILED
    examiner_id: Optional[str] = None
    manifest_path: Optional[str] = None
    started_at: str = field(default_factory=utcnow)
    completed_at: Optional[str] = None


@dataclass
class Evidence:
    evidence_id: str
    case_id: str
    source_device_id: Optional[str]
    acquisition_id: Optional[str]
    evidence_type: str
    original_filename: str
    storage_path: str
    byte_size: int
    sha256: Optional[str] = None
    sha512: Optional[str] = None
    examiner_id: Optional[str] = None
    description: Optional[str] = None
    integrity_status: str = "PENDING"
    created_at: str = field(default_factory=utcnow)
    acquired_at: Optional[str] = None


@dataclass
class Experiment:
    experiment_id: str
    case_id: str
    target_id: str
    definition_code: str                        # EXP-001 ..
    objective: str
    status: str = "DEFINED"
    notes: Optional[str] = None
    created_at: str = field(default_factory=utcnow)


@dataclass
class AuthenticationEvent:
    event_id: str
    experiment_id: str
    target_id: str
    attempt_number: int
    test_input_id: str                          # معرّف مدخل اصطناعي — لا كلمة مرور
    result: str
    response_time_ms: float
    target_state: str
    lockout_state: bool
    rate_limit_state: bool
    delay_before_ms: Optional[float] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utcnow)


@dataclass
class TimelineEvent:
    event_id: str
    case_id: str
    event_type: str
    timestamp: str                              # زمن الحدث الأصلي
    device_id: Optional[str] = None
    evidence_id: Optional[str] = None
    source: str = "mfaf"
    description: Optional[str] = None
    metadata: Optional[dict] = None
    confidence: str = "OBSERVED"                # OBSERVED / INFERRED
    created_at: str = field(default_factory=utcnow)   # زمن الابتلاع (منفصل)


def to_dict(obj: Any) -> dict:
    return asdict(obj)
