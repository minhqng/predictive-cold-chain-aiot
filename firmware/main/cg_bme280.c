/*
 * ColdGuard firmware - BME280 ambient environment producer. See cg_bme280.h for
 * the authority this implementation follows and for what it refuses to publish.
 */
#include "cg_bme280.h"

#include <stdio.h>
#include <string.h>

#define CG_BME_TEMP_MIN_DC (-4000)
#define CG_BME_TEMP_MAX_DC (8500)
/* Humidity compensation is Q22.10 per the datasheet: 1024 units per %RH, so the
* saturation clamp 102400 is exactly 100.0 %RH - not 102.4. */
#define CG_BME_HUM_MAX_Q2210 (102400u)
#define CG_BME_HUM_Q2210_PER_PCT (1024.0f)
#define CG_BME_HUM_CLAMP_V (419430400)

static cg_bme_read_result_t classify_port(cg_bme_port_result_t p);

void cg_bme280_reset(cg_bme280_t *s)
{
    if (s == NULL) {
        return;
    }
    memset(s, 0, sizeof(*s));
    s->state = CG_BME_STATE_UNPROBED;
}

void cg_bme280_parse_calib(const uint8_t tp[CG_BME280_CALIB_T_BYTES],
                           uint8_t h1,
                           const uint8_t hb[CG_BME280_CALIB_H_BLOCK],
                           cg_bme280_calib_t *c)
{
    if (tp == NULL || hb == NULL || c == NULL) {
        return;
    }
    /* 0x88 block: T1 u16, T2 i16, T3 i16, little-endian. */
    c->dig_t1 = (uint16_t)((uint16_t)tp[1] << 8 | tp[0]);
    c->dig_t2 = (int16_t)((uint16_t)tp[3] << 8 | tp[2]);
    c->dig_t3 = (int16_t)((uint16_t)tp[5] << 8 | tp[4]);

    c->dig_h1 = h1;
    /* Humidity trim block starts at 0xE1, so hb[i] is register 0xE1 + i.
     * The H4/H5 pairing is transcribed from BoschSensortec/BME280_driver/bme280.c:
     *   dig_h4_msb = (int16_t)(int8_t)reg_data[3] * 16;
     *   dig_h4_lsb = (int16_t)(reg_data[4] & 0x0F);
     *   dig_h5_msb = (int16_t)(int8_t)reg_data[5] * 16;
     *   dig_h5_lsb = (int16_t)(reg_data[4] >> 4);
     * so dig_H4 is the signed byte 0xE4 shifted left 4 with the LOW nibble of
     * 0xE5, and dig_H5 is the signed byte 0xE6 shifted left 4 with the HIGH nibble
     * of 0xE5. Multiplying the signed byte by 16 and OR-ing the nibble in is what
     * carries the sign: the two's-complement bits above bit 11 survive the OR, so
     * no separate sign-extension step is needed and none is attempted here. */
    c->dig_h2 = (int16_t)((uint16_t)hb[1] << 8 | hb[0]);
    c->dig_h3 = hb[2];
    c->dig_h4 = (int16_t)(((int16_t)(int8_t)hb[3] * 16) | (int16_t)(hb[4] & 0x0F));
    c->dig_h5 = (int16_t)(((int16_t)(int8_t)hb[5] * 16) | (int16_t)(hb[4] >> 4));
    c->dig_h6 = (int8_t)hb[6];
}

bool cg_bme280_identity_is_bme280(uint8_t id)
{
    return id == CG_BME280_CHIP_ID;
}

int32_t cg_bme280_compensate_temperature(cg_bme280_calib_t *c, uint32_t adc_t)
{
    int32_t var1;
    int32_t var2;
    int32_t temperature;

    /* Bosch fixed-point temperature compensation (hundredths of a degree). */
    var1 = (int32_t)((adc_t / 8) - ((int32_t)c->dig_t1 * 2));
    var1 = (var1 * ((int32_t)c->dig_t2)) / 2048;
    var2 = (int32_t)((adc_t / 16) - ((int32_t)c->dig_t1));
    var2 = (((var2 * var2) / 4096) * ((int32_t)c->dig_t3)) / 16384;
    /* t_fine is an output of this function: humidity compensation consumes it. */
    c->t_fine = var1 + var2;
    temperature = (c->t_fine * 5 + 128) / 256;

    if (temperature < CG_BME_TEMP_MIN_DC) {
        temperature = CG_BME_TEMP_MIN_DC;
    } else if (temperature > CG_BME_TEMP_MAX_DC) {
        temperature = CG_BME_TEMP_MAX_DC;
    }
    return temperature;
}

uint32_t cg_bme280_compensate_humidity(cg_bme280_calib_t *c, uint32_t adc_h)
{
    int32_t var1, var2, var3, var4, var5;
    uint32_t humidity;

    var1 = c->t_fine - ((int32_t)76800);
    var2 = (int32_t)(adc_h * 16384);
    var3 = (int32_t)(((int32_t)c->dig_h4) * 1048576);
    var4 = ((int32_t)c->dig_h5) * var1;
    var5 = (((var2 - var3) - var4) + (int32_t)16384) / 32768;
    var2 = (var1 * ((int32_t)c->dig_h6)) / 1024;
    var3 = (var1 * ((int32_t)c->dig_h3)) / 2048;
    var4 = ((var2 * (var3 + (int32_t)32768)) / 1024) + (int32_t)2097152;
    var2 = ((var4 * ((int32_t)c->dig_h2)) + 8192) / 16384;
    var3 = var5 * var2;
    var4 = ((var3 / 32768) * (var3 / 32768)) / 128;
    var5 = var3 - ((var4 * ((int32_t)c->dig_h1)) / 16);
    var5 = (var5 < 0) ? 0 : var5;
    var5 = (var5 > CG_BME_HUM_CLAMP_V) ? CG_BME_HUM_CLAMP_V : var5;
    humidity = (uint32_t)(var5 / 4096);

    if (humidity > CG_BME_HUM_MAX_Q2210) {
        humidity = CG_BME_HUM_MAX_Q2210;
    }
    return humidity;
}

uint32_t cg_bme280_unpack_temperature_raw(const uint8_t data[CG_BME280_DATA_LEN])
{
    return (((uint32_t)data[CG_BME280_OFF_TEMP_MSB] << 12) |
            ((uint32_t)data[CG_BME280_OFF_TEMP_LSB] << 4) |
            ((uint32_t)data[CG_BME280_OFF_TEMP_XLSB] >> 4));
}

uint32_t cg_bme280_unpack_humidity_raw(const uint8_t data[CG_BME280_DATA_LEN])
{
    return (((uint32_t)data[CG_BME280_OFF_HUM_MSB] << 8) |
            ((uint32_t)data[CG_BME280_OFF_HUM_LSB]));
}

cg_bme_read_result_t cg_bme280_collect_diag(const cg_bme280_port_t *port,
                                            cg_bme280_t *s, cg_bme280_diag_t *d)
{
    uint8_t status = 0u;
    uint32_t attempt;
    cg_bme_port_result_t r;

    if (port == NULL || s == NULL || d == NULL || port->read == NULL ||
        port->write == NULL) {
        return CG_BME_READ_NOT_READY;
    }
    memset(d, 0, sizeof(*d));
    d->result = CG_BME_READ_NOT_READY;

    r = port->read(port->ctx, CG_BME280_REG_ID, &d->chip_id, 1u);
    if (r != CG_BME_PORT_OK) {
        d->result = classify_port(r);
        return d->result;
    }
    if (!cg_bme280_identity_is_bme280(d->chip_id)) {
        d->result = CG_BME_READ_NACK;
        return d->result;
    }
    /* Calibration NVM must be settled before these bytes mean anything. */
    for (attempt = 0u; attempt < 2u; attempt++) {
        r = port->read(port->ctx, CG_BME280_REG_STATUS, &status, 1u);
        if (r != CG_BME_PORT_OK) {
            d->result = classify_port(r);
            return d->result;
        }
        if ((status & CG_BME280_STATUS_IM_UPDATE) == 0u) {
            break;
        }
        if (port->settle_ms != NULL) {
            port->settle_ms(port->ctx, 2u);
        }
    }
    if ((status & CG_BME280_STATUS_IM_UPDATE) != 0u) {
        d->result = CG_BME_READ_IM_NOT_READY;
        return d->result;
    }
    r = port->read(port->ctx, 0x88u, d->tp, sizeof(d->tp));
    if (r != CG_BME_PORT_OK) {
        d->result = classify_port(r);
        return d->result;
    }
    r = port->read(port->ctx, 0xA1u, &d->h1, 1u);
    if (r != CG_BME_PORT_OK) {
        d->result = classify_port(r);
        return d->result;
    }
    r = port->read(port->ctx, 0xE1u, d->hb, sizeof(d->hb));
    if (r != CG_BME_PORT_OK) {
        d->result = classify_port(r);
        return d->result;
    }
    cg_bme280_parse_calib(d->tp, d->h1, d->hb, &d->calib);

    /* The data registers only hold a conversion once the sensor is measuring.
     * On a cold boot CTRL_MEAS is still sleep, so configure it exactly as the
     * producer does (ctrl_hum before ctrl_meas) and let one conversion settle;
     * otherwise the burst would be power-on defaults reported as OK. */
    r = port->write(port->ctx, CG_BME280_REG_CTRL_HUM, CG_BME280_OSRS_H_X1);
    if (r != CG_BME_PORT_OK) {
        d->result = classify_port(r);
        return d->result;
    }
    r = port->write(port->ctx, CG_BME280_REG_CTRL_MEAS,
                    (uint8_t)(CG_BME280_OSRS_T_X1 | CG_BME280_OSRS_P_X1 |
                              CG_BME280_MODE_NORMAL));
    if (r != CG_BME_PORT_OK) {
        d->result = classify_port(r);
        return d->result;
    }
    r = port->write(port->ctx, CG_BME280_REG_CONFIG, CG_BME280_STANDBY_500MS);
    if (r != CG_BME_PORT_OK) {
        d->result = classify_port(r);
        return d->result;
    }
    if (port->settle_ms != NULL) {
        port->settle_ms(port->ctx, 50u);   /* > one x1 conversion (~8-10 ms) */
    }

    r = port->read(port->ctx, CG_BME280_REG_DATA, d->data, sizeof(d->data));
    if (r != CG_BME_PORT_OK) {
        d->result = classify_port(r);
        return d->result;
    }
    d->adc_t = cg_bme280_unpack_temperature_raw(d->data);
    d->adc_h = cg_bme280_unpack_humidity_raw(d->data);
    d->temp_dc = cg_bme280_compensate_temperature(&d->calib, d->adc_t);
    d->hum_q2210 = cg_bme280_compensate_humidity(&d->calib, d->adc_h);
    d->result = CG_BME_READ_OK;
    return d->result;
}

bool cg_bme280_reading_in_range(int32_t temp_dc, uint32_t hum_q2210)
{
    /* A wrong register offset or a half-coupled bus has to fail here rather than
     * publish a plausible-looking number: the ranges are the datasheet's. */
    if (temp_dc < CG_BME_TEMP_MIN_DC || temp_dc > CG_BME_TEMP_MAX_DC) {
        return false;
    }
    if (hum_q2210 > CG_BME_HUM_MAX_Q2210) {
        return false;
    }
    return true;
}

const char *cg_bme280_read_result_name(cg_bme_read_result_t r)
{
    switch (r) {
        case CG_BME_READ_OK:             return "OK";
        case CG_BME_READ_ABSENT:         return "ABSENT";
        case CG_BME_READ_TIMEOUT:        return "TIMEOUT";
        case CG_BME_READ_NACK:           return "NACK";
        case CG_BME_READ_IM_NOT_READY:   return "IM_NOT_READY";
        case CG_BME_READ_NOT_READY:      return "NOT_READY";
        case CG_BME_READ_OUT_OF_RANGE:   return "OUT_OF_RANGE";
        case CG_BME_READ_SHORT:          return "SHORT_READ";
        case CG_BME_READ_TRIM_UNCONFIRMED: return "TRIM_UNCONFIRMED";
        default:                         return "ERROR";
    }
}

void cg_bme280_trim_gate(cg_bme280_obs_t *obs, cg_bme_read_result_t *reason,
                         char *diag, size_t diag_size)
{
    if (diag != NULL && diag_size > 0) {
        diag[0] = '\0';
    }
#if !CG_BME280_TRIM_LAYOUT_CONFIRMED
    if (obs != NULL && obs->valid) {
        if (diag != NULL && diag_size > 0) {
            snprintf(diag, diag_size,
                     "unvalidated_t_c=%.2f unvalidated_rh_pct=%.2f",
                     (double)obs->temperature_c, (double)obs->relative_humidity_pct);
        }
        obs->valid = false;
        if (reason != NULL) {
            *reason = CG_BME_READ_TRIM_UNCONFIRMED;
        }
    }
#else
    (void)obs;
    (void)reason;
#endif
}

static cg_bme_read_result_t classify_port(cg_bme_port_result_t p)
{
    switch (p) {
        case CG_BME_PORT_NACK:    return CG_BME_READ_NACK;
        case CG_BME_PORT_TIMEOUT: return CG_BME_READ_TIMEOUT;
        case CG_BME_PORT_ERROR:   return CG_BME_READ_SHORT;
        default:                  return CG_BME_READ_OK;
    }
}

cg_bme_read_result_t cg_bme280_probe(const cg_bme280_port_t *port, cg_bme280_t *s)
{
    uint8_t id = 0u;
    uint8_t tp[CG_BME280_CALIB_T_BYTES];
    uint8_t h1 = 0u;
    uint8_t hb[CG_BME280_CALIB_H_BLOCK];
    uint8_t status = 0u;
    cg_bme_port_result_t r;

    if (port == NULL || s == NULL || port->read == NULL || port->write == NULL ||
        port->now_ms == NULL) {
        return CG_BME_READ_NOT_READY;
    }

    r = port->read(port->ctx, CG_BME280_REG_ID, &id, 1u);
    if (r == CG_BME_PORT_NACK) {
        /* Silence is a known configuration fact, not a fault: the producer slot
         * stays honest and the aggregate health layer must not call it missing. */
        s->state = CG_BME_STATE_ABSENT;
        s->chip_id = 0u;
        return CG_BME_READ_ABSENT;
    }
    if (r != CG_BME_PORT_OK) {
        s->state = CG_BME_STATE_FAULT;
        return classify_port(r);
    }
    s->chip_id = id;
    if (!cg_bme280_identity_is_bme280(id)) {
        /* A BMP280 answers here. Its trim block differs and it has no humidity
         * section, so publishing its bytes as BME280 data would be a fabricated
         * reading: refuse instead. */
        s->state = CG_BME_STATE_IDENTITY_BAD;
        return CG_BME_READ_NACK;
    }

    /* Calibration comes out of NVM after reset; the IM_UPDATE flag must clear
     * before those bytes mean anything. */
    for (uint32_t attempt = 0; attempt < 2u; attempt++) {
        r = port->read(port->ctx, CG_BME280_REG_STATUS, &status, 1u);
        if (r != CG_BME_PORT_OK) {
            s->state = CG_BME_STATE_FAULT;
            return classify_port(r);
        }
        if ((status & CG_BME280_STATUS_IM_UPDATE) == 0u) {
            break;
        }
        if (port->settle_ms != NULL) {
            port->settle_ms(port->ctx, 2u);
        }
    }
    if ((status & CG_BME280_STATUS_IM_UPDATE) != 0u) {
        s->state = CG_BME_STATE_FAULT;
        return CG_BME_READ_IM_NOT_READY;
    }

    r = port->read(port->ctx, 0x88u, tp, sizeof(tp));
    if (r != CG_BME_PORT_OK) {
        s->state = CG_BME_STATE_FAULT;
        return classify_port(r);
    }
    r = port->read(port->ctx, 0xA1u, &h1, 1u);
    if (r != CG_BME_PORT_OK) {
        s->state = CG_BME_STATE_FAULT;
        return classify_port(r);
    }
    r = port->read(port->ctx, 0xE1u, hb, sizeof(hb));
    if (r != CG_BME_PORT_OK) {
        s->state = CG_BME_STATE_FAULT;
        return classify_port(r);
    }
    cg_bme280_parse_calib(tp, h1, hb, &s->calib);

    /* ctrl_hum must be written before ctrl_meas for its setting to take effect. */
    r = port->write(port->ctx, CG_BME280_REG_CTRL_HUM, CG_BME280_OSRS_H_X1);
    if (r != CG_BME_PORT_OK) {
        s->state = CG_BME_STATE_FAULT;
        return classify_port(r);
    }
    r = port->write(port->ctx, CG_BME280_REG_CTRL_MEAS,
                    (uint8_t)(CG_BME280_OSRS_T_X1 | CG_BME280_OSRS_P_X1 |
                              CG_BME280_MODE_NORMAL));
    if (r != CG_BME_PORT_OK) {
        s->state = CG_BME_STATE_FAULT;
        return classify_port(r);
    }
    r = port->write(port->ctx, CG_BME280_REG_CONFIG, CG_BME280_STANDBY_500MS);
    if (r != CG_BME_PORT_OK) {
        s->state = CG_BME_STATE_FAULT;
        return classify_port(r);
    }

    s->state = CG_BME_STATE_READY;
    /* consecutive_failures is deliberately NOT cleared here: a module that answers
     * the identity register while its data transaction keeps timing out must still
     * reach the backoff threshold. Only a published reading clears it. */
    s->backoff_until_ms = 0u;
    return CG_BME_READ_OK;
}

cg_bme_read_result_t cg_bme280_sample(const cg_bme280_port_t *port, cg_bme280_t *s,
                                      cg_bme280_obs_t *out)
{
    uint8_t data[CG_BME280_DATA_LEN];
    int32_t temp_dc;
    uint32_t hum_q2210;
    uint32_t adc_t, adc_h;
    uint64_t now;
    cg_bme_read_result_t res;

    if (out != NULL) {
        memset(out, 0, sizeof(*out));
    }
    if (port == NULL || s == NULL || out == NULL || port->read == NULL ||
        port->now_ms == NULL) {
        return CG_BME_READ_NOT_READY;
    }

    now = port->now_ms(port->ctx);
    out->obs_ms = now;

    if (s->state != CG_BME_STATE_READY) {
        /* Every non-ready state re-probes under the backoff gate, including
         * ABSENT and IDENTITY_BAD. Returning early for those two would make them
         * terminal: a module that is simply slow to power up, or one that was
         * hot-reseated, would stay declared absent for the whole uptime while the
         * comment below promised recovery without a reboot. The backoff bound
         * keeps a genuinely dead bus from being polled at full rate. */
        if (s->backoff_until_ms != 0u && now < s->backoff_until_ms) {
            out->reason = CG_BME_READ_NOT_READY;
            return CG_BME_READ_NOT_READY;
        }
        res = cg_bme280_probe(port, s);
        if (res != CG_BME_READ_OK) {
            s->reprobe_count++;
            s->backoff_until_ms = now + CG_BME280_BACKOFF_MS;
            out->reason = res;
            return res;
        }
    }

    memset(data, 0, sizeof(data));
    {
        cg_bme_port_result_t pr = port->read(port->ctx, CG_BME280_REG_DATA, data,
                                             sizeof(data));
        if (pr != CG_BME_PORT_OK) {
        res = classify_port(pr);
        s->state = CG_BME_STATE_FAULT;
        s->consecutive_failures++;
        if (s->consecutive_failures >= CG_BME280_MAX_CONSECUTIVE_FAILURES) {
            s->backoff_until_ms = now + CG_BME280_BACKOFF_MS;
            s->state = CG_BME_STATE_UNPROBED;   /* forces a full re-probe next call */
            s->consecutive_failures = 0u;
        }
        out->reason = (res == CG_BME_READ_OK) ? CG_BME_READ_SHORT : res;
        return out->reason;
        }
    }

    adc_t = cg_bme280_unpack_temperature_raw(data);
    adc_h = cg_bme280_unpack_humidity_raw(data);

    /* Compensation clamps to the datasheet bounds, so a saturated or zeroed raw
     * code - what a stuck or half-coupled bus returns - would otherwise come out
     * as a plausible extreme reading and be published. Check the code, not the
     * clamped result. */
    if (adc_t == 0u || adc_t == 0xFFFFFu || adc_h == 0xFFFFu) {
        s->state = CG_BME_STATE_FAULT;
        s->consecutive_failures++;
        if (s->consecutive_failures >= CG_BME280_MAX_CONSECUTIVE_FAILURES) {
            s->backoff_until_ms = now + CG_BME280_BACKOFF_MS;
            s->state = CG_BME_STATE_UNPROBED;
            s->consecutive_failures = 0u;
        }
        out->reason = CG_BME_READ_OUT_OF_RANGE;
        return CG_BME_READ_OUT_OF_RANGE;
    }
    temp_dc = cg_bme280_compensate_temperature(&s->calib, adc_t);
    hum_q2210 = cg_bme280_compensate_humidity(&s->calib, adc_h);

    if (!cg_bme280_reading_in_range(temp_dc, hum_q2210)) {
        s->consecutive_failures++;
        out->reason = CG_BME_READ_OUT_OF_RANGE;
        return CG_BME_READ_OUT_OF_RANGE;
    }

    s->consecutive_failures = 0u;
    s->seq++;
    out->valid = true;
    out->temperature_c = (float)temp_dc / 100.0f;
    out->relative_humidity_pct = (float)hum_q2210 / CG_BME_HUM_Q2210_PER_PCT;
    out->obs_ms = port->now_ms(port->ctx);
    out->seq = s->seq;
    out->reason = CG_BME_READ_OK;
    return CG_BME_READ_OK;
}

const char *cg_bme280_state_name(cg_bme280_state_t state)
{
    switch (state) {
        case CG_BME_STATE_ABSENT:       return "ABSENT";
        case CG_BME_STATE_UNPROBED:     return "UNPROBED";
        case CG_BME_STATE_READY:        return "READY";
        case CG_BME_STATE_FAULT:        return "FAULT";
        case CG_BME_STATE_IDENTITY_BAD: return "IDENTITY_BAD";
        default:                        return "ERROR";
    }
}

bool cg_bme280_is_present(const cg_bme280_t *s)
{
    /* Presence means this module was seen answering with a BME280 identity at
     * some point. Requiring the confirmed chip id is what makes FAULT mean
     * "a sensor that is fitted has started misbehaving": an unpowered or
     * disconnected module leaves the bus floating, and the very first probe then
     * returns a bus timeout rather than a NACK. Counting that FAULT as presence
     * would report "a module is here and is failing" when nothing has ever
     * answered - and would keep the declared-absent path unreachable for the most
     * likely real condition. */
    /* A fitted module that has entered re-probe backoff (UNPROBED after
     * repeated read faults) is still present: chip identity was established.
     * Only an explicit ABSENT/NACK path clears presence. */
    return s != NULL && s->chip_id == CG_BME280_CHIP_ID &&
           s->state != CG_BME_STATE_ABSENT;
}
