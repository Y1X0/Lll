"""
تجريد الاقتناء المصرّح به (AcquisitionProvider).

مزوّدون آمنون: mock/test، filesystem/dataset. الاقتناء من Android/iOS الحقيقي
عبر أدوات/واجهات مدعومة مصرّح بها فقط — وإن تعذّر في الحالة الراهنة تُسجَّل
النتيجة ACQUISITION_NOT_AVAILABLE مع السبب (نتيجة جنائية صالحة).

⚖️ لا تجاوز lock-screen ولا استغلال. المزوّد يجمع فقط ما تسمح به الحالة.
"""
from __future__ import annotations

import os
import uuid
import json
from . import models as M
from . import validation as V
from . import hashing
from .errors import UnsupportedOperationError, ValidationError


class AcquisitionProvider:
    """واجهة مزوّد الاقتناء."""
    name = "base"

    def validate_source(self, source) -> None:
        raise NotImplementedError

    def collect(self, source, storage_dir) -> list[dict]:
        """يعيد قائمة عناصر {"original_filename","storage_path","byte_size","evidence_type"}."""
        raise NotImplementedError


class MockAcquisitionProvider(AcquisitionProvider):
    """يولّد أدلّة اصطناعية حتمية للاختبار."""
    name = "mock"

    def __init__(self, artifacts: dict | None = None):
        # {filename: bytes}
        self.artifacts = artifacts or {"synthetic_dataset.bin": b"MFAF-SYNTHETIC-EVIDENCE"}

    def validate_source(self, source):
        return None

    def collect(self, source, storage_dir):
        items = []
        for fname, data in self.artifacts.items():
            safe = V.safe_filename(fname)
            path = V.resolve_within(storage_dir, safe)
            with open(path, "wb") as fh:
                fh.write(data)
            os.chmod(path, 0o600)
            items.append({"original_filename": safe, "storage_path": path,
                          "byte_size": len(data), "evidence_type": "mock"})
        return items


class FilesystemAcquisitionProvider(AcquisitionProvider):
    """اقتناء مجموعة بيانات من مجلّد مصدر (نسخ آمن + تجزئة)."""
    name = "filesystem"

    def __init__(self, max_bytes=V.DEFAULT_MAX_ARTIFACT_BYTES):
        self.max_bytes = max_bytes

    def validate_source(self, source):
        if not isinstance(source, str) or not os.path.isdir(source):
            raise ValidationError(f"مصدر filesystem ليس مجلّدًا: {source}")

    def collect(self, source, storage_dir):
        self.validate_source(source)
        src_abs = os.path.realpath(source)
        items = []
        for root, _, files in os.walk(src_abs):
            for f in files:
                full = os.path.join(root, f)
                if not os.path.isfile(full) or os.path.islink(full):
                    continue
                size = os.path.getsize(full)
                V.validate_size(size, "artifact", self.max_bytes)
                safe = V.safe_filename(f)
                # تجنّب الدهس: بادئة فريدة
                dest_name = f"{uuid.uuid4().hex[:8]}_{safe}"
                dest = V.resolve_within(storage_dir, dest_name)
                with open(full, "rb") as rf, open(dest, "wb") as wf:
                    while True:
                        chunk = rf.read(1024 * 1024)
                        if not chunk:
                            break
                        wf.write(chunk)
                os.chmod(dest, 0o600)
                items.append({"original_filename": safe, "storage_path": dest,
                              "byte_size": size, "evidence_type": "dataset"})
        return items


class UnavailableAcquisitionProvider(AcquisitionProvider):
    """يمثّل منصّة لا تسمح بالاقتناء في الحالة الراهنة → ACQUISITION_NOT_AVAILABLE."""
    name = "unavailable"

    def __init__(self, reason="acquisition not permitted in current device state"):
        self.reason = reason

    def validate_source(self, source):
        raise UnsupportedOperationError(self.reason)

    def collect(self, source, storage_dir):
        raise UnsupportedOperationError(self.reason)


class AcquisitionEngine:
    """
    ينفّذ اقتناءً كاملًا: يتحقّق، يجمع، يجزّئ، ينشئ أدلّة، يصدر أحداث عهدة/خطّ زمني،
    ويكتب مانفست. يسجّل NOT_AVAILABLE كنتيجة صالحة عند تعذّر المنصّة.
    """
    def __init__(self, db, custody_log=None, timeline=None):
        self.db = db
        self.custody = custody_log
        self.timeline = timeline

    def run(self, case_id, device_id, provider: AcquisitionProvider, source,
            storage_dir, examiner_id=None, actor="engine") -> dict:
        os.makedirs(storage_dir, exist_ok=True)
        os.chmod(storage_dir, 0o700)
        acq_id = f"ACQ-{uuid.uuid4().hex[:12]}"
        acq = M.Acquisition(acq_id, case_id, device_id, provider.name, status="STARTED",
                            examiner_id=examiner_id)
        self.db.add_acquisition(acq)
        if self.custody:
            self.custody.append(actor, "ACQUISITION_STARTED", case_id=case_id,
                                metadata={"acquisition_id": acq_id, "provider": provider.name})
        if self.timeline:
            self.timeline.add(case_id, "ACQUISITION_STARTED", device_id=device_id,
                              metadata={"acquisition_id": acq_id})

        try:
            provider.validate_source(source)
            items = provider.collect(source, storage_dir)
        except UnsupportedOperationError as e:
            self.db.update_acquisition(acq_id, "NOT_AVAILABLE", reason=str(e))
            if self.custody:
                self.custody.append(actor, "ACQUISITION_NOT_AVAILABLE", case_id=case_id,
                                    metadata={"acquisition_id": acq_id, "reason": str(e)})
            if self.timeline:
                self.timeline.add(case_id, "ACQUISITION_NOT_AVAILABLE", device_id=device_id,
                                  description=str(e), confidence="OBSERVED")
            return {"acquisition_id": acq_id, "status": "NOT_AVAILABLE",
                    "reason": str(e), "evidence": []}

        created = []
        for it in items:
            h = hashing.hash_file(it["storage_path"])
            ev_id = f"EV-{uuid.uuid4().hex[:12]}"
            ev = M.Evidence(
                evidence_id=ev_id, case_id=case_id, source_device_id=device_id,
                acquisition_id=acq_id, evidence_type=it["evidence_type"],
                original_filename=it["original_filename"], storage_path=it["storage_path"],
                byte_size=it["byte_size"], sha256=h["sha256"], sha512=h["sha512"],
                examiner_id=examiner_id, integrity_status="VERIFIED",
                acquired_at=M.utcnow())
            self.db.add_evidence(ev)
            self.db.add_evidence_hash(ev_id, "sha256", h["sha256"])
            self.db.add_evidence_hash(ev_id, "sha512", h["sha512"])
            created.append(M.to_dict(ev))
            if self.custody:
                self.custody.append(actor, "EVIDENCE_CREATED", case_id=case_id,
                                    evidence_id=ev_id, metadata={"sha256": h["sha256"]})
                self.custody.append(actor, "EVIDENCE_HASHED", case_id=case_id,
                                    evidence_id=ev_id, metadata={"algorithms": ["sha256", "sha512"]})
            if self.timeline:
                self.timeline.add(case_id, "EVIDENCE_CREATED", device_id=device_id,
                                  evidence_id=ev_id)
                self.timeline.add(case_id, "HASH_CALCULATED", evidence_id=ev_id)

        # مانفست الاقتناء
        manifest = {
            "acquisition_id": acq_id, "case_id": case_id, "device_id": device_id,
            "provider": provider.name, "created_at": M.utcnow(),
            "evidence": [{"evidence_id": e["evidence_id"], "filename": e["original_filename"],
                          "byte_size": e["byte_size"], "sha256": e["sha256"]} for e in created],
        }
        manifest_path = V.resolve_within(storage_dir, "acquisition_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, ensure_ascii=False)
        os.chmod(manifest_path, 0o600)
        self.db.update_acquisition(acq_id, "COMPLETED", manifest_path=manifest_path)
        if self.custody:
            self.custody.append(actor, "ACQUISITION_COMPLETED", case_id=case_id,
                                metadata={"acquisition_id": acq_id, "evidence_count": len(created)})
        if self.timeline:
            self.timeline.add(case_id, "ACQUISITION_COMPLETED", device_id=device_id,
                              metadata={"acquisition_id": acq_id})
        return {"acquisition_id": acq_id, "status": "COMPLETED",
                "manifest_path": manifest_path, "evidence": created}


def verify_evidence_integrity(db, evidence_id) -> str:
    """يعيد VERIFIED / MISMATCH / MISSING / ERROR."""
    try:
        ev = db.get_evidence(evidence_id)
    except Exception:
        return "ERROR"
    path = ev["storage_path"]
    if not os.path.isfile(path):
        db.set_evidence_integrity(evidence_id, "MISSING")
        return "MISSING"
    try:
        h = hashing.hash_file(path)
    except Exception:
        db.set_evidence_integrity(evidence_id, "ERROR")
        return "ERROR"
    status = "VERIFIED" if ev["sha256"] and h["sha256"] == ev["sha256"] else "MISMATCH"
    db.set_evidence_integrity(evidence_id, status)
    return status
