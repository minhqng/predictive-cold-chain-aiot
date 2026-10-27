#include <Arduino.h>
#include <Preferences.h>
#include <string.h>

// ColdGuard W03 / ESP32-S3 + existing 5V TTL485 auto-direction + PZEM-017.
// Wiring: ESP GPIO36 TX -> TTL485 RXD; TTL485 TXD -> 5k/10k divider -> GPIO37 RX.
// UART: 9600 8N1, the configuration verified with the existing W03 tests.
// Scope: PZEM shunt-profile setup only. No TEC/IBT-2 control, no automatic writes.
// WARNING: Never connect TTL485 5V TXD directly to the ESP32 GPIO37.

static const uint8_t SLAVE = 1;
static const uint8_t FC03 = 0x03;
static const uint8_t FC06 = 0x06;
static const uint16_t SHUNT_REGISTER = 0x0003;
static const uint16_t SHUNT_100A = 0x0000;
static const uint16_t SHUNT_50A = 0x0001;
static const int ESP_RX = 37, ESP_TX = 36;
static const uint32_t READ_TIMEOUT_MS = 300;

HardwareSerial Meter(1);
Preferences guard;
bool guardReady = false;
bool attemptedThisBoot = false;

static uint16_t crc16(const uint8_t *p, size_t n) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < n; ++i) {
    crc ^= p[i];
    for (uint8_t k = 0; k < 8; ++k)
      crc = (crc & 1U) ? uint16_t((crc >> 1U) ^ 0xA001U) : uint16_t(crc >> 1U);
  }
  return crc;
}

static bool crcOK(const uint8_t *p, size_t n) {
  if (n < 4) return false;
  return crc16(p, n - 2) == (uint16_t(p[n - 2]) | (uint16_t(p[n - 1]) << 8));
}

static void printHex(const uint8_t *p, size_t n) {
  for (size_t i = 0; i < n; ++i) {
    if (p[i] < 16) Serial.print('0');
    Serial.print(p[i], HEX);
    if (i + 1 != n) Serial.print(' ');
  }
  Serial.println();
}

static void makeRequest(uint8_t fn, uint16_t reg, uint16_t value, uint8_t out[8]) {
  out[0] = SLAVE;
  out[1] = fn;
  out[2] = uint8_t(reg >> 8);
  out[3] = uint8_t(reg);
  out[4] = uint8_t(value >> 8);
  out[5] = uint8_t(value);
  uint16_t crc = crc16(out, 6);
  out[6] = uint8_t(crc);
  out[7] = uint8_t(crc >> 8);
}

static void clearStale() {
  while (Meter.available() > 0) Meter.read();
}

// The actual W03 TTL485 can echo our own request (7-8 prefix bytes).
// Look for a CRC-validated FC03 response within the received byte stream.
static bool readConfig(uint16_t regs[4]) {
  uint8_t tx[8];
  makeRequest(FC03, 0, 4, tx);
  delay(100);
  clearStale();
  if (Meter.write(tx, 8) != 8) {
    Serial.println("#READ_FAIL tx_short");
    return false;
  }
  Meter.flush(true); // ESP32 Arduino core: wait until UART TX bytes leave the peripheral.

  uint8_t raw[96] = {};
  size_t n = 0;
  const uint32_t start = millis();
  while (uint32_t(millis() - start) < READ_TIMEOUT_MS) {
    while (Meter.available() > 0) {
      const int x = Meter.read();
      if (x < 0) break;
      if (n == sizeof(raw)) {
        Serial.println("#READ_FAIL rx_overflow");
        return false;
      }
      raw[n++] = uint8_t(x);
      // An FC03 4-register response is exactly 13 bytes.
      if (n >= 13) {
        const uint8_t *r = raw + n - 13;
        if (r[0] == SLAVE && r[1] == FC03 && r[2] == 8 && crcOK(r, 13)) {
          for (uint8_t k = 0; k < 4; ++k)
            regs[k] = (uint16_t(r[3 + 2 * k]) << 8) | r[4 + 2 * k];
          if (regs[2] != SLAVE || regs[3] > 3) {
            Serial.println("#READ_FAIL unexpected_slave_or_shunt");
            return false;
          }
          Serial.printf("#READ_PASS slave=%u shunt_reg=0x%04X high_v=%.2f low_v=%.2f prefix=%u\n",
                        unsigned(regs[2]), unsigned(regs[3]),
                        regs[0] / 100.0, regs[1] / 100.0,
                        unsigned(n - 13));
          return true;
        }
      }
      if (n >= 5) {
        const uint8_t *e = raw + n - 5;
        if (e[0] == SLAVE && e[1] == uint8_t(FC03 | 0x80) && crcOK(e, 5)) {
          Serial.printf("#READ_FAIL modbus_exception=0x%02X\n", unsigned(e[2]));
          return false;
        }
      }
    }
    delay(1);
  }
  Serial.print("#READ_FAIL timeout_raw=");
  printHex(raw, n);
  return false;
}

static void readOnly() {
  uint16_t regs[4] = {};
  if (readConfig(regs))
    Serial.printf("#PROFILE_RESULT shunt=%s raw=0x%04X\n",
                  regs[3] == SHUNT_50A ? "50A" :
                  (regs[3] == SHUNT_100A ? "100A" : "OTHER"),
                  unsigned(regs[3]));
  else Serial.println("#PROFILE_RESULT READ_FAILED");
}

// Exactly one device register write. No automatic retry on timeout or ambiguous echo.
static void set50Once() {
  if (!guardReady || attemptedThisBoot || guard.getBool("attempted", false)) {
    Serial.println("#STOP_WRITE50 persistent_one_shot_guard_locked");
    return;
  }
  Serial.println("#PRECHECK_READ_3 START");
  for (uint8_t k = 1; k <= 3; ++k) {
    uint16_t r[4] = {};
    if (!readConfig(r)) {
      Serial.printf("#STOP_WRITE50 precheck_read_%u_failed\n", unsigned(k));
      return;
    }
    if (r[3] == SHUNT_50A) {
      Serial.println("#ALREADY_50A no_write_required");
      return;
    }
    if (r[3] != SHUNT_100A) {
      Serial.printf("#STOP_WRITE50 unexpected_original_profile=0x%04X\n", unsigned(r[3]));
      return;
    }
  }

  // Persist the one-shot lock BEFORE transmitting FC06. If the reply is lost,
  // we must read the meter before deciding anything, not blindly resend FC06.
  attemptedThisBoot = true;
  if (guard.putBool("attempted", true) != 1) {
    Serial.println("#STOP_WRITE50 guard_persist_failed_no_write");
    return;
  }

  uint8_t tx[8];
  makeRequest(FC06, SHUNT_REGISTER, SHUNT_50A, tx);
  Serial.print("#WRITE50_FC06_TX_ONCE ");
  printHex(tx, sizeof(tx));
  delay(120);
  clearStale();
  const size_t written = Meter.write(tx, sizeof(tx));
  Meter.flush(true);
  if (written != sizeof(tx)) {
    Serial.println("#WRITE50_SEND_UNCERTAIN short_tx_no_retry");
  } else {
    Serial.println("#WRITE50_SENT exactly_one_attempt");
  }

  // A local TX echo can look exactly like an FC06 acknowledgement. Treat it
  // as ambiguous and use independently CRC-validated FC03 readbacks to prove.
  uint8_t raw[64] = {};
  size_t n = 0;
  const uint32_t t0 = millis();
  while (millis() - t0 < READ_TIMEOUT_MS) {
    while (Meter.available() > 0) {
      int v = Meter.read();
      if (v >= 0 && n < sizeof(raw)) raw[n++] = uint8_t(v);
    }
    delay(1);
  }
  Serial.print("#WRITE50_RX_ACK_OR_ECHO_UNTRUSTED ");
  printHex(raw, n);

  uint8_t verified = 0;
  for (uint8_t k = 1; k <= 3; ++k) {
    uint16_t r[4] = {};
    if (readConfig(r) && r[3] == SHUNT_50A) ++verified;
    else Serial.printf("#READBACK_NOT_50A_OR_FAILED n=%u\n", unsigned(k));
    delay(250);
  }
  if (verified == 3) Serial.println("#SET50_VERIFIED PASS readback=3/3 shunt_reg=0x0001");
  else Serial.printf("#SET50_UNCONFIRMED readback=%u/3 NO_SECOND_WRITE\n", unsigned(verified));
  Serial.println("#WRITE50_LOCKED No more FC06 from this firmware instance");
}

static void help() {
  Serial.println("#HELP READ | STATUS | WRITE50 | HELP (Serial Monitor: 115200 Newline)");
  Serial.println("#HELP WRITE50 triggers 3 FC03 prechecks, ONE FC06 write, then 3 FC03 readbacks");
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(200);
  delay(1000);
  Meter.setRxBufferSize(512);
  Meter.begin(9600, SERIAL_8N1, ESP_RX, ESP_TX);
  guardReady = guard.begin("w03_shunt50", false);
  Serial.println("#BOOT ColdGuard_W03_TTL485_SET50A_ONCE_8N1");
  Serial.println("#PINS gpio_tx=36 gpio_rx=37 via_existing_5k_10k_divider");
  Serial.println("#CONFIG slave=1 baud=9600 framing=8N1 shunt_reg=0x0003 target=0x0001");
  Serial.println("#SAFETY no_auto_write=1 no_tec_or_ibt2_control=1 no_fc41_no_fc42=1");
  Serial.printf("#GUARD nvs_ok=%u attempted_before=%u\n",
                unsigned(guardReady), unsigned(guardReady && guard.getBool("attempted", false)));
  help();
}

void loop() {
  if (!Serial.available()) { delay(10); return; }
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();
  if (cmd == "READ") readOnly();
  else if (cmd == "WRITE50") set50Once();
  else if (cmd == "STATUS")
    Serial.printf("#STATUS nvs_ok=%u attempted_boot=%u attempted_persistent=%u\n",
                  unsigned(guardReady), unsigned(attemptedThisBoot),
                  unsigned(guardReady && guard.getBool("attempted", false)));
  else if (cmd.length()) help();
}
