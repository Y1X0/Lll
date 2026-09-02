# 06 — قاعدة بيانات المركبات

## 1. المبدأ التصميمي الحاكم

> ❗ **الخطأ الأكبر الذي يرتكبه المبتدئون: فهرسة القاعدة على `(Make, Model, Year)`.**
> الواقع أن السلوك يتحدّد بـ **`(Generation, KeySystem, ECU Part Number, Market, KeyState)`**.
> RAV4 موديل 2014 قد يكون G-chip أو H-chip حسب شهر الإنتاج والسوق. سنة الصنع **مؤشّر ترجيحي فقط**.

لذلك القاعدة مقسّمة إلى **طبقتين**:
1. **طبقة الترجيح (Presumption)** — من VIN والسنة نتوقّع النظام المحتمل.
2. **طبقة التأكيد (Confirmation)** — من بصمة ECU الفعلية نؤكّد أو نصحّح.
**الإجراء لا يُعرض إلا بعد التأكيد.**

---

## 2. المخطّط (PostgreSQL في السحابة، SQLite على الجهاز)

راجع الملف الكامل: [`schema/vehicle_db.sql`](schema/vehicle_db.sql)

### الجداول الأساسية

```
makes ─┬─ models ─┬─ generations ─┬─ variants ────┬─ vehicle_profiles
       │          │               │               │
       │          │               └─ vin_patterns  └─ ecu_fingerprints
       │          │
key_systems ──────┴─ procedures ─┬─ procedure_steps
                                 ├─ required_equipment
                                 └─ authorization_requirements
```

| الجدول | الدور |
|---|---|
| `generations` | الجيل (XA20/XA30/XA40/XA50) بحدود إنتاج وأسواق |
| `variants` | التنويعة داخل الجيل: `(generation, market, production_from, production_to)` |
| `key_systems` | التصنيف: `MECHANICAL, TRANSPONDER_4C, TRANSPONDER_4D, TRANSPONDER_G, TRANSPONDER_H, SMART_KEY_G, SMART_KEY_H, SMART_KEY_2020PLUS` |
| `vehicle_profiles` | **ملف التعريف التشغيلي**: عناوين CAN، معدّل الناقل، DIDs الآمنة، إعدادات Padding/STmin |
| `ecu_fingerprints` | بصمات تأكيدية: أرقام قطع، عناوين استجابة، DIDs موجودة |
| `procedures` | الإجراء: `(variant, key_state, path)` حيث `path ∈ {SELF, OEM_PASSTHRU, REMOTE_TECH, DEALER_ONLY, NOT_SUPPORTED}` |
| `authorization_requirements` | ما يلزم قانونيًا: إثبات ملكية، اعتماد فنّي، حساب OEM |
| `procedure_status` | `VERIFIED / COMMUNITY_REPORTED / UNTESTED / DEPRECATED / BLOCKED` |

### الحقول المطلوبة في طلبك — أين تقع

| ما طلبته | الجدول | ملاحظة |
|---|---|---|
| Make / Model / Year | `makes`/`models`/`variants` | Year مشتق من `production_from/to` |
| Generation | `generations` | ✅ |
| ECU | `ecu_fingerprints` | متعدّد لكل تنويعة |
| Key Type / Transponder Type | `key_systems` | مدمجان في تصنيف واحد + حقل `transponder_family` |
| Diagnostic Protocol | `vehicle_profiles.protocol` | `CAN_ISOTP / KLINE_KWP / KLINE_9141` |
| Supported Functions | `procedures` | صفّ لكل وظيفة |
| Required Equipment | `required_equipment` | ✅ |
| Required Authorization | `authorization_requirements` | ✅ |
| Procedure Status | `procedures.status` | ✅ |
| Firmware Version | `procedures.min_firmware` | حدّ أدنى مطلوب |
| Notes | `procedures.notes` (متعدّد اللغات) | ar/en |

---

## 3. حقل `procedure.path` — أهم حقل في النظام

| القيمة | المعنى | ما تعرضه الواجهة |
|---|---|---|
| `SELF` | جهازنا ينفّذها بالكامل | "ابدأ الآن" |
| `OEM_PASSTHRU` | تحتاج برنامج OEM عبر جهازنا | "يتطلب جلسة OEM — التكلفة ~X — ابدأ الشراء" |
| `REMOTE_TECH` | فنّي معتمد عن بُعد | "احجز فنّيًا عن بُعد — السعر Y — التوفّر Z" |
| `DEALER_ONLY` | الوكالة فقط | "هذه المركبة تتطلب الوكالة. إليك أقرب مركز" |
| `NOT_SUPPORTED` | غير مدعوم بعد | "غير مدعوم — أبلغنا لنعطيه أولوية" |

> **الصدق التجاري ميزة:** إخبار الفنّي خلال 40 ثانية أن المركبة تحتاج الوكالة **يوفّر عليه ساعتين
> وسمعته أمام العميل.** هذا وحده سبب كافٍ للاشتراك، حتى لو لم ننفّذ ولا عملية كتابة واحدة.

---

## 4. حوكمة البيانات

### مصادر البيانات (مرتّبة بالموثوقية)
1. **قياس مباشر على مركبة** بواسطة فريقنا → `VERIFIED`
2. **وثائق OEM رسمية** (اشتراك بيانات فنية) → `VERIFIED`
3. **تقارير من الفنّيين** (تلقائيًا من الجهاز) → `COMMUNITY_REPORTED`
4. **استدلال من مركبات مشابهة** → `UNTESTED` (لا يُعرض كإجراء قابل للتنفيذ)

### حلقة التغذية الراجعة (أهم أصل تنافسي)
```
عملية فعلية → نتيجة (نجاح/فشل + سبب) → تلقائيًا إلى السحابة (مجهولة الهوية)
   → مراجعة بشرية أسبوعية → ترقية/تنزيل حالة الإجراء → دفعة تحديث للجميع
```
**بعد 500 عملية، تصبح القاعدة أدقّ من أي منافس في السوق الأردني — لأنها مبنية على أسطول الأردن الفعلي.**
هذا هو **الخندق الدفاعي الحقيقي للمشروع** ولا يمكن نسخه بالمال.

### إصدار البيانات
- كل حزمة بيانات لها `version` دلالي و `signature` (Ed25519).
- الجهاز/التطبيق يرفض أي حزمة غير موقّعة.
- تحديث تفاضلي (delta) لتوفير البيانات.

---

## 5. بيانات البذرة لـ MVP (RAV4)

الحدّ الأدنى لإطلاق v1.0:

| البند | العدد |
|---|---|
| `generations` | 4 (XA20, XA30, XA40, XA50) |
| `variants` | ~12 (مع تقسيم السوق: خليج / أوروبا / أمريكا) |
| `key_systems` | 6 |
| `vehicle_profiles` | ~8 |
| `procedures` | ~24 (4 حالات مفتاح × 6 تنويعات رئيسية) |
| `ecu_fingerprints` | ~20 — **تُبنى بالقياس، لا بالافتراض** |

**الجهد المقدّر: 3–5 أسابيع لمهندس واحد بوجود أسطول اختبار.**
