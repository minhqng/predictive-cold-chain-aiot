/*
 * Recording implementations of the host mock GPIO/LEDC driver, Leader-owned.
 */
#include "driver/gpio.h"
#include "driver/ledc.h"

#include <string.h>

#define HW_HOST_PIN_MAX 64

static int s_last_output[HW_HOST_PIN_MAX];
static int s_input_level[HW_HOST_PIN_MAX];
static int s_pin_mode[HW_HOST_PIN_MAX];
static int s_gpio_configs;

static uint32_t s_ledc_last_duty;
static uint32_t s_ledc_duty_writes;
static uint32_t s_ledc_fhz;
static uint32_t s_ledc_resolution_bits;
static uint32_t s_ledc_channel_gpio;
static uint32_t s_ledc_channel_configs;
static bool s_ledc_pad_attached;

void hw_host_reset(void)
{
    memset(s_last_output, 0xFF, sizeof(s_last_output)); /* -1 = never written */
    memset(s_pin_mode, 0xFF, sizeof(s_pin_mode));       /* -1 = never configured */
    for (int i = 0; i < HW_HOST_PIN_MAX; i++) {
        s_input_level[i] = 1; /* unpulled-by-harness input reads high */
    }
    s_gpio_configs = 0;
    s_ledc_last_duty = 0U;
    s_ledc_duty_writes = 0U;
    s_ledc_fhz = 0U;
    s_ledc_resolution_bits = 0U;
    s_ledc_channel_gpio = 0U;
    s_ledc_channel_configs = 0U;
    s_ledc_pad_attached = false;
}

int hw_host_gpio_output_level(int pin)
{
    if (pin < 0 || pin >= HW_HOST_PIN_MAX) {
        return -1;
    }
    return s_last_output[pin];
}

int hw_host_gpio_pin_mode(int pin)
{
    if (pin < 0 || pin >= HW_HOST_PIN_MAX) {
        return -1;
    }
    return s_pin_mode[pin];
}

int hw_host_gpio_config_count(void)
{
    return s_gpio_configs;
}

void hw_host_set_input_level(int pin, int level)
{
    if (pin >= 0 && pin < HW_HOST_PIN_MAX) {
        s_input_level[pin] = level;
    }
}

uint32_t hw_host_ledc_last_duty(void)
{
    return s_ledc_last_duty;
}

uint32_t hw_host_ledc_duty_writes(void)
{
    return s_ledc_duty_writes;
}

uint32_t hw_host_ledc_fhz(void)
{
    return s_ledc_fhz;
}

uint32_t hw_host_ledc_resolution_bits(void)
{
    return s_ledc_resolution_bits;
}

uint32_t hw_host_ledc_channel_configs(void)
{
    return s_ledc_channel_configs;
}

bool hw_host_ledc_pad_attached(void)
{
    return s_ledc_pad_attached;
}

uint32_t hw_host_ledc_channel_gpio(void)
{
    return s_ledc_channel_gpio;
}

esp_err_t gpio_config(const gpio_config_t *config)
{
    if (config == NULL) {
        return ESP_FAIL;
    }
    s_gpio_configs++;
    /* Member A's force_off() drives outputs inactive through gpio_set_level
     * below; the mock only records that a configuration happened. */
    for (int p = 0; p < HW_HOST_PIN_MAX; p++) {
        if ((config->pin_bit_mask >> p) & 1ULL) {
            s_pin_mode[p] = (int)config->mode;
            if (config->mode == GPIO_MODE_OUTPUT) {
                s_last_output[p] = 0;
                /* A plain GPIO output configuration on the PWM pad detaches
                 * the LEDC peripheral route, as ESP-IDF gpio_config does. */
                if (p == 5) {
                    s_ledc_pad_attached = false;
                }
            }
        }
    }
    return ESP_OK;
}

esp_err_t gpio_set_level(gpio_num_t gpio_num, uint32_t level)
{
    if (gpio_num < 0 || gpio_num >= HW_HOST_PIN_MAX) {
        return ESP_FAIL;
    }
    s_last_output[gpio_num] = (level != 0U) ? 1 : 0;
    return ESP_OK;
}

int gpio_get_level(gpio_num_t gpio_num)
{
    if (gpio_num < 0 || gpio_num >= HW_HOST_PIN_MAX) {
        return 1;
    }
    return s_input_level[gpio_num];
}

esp_err_t gpio_reset_pin(gpio_num_t gpio_num)
{
    (void)gpio_num;
    return ESP_OK;
}

esp_err_t ledc_timer_config(const ledc_timer_config_t *timer_conf)
{
    if (timer_conf == NULL) {
        return ESP_FAIL;
    }
    s_ledc_fhz = timer_conf->freq_hz;
    s_ledc_resolution_bits = (uint32_t)timer_conf->duty_resolution;
    return ESP_OK;
}

esp_err_t ledc_channel_config(const ledc_channel_config_t *chan_conf)
{
    if (chan_conf == NULL) {
        return ESP_FAIL;
    }
    s_ledc_channel_gpio = (uint32_t)chan_conf->gpio_num;
    s_ledc_last_duty = chan_conf->duty;
    s_ledc_channel_configs++;
    s_ledc_pad_attached = true;
    return ESP_OK;
}

esp_err_t ledc_set_duty(ledc_mode_t speed_mode, ledc_channel_t channel, uint32_t duty)
{
    (void)speed_mode;
    (void)channel;
    s_ledc_last_duty = duty;
    s_ledc_duty_writes++;
    return ESP_OK;
}

esp_err_t ledc_update_duty(ledc_mode_t speed_mode, ledc_channel_t channel)
{
    (void)speed_mode;
    (void)channel;
    return ESP_OK;
}
