# Phase 4 — Pre-Implementation Spec (APPROVED): ISO-TP & UDS Layer

**الأساس:** commit `00d82af` · الفرع `claude/car-key-programmer-feasibility-5zpw2h`
**الحالة:** معتمد من المستخدم — نطاق مضبوط.

---

## 1. الهدف
بناء طبقة نقل ISO-TP (ISO 15765-2) للرسائل > 8 بايت، وفوقها خدمات UDS (ISO 14229)
الأساسية، لتبادل أوامر تشخيص بين محاكي ECU وأداة الفحص في **بيئة معزولة برمجيًا**.

## 2. الحدّ الأمني (Security Boundary)
منصّة محاكاة تعليمية معزولة. **مستبعَد صراحةً ولن يُنفَّذ:**
- ❌ SecurityAccess (`0x27`) — لا Seed/Key، المحاكي يردّ `NRC 0x11`
- ❌ WriteDataByIdentifier (`0x2E`) · نقل بيانات/Flashing (`0x34/0x36/0x37`)
- ❌ RoutineControl (`0x31`) لمشغّلات حرجة · CommunicationControl (`0x28`)
- ❌ أي توجيه ضد مركبة حقيقية

## 3. الملفات (معتمدة)
| ملف | الدور |
|---|---|
| `rf/code/isotp.py` | محرك ISO-TP: SF/FF/CF/FC، BS، STmin، تجزئة/تجميع |
| `rf/code/uds_services.py` | عميل UDS: بناء الطلبات وفكّ الردود (+NRC) |
| `rf/code/uds_simulator.py` | محاكي ECU يردّ عبر ISO-TP/UDS (المحاكي أولًا) |
| `rf/code/test_iso_tp.py` | اختبارات ISO-TP + UDS + التكامل |

**اعتماديات:** بلا جديد — Pure Python. تبادل في الذاكرة عبر ناقل محاكى.

## 4. خدمات UDS (النطاق المعتمد)
| SID | الخدمة | الحالة |
|---|---|---|
| `0x10` | DiagnosticSessionControl | ✅ |
| `0x22` | ReadDataByIdentifier | ✅ (قراءة) |
| `0x3E` | TesterPresent | ✅ |
| `0x7F` | NegativeResponse | ✅ يُفكّ ويُصنّف |
| غير ذلك (`0x27` ضمنها) | — | ❌ يردّ `NRC 0x11` بلا منطق |

**NRC مدعوم:** `0x11` serviceNotSupported، `0x12` subFunctionNotSupported،
`0x13` incorrectLength، `0x31` requestOutOfRange، `0x78` responsePending.

## 5. ISO-TP (النطاق)
SF (≤7 بايت) · FF (طول 12-bit) · CF (تسلسل 4-bit دوّار) · FC (CTS/Wait/Overflow) ·
احترام BlockSize و STmin · حشو 8 بايت · أخطاء التسلسل/المهلة مصنّفة.
**حدود:** 11-bit IDs، classical CAN فقط (لا 29-bit، لا CAN-FD — مؤجّلة).

## 6. معايير القبول — التغطية الفعلية (Phase 4A)

اعتُمد تنفيذ الـ Architect (نسخة مبسّطة: encode/decode_stream على قائمة إطارات، بلا
تفاوض Flow Control حقيقي). التغطية الفعلية على commit التنفيذ:

| # | اختبار | الحالة الفعلية |
|---|---|---|
| T1 | ISO-TP SF ذهاب/عودة | ✅ مغطّى (test_single_frame) |
| T2 | رسالة طويلة FF+CF | ✅ مغطّى (test_multi_frame، 23 بايت) |
| T5 | `0x10` تبديل جلسة | ✅ مغطّى |
| T6 | `0x22` DID معروف | ✅ مغطّى |
| T8 | `0x3E` TesterPresent | ✅ مغطّى |
| T12 | انحدار | ✅ test_can 20/20 + test_database 8/8 |
| — | `0x27` حدّ الأمان | 🟡 **يعمل كودًا** (UDSServer يردّ NRC 0x11) لكن **غير مُختبَر** |
| T3 | احترام BlockSize / FC | ❌ **غير منفّذ** — decode_stream يتجاهل FC |
| T4 | تسلسل CF خاطئ | ❌ **غير مكتشَف** — لا تحقّق تسلسل (بيانات مبتورة صامتة عند فقد CF) |
| T7 | `0x22` DID مجهول → NRC 0x31 | 🟡 يعمل كودًا لكن غير مُختبَر |
| T9 | `0x7F` فكّ سلبي (عميل) | ❌ لا يوجد عميل فكّ (parse_response) في هذه النسخة |
| T11 | تكامل client⇄sim عبر ISO-TP | ❌ غير موجود (الاختبارات تفصل ISO-TP عن UDS) |

**حالة Phase 4A:** ✅ **الأساس يعمل** (SF/FF/CF segmentation+reassembly + 3 خدمات UDS)،
5/5 اختبارات تمرّ. لكن **ليست "Phase 4 كاملة"** بمقياس T1–T12 الأصلي: FC/BS والتحقّق من
التسلسل وعميل الفكّ والتكامل **مؤجّلة إلى Phase 4B** إن رغبتم.

**DoD المتحقّق فعلًا:** T1,T2,T5,T6,T8,T12 تمرّ بأمر فعلي، بلا كسر اختبار قائم.

## 7. تسلسل التنفيذ
1. `isotp.py` + T1–T4  2. `uds_simulator.py`  3. `uds_services.py` + T5–T10
4. تكامل T11 + انحدار T12  5. commit واحد + hash حقيقي.
