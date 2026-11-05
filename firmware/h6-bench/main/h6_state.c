/*
 * ColdGuard H6 - test state machine implementation.
 */
#include "h6_state.h"

#include <stddef.h>

#include "h6_config.h"

void h6_sm_init(h6_sm_t *sm)
{
    if (sm == NULL) {
        return;
    }
    sm->state = H6_STATE_BOOT;
    sm->stop_reason = H6_STOP_NONE;
    sm->run_start_us = 0;
    sm->run_stop_us = 0;
    sm->run_consumed = false;
}

bool h6_sm_safe_off(h6_sm_t *sm)
{
    if (sm == NULL || sm->state != H6_STATE_BOOT) {
        return false;
    }
    sm->state = H6_STATE_SAFE_OFF;
    return true;
}

bool h6_sm_ready(h6_sm_t *sm)
{
    if (sm == NULL || sm->state != H6_STATE_SAFE_OFF) {
        return false;
    }
    sm->state = H6_STATE_WAIT_FOR_MANUAL_ARM;
    return true;
}

bool h6_sm_arm(h6_sm_t *sm)
{
    if (sm == NULL || sm->state != H6_STATE_WAIT_FOR_MANUAL_ARM) {
        return false;
    }
    sm->state = H6_STATE_ARMED;
    return true;
}

bool h6_sm_start(h6_sm_t *sm, int64_t now_us)
{
    if (sm == NULL || sm->state != H6_STATE_ARMED || sm->run_consumed) {
        return false;
    }
    sm->state = H6_STATE_RUNNING_10_PERCENT;
    sm->run_start_us = now_us;
    sm->run_consumed = true;
    sm->stop_reason = H6_STOP_NONE;
    return true;
}

bool h6_sm_stop(h6_sm_t *sm, h6_stop_reason_t reason, int64_t now_us)
{
    if (sm == NULL || sm->state != H6_STATE_RUNNING_10_PERCENT) {
        return false;
    }
    sm->state = H6_STATE_SAFE_OFF_FINAL;
    sm->stop_reason = reason;
    sm->run_stop_us = now_us;
    return true;
}

bool h6_sm_complete(h6_sm_t *sm)
{
    if (sm == NULL || sm->state != H6_STATE_SAFE_OFF_FINAL) {
        return false;
    }
    sm->state = H6_STATE_COMPLETE;
    return true;
}

bool h6_sm_deadline_reached(const h6_sm_t *sm, int64_t now_us)
{
    if (sm == NULL || sm->state != H6_STATE_RUNNING_10_PERCENT) {
        return false;
    }
    return (now_us - sm->run_start_us) >= H6_MAX_ON_US;
}

int64_t h6_sm_elapsed_us(const h6_sm_t *sm, int64_t now_us)
{
    if (sm == NULL) {
        return 0;
    }
    if (sm->state == H6_STATE_RUNNING_10_PERCENT) {
        return now_us - sm->run_start_us;
    }
    if (sm->state == H6_STATE_SAFE_OFF_FINAL || sm->state == H6_STATE_COMPLETE) {
        return sm->run_stop_us - sm->run_start_us;
    }
    return 0;
}

const char *h6_state_name(h6_state_t state)
{
    switch (state) {
    case H6_STATE_BOOT:
        return "BOOT";
    case H6_STATE_SAFE_OFF:
        return "SAFE_OFF";
    case H6_STATE_WAIT_FOR_MANUAL_ARM:
        return "WAIT_FOR_MANUAL_ARM";
    case H6_STATE_ARMED:
        return "ARMED";
    case H6_STATE_RUNNING_10_PERCENT:
        return "RUNNING_10_PERCENT";
    case H6_STATE_SAFE_OFF_FINAL:
        return "SAFE_OFF_FINAL";
    case H6_STATE_COMPLETE:
        return "COMPLETE";
    default:
        return "UNKNOWN";
    }
}

const char *h6_stop_reason_name(h6_stop_reason_t reason)
{
    switch (reason) {
    case H6_STOP_NONE:
        return "NONE";
    case H6_STOP_TIMEOUT:
        return "TIMEOUT";
    case H6_STOP_OPERATOR:
        return "OPERATOR_STOP";
    case H6_STOP_TELEMETRY_INVALID:
        return "TELEMETRY_INVALID";
    case H6_STOP_FAULT:
        return "FAULT";
    default:
        return "UNKNOWN";
    }
}
