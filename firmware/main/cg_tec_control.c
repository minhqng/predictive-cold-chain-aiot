/*
 * ColdGuard firmware - fail-closed cooling-only TEC controller (W04).
 *
 * Pure C by design: the host harness compiles this file unchanged. All
 * physical effects go through cg_tec_hw_ops_t, so "no output" is provable
 * by checking that the fake backend never saw an enable or a nonzero duty.
 */
#include "cg_tec_control.h"

#include <string.h>

static void set_reason(cg_tec_control_t *ctl, const char *reason)
{
    if (reason == NULL) {
        ctl->reason[0] = '\0';
        return;
    }
    size_t len = strlen(reason);
    if (len >= sizeof(ctl->reason)) {
        len = sizeof(ctl->reason) - 1U;
    }
    memcpy(ctl->reason, reason, len);
    ctl->reason[len] = '\0';
}

static bool token_matches(const char *expected, const char *given)
{
    if (expected == NULL || given == NULL || expected[0] == '\0') {
        return false;
    }
    if (strlen(expected) != strlen(given)) {
        return false;
    }
    /* The token is bound to the local UART console, not to a hostile network.
     * This loop avoids an early-exit compare anyway. */
    unsigned char diff = 0U;
    for (size_t i = 0; expected[i] != '\0'; i++) {
        diff |= (unsigned char)(expected[i] ^ given[i]);
    }
    return diff == 0U;
}

static bool ops_ok(const cg_tec_control_t *ctl)
{
    return ctl->ops.set_enables != NULL && ctl->ops.set_cooling_duty != NULL &&
           ctl->ops.set_fan != NULL && ctl->ops.read_interlock != NULL &&
           ctl->ops.output_stage_available != NULL && ctl->ops.fan_available != NULL;
}

static bool stage_available(const cg_tec_control_t *ctl)
{
    return ops_ok(ctl) && ctl->ops.output_stage_available();
}

static bool fan_available(const cg_tec_control_t *ctl)
{
    return ops_ok(ctl) && ctl->ops.fan_available();
}

static float limit_value(const cg_tec_control_t *ctl, cg_limit_id_t id)
{
    const cg_limit_t *limit = cg_tec_limit(ctl->limits, id);
    return limit == NULL ? 0.0f : limit->value;
}

/* Enables off first, then PWM off. Used by every stop and fault path. */
static bool safe_stop_outputs(cg_tec_control_t *ctl)
{
    bool ok = true;

    if (!ops_ok(ctl)) {
        ctl->outputs_energized = false;
        return false;
    }
    if (!ctl->ops.set_enables(false, false)) {
        ok = false;
    }
    if (!ctl->ops.set_cooling_duty(0U)) {
        ok = false;
    }
    ctl->outputs_energized = false;
    ctl->duty_permille = 0U;
    return ok;
}

static void latch_fault(cg_tec_control_t *ctl, uint32_t bit, const char *reason)
{
    ctl->fault_bits |= bit;
    ctl->fault_count++;
    (void)safe_stop_outputs(ctl);
    /* Keep the fan running while latched: the hot side may be warm. */
    if (ops_ok(ctl) && fan_available(ctl)) {
        (void)ctl->ops.set_fan(true);
        ctl->fan_on = true;
    } else {
        ctl->fan_on = false;
    }
    ctl->state = CG_TEC_STATE_FAULT_LATCH;
    set_reason(ctl, reason);
}

static bool arm_valid(const cg_tec_control_t *ctl, uint64_t now_ms)
{
    if (!ctl->authorized) {
        return false;
    }
    if (now_ms < ctl->authorized_at_ms) {
        return false;
    }
    return (now_ms - ctl->authorized_at_ms) <= (uint64_t)ctl->arm_ttl_ms;
}

static void disarm(cg_tec_control_t *ctl)
{
    ctl->authorized = false;
}

/* First sensor/limit problem, as a fault bit (0 = healthy). `under_load`
 * enables the supply-voltage lower bound, which is only meaningful while the
 * branch draws current. */
static uint32_t inputs_problem(const cg_tec_control_t *ctl, const cg_tec_inputs_t *in,
                               bool under_load, const char **reason)
{
    *reason = "OK";

    if (!in->thermal_observed) {
        *reason = "NO_THERMAL_DATA";
        return CG_TEC_FAULT_SENSOR_INVALID;
    }
    if (in->now_ms < in->thermal_obs_ms ||
        in->now_ms - in->thermal_obs_ms > (uint64_t)ctl->thermal_stale_ms) {
        *reason = "THERMAL_STALE";
        return CG_TEC_FAULT_SENSOR_STALE;
    }
    if (!in->thermal_valid) {
        *reason = "THERMAL_INVALID";
        return CG_TEC_FAULT_SENSOR_INVALID;
    }
    if (!in->t_cold_side_valid) {
        *reason = "NO_COLD_SIDE_SENSOR";
        return CG_TEC_FAULT_SENSOR_INVALID;
    }
    if (!in->t_hot_side_valid) {
        *reason = "NO_HOT_SIDE_SENSOR";
        return CG_TEC_FAULT_SENSOR_INVALID;
    }
    if (!in->power_observed) {
        *reason = "NO_POWER_DATA";
        return CG_TEC_FAULT_SENSOR_INVALID;
    }
    if (in->now_ms < in->power_obs_ms ||
        in->now_ms - in->power_obs_ms > (uint64_t)ctl->power_stale_ms) {
        *reason = "POWER_STALE";
        return CG_TEC_FAULT_SENSOR_STALE;
    }
    if (!in->power_valid) {
        *reason = "POWER_INVALID";
        return CG_TEC_FAULT_SENSOR_INVALID;
    }
    if (in->current_a > limit_value(ctl, CG_LIMIT_CURRENT_MAX_A)) {
        *reason = "OVERCURRENT";
        return CG_TEC_FAULT_OVERCURRENT;
    }
    if (in->voltage_v > limit_value(ctl, CG_LIMIT_VOLTAGE_MAX_V)) {
        *reason = "OVERVOLTAGE";
        return CG_TEC_FAULT_OVERVOLTAGE;
    }
    if (under_load && in->voltage_v < limit_value(ctl, CG_LIMIT_VOLTAGE_MIN_V)) {
        *reason = "UNDERVOLTAGE";
        return CG_TEC_FAULT_UNDERVOLTAGE;
    }
    if (in->t_hot_side_c > limit_value(ctl, CG_LIMIT_HOT_SIDE_MAX_C)) {
        *reason = "OVERTEMP";
        return CG_TEC_FAULT_OVERTEMP;
    }
    return 0U;
}

static void begin_cooldown(cg_tec_control_t *ctl, uint64_t now_ms, const char *reason)
{
    (void)safe_stop_outputs(ctl);
    if (ops_ok(ctl) && fan_available(ctl)) {
        (void)ctl->ops.set_fan(true);
        ctl->fan_on = true;
    }
    ctl->state = CG_TEC_STATE_COOLDOWN;
    ctl->cooldown_until_ms = now_ms + (uint64_t)ctl->cooldown_ms;
    set_reason(ctl, reason);
}

void cg_tec_control_init(cg_tec_control_t *ctl, const cg_tec_limit_table_t *limits,
                         const cg_tec_hw_ops_t *ops, const char *boot_token,
                         uint64_t now_ms, uint32_t arm_ttl_ms,
                         uint32_t heartbeat_timeout_ms, uint32_t cooldown_ms,
                         uint32_t thermal_stale_ms, uint32_t power_stale_ms)
{
    memset(ctl, 0, sizeof(*ctl));
    ctl->limits = limits;
    if (ops != NULL) {
        ctl->ops = *ops;
    }
    if (boot_token != NULL) {
        size_t len = strlen(boot_token);
        if (len >= sizeof(ctl->token)) {
            len = sizeof(ctl->token) - 1U;
        }
        memcpy(ctl->token, boot_token, len);
        ctl->token[len] = '\0';
    }
    ctl->state = CG_TEC_STATE_OFF;
    ctl->last_tick_ms = now_ms;
    ctl->have_tick = false;
    ctl->arm_ttl_ms = arm_ttl_ms;
    ctl->heartbeat_timeout_ms = heartbeat_timeout_ms;
    ctl->cooldown_ms = cooldown_ms;
    ctl->thermal_stale_ms = thermal_stale_ms;
    ctl->power_stale_ms = power_stale_ms;
    set_reason(ctl, "BOOT_SAFE_OFF");
}

bool cg_tec_arm(cg_tec_control_t *ctl, const char *token, uint64_t now_ms)
{
    if (ctl->state != CG_TEC_STATE_OFF && ctl->state != CG_TEC_STATE_ARMED) {
        ctl->refuse_count++;
        set_reason(ctl, "ARM_BAD_STATE");
        return false;
    }
    if (!token_matches(ctl->token, token)) {
        ctl->refuse_count++;
        set_reason(ctl, "ARM_BAD_TOKEN");
        return false;
    }
    ctl->authorized = true;
    ctl->authorized_at_ms = now_ms;
    ctl->state = CG_TEC_STATE_ARMED;
    set_reason(ctl, "ARMED");
    return true;
}

bool cg_tec_is_armed(const cg_tec_control_t *ctl, uint64_t now_ms)
{
    return ctl->state == CG_TEC_STATE_ARMED && arm_valid(ctl, now_ms);
}

cg_tec_start_result_t cg_tec_start(cg_tec_control_t *ctl, const cg_tec_inputs_t *in,
                                   uint32_t duration_ms, uint32_t duty_permille)
{
    const char *reason = "OK";
    uint32_t problem;
    const cg_limit_t *on_time_limit = cg_tec_limit(ctl->limits, CG_LIMIT_ON_TIME_MAX_MS);
    const cg_limit_t *duty_limit = cg_tec_limit(ctl->limits, CG_LIMIT_DUTY_MAX_PERMILLE);

    if (in == NULL || ctl->state == CG_TEC_STATE_COOLING || ctl->state == CG_TEC_STATE_COOLDOWN ||
        ctl->state == CG_TEC_STATE_FAULT_LATCH) {
        ctl->refuse_count++;
        set_reason(ctl, "START_BAD_STATE");
        return CG_TEC_START_BAD_STATE;
    }
    if (!arm_valid(ctl, in->now_ms)) {
        const bool was_armed = ctl->state == CG_TEC_STATE_ARMED;

        disarm(ctl);
        if (was_armed) {
            /* Keep the reported state truthful: an expired ARM is not an ARM,
             * even when the operator never ticked between expiry and START. */
            ctl->state = CG_TEC_STATE_OFF;
            set_reason(ctl, "ARM_EXPIRED");
        } else {
            set_reason(ctl, "START_NOT_ARMED");
        }
        ctl->refuse_count++;
        return CG_TEC_START_NOT_ARMED;
    }
    if (!ops_ok(ctl)) {
        ctl->refuse_count++;
        set_reason(ctl, "START_NO_PLATFORM");
        return CG_TEC_START_HW_REJECTED;
    }
    if (duty_permille == 0U || duty_permille > CG_TEC_DUTY_MAX) {
        ctl->refuse_count++;
        set_reason(ctl, "START_BAD_DUTY");
        return CG_TEC_START_BAD_DUTY;
    }
    if (duration_ms == 0U) {
        ctl->refuse_count++;
        set_reason(ctl, "START_BAD_DURATION");
        return CG_TEC_START_BAD_DURATION;
    }
    if (!cg_tec_limits_all_resolved(ctl->limits)) {
        ctl->refuse_count++;
        set_reason(ctl, "START_LIMITS_UNRESOLVED");
        return CG_TEC_START_LIMITS_UNRESOLVED;
    }
    if (on_time_limit == NULL || duty_limit == NULL ||
        (float)duration_ms > on_time_limit->value ||
        (float)duty_permille > duty_limit->value) {
        ctl->refuse_count++;
        set_reason(ctl, "START_OUTSIDE_LIMITS");
        return CG_TEC_START_BAD_DURATION;
    }
    if (!stage_available(ctl)) {
        ctl->refuse_count++;
        set_reason(ctl, "START_STAGE_UNAVAILABLE");
        return CG_TEC_START_STAGE_UNAVAILABLE;
    }
    problem = inputs_problem(ctl, in, false, &reason);
    if (problem != 0U) {
        ctl->refuse_count++;
        set_reason(ctl, reason);
        return CG_TEC_START_SENSOR;
    }
    if (!ctl->ops.read_interlock()) {
        ctl->refuse_count++;
        set_reason(ctl, "START_INTERLOCK_OPEN");
        return CG_TEC_START_INTERLOCK_OPEN;
    }
    if (!ctl->ops.fan_available()) {
        ctl->refuse_count++;
        set_reason(ctl, "START_FAN_UNAVAILABLE");
        return CG_TEC_START_FAN_UNAVAILABLE;
    }

    /* Ordered bring-up. Any failure rolls the whole sequence back. */
    if (!ctl->ops.set_cooling_duty(0U)) {
        (void)ctl->ops.set_enables(false, false);
        ctl->refuse_count++;
        latch_fault(ctl, CG_TEC_FAULT_HW_REJECTED, "START_HW_REJECTED");
        return CG_TEC_START_HW_REJECTED;
    }
    if (!ctl->ops.set_fan(true)) {
        (void)ctl->ops.set_cooling_duty(0U);
        (void)ctl->ops.set_enables(false, false);
        ctl->refuse_count++;
        latch_fault(ctl, CG_TEC_FAULT_HW_REJECTED, "START_FAN_REJECTED");
        return CG_TEC_START_HW_REJECTED;
    }
    if (!ctl->ops.set_enables(true, false)) {
        (void)ctl->ops.set_enables(false, false);
        (void)ctl->ops.set_cooling_duty(0U);
        (void)ctl->ops.set_fan(false);
        ctl->refuse_count++;
        latch_fault(ctl, CG_TEC_FAULT_HW_REJECTED, "START_ENABLE_REJECTED");
        return CG_TEC_START_HW_REJECTED;
    }
    if (!ctl->ops.set_cooling_duty(duty_permille)) {
        (void)ctl->ops.set_enables(false, false);
        (void)ctl->ops.set_cooling_duty(0U);
        (void)ctl->ops.set_fan(false);
        ctl->refuse_count++;
        latch_fault(ctl, CG_TEC_FAULT_HW_REJECTED, "START_DUTY_REJECTED");
        return CG_TEC_START_HW_REJECTED;
    }

    disarm(ctl); /* one ARM authorizes exactly one bounded run */
    ctl->state = CG_TEC_STATE_COOLING;
    ctl->outputs_energized = true;
    ctl->fan_on = true;
    ctl->duty_permille = duty_permille;
    ctl->cooling_start_ms = in->now_ms;
    ctl->cooling_deadline_ms = in->now_ms + (uint64_t)duration_ms;
    ctl->start_count++;
    set_reason(ctl, "COOLING");
    return CG_TEC_START_OK;
}

void cg_tec_stop(cg_tec_control_t *ctl, const cg_tec_inputs_t *in, const char *reason)
{
    uint64_t now_ms = in != NULL ? in->now_ms : ctl->last_tick_ms;

    switch (ctl->state) {
        case CG_TEC_STATE_COOLING:
            begin_cooldown(ctl, now_ms, reason != NULL ? reason : "OPERATOR_STOP");
            ctl->stop_count++;
            break;
        case CG_TEC_STATE_ARMED:
            disarm(ctl);
            ctl->state = CG_TEC_STATE_OFF;
            set_reason(ctl, "STOPPED_BEFORE_START");
            ctl->stop_count++;
            break;
        case CG_TEC_STATE_OFF:
        case CG_TEC_STATE_COOLDOWN:
            set_reason(ctl, "STOP_NOOP");
            break;
        case CG_TEC_STATE_FAULT_LATCH:
        default:
            /* A latched fault keeps its reason: STOP is not a CLEAR, so the
             * diagnostic cause must survive in the status and telemetry. */
            break;
    }
}

void cg_tec_estop(cg_tec_control_t *ctl, uint64_t now_ms, const char *reason)
{
    (void)now_ms;
    ctl->estop_count++;
    latch_fault(ctl, CG_TEC_FAULT_ESTOP, reason != NULL ? reason : "ESTOP");
}

bool cg_tec_clear_fault(cg_tec_control_t *ctl, const char *token, const cg_tec_inputs_t *in)
{
    const char *reason = "OK";
    uint32_t problem;

    if (ctl->state != CG_TEC_STATE_FAULT_LATCH) {
        set_reason(ctl, "CLEAR_NO_FAULT");
        return false;
    }
    if (!token_matches(ctl->token, token)) {
        ctl->refuse_count++;
        set_reason(ctl, "CLEAR_BAD_TOKEN");
        return false;
    }
    if (in == NULL) {
        ctl->refuse_count++;
        set_reason(ctl, "CLEAR_NO_INPUTS");
        return false;
    }
    problem = inputs_problem(ctl, in, true, &reason);
    if (problem != 0U) {
        ctl->refuse_count++;
        set_reason(ctl, reason);
        return false;
    }
    if (!ops_ok(ctl) || !ctl->ops.read_interlock()) {
        ctl->refuse_count++;
        set_reason(ctl, "CLEAR_INTERLOCK_OPEN");
        return false;
    }
    ctl->fault_bits = 0U;
    ctl->state = CG_TEC_STATE_COOLDOWN;
    ctl->cooldown_until_ms = in->now_ms + (uint64_t)ctl->cooldown_ms;
    set_reason(ctl, "FAULT_CLEARED");
    return true;
}

void cg_tec_tick(cg_tec_control_t *ctl, const cg_tec_inputs_t *in)
{
    const char *reason = "OK";
    uint32_t problem;
    uint64_t now_ms;

    if (in == NULL) {
        return;
    }
    now_ms = in->now_ms;

    if (ctl->have_tick) {
        if (now_ms < ctl->last_tick_ms) {
            latch_fault(ctl, CG_TEC_FAULT_HEARTBEAT, "CLOCK_BACKWARDS");
            ctl->last_tick_ms = now_ms;
            return;
        }
        /* A scheduling gap only matters while the branch can be energized; in
         * OFF the task watchdog and the per-boot safe state cover the system. */
        if (ctl->state == CG_TEC_STATE_COOLING &&
            now_ms - ctl->last_tick_ms > (uint64_t)ctl->heartbeat_timeout_ms) {
            latch_fault(ctl, CG_TEC_FAULT_HEARTBEAT, "HEARTBEAT_LOST");
        }
    }
    ctl->last_tick_ms = now_ms;
    ctl->have_tick = true;

    switch (ctl->state) {
        case CG_TEC_STATE_OFF:
            if (ctl->outputs_energized) {
                (void)safe_stop_outputs(ctl);
            }
            break;

        case CG_TEC_STATE_ARMED:
            if (!arm_valid(ctl, now_ms)) {
                disarm(ctl);
                ctl->state = CG_TEC_STATE_OFF;
                set_reason(ctl, "ARM_EXPIRED");
            }
            break;

        case CG_TEC_STATE_COOLING:
            problem = inputs_problem(ctl, in, true, &reason);
            if (problem != 0U) {
                latch_fault(ctl, problem, reason);
                break;
            }
            if (!ctl->ops.read_interlock()) {
                latch_fault(ctl, CG_TEC_FAULT_INTERLOCK_OPEN, "INTERLOCK_OPEN");
                break;
            }
            if (!fan_available(ctl)) {
                latch_fault(ctl, CG_TEC_FAULT_FAN_UNAVAILABLE, "FAN_UNAVAILABLE");
                break;
            }
            if (now_ms >= ctl->cooling_deadline_ms) {
                begin_cooldown(ctl, now_ms, "DURATION_REACHED");
            }
            break;

        case CG_TEC_STATE_COOLDOWN:
            if (now_ms >= ctl->cooldown_until_ms) {
                if (ops_ok(ctl) && ctl->fan_on) {
                    (void)ctl->ops.set_fan(false);
                }
                ctl->fan_on = false;
                ctl->state = CG_TEC_STATE_OFF;
                set_reason(ctl, "COOLDOWN_DONE");
            } else if (ops_ok(ctl) && fan_available(ctl) && !ctl->fan_on) {
                (void)ctl->ops.set_fan(true);
                ctl->fan_on = true;
            }
            break;

        case CG_TEC_STATE_FAULT_LATCH:
        default:
            if (ctl->outputs_energized) {
                (void)safe_stop_outputs(ctl);
            }
            break;
    }
}

void cg_tec_get_status(const cg_tec_control_t *ctl, cg_tec_status_t *out)
{
    memset(out, 0, sizeof(*out));
    out->state = ctl->state;
    out->fault_bits = ctl->fault_bits;
    out->duty_permille = ctl->duty_permille;
    out->start_count = ctl->start_count;
    out->stop_count = ctl->stop_count;
    out->estop_count = ctl->estop_count;
    out->fault_count = ctl->fault_count;
    out->refuse_count = ctl->refuse_count;
    out->fan_on = ctl->fan_on;
    if (ctl->state == CG_TEC_STATE_COOLING) {
        out->elapsed_ms = ctl->last_tick_ms >= ctl->cooling_start_ms
                              ? ctl->last_tick_ms - ctl->cooling_start_ms
                              : 0U;
        out->remaining_ms = ctl->cooling_deadline_ms > ctl->last_tick_ms
                                ? ctl->cooling_deadline_ms - ctl->last_tick_ms
                                : 0U;
    }
    memcpy(out->reason, ctl->reason, sizeof(out->reason));
    out->reason[sizeof(out->reason) - 1U] = '\0';
}

const char *cg_tec_state_name(cg_tec_state_t state)
{
    switch (state) {
        case CG_TEC_STATE_OFF:
            return "OFF";
        case CG_TEC_STATE_ARMED:
            return "ARMED";
        case CG_TEC_STATE_COOLING:
            return "COOLING";
        case CG_TEC_STATE_COOLDOWN:
            return "COOLDOWN";
        case CG_TEC_STATE_FAULT_LATCH:
            return "FAULT_LATCH";
        default:
            return "UNKNOWN";
    }
}

const char *cg_tec_start_result_name(cg_tec_start_result_t result)
{
    switch (result) {
        case CG_TEC_START_OK:
            return "OK";
        case CG_TEC_START_NOT_ARMED:
            return "NOT_ARMED";
        case CG_TEC_START_BAD_STATE:
            return "BAD_STATE";
        case CG_TEC_START_BAD_DUTY:
            return "BAD_DUTY";
        case CG_TEC_START_BAD_DURATION:
            return "BAD_DURATION";
        case CG_TEC_START_LIMITS_UNRESOLVED:
            return "LIMITS_UNRESOLVED";
        case CG_TEC_START_STAGE_UNAVAILABLE:
            return "STAGE_UNAVAILABLE";
        case CG_TEC_START_SENSOR:
            return "SENSOR";
        case CG_TEC_START_INTERLOCK_OPEN:
            return "INTERLOCK_OPEN";
        case CG_TEC_START_FAN_UNAVAILABLE:
            return "FAN_UNAVAILABLE";
        case CG_TEC_START_HW_REJECTED:
            return "HW_REJECTED";
        default:
            return "UNKNOWN";
    }
}
