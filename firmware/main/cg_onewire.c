/*
 * ColdGuard firmware - minimal 1-Wire bus driver (Member A, W02).
 *
 * Timing follows the DS18B20 datasheet slots:
 *   reset pulse low >= 480 us, presence sampled 70 us after release
 *   write 1 : low 6 us, then release for the rest of the 70 us slot
 *   write 0 : low 60 us, then release 10 us
 *   read    : low 3 us, release, sample at 10 us, rest of the slot
 * Each bit/byte runs inside a short critical section so a task switch or
 * an interrupt cannot stretch a slot beyond the datasheet window.
 */
#include "cg_onewire.h"

#include <string.h>

#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"

static int s_pin = -1;
static portMUX_TYPE s_bus_mux = portMUX_INITIALIZER_UNLOCKED;

static inline void ow_drive_low(void)
{
    (void)gpio_set_level(s_pin, 0);
}

static inline void ow_release(void)
{
    (void)gpio_set_level(s_pin, 1); /* open drain: pad goes high-Z */
}

static inline int ow_level(void)
{
    return gpio_get_level(s_pin);
}

void cg_onewire_init(int pin)
{
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << (uint32_t)pin,
        .mode = GPIO_MODE_INPUT_OUTPUT_OD,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&cfg));
    s_pin = pin;
    ow_release();
}

bool cg_onewire_reset(void)
{
    bool presence = false;

    portENTER_CRITICAL(&s_bus_mux);
    ow_drive_low();
    esp_rom_delay_us(480);
    ow_release();
    esp_rom_delay_us(70);
    presence = (ow_level() == 0);
    esp_rom_delay_us(410);
    portEXIT_CRITICAL(&s_bus_mux);

    return presence;
}

void cg_onewire_write_bit(int bit)
{
    portENTER_CRITICAL(&s_bus_mux);
    if (bit) {
        ow_drive_low();
        esp_rom_delay_us(6);
        ow_release();
        esp_rom_delay_us(64);
    } else {
        ow_drive_low();
        esp_rom_delay_us(60);
        ow_release();
        esp_rom_delay_us(10);
    }
    portEXIT_CRITICAL(&s_bus_mux);
}

int cg_onewire_read_bit(void)
{
    int bit;

    portENTER_CRITICAL(&s_bus_mux);
    ow_drive_low();
    esp_rom_delay_us(3);
    ow_release();
    esp_rom_delay_us(10);
    bit = ow_level();
    esp_rom_delay_us(53);
    portEXIT_CRITICAL(&s_bus_mux);

    return bit;
}

void cg_onewire_write_byte(uint8_t byte)
{
    for (int i = 0; i < 8; i++) {
        cg_onewire_write_bit((byte >> i) & 0x01);
    }
}

uint8_t cg_onewire_read_byte(void)
{
    uint8_t byte = 0;
    for (int i = 0; i < 8; i++) {
        byte |= (uint8_t)(cg_onewire_read_bit() << i);
    }
    return byte;
}

void cg_onewire_write_bytes(const uint8_t *data, int len)
{
    for (int i = 0; i < len; i++) {
        cg_onewire_write_byte(data[i]);
    }
}

void cg_onewire_read_bytes(uint8_t *out, int len)
{
    for (int i = 0; i < len; i++) {
        out[i] = cg_onewire_read_byte();
    }
}

uint8_t cg_onewire_crc8(const uint8_t *data, int len)
{
    uint8_t crc = 0;
    for (int i = 0; i < len; i++) {
        uint8_t byte = data[i];
        for (int bit = 0; bit < 8; bit++) {
            uint8_t mix = (uint8_t)((crc ^ byte) & 0x01);
            crc >>= 1;
            if (mix) {
                crc ^= 0x8C;
            }
            byte >>= 1;
        }
    }
    return crc;
}
