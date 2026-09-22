"""
تحقّق أمني من كل القيم الخارجية: أسماء الملفات، المسارات، الأحجام، السلاسل.

لا تثق أبدًا بـ: بيانات USB، أسماء الملفات، سلاسل الجهاز، بيانات الأدلّة
المستوردة، حقول التقرير. كل قيمة خارجية تمرّ من هنا.
"""
from __future__ import annotations

import os
import re
from .errors import ValidationError

# حدود موارد افتراضية (قابلة للتجاوز عند الاستدعاء)
DEFAULT_MAX_ARTIFACT_BYTES = 8 * 1024 * 1024 * 1024      # 8 GiB
MAX_STRING_LEN = 4096
MAX_FILENAME_LEN = 255

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
# محارف تحكّم (بما فيها newline/tab) ممنوعة في الحقول النصّية القصيرة
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def clean_text(value, field="field", max_len=MAX_STRING_LEN, allow_none=False,
               allow_empty=False, multiline=False):
    """يعيد نصًّا مُتحقَّقًا منه أو يرفع ValidationError."""
    if value is None:
        if allow_none:
            return None
        raise ValidationError(f"{field}: مطلوب")
    if not isinstance(value, str):
        raise ValidationError(f"{field}: يجب أن يكون نصًّا")
    if len(value) > max_len:
        raise ValidationError(f"{field}: يتجاوز {max_len} محرفًا")
    probe = value.replace("\n", "").replace("\t", "") if multiline else value
    if _CONTROL_RE.search(probe):
        raise ValidationError(f"{field}: يحتوي محارف تحكّم غير مسموحة")
    if not allow_empty and value.strip() == "":
        raise ValidationError(f"{field}: لا يمكن أن يكون فارغًا")
    return value


def validate_identifier(value, field="id"):
    """معرّف آمن: حروف/أرقام/._:- فقط، لا مسارات ولا محارف خطرة."""
    if not isinstance(value, str) or not _SAFE_ID_RE.match(value):
        raise ValidationError(
            f"{field}: معرّف غير صالح (مسموح A-Z a-z 0-9 . _ : - حتى 128 محرفًا)")
    return value


def safe_filename(name, field="filename"):
    """
    يعقّم اسم ملف: يزيل مكوّنات المسار، يمنع الأسماء الخطرة، يحدّ الطول.
    يرفع ValidationError للأسماء الخبيثة بدل تعقيمها بصمت عندما تكون خطرة.
    """
    if not isinstance(name, str) or name == "":
        raise ValidationError(f"{field}: اسم ملف مطلوب")
    if _CONTROL_RE.search(name) or "\x00" in name:
        raise ValidationError(f"{field}: محارف تحكّم في اسم الملف")
    # ارفض أي مكوّن مسار صريح
    if "/" in name or "\\" in name:
        raise ValidationError(f"{field}: اسم الملف لا يجوز أن يحتوي فواصل مسار")
    base = os.path.basename(name)
    if base in ("", ".", ".."):
        raise ValidationError(f"{field}: اسم ملف غير صالح")
    if len(base) > MAX_FILENAME_LEN:
        raise ValidationError(f"{field}: اسم الملف يتجاوز {MAX_FILENAME_LEN}")
    return base


def resolve_within(base_dir, candidate, field="path"):
    """
    يحلّ مسارًا ويضمن بقاءه **داخل** base_dir (حماية Path Traversal).
    يعيد المسار المطلق المُطبّع أو يرفع ValidationError.
    """
    base_abs = os.path.realpath(os.path.abspath(base_dir))
    target = os.path.realpath(os.path.abspath(os.path.join(base_abs, candidate)))
    # يجب أن يكون target == base_abs أو تحته مباشرة
    if target != base_abs and not target.startswith(base_abs + os.sep):
        raise ValidationError(f"{field}: يخرج عن الدليل المسموح (path traversal)")
    return target


def validate_size(nbytes, field="size", max_bytes=DEFAULT_MAX_ARTIFACT_BYTES):
    """يتحقّق أن حجمًا صحيح وضمن الحدّ الأقصى."""
    if not isinstance(nbytes, int) or isinstance(nbytes, bool):
        raise ValidationError(f"{field}: يجب أن يكون عددًا صحيحًا")
    if nbytes < 0:
        raise ValidationError(f"{field}: لا يمكن أن يكون سالبًا")
    if nbytes > max_bytes:
        raise ValidationError(f"{field}: يتجاوز الحدّ الأقصى ({max_bytes} بايت)")
    return nbytes


def validate_choice(value, choices, field="value"):
    if value not in choices:
        raise ValidationError(f"{field}: يجب أن يكون أحد {sorted(choices)}")
    return value
