"""تعريفات التجارب EXP-001 .. EXP-010 — بيانات وصفية للمنهجية والتكرار."""
from __future__ import annotations

EXPERIMENTS = {
    "EXP-001": {
        "objective": "تحديد هوية الجهاز من البيانات الوصفية المتاحة شرعيًا",
        "prerequisites": ["جهاز اختبار/محاكى", "حالة تفويض مسجّلة"],
        "setup": "توصيل الهدف وتسجيل حدث USB والتعريف",
        "procedure": ["رصد USB_CONNECTED", "استخراج VID/PID/manufacturer", "إنشاء سجلّ Device"],
        "expected_observations": ["حقول متاحة مملوءة", "حقول غير متاحة = null صريح"],
        "collected_evidence": ["سجلّ Device", "أحداث USB"],
        "metrics": ["timeline_event_count"],
        "limitations": ["serial قد لا يكون متاحًا بلا وصول مصرّح"],
    },
    "EXP-002": {
        "objective": "رصد حالة اتصال/فصل USB",
        "prerequisites": ["USBObserver"],
        "setup": "تسلسل اتصال/فصل محاكى",
        "procedure": ["record USB_CONNECTED", "record USB_DISCONNECTED"],
        "expected_observations": ["أحداث مبنيّة بطوابع زمنية"],
        "collected_evidence": ["أحداث USB"],
        "metrics": ["usb_event_count"],
        "limitations": ["لا تنفيذ أوامر على الجهاز"],
    },
    "EXP-003": {
        "objective": "مقارنة حالة مقفلة مقابل غير مقفلة عبر مؤشّرات شرعية",
        "prerequisites": ["MockMobileDevice"],
        "setup": "قراءة get_state قبل/بعد نجاح مصادقة اصطناعية",
        "procedure": ["get_state (LOCKED)", "submit correct synthetic input", "get_state (UNLOCKED)"],
        "expected_observations": ["انتقال LOCKED→UNLOCKED"],
        "collected_evidence": ["authentication_events"],
        "metrics": ["authentication_success_count"],
        "limitations": ["على هدف اختباري فقط"],
    },
    "EXP-004": {
        "objective": "قياس سلوك فشل المصادقة المضبوط",
        "prerequisites": ["MockMobileDevice", "AuthenticationHarness"],
        "setup": "سلسلة مدخلات اصطناعية خاطئة",
        "procedure": ["تشغيل محاولات خاطئة", "تسجيل النتائج والحالات"],
        "expected_observations": ["نتائج FAIL متتابعة"],
        "collected_evidence": ["authentication_events"],
        "metrics": ["authentication_failure_count", "average_response_time_ms"],
        "limitations": ["لا كسر/تجاوز — قياس فقط"],
    },
    "EXP-005": {
        "objective": "قياس تحديد المعدّل (rate limiting)",
        "prerequisites": ["MockMobileDevice"],
        "setup": "محاولات متتالية لرصد زيادة التأخّر",
        "procedure": ["تشغيل محاولات > rate_limit_after", "قياس latency والتغيّر"],
        "expected_observations": ["زيادة التأخّر بعد العتبة", "rate_limit_detected=true"],
        "collected_evidence": ["authentication_events"],
        "metrics": ["rate_limit_detected", "maximum_response_time_ms"],
        "limitations": ["العتبة تُقاس عبر سلوك اختباري شرعي"],
    },
    "EXP-006": {
        "objective": "قياس حالة الإغلاق (lockout)",
        "prerequisites": ["MockMobileDevice"],
        "setup": "محاولات > lockout_after",
        "procedure": ["تشغيل حتى LOCKOUT", "رصد الانتقال والاسترداد"],
        "expected_observations": ["lockout_detected=true", "احترام الإغلاق (لا تجاوز)"],
        "collected_evidence": ["authentication_events"],
        "metrics": ["lockout_detected"],
        "limitations": ["الاسترداد يُقاس عبر recover_step"],
    },
    "EXP-007": {
        "objective": "مقارنة الحالة قبل/بعد إعادة الإقلاع",
        "prerequisites": ["MockMobileDevice"],
        "setup": "محاولات ثم reboot",
        "procedure": ["فشل محاولات", "reboot", "مقارنة get_state"],
        "expected_observations": ["الحالة الآمنة تبقى (مقفل يبقى مقفلًا)"],
        "collected_evidence": ["مقارنة before/after"],
        "metrics": ["attempts_cleared"],
        "limitations": ["لا تجاوز لحالة ما بعد الإقلاع"],
    },
    "EXP-008": {
        "objective": "سلامة اقتناء الأدلّة",
        "prerequisites": ["AcquisitionEngine", "provider"],
        "setup": "اقتناء + تجزئة + تحقّق",
        "procedure": ["run acquisition", "verify_evidence_integrity"],
        "expected_observations": ["VERIFIED", "تطابق SHA-256"],
        "collected_evidence": ["evidence", "evidence_hashes", "manifest"],
        "metrics": ["evidence_count", "hash_verification_success"],
        "limitations": ["المصادر المدعومة فقط؛ غيرها NOT_AVAILABLE"],
    },
    "EXP-009": {
        "objective": "إعادة بناء الخطّ الزمني",
        "prerequisites": ["Timeline"],
        "setup": "توليد أحداث عبر دورة الحياة",
        "procedure": ["إضافة أحداث", "chronological()"],
        "expected_observations": ["ترتيب زمني صحيح", "فصل زمن الحدث عن الابتلاع"],
        "collected_evidence": ["timeline_events"],
        "metrics": ["timeline_event_count"],
        "limitations": ["الدقّة الزمنية بحدود المصدر"],
    },
    "EXP-010": {
        "objective": "اختبار قابلية التكرار",
        "prerequisites": ["MockMobileDevice بإعداد ثابت"],
        "setup": "تشغيل نفس التجربة مرّتين بنفس الإعداد",
        "procedure": ["run", "reset_test_state", "run", "مقارنة المقاييس"],
        "expected_observations": ["نتائج متطابقة (حتمية)"],
        "collected_evidence": ["مجموعتا authentication_events"],
        "metrics": ["repeatability_match"],
        "limitations": ["الحتمية مضمونة للمحاكي فقط"],
    },
}


def get_definition(code: str) -> dict:
    from .errors import NotFoundError
    if code not in EXPERIMENTS:
        raise NotFoundError(f"تعريف تجربة غير معروف: {code}")
    return dict(EXPERIMENTS[code])


def list_codes() -> list[str]:
    return sorted(EXPERIMENTS.keys())
