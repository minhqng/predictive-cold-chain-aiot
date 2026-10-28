#include <Arduino.h>
#include <string.h>

// ColdGuard W03: existing hardware only (ESP32-S3 right MCU + TTL485-V2.0 + PZEM-017).
// Read-only diagnostic, NEVER sends FC06 or any command to TEC / IBT-2.
// ESP TX GPIO36 -> TTL485 RXD; TTL485 TXD -> existing 5k/10k divider -> ESP RX GPIO37.
// TTL485 5V and PZEM communication power: keep existing wiring, common reference as verified.
// ESP USB COM4 115200 newline; PZEM UART 9600 8N1 (A/B test against V4 8N2), slave ID 1.
// Keep TEC electrically disabled; do not connect high-current shunt path for these tests.
// Arduino IDE 1.8.x needs type declarations before prototypes below.

struct Reply;
static uint16_t crc16(const uint8_t *data, size_t length);
static void printRaw(const uint8_t *data, size_t length);
static struct Reply poll(uint8_t fn, uint8_t qty);
static void show(const struct Reply &r, unsigned index, bool verbose);
static void batch(unsigned target, uint8_t fn, uint8_t qty, uint8_t attempts, uint32_t gapMs);
static void help();

HardwareSerial Meter(1);
static const int RX_PIN = 37;
static const int TX_PIN = 36;
static const uint8_t MODBUS_SLAVE = 1;
static const uint32_t READ_TIMEOUT_MS = 260;
static const uint32_t RETRY_DELAY_MS = 350;
static const uint16_t RAW_MAX = 128;

struct Reply {
  uint8_t raw[RAW_MAX] = {};
  uint16_t n = 0, prefixed = 0, stale = 0;
  uint16_t values[8] = {};
  uint8_t nValues = 0;
  uint8_t fn = 0;
  uint8_t exceptionCode = 0;
  bool valid = false, crcBad = false, overflow = false, exception = false, echo = false;
  uint32_t completeUs = 0;
};

static uint16_t crc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; ++b)
      crc = (crc & 1U) ? uint16_t((crc >> 1U) ^ 0xA001U) : uint16_t(crc >> 1U);
  }
  return crc;
}

static bool crcGood(const uint8_t *p, size_t n) {
  if (n < 4) return false;
  return crc16(p, n - 2) == (uint16_t(p[n-2]) | (uint16_t(p[n-1]) << 8));
}

static void printRaw(const uint8_t *p, size_t n) {
  if (!n) { Serial.println("NONE"); return; }
  for (size_t i = 0; i < n; ++i) {
    if (p[i] < 16) Serial.print('0');
    Serial.print(p[i], HEX);
    if (i + 1 < n) Serial.print(' ');
  }
  Serial.println();
}

static struct Reply poll(uint8_t fn, uint8_t qty) {
  Reply r;
  r.fn = fn;
  r.nValues = qty;
  uint8_t command[8] = {MODBUS_SLAVE, fn, 0, 0, 0, qty, 0, 0};
  const uint16_t reqCRC = crc16(command, 6);
  command[6] = uint8_t(reqCRC & 0xFF);
  command[7] = uint8_t(reqCRC >> 8);
  // No RX cleanup AFTER TX: that could erase the beginning of a real response.
  while (Meter.available()) { Meter.read(); ++r.stale; }
  if (Meter.write(command, 8) != 8) return r;
  Meter.flush(true);  // Arduino ESP32 core 3.3.x: wait for TX completion only.
  const uint32_t t0 = micros();
  const uint32_t tMs = millis();
  const size_t responseLen = size_t(5 + 2 * qty); // FC03/FC04 response.
  while (uint32_t(millis() - tMs) < READ_TIMEOUT_MS) {
    while (Meter.available()) {
      const int x = Meter.read();
      if (x < 0) break;
      if (r.n >= RAW_MAX) { r.overflow = true; continue; }
      r.raw[r.n++] = uint8_t(x);
      if (r.n >= 8 && memcmp(r.raw + r.n - 8, command, 8) == 0)
        r.echo = true;
      if (r.n >= 5) {
        const uint8_t *q = r.raw + r.n - 5;
        if (q[0] == MODBUS_SLAVE && q[1] == uint8_t(fn | 0x80U) && crcGood(q, 5)) {
          r.exception = true;
          r.exceptionCode = q[2];
          return r;
        }
      }
      // Sliding window tolerates partial TX echo and garbage, but NEVER accepts wrong CRC.
      if (r.n >= responseLen) {
        const size_t pos = r.n - responseLen;
        const uint8_t *q = r.raw + pos;
        if (q[0] == MODBUS_SLAVE && q[1] == fn && q[2] == uint8_t(qty * 2)) {
          if (crcGood(q, responseLen)) {
            for (uint8_t k = 0; k < qty; ++k)
              r.values[k] = uint16_t((uint16_t(q[3 + k*2]) << 8) | q[4 + k*2]);
            // FC03 config: validate slave and known shunt profiles, but DO NOT hardcode alarm limits.
            if (fn == 3 && (r.values[2] != MODBUS_SLAVE || r.values[3] > 3)) {
              r.crcBad = true;
              continue;
            }
            r.valid = true;
            r.prefixed = uint16_t(pos);
            r.completeUs = uint32_t(micros() - t0);
            return r;
          }
          r.crcBad = true;
        }
      }
    }
    delay(1);
  }
  return r;
}

static void show(const struct Reply &r, unsigned index, bool verbose) {
  if (!r.valid) {
    Serial.printf("#FAIL n=%u fn=0x%02X received=%u echo=%u crc_bad_candidate=%u exception=%u code=0x%02X stale=%u overflow=%u\n",
      index, r.fn, r.n, unsigned(r.echo), unsigned(r.crcBad), unsigned(r.exception),
      r.exceptionCode, r.stale, unsigned(r.overflow));
    Serial.print("#RX_RAW n="); Serial.print(index); Serial.print(' ');
    printRaw(r.raw, r.n);
    return;
  }
  if (r.fn == 3) {
    Serial.printf("#CFG_PASS n=%u slave=%u shunt_reg=0x%04X profile=%s high_alarm_v=%.2f low_alarm_v=%.2f prefix=%u echo=%u rx_complete_us=%lu\n",
      index, r.values[2], r.values[3], r.values[3] == 1 ? "50A" : (r.values[3] == 0 ? "100A" : "OTHER"),
      r.values[0] / 100.0, r.values[1] / 100.0, r.prefixed, unsigned(r.echo), (unsigned long)r.completeUs);
  } else if (r.fn == 4) {
    uint32_t powerRaw = uint32_t(r.values[2]) | (uint32_t(r.values[3]) << 16);
    uint32_t energyRaw = uint32_t(r.values[4]) | (uint32_t(r.values[5]) << 16);
    Serial.printf("#MEAS_PASS n=%u voltage_v=%.2f current_a=%.2f power_w=%.1f energy_wh=%lu alarm_h=0x%04X alarm_l=0x%04X prefix=%u echo=%u rx_complete_us=%lu\n",
      index, r.values[0] / 100.0, r.values[1] / 100.0, powerRaw / 10.0,
      (unsigned long)energyRaw, r.values[6], r.values[7], r.prefixed,
      unsigned(r.echo), (unsigned long)r.completeUs);
  }
  if (verbose) {
    Serial.print("#RX_RAW n="); Serial.print(index); Serial.print(' ');
    printRaw(r.raw, r.n);
  }
}

static void batch(unsigned target, uint8_t fn, uint8_t qty, uint8_t attempts, uint32_t gapMs) {
  unsigned logicalPass = 0, logicalFail = 0, recovered = 0;
  unsigned physicalPass = 0, physicalFail = 0, crcBad = 0, echo = 0;
  const uint32_t startMs = millis();
  Serial.printf("#RUN_START target=%u function=0x%02X qty=%u max_attempts=%u gap_after_sample_ms=%lu timeout_ms=%lu\n",
    target, fn, qty, attempts, (unsigned long)gapMs, (unsigned long)READ_TIMEOUT_MS);
  for (unsigned i = 1; i <= target; ++i) {
    bool success = false;
    Reply last;
    for (uint8_t attempt = 1; attempt <= attempts; ++attempt) {
      Reply r = poll(fn, qty);
      if (r.echo) ++echo;
      if (r.crcBad) ++crcBad;
      if (r.valid) {
        ++physicalPass;
        ++logicalPass;
        success = true;
        if (attempt > 1) { ++recovered; Serial.printf("#RECOVERED n=%u attempt=%u\n",i,attempt); }
        if (target == 1 || (i % 10 == 0)) show(r, i, false);
        break;
      }
      ++physicalFail;
      last = r;
      if (target <= 1 || attempt == attempts) show(r, i, true);
      if (attempt != attempts) delay(RETRY_DELAY_MS);
    }
    if (!success) ++logicalFail;
    if (i % 10 == 0 || i == target)
      Serial.printf("#PROGRESS n=%u logical_pass=%u fail=%u physical_pass=%u physical_fail=%u recovered=%u\n",
        i,logicalPass,logicalFail,physicalPass,physicalFail,recovered);
    if (i < target) delay(gapMs);
  }
  Serial.printf("#W3_RESULT logical_pass=%u/%u logical_fail=%u physical_pass=%u physical_fail=%u recovered=%u crc_candidate_attempts=%u echo_attempts=%u duration_ms=%lu read_only=1\n",
    logicalPass,target,logicalFail,physicalPass,physicalFail,recovered,crcBad,echo,
    (unsigned long)(millis()-startMs));
  if (physicalFail) Serial.println("#NOTE physical_errors_exist_even_if_logical_pass_is_100pct");
  if (fn == 4) Serial.println("#NOTE measured_values_require_reference_calibration_before_accuracy_claim");
  Serial.println("#RUN_DONE TEC_CONTROL_DISABLED FC06_DISABLED");
}

static void help() {
  Serial.println("#FRAMING_TEST TX_AND_RX=8N1 read_only=1 previous_baseline=8N2");
  Serial.println("#HELP CFG=1 FC03 config; RAW100=100 physical FC03 at 1Hz-ish no retry; CHECK=100 logical FC03 with up to 3 tries;");
  Serial.println("#HELP MEAS=1 FC04 V/I/P/Wh; MEAS100=100 logical FC04 reads; STATUS; HELP");
  Serial.println("#HELP keep TEC electrically disabled. For MEAS, supply PZEM measurement side safely; config-only test needs comm power.");
}

void setup() {
  Serial.begin(115200);
  delay(1200);
  Meter.setRxBufferSize(512);
  Meter.begin(9600, SERIAL_8N1, RX_PIN, TX_PIN);
  Serial.println("#BOOT ColdGuard_W03_TTL485_V4_8N1_TEST");
  Serial.println("#PINS esp_tx=36 esp_rx=37 ttl485_auto_5v_rx_via_5k_10k_divider");
  Serial.println("#SAFETY NO_FC06 NO_50A_WRITE NO_TEC_OR_IBT2_CONTROL");
  help();
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    command.toUpperCase();
    if (command == "CFG") batch(1, 3, 4, 1, 0);
    else if (command == "RAW100") batch(100, 3, 4, 1, 1000);
    else if (command == "CHECK") batch(100, 3, 4, 3, 1000);
    else if (command == "MEAS") batch(1, 4, 8, 1, 0);
    else if (command == "MEAS100") batch(100, 4, 8, 3, 1000);
    else if (command == "STATUS") Serial.println("#STATUS read_only=1 gpio_tx=36 gpio_rx=37 pzem=9600_8N1 attempts=3 retry=350ms sample_gap=1000ms");
    else if (command.length()) help();
  }
  delay(10);
}
