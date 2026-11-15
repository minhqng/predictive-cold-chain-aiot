/*
 * Host-harness mock for the ESP-IDF GPIO driver, Leader-owned.
 *
 * Records every output write so the host harness can assert what the real
 * branch would have seen, and keeps a per-pin level store that stands in for
 * real inputs (interlock sense). Every pin that was never driven reads high,
 * like a pulled-up missing contact: fail closed.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* ESP-IDF surface actually used by the code under test. */
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1

#define ESP_ERROR_CHECK(x) do { esp_err_t ec__ = (x); if (ec__ != ESP_OK) { return; } } while (0)

typedef enum {
    GPIO_MODE_INPUT = 0,
    GPIO_MODE_OUTPUT,
} gpio_mode_t;

typedef enum {
    GPIO_PULLUP_DISABLE = 0,
    GPIO_PULLUP_ENABLE,
} gpio_pullup_t;

typedef enum {
    GPIO_PULLDOWN_DISABLE = 0,
    GPIO_PULLDOWN_ENABLE,
} gpio_pulldown_t;

typedef enum {
    GPIO_INTR_DISABLE = 0,
} gpio_int_type_t;

typedef int gpio_num_t;

typedef struct {
    uint64_t pin_bit_mask;
    gpio_mode_t mode;
    gpio_pullup_t pull_up_en;
    gpio_pulldown_t pull_down_en;
    gpio_int_type_t intr_type;
} gpio_config_t;

esp_err_t gpio_config(const gpio_config_t *config);
esp_err_t gpio_set_level(gpio_num_t gpio_num, uint32_t level);
int gpio_get_level(gpio_num_t gpio_num);
esp_err_t gpio_reset_pin(gpio_num_t gpio_num);

/* Harness controls: inspect recorded outputs and drive fake inputs. */
void hw_host_reset(void);
int hw_host_gpio_output_level(int pin);   /* last written level, -1 never written */
int hw_host_gpio_pin_mode(int pin);       /* GPIO_MODE_* last configured, -1 unknown */
int hw_host_gpio_config_count(void);      /* gpio_config() calls so far */
void hw_host_set_input_level(int pin, int level);
