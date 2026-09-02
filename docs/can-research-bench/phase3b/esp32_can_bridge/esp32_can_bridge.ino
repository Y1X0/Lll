/*
 * esp32_can_bridge.ino — جسر CAN→USB لـ Phase 3B
 *
 * ⚠️ مكتوب، غير مُختبَر على عتاد من قِبلي. يجب رفعه واختباره على مقعدك.
 *
 * يقرأ إطارات CAN عبر TWAI المدمجة، ويغلّفها بالبروتوكول المتّفق عليه، ويرسلها
 * عبر USB CDC إلى الـ Host (serial_capture.py → PacketParser).
 *
 * ┌──────────────────────────────────────────────────────────────────────┐
 * │ عقد السلك — يجب أن يطابق can_interface.py::_HDR = struct(">dIBBB")      │
 * │  الرزمة: [0xAA][LEN_MSB][LEN_LSB][PAYLOAD ...][CRC_MSB][CRC_LSB]        │
 * │  LEN     = طول PAYLOAD  (Big-Endian, 2 بايت)                            │
 * │  PAYLOAD (Big-Endian, 15 + dlc بايت):                                   │
 * │    timestamp  double 64-bit  (8)   ← ثوانٍ (esp_timer_get_time()/1e6)   │
 * │    can_id     uint32          (4)                                       │
 * │    is_extended uint8          (1)                                       │
 * │    dlc        uint8           (1)                                       │
 * │    direction  uint8           (1)   ← 0=RX (الجهاز يتنصّت)              │
 * │    payload    dlc بايت        (0..8)                                    │
 * │  CRC-16-CCITT (poly 0x1021, init 0xFFFF) على PAYLOAD، Big-Endian        │
 * └──────────────────────────────────────────────────────────────────────┘
 *
 * ⚖️ مقعد معزول، عتاد مملوك. تنصّت فقط (RX). لا إرسال، لا ISO-TP/UDS.
 */
#include <driver/twai.h>
#include <esp_timer.h>
#include <string.h>

static const uint8_t START_BYTE = 0xAA;
static const uint8_t DIR_RX = 0;   // الجهاز يستقبل من الناقل

// أطراف الترانسيفر (TCAN332/SN65HVD230). عدّلها حسب توصيلك.
#define CAN_TX_PIN GPIO_NUM_5
#define CAN_RX_PIN GPIO_NUM_4

// CRC-16-CCITT (مطابق لـ crc16_ccitt في can_interface.py)
static uint16_t calculate_crc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; i++) {
    crc ^= ((uint16_t)data[i] << 8);
    for (uint8_t j = 0; j < 8; j++) {
      crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
  }
  return crc;
}

// كتابة عدد Big-Endian إلى مخزن
static size_t put_be(uint8_t *buf, uint64_t value, uint8_t nbytes) {
  for (int8_t i = nbytes - 1; i >= 0; i--)
    buf[nbytes - 1 - i] = (uint8_t)((value >> (8 * i)) & 0xFF);
  return nbytes;
}

void setup() {
  Serial.begin(2000000);
  // على ESP32-S3 (USB CDC أصلي) الـ baud يُتجاهَل؛ على ESP32 الكلاسيكي يمرّ عبر جسر UART.
  uint32_t t0 = millis();
  while (!Serial && (millis() - t0) < 2000) { delay(10); }

  twai_general_config_t g_config =
      TWAI_GENERAL_CONFIG_DEFAULT(CAN_TX_PIN, CAN_RX_PIN, TWAI_MODE_NORMAL);
  g_config.rx_queue_len = 64;   // طابور أعمق لتقليل الفقد عند الحمل العالي
  twai_timing_config_t t_config = TWAI_TIMING_CONFIG_500KBITS();
  twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  if (twai_driver_install(&g_config, &t_config, &f_config) != ESP_OK) return;
  twai_start();
}

void loop() {
  twai_message_t message;
  if (twai_receive(&message, pdMS_TO_TICKS(10)) != ESP_OK) return;

  uint8_t payload[32];
  size_t cur = 0;

  // 1) timestamp: double (ثوانٍ) — Big-Endian عبر تمثيل البتات
  double ts = (double)esp_timer_get_time() / 1e6;
  uint64_t ts_bits;
  memcpy(&ts_bits, &ts, 8);            // بتات IEEE-754 المحلية
  cur += put_be(payload + cur, ts_bits, 8);   // ثم نكتبها Big-Endian

  // 2) can_id (Big-Endian 32-bit)
  cur += put_be(payload + cur, (uint32_t)message.identifier, 4);

  // 3) is_extended
  payload[cur++] = message.extd ? 1 : 0;

  // 4) dlc
  uint8_t dlc = message.data_length_code;
  if (dlc > 8) dlc = 8;
  payload[cur++] = dlc;

  // 5) direction (0 = RX) — الحقل الذي كان مفقودًا
  payload[cur++] = DIR_RX;

  // 6) payload bytes
  for (uint8_t i = 0; i < dlc; i++) payload[cur++] = message.data[i];

  uint16_t payload_len = (uint16_t)cur;     // 15 + dlc
  uint16_t crc = calculate_crc16(payload, payload_len);

  Serial.write(START_BYTE);
  Serial.write((uint8_t)(payload_len >> 8));
  Serial.write((uint8_t)(payload_len & 0xFF));
  Serial.write(payload, payload_len);
  Serial.write((uint8_t)(crc >> 8));
  Serial.write((uint8_t)(crc & 0xFF));
}
