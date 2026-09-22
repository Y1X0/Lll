"""
استيراد نتائج التحقّق الميداني V1 (Android فعلي) التي يُدخلها فاحص بشري.

⚖️ هذا الملف **لا ينفّذ** أي عملية على جهاز، ولا يولّد نتائج عتاد. يتحقّق فقط من
بنية ملف نتائج ميدانية أدخله إنسان، ويحفظه ويربطه بقضية ويولّد أحداث خطّ زمني.

قاعدة صارمة: صحّة المخطّط **لا** تعني اجتياز V1. لا يمكن ترقية الحالة إلى COMPLETED/
"VERIFIED" آليًا — الحالة تأتي من إدخال الفاحص، وترقيتها إلى COMPLETED مشروطة بوجود
ملاحظات فعلية ومقاييس مرصودة (لا nulls فقط)، ولا يُقبل مطلقًا أي status نصّه VERIFIED.
"""
from __future__ import annotations

import json
import uuid

from . import models as M
from . import validation as V
from .errors import ValidationError, NotFoundError

# حالات V1 الصريحة
V1_STATES = ("NOT_VERIFIED", "IN_PROGRESS", "COMPLETED", "PARTIAL", "FAILED")

# الحقول العليا المطلوبة في ملف V1
REQUIRED_TOP = ("validation_version", "status", "examiner", "case", "device",
                "environment", "observations", "acquisitions", "evidence",
                "timeline", "integrity_checks", "limitations", "raw_logs")

# مقاييس البحث — القيم المسموحة: True/False/None (None = لم يُرصد/لا ينطبق، ليست False)
METRIC_FIELDS = (
    "device_identification_success", "usb_observation_success",
    "authorized_acquisition_available", "evidence_hash_verified",
    "timeline_reconstructed", "repeatability_consistent", "unexpected_behavior",
)

_TIMELINE_MAP = {
    # يقبل نصوصًا ميدانية شائعة ويربطها بأنواع الخطّ الزمني المدعومة
    "USB_CONNECTED": "DEVICE_CONNECTED",
    "DEVICE_CONNECTED": "DEVICE_CONNECTED",
    "DEVICE_IDENTIFIED": "DEVICE_IDENTIFIED",
    "ACQUISITION_STARTED": "ACQUISITION_STARTED",
    "ACQUISITION_COMPLETED": "ACQUISITION_COMPLETED",
    "ACQUISITION_NOT_AVAILABLE": "ACQUISITION_NOT_AVAILABLE",
    "USB_DISCONNECTED": "DEVICE_DISCONNECTED",
    "DEVICE_DISCONNECTED": "DEVICE_DISCONNECTED",
}


class V1ImportError(ValidationError):
    """خطأ في بنية/محتوى ملف V1."""


def validate_v1_document(doc: dict) -> dict:
    """
    يتحقّق من بنية مستند V1. يرفع V1ImportError عند الخطأ. يعيد المستند كما هو
    (لا يعدّل الملاحظات). لا يرقّي الحالة.
    """
    if not isinstance(doc, dict):
        raise V1ImportError("مستند V1 يجب أن يكون كائن JSON")
    for k in REQUIRED_TOP:
        if k not in doc:
            raise V1ImportError(f"حقل مطلوب مفقود: {k}")
    if doc["validation_version"] != "V1":
        raise V1ImportError("validation_version يجب أن يكون 'V1'")
    status = doc["status"]
    if status not in V1_STATES:
        raise V1ImportError(f"status غير صالح: {status} (المسموح {list(V1_STATES)})")
    # منع صريح لأي ادّعاء "VERIFIED"
    if isinstance(status, str) and "VERIFIED" in status.upper() and status != "NOT_VERIFIED":
        raise V1ImportError("لا يُقبل status يحمل VERIFIED — الحالة تُشتقّ من الملاحظات")
    # الحقول القائمة يجب أن تكون قوائم
    for k in ("observations", "acquisitions", "evidence", "timeline",
              "integrity_checks", "limitations", "raw_logs"):
        if not isinstance(doc[k], list):
            raise V1ImportError(f"{k} يجب أن يكون قائمة")
    # الكائنات
    for k in ("examiner", "case", "device", "environment"):
        if not isinstance(doc[k], dict):
            raise V1ImportError(f"{k} يجب أن يكون كائنًا")
    # المقاييس (إن وُجدت) True/False/None فقط
    metrics = doc.get("metrics", {})
    if metrics and not isinstance(metrics, dict):
        raise V1ImportError("metrics يجب أن يكون كائنًا")
    for mf, mv in (metrics or {}).items():
        if mv not in (True, False, None):
            raise V1ImportError(f"metric '{mf}' يجب أن يكون true/false/null فقط (وصل {mv!r})")
    return doc


def derive_effective_status(doc: dict) -> str:
    """
    يشتقّ حالة فعّالة **محافظة** من محتوى فعلي — لا يرقّي بلا رصد.
    - NOT_VERIFIED يبقى NOT_VERIFIED (لا محتوى فعلي) إلا إذا صرّح الفاحص بغيرها.
    - لا يُرجِع أبدًا حالة تفوق ما أدخله الفاحص؛ يقيّده فقط لأسفل عند غياب المحتوى.
    """
    declared = doc["status"]
    has_observations = len(doc["observations"]) > 0
    metrics = doc.get("metrics", {})
    measured = any(v is not None for v in metrics.values()) if metrics else False
    # حماية: إن ادّعى الفاحص COMPLETED بلا أي ملاحظات/قياس → PARTIAL
    if declared == "COMPLETED" and not (has_observations and measured):
        return "PARTIAL"
    return declared


def import_v1(db, file_path: str, case_id: str, actor: str = "examiner",
              timeline=None) -> dict:
    """
    يستورد ملف V1 مكتملًا: يتحقّق، يربطه بقضية موجودة، يحفظ طابع الاستيراد،
    يولّد أحداث خطّ زمني من مصفوفة timeline. يحافظ على الملاحظات الأصلية حرفيًا.
    لا يقيّد V1 كناجح؛ يعيد الحالة الفعّالة المشتقّة.
    """
    # القضية يجب أن تكون موجودة (لا نخترعها)
    db.get_case(case_id)   # يرفع NotFoundError إن غابت
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as e:
        raise V1ImportError(f"تعذّر قراءة الملف: {e}") from e
    if len(raw) > 16 * 1024 * 1024:
        raise V1ImportError("ملف V1 يتجاوز الحدّ (16 MiB)")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise V1ImportError(f"JSON غير صالح: {e}") from e

    validate_v1_document(doc)
    effective = derive_effective_status(doc)

    # توليد أحداث خطّ زمني (اختياري) — يحافظ على الطوابع الأصلية
    timeline_created = 0
    if timeline is not None:
        for item in doc["timeline"]:
            if not isinstance(item, dict):
                continue
            raw_type = str(item.get("event_type", "")).upper()
            mapped = _TIMELINE_MAP.get(raw_type)
            if not mapped:
                continue   # نتجاهل الأنواع غير المدعومة بدل رفض الاستيراد كلّه
            timeline.add(case_id, mapped,
                         timestamp=item.get("timestamp"),
                         source="v1_field_import",
                         description=item.get("description"),
                         confidence="OBSERVED")
            timeline_created += 1

    import_record = {
        "import_id": f"V1-IMP-{uuid.uuid4().hex[:12]}",
        "case_id": case_id,
        "imported_at": M.utcnow(),
        "imported_by": actor,
        "declared_status": doc["status"],
        "effective_status": effective,
        "source_file": file_path,
        "observation_count": len(doc["observations"]),
        "acquisition_count": len(doc["acquisitions"]),
        "evidence_count": len(doc["evidence"]),
        "timeline_events_created": timeline_created,
        "metrics": doc.get("metrics", {}),
        "original_document": doc,   # محفوظ حرفيًا (الملاحظات الأصلية)
    }
    return import_record
