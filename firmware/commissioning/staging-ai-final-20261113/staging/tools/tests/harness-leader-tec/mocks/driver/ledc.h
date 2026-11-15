/*
 * Host-harness mock for the ESP-IDF LEDC PWM driver, Leader-owned.
 *
 * Records timer/channel setup and every duty write so the harness can assert
 * the exact duty the IBT-2 RPWM input would have received.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "driver/gpio.h" /* esp_err_t / ESP_OK live here in the host mock */

typedef enum {
    LEDC_HIGH_SPEED_MODE = 0,
    LEDC_LOW_SPEED_MODE,
    LEDC_SPEED_MODE_MAX,
} ledc_mode_t;

typedef enum {
    LEDC_TIMER_0 = 0,
    LEDC_TIMER_1,
    LEDC_TIMER_2,
    LEDC_TIMER_3,
} ledc_timer_t;

typedef enum {
    LEDC_CHANNEL_0 = 0,
    LEDC_CHANNEL_1,
    LEDC_CHANNEL_2,
} ledc_channel_t;

typedef enum {
    LEDC_TIMER_10_BIT = 10,
    LEDC_TIMER_13_BIT = 13,
} ledc_timer_bit_t;

typedef enum {
    LEDC_AUTO_CLK = 0,
} ledc_clk_cfg_t;

typedef struct {
    ledc_mode_t speed_mode;
    ledc_timer_bit_t duty_resolution;
    ledc_timer_t timer_num;
    uint32_t freq_hz;
    ledc_clk_cfg_t clk_cfg;
    bool deconfigure;
} ledc_timer_config_t;

typedef struct {
    int gpio_num;
    ledc_mode_t speed_mode;
    ledc_channel_t channel;
    int dummy_intr_field; /* layout realism; unused by the code under test */
    ledc_timer_t timer_sel;
    uint32_t duty;
    int hpoint;
    bool output_invert;
} ledc_channel_config_t;

esp_err_t ledc_timer_config(const ledc_timer_config_t *timer_conf);
esp_err_t ledc_channel_config(const ledc_channel_config_t *chan_conf);
esp_err_t ledc_set_duty(ledc_mode_t speed_mode, ledc_channel_t channel, uint32_t duty);
esp_err_t ledc_update_duty(ledc_mode_t speed_mode, ledc_channel_t channel);

/* Harness controls. */
uint32_t hw_host_ledc_last_duty(void);
uint32_t hw_host_ledc_duty_writes(void);
uint32_t hw_host_ledc_fhz(void);
uint32_t hw_host_ledc_resolution_bits(void);
uint32_t hw_host_ledc_channel_configs(void);
bool hw_host_ledc_pad_attached(void);
uint32_t hw_host_ledc_channel_gpio(void);
