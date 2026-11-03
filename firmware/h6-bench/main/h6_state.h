/*
 * ColdGuard H6 - test state machine (pure C, no ESP-IDF dependency).
 *
 * The host test in tools/host_test_h6_state.c exercises every transition and
 * the 60 s boundary, so this file must stay free of platform headers.
 *
 *   BOOT -> SAFE_OFF -> WAIT_FOR_MANUAL_ARM -> ARMED -> RUNNING_10_PERCENT
 *                                                          |
 *                                                          v
 *                                                 SAFE_OFF_FINAL -> COMPLETE
 *
 * One run per boot: h6_sm_start() latches run_consumed and never clears it.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    H6_STATE_BOOT = 0,
    H6_STATE_SAFE_OFF,
    H6_STATE_WAIT_FOR_MANUAL_ARM,
    H6_STATE_ARMED,
    H6_STATE_RUNNING_10_PERCENT,
    H6_STATE_SAFE_OFF_FINAL,
    H6_STATE_COMPLETE,
} h6_state_t;

typedef enum {
    H6_STOP_NONE = 0,
    H6_STOP_TIMEOUT,
    H6_STOP_OPERATOR,
    H6_STOP_TELEMETRY_INVALID,
    H6_STOP_FAULT,
} h6_stop_reason_t;

typedef struct {
    h6_state_t state;
    h6_stop_reason_t stop_reason;
    int64_t run_start_us;
    int64_t run_stop_us;
    bool run_consumed;
} h6_sm_t;

void h6_sm_init(h6_sm_t *sm);

/* BOOT -> SAFE_OFF, and SAFE_OFF -> WAIT_FOR_MANUAL_ARM. */
bool h6_sm_safe_off(h6_sm_t *sm);
bool h6_sm_ready(h6_sm_t *sm);

/* WAIT_FOR_MANUAL_ARM -> ARMED. */
bool h6_sm_arm(h6_sm_t *sm);

/* ARMED -> RUNNING_10_PERCENT. Only once per boot. */
bool h6_sm_start(h6_sm_t *sm, int64_t now_us);

/* RUNNING_10_PERCENT -> SAFE_OFF_FINAL. Rejected in any other state, so a
 * late caller cannot overwrite the first stop reason. */
bool h6_sm_stop(h6_sm_t *sm, h6_stop_reason_t reason, int64_t now_us);

/* SAFE_OFF_FINAL -> COMPLETE. */
bool h6_sm_complete(h6_sm_t *sm);

/* True only while RUNNING and elapsed >= H6_MAX_ON_US. */
bool h6_sm_deadline_reached(const h6_sm_t *sm, int64_t now_us);

/* 0 outside a run; now-start while running; stop-start afterwards. */
int64_t h6_sm_elapsed_us(const h6_sm_t *sm, int64_t now_us);

const char *h6_state_name(h6_state_t state);
const char *h6_stop_reason_name(h6_stop_reason_t reason);
