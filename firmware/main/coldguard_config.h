/*
 * ColdGuard firmware - W02 sensor foundation + W03 power/RS-485 + W04 TEC
 * commissioning configuration (Member A).
 *
 * Scope of this file: pins, identity, sampling cadence, DS18B20 ROM->role
 * map, MC-38 door configuration, the W03 RS-485/PZEM/IBT-2 logic
 * configuration, and the W04 fail-closed TEC control/telemetry parameters.
 * Everything that a bench operator may need to change lives here so that the
 * rest of the firmware stays free of scattered magic numbers.
 *
 * W04 ships with the TEC output stage compiled out. The control mechanism,
 * the authorization gate, the fault latch and the raw telemetry path are
 * complete and tested offline; no code path can energize the branch until
 * the hardware gates in docs/06 are measured and recorded.
 *
 * Authority:
 *   - evidence/A/as-built-pinmap-2026-10-27.md (as-built map v2, from the
 *     2026-10-25..27 bench sessions; it supersedes the docs/01 §11.7
 *     "Proposed GPIO mapping v1" table, which stays as history).
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

#define CG_FIRMWARE_VERSION "cg-w04-0.1.0"
#define CG_HARDWARE_CONFIG_ID "CG-HW-001"
#define CG_PIN_MAP_VERSION 2
/* Grammar v2 = grammar v1 line kinds, unchanged, plus the W03 PZEM/PZEM_CFG/
 * PZEM_RANGE lines. A v1 parser ignores the new kinds as unknown; a v2 parser
 * must still accept v1 captures. See cg_log.h and firmware/tools/cg_serial.py. */
#define CG_LOG_GRAMMAR_VERSION 2
#define CG_DEVICE_ID "coldguard-001"

/* ------------------------------------------------------------------ */
/* Board profile used by the pin guards below                          */
/* ------------------------------------------------------------------ */

/* The MAKDRIVERONE board carries an ESP32-S3R2 (2 MB Quad in-package
 * PSRAM) and an external W25Q32 Quad flash. GPIO26-32 are the SPI0/1
 * flash bus. GPIO33-37 are available on this profile; an Octal-PSRAM
 * part (S3R8/S3R8V) would additionally occupy them, so the guard below
 * is conditional on this switch instead of assuming either variant. */
#define CG_HW_PSRAM_OCTAL 0

/* ------------------------------------------------------------------ */
/* Pins - as-built map v2 (2026-10-27)                                 */
/* ------------------------------------------------------------------ */

/* DS18B20 DATA moved from GPIO10 to GPIO33 during TEST 129D: four ROMs
 * were read on the 33 bus. GPIO10 belongs exclusively to IBT-2 L_EN. */
#define CG_PIN_DS18B20_DATA 33
#define CG_PIN_BME280_SDA 21
/* SCL moved from GPIO33 to GPIO34 when the BME280 header was wired. */
#define CG_PIN_BME280_SCL 34
/* MC-38 moved from GPIO34 to GPIO35; GPIO34 now carries BME280 SCL. */
#define CG_PIN_MC38 35
#define CG_PIN_UART_TX_TO_MAX3485_DI 36
#define CG_PIN_UART_RX_FROM_MAX3485_RO 37
#define CG_PIN_IBT2_COOLING_PWM 5
#define CG_PIN_IBT2_REN 6
#define CG_PIN_IBT2_LEN 10
/* Compatibility name kept for the W02 log/actuator call sites: R_EN is the
 * enable that pin map v1 called "IBT-2 enable". L_EN is separate. */
#define CG_PIN_IBT2_ENABLE CG_PIN_IBT2_REN

/* Canonical MAX3485 DE/RE pin for the compiled-out MANUAL direction mode.
 * The as-built module is a TTL485-V2.0 (AUTO, no DE/RE), so this macro is
 * unused on the shipped hardware; it exists so the MANUAL option has a pin
 * to name. GPIO35 is the historical value and is now the MC-38 door input,
 * so selecting MANUAL with the default fails the guard below. */
#define CG_PIN_MAX3485_DE_RE 35

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
/* Compile-time GPIO ownership guards                                  */
/* ------------------------------------------------------------------ */

#define CG_GPIO_SAME(a, b) ((a) == (b))
#define CG_GPIO_IS_FLASH_BUS(p) ((p) >= 26 && (p) <= 32)
#define CG_GPIO_IS_OCTAL_PSRAM(p) ((p) >= 33 && (p) <= 37)
#define CG_GPIO_IS_STRAPPING(p) ((p) == 0 || (p) == 3 || (p) == 45 || (p) == 46)

/* One authoritative owner per pin. A duplicate here means two drivers
 * would configure the same pad in different modes. */
#if CG_GPIO_SAME(CG_PIN_DS18B20_DATA, CG_PIN_BME280_SDA) || \
    CG_GPIO_SAME(CG_PIN_DS18B20_DATA, CG_PIN_BME280_SCL) || \
    CG_GPIO_SAME(CG_PIN_DS18B20_DATA, CG_PIN_MC38) || \
    CG_GPIO_SAME(CG_PIN_DS18B20_DATA, CG_PIN_UART_TX_TO_MAX3485_DI) || \
    CG_GPIO_SAME(CG_PIN_DS18B20_DATA, CG_PIN_UART_RX_FROM_MAX3485_RO) || \
    CG_GPIO_SAME(CG_PIN_DS18B20_DATA, CG_PIN_IBT2_COOLING_PWM) || \
    CG_GPIO_SAME(CG_PIN_DS18B20_DATA, CG_PIN_IBT2_REN) || \
    CG_GPIO_SAME(CG_PIN_DS18B20_DATA, CG_PIN_IBT2_LEN) || \
    CG_GPIO_SAME(CG_PIN_BME280_SDA, CG_PIN_BME280_SCL) || \
    CG_GPIO_SAME(CG_PIN_BME280_SDA, CG_PIN_MC38) || \
    CG_GPIO_SAME(CG_PIN_BME280_SDA, CG_PIN_UART_TX_TO_MAX3485_DI) || \
    CG_GPIO_SAME(CG_PIN_BME280_SDA, CG_PIN_UART_RX_FROM_MAX3485_RO) || \
    CG_GPIO_SAME(CG_PIN_BME280_SDA, CG_PIN_IBT2_COOLING_PWM) || \
    CG_GPIO_SAME(CG_PIN_BME280_SDA, CG_PIN_IBT2_REN) || \
    CG_GPIO_SAME(CG_PIN_BME280_SDA, CG_PIN_IBT2_LEN) || \
    CG_GPIO_SAME(CG_PIN_BME280_SCL, CG_PIN_MC38) || \
    CG_GPIO_SAME(CG_PIN_BME280_SCL, CG_PIN_UART_TX_TO_MAX3485_DI) || \
    CG_GPIO_SAME(CG_PIN_BME280_SCL, CG_PIN_UART_RX_FROM_MAX3485_RO) || \
    CG_GPIO_SAME(CG_PIN_BME280_SCL, CG_PIN_IBT2_COOLING_PWM) || \
    CG_GPIO_SAME(CG_PIN_BME280_SCL, CG_PIN_IBT2_REN) || \
    CG_GPIO_SAME(CG_PIN_BME280_SCL, CG_PIN_IBT2_LEN) || \
    CG_GPIO_SAME(CG_PIN_MC38, CG_PIN_UART_TX_TO_MAX3485_DI) || \
    CG_GPIO_SAME(CG_PIN_MC38, CG_PIN_UART_RX_FROM_MAX3485_RO) || \
    CG_GPIO_SAME(CG_PIN_MC38, CG_PIN_IBT2_COOLING_PWM) || \
    CG_GPIO_SAME(CG_PIN_MC38, CG_PIN_IBT2_REN) || \
    CG_GPIO_SAME(CG_PIN_MC38, CG_PIN_IBT2_LEN) || \
    CG_GPIO_SAME(CG_PIN_UART_TX_TO_MAX3485_DI, CG_PIN_UART_RX_FROM_MAX3485_RO) || \
    CG_GPIO_SAME(CG_PIN_UART_TX_TO_MAX3485_DI, CG_PIN_IBT2_COOLING_PWM) || \
    CG_GPIO_SAME(CG_PIN_UART_TX_TO_MAX3485_DI, CG_PIN_IBT2_REN) || \
    CG_GPIO_SAME(CG_PIN_UART_TX_TO_MAX3485_DI, CG_PIN_IBT2_LEN) || \
    CG_GPIO_SAME(CG_PIN_UART_RX_FROM_MAX3485_RO, CG_PIN_IBT2_COOLING_PWM) || \
    CG_GPIO_SAME(CG_PIN_UART_RX_FROM_MAX3485_RO, CG_PIN_IBT2_REN) || \
    CG_GPIO_SAME(CG_PIN_UART_RX_FROM_MAX3485_RO, CG_PIN_IBT2_LEN) || \
    CG_GPIO_SAME(CG_PIN_IBT2_COOLING_PWM, CG_PIN_IBT2_REN) || \
    CG_GPIO_SAME(CG_PIN_IBT2_COOLING_PWM, CG_PIN_IBT2_LEN) || \
    CG_GPIO_SAME(CG_PIN_IBT2_REN, CG_PIN_IBT2_LEN)
#error "GPIO ownership conflict: one pin drives two peripherals in the active map"
#endif

/* Specific diagnostics for the historical conflicts. */
#if CG_GPIO_SAME(CG_PIN_DS18B20_DATA, CG_PIN_IBT2_LEN)
#error "DS18B20 DATA and IBT-2 L_EN cannot share a pin (as-built: DATA=GPIO33, L_EN=GPIO10)"
#endif
#if CG_GPIO_SAME(CG_PIN_BME280_SCL, CG_PIN_MC38)
#error "BME280 SCL and the MC-38 door input cannot share a pin (as-built: SCL=GPIO34, MC-38=GPIO35)"
#endif

/* MANUAL RS-485 direction owns one extra pin. In AUTO (as-built) no DE/RE
 * is wired, so the pin must not be claimed; with MANUAL selected it must
 * not collide with any other function - in particular not with MC-38 on
 * GPIO35, which pin map v1 wrongly used for DE/RE. The guard lives in the
 * RS-485 section below so that CG_RS485_DIR_MODE is already defined. */

#if CG_GPIO_IS_FLASH_BUS(CG_PIN_DS18B20_DATA) || \
    CG_GPIO_IS_FLASH_BUS(CG_PIN_BME280_SDA) || \
    CG_GPIO_IS_FLASH_BUS(CG_PIN_BME280_SCL) || \
    CG_GPIO_IS_FLASH_BUS(CG_PIN_MC38) || \
    CG_GPIO_IS_FLASH_BUS(CG_PIN_UART_TX_TO_MAX3485_DI) || \
    CG_GPIO_IS_FLASH_BUS(CG_PIN_UART_RX_FROM_MAX3485_RO) || \
    CG_GPIO_IS_FLASH_BUS(CG_PIN_IBT2_COOLING_PWM) || \
    CG_GPIO_IS_FLASH_BUS(CG_PIN_IBT2_REN) || \
    CG_GPIO_IS_FLASH_BUS(CG_PIN_IBT2_LEN)
#error "A pin is on the SPI0/1 flash bus (GPIO26-32) of the W25Q32 profile"
#endif

#if CG_HW_PSRAM_OCTAL && \
    (CG_GPIO_IS_OCTAL_PSRAM(CG_PIN_DS18B20_DATA) || \
     CG_GPIO_IS_OCTAL_PSRAM(CG_PIN_BME280_SCL) || \
     CG_GPIO_IS_OCTAL_PSRAM(CG_PIN_MC38) || \
     CG_GPIO_IS_OCTAL_PSRAM(CG_PIN_UART_TX_TO_MAX3485_DI) || \
     CG_GPIO_IS_OCTAL_PSRAM(CG_PIN_UART_RX_FROM_MAX3485_RO))
#error "Octal-PSRAM profile: GPIO33-37 are reserved for the memory bus"
#endif

#if CG_GPIO_IS_STRAPPING(CG_PIN_DS18B20_DATA) || \
    CG_GPIO_IS_STRAPPING(CG_PIN_BME280_SDA) || \
    CG_GPIO_IS_STRAPPING(CG_PIN_BME280_SCL) || \
    CG_GPIO_IS_STRAPPING(CG_PIN_MC38) || \
    CG_GPIO_IS_STRAPPING(CG_PIN_UART_TX_TO_MAX3485_DI) || \
    CG_GPIO_IS_STRAPPING(CG_PIN_UART_RX_FROM_MAX3485_RO) || \
    CG_GPIO_IS_STRAPPING(CG_PIN_IBT2_COOLING_PWM) || \
    CG_GPIO_IS_STRAPPING(CG_PIN_IBT2_REN) || \
    CG_GPIO_IS_STRAPPING(CG_PIN_IBT2_LEN)
#error "A strapping pin (GPIO0/3/45/46) is assigned to a peripheral"
#endif

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

/* UART1 is used; UART0 stays the console. The pins are the as-built map v2
 * (GPIO36 TX, GPIO37 RX) and are the same wires the W01 bench UART test used.
 * GPIO37 is fed from the TTL485-V2.0 receiver through a 10k/10k/10k divider
 * (~3.3 V), so the ESP32-S3 input is never driven by the 5 V rail directly. */
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

/* MANUAL DE/RE ownership guard (CG_RS485_DIR_MODE is defined above, so the
 * preprocessor evaluates the real value). AUTO claims no extra pin. */
#if CG_RS485_DIR_MODE == CG_RS485_DIR_MANUAL
#if CG_GPIO_SAME(CG_PIN_MAX3485_DE_RE, CG_PIN_DS18B20_DATA) || \
    CG_GPIO_SAME(CG_PIN_MAX3485_DE_RE, CG_PIN_BME280_SDA) || \
    CG_GPIO_SAME(CG_PIN_MAX3485_DE_RE, CG_PIN_BME280_SCL) || \
    CG_GPIO_SAME(CG_PIN_MAX3485_DE_RE, CG_PIN_MC38) || \
    CG_GPIO_SAME(CG_PIN_MAX3485_DE_RE, CG_PIN_UART_TX_TO_MAX3485_DI) || \
    CG_GPIO_SAME(CG_PIN_MAX3485_DE_RE, CG_PIN_UART_RX_FROM_MAX3485_RO) || \
    CG_GPIO_SAME(CG_PIN_MAX3485_DE_RE, CG_PIN_IBT2_COOLING_PWM) || \
    CG_GPIO_SAME(CG_PIN_MAX3485_DE_RE, CG_PIN_IBT2_REN) || \
    CG_GPIO_SAME(CG_PIN_MAX3485_DE_RE, CG_PIN_IBT2_LEN)
#error "MANUAL RS-485 DE/RE collides with another pin (GPIO35 is the MC-38 door input; choose a free pin)"
#endif
#if CG_GPIO_IS_FLASH_BUS(CG_PIN_MAX3485_DE_RE) || CG_GPIO_IS_STRAPPING(CG_PIN_MAX3485_DE_RE)
#error "MANUAL RS-485 DE/RE on a flash-bus or strapping pin"
#endif
#endif /* CG_RS485_DIR_MODE == CG_RS485_DIR_MANUAL */

/* A response chunk is considered complete after this much line silence. The
 * transport still returns as soon as the caller's buffer is full; the poll
 * loop below uses this only to stop waiting for more bytes after the last
 * received one. It must stay above the Modbus RTU 3.5-character gap (about
 * 4 ms at 9600 8N1) so a frame is not split by normal inter-byte spacing. */
#define CG_RS485_RX_IDLE_MS 10

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

/* As-built wiring (map v2): the controller drives all three logic inputs
 * it can influence - RPWM (GPIO5), R_EN (GPIO6) and L_EN (GPIO10). LPWM is
 * tied to GND on the module and is not a firmware output; R_IS/L_IS are
 * unconnected. The safe state is therefore RPWM low, R_EN low, L_EN low,
 * with LPWM physically low. W03 still generates no PWM. */
#define CG_ACTUATOR_RPWM_PIN CG_PIN_IBT2_COOLING_PWM
#define CG_ACTUATOR_REN_PIN CG_PIN_IBT2_REN
#define CG_ACTUATOR_LEN_PIN CG_PIN_IBT2_LEN
/* Compatibility alias: the W02 call sites and log line use "ENABLE". */
#define CG_ACTUATOR_ENABLE_PIN CG_ACTUATOR_REN_PIN

/* ------------------------------------------------------------------ */
/* W04 - TEC commissioning control (output stage compiled out)         */
/* ------------------------------------------------------------------ */

/* The W04 slice implements the fail-closed control mechanism and its
 * offline tests. It must not energize the TEC branch: the output stage is
 * compiled out and the hardware gates in docs/06 are not measured. Setting
 * this to 1 is a deliberate commissioning decision that requires recorded
 * gate evidence, not a build tweak. */
#define CG_TEC_OUTPUT_STAGE_ENABLED 0
#define CG_TEC_HARDWARE_GATES_VERIFIED 0

#if CG_TEC_OUTPUT_STAGE_ENABLED != 0 && CG_TEC_OUTPUT_STAGE_ENABLED != 1
#error "CG_TEC_OUTPUT_STAGE_ENABLED must be 0 or 1"
#endif
#if CG_TEC_OUTPUT_STAGE_ENABLED == 1 && CG_TEC_HARDWARE_GATES_VERIFIED != 1
#error "output stage requires the hardware gates in docs/06 to be verified and recorded"
#endif
#if CG_TEC_OUTPUT_STAGE_ENABLED == 1 && CG_ACTUATOR_ENABLE_ALLOWED != 1
#error "output stage requires the actuator authorization gate (CG_ACTUATOR_ENABLE_ALLOWED)"
#endif

/* Control loop cadence. The tick drives the fault checks, the bounded run
 * duration and the watchdog gap detection. */
#define CG_TEC_TICK_MS 100
#define CG_TEC_HEARTBEAT_TIMEOUT_MS 1000

/* Authorization window: ARM authorizes one bounded run. The token is
 * generated at boot and printed only on the local UART. */
#define CG_TEC_ARM_TTL_MS 120000

/* Fan hold after a stop or fault. This is a bench cool-down duration, not a
 * TEC operating limit, and it never authorizes output. */
#define CG_TEC_COOLDOWN_MS 60000

/* Duty requested by a console START. 0 refuses the command: the as-built
 * TEC has no established continuous rating, so no duty is claimed safe
 * (docs/06). It is set only after the commissioning measurements exist. */
#define CG_TEC_REQUEST_DUTY_PERMILLE 0

#define CG_TEC_TOKEN_LEN 9   /* 8 hex characters + NUL */
#define CG_TEC_REASON_LEN 40
#define CG_TEC_RUN_ID_LEN 33 /* 32 characters + NUL */
#define CG_TEC_PHASE_LEN 16

/* A thermal/power observation older than three periods is stale. A stale
 * observation is never reused as a current value. */
#define CG_TEC_STALE_THERMAL_MS (3 * CG_SAMPLE_PERIOD_MS)
#define CG_TEC_STALE_POWER_MS (3 * CG_PZEM_POLL_PERIOD_MS)

/* Raw telemetry line family. It carries its own schema version because it
 * is a separate stream: CG_LOG_GRAMMAR_VERSION stays 2 so W02/W03 captures
 * and their parser keep working unchanged. The limit bounds the whole raw
 * line that cg_log_raw_line() will transmit; a line above it is refused, never
 * truncated.
 *
 * W02/W03 frames need 1536 bytes. The longest #CG TELEM line actually
 * observed in the committed W04 captures is 1012 bytes, so 2560 is headroom,
 * not a number taken from a guess. The value stays at 2560 because Member A's
 * local H8 bench tree (deliberately outside this repository, fingerprinted in
 * evidence/A/W04/ARTIFACT-MANIFEST.md) reuses this guard and needs 2342; that
 * dependency is disclosed there instead of being documented as a W04 result.
 * W02/W03 output is unchanged and its captures stay parseable. */
#define CG_TELEMETRY_SCHEMA_VERSION 1
#define CG_TELEMETRY_PERIOD_MS 1000
#define CG_TELEMETRY_LINE_MAX 2560

/* Local operator console on UART0 (the log console). Commands share the
 * terminal with the log stream; the parser rejects every line it does not
 * understand, and a command that arrives half-typed is simply not parsed. */
#define CG_CONSOLE_ENABLED 1
#define CG_CONSOLE_UART_PORT 0
#define CG_CONSOLE_BAUD 115200
#define CG_CONSOLE_LINE_MAX 96

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
#define CG_LOG_AUTH "AUTH"
#define CG_LOG_TEC "TEC"
#define CG_LOG_TEC_LIMIT "TEC_LIMIT"
#define CG_LOG_TELEM "TELEM"
#define CG_LOG_ERROR "ERR"

/* Token printed instead of a number when a probe reading is not valid.
 * Never 0.0, never a previous value pretending to be current
 * (docs/01 PHY-DS-004). Parsers map it to an empty CSV cell. */
#define CG_INVALID_VALUE_TOKEN "nan"
