# منصّة أبحاث أمن السيارات — CAN / RF / UDS Research Bench

**الحالة:** برمجيًا مكتملة ومُختبَرة · **آخر commit موثّق:** `2741e36`
**الفرع:** `claude/car-key-programmer-feasibility-5zpw2h`
**الاختبارات:** 62/62 خضراء · **الوحدات:** 11 وحدة Python + فيرموير ESP32

منصّة تعليمية/بحثية متكاملة لتحليل إشارات مفاتيح السيارات (RF)، والتقاط ناقل
CAN والتحقّق منه، وطبقة نقل ISO-TP، وخدمات تشخيص UDS، وتخزين الأدلّة وتوليد
تقارير موحّدة — مبنية بمبدأ **«المحاكي أولًا، ثم العتاد»** واختبار آلي لكل طبقة.

---

## ⚖️ 0. النطاق والحدود الأخلاقية (يُقرأ أولًا)

هذه منصّة **بحث وتعلّم على مقعد اختبار معزول بعتاد يملكه المستخدم**. الحدود
مفروضة **تصميميًا لا سياسيًا**:

| ✅ ضمن النطاق | ❌ خارج النطاق (غير منفّذ ولن يُنفّذ) |
|---|---|
| التقاط RF **استقبال فقط** لمفتاح مملوك | إعادة إرسال (Replay) · تشويش (Jamming) |
| تحليل OOK/ASK وفكّه إلى بتات | كسر Rolling Code لتشغيل مركبة |
| التقاط CAN والتحقّق منه على مقعد معزول | توجيه ضد مركبة لا يملكها المستخدم |
| ISO-TP + خدمات UDS للقراءة (0x10/0x22/0x3E/0x19/0x14) | SecurityAccess (0x27): يُرفض NRC 0x11 بلا منطق Seed |
| محاكاة ECU وتوثيق آلية الحماية | كتابة (0x2E) · تفليش (0x34/0x36) · RoutineControl حرج |

> 🔒 **حدّ الأمان مفروض كودًا:** أي SID خارج النطاق المدعوم (0x27 ضمنه) يردّ
> `NRC 0x11 serviceNotSupported` — **لا خوارزمية Seed→Key في المستودع إطلاقًا.**
> نفس المبدأ المفروض في [دراسة اللوكسمِث](../car-key-programmer/README.md).

**الرابط مع مشروع اللوكسمِث:** مساران متعايشان في المستودع دون تداخل — ذاك منتج
خدمة تجاري يتجنّب لمس الحماية، وهذا بحث أمني على عتاد المستخدم.

---

## 1. المعمارية — الطبقات والتدفّق

```
   ┌─────────────────────── طبقة RF (لاسلكي) ───────────────────────┐
   │  [مفتاح 433.92MHz] → RTL-SDR (استقبال) → capture_rtlsdr        │
   │        → ook_decode (مغلّف→عتبة→نبضات→بتات) → plot_timing       │
   │        → AnalysisResult → JSON + SQLite(captures/pulses)        │
   └────────────────────────────────────────────────────────────────┘

   ┌─────────────────────── طبقة CAN (سلكي) ────────────────────────┐
   │  [ECU/محاكي] → can_simulator ──┐                                │
   │  [ESP32 عتاد] → serial_capture ┤→ can_interface (تحقّق+تأطير)   │
   │                                 └→ SQLite(can_captures/can_frames)│
   └────────────────────────────────────────────────────────────────┘

   ┌──────────── طبقة النقل + التشخيص (ISO-TP + UDS) ────────────────┐
   │  isotp (SF/FF/CF/FC · BS · STmin · تحقّق تسلسل)                 │
   │        ↕                                                        │
   │  uds_services (UDSServer + ExtendedUDSServer: 0x10/0x22/0x3E     │
   │               /0x19/0x14 · حدّ 0x27)                             │
   └────────────────────────────────────────────────────────────────┘

   ┌──────────── مسار التكامل + الأدلّة + التقرير ────────────────────┐
   │  diag_pipeline:  CAN → ISO-TP → UDS → Evidence (مسار واحد متصل)  │
   │  database:  EvidenceDB · CanEvidenceDB · UDSEvidenceDB           │
   │  evidence_reporter:  RF+CAN+UDS → تقرير موحّد (JSON/Markdown)     │
   └────────────────────────────────────────────────────────────────┘
```

---

## 2. الوحدات الـ12 (مرجع سريع)

### وحدات Python (11)
| # | الوحدة | أسطر | الطبقة | الدور |
|---|---|---|---|---|
| 1 | `rf/code/capture_rtlsdr.py` | 60 | RF | التقاط IQ خام (استقبال فقط) → complex64 |
| 2 | `rf/code/ook_decode.py` | 313 | RF | فكّ OOK/ASK كامل → بتات + JSON + SQLite |
| 3 | `rf/code/plot_timing.py` | 88 | RF | مخطط زمني ثلاثي للتقرير |
| 4 | `rf/code/database.py` | 433 | التخزين | `EvidenceDB`/`CanEvidenceDB`/`UDSEvidenceDB` |
| 5 | `rf/code/can_interface.py` | 209 | CAN | تحقّق الإطارات + تأطير USB + ابتلاع |
| 6 | `rf/code/can_simulator.py` | 104 | CAN | مولّد إطارات + مقياس أداء |
| 7 | `rf/code/serial_capture.py` | 114 | CAN | جسر ESP32 التسلسلي → SQLite |
| 8 | `rf/code/isotp.py` | 307 | النقل | ISO-TP: تجزئة/تجميع + FC/BS + تسلسل |
| 9 | `rf/code/uds_services.py` | 136 | التشخيص | UDS + خدمات DTC الموسّعة |
| 10 | `rf/code/diag_pipeline.py` | 119 | التكامل | مسار CAN→ISO-TP→UDS→Evidence |
| 11 | `rf/code/evidence_reporter.py` | 136 | التقرير | تقرير موحّد RF+CAN+UDS |

### فيرموير (1)
| 12 | `phase3b/esp32_can_bridge/esp32_can_bridge.ino` | 110 | العتاد | جسر CAN→USB (⚠️ غير مُختبَر على عتاد) |

---

## 3. مخطّط قاعدة البيانات (6 جداول، 3 مجالات معزولة)

```
RF   : captures ─< pulses_analysis
CAN  : can_captures ─< can_frames
UDS  : uds_sessions ─< uds_messages
```
- كل مجال **معزول** (لا مفاتيح أجنبية متقاطعة بين المجالات).
- **FK مفعّل** في المجالات الثلاثة (`PRAGMA foreign_keys=ON`) → لا رسائل يتيمة.
- `ON DELETE CASCADE` من الأب إلى الأبناء.
- BLOBs (payload) تُخزَّن خامًا وتُصدَّر hex في التقارير.
- المخطّط الكامل: [`schema/vehicle_db.sql`](schema/vehicle_db.sql) (لوكسمِث) +
  DDL مضمّن في `database.py` (RF/CAN/UDS).

---

## 4. مجموعة الاختبارات (62 اختبارًا)

| ملف | عدد | يغطّي |
|---|---|---|
| `test_database.py` | 8 | RF: مخطّط، FK، CASCADE، ثبات، JSON، خطّ OOK اصطناعي |
| `test_can.py` | 20 | تحقّق CAN، تأطير USB+CRC+resync، أداء 500f/s، توافق فيرموير بايت-لبايت |
| `test_iso_tp.py` | 5 | ISO-TP الأساسي (SF/FF/CF + خدمات UDS) |
| `test_uds_database.py` | 6 | UDS evidence: FK، CASCADE، عزل، قيد الاتجاه |
| `test_uds_dtc.py` | 5 | خدمات DTC (0x19/0x14) + بقاء الخدمات الأساسية |
| `test_integration.py` | 14 | ISO-TP FC/BS + تسلسل + المسار الكامل + DTC عبر المسار |
| `test_reporter.py` | 4 | التقرير الموحّد JSON/Markdown + قاعدة جزئية |
| **الإجمالي** | **62** | **كلها خضراء** |

### التشغيل
```bash
cd docs/can-research-bench/rf/code
for t in test_database test_can test_iso_tp test_uds_database \
         test_uds_dtc test_integration test_reporter; do python3 $t.py; done
```

---

## 5. أمثلة تشغيل

```bash
# 1) تحليل إشارة RF (استقبال فقط) → تقرير
python3 ook_decode.py signal.iq --rate 2.048e6 --json out.json --db evidence.db

# 2) مقياس أداء محاكي CAN → SQLite
python3 can_simulator.py --count 2000 --rate 500 --db evidence.db

# 3) جسر ESP32 (على العتاد) — منطقه مُختبَر عبر --selftest
python3 serial_capture.py --selftest
python3 serial_capture.py --port /dev/ttyUSB0 --baud 2000000 --db evidence.db

# 4) مسار تشخيص متكامل برمجيًا (بايثون)
python3 -c "from diag_pipeline import DiagnosticPipeline; \
from uds_services import ExtendedUDSServer; \
p=DiagnosticPipeline('evidence.db', ecu=ExtendedUDSServer()); \
print(p.request(b'\\x22\\xF1\\x90')); p.close()"

# 5) تقرير أدلّة موحّد
python3 evidence_reporter.py evidence.db --format markdown --out report.md
```

---

## 6. تاريخ المراحل (Phase History)

| المرحلة | المحتوى | commit |
|---|---|---|
| Phase 1 | مقعد CAN: مراجعة مواصفة + ربط + بيئة فيرموير | `5014689` |
| RF | التقاط + فكّ OOK + مخطط | `be226ad` |
| Phase 2 | تخزين أدلّة RF على SQLite + JSON | `3bb34c4`/`c2b382f` |
| Phase 3 | CAN sniffing: محاكي + تحقّق + ابتلاع + SQLite | `55304bd` |
| Phase 3B | جسر ESP32 (كود متوافق، بانتظار عتاد) | `00d82af` |
| Phase 4A | ISO-TP + خدمات UDS (نسخة الـ Architect) | `878532e` |
| Phase 4B | تخزين أدلّة UDS + FC/BS + تسلسل + مسار تكامل | `27cdc40`/`459336b` |
| Phase 4C | خدمات DTC (0x19/0x14) | `61b30cd` |
| Phase 5 | تقرير الأدلّة الموحّد | `2741e36` |

---

## 7. حالة الصدق (Honest Status)

| المكوّن | الحالة |
|---|---|
| كل الطبقات البرمجية (RF/CAN/ISO-TP/UDS/Evidence/Report) | ✅ **مُختبَرة برمجيًا** (62/62) |
| توافق فيرموير ESP32 ↔ Host | ✅ **مُختبَر بايت-لبايت** آليًا |
| **تشغيل ESP32 على لوحة فعلية** | ⚠️ **غير مُتحقَّق** — الكود لم يُرفع ولم يلتقط إطارًا حقيقيًا |

> **الحلقة الوحيدة الناقصة:** التحقّق الميداني من الفيرموير على عتاد ESP32 حقيقي.
> كل ما عداه محاكاة كاملة مُختبَرة. راجع [phase3b/README.md](phase3b/README.md)
> لدليل الـ Bring-up ومعيار قبول العتاد.

### حدود تقنية موثّقة (مؤجَّلة، ليست عيوبًا)
- ISO-TP: 11-bit IDs + classical CAN فقط (لا 29-bit / CAN-FD / DoIP).
- `ISOTPSession` القديم (نسخة الـ Architect) بلا FC؛ النقل الواعي بالـ FC/BS
  في `ISOTPSender`/`ISOTPReceiver`/`isotp_transfer` (الطبقة المعتمدة للتكامل).
- STmin يُحترم عبر `sleep_fn` في النقل الحقيقي (مُعطَّل في الاختبارات للحتمية).

---

## 8. الفهرس

| المستند | المحتوى |
|---|---|
| [00-spec-review.md](00-spec-review.md) | مراجعة مواصفة العتاد (STM32/transceiver) |
| [phase1/](phase1/) | ربط CAN + بيئة الفيرموير |
| [phase3b/README.md](phase3b/README.md) | جسر ESP32 + دليل Bring-up |
| [phase4/00-spec.md](phase4/00-spec.md) | مواصفة ISO-TP/UDS المعتمدة |
| [rf/README.md](rf/README.md) | تحليل إشارة RF |
| `rf/code/` | كل وحدات الكود والاختبارات |

---

*منصّة بحثية تعليمية — للاستخدام على عتاد مملوك في بيئة معزولة فقط.*
