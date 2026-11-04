/*
 * Host harness for the BME280 producer: compiles the real, unchanged
 * cg_bme280.c against a scripted I2C port. It proves the decision logic
 * (identity, absence, NVM readiness, plausibility refusal, failure backoff and
 * recovery) and the compensation function's properties, without a board.
 *
 * It deliberately does not assert invented "expected" temperatures: no value
 * here is presented as hardware verification. The physical readback stays an
 * operator evidence item.
 */
#include <stdio.h>
#include <string.h>

#include "cg_bme280.h"

#define SCEN_OK 0
#define SCEN_NACK 1
#define SCEN_BMP280 2
#define SCEN_IM_STUCK 3
#define SCEN_TIMEOUT 4
#define SCEN_GARBAGE 5

static int failures;
static uint8_t tp[CG_BME280_CALIB_T_BYTES];
static uint8_t hb[CG_BME280_CALIB_H_BLOCK];
static uint8_t h1;
static uint8_t data[CG_BME280_DATA_LEN];
static int scenario;
static int status_reads;
static int write_count;

static void check(int cond, const char *what)
{
    if (!cond) {
        printf("FAIL %s\n", what);
        failures++;
    }
}

static cg_bme_port_result_t fake_read(void *ctx, uint8_t reg, uint8_t *out, size_t len)
{
    (void)ctx;
    if (scenario == SCEN_NACK || scenario == SCEN_BMP280) {
        if (reg == CG_BME280_REG_ID && scenario == SCEN_NACK) return CG_BME_PORT_NACK;
    }
    if (scenario == SCEN_TIMEOUT && reg == CG_BME280_REG_DATA) return CG_BME_PORT_TIMEOUT;
    memset(out, 0, len);
    if (reg == CG_BME280_REG_ID) {
        out[0] = (scenario == SCEN_BMP280) ? 0x57u : CG_BME280_CHIP_ID;
    } else if (reg == CG_BME280_REG_STATUS) {
        if (scenario == SCEN_IM_STUCK) {
            out[0] = CG_BME280_STATUS_IM_UPDATE;
        } else {
            out[0] = (status_reads++ < 1) ? CG_BME280_STATUS_IM_UPDATE : 0u;
        }
    } else if (reg == 0x88u && len == sizeof(tp)) {
        memcpy(out, tp, sizeof(tp));
    } else if (reg == 0xA1u && len == 1u) {
        out[0] = h1;
    } else if (reg == 0xE1u && len == sizeof(hb)) {
        memcpy(out, hb, sizeof(hb));
    } else if (reg == CG_BME280_REG_DATA && len == sizeof(data)) {
        memcpy(out, data, sizeof(data));
        if (scenario == SCEN_GARBAGE) {
            /* saturating raw codes: the only defensible reading is "not physical" */
            memset(out, 0xFF, len);
        }
    } else {
        return CG_BME_PORT_ERROR;
    }
    return CG_BME_PORT_OK;
}

static cg_bme_port_result_t fake_write(void *ctx, uint8_t reg, uint8_t value)
{
    (void)ctx; (void)reg; (void)value;
    write_count++;
    return CG_BME_PORT_OK;
}

static uint64_t clock_ms;
static uint64_t fake_now(void *ctx) { (void)ctx; return clock_ms; }
static void fake_settle(void *ctx, uint32_t ms) { (void)ctx; clock_ms += ms; }

static void load_scratch(void)
{
    /* Arbitrary but fixed trim: dig_T1=27504, T2=494, T3=0 as in a typical part. */
    memset(tp, 0, sizeof(tp));
    tp[0] = (uint8_t)(27504 & 0xFF); tp[1] = (uint8_t)(27504 >> 8);
    /* dig_T2 is a little-endian int16: 494 -> 0xEE,0x01 */
    tp[2] = (uint8_t)(494 & 0xFF); tp[3] = (uint8_t)(494 >> 8);
    tp[4] = 0; tp[5] = 0;
    h1 = (uint8_t)0x21;
    memset(hb, 0, sizeof(hb));
    hb[0] = (uint8_t)0x3B; hb[1] = 0x00;      /* dig_H2 */
    hb[2] = (uint8_t)0xF2;                     /* dig_H3 + H4 high nibble */
    hb[3] = (uint8_t)0x39;                     /* H4 low nibble | H5 high nibble */
    hb[4] = (uint8_t)0x12;                     /* dig_H5 */
    hb[6] = (uint8_t)0xFA;                      /* dig_H6 */
    memset(data, 0, sizeof(data));
    data[5] = (uint8_t)0x4E; data[6] = (uint8_t)0x63; data[7] = (uint8_t)0x60;   /* temp raw */
    data[3] = (uint8_t)0x5D; data[4] = (uint8_t)0xB0;                   /* hum raw    */
}

int main(void)
{
    cg_bme280_port_t port;
    cg_bme280_t s;
    cg_bme280_obs_t obs;
    cg_bme280_calib_t c;
    int32_t t1, t2;
    uint32_t h_a, h_b;

    port.ctx = NULL;
    port.read = fake_read;
    port.write = fake_write;
    port.now_ms = fake_now;
    port.settle_ms = fake_settle;
    load_scratch();

    /* 1. nominal probe: identity, NVM wait, trim, control writes */
    scenario = SCEN_OK;
    cg_bme280_reset(&s);
    status_reads = 0; write_count = 0;
    check(cg_bme280_probe(&port, &s) == CG_BME_READ_OK, "nominal probe succeeds");
    check(s.state == CG_BME_STATE_READY, "ready after probe");
    check(write_count == 3, "ctrl_hum, ctrl_meas, config all written");
    check(cg_bme280_is_present(&s), "present after successful probe");

    /* 2. sampling publishes exactly once per reading */
    clock_ms = 1000;
    check(cg_bme280_sample(&port, &s, &obs) == CG_BME_READ_OK, "sample ok");
    check(obs.valid, "sample valid");
    check(obs.seq == 1u, "sequence advanced once");
    uint32_t first_seq = s.seq;
    check(cg_bme280_sample(&port, &s, &obs) == CG_BME_READ_OK, "second sample ok");
    check(obs.seq == first_seq + 1u, "sequence strictly increases");

    /* 3. absence is a known state, never a fault, and never a value */
    scenario = SCEN_NACK;
    cg_bme280_reset(&s);
    check(cg_bme280_probe(&port, &s) == CG_BME_READ_ABSENT, "NACK classifies absent");
    check(s.state == CG_BME_STATE_ABSENT, "state absent");
    check(!cg_bme280_is_present(&s), "absent is not present");
    /* Presence and liveness are different questions. The producer task keeps
     * completing cycles against a quiet module, so absence must stay a stable,
     * repeatedly reportable finding rather than decaying into FAULT - a fault is
     * what would let a silent sensor be read as a crashed producer. */
    check(cg_bme280_state_name(s.state) != NULL, "absence is nameable for the log line");
    clock_ms = 2000;
    check(cg_bme280_sample(&port, &s, &obs) == CG_BME_READ_ABSENT, "sample while absent refuses");
    check(!obs.valid && obs.seq == 0u, "absent publishes nothing");

    /* 4. a BMP280 must be refused, not silently used as a BME280 */
    scenario = SCEN_BMP280;
    cg_bme280_reset(&s);
    check(cg_bme280_probe(&port, &s) != CG_BME_READ_OK, "BMP280 id refused");
    check(s.state == CG_BME_STATE_IDENTITY_BAD, "identity-bad state recorded");
    check(s.chip_id == 0x57u, "answered id retained for evidence");

    /* 5. stuck IM_UPDATE must not yield calibration-backed readings */
    scenario = SCEN_IM_STUCK;
    cg_bme280_reset(&s);
    check(cg_bme280_probe(&port, &s) == CG_BME_READ_IM_NOT_READY, "im-update refusal");
    check(s.state == CG_BME_STATE_FAULT, "fault on stuck im-update");

    /* 6. out-of-range raw codes must be refused and must not advance sequence */
    scenario = SCEN_GARBAGE;
    cg_bme280_reset(&s);
    status_reads = 0;
    check(cg_bme280_probe(&port, &s) == CG_BME_READ_OK, "probe ok for garbage case");
    uint32_t before = s.seq;
    clock_ms = 3000;
    check(cg_bme280_sample(&port, &s, &obs) == CG_BME_READ_OUT_OF_RANGE, "garbage refused");
    check(!obs.valid, "garbage not published");
    check(s.seq == before, "refused sample does not consume a sequence number");

    /* 7. transport timeout must not publish and must eventually re-probe */
    scenario = SCEN_TIMEOUT;
    cg_bme280_reset(&s);
    status_reads = 0;
    check(cg_bme280_probe(&port, &s) == CG_BME_READ_OK, "probe ok before timeouts");
    for (int i = 0; i < (int)CG_BME280_MAX_CONSECUTIVE_FAILURES; i++) {
        clock_ms += 1000;
        check(cg_bme280_sample(&port, &s, &obs) != CG_BME_READ_OK, "timeout never ok");
        check(!obs.valid, "timeout never publishes");
    }
    check(s.state == CG_BME_STATE_UNPROBED, "backoff forces re-probe after max failures");
    clock_ms += CG_BME280_BACKOFF_MS + 1u;
    scenario = SCEN_OK;
    status_reads = 0;
    clock_ms += 1000;
    check(cg_bme280_sample(&port, &s, &obs) == CG_BME_READ_OK, "recovers after backoff");
    check(obs.valid, "recovered reading valid");

    /* 8. compensation properties: deterministic, monotone, clamped, coupled */
    cg_bme280_parse_calib(tp, h1, hb, &c);
    t1 = cg_bme280_compensate_temperature(&c, 0x4E636u);
    t2 = cg_bme280_compensate_temperature(&c, 0x4E637u);
    check(t1 == cg_bme280_compensate_temperature(&c, 0x4E636u), "temperature deterministic");
    check(t2 >= t1, "temperature monotone in raw code");
    check(t1 >= -4000 && t1 <= 8500, "temperature in datasheet range");
    check(cg_bme280_compensate_temperature(&c, 0u) >= -4000, "cold clamp honoured");
    check(cg_bme280_compensate_temperature(&c, 0xFFFFFu) <= 8500, "hot clamp honoured");
    h_a = cg_bme280_compensate_humidity(&c, 0x5DB0u);
    h_b = cg_bme280_compensate_humidity(&c, 0x5DB1u);
    check(h_b >= h_a, "humidity monotone in raw code");
    check(h_a <= 102400u, "humidity clamped to datasheet maximum");
    c.t_fine = 0;
    uint32_t h_cold = cg_bme280_compensate_humidity(&c, 0x5DB0u);
    c.t_fine = 1000000;
    uint32_t h_hot = cg_bme280_compensate_humidity(&c, 0x5DB0u);
    check(h_cold != h_hot, "humidity consumes t_fine (not an independent guess)");

    /* 9. range gate and names */
    check(cg_bme280_reading_in_range(2500, 50000u), "normal reading accepted");
    check(!cg_bme280_reading_in_range(-4001, 50000u), "below-range rejected");
    check(!cg_bme280_reading_in_range(2500, 102401u), "over-range rejected");
    check(strcmp(cg_bme280_read_result_name(CG_BME_READ_ABSENT), "ABSENT") == 0, "absent named");
    check(strcmp(cg_bme280_read_result_name(CG_BME_READ_OUT_OF_RANGE), "OUT_OF_RANGE") == 0,
          "out-of-range named");

    if (failures == 0) {
        printf("BME280 PRODUCER HARNESS: ALL SCENARIOS PASS\n");
        return 0;
    }
    printf("BME280 PRODUCER HARNESS: %d FAILURE(S)\n", failures);
    return 1;
}
