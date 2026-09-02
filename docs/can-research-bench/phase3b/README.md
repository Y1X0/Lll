# Phase 3B — جسر ESP32 CAN→USB: دليل Bring-up

> ⚠️ **حالة الصدق:** الفيرموير والجسر **مكتوبان، غير مُختبَرين على عتاد من قِبلي**
> (لا عتاد في بيئتي). ما اختبرته فعليًا: **توافق تنسيق السلك بايت-لبايت** بين الفيرموير
> والـ Host عبر اختبارات آلية (20/20). أنت تشغّل على المقعد وتعيد السجلّات لنقيّد النجاح.

---

## 🔴 تصحيحات على فيرموير الـ Architect (ثلاثة أخطاء تمنع العمل)

الفيرموير الأصلي **لن يتوافق** مع الـ Host الذي بنيناه واختبرناه. الـ Host مصدر الحقيقة
(`can_interface.py::_HDR = struct(">dIBBB")`)، فصُحّح الفيرموير ليطابقه:

| # | الخطأ في النسخة الأصلية | الأثر | التصحيح |
|---|---|---|---|
| 1 | `memcpy` يكتب **Little-Endian** (native ESP32) | الـ Host يتوقّع **Big-Endian** → كل حقل رقمي قمامة | كتابة Big-Endian يدويًا عبر `put_be()` |
| 2 | `timestamp` كـ **uint64 (ميكروثانية)** | الـ Host يفكّه كـ **double** (`>d`) → قيمة زمنية بلا معنى | إرسال **double بالثواني** (`esp_timer_get_time()/1e6`) |
| 3 | **حقل `direction` مفقود** (14 بايت ترويسة) | الـ Host يتوقّع **15 بايت** → إزاحة بايت تُفسد dlc/payload | إضافة بايت `direction = 0 (RX)` |

**دليل التصحيح (اختبار آلي):**
- `test_firmware_wire_layout_parses_on_host` — يعيد بناء بايتات الفيرموير المصحّح ويؤكّد فكّها صحيحة.
- `test_firmware_wrong_layout_would_fail` — يثبت أن التنسيق الأصلي يعطي قيمًا خاطئة.

---

## عقد السلك النهائي (يجب أن يتطابق الطرفان عليه)

```
الرزمة:  [0xAA][LEN_MSB][LEN_LSB][ PAYLOAD ...][CRC_MSB][CRC_LSB]
LEN      = طول PAYLOAD (Big-Endian, 2 بايت)
PAYLOAD  = (Big-Endian، 15 + dlc بايت):
   timestamp   double 64-bit   (8)   ثوانٍ
   can_id      uint32          (4)
   is_extended uint8           (1)
   dlc         uint8           (1)
   direction   uint8           (1)   0=RX
   payload     dlc بايت        (0..8)
CRC-16-CCITT (0x1021, init 0xFFFF) على PAYLOAD، Big-Endian
```

---

## الملفات

| الملف | الدور | مُختبَر؟ |
|---|---|---|
| [`esp32_can_bridge/esp32_can_bridge.ino`](esp32_can_bridge/esp32_can_bridge.ino) | فيرموير ESP32 (TWAI → USB) | ⚠️ مكتوب، اختبار عتاد عليك |
| [`../rf/code/serial_capture.py`](../rf/code/serial_capture.py) | جسر Host: منفذ تسلسلي → PacketParser → SQLite | ✅ منطقه مُختبَر (`--selftest`) |
| [`../rf/code/can_interface.py`](../rf/code/can_interface.py) | `PacketParser` + التحقّق + الابتلاع | ✅ 20/20 |

---

## قائمة تحقّق Bring-up (نفّذها بالترتيب)

### 1) العتاد (الطاقة مفصولة)
```
[ ] ESP32 GPIO5(TX)/GPIO4(RX) → TCAN332/SN65HVD230 (TXD/RXD)
[ ] الترانسيفر مغذّى 3.3V (لا 5V)
[ ] أرضي مشترك: ESP32 + الترانسيفر + عقدة الاختبار + التغذية
[ ] CANH↔CANH، CANL↔CANL
[ ] مقاومة الناقل ≈ 60Ω بالأومميتر (احذر الإنهاء المزدوج — راجع phase1/01-wiring §3)
[ ] تغذية مخبرية معزولة 5V/12V + مصهر
```

### 2) رفع الفيرموير
```
[ ] Arduino IDE: اللوحة = ESP32 المناسبة، المنفذ = /dev/ttyUSB0 (أو COMx)
[ ] عدّل CAN_TX_PIN/CAN_RX_PIN إن اختلفت توصيلتك
[ ] ESP32-S3؟ USB CDC أصلي (baud يُتجاهَل). كلاسيكي؟ عبر جسر UART @2Mbps
[ ] Upload بنجاح بلا أخطاء ترجمة
```

### 3) التقاط على الـ Host
```bash
pip install pyserial
# تحقّق أولًا من منطق الجسر بلا عتاد:
python ../rf/code/serial_capture.py --selftest        # يجب: SELFTEST PASS

# ثم الالتقاط الحقيقي من ESP32:
python ../rf/code/serial_capture.py \
    --port /dev/ttyUSB0 --baud 2000000 \
    --db can_evidence.db --idle 5
```

### 4) توليد إطارات من عقدة ثانية
- استخدم عقدة CAN ثانية (ESP32/Arduino+MCP2515 أو أداة USB-CAN) لإرسال إطارات معروفة على الناقل المعزول.
- راقب مخرج `[metrics]`.

---

## معيار قبول Phase 3B (لتقييده رسميًا)

| المقياس | الهدف |
|---|---|
| `framing_errors` | 0 (أو قريب جدًا — إعادة المزامنة تعمل) |
| `invalid_frames` | 0 على إطارات صحيحة معروفة |
| `dropped_frames` | 0 عند معدّل الاختبار |
| `stored_frames` | = عدد الإطارات المُرسَلة من العقدة الثانية |
| القيم في SQLite | can_id/dlc/payload تطابق ما أرسلته العقدة الثانية |

**أعد لي مخرج `[metrics]` + عيّنة `SELECT * FROM can_frames LIMIT 5` لنقيّد Phase 3B.**

---

## أخطاء شائعة أثناء Bring-up

| العرض | السبب المرجّح |
|---|---|
| لا إطارات إطلاقًا | إنهاء خاطئ · TX/RX معكوسان · أرضي غير مشترك · معدّل ناقل مختلف |
| `framing_errors` عالٍ | baud غير متطابق · فقد بايتات على الجسر · ضوضاء |
| can_id/payload مزاحة | تنسيق سلك غير متطابق (تأكّد أنك رفعت الفيرموير المصحّح، لا الأصلي) |
| `dropped_frames` > 0 | حمل ناقل يفوق طابور TWAI · زد `rx_queue_len` · باود USB أعلى |
| timestamp غريب | لم تُطبّق تصحيحات double/Big-Endian |
