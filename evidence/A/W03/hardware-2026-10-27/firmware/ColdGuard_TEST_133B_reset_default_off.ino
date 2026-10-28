
#include <Arduino.h>
#include <esp_system.h>

// ========================================
// COLDGUARD TEST 133B
// A-W03-07 + A-W04-04
//
// IBT-2 DEFAULT OFF / RESET TEST
// AUTO MEASURE AFTER EACH BOOT
//
// SERIAL COMMANDS:
// R = Replay results
// X = Software reset
//
// TEC NEVER ACTIVATED BY FIRMWARE
// ========================================

// IBT-2
#define RPWM 5
#define REN  6
#define LEN  10

// PZEM-017 / TTL485
#define PZEM_RX 37
#define PZEM_TX 36

const uint32_t TEST_DURATION_MS = 20000UL;
const uint32_t SAMPLE_INTERVAL_MS = 1000UL;

const int MAX_SAMPLES = 25;

HardwareSerial pzem(2);

const uint8_t requestFrame[8] = {
  0x01, 0x04, 0x00, 0x00,
  0x00, 0x08, 0xF1, 0xCC
};

// ========================================
// STORED TEST DATA
// ========================================

uint32_t sampleTime[MAX_SAMPLES];
float voltageLog[MAX_SAMPLES];
float currentLog[MAX_SAMPLES];
float powerLog[MAX_SAMPLES];
bool validLog[MAX_SAMPLES];

int sampleCount = 0;

uint32_t validCount = 0;
uint32_t failedCount = 0;
uint32_t nonzeroCurrentCount = 0;

float maxCurrent = 0;
float maxPower = 0;

bool finished = false;

uint32_t testStart = 0;
uint32_t nextSample = 0;

esp_reset_reason_t resetReason;

// ========================================
// TEC OFF
// ========================================

void tecOff() {
  digitalWrite(RPWM, LOW);
  digitalWrite(REN, LOW);
  digitalWrite(LEN, LOW);
}

// ========================================
// MODBUS CRC16
// ========================================

uint16_t modbusCRC(
  const uint8_t *data,
  size_t len
) {
  uint16_t crc = 0xFFFF;

  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];

    for (int bit = 0; bit < 8; bit++) {
      if (crc & 1) {
        crc = (crc >> 1) ^ 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }

  return crc;
}

// ========================================
// READ 16-BIT REGISTER
// ========================================

uint16_t readU16(
  const uint8_t *data,
  size_t pos
) {
  return ((uint16_t)data[pos] << 8)
       | data[pos + 1];
}

// ========================================
// READ PZEM-017
// ========================================

bool readPZEM(
  float &voltage,
  float &current,
  float &power
) {
  while (pzem.available()) {
    pzem.read();
  }

  pzem.write(requestFrame, 8);
  pzem.flush();

  uint8_t rx[80];
  size_t count = 0;

  uint32_t start = millis();

  while (millis() - start < 800) {

    tecOff();

    while (pzem.available()) {
      uint8_t b = pzem.read();

      if (count < sizeof(rx)) {
        rx[count++] = b;
      }
    }

    // Valid PZEM response:
    // 01 04 10 [16 data bytes] [CRC2]
    //
    // Ignore possible 8-byte TX echo.

    for (size_t i = 0; i + 21 <= count; i++) {

      if (rx[i] != 0x01 ||
          rx[i + 1] != 0x04 ||
          rx[i + 2] != 0x10) {
        continue;
      }

      uint16_t calculated =
        modbusCRC(rx + i, 19);

      uint16_t received =
        (uint16_t)rx[i + 19] |
        ((uint16_t)rx[i + 20] << 8);

      if (calculated != received) {
        continue;
      }

      uint16_t r0 = readU16(rx, i + 3);
      uint16_t r1 = readU16(rx, i + 5);
      uint16_t r2 = readU16(rx, i + 7);
      uint16_t r3 = readU16(rx, i + 9);

      uint32_t rawPower =
        ((uint32_t)r3 << 16) | r2;

      voltage = r0 / 100.0f;
      current = r1 / 100.0f;
      power = rawPower / 10.0f;

      return true;
    }

    delay(1);
  }

  return false;
}

// ========================================
// RESET REASON
// ========================================

void printResetReason() {

  Serial.print("RESET_REASON: ");

  switch (resetReason) {

    case ESP_RST_POWERON:
      Serial.println("POWER_ON");
      break;

    case ESP_RST_SW:
      Serial.println("SOFTWARE_RESET");
      break;

    case ESP_RST_EXT:
      Serial.println("EXTERNAL_RESET");
      break;

    case ESP_RST_PANIC:
      Serial.println("PANIC_RESET");
      break;

    case ESP_RST_WDT:
      Serial.println("WATCHDOG_RESET");
      break;

    case ESP_RST_BROWNOUT:
      Serial.println("BROWNOUT_RESET");
      break;

    default:
      Serial.print("OTHER_CODE_");
      Serial.println((int)resetReason);
      break;
  }
}

// ========================================
// PRINT / REPLAY REPORT
// ========================================

void printReport() {

  tecOff();

  Serial.println();
  Serial.println("==============================");
  Serial.println("COLDGUARD TEST 133B");
  Serial.println("IBT-2 DEFAULT OFF TEST");
  Serial.println("==============================");

  printResetReason();

  Serial.println("CSV_BEGIN");
  Serial.println(
    "elapsed_ms,valid,voltage_v,current_a,power_w"
  );

  for (int i = 0; i < sampleCount; i++) {

    Serial.print(sampleTime[i]);
    Serial.print(",");

    if (validLog[i]) {

      Serial.print("1,");
      Serial.print(voltageLog[i], 2);
      Serial.print(",");
      Serial.print(currentLog[i], 2);
      Serial.print(",");
      Serial.println(powerLog[i], 1);

    } else {

      Serial.println("0,,,");

    }
  }

  Serial.println("CSV_END");

  Serial.println();
  Serial.println("------ SUMMARY ------");

  Serial.print("VALID_SAMPLES: ");
  Serial.println(validCount);

  Serial.print("FAILED_SAMPLES: ");
  Serial.println(failedCount);

  Serial.print("NONZERO_CURRENT_SAMPLES: ");
  Serial.println(nonzeroCurrentCount);

  Serial.print("MAX_CURRENT_A: ");
  Serial.println(maxCurrent, 2);

  Serial.print("MAX_POWER_W: ");
  Serial.println(maxPower, 1);

  Serial.println("RPWM: LOW");
  Serial.println("R_EN: LOW");
  Serial.println("L_EN: LOW");
  Serial.println("TEC COMMAND: OFF");

  if (validCount == 0) {

    Serial.println(
      "RESULT: NOT VERIFIED"
    );

  } else if (nonzeroCurrentCount > 0) {

    Serial.println(
      "RESULT: UNEXPECTED CURRENT"
    );

    Serial.println(
      "ACTION: DISCONNECT POWER"
    );

  } else {

    Serial.println(
      "RESULT: NO CURRENT DETECTED"
    );

    Serial.println(
      "SCOPE: AFTER FIRMWARE START ONLY"
    );
  }

  Serial.println("------------------------------");

  Serial.println("COMMANDS:");
  Serial.println("R = REPLAY REPORT");
  Serial.println("X = SOFTWARE RESET");

  Serial.println("==============================");
}

// ========================================
// SOFTWARE RESET
// ========================================

void softwareReset() {

  tecOff();

  Serial.println();
  Serial.println("==============================");
  Serial.println("SOFTWARE RESET REQUESTED");
  Serial.println("TEC: OFF");
  Serial.println("RESTARTING ESP32");
  Serial.println("==============================");

  Serial.flush();

  delay(100);

  ESP.restart();
}

// ========================================
// SETUP
// ========================================

void setup() {

  // Put output latches LOW before
  // configuring the GPIOs as outputs.

  digitalWrite(RPWM, LOW);
  digitalWrite(REN, LOW);
  digitalWrite(LEN, LOW);

  pinMode(RPWM, OUTPUT);
  pinMode(REN, OUTPUT);
  pinMode(LEN, OUTPUT);

  tecOff();

  resetReason = esp_reset_reason();

  // Initialize PZEM UART.
  pzem.begin(
    9600,
    SERIAL_8N1,
    PZEM_RX,
    PZEM_TX
  );

  Serial.begin(115200);

  Serial.println();
  Serial.println("==============================");
  Serial.println("COLDGUARD TEST 133B");
  Serial.println("AUTO BOOT / RESET OFF CHECK");
  Serial.println("==============================");

  printResetReason();

  Serial.println("TEC: OFF");
  Serial.println("TEST DURATION: 20 SECONDS");
  Serial.println("TEST STARTING AUTOMATICALLY");

  sampleCount = 0;

  validCount = 0;
  failedCount = 0;
  nonzeroCurrentCount = 0;

  maxCurrent = 0;
  maxPower = 0;

  finished = false;

  testStart = millis();
  nextSample = testStart;
}

// ========================================
// LOOP
// ========================================

void loop() {

  tecOff();

  // ====================================
  // TEST FINISHED
  // ====================================

  if (finished) {

    while (Serial.available()) {

      char c = Serial.read();

      if (c == 'R' || c == 'r') {

        printReport();

      } else if (c == 'X' || c == 'x') {

        softwareReset();

      }
    }

    delay(20);
    return;
  }

  // Clear unused input during sampling.
  // Commands become available after
  // the test is finished.
  while (Serial.available()) {
    Serial.read();
  }

  // ====================================
  // TEST RUNNING
  // ====================================

  uint32_t now = millis();

  if (now - testStart >= TEST_DURATION_MS ||
      sampleCount >= MAX_SAMPLES) {

    finished = true;

    printReport();

    return;
  }

  // Wait for next sample
  if ((int32_t)(now - nextSample) < 0) {

    delay(1);
    return;
  }

  nextSample += SAMPLE_INTERVAL_MS;

  float voltage = 0;
  float current = 0;
  float power = 0;

  bool ok = readPZEM(
    voltage,
    current,
    power
  );

  int index = sampleCount++;

  sampleTime[index] = millis() - testStart;
  validLog[index] = ok;

  voltageLog[index] = voltage;
  currentLog[index] = current;
  powerLog[index] = power;

  if (ok) {

    validCount++;

    if (current > maxCurrent) {
      maxCurrent = current;
    }

    if (power > maxPower) {
      maxPower = power;
    }

    if (current > 0.001f ||
        power > 0.001f) {

      nonzeroCurrentCount++;
    }

  } else {

    failedCount++;

  }

  tecOff();
}
