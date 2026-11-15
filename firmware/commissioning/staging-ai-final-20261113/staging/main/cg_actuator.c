/*
 * ColdGuard firmware - IBT-2/BTS7960 safe-state module (Member A, W03).
 */
#include "cg_actuator.h"

#include "driver/gpio.h"

#include "coldguard_config.h"

static bool s_off = true;
static uint32_t s_forced_off_count;

void cg_actuator_force_off(void)
{
    gpio_config_t config = {
        .pin_bit_mask = (1ULL << (uint32_t)CG_ACTUATOR_RPWM_PIN) |
                        (1ULL << (uint32_t)CG_ACTUATOR_REN_PIN) |
                        (1ULL << (uint32_t)CG_ACTUATOR_LEN_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE, /* keep the enables low if undriven */
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&config));

    /* IBT-2/BTS7960: PWM duty 0 and both enable inputs inactive. The
     * enables are cleared before the PWM level is written, so the safe
     * state is reached without a window where a driven PWM is enabled.
     * LPWM is tied to GND on the module and is not driven here. */
    (void)gpio_set_level(CG_ACTUATOR_REN_PIN, 0);
    (void)gpio_set_level(CG_ACTUATOR_LEN_PIN, 0);
    (void)gpio_set_level(CG_ACTUATOR_RPWM_PIN, 0);

    s_off = true;
    s_forced_off_count++;
}

bool cg_actuator_outputs_allowed(bool operator_authorized, uint32_t rpwm_duty,
                                 uint32_t lpwm_duty)
{
    if (rpwm_duty > CG_ACTUATOR_DUTY_MAX || lpwm_duty > CG_ACTUATOR_DUTY_MAX) {
        return false;
    }
    /* W03 drives at most one half-bridge. With both driven the load would see
     * (RPWM - LPWM)*V: equal duties give equal bridge outputs and no
     * differential (not a reverse), and an unequal pair is a differential
     * this layer never commands. */
    if (rpwm_duty > 0U && lpwm_duty > 0U) {
        return false;
    }
    /* No operator authorization, no output. */
    if (!operator_authorized) {
        return false;
    }
#if CG_ACTUATOR_ENABLE_ALLOWED != 1
    /* W03: the output layer does not exist yet; refuse even authorized work. */
    return false;
#else
    return true;
#endif
}

bool cg_actuator_is_off(void)
{
    return s_off;
}

uint32_t cg_actuator_forced_off_count(void)
{
    return s_forced_off_count;
}
