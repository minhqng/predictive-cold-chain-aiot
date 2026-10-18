/*
 * ColdGuard firmware - W02 sensor foundation configuration (Member A).
 *
 * Scope of this file: pins, identity, sampling cadence, DS18B20 ROM->role
 * map, MC-38 door configuration. Everything that a bench operator may need
 * to change lives here so that the rest of the firmware stays free of
 * scattered magic numbers.
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

#define CG_FIRMWARE_VERSION "cg-w02-0.1.0"
#define CG_HARDWARE_CONFIG_ID "CG-HW-001"
#define CG_PIN_MAP_VERSION 1
#define CG_LOG_GRAMMAR_VERSION 1
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
#define CG_LOG_ERROR "ERR"

/* Token printed instead of a number when a probe reading is not valid.
 * Never 0.0, never a previous value pretending to be current
 * (docs/01 PHY-DS-004). Parsers map it to an empty CSV cell. */
#define CG_INVALID_VALUE_TOKEN "nan"
