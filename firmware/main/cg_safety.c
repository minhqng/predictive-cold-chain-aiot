/*
 * ColdGuard firmware - boot/default safety state (Member A, W02/W03).
 *
 * docs/01 section 11.8: at reset and boot the edge controller must not
 * intentionally energize the cooling branch before GPIO mode, safety state
 * and actuator policy are initialized. W03 keeps the same boot invariant as
 * W02 - force the IBT-2 inputs to their inactive level as the very first
 * action of app_main - and now delegates the pin work to the dedicated
 * safe-state module (cg_actuator.c). There is no path in this firmware that
 * can turn the branch on.
 */
#include "cg_safety.h"

#include "coldguard_config.h"
#include "cg_actuator.h"
#include "cg_log.h"

void cg_safety_force_actuator_off(void)
{
    cg_actuator_force_off();
    cg_log_safety_actuator_off();
}
