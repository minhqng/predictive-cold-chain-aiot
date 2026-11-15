/*
 * Host harness for the Leader TEC hardware adapter, Leader-owned.
 *
 * Links the REAL, unchanged member control core (cg_tec_control.c +
 * cg_tec_limits.c), the REAL member stub (cg_tec_hw.c) and the REAL leader
 * adapter (cg_leader_tec_hw.c) with the real member safe-state module
 * (cg_actuator.c) against a recording host mock of the GPIO/LEDC drivers
 * (hw_host.c + mocks/). The ops interposition is expressed with the exact
 * GNU --wrap rename pair (__wrap_cg_tec_hw_ops / __real_cg_tec_hw_ops) also
 * used on target; on GCC builds the rename doubles as the true linker wrap.
 *
 * Build variants (exactly one -D per binary):
 *   CGH_VARIANT_DEFAULT         shipped configuration: adapter off,
 *                               passthrough keeps the stub refuse-all.
 *   CGH_VARIANT_ACTIVE_UNSIGNED adapter on but member gates unsigned,
 *                               no interlock installed: still fail closed.
 *   CGH_VARIANT_ACTIVE_SIGNED   commissioning-shaped configuration with a
 *                               signed gates record, a configured U6 sense
 *                               input and the recorded continuous fan.
 *
 * Exit code: 0 when every scenario passes, 1 otherwise.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "coldguard_config.h"

#include "cg_tec_control.h"
#include "cg_tec_limits.h"
#include "cg_tec_platform.h"
#include "cg_actuator.h"
#include "cg_leader_tec_hw.h"

#if defined(CGH_VARIANT_DEFAULT)
#define CGH_VARIANT_NAME "default"
#elif defined(CGH_VARIANT_ACTIVE_UNSIGNED)
#define CGH_VARIANT_NAME "active-unsigned"
#elif defined(CGH_VARIANT_ACTIVE_SIGNED)
#define CGH_VARIANT_NAME "active-signed"
#elif defined(CGH_VARIANT_ACTIVE_SIGNED_NOILOCK)
#define CGH_VARIANT_NAME "active-signed-noilock"
#elif defined(CGH_VARIANT_ACTIVE_SIGNED_NOCOLD)
#define CGH_VARIANT_NAME "active-signed-nocold"
#elif defined(CGH_VARIANT_ACTIVE_SIGNED_NOCOLD_1000)
#define CGH_VARIANT_NAME "active-signed-nocold-1000"
#elif defined(CGH_VARIANT_ACTIVE_UNSIGNED_NOCOLD)
#define CGH_VARIANT_NAME "active-unsigned-nocold"
#else
#error "exactly one CGH_VARIANT_* must be defined"
#endif

#ifndef CGH_INTERLOCK_PIN
#define CGH_INTERLOCK_PIN CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN
#endif

static int g_checks;
static int g_failures;

static void check(bool cond, const char *what)
{
    g_checks++;
    if (!cond) {
        g_failures++;
        printf("FAIL [%s] %s\n", CGH_VARIANT_NAME, what);
    }
}

static uint32_t forced_off(void)
{
    return cg_actuator_forced_off_count();
}

/* Fill one observation set at time now_ms with fresh valid values. */
static void fill_inputs(cg_tec_inputs_t *in, uint64_t now_ms)
{
    in->now_ms = now_ms;
    in->thermal_observed = true;
    in->thermal_valid = true;
    in->thermal_obs_ms = now_ms - 100U;
    in->t_cold_side_valid = true;
    in->t_cold_side_c = 24.9f;
    in->t_hot_side_valid = true;
    in->t_hot_side_c = 45.2f;
    in->power_observed = true;
    in->power_valid = true;
    in->power_obs_ms = now_ms - 100U;
    in->voltage_v = 12.0f;
    in->current_a = 0.0f;
    in->door_observed = true;
    in->door_open = false;
    in->door_obs_ms = now_ms - 100U;
}

/* Limit table with HARNESS TEST numbers, not hardware claims: they only
 * exercise the resolution/limit mechanics of the member control core. */
static void fill_limits(cg_tec_limit_table_t *t)
{
    static const cg_limit_t entries[CG_LIMIT_COUNT] = {
        { CG_LIMIT_CURRENT_MAX_A, "CUR_MAX", "A", CG_LIMIT_RESOLVED, 15.0f, "HARNESS-TEST" },
        { CG_LIMIT_VOLTAGE_MAX_V, "V_MAX", "V", CG_LIMIT_RESOLVED, 13.0f, "HARNESS-TEST" },
        { CG_LIMIT_VOLTAGE_MIN_V, "V_MIN", "V", CG_LIMIT_RESOLVED, 10.0f, "HARNESS-TEST" },
        { CG_LIMIT_HOT_SIDE_MAX_C, "HOT_MAX", "C", CG_LIMIT_RESOLVED, 70.0f, "HARNESS-TEST" },
        { CG_LIMIT_DUTY_MAX_PERMILLE, "DUTY_MAX", "permille", CG_LIMIT_RESOLVED, 1000.0f, "HARNESS-TEST" },
        { CG_LIMIT_ON_TIME_MAX_MS, "ON_MAX", "ms", CG_LIMIT_RESOLVED, 5000.0f, "HARNESS-TEST" },
    };
    for (size_t i = 0; i < CG_LIMIT_COUNT; i++) {
        t->entry[i] = entries[i];
    }
}

static cg_tec_limit_table_t s_limits;

static void make_ctl(cg_tec_control_t *ctl)
{
    cg_tec_control_init(ctl, cg_tec_limits_all_resolved(&s_limits) ? &s_limits : &s_limits,
                        cg_tec_hw_ops(), "GO12345",
                        100000U, 5000U, 500U, 300U, 2000U, 2000U);
}

#if defined(CGH_VARIANT_DEFAULT)
static void scenario_default_passthrough(void)
{
    const cg_tec_hw_ops_t *ops = cg_tec_hw_ops();

    check(ops->output_stage_available() == false, "stub reports stage unavailable");
    check(ops->fan_available() == false, "stub reports no commandable fan");
    check(ops->read_interlock() == false, "stub reports interlock open");
    check(ops->set_enables(true, false) == false, "stub refuses enable");
    check(cg_actuator_forced_off_count() > 0U, "stub force-off on refused enable");
    check(ops->set_cooling_duty(500U) == false, "stub refuses non-zero duty");
    check(ops->set_cooling_duty(0U) == true, "stub accepts zero duty");
    check(ops->set_fan(true) == false, "stub refuses fan");
}

static void scenario_default_controller_fail_closed(void)
{
    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;

    make_ctl(&ctl);
    fill_inputs(&in, 100000U);

    check(cg_tec_arm(&ctl, "WRONG", 100000U) == false, "wrong ARM token refused");
    check(cg_tec_arm(&ctl, "GO12345", 100000U) == true, "ARM accepted");
    check(cg_tec_start(&ctl, &in, 600U, 400U) == CG_TEC_START_STAGE_UNAVAILABLE,
          "start refused: shipped build has no output stage");
    cg_tec_get_status(&ctl, &st);
    /* The refused START does not consume the ARM: the machine truthfully
     * reports ARMED with outputs never energized. */
    check(st.state == CG_TEC_STATE_ARMED, "state reported ARMED after refused start");
    check(st.outputs_energized == false, "outputs never energized");
    check(hw_host_gpio_output_level(6) == 0 || hw_host_gpio_output_level(6) == -1,
          "R_EN never driven high");
    check(hw_host_ledc_last_duty() == 0U || hw_host_ledc_duty_writes() == 0U,
          "no duty written in shipped build");
    check(cg_tec_is_armed(&ctl, 100500U) == true, "ARM survives the refusal");
}
#endif

#if defined(CGH_VARIANT_ACTIVE_UNSIGNED)
static void scenario_unsigned_gates_fail_closed(void)
{
    const cg_tec_hw_ops_t *ops = cg_tec_hw_ops();

    /* Adapter IS active (next variant proves the managed path), but the
     * member commissioning gates are not signed and no U6 is installed:
     * every energizing request must still fail closed. */
    check(ops->output_stage_available() == false, "unsigned gates: stage unavailable");
    check(ops->read_interlock() == false, "unconfigured U6 pin reads open");
    check(ops->set_enables(true, false) == false, "unsigned gates: enable refused");
    check(hw_host_gpio_output_level(6) == 0, "R_EN left driven low");
    check(ops->set_cooling_duty(500U) == false, "unsigned gates: duty refused");
    check(ops->set_fan(true) == false, "continuous fan not recorded: fan refused");

    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;
    make_ctl(&ctl);
    fill_inputs(&in, 100000U);
    (void)cg_tec_arm(&ctl, "GO12345", 100000U);
    check(cg_tec_start(&ctl, &in, 600U, 400U) == CG_TEC_START_STAGE_UNAVAILABLE,
          "controller refused with unsigned gates");
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_ARMED && st.outputs_energized == false,
          "controller stayed ARMED/unenergized with unsigned gates");
}
#endif

#if defined(CGH_VARIANT_ACTIVE_SIGNED)
static void scenario_interlock_and_gate_admission(void)
{
    const cg_tec_hw_ops_t *ops = cg_tec_hw_ops();
    uint32_t cfg_before;

    hw_host_reset();
    check(ops->output_stage_available() == true, "signed gates: stage available");
    /* Interlock fails closed until the U6 loop closes. The first read also
     * performs the safe-state lazy initialization. */
    check(ops->read_interlock() == false, "open U6 loop reads open");
    hw_host_set_input_level(CGH_INTERLOCK_PIN, 0);
    check(ops->read_interlock() == true, "closed U6 loop reads closed");

    /* Lazy init established the H8 route: both enables are outputs, with
     * pulldown and both low before LEDC is attached. */
    check(hw_host_gpio_pin_mode(6) == GPIO_MODE_OUTPUT,
          "R_EN configured as output");
    check(hw_host_gpio_pin_mode(10) == GPIO_MODE_OUTPUT,
          "L_EN configured as output (not an input)");
    check(hw_host_gpio_output_level(6) == 0, "R_EN low after init");
    check(hw_host_gpio_output_level(10) == 0, "L_EN low after init");

    /* Mixed active request is both-or-nothing: refused, both low. The
     * member force-off configures GPIO5 as a plain output, detaching LEDC. */
    cfg_before = hw_host_ledc_channel_configs();
    check(ops->set_enables(true, false) == false, "mixed R_EN-only request refused");
    check(hw_host_gpio_output_level(6) == 0, "R_EN low after mixed refusal");
    check(hw_host_gpio_output_level(10) == 0, "L_EN low after mixed refusal");
    check(!hw_host_ledc_pad_attached(), "refusal detaches the LEDC pad route");

    /* The next operation must re-run channel config before any duty write. */
    check(ops->set_cooling_duty(0U) == true, "duty 0 accepted after refusal");
    check(hw_host_ledc_channel_configs() > cfg_before,
          "post-refusal operation reconfigures the LEDC channel");
    check(hw_host_ledc_pad_attached(), "LEDC pad route reattached before duty");

    /* Full authorized bring-up sequence. */
    check(ops->set_fan(true) == true, "recorded continuous fan present");
    check(ops->set_enables(true, true) == true, "authorized paired enable accepted");
    check(hw_host_gpio_output_level(6) == 1, "R_EN driven high");
    check(hw_host_gpio_output_level(10) == 1, "L_EN driven high (H8 route)");
    check(hw_host_ledc_last_duty() == 0U, "PWM remains zero when enables rise");
    check(ops->set_cooling_duty(400U) == true, "authorized duty accepted");
    check(hw_host_ledc_last_duty() == 3276U, "duty 400 permille -> 3276/8192 bits");
    check(hw_host_ledc_fhz() == 1000U, "LEDC configured at 1000 Hz (H8)");
    check(hw_host_ledc_resolution_bits() == 13U, "LEDC configured at 13 bit (H8)");
    check(hw_host_ledc_channel_gpio() == 5U, "PWM on GPIO5 (RPWM as-built)");
    check(ops->set_cooling_duty(200U) == true, "200 permille accepted");
    check(hw_host_ledc_last_duty() == 1638U, "duty 200 permille -> 1638/8192 bits");
    check(ops->set_cooling_duty(1000U) == true, "1000 permille accepted");
    check(hw_host_ledc_last_duty() == 8191U, "duty 1000 permille saturates at 8191");

    /* Out-of-range, disabled and interlock-open duty refusals force off. */
    check(ops->set_cooling_duty(1001U) == false, "duty above permille max refused");
    check(ops->set_enables(false, false) == true, "disable accepted");
    check(hw_host_gpio_output_level(6) == 0, "R_EN released");
    check(hw_host_gpio_output_level(10) == 0, "L_EN released");
    check(hw_host_ledc_last_duty() == 0U, "duty zeroed on disable");
    check(ops->set_cooling_duty(400U) == false, "duty with enables off refused");
    hw_host_set_input_level(CGH_INTERLOCK_PIN, 0);
    check(ops->set_enables(true, true) == true, "re-enable accepted");
    check(hw_host_gpio_output_level(10) == 1, "L_EN high on re-enable");
    hw_host_set_input_level(CGH_INTERLOCK_PIN, 1);
    check(ops->set_cooling_duty(200U) == false, "open interlock blocks duty");
    check(hw_host_gpio_output_level(6) == 0, "R_EN force-released on interlock open");
    check(hw_host_gpio_output_level(10) == 0, "L_EN force-released on interlock open");
    check(hw_host_ledc_last_duty() == 0U, "duty force-zeroed on interlock open");
}

static void scenario_controller_full_cycle(void)
{
    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;

    make_ctl(&ctl);
    hw_host_reset();
    hw_host_set_input_level(CGH_INTERLOCK_PIN, 0);
    fill_inputs(&in, 100000U);

    check(cg_tec_arm(&ctl, "WRONGTOK", 100000U) == false, "arm with bad token refused");
    check(cg_tec_is_armed(&ctl, 100050U) == false, "no authorization exists");
    check(cg_tec_arm(&ctl, "GO12345", 100000U) == true, "arm accepted");
    check(cg_tec_is_armed(&ctl, 100100U) == true, "authorization live inside TTL");
    check(cg_tec_is_armed(&ctl, 106000U) == false, "authorization expired by TTL");

    check(cg_tec_arm(&ctl, "GO12345", 106000U) == true, "re-arm after expiry");
    check(cg_tec_start(&ctl, &in, 600U, 450U) == CG_TEC_START_NOT_ARMED,
          "start with the stale (expired) ARM refused");
    check(cg_tec_arm(&ctl, "GO12345", 106000U) == true, "fresh arm for the real run");
    fill_inputs(&in, 106000U);
    check(cg_tec_start(&ctl, &in, 600U, 450U) == CG_TEC_START_OK, "authorized start accepted");
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLING, "state COOLING after start");
    check(st.outputs_energized == true, "outputs_energized true");
    check(st.duty_permille == 450U, "controller tracks requested duty");
    check(hw_host_gpio_output_level(6) == 1, "R_EN high during cooling");
    check(hw_host_ledc_last_duty() == 3686U, "duty 450 permille -> 3686/8192 bits");
    check(cg_tec_arm(&ctl, "GO12345", 106100U) == false, "no re-arm while cooling");

    /* Supervised tick inside the run. */
    fill_inputs(&in, 106200U);
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLING, "tick inside window keeps cooling");
    check(st.elapsed_ms == 200U, "elapsed tracks ticks");

    /* Run deadline reached: bounded duration rolls into cooldown. */
    fill_inputs(&in, 106700U);
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLDOWN, "duration limit entered cooldown");
    check(st.outputs_energized == false, "outputs down in cooldown");
    check(hw_host_gpio_output_level(6) == 0, "R_EN off in cooldown");
    check(hw_host_ledc_last_duty() == 0U, "duty zero in cooldown");

    /* Cooldown window passes: OFF. */
    fill_inputs(&in, 107100U);
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_OFF, "cooldown completed to OFF");
    check(st.start_count == 1U, "one bounded run counted");
}

static void scenario_controller_estop_and_clear(void)
{
    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;

    make_ctl(&ctl);
    hw_host_reset();
    hw_host_set_input_level(CGH_INTERLOCK_PIN, 0);
    fill_inputs(&in, 200000U);
    (void)cg_tec_arm(&ctl, "GO12345", 200000U);
    check(cg_tec_start(&ctl, &in, 4000U, 300U) == CG_TEC_START_OK, "start for estop test");

    in.now_ms = 200100U;
    fill_inputs(&in, 200100U);
    cg_tec_estop(&ctl, 200100U, "ESTOP_TEST");
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_FAULT_LATCH, "estop latched fault");
    check(st.estop_count == 1U, "estop counted");
    check(hw_host_gpio_output_level(6) == 0, "R_EN off after estop");
    check(hw_host_ledc_last_duty() == 0U, "duty zero after estop");

    /* Blocked while latched. */
    check(cg_tec_arm(&ctl, "GO12345", 200150U) == false, "arm blocked while latched");

    /* Clear with a bad token refused. */
    check(cg_tec_clear_fault(&ctl, "BADTOK1", &in) == false, "clear with bad token refused");

    /* Clear with the boot token and healthy inputs returns to cooldown. */
    check(cg_tec_clear_fault(&ctl, "GO12345", &in) == true, "clear accepted");
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLDOWN, "clear moves to cooldown");
    check(cg_tec_is_armed(&ctl, 200200U) == false, "clear does not arm a run");

    in.now_ms = 200450U;
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_OFF, "post-clear countdown reached OFF");
}

static void scenario_heartbeat_gap_fault(void)
{
    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;

    make_ctl(&ctl);
    hw_host_reset();
    hw_host_set_input_level(CGH_INTERLOCK_PIN, 0);
    fill_inputs(&in, 300000U);
    (void)cg_tec_arm(&ctl, "GO12345", 300000U);
    check(cg_tec_start(&ctl, &in, 4000U, 200U) == CG_TEC_START_OK, "start for heartbeat test");

    /* First tick establishes the heartbeat baseline. */
    fill_inputs(&in, 300100U);
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLING, "first tick keeps cooling");

    /* Tick gap beyond the heartbeat timeout must trip the fault and de-
     * energize. */
    fill_inputs(&in, 301000U);
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_FAULT_LATCH, "heartbeat gap latched fault");
    check((st.fault_bits & CG_TEC_FAULT_HEARTBEAT) != 0U, "HEARTBEAT bit set");
    check(st.outputs_energized == false, "outputs down after heartbeat fault");
    check(hw_host_gpio_output_level(6) == 0, "REN low after heartbeat fault");
    check(hw_host_ledc_last_duty() == 0U, "duty zero after heartbeat fault");
}

static void scenario_stale_sensor_fault(void)
{
    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;

    make_ctl(&ctl);
    hw_host_reset();
    hw_host_set_input_level(CGH_INTERLOCK_PIN, 0);
    fill_inputs(&in, 400000U);
    (void)cg_tec_arm(&ctl, "GO12345", 400000U);
    check(cg_tec_start(&ctl, &in, 4000U, 200U) == CG_TEC_START_OK, "start for stale test");

    /* The thermal observation timestamp never advances past the freshness
     * window: the supervisor must trip the sensor gate and de-energize. */
    in.now_ms = 400300U;
    in.thermal_obs_ms = 398000U;
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_FAULT_LATCH, "stale sensors latched fault");
    check(st.outputs_energized == false, "outputs down after stale fault");
    check(hw_host_ledc_last_duty() == 0U, "duty zero after stale fault");
}
#endif

#if defined(CGH_VARIANT_ACTIVE_SIGNED_NOILOCK)
/* The owner's as-built decision (2026-11-13): NO separate U6 interlock
 * exists or will be added. This scenario proves the explicitly configured
 * none-by-design mode end to end: the member admission chain runs to a real
 * authorized cooling cycle with NO pin configured and NO input driven, and
 * every independent protection (gates, paired enables, bounded duration,
 * e-stop latch) still owns the plant. This is a recorded commissioning
 * decision, never a simulated contact: the build manifest and the dashboard
 * report "interlock: NOT FITTED". */
static void scenario_no_interlock_by_design(void)
{
    const cg_tec_hw_ops_t *ops = cg_tec_hw_ops();
    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;

    hw_host_reset();
    check(ops->output_stage_available() == true, "noilock: stage available");
    check(CGH_INTERLOCK_PIN < 0, "noilock: build has no interlock pin");
    check(ops->read_interlock() == true,
          "noilock: the recorded none-by-design mode reports permitted with no pin");

    /* Full authorized lifecycle through the REAL member controller. */
    make_ctl(&ctl);
    fill_inputs(&in, 200000U);
    check(cg_tec_arm(&ctl, "GO12345", 200000U) == true, "noilock: arm accepted");
    fill_inputs(&in, 200100U);
    check(cg_tec_start(&ctl, &in, 500U, 300U) == CG_TEC_START_OK,
          "noilock: authorized start admitted without a physical loop");
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLING, "noilock: state cooling");
    check(st.outputs_energized == true, "noilock: outputs energized");
    check(hw_host_gpio_output_level(6) == 1, "noilock: R_EN high");
    check(hw_host_gpio_output_level(10) == 1, "noilock: L_EN high (H8 route)");
    check(hw_host_ledc_last_duty() == 2457U, "noilock: duty 300 permille -> 2457/8192");
    check(hw_host_ledc_channel_gpio() == 5U, "noilock: PWM on GPIO5");

    /* The independent protections still own the plant mid-run. */
    check(ops->set_enables(true, false) == false, "noilock: mixed enable still refused");
    check(ops->set_enables(true, true) == true, "noilock: paired enable accepted");
    check(ops->set_cooling_duty(1001U) == false, "noilock: out-of-range duty refused");

    /* E-stop kills a live run and latches the fault. */
    fill_inputs(&in, 200200U);
    cg_tec_estop(&ctl, 200200U, "ESTOP_NOILOCK");
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_FAULT_LATCH, "noilock: estop latched");
    check(hw_host_gpio_output_level(6) == 0, "noilock: R_EN off after estop");
    check(hw_host_ledc_last_duty() == 0U, "noilock: duty zero after estop");

    /* Bounded-duration path still rolls to cooldown and OFF: clear, let the
     * cooldown elapse, then a second authorized run. */
    check(cg_tec_clear_fault(&ctl, "GO12345", &in) == true, "noilock: clear accepted");
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLDOWN, "noilock: clear moves to cooldown");
    fill_inputs(&in, 200600U);
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_OFF, "noilock: cooldown completed to OFF");
    check(cg_tec_arm(&ctl, "GO12345", 200600U) == true, "noilock: re-arm after clear");
    fill_inputs(&in, 200600U);
    check(cg_tec_start(&ctl, &in, 400U, 200U) == CG_TEC_START_OK,
          "noilock: second bounded run admitted");
    fill_inputs(&in, 201100U);
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLDOWN, "noilock: duration limit cooled down");
    check(hw_host_gpio_output_level(6) == 0, "noilock: R_EN off in cooldown");
    fill_inputs(&in, 201500U);
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_OFF, "noilock: second run completed to OFF");
}
#endif

#if defined(CGH_VARIANT_ACTIVE_SIGNED_NOCOLD_1000)
/* Explicit TEC1000 full-duty attended demo: 1000 permille, 10.0 A stop,
 * same 40 C/voltage/duration/estop chain. The adapter saturates the 13-bit
 * PWM at 8191/8192; the 10.0 A boundary is strict ">" in the member core. */
static void scenario_full_duty_1000_profile(void)
{
    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;

    hw_host_reset();
    make_ctl(&ctl);
    check(cg_leader_tec_cold_probe_required() == false,
          "tec1000: actual controller policy keeps cold probe waived");
    check(cg_tec_cold_side_required(&ctl) == false,
          "tec1000: member controller records the selected policy");
    check(cg_leader_tec_continuous_allowed() == true,
          "tec1000: continuous policy reported allowed");
    check(ctl.continuous_allowed == true,
          "tec1000: member controller received the continuous policy");
    check(ctl.ai_demo_allowed == true,
          "tec1000: member controller received the AI-demo policy");

    fill_inputs(&in, 100000U);
    in.t_cold_side_valid = false;
    in.t_hot_side_c = 30.0f;
    check(cg_tec_arm(&ctl, "GO12345", 100000U) == true, "tec1000: arm accepted");
    check(cg_tec_start(&ctl, &in, 0U, 1000U) == CG_TEC_START_BAD_DURATION,
          "tec1000: bare START 0 refused without a lease");
    check(cg_tec_ai_demo_start(&ctl, &in, 1000U, 3000U, 1U) == CG_TEC_START_OK,
          "tec1000: lease-bound AISTART admitted");
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLING, "tec1000: cooling");
    check(st.continuous == true, "tec1000: continuous mode reported");
    check(st.remaining_ms == 0U, "tec1000: no fake remaining deadline");
    check(st.duty_permille == 1000U, "tec1000: controller tracks 1000 permille");
    check(hw_host_gpio_output_level(6) == 1, "tec1000: R_EN high");
    check(hw_host_gpio_output_level(10) == 1, "tec1000: L_EN high (H8 route)");
    check(hw_host_ledc_last_duty() == 8191U, "tec1000: duty saturates at 8191/8192");

    /* No 30 s auto-stop: beyond 31 s and 60 s the run is still controlled.
     * Ticks stay inside the 500 ms heartbeat window (the guard itself is
     * unchanged); only the run deadline is absent. */
    {
        uint32_t seq = 2U;
        for (uint64_t t = 100500U; t <= 161000U; t += 400U) {
            fill_inputs(&in, t);
            in.t_hot_side_c = 30.0f;
            if (t % 2000U == 500U) {
                check(cg_tec_ai_demo_update(&ctl, &in, 1000U, 3000U, seq++),
                      "tec1000: bounded AILEASE renewal accepted");
            }
            cg_tec_tick(&ctl, &in);
        }
    }
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLING, "tec1000: still cooling after 61 s");
    check(st.continuous == true, "tec1000: continuous survives healthy ticks");
    check(st.elapsed_ms >= 60000U, "tec1000: elapsed passes 60 s");

    /* Exactly 10.0 A is still inside the member core's strict ">" trip. */
    fill_inputs(&in, 161100U);
    in.t_hot_side_c = 30.0f;
    in.current_a = 10.0f;
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLING, "tec1000: 10.0 A does not trip");
    check(st.outputs_energized == true, "tec1000: still energized at 10.0 A");

    /* Any value above the supervisory stop trips and de-energizes. */
    fill_inputs(&in, 161200U);
    in.t_hot_side_c = 30.0f;
    in.current_a = 10.01f;
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_FAULT_LATCH, "tec1000: 10.01 A latched fault");
    check(st.continuous == false, "tec1000: fault cleared continuous state");
    check((st.fault_bits & CG_TEC_FAULT_OVERCURRENT) != 0U,
          "tec1000: OVERCURRENT bit set");
    check(hw_host_gpio_output_level(6) == 0, "tec1000: R_EN off after overcurrent");
    check(hw_host_ledc_last_duty() == 0U, "tec1000: duty zero after overcurrent");

    /* The 40 C T2 stop is unchanged at full duty. */
    fill_inputs(&in, 161300U);
    in.t_hot_side_c = 30.0f;
    check(cg_tec_clear_fault(&ctl, "GO12345", &in) == true, "tec1000: clear accepted");
    cg_tec_tick(&ctl, &in);
    fill_inputs(&in, 161600U);
    in.t_hot_side_c = 30.0f;
    cg_tec_tick(&ctl, &in);
    check(cg_tec_arm(&ctl, "GO12345", 161600U) == true, "tec1000: re-arm");
    check(cg_tec_ai_demo_start(&ctl, &in, 1000U, 3000U, 200U) == CG_TEC_START_OK,
          "tec1000: second lease-bound run admitted");
    fill_inputs(&in, 161700U);
    in.t_hot_side_c = 40.1f;
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_FAULT_LATCH, "tec1000: 40.1 C latched");
    check((st.fault_bits & CG_TEC_FAULT_OVERTEMP) != 0U,
          "tec1000: OVERTEMP bit set");
    check(hw_host_ledc_last_duty() == 0U, "tec1000: duty zero after T2 stop");
}
#endif

#if defined(CGH_VARIANT_ACTIVE_UNSIGNED_NOCOLD)
/* Negative public-profile combination: flag present, signed gates absent.
 * The cold-probe policy must stay REQUIRED and every start must refuse. */
static void scenario_unsigned_no_cold_flag_refused(void)
{
    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;

    hw_host_reset();
    make_ctl(&ctl);
    check(cg_leader_tec_cold_probe_required() == true,
          "unsigned nocold: actual policy keeps the cold probe required");
    check(cg_tec_cold_side_required(&ctl) == true,
          "unsigned nocold: member controller keeps cold-side required");
    fill_inputs(&in, 100000U);
    in.t_cold_side_valid = false;
    (void)cg_tec_arm(&ctl, "GO12345", 100000U);
    check(cg_tec_start(&ctl, &in, 30000U, 200U) == CG_TEC_START_STAGE_UNAVAILABLE,
          "unsigned nocold: staged output stage stays unavailable");
    cg_tec_get_status(&ctl, &st);
    check(st.outputs_energized == false, "unsigned nocold: never energized");
    check(hw_host_ledc_last_duty() == 0U, "unsigned nocold: PWM remains zero");
}
#endif

#if defined(CGH_VARIANT_ACTIVE_SIGNED_NOCOLD)
/* SUPERVISED_NO_COLD_PROBE: the wrapper clears the member controller's
 * policy only because all three recorded selections are present and the
 * first-step duty is exactly 200. The real controller then admits a run
 * with the cold flag false and a real T2 hot input, while the 40 C stop
 * still de-energizes it. */
static void scenario_no_cold_probe_profile(void)
{
    cg_tec_control_t ctl;
    cg_tec_inputs_t in;
    cg_tec_status_t st;

    hw_host_reset();
    make_ctl(&ctl);
    check(cg_leader_tec_cold_probe_required() == false,
          "nocold: actual controller policy exposed as not requiring a cold probe");
    check(cg_tec_cold_side_required(&ctl) == false,
          "nocold: member controller records the selected policy");

    fill_inputs(&in, 100000U);
    in.t_cold_side_valid = false;
    in.t_cold_side_c = 0.0f;
    in.t_hot_side_c = 30.0f;
    check(cg_tec_arm(&ctl, "GO12345", 100000U) == true, "nocold: arm accepted");
    check(cg_leader_tec_continuous_allowed() == false,
          "nocold: TEC200 has no continuous policy");
    check(cg_tec_start(&ctl, &in, 0U, 200U) == CG_TEC_START_BAD_DURATION,
          "nocold: timed TEC200 still refuses START 0");
    check(cg_tec_start(&ctl, &in, 30000U, 200U) == CG_TEC_START_OK,
          "nocold: start admitted without a cold probe on the real T2 hot input");
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_COOLING, "nocold: cooling");
    check(st.outputs_energized == true, "nocold: outputs energized");
    check(hw_host_gpio_output_level(6) == 1, "nocold: R_EN high");
    check(hw_host_ledc_last_duty() == 1638U, "nocold: duty 200 permille -> 1638/8192");

    /* The hot-side stop is unchanged. */
    in.now_ms = 100100U;
    in.thermal_obs_ms = 100000U;
    in.t_hot_side_c = 40.1f;
    cg_tec_tick(&ctl, &in);
    cg_tec_get_status(&ctl, &st);
    check(st.state == CG_TEC_STATE_FAULT_LATCH, "nocold: 40 C stop still latched");
    check((st.fault_bits & CG_TEC_FAULT_OVERTEMP) != 0U, "nocold: OVERTEMP bit set");
    check(st.outputs_energized == false, "nocold: outputs down after 40 C stop");
    check(hw_host_ledc_last_duty() == 0U, "nocold: duty zero after 40 C stop");

    /* A missing hot channel is still refused after a clear. */
    fill_inputs(&in, 100200U);
    in.t_cold_side_valid = false;
    in.t_hot_side_valid = false;
    check(cg_tec_clear_fault(&ctl, "GO12345", &in) == false,
          "nocold: clear still refuses a missing hot channel");
}
#endif

int main(void)
{
    int base_failures;
    const uint32_t boot_forced = forced_off() > 0U ? forced_off() : 0U;

    fill_limits(&s_limits);
    check(cg_tec_limits_all_resolved(&s_limits) == true, "harness limit table resolved");
    check(forced_off() >= 0U && hw_host_gpio_config_count() >= 0, "harness host alive");

    base_failures = g_failures;
#if defined(CGH_VARIANT_DEFAULT)
    scenario_default_passthrough();
    scenario_default_controller_fail_closed();
#elif defined(CGH_VARIANT_ACTIVE_UNSIGNED)
    scenario_unsigned_gates_fail_closed();
#elif defined(CGH_VARIANT_ACTIVE_SIGNED)
    scenario_interlock_and_gate_admission();
    scenario_controller_full_cycle();
    scenario_controller_estop_and_clear();
    scenario_heartbeat_gap_fault();
    scenario_stale_sensor_fault();
#elif defined(CGH_VARIANT_ACTIVE_SIGNED_NOILOCK)
    scenario_no_interlock_by_design();
#elif defined(CGH_VARIANT_ACTIVE_SIGNED_NOCOLD)
    scenario_no_cold_probe_profile();
#elif defined(CGH_VARIANT_ACTIVE_SIGNED_NOCOLD_1000)
    scenario_full_duty_1000_profile();
#elif defined(CGH_VARIANT_ACTIVE_UNSIGNED_NOCOLD)
    scenario_unsigned_no_cold_flag_refused();
#endif
    (void)boot_forced;
    (void)base_failures;

    if (g_failures == 0) {
        printf("LEADER TEC ADAPTER HARNESS [%s]: ALL %d CHECKS PASS\n",
               CGH_VARIANT_NAME, g_checks);
        return 0;
    }
    printf("LEADER TEC ADAPTER HARNESS [%s]: %d of %d checks FAILED\n",
           CGH_VARIANT_NAME, g_failures, g_checks);
    return 1;
}
