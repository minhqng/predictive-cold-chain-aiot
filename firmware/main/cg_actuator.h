/*
 * ColdGuard firmware - IBT-2/BTS7960 safe-state module (Member A, W03).
 *
 * W03 scope is logic only (A-W03-07 / docs/01 section 12.6, gate H4):
 *
 *   - the cooling branch inputs are forced OFF at boot/reset and stay OFF;
 *   - the firmware generates no PWM at all in W03 (no LEDC/MCPWM peripheral
 *     is configured), so it cannot command the module even by accident;
 *   - the predicate below is the invariant the future PWM layer (W04+) must
 *     satisfy before it may drive an output: a real operator authorization
 *     AND at most one direction carrying non-zero duty. With
 *     CG_ACTUATOR_ENABLE_ALLOWED at 0 it refuses everything, so a stray call
 *     in W03 cannot energize the branch.
 *
 * The module header (photo 14-ibt2-actual.jpg) exposes VCC, GND, R_IS,
 * L_IS, R_EN, L_EN, RPWM, LPWM. The as-built wiring drives RPWM and a
 * shared enable (pin map v1); the remaining inputs are a hardware tie-off
 * decision that Member D owns. See evidence/A/W03/ibt2-pin-map.md.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* Duty scale used by the future PWM layer: 0..1000 (permille). */
#define CG_ACTUATOR_DUTY_MAX 1000U

/* Drives every firmware-controlled IBT-2 input to its inactive level and
 * configures the pins as outputs. Idempotent; safe to call from any
 * boot/error path. This is the only function in the firmware that may
 * change an actuator pin. */
void cg_actuator_force_off(void);

/* True only when a future layer may drive outputs. Refused when:
 *   - a duty is out of range,
 *   - both directions carry non-zero duty (opposing PWM),
 *   - no operator authorization is present,
 *   - outputs are compile-time disabled (W03: CG_ACTUATOR_ENABLE_ALLOWED=0). */
bool cg_actuator_outputs_allowed(bool operator_authorized, uint32_t rpwm_duty,
                                 uint32_t lpwm_duty);

/* True while the branch is in the forced-off state. */
bool cg_actuator_is_off(void);

/* Number of times the safe state was (re)established - boot count included,
 * so a bench log can show the invariant was applied on every run. */
uint32_t cg_actuator_forced_off_count(void);
