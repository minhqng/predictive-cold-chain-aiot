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
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "cg_bme280.h"

#define SCEN_OK 0
#define SCEN_NACK 1
#define SCEN_BMP280 2
#define SCEN_IM_STUCK 3
#define SCEN_TIMEOUT 4
#define SCEN_GARBAGE 5
#define SCEN_HUM_ZERO 6

static int failures;
static uint8_t tp[CG_BME280_CALIB_T_BYTES];
static uint8_t hb[CG_BME280_CALIB_H_BLOCK];
static uint8_t h1;
static uint8_t data[CG_BME280_DATA_LEN];
static int scenario;
static int status_reads;
static int write_count;
static int mode_configured;   /* CTRL_MEAS(normal) has been written */
static int data_before_mode;  /* data burst read before mode configured  */
static int settle_after_mode; /* conversion settle observed after mode   */

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
        if (!mode_configured) {
            data_before_mode++;
            return CG_BME_PORT_ERROR;
        }
        memcpy(out, data, sizeof(data));
        if (scenario == SCEN_GARBAGE) {
            /* saturating raw codes: the only defensible reading is "not physical" */
            memset(out, 0xFF, len);
        }
        if (scenario == SCEN_HUM_ZERO) {
            /* A stuck-low humidity line reads 0, which compensates to 0.0 %RH
             * and passes every range check: it must be refused as a raw code. */
            out[CG_BME280_OFF_HUM_MSB] = 0u;
            out[CG_BME280_OFF_HUM_LSB] = 0u;
        }
    } else {
        return CG_BME_PORT_ERROR;
    }
    return CG_BME_PORT_OK;
}

static cg_bme_port_result_t fake_write(void *ctx, uint8_t reg, uint8_t value)
{
    (void)ctx; (void)value;
    if (reg == CG_BME280_REG_CTRL_MEAS) {
        mode_configured = 1;
    }
    write_count++;
    return CG_BME_PORT_OK;
}

static uint64_t clock_ms;
static uint64_t fake_now(void *ctx) { (void)ctx; return clock_ms; }
static void fake_settle(void *ctx, uint32_t ms)
{
    (void)ctx;
    clock_ms += ms;
    if (mode_configured) {
        settle_after_mode++;
    }
}

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
    hb[0] = (uint8_t)0x3B; hb[1] = 0x00;      /* dig_H2 = 59                    */
    hb[2] = (uint8_t)0xF2;                     /* dig_H3 = 242 (unsigned)        */
    hb[3] = (uint8_t)0x39;                     /* dig_H4 high byte (signed *16)  */
    hb[4] = (uint8_t)0x12;                     /* dig_H4 low nibble / H5 high    */
    hb[5] = 0x00;                              /* dig_H5 high byte (signed *16)  */
    hb[6] = (uint8_t)0xFA;                     /* dig_H6 = -6 (signed)           */
    memset(data, 0, sizeof(data));
    data[3] = (uint8_t)0x4E; data[4] = (uint8_t)0x63; data[5] = (uint8_t)0x60;   /* temp raw 0xFA..0xFC */
    data[6] = (uint8_t)0x5D; data[7] = (uint8_t)0xB0;                   /* hum raw 0xFD..0xFE */
}

/* Golden vectors for the trim decode and both compensation paths.
 *
 * The expected numbers come from a separate Python transcription of the same
 * published formulas (bosch_oracle), not from this C file, so agreement is a
 * cross-check between two independent implementations rather than a tautology.
 * The nibble pairing itself is the one quoted from BoschSensortec/BME280_driver:
 *   dig_h4 = (int16_t)(int8_t)reg_data[3] * 16 | (reg_data[4] & 0x0F)
 *   dig_h5 = (int16_t)(int8_t)reg_data[5] * 16 | (reg_data[4] >> 4)
 * with reg_data read as 7 bytes from 0xE1. Humidity is Q22.10: 1024 units per
 * %RH, saturation clamp 102400 == exactly 100.0 %RH.
 *
 * These were mutation-checked: decoding H4/H5 the way an earlier revision of this
 * driver did turns 86196 into the 102400 saturation value, and scaling humidity by
 * 1000 instead of 1024 moves 84.18 %RH to 86.20. So the assertions can actually
 * fail for the mistakes they exist to catch. None of this is silicon evidence -
 * it says the arithmetic follows the specification, not that a fitted module
 * behaves that way on this board. */
/* Loads the golden trim and raw codes into the scripted fixture. Unlike
 * load_scratch() this frame has a non-zero humidity, which is what makes the
 * unit-conversion assertions below able to fail on a wrong divisor. */
static void load_golden(void)
{
    static const uint8_t g_tp[CG_BME280_CALIB_T_BYTES] = {
        0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    };
    static const uint8_t g_hb[CG_BME280_CALIB_H_BLOCK] = {
        0x41, 0x01, 0x0E, 0x00, 0xC8, 0x0C, 0x9C
    };
    uint32_t adc_t = 518500u, adc_h = 20000u;

    memcpy(tp, g_tp, sizeof(tp));
    memcpy(hb, g_hb, sizeof(hb));
    h1 = 0x64u;
    memset(data, 0, sizeof(data));
    data[CG_BME280_OFF_TEMP_MSB] = (uint8_t)((adc_t >> 12) & 0xFFu);
    data[CG_BME280_OFF_TEMP_LSB] = (uint8_t)((adc_t >> 4) & 0xFFu);
    data[CG_BME280_OFF_TEMP_XLSB] = (uint8_t)((adc_t & 0x0Fu) << 4);
    data[CG_BME280_OFF_HUM_MSB] = (uint8_t)((adc_h >> 8) & 0xFFu);
    data[CG_BME280_OFF_HUM_LSB] = (uint8_t)(adc_h & 0xFFu);
}

static void check_golden_vectors(void)
{
    static const uint8_t g_tp[CG_BME280_CALIB_T_BYTES] = {
        0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    };
    /* 0xE1..0xE7: h2=321, h3=14, h4=8, h5=204, h6=-100 */
    static const uint8_t g_hb[CG_BME280_CALIB_H_BLOCK] = {
        0x41, 0x01, 0x0E, 0x00, 0xC8, 0x0C, 0x9C
    };
    /* Same shape with both shared-nibble fields negative: 0xE4=0xFC, 0xE5=0x27,
     * 0xE6=0xF8 -> dig_H4 = -4*16|7 = -57, dig_H5 = -8*16|2 = -126. */
    static const uint8_t g_hbn[CG_BME280_CALIB_H_BLOCK] = {
        0x41, 0x01, 0x0E, 0xFC, 0x27, 0xF8, 0x64
    };
    cg_bme280_calib_t c;
    int32_t temp_dc;
    uint32_t hum_q;

    cg_bme280_parse_calib(g_tp, 0x64u, g_hb, &c);
    check(c.dig_t1 == 27504u, "golden: dig_T1");
    check(c.dig_t2 == 26435, "golden: dig_T2");
    check(c.dig_t3 == -1000, "golden: dig_T3");
    check(c.dig_h1 == 100u, "golden: dig_H1 unsigned at 0xA1");
    check(c.dig_h2 == 321, "golden: dig_H2 signed at 0xE1:0xE2");
    check(c.dig_h3 == 14u, "golden: dig_H3 unsigned at 0xE3");
    check(c.dig_h4 == 8, "golden: dig_H4 = 0xE4 signed *16 | low nibble 0xE5");
    check(c.dig_h5 == 204, "golden: dig_H5 = 0xE6 signed *16 | high nibble 0xE5");
    check(c.dig_h6 == -100, "golden: dig_H6 signed at 0xE7");

    temp_dc = cg_bme280_compensate_temperature(&c, 518500u);
    check(temp_dc == 2465, "golden: temperature 24.65 dC from adc_T 518500");
    /* Humidity consumes t_fine published by the call above: temperature first is
     * a requirement of the algorithm, not a stylistic ordering. */
    hum_q = cg_bme280_compensate_humidity(&c, 20000u);
    check(hum_q == 86196u, "golden: humidity Q22.10 from adc_H 20000");
    check(c.t_fine == 126189, "golden: t_fine carried into humidity");

    cg_bme280_parse_calib(g_tp, 0x01u, g_hbn, &c);
    check(c.dig_h4 == -57, "golden: dig_H4 sign from 0xE4=0xFC");
    check(c.dig_h5 == -126, "golden: dig_H5 sign from 0xE6=0xF8");
    check(c.dig_h6 == 100, "golden: dig_H6 positive at 0xE7");

    /* Q22.10 identity, asserted rather than assumed: the datasheet's saturation
     * bound is exactly 100 %RH only under a 1024 scale, which is the scale this
     * driver publishes with. Under the /1000 an earlier revision used, the same
     * bound would have read 102.40 %RH. */
    check(102400u / 1024u == 100u, "golden: humidity saturation is 100.0 %RH");
}

/* A case whose expected numbers can be finished on paper, so the assertion does
 * not rest on running any program first.
 *
 * dig_T1 = 0, dig_T2 = 3200, dig_T3 = 0, adc_T = 524288:
 *   adc_T/8   = 65536;  (65536 - 2*0) * 3200 / 2048 = 102400  -> var1
 *   var2 = 0 because dig_T3 is 0
 *   t_fine = 102400;  T = (102400*5 + 128)/256 = 512128/256 = 2000 = 20.00 C
 *
 * dig_H1 = 100, H2 = 1, H3 = 2, H4 = 0, H5 = 0, H6 = 0, adc_H = 21429:
 *   var1 = 102400 - 76800 = 25600
 *   var5 = (21429*16384 - 0 - 0 + 16384)/32768 = 10715
 *   var2 = 25600*0/1024 = 0;  var3 = 25600*2/2048 = 25
 *   var4 = (0*(25+32768))/1024 + 2097152 = 2097152
 *   var2 = (2097152*1 + 8192)/16384 = 128
 *   var3 = 10715*128 = 1371520
 *   var4 = ((1371520/32768) * (1371520/32768))/128 = (41*41)/128 = 13
 *   var5 = 1371520 - (13*100)/16 = 1371520 - 81 = 1371439
 *   humidity = 1371439/4096 = 334  -> 334/1024 = 0.33 %RH
 *
 * Under the /1000 scale this driver used to have, the same raw code would publish
 * 0.334 as if it were 0.33 %RH, and at the ceiling it would call 102400 "102.4".
 */
static void check_hand_derived_vector(void)
{
    static const uint8_t h_tp[CG_BME280_CALIB_T_BYTES] = {
        0x00, 0x00, 0x80, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    };
    static const uint8_t h_hb[CG_BME280_CALIB_H_BLOCK] = {
        0x01, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00
    };
    cg_bme280_calib_t c;
    int32_t temp_dc;
    uint32_t hum_q;

    cg_bme280_parse_calib(h_tp, 100u, h_hb, &c);
    check(c.dig_t2 == 3200, "hand: dig_T2 from 0x0C80 little-endian");
    check(c.dig_h2 == 1, "hand: dig_H2");
    check(c.dig_h3 == 2u, "hand: dig_H3 unsigned");
    check(c.dig_h4 == 0, "hand: dig_H4 zero pairing");
    check(c.dig_h5 == 0, "hand: dig_H5 zero pairing");

    temp_dc = cg_bme280_compensate_temperature(&c, 524288u);
    check(temp_dc == 2000, "hand: 20.00 C");
    check(c.t_fine == 102400, "hand: t_fine 102400");
    hum_q = cg_bme280_compensate_humidity(&c, 21429u);
    check(hum_q == 334u, "hand: humidity 334 Q22.10");
}

/* Reproduces the burst register mapping: a read from 0xF7 lays out press(0..2),
 * temp(3..5), hum(6..7). If the temp/hum offsets are swapped, the unpackers read
 * the wrong bytes and this fails even though the compensation arithmetic is right. */
static void check_burst_offsets(void)
{
    uint8_t d[CG_BME280_DATA_LEN];
    uint32_t adc_t = 518500u, adc_h = 20000u;
    memset(d, 0, sizeof(d));
    d[3] = (uint8_t)((adc_t >> 12) & 0xFFu);
    d[4] = (uint8_t)((adc_t >> 4) & 0xFFu);
    d[5] = (uint8_t)((adc_t & 0x0Fu) << 4);
    d[6] = (uint8_t)((adc_h >> 8) & 0xFFu);
    d[7] = (uint8_t)(adc_h & 0xFFu);
    check(cg_bme280_unpack_temperature_raw(d) == adc_t, "burst: temp at 0xFA..0xFC");
    check(cg_bme280_unpack_humidity_raw(d) == adc_h, "burst: hum at 0xFD..0xFE");
}

/* One-shot diagnostic must collect the SAME bytes the producer uses, at the
 * datasheet addresses, and surface a failed read instead of a partial dump. */
static void check_diag(void)
{
    cg_bme280_port_t port;
    cg_bme280_t s;
    cg_bme280_diag_t d;
    port.ctx = NULL;
    port.read = fake_read;
    port.write = fake_write;
    port.now_ms = fake_now;
    port.settle_ms = fake_settle;
    load_scratch();
    scenario = SCEN_OK;
    status_reads = 0;
    write_count = 0;
    mode_configured = 0;
    data_before_mode = 0;
    cg_bme280_reset(&s);
    check(cg_bme280_collect_diag(&port, &s, &d) == CG_BME_READ_OK, "diag: collect ok");
    check(write_count == 3, "diag: configures ctrl_hum/ctrl_meas/config before reading");
    check(mode_configured == 1 && data_before_mode == 0,
          "diag: data burst read only AFTER mode is configured");
    check(d.chip_id == CG_BME280_CHIP_ID, "diag: chip id 0x60 at 0xD0");
    check(d.calib.dig_t1 == 27504u && d.calib.dig_t2 == 494 && d.calib.dig_t3 == 0,
          "diag: dig_T parsed from 0x88..");
    check(d.calib.dig_h1 == 0x21u, "diag: dig_H1 from 0xA1");
    check(d.adc_t == 0x4E636u, "diag: adc_t from 0xFA..0xFC");
    check(d.adc_h == 0x5DB0u, "diag: adc_h from 0xFD..0xFE");
    scenario = SCEN_TIMEOUT;
    cg_bme280_reset(&s);
    check(cg_bme280_collect_diag(&port, &s, &d) == CG_BME_READ_TIMEOUT,
          "diag: data-read timeout surfaced, not a partial dump");
}

/* The published floats must be the compensated integers converted with the
 * datasheet's units: hundredths of a degree and Q22.10 humidity. Comparing
 * against the same integers pins the conversion, which a wrong divisor (e.g.
 * /1000 humidity) would otherwise leave untested. */
static void check_published_units(void)
{
    cg_bme280_port_t port;
    cg_bme280_t s;
    cg_bme280_obs_t obs;
    int32_t t_dc;
    uint32_t h_q;

    port.ctx = NULL;
    port.read = fake_read;
    port.write = fake_write;
    port.now_ms = fake_now;
    port.settle_ms = fake_settle;
    load_golden();
    scenario = SCEN_OK;
    status_reads = 0;
    cg_bme280_reset(&s);
    check(cg_bme280_probe(&port, &s) == CG_BME_READ_OK, "units: probe");
    check(cg_bme280_sample(&port, &s, &obs) == CG_BME_READ_OK, "units: sample");
    t_dc = cg_bme280_compensate_temperature(&s.calib, cg_bme280_unpack_temperature_raw(data));
    h_q = cg_bme280_compensate_humidity(&s.calib, cg_bme280_unpack_humidity_raw(data));
    /* A zero humidity would make the comparison below pass under any divisor. */
    check(h_q > 0u, "units: scripted frame has a non-zero humidity");
    check(obs.valid, "units: reading published");
    check(fabsf(obs.temperature_c - (float)t_dc / 100.0f) < 0.001f,
          "units: centi-degree to C");
    check(fabsf(obs.relative_humidity_pct - (float)h_q / 1024.0f) < 0.001f,
          "units: Q22.10 to %RH");
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
    check_golden_vectors();
    check_hand_derived_vector();
    check_burst_offsets();
    check_diag();
    check_published_units();

    /* 1. nominal probe: identity, NVM wait, trim, control writes */
    scenario = SCEN_OK;
    load_scratch();
    cg_bme280_reset(&s);
    status_reads = 0; write_count = 0; settle_after_mode = 0;
    mode_configured = 0; data_before_mode = 0;
    check(cg_bme280_probe(&port, &s) == CG_BME_READ_OK, "nominal probe succeeds");
    /* A reset or sleeping module holds 0x80000/0x8000 in its data registers,
     * which decode to a plausible reading. The probe must give the first
     * conversion time to land before the caller reads that burst. */
    check(settle_after_mode >= 1, "probe waits one conversion after configuring mode");
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

    /* 6b. a zero humidity raw code is as impossible as 0xFFFF and must be
     * refused before compensation turns it into a plausible 0.0 %RH. */
    scenario = SCEN_HUM_ZERO;
    cg_bme280_reset(&s);
    status_reads = 0;
    check(cg_bme280_probe(&port, &s) == CG_BME_READ_OK, "probe ok for zero-humidity case");
    before = s.seq;
    clock_ms = 3500;
    check(cg_bme280_sample(&port, &s, &obs) == CG_BME_READ_OUT_OF_RANGE,
          "zero humidity raw code refused");
    check(!obs.valid, "zero humidity not published");
    check(s.seq == before, "zero humidity does not consume a sequence number");

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
    check(cg_bme280_is_present(&s), "fitted module remains present during re-probe backoff");
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
    /* Temperature dependence must be shown with trims that leave the humidity
     * path out of saturation at both ends. With the scratch fixture's dig_H4 = 914
     * the algorithm clamps to 0 for every t_fine, so comparing two t_fine values
     * there would have compared 0 with 0 and proved nothing either way. */
    cg_bme280_calib_t dep;
    memset(&dep, 0, sizeof(dep));
    dep.dig_h1 = 100u; dep.dig_h2 = 321; dep.dig_h3 = 14u;
    dep.dig_h4 = 8; dep.dig_h5 = 204; dep.dig_h6 = -100;
    dep.t_fine = 126189;
    uint32_t h_warm = cg_bme280_compensate_humidity(&dep, 20000u);
    dep.t_fine = 0;
    uint32_t h_cold = cg_bme280_compensate_humidity(&dep, 20000u);
    check(h_warm == 86196u, "golden: humidity at its own t_fine");
    check(h_cold == 102400u, "golden: humidity rises as t_fine falls");
    check(h_cold != h_warm, "humidity consumes t_fine (not an independent guess)");

    /* 9. range gate and names */
    check(cg_bme280_reading_in_range(2500, 50000u), "normal reading accepted");
    check(!cg_bme280_reading_in_range(-4001, 50000u), "below-range rejected");
    check(!cg_bme280_reading_in_range(2500, 102401u), "over-range rejected");
    check(strcmp(cg_bme280_read_result_name(CG_BME_READ_ABSENT), "ABSENT") == 0, "absent named");
    check(strcmp(cg_bme280_read_result_name(CG_BME_READ_OUT_OF_RANGE), "OUT_OF_RANGE") == 0,
          "out-of-range named");

    /* 10. the trim gate drops the value but preserves it for the reference
     * comparison: published fields stay invalid while the diagnostic carries the
     * discarded compensated numbers, so the trim layout can be confirmed once
     * against a reference instrument without ever publishing unvalidated data. */
    {
        cg_bme280_obs_t gated = { .valid = true, .temperature_c = 24.37f,
                                  .relative_humidity_pct = 51.28f, .obs_ms = 0, .seq = 7 };
        cg_bme_read_result_t reason = CG_BME_READ_OK;
        char diag[64];
        cg_bme280_trim_gate(&gated, &reason, diag, sizeof(diag));
#if CG_BME280_TRIM_LAYOUT_CONFIRMED
        check(gated.valid, "confirmed build publishes the compensated value");
        check(diag[0] == '\0', "confirmed build emits no diagnostic");
#else
        check(!gated.valid, "unconfirmed build never publishes the value");
        check(reason == CG_BME_READ_TRIM_UNCONFIRMED, "reason names the trim gate");
        check(strstr(diag, "unvalidated_t_c=24.37") != NULL, "diagnostic keeps temperature");
        check(strstr(diag, "unvalidated_rh_pct=51.28") != NULL, "diagnostic keeps humidity");
        printf("TRIM_GATE diag=[%s] valid=%d reason=%s\n", diag, (int)gated.valid,
               cg_bme280_read_result_name(reason));
#endif
        cg_bme280_obs_t empty = { .valid = false, .temperature_c = 0.0f,
                                  .relative_humidity_pct = 0.0f, .obs_ms = 0, .seq = 0 };
        reason = CG_BME_READ_ABSENT;
        cg_bme280_trim_gate(&empty, &reason, diag, sizeof(diag));
        check(diag[0] == '\0', "an already-invalid observation yields no diagnostic");
        check(reason == CG_BME_READ_ABSENT, "the gate does not relabel other refusals");
        cg_bme280_trim_gate(&gated, &reason, NULL, 0);
        check(1, "null diagnostic buffer is tolerated");
    }

    if (failures == 0) {
        printf("BME280 PRODUCER HARNESS: ALL SCENARIOS PASS\n");
        return 0;
    }
    printf("BME280 PRODUCER HARNESS: %d FAILURE(S)\n", failures);
    return 1;
}
