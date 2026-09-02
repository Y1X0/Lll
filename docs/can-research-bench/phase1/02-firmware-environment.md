# Phase 1 — إعداد بيئة الفيرموير (Firmware Environment)

> الهدف: بيئة تطوير STM32F407 جاهزة، ومشروع يقلع، ويهيّئ CAN1 + USB CDC + TIM2،
> ويرسل أول إطار خام إلى الـ Host. **لا Fuzzing في هذه المرحلة — بنية أساس فقط.**

---

## 1. اختيار سلسلة الأدوات (Toolchain)

| الخيار | الوصف | القرار |
|---|---|---|
| **STM32CubeIDE** | IDE رسمي من ST + CubeMX مدمج + مصحّح | ✅ **الأسرع للبدء** — يولّد تهيئة CAN/USB/Clock بصريًا |
| STM32CubeMX + Makefile + arm-none-eabi-gcc | توليد كود ثم بناء بسطر الأوامر | 🟢 للمتقدّمين/الأتمتة |
| PlatformIO (framework: stm32cube) | داخل VS Code | 🟢 بديل نظيف |
| libopencm3 / bare-metal سجلّات | تحكّم كامل، منحنى حادّ | 🟡 لاحقًا للأداء |

**التوصية للنموذج:** **STM32CubeIDE** (يولّد HAL + USB CDC middleware جاهزًا)، ثم نكتب منطق CAN/الحلقة يدويًا فوقه.

### التثبيت (Linux — Ubuntu/Debian)
```bash
# 1) STM32CubeIDE: نزّله من st.com (حساب مجاني) وثبّت الـ .deb
sudo dpkg -i st-stm32cubeide_*.deb || sudo apt -f install

# 2) بديل بسطر الأوامر (إن فضّلت Makefile)
sudo apt update
sudo apt install -y gcc-arm-none-eabi gdb-multiarch stlink-tools openocd make

# 3) صلاحية الوصول لمبرمجة ST-Link بلا sudo
sudo tee /etc/udev/rules.d/49-stlink.rules >/dev/null <<'RULES'
SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="3748", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374b", MODE="0666"
RULES
sudo udevadm control --reload-rules && sudo udevadm trigger

# 4) تحقّق من رؤية المبرمجة (ST-Link موصولة بـ STM32)
st-info --probe
```

### أداة الفلاش والتصحيح
- **البرمجة:** ST-Link V2 (رخيص ~$3) عبر دبابيس SWD: `SWDIO=PA13`, `SWCLK=PA14`, `GND`, `3V3`.
- **التصحيح:** OpenOCD + gdb-multiarch، أو مصحّح CubeIDE.
- **الطرفية التسلسلية للـ Host:** بعد تفعيل USB CDC سيظهر الجهاز كـ `/dev/ttyACM0`.

---

## 2. تهيئة CubeMX (الإعدادات الحرجة)

عند إنشاء المشروع في CubeIDE لشريحة `STM32F407VETx`:

### Clock
- مصدر: HSE = بلّورة 8MHz (على معظم اللوحات) → PLL → **SYSCLK = 168MHz**
- **APB1 = 42MHz** ← مهم: bxCAN و TIM2 على APB1؛ حساب توقيت البت يعتمد عليه (راجع §4)

### CAN1
- Mode: `Activated`
- الدبابيس: `PB8 = CAN1_RX`, `PB9 = CAN1_TX` (AF9)
- المعاملات (لسرعة 500 kbps @ APB1=42MHz): `Prescaler=6`, `BS1=13TQ`, `BS2=2TQ`, `SJW=1TQ`
  → `TQ = Presc/APB1 = 6/42MHz`; `bit = (1+13+2)·TQ = 16TQ`; `bitrate = 42MHz/(6·16) = 437.5k` ❌
  → **القيم الصحيحة لـ 500k بالضبط:** `Prescaler=6`, `BS1=11TQ`, `BS2=2TQ` → `42M/(6·14)=500k` ✅
  (نقطة العيّنة ≈ 85.7% — مناسبة)
- NVIC: فعّل `CAN1 RX0 interrupt`

### USB_OTG_FS
- Mode: `Device_Only`
- الدبابيس: `PA11 = DM`, `PA12 = DP`
- Middleware: `USB_DEVICE` → Class = `Communication Device Class (CDC)`

### TIM2 (للختم الزمني)
- Mode: `Internal Clock`
- Prescaler لجعل عدّاد بدقّة 1µs: `TIM2CLK` على APB1 = 84MHz (مضاعف) → `Prescaler = 84-1` → tick=1µs
- `Counter Period = 0xFFFFFFFF` (32-bit، يلتفّ كل ~71 دقيقة — كافٍ)
- ابدأه حرًّا بلا مقاطعة.

> ⚠️ راجع نقطة العيّنة وقيم TQ بعد التوليد. **أهم رقم أن يخرج bitrate = 500000 بالضبط**، وإلا
> فأخطاء استقبال متقطّعة يصعب تشخيصها.

---

## 3. هيكل المشروع

```
firmware/
├── Core/
│   ├── Inc/
│   │   ├── main.h
│   │   ├── can_bench.h        ← واجهة CAN (init, RX ISR hook, TX)
│   │   ├── ring_buffer.h      ← Circular buffer آمن مع ISR
│   │   └── host_proto.h       ← تأطير Host (Start/CmdID/Len/Payload/Checksum)
│   ├── Src/
│   │   ├── main.c             ← init + الحلقة الرئيسية (تفريغ الـ ring للـ USB)
│   │   ├── can_bench.c        ← تهيئة CAN1 + معالج HAL_CAN_RxFifo0MsgPendingCallback
│   │   ├── ring_buffer.c
│   │   ├── host_proto.c       ← ترميز/فكّ الإطارات نحو/من الـ Host
│   │   └── stm32f4xx_it.c     ← نواقل المقاطعات
├── USB_DEVICE/               ← مولّد من CubeMX (CDC)
├── Drivers/                  ← HAL
└── firmware.ioc              ← ملف CubeMX
```

### توزيع المسؤوليات
| الوحدة | المسؤولية | القاعدة الحرجة |
|---|---|---|
| `can_bench.c` (ISR) | نسخ الإطار + طابع TIM2 إلى الـ ring | **لا معالجة داخل ISR — نسخ وخروج فقط** |
| `ring_buffer.c` | تخزين آمن بين ISR والحلقة | مؤشّرات `volatile`، ذرّية على 32-bit |
| `main.c` (الحلقة) | سحب من الـ ring → تأطير → USB CDC | يراقب علم Overrun ويرسله كحدث |
| `host_proto.c` | تنفيذ التأطير المتّفق عليه | Checksum على كل إطار |

---

## 4. منطق ISR الاستقبال (الجوهر)

```c
/* داخل can_bench.c — يُستدعى من HAL عند وصول إطار إلى FIFO0 */
void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef *hcan)
{
    CAN_RxHeaderTypeDef rx;
    uint8_t data[8];

    /* اقرأ الطابع الزمني فورًا — أول شيء، قبل أي عمل آخر */
    uint32_t ts_us = __HAL_TIM_GET_COUNTER(&htim2);

    if (HAL_CAN_GetRxMessage(hcan, CAN_RX_FIFO0, &rx, data) != HAL_OK)
        return;

    can_record_t rec;
    rec.ts_us  = ts_us;
    rec.can_id = (rx.IDE == CAN_ID_EXT) ? rx.ExtId : rx.StdId;
    rec.ext    = (rx.IDE == CAN_ID_EXT);
    rec.rtr    = (rx.RTR == CAN_RTR_REMOTE);
    rec.dlc    = rx.DLC;
    for (uint8_t i = 0; i < rx.DLC && i < 8; i++) rec.data[i] = data[i];

    /* ادفع للـ ring — إن امتلأ، علّم فقدانًا (لا تحجب) */
    if (!ring_push(&rx_ring, &rec))
        g_overrun_count++;   /* يُرسَل لاحقًا كحدث تشخيصي */
}
```

**القاعدة:** ISR قصيرة قدر الإمكان. كل التأطير والإرسال عبر USB يحدث في الحلقة الرئيسية.

### الحلقة الرئيسية
```c
while (1) {
    can_record_t rec;
    while (ring_pop(&rx_ring, &rec)) {
        uint8_t frame[32];
        size_t n = host_encode_can(frame, &rec);   /* [0xAA][CMD][LEN][payload][CKSUM] */
        CDC_Transmit_FS(frame, n);
    }
    if (g_overrun_count) {
        host_send_event(EVT_RX_OVERRUN, g_overrun_count);
        g_overrun_count = 0;
    }
    /* لاحقًا: معالجة أوامر واردة من الـ Host (TX / config / fuzz-step) */
}
```

---

## 5. بروتوكول الـ Host (مطابق لمواصفتك + إضافات)

```
الإطار:  [START=0xAA] [CMD_ID] [LEN] [PAYLOAD ...] [CHECKSUM]
CHECKSUM = XOR على (CMD_ID .. آخر بايت payload)   ← بسيط وسريع
```

| CMD_ID | الاتجاه | المعنى | Payload |
|---|---|---|---|
| `0x01` CAN_RX | STM32→Host | إطار مستقبَل | ts(4) · id(4) · flags(1) · dlc(1) · data(0..8) |
| `0x02` CAN_TX | Host→STM32 | أرسل إطارًا | id(4) · flags(1) · dlc(1) · data(0..8) |
| `0x03` SET_BITRATE | Host→STM32 | غيّر سرعة الناقل | bitrate(4) |
| `0x04` SET_FILTER | Host→STM32 | ضبط الفلتر (افتراضي: مرّر الكل) | id(4) · mask(4) |
| `0x05` EVT | STM32→Host | حدث (Overrun/BusOff/Error) | evt_id(1) · count(4) |
| `0x06` PING/PONG | ثنائي | نبض حياة | — |

> ⚠️ **التأطير مع بايت بداية `0xAA` قد يتزامن مع بايت داخل البيانات.** لتجنّب سوء المزامنة على
> ناقل مزدحم: أضف **حقل طول صريح (LEN)** (موجود) + **Checksum** (موجود)، وعند فشل الـ Checksum
> يعيد الـ Host المزامنة بالبحث عن `0xAA` التالي. (كافٍ للنموذج؛ COBS كتحسين لاحق.)

---

## 6. معايير قبول Phase 1 (Definition of Done)

| # | المعيار | كيف نتحقّق |
|---|---|---|
| P1.1 | المشروع يقلع ويومض LED | مؤشّر حياة في الحلقة |
| P1.2 | USB CDC يظهر كـ `/dev/ttyACM0` | `dmesg | grep ACM` |
| P1.3 | CAN1 يُهيّأ بسرعة 500k بالضبط | حساب TQ + التقاط بمحلّل مرجعي |
| P1.4 | استقبال إطار من ECU المحاكى | ESP32+MCP2515 يرسل ID معروف |
| P1.5 | الإطار يصل الـ Host بطابع زمني صحيح | سكربت python يفكّ ويطبع |
| P1.6 | إرسال إطار من Host يظهر على الناقل | محلّل مرجعي يراه |
| P1.7 | كشف Overrun يُبلَّغ ولا يُخفى | إغراق الناقل عمدًا ومراقبة `EVT` |
| P1.8 | لا فقدان إطار عند حمل معتدل (~1000 f/s) | عدّاد متسلسل من المحاكي |

**عند اجتياز P1.1–P1.8 ⇒ ننتقل إلى Phase 2: طبقة ISO-TP + UDS في python على الـ Host.**

---

## 7. جانب الـ Host — نقطة البداية السريعة (بالتوازي)

بينما يُبنى الفيرموير، يمكن بدء تطوير طبقة python فورًا مقابل **CAN افتراضي** بلا أي عتاد:
```bash
# Linux: ناقل CAN وهمي لتطوير واختبار طبقات ISO-TP/UDS بلا عتاد
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

pip install python-can can-isotp udsoncan
# الآن طوّر Protocol/Engine layers ضد vcan0، ثم بدّل الناقل إلى جهاز STM32 لاحقًا
```
هذا يفصل تطوير البرمجيات عن جاهزية العتاد — **يوفّر أسابيع.**

> **ملخّص القرار:** ابنِ الفيرموير (هذا المستند) و**بالتوازي** طوّر طبقات python على `vcan0`.
> عند جاهزية P1.4، وصّل الاثنين. هذا أسرع مسار عملي.
