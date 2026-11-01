/*
 * ColdGuard firmware - TEC hardware boundary (W04).
 *
 * The control state machine is pure C and never touches a pin. Everything
 * that can change the physical world is behind this tiny interface, which
 * lets the same controller run against:
 *
 *   - the as-built adapter (cg_tec_hw.c): every request that would energize
 *     the branch is refused and re-forced into the W03 safe state;
 *   - a recording fake in the offline harness, which proves the ordering,
 *     the rollback and the "never both enables / never reverse" invariants.
 *
 * Contract:
 *   - set_enables(ren, len) is the only path that can enable a half-bridge.
 *     The controller only ever calls (true, false) or (false, false).
 *   - set_cooling_duty is the only path that can drive the cooling PWM.
 *   - There is no reverse function at all: LPWM is tied to GND on the
 *     as-built module and the firmware has no code to drive it.
 *   - Every function returns false when the request was refused or failed;
 *     the controller treats false as a fault and rolls back.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool (*set_enables)(bool ren, bool len);
    bool (*set_cooling_duty)(uint32_t permille);
    bool (*set_fan)(bool on);
    bool (*read_interlock)(void);      /* true = closed/permitted */
    bool (*output_stage_available)(void);
    bool (*fan_available)(void);
} cg_tec_hw_ops_t;

/* The as-built adapter. All functions are safe to call at any time. */
const cg_tec_hw_ops_t *cg_tec_hw_ops(void);
