/*
 * ColdGuard firmware - boot/default safety state (Member A, W02).
 *
 * docs/01 section 11.8: at reset and boot the edge controller must not
 * intentionally energize the cooling branch before GPIO mode, safety
 * state and actuator policy are initialized. W02 has no cooling control
 * yet, so the honest implementation is to force the IBT-2 inputs to
 * their inactive level as the very first action of app_main and to say
 * so on the serial log.
 */
#pragma once

void cg_safety_force_actuator_off(void);
