/*
 * ColdGuard firmware - boot/default safety state (Member A, W02).
 */
#include "cg_safety.h"

#include "driver/gpio.h"

#include "coldguard_config.h"
#include "cg_log.h"

void cg_safety_force_actuator_off(void)
{
    gpio_config_t cfg = {
        .pin_bit_mask = (1ULL << (uint32_t)CG_PIN_IBT2_COOLING_PWM) |
                        (1ULL << (uint32_t)CG_PIN_IBT2_ENABLE),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE, /* keep the enable low if undriven */
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&cfg));

    /* IBT-2/BTS7960: PWM duty 0 and both enables inactive. */
    (void)gpio_set_level(CG_PIN_IBT2_COOLING_PWM, 0);
    (void)gpio_set_level(CG_PIN_IBT2_ENABLE, 0);

    cg_log_safety_actuator_off();
}
