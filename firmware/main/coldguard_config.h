/*
 * ColdGuard firmware - W02 sensor foundation + W03 power/RS-485 configuration
 * (Member A).
 *
 * Scope of this file: pins, identity, sampling cadence, DS18B20 ROM->role
 * map, MC-38 door configuration, and the W03 RS-485/PZEM/IBT-2 logic
 * configuration. Everything that a bench operator may need to change lives
 * here so that the rest of the firmware stays free of scattered magic
 * numbers.
 *
 * Authority:
 *   - docs/01 section 11.7 "Proposed GPIO mapping v1" (subject to board
 *     verification; a change bumps pin_map_version, not the BOM).
 *   - docs/01 section 6.4/6.5 (T1 near door, T2 center, T3 far/opposite;
 *     identity is the ROM code, never a library enumeration index).
 *   - docs/01 section 8.2 (raw MC-38 level -> OPEN/CLOSED MUST be
 *     physically commissioned; firmware must not assume a polarity).
 *   - docs/01 section 11.8 (actuator must be OFF at reset/boot).
 *
 * ROM map matches evidence/A/W02/sensor-rom-map.yaml byte for byte. Any
 * change here must be accompanied by the same change in that record.
 */
#pragma once

/* ------------------------------------------------------------------ */
/* Identity                                                            */
/* ------------------------------------------------------------------ */

#define CG_FIRMWARE_VERSION "cg-w03-0.1.0"
#define CG_HARDWARE_CONFIG_ID "CG-HW-001"
#define CG_PIN_MAP_VERSION 1
/* Grammar v2 = grammar v1 line kinds, unchanged, plus the W03 PZEM/PZEM_CFG/
 * PZEM_RANGE lines. A v1 parser ignores the new kinds as unknown; a v2 parser
 * must still accept v1 captures. See cg_log.h and firmware/tools/cg_serial.py. */
#define CG_LOG_GRAMMAR_VERSION 2
#define CG_DEVICE_ID "coldguard-001"

/* ------------------------------------------------------------------ */
/* Pins - docs/01 section 11.7                                         */
/* ------------------------------------------------------------------ */

#define CG_PIN_DS18B20_DATA 10
#define CG_PIN_BME280_SDA 21
#define CG_PIN_BME280_SCL 33
#define CG_PIN_MC38 34
#define CG_PIN_MAX3485_DE_RE 35
#define CG_PIN_UART_TX_TO_MAX3485_DI 36
#define CG_PIN_UART_RX_FROM_MAX3485_RO 37
#define CG_PIN_IBT2_COOLING_PWM 5
#define CG_PIN_IBT2_ENABLE 6

/* W03 aliases. The as-built RS-485 interface for CG-HW-001 is NOT a MAX3485:
 * it is a TTL485-V2.0 (5 V rail, auto-direction transceiver, no DE//RE pin -
 * see evidence/A/W03/rs485-pin-and-compatibility.md and the W01 deviation
 * review CR-A-W01-01, still PENDING). The alias names describe the signal
 * role, not the chip, so the RFC of the transceiver can change without
 * touching the firmware logic. */
#define CG_PIN_RS485_TX CG_PIN_UART_TX_TO_MAX3485_DI
#define CG_PIN_RS485_RX CG_PIN_UART_RX_FROM_MAX3485_RO
#define CG_PIN_RS485_DE_RE CG_PIN_MAX3485_DE_RE

/* ------------------------------------------------------------------ */
/* DS18B20 acquisition - docs/01 sections 6.6 / 6.7                    */
/* ------------------------------------------------------------------ */

/* Effective thermal snapshot target: approximately 1 Hz. The loop is
 * deadline based, so the logged uptime is the real observation time and
 * no fake 1 Hz duplicate is ever emitted (docs/01 section 6.7). */
#define CG_SAMPLE_PERIOD_MS 1000

/* 12-bit resolution = 0.0625 C step, 750 ms worst-case conversion. */
#define CG_DS18B20_RESOLUTION_BITS 12
#define CG_DS18B20_CONVERSION_MS 750

/* DS18B20 scratchpad defaults: 85.0 C is the documented power-on reset
 * value and must never be reported as a plausible chamber temperature. */
#define CG_DS18B20_POWER_ON_RAW 0x0550
#define CG_DS18B20_MIN_C (-55.0f)
#define CG_DS18B20_MAX_C (125.0f)

/* Open-drain 1-Wire bus on the DS18B20 data pin (external 4.7k pull-up). */
#define CG_ONEWIRE_PIN CG_PIN_DS18B20_DATA

/* ------------------------------------------------------------------ */
/* Frozen ROM -> role map (W02), see evidence/A/W02/sensor-rom-map.yaml */
/* Every entry is the 8-byte ROM in wire order: family, 6 serial, CRC8. */
/* ------------------------------------------------------------------ */

/* T1 - assigned role: near-door region. Physical label: PENDING. */
#define CG_ROM_T1_BYTES {0x28, 0x70, 0x88, 0xCA, 0x00, 0x00, 0x00, 0x51}
/* T2 - assigned role: central region. Physical label: PENDING. */
#define CG_ROM_T2_BYTES {0x28, 0xAE, 0xBF, 0x22, 0x00, 0x00, 0x00, 0x06}
/* T3 - assigned role: far/opposite region. Physical label: PENDING. */
#define CG_ROM_T3_BYTES {0x28, 0xCB, 0xE9, 0xCA, 0x00, 0x00, 0x00, 0x72}
/* SPARE - not a measurement role; must stay outside T1/T2/T3. */
#define CG_ROM_SPARE_BYTES {0x28, 0x3B, 0xE5, 0xC9, 0x00, 0x00, 0x00, 0xA9}

/* Status string carried in every ROM line so the log itself states that
 * the physical label was not yet applied. */
#define CG_ROM_STATUS "ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING"

/* ------------------------------------------------------------------ */
/* MC-38 door - docs/01 section 8                                      */
/* ------------------------------------------------------------------ */

/* Raw level sampling period of the door task (FreeRTOS tick limited). */
#define CG_DOOR_POLL_MS 5

/* Debounce window. A raw level must stay stable for at least this long
 * before it becomes the committed state. Default 50 ms is ~50x shorter
 * than any deliberately controlled door-open interval used for a
 * disturbance test, so debounce cannot erase the treatment (docs/01
 * section 8.3). The value must be confirmed on the bench and then
 * recorded in the evidence dossier. */
#define CG_DOOR_DEBOUNCE_MS 50

/* Polarity is NOT commissioned yet (docs/01 section 8.2). While this is
 * 0 the firmware reports the door semantic state as UNVERIFIED and only
 * logs the raw electrical level. Set to 1 only after a physical
 * open/close observation, and then record CG_DOOR_RAW_OPEN_LEVEL and the
 * observation in the evidence dossier. */
#define CG_DOOR_POLARITY_CONFIRMED 0
#define CG_DOOR_RAW_OPEN_LEVEL 0

/* ------------------------------------------------------------------ */
/* W03 - RS-485 transport (docs/01 section 10, PHY-PZ-001)             */
/* ------------------------------------------------------------------ */

/* UART1 is used; UART0 stays the console. The pins are the proposed mapping
 * v1 (docs/01 11.7) and are the same wires the W01 bench UART test used. */
#define CG_RS485_UART_PORT 1

/* Framing is a commissioning parameter (docs/01 PHY-PZ-001). The circulated
 * PZEM-017 manual documents 9600 8N1 for newer units and 2 stop bits for
 * some older units, so the framing is configured here instead of being
 * hard-coded in the driver. Default is 8N1: the bench sketch that produced
 * the only reported PZEM response used 9600 8N1, and a stop-bit mismatch may
 * not be assumed until the shipped revision's manual is checked. */
#define CG_RS485_BAUD 9600
#define CG_RS485_DATA_BITS 8
#define CG_RS485_PARITY 0 /* 0 = none, 1 = even, 2 = odd */
#define CG_RS485_STOP_BITS 1

/* Direction control:
 *   0 = AUTO   - module has an auto-direction transceiver and exposes no
 *                DE//RE pin (as-built TTL485-V2.0, photo 03-rs485-back.jpg).
 *   1 = MANUAL - DE//RE on CG_PIN_RS485_DE_RE (canonical MAX3485 module).
 * The as-built hardware is AUTO; MANUAL is compiled out, not untested code
 * pretending to work on this module. */
#define CG_RS485_DIR_MODE 0
#define CG_RS485_DIR_MANUAL 1
#define CG_RS485_TX_DONE_TIMEOUT_MS 50

/* ------------------------------------------------------------------ */
/* W03 - PZEM-017 Modbus RTU (docs/01 section 9)                       */
/* ------------------------------------------------------------------ */

/* Slave address is a commissioning parameter; the shipped default is 1 and
 * it must be confirmed per module (docs/01 A-W03-03). */
#define CG_PZEM_SLAVE_ADDRESS 1

/* Response timeout and retry bound. A timeout is a classified result, not
 * a reason to loop forever. Attempts counts total tries per poll. */
#define CG_PZEM_RESPONSE_TIMEOUT_MS 250
#define CG_PZEM_MAX_ATTEMPTS 2
#define CG_PZEM_POLL_PERIOD_MS 1000
#define CG_PZEM_RX_MAX 32

/* Manual-derived register semantics (docs/01 9.3). Function 0x04 reads the
 * input registers; function 0x03 reads the holding register that carries the
 * current-range profile. There is deliberately no write function code in
 * the firmware: A-W03-04 is a READ-ONLY verification. */
#define CG_PZEM_FC_READ_HOLDING 0x03
#define CG_PZEM_FC_READ_INPUT 0x04

#define CG_PZEM_REG_VOLTAGE 0x0000
#define CG_PZEM_REG_CURRENT 0x0001
#define CG_PZEM_REG_POWER_L 0x0002
#define CG_PZEM_REG_POWER_H 0x0003
#define CG_PZEM_REG_ENERGY_L 0x0004
#define CG_PZEM_REG_ENERGY_H 0x0005
#define CG_PZEM_REG_INPUT_COUNT 6

/* Holding register 0x0003 carries the current-range profile. This address
 * overlaps input register 0x0003 (power high) on purpose: the meaning
 * depends on the function code, so the reader must never mix the two. */
#define CG_PZEM_HOLDING_CURRENT_RANGE 0x0003
#define CG_PZEM_RANGE_100A 0x0000
#define CG_PZEM_RANGE_50A 0x0001
#define CG_PZEM_RANGE_200A 0x0002
#define CG_PZEM_RANGE_300A 0x0003

/* Register least-significant-bit values (the scaling is part of the
 * contract, not a display detail). */
#define CG_PZEM_VOLT_LSB 0.01f  /* V per count   */
#define CG_PZEM_CURRENT_LSB 0.01f /* A per count */
#define CG_PZEM_POWER_LSB 0.1f  /* W per count   */
#define CG_PZEM_ENERGY_LSB 1.0f /* Wh per count  */

/* One read-only range check at boot; retried at this interval until it
 * succeeds. It never becomes a write path. */
#define CG_PZEM_RANGE_RETRY_MS 60000

/* ------------------------------------------------------------------ */
/* W03 - IBT-2 logic-only safe state (docs/01 sections 11.8, 12)       */
/* ------------------------------------------------------------------ */

/* W03 does not generate PWM and has no path that can energize the cooling
 * branch. The guard below is the invariant the future PWM layer must honour
 * before it may drive outputs (W04+): output is allowed only when an
 * operator authorization exists AND at most one direction carries non-zero
 * duty. With CG_ACTUATOR_ENABLE_ALLOWED at 0 the firmware refuses every
 * request, so a stray call in W03 cannot turn the TEC branch on. */
#define CG_ACTUATOR_ENABLE_ALLOWED 0

/* The as-built wiring noted in W01 (pin map v1, docs/01 11.7) drives the
 * module with two logic signals: RPWM and a shared enable. The other IBT-2
 * inputs (LPWM, second enable) are a hardware tie-off decision that Member D
 * must review before any powered test. W03 firmware only drives the two
 * documented pins. */
#define CG_ACTUATOR_RPWM_PIN CG_PIN_IBT2_COOLING_PWM
#define CG_ACTUATOR_ENABLE_PIN CG_PIN_IBT2_ENABLE

/* ------------------------------------------------------------------ */
/* Boot identity proof - docs/05A A-W02-03                             */
/* ------------------------------------------------------------------ */

/* NVS namespace/keys for the reboot counter that makes >=5 reboot
 * identity cycles verifiable from a single serial capture. */
#define CG_NVS_NAMESPACE "coldguard"
#define CG_NVS_KEY_BOOT_COUNT "boot_count"

/* ------------------------------------------------------------------ */
/* Serial log grammar tokens (parsed by firmware/tools/cg_serial.py)   */
/* ------------------------------------------------------------------ */

#define CG_LOG_PREFIX "#CG"
#define CG_LOG_BANNER "LOG"
#define CG_LOG_BOOT "BOOT"
#define CG_LOG_ROM "ROM"
#define CG_LOG_ROMS "ROMS"
#define CG_LOG_SAMPLE "SAMPLE"
#define CG_LOG_DOOR_EDGE "DOOR_EDGE"
#define CG_LOG_DOOR_STATE "DOOR_STATE"
#define CG_LOG_DOOR_POLARITY "DOOR_POLARITY"
#define CG_LOG_SAFETY "SAFETY"
#define CG_LOG_PZEM_CFG "PZEM_CFG"
#define CG_LOG_PZEM_RANGE "PZEM_RANGE"
#define CG_LOG_PZEM "PZEM"
#define CG_LOG_ERROR "ERR"

/* Token printed instead of a number when a probe reading is not valid.
 * Never 0.0, never a previous value pretending to be current
 * (docs/01 PHY-DS-004). Parsers map it to an empty CSV cell. */
#define CG_INVALID_VALUE_TOKEN "nan"
