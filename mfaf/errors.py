"""أخطاء MFAF المصنّفة."""


class MFAFError(Exception):
    """أساس كل أخطاء المنصّة."""


class ValidationError(MFAFError):
    """قيمة خارجية فشلت التحقّق."""


class NotFoundError(MFAFError):
    """كيان مطلوب غير موجود."""


class IntegrityError(MFAFError):
    """انتهاك سلامة (تكرار، سلسلة عهدة مكسورة، ...)."""


class UnsupportedOperationError(MFAFError):
    """عملية غير مدعومة/غير مصرّح بها في الحالة الراهنة (نتيجة جنائية صالحة)."""


class SafetyBoundaryError(MFAFError):
    """محاولة تجاوز حدّ المختبر/الأمان — مرفوضة تصميميًا."""
