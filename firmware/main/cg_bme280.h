/*
 * ColdGuard firmware - BME280 ambient environment producer (A-W02-06).
 *
 * The producer is split so the parts that decide *what the sensor said* can be
 * executed on a host without ESP-IDF headers: this header and cg_bme280.c are
 * pure C plus an injected port, and the only file that touches the I2C driver
 * is cg_bme280_idf.c. That split is what lets firmware/tools/tests/
 * cg_bme280_harness.c compile the real, unchanged decision logic.
 *
 * Bosch facts this file depends on, taken from the BME280 datasheet and from
 * BoschSensortec/BME280_driver rather than recalled: chip id 0x60 at 0xD0;
 * CTRL_HUM 0xF2, STATUS 0xF3, CTRL_MEAS 0xF4, CONFIG 0xF5, RESET 0xE0; mode
 * sleep/forced/normal 0/1/3; osrs_h CTRL_HUM 2:0, osrs_p CTRL_MEAS 4:2, osrs_t
 * 7:5; STATUS bit 0 is the NVM im_update flag that must clear before calibration
 * is trustworthy. Trim types follow the reference driver's calibration struct:
 * dig_H1 and dig_H3 unsigned, dig_H2/H4/H5 signed 16, dig_H6 signed 8. Humidity
 * compensation is Q22.10 - 1024 units per %RH, so its 102400 saturation clamp is
 * exactly 100.0 %RH. Temperature is hundredths of a degree clamped -4000..8500.
 *
 * An earlier revision of this file paired dig_H4/dig_H5 from 0xE3/0xE4 and scaled
 * humidity by 1000. Both were wrong: the reference driver pairs H4 from the signed
 * byte 0xE4 with the low nibble of 0xE5, and H5 from the signed byte 0xE6 with the
 * high nibble of 0xE5, and the datasheet states the Q22.10 unit above. Those two
 * errors would have published humidity roughly 2.4 %RH high and put a wrong sign on
 * any negative trim, with nothing downstream able to tell.
 *
 * What this module never does: it never publishes a value it did not read. A
 * missing sensor is ABSENT, a failed transaction is a failure with the previous
 * observation left unpublished, and an implausible result is OUT_OF_RANGE
 * rather than "close enough". docs/01 forbids a fabricated reading standing in
 * for a real one, and the W05 telemetry layer keeps the same rule for a missing
 * value.
 *
 * Still unverified, and the reason the caller keeps CG_BME280_TRIM_LAYOUT_CONFIRMED
 * at 0: the decode agrees with Bosch's own driver and the golden vectors derived
 * from it, but no fitted module on THIS board has been compared against a
 * reference instrument, and the strap address on the current SCL=GPIO34 wiring has
 * never been read. See evidence/A/W02/acceptance.md section 9.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

#define CG_BME280_REG_ID        0xD0u
#define CG_BME280_REG_RESET       0xE0u
#define CG_BME280_REG_STATUS      0xF3u
#define CG_BME280_REG_CTRL_HUM    0xF2u
#define CG_BME280_REG_CTRL_MEAS   0xF4u
#define CG_BME280_REG_CONFIG      0xF5u
#define CG_BME280_REG_DATA        0xF7u   /* burst base: press, temp, hum (8 bytes) */
#define CG_BME280_DATA_LEN          8u

#define CG_BME280_CHIP_ID        0x60u   /* BME280; BMP280 answers 0x56/0x57 */
#define CG_BME280_RESET_CMD      0xB6u
#define CG_BME280_STATUS_IM_UPDATE 0x01u

/* Burst offsets from CG_BME280_REG_DATA, per the Bosch BME280 register map:
 * 0xF7..0xF9 press, 0xFA..0xFC temp, 0xFD..0xFE hum. */
#define CG_BME280_OFF_PRESS_MSB    0u   /* 0xF7 */
#define CG_BME280_OFF_TEMP_MSB     3u   /* 0xFA */
#define CG_BME280_OFF_TEMP_LSB     4u   /* 0xFB */
#define CG_BME280_OFF_TEMP_XLSB    5u   /* 0xFC */
#define CG_BME280_OFF_HUM_MSB      6u   /* 0xFD */
#define CG_BME280_OFF_HUM_LSB      7u   /* 0xFE */

/* Oversampling x1 and normal mode: the plant only needs one ambient stream at
 * the reported cadence, and x1 keeps the conversion inside the bounded timeout. */
#define CG_BME280_OSRS_H_X1        0x01u
#define CG_BME280_OSRS_T_X1        (0x01u << 5)
#define CG_BME280_OSRS_P_X1        (0x01u << 2)
#define CG_BME280_MODE_NORMAL      0x03u
#define CG_BME280_MODE_FORCED      0x01u
#define CG_BME280_STANDBY_500MS    (0x02u << 2)

#define CG_BME280_CALIB_T_BYTES    24u   /* 0x88..0x9F: T and P trim            */
#define CG_BME280_CALIB_H1_BYTES    1u   /* 0xA1: dig_H1                        */
#define CG_BME280_CALIB_H_BLOCK    7u   /* 0xE1..0xE7: dig_H2..H6, sub, ctrl    */

#define CG_BME280_MAX_CONSECUTIVE_FAILURES 3u
#define CG_BME280_BACKOFF_MS            5000u

typedef enum {
    CG_BME_PORT_OK = 0,
    CG_BME_PORT_NACK,        /* no device acknowledged the address: absence      */
    CG_BME_PORT_TIMEOUT,     /* transaction exceeded its bound                   */
    CG_BME_PORT_ERROR        /* bus error, short read, or driver fault            */
} cg_bme_port_result_t;

typedef struct {
    /* Injected transport. `ctx` is opaque: the real port is the I2C device
     * handle, the harness uses a scripted fixture. */
    void *ctx;
    cg_bme_port_result_t (*read)(void *ctx, uint8_t reg, uint8_t *out, size_t len);
    cg_bme_port_result_t (*write)(void *ctx, uint8_t reg, uint8_t value);
    uint64_t (*now_ms)(void *ctx);
    void (*settle_ms)(void *ctx, uint32_t ms);
} cg_bme280_port_t;

typedef struct {
    uint16_t dig_t1;
    int16_t dig_t2;
    int16_t dig_t3;
    uint8_t dig_h1;
    int16_t dig_h2;
    uint8_t dig_h3;
    int16_t dig_h4;   /* signed 0xE4 * 16 | low nibble of 0xE5                 */
    int16_t dig_h5;   /* signed 0xE6 * 16 | high nibble of 0xE5                */
    int8_t dig_h6;
    int32_t t_fine;
} cg_bme280_calib_t;

typedef enum {
    CG_BME_STATE_ABSENT = 0,   /* never answered: known configuration fact       */
    CG_BME_STATE_UNPROBED,     /* init has not run yet                            */
    CG_BME_STATE_READY,        /* identity + trim good, readings trusted          */
    CG_BME_STATE_FAULT,        /* was present, now failing transport              */
    CG_BME_STATE_IDENTITY_BAD  /* answered with a chip id that is not a BME280    */
} cg_bme280_state_t;

typedef enum {
    CG_BME_READ_OK = 0,
    CG_BME_READ_ABSENT,
    CG_BME_READ_TIMEOUT,
    CG_BME_READ_NACK,
    CG_BME_READ_IM_NOT_READY,
    CG_BME_READ_NOT_READY,
    CG_BME_READ_OUT_OF_RANGE,
    CG_BME_READ_SHORT,
    /* Set by the caller that owns board policy, not by the transport: the trim
     * bytes were decoded, but the nibble layout they were decoded with has never
     * been confirmed against a fitted module, so no number may be published. */
    CG_BME_READ_TRIM_UNCONFIRMED
} cg_bme_read_result_t;

typedef struct {
    bool valid;
    float temperature_c;
    float relative_humidity_pct;
    uint64_t obs_ms;
    uint32_t seq;
    cg_bme_read_result_t reason;
} cg_bme280_obs_t;

typedef struct {
    cg_bme280_state_t state;
    cg_bme280_calib_t calib;
    uint8_t chip_id;
    uint32_t consecutive_failures;
    uint32_t reprobe_count;
    uint64_t backoff_until_ms;
    uint32_t seq;
    bool heartbeat_running;
} cg_bme280_t;

/* One-shot fitted-device diagnostic: the raw calibration bytes and one raw
 * measurement context, so a host can decode the SAME bytes independently. This
 * never publishes a value and never touches the trim gate. */
typedef struct {
    uint8_t chip_id;
    uint8_t tp[CG_BME280_CALIB_T_BYTES];
    uint8_t h1;
    uint8_t hb[CG_BME280_CALIB_H_BLOCK];
    cg_bme280_calib_t calib;
    uint8_t data[CG_BME280_DATA_LEN];
    uint32_t adc_t;
    uint32_t adc_h;
    int32_t temp_dc;
    uint32_t hum_q2210;
    cg_bme_read_result_t result;
} cg_bme280_diag_t;

cg_bme_read_result_t cg_bme280_collect_diag(const cg_bme280_port_t *port,
                                            cg_bme280_t *s, cg_bme280_diag_t *d);

/* ---- pure logic, executed by the host harness ---- */
void cg_bme280_reset(cg_bme280_t *s);

/* Bosch trim layout is little-endian with two packed humidity fields. */
void cg_bme280_parse_calib(const uint8_t tp[CG_BME280_CALIB_T_BYTES],
                           uint8_t h1,
                           const uint8_t hb[CG_BME280_CALIB_H_BLOCK],
                           cg_bme280_calib_t *c);

bool cg_bme280_identity_is_bme280(uint8_t id);

/* Datasheet fixed-point compensation. Temperature returns hundredths of a
 * degree with the datasheet's -4000..8500 clamp; humidity returns %RH in Q22.10
 * (divide by 1024) with its 0..102400 clamp, where 102400 is exactly 100.0 %RH. */
/* `c` is not const: the datasheet algorithm publishes t_fine into it. */
int32_t cg_bme280_compensate_temperature(cg_bme280_calib_t *c, uint32_t adc_t);
uint32_t cg_bme280_compensate_humidity(cg_bme280_calib_t *c, uint32_t adc_h);

/* 20-bit left-justified assembly, matching the datasheet's 20.8-bit fields. */
uint32_t cg_bme280_unpack_temperature_raw(const uint8_t data[CG_BME280_DATA_LEN]);
uint32_t cg_bme280_unpack_humidity_raw(const uint8_t data[CG_BME280_DATA_LEN]);

/* Physical plausibility, applied before a value is allowed to be published. */
bool cg_bme280_reading_in_range(int32_t temp_dc, uint32_t hum_q2210);

/* Probe identity + NVM calibration load. Classifies absence from a real NACK so
 * "wired but silent" and "not fitted" stay distinguishable. */
cg_bme_read_result_t cg_bme280_probe(const cg_bme280_port_t *port, cg_bme280_t *s);

/* One bounded acquisition. Never advances `seq` or reports valid on failure. */
cg_bme_read_result_t cg_bme280_sample(const cg_bme280_port_t *port, cg_bme280_t *s,
                                      cg_bme280_obs_t *out);

/* Fail-closed trim gate with a diagnostic escape hatch.
 *
 * Published telemetry must never carry unvalidated compensated values, but the
 * trim layout can only be confirmed by comparing those very values against a
 * reference instrument once. When the gate drops an otherwise valid observation
 * it formats the discarded numbers into `diag` (left empty when nothing was
 * dropped) so the caller can log them under an explicit UNVALIDATED token
 * without touching any published field. With CG_BME280_TRIM_LAYOUT_CONFIRMED=1
 * the gate compiles to a no-op. */
void cg_bme280_trim_gate(cg_bme280_obs_t *obs, cg_bme_read_result_t *reason,
                         char *diag, size_t diag_size);

/* Presence is the producer's belief that a module is on the bus. It is NOT the
 * heartbeat gate: the task that owns this state beats every completed cycle,
 * including one that concluded the module is absent, so a quiet sensor can never
 * be mistaken for a crashed producer. */
bool cg_bme280_is_present(const cg_bme280_t *s);
const char *cg_bme280_read_result_name(cg_bme_read_result_t r);
const char *cg_bme280_state_name(cg_bme280_state_t state);
