"""نموذج الخطّ الزمني الجنائي الموحّد — ترتيب زمني، وفصل زمن الحدث عن زمن الابتلاع."""
from __future__ import annotations

import uuid
from . import models as M

TIMELINE_EVENT_TYPES = (
    "DEVICE_CONNECTED", "DEVICE_DISCONNECTED", "DEVICE_IDENTIFIED",
    "ACQUISITION_STARTED", "ACQUISITION_COMPLETED", "ACQUISITION_NOT_AVAILABLE",
    "AUTHENTICATION_ATTEMPT", "LOCKOUT_DETECTED", "REBOOT",
    "EVIDENCE_CREATED", "HASH_CALCULATED", "HASH_VERIFIED", "REPORT_GENERATED",
)


class Timeline:
    def __init__(self, db):
        self.db = db

    def add(self, case_id, event_type, timestamp=None, device_id=None,
            evidence_id=None, source="mfaf", description=None, metadata=None,
            confidence="OBSERVED") -> str:
        from .validation import validate_choice
        validate_choice(event_type, TIMELINE_EVENT_TYPES, "event_type")
        validate_choice(confidence, ("OBSERVED", "INFERRED"), "confidence")
        ev = M.TimelineEvent(
            event_id=str(uuid.uuid4()), case_id=case_id, event_type=event_type,
            timestamp=timestamp or M.utcnow(), device_id=device_id,
            evidence_id=evidence_id, source=source, description=description,
            metadata=metadata, confidence=confidence)
        return self.db.add_timeline_event(ev)

    def chronological(self, case_id) -> list[dict]:
        """أحداث مرتّبة زمنيًا حسب زمن الحدث الأصلي ثم زمن الابتلاع."""
        return self.db.list_timeline(case_id)
