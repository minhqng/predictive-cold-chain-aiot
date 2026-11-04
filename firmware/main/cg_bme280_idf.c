/*
 * ColdGuard firmware - ESP-IDF I2C transport for the BME280 producer.
 * See cg_bme280_idf.h for the error mapping this file implements and for why
 * absence is an observation rather than an open() failure.
 */
#include "cg_bme280_idf.h"

#include <string.h>

#include "driver/i2c_master.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "coldguard_config.h"

/* A bounded transaction is the point of this file: an unbounded I2C call would
 * let one stuck device hold the producer task, and the telemetry would report a
 * stalled producer instead of a faulty sensor. 40 ms is well above a 100 kHz
 * register read (a 9-byte transaction is ~1 ms) and well below the 1 s producer
 * period, so a timeout is a real bus fault and not normal slack. */
#define CG_BME_I2C_TIMEOUT_MS 40
#define CG_BME_I2C_SCL_HZ 100000u

static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_dev;
static uint8_t s_address;
static bool s_bus_ready;

static cg_bme_port_result_t map_err(esp_err_t err)
{
    switch (err) {
        case ESP_OK:
            return CG_BME_PORT_OK;
        case ESP_ERR_TIMEOUT:
            return CG_BME_PORT_TIMEOUT;
        /* The v6.1 master driver reports a NACKed address as INVALID_RESPONSE on
         * transmit and NOT_FOUND on probe; both mean "no device at this
         * address", which is the one distinction the producer must keep. */
        case ESP_ERR_INVALID_RESPONSE:
        case ESP_ERR_NOT_FOUND:
            return CG_BME_PORT_NACK;
        default:
            return CG_BME_PORT_ERROR;
    }
}

static cg_bme_port_result_t bme_read(void *ctx, uint8_t reg, uint8_t *out, size_t len)
{
    i2c_master_dev_handle_t dev = (i2c_master_dev_handle_t)ctx;

    if (dev == NULL || out == NULL || len == 0u) {
        return CG_BME_PORT_ERROR;
    }
    return map_err(i2c_master_transmit_receive(dev, &reg, 1u, out, len,
                                               CG_BME_I2C_TIMEOUT_MS));
}

static cg_bme_port_result_t bme_write(void *ctx, uint8_t reg, uint8_t value)
{
    i2c_master_dev_handle_t dev = (i2c_master_dev_handle_t)ctx;
    uint8_t buf[2];

    if (dev == NULL) {
        return CG_BME_PORT_ERROR;
    }
    buf[0] = reg;
    buf[1] = value;
    return map_err(i2c_master_transmit(dev, buf, sizeof(buf), CG_BME_I2C_TIMEOUT_MS));
}

static uint64_t bme_now_ms(void *ctx)
{
    (void)ctx;
    return (uint64_t)(esp_timer_get_time() / 1000);
}

static void bme_settle_ms(void *ctx, uint32_t ms)
{
    TickType_t ticks;

    (void)ctx;
    /* pdMS_TO_TICKS rounds down, and vTaskDelay(0) only yields to equal or
     * higher priority tasks - so a 1-2 ms settle would not actually settle. The
     * same rounding the door task had to fix applies here. */
    ticks = pdMS_TO_TICKS(ms);
    if (ticks == 0u) {
        ticks = 1u;
    }
    vTaskDelay(ticks);
}

bool cg_bme280_idf_open(cg_bme280_port_t *port, uint8_t *address_out)
{
    i2c_master_bus_config_t bus_cfg;
    i2c_device_config_t dev_cfg;
    const uint8_t candidates[2] = {CG_BME280_I2C_ADDR_EVIDENCED, CG_BME280_I2C_ADDR_ALT};
    uint8_t chosen = CG_BME280_I2C_ADDR_EVIDENCED;
    bool acked = false;
    esp_err_t err;

    if (port == NULL) {
        return false;
    }
    if (s_bus_ready) {
        *port = (cg_bme280_port_t){
            .ctx = s_dev, .read = bme_read, .write = bme_write,
            .now_ms = bme_now_ms, .settle_ms = bme_settle_ms,
        };
        if (address_out != NULL) {
            *address_out = s_address;
        }
        return true;
    }

    memset(&bus_cfg, 0, sizeof(bus_cfg));
    bus_cfg.i2c_port = I2C_NUM_0;
    bus_cfg.sda_io_num = CG_PIN_BME280_SDA;
    bus_cfg.scl_io_num = CG_PIN_BME280_SCL;
    bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_cfg.glitch_ignore_cnt = 7;
    /* v6.1 has no per-line pull-up field on the bus config; the internal pull-ups
     * are one flag. External pull-ups are reported for this board but never
     * verified: evidence/A/W01/hardware-audit-w01.md records the 4.7k resistor as
     * "no photo/measurement", and evidence/A/W04/g0-electrical-verification.md
     * says it cannot prove where that resistor sits. The internal flag is enabled
     * because the bus may have none at all; whether 100 kHz actually works on this
     * board is an operator confirmation item, not something this line asserts. */
    bus_cfg.flags.enable_internal_pullup = true;

    err = i2c_new_master_bus(&bus_cfg, &s_bus);
    if (err != ESP_OK) {
        return false;
    }

    /* The strap decides between the two addresses and nobody has read the strap
     * on this board: evidence/A/W02/bme280/ shows 0x76 answering while the SCL
     * was still on GPIO33, and the header has since been re-soldered to GPIO34.
     * Probing both is bounded and cheap; binding the evidenced address when
     * neither answers keeps a silent module reportable as ABSENT instead of
     * failing the whole producer open. */
    for (size_t i = 0; i < sizeof(candidates) / sizeof(candidates[0]); i++) {
        if (i2c_master_probe(s_bus, candidates[i], CG_BME_I2C_TIMEOUT_MS) == ESP_OK) {
            chosen = candidates[i];
            acked = true;
            break;
        }
    }
    s_address = chosen;

    memset(&dev_cfg, 0, sizeof(dev_cfg));
    dev_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev_cfg.device_address = s_address;
    dev_cfg.scl_speed_hz = CG_BME_I2C_SCL_HZ;

    if (i2c_master_bus_add_device(s_bus, &dev_cfg, &s_dev) != ESP_OK) {
        i2c_del_master_bus(s_bus);
        s_bus = NULL;
        return false;
    }

    s_bus_ready = true;
    *port = (cg_bme280_port_t){
        .ctx = s_dev, .read = bme_read, .write = bme_write,
        .now_ms = bme_now_ms, .settle_ms = bme_settle_ms,
    };
    if (address_out != NULL) {
        *address_out = s_address;
    }
    /* `acked` is reported by the caller through cg_bme280_idf_address() plus the
     * producer's own probe result; it is not folded into the return value,
     * because "bus is up, device is quiet" must stay a working configuration. */
    (void)acked;
    return true;
}

uint8_t cg_bme280_idf_address(void)
{
    return s_address;
}

bool cg_bme280_idf_bus_ready(void)
{
    return s_bus_ready;
}
