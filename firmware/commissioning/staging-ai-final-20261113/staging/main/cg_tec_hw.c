/*
 * ColdGuard firmware - as-built TEC hardware adapter (W04).
 *
 * This adapter is deliberately incapable of energizing the branch:
 *
 *   - any request that would set an enable or a non-zero duty is refused and
 *     the W03 safe state is re-forced; the request returns false, so the
 *     controller rolls back and latches a fault;
 *   - the output stage is reported unavailable unless
 *     CG_TEC_OUTPUT_STAGE_ENABLED is 1 (and the configuration guard then also
 *     requires CG_ACTUATOR_ENABLE_ALLOWED and the recorded hardware gates);
 *   - no fan output is wired to a controller GPIO on the as-built assembly,
 *     so the fan is reported not commandable (PHY-TH-001);
 *   - no hardware interlock is wired, so the interlock reads open (fail
 *     closed).
 *
 * Enabling the branch therefore requires new, reviewed hardware and a new
 * adapter - not a one-line macro flip. cg_actuator_force_off() remains the
 * only function that touches an actuator pin, and it only writes 0.
 */
#include "cg_tec_platform.h"

#include "cg_actuator.h"
#include "coldguard_config.h"

static bool hw_set_enables(bool ren, bool len)
{
    if (ren || len) {
        cg_actuator_force_off(); /* roll back immediately */
        return false;
    }
    cg_actuator_force_off();
    return true;
}

static bool hw_set_cooling_duty(uint32_t permille)
{
    if (permille != 0U) {
        cg_actuator_force_off();
        return false;
    }
    return true;
}

static bool hw_set_fan(bool on)
{
    (void)on;
    return false; /* no controllable fan output in the as-built wiring */
}

static bool hw_read_interlock(void)
{
    return false; /* no interlock contact is wired; fail closed */
}

static bool hw_output_stage_available(void)
{
#if CG_TEC_OUTPUT_STAGE_ENABLED == 1
    return true;
#else
    return false;
#endif
}

static bool hw_fan_available(void)
{
    return false;
}

static const cg_tec_hw_ops_t s_ops = {
    .set_enables = hw_set_enables,
    .set_cooling_duty = hw_set_cooling_duty,
    .set_fan = hw_set_fan,
    .read_interlock = hw_read_interlock,
    .output_stage_available = hw_output_stage_available,
    .fan_available = hw_fan_available,
};

const cg_tec_hw_ops_t *cg_tec_hw_ops(void)
{
    return &s_ops;
}
