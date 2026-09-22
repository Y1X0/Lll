# MFAF — Architecture

**Mobile Forensic Acquisition & Authentication Research Platform**
Pure-Python + SQLite subsystem · `mfaf/` package · no external deps · no physical device required.

## Scope
منصّة بحث جنائي رقمي **معتمدة** لأجهزة مملوكة للمختبر/اختبارية، محاكيات، ومجموعات
بيانات اصطناعية. تبني البنية التحتية حول: الاقتناء المصرّح به، تعريف الجهاز، تجارب
مصادقة مضبوطة، حفظ الأدلّة، التحقّق من السلامة، الخطّ الزمني، سلسلة العهدة، والتقارير.

**ليست** أداة فتح هواتف، ولا كاسر PIN، ولا تجاوز شاشة قفل، ولا إطار استغلال. لا تحتوي
أي آلية غرضها تجاوز مصادقة أو ضبط معدّل أو حماية جهاز.

## Layers / Modules
```
CLI (mfaf/cli.py)
  │
  ├─ Domain models (models.py) ── Validation (validation.py, كل قيمة خارجية)
  ├─ Persistence (db.py: SQLite, FK ON, CHECK, CASCADE, 11 tables)
  ├─ Hashing (hashing.py: streaming SHA-256/512)
  ├─ Chain of Custody (custody.py: append-only + hash chain)
  ├─ Mock Device (mock_device.py: AuthenticationTarget, deterministic)
  ├─ Auth Harness (auth_harness.py) + Metrics (metrics.py)
  ├─ USB Observer (usb_observer.py: observe-only)
  ├─ Acquisition (acquisition.py: providers + engine + verify)
  ├─ Timeline (timeline.py)
  ├─ Experiments (experiments.py: EXP-001..010)
  └─ Report (report.py: 16 sections, JSON/Markdown)
```

## Pipeline
```
DEVICE → IDENTIFICATION → CASE → AUTHORIZED ACQUISITION → EVIDENCE PRESERVATION
→ HASHING → TIMELINE → CONTROLLED EXPERIMENT ANALYSIS → REPORT
```

## Integration with existing repo
المستودع وثائقي + بنش أبحاث CAN/RF/UDS (Pure Python + SQLite + unittest). MFAF يتبع
نفس الأعراف بالضبط (اتصال دائم، `PRAGMA foreign_keys=ON`، DDL عبر executescript،
context manager، unittest، بلا اعتماديات) كنظام فرعي معزول في `mfaf/` — بلا اقتران
ببنش CAN/RF.

## Database (12 tables)
examiners · cases · devices · acquisitions · evidence · evidence_hashes ·
experiments · authentication_events · timeline_events · chain_of_custody_events · reports · **v1_imports** (append-only V1 field import records).
كل الجداول بقيود CHECK وFK وفهارس. سلسلة العهدة append-only مع ربط تجزئة.
