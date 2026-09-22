"""
تجزئة تدفّقية للأدلّة — لا تُحمَّل الملفات الكبيرة كاملة في الذاكرة.
تجريد يسمح بإضافة خوارزميات لاحقًا. SHA-256 أساسي، SHA-512 مدعوم.
"""
from __future__ import annotations

import hashlib
import os
from typing import Iterable

from .errors import ValidationError

DEFAULT_ALGOS = ("sha256", "sha512")
_CHUNK = 1024 * 1024   # 1 MiB


def supported_algorithms() -> tuple:
    return DEFAULT_ALGOS


def hash_stream(fileobj, algorithms: Iterable[str] = DEFAULT_ALGOS,
                max_bytes: int | None = None) -> dict:
    """
    يجزّئ كائن ملف مفتوح بوضع ثنائي تدفّقيًا. يعيد {"algo": digest, ..., "_size": n}.
    يرفع ValidationError إن تجاوز max_bytes.
    """
    algos = tuple(algorithms)
    for a in algos:
        if a not in hashlib.algorithms_available:
            raise ValidationError(f"خوارزمية غير مدعومة: {a}")
    hs = {a: hashlib.new(a) for a in algos}
    size = 0
    while True:
        chunk = fileobj.read(_CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if max_bytes is not None and size > max_bytes:
            raise ValidationError(f"الملف يتجاوز الحدّ الأقصى {max_bytes} بايت")
        for h in hs.values():
            h.update(chunk)
    out = {a: h.hexdigest() for a, h in hs.items()}
    out["_size"] = size
    return out


def hash_file(path: str, algorithms: Iterable[str] = DEFAULT_ALGOS,
              max_bytes: int | None = None) -> dict:
    """يجزّئ ملفًا على القرص تدفّقيًا."""
    if not os.path.isfile(path):
        raise ValidationError(f"المسار ليس ملفًا: {path}")
    with open(path, "rb") as fh:
        return hash_stream(fh, algorithms, max_bytes)


def hash_bytes(data: bytes, algorithms: Iterable[str] = DEFAULT_ALGOS) -> dict:
    import io
    return hash_stream(io.BytesIO(data), algorithms)
