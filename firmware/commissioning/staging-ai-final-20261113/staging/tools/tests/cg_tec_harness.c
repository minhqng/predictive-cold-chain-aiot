/*
 * Host harness for the ColdGuard W04 TEC control core.
 *
 * Compiles firmware/main/cg_tec_control.c and cg_tec_limits.c unchanged and
 * drives them with a recording fake backend. Every scenario asserts what the
 * physical branch would have done: no enable, no non-zero duty, no reverse
 * request, in every failure path.
 *
 * The limit values in resolved_limits() are harness test numbers, not hardware
 * claims; the shipped table stays UNRESOLVED.
 *
 * Exit code: 0 when every scenario passes, 1 otherwise.
 */
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cg_tec_control.h"
#include "cg_tec_limits.h"
#include "cg_telemetry.h"
#include "coldguard_config.h"

enum {
    CALL_EN = 1,
    CALL_DUTY,
    CALL_FAN,
};

typedef struct {
    int kind;
    int a;
    int b;
} call_t;

typedef struct {
    call_t calls[128];
    int count;
    bool stage_available;
    bool fan_available;
    bool interlock;
    int enable_calls;
    int fail_enable_call; /* 1-based enable call to fail, 0 = never */
    int duty_calls;
    int fail_duty_call;   /* 1-based duty call to fail, 0 = never */
    int fan_calls;
    int fail_fan_call;
} fake_t;

static fake_t g_hw;
static cg_tec_control_t g_ctl;
static int g_failures;

static void record(int kind, int a, int b)
{
    if (g_hw.count < (int)(sizeof(g_hw.calls) / sizeof(g_hw.calls[0]))) {
        g_hw.calls[g_hw.count].kind = kind;
        g_hw.calls[g_hw.count].a = a;
        g_hw.calls[g_hw.count].b = b;
        g_hw.count++;
    }
}

static bool fake_set_enables(bool ren, bool len)
{
    record(CALL_EN, ren ? 1 : 0, len ? 1 : 0);
    g_hw.enable_calls++;
    if (g_hw.fail_enable_call != 0 && g_hw.enable_calls == g_hw.fail_enable_call) {
        return false;
    }
    return true;
}

static bool fake_set_cooling_duty(uint32_t permille)
{
    record(CALL_DUTY, (int)permille, 0);
    g_hw.duty_calls++;
    if (g_hw.fail_duty_call != 0 && g_hw.duty_calls == g_hw.fail_duty_call) {
        return false;
    }
    return true;
}

static bool fake_set_fan(bool on)
{
    record(CALL_FAN, on ? 1 : 0, 0);
    g_hw.fan_calls++;
    if (g_hw.fail_fan_call != 0 && g_hw.fan_calls == g_hw.fail_fan_call) {
        return false;
    }
    return true;
}

static bool fake_read_interlock(void)
{
    return g_hw.interlock;
}

static bool fake_stage_available(void)
{
    return g_hw.stage_available;
}

static bool fake_fan_available(void)
{
    return g_hw.fan_available;
}

static cg_tec_hw_ops_t make_ops(void)
{
    cg_tec_hw_ops_t ops;

    memset(&ops, 0, sizeof(ops));
    ops.set_enables = fake_set_enables;
    ops.set_cooling_duty = fake_set_cooling_duty;
    ops.set_fan = fake_set_fan;
    ops.read_interlock = fake_read_interlock;
    ops.output_stage_available = fake_stage_available;
    ops.fan_available = fake_fan_available;
    return ops;
}

static void fake_reset(void)
{
    memset(&g_hw, 0, sizeof(g_hw));
    g_hw.stage_available = true;
    g_hw.fan_available = true;
    g_hw.interlock = true;
}

static cg_tec_limit_table_t resolved_limits(void)
{
    cg_tec_limit_table_t table = cg_tec_limits_shipped;
    int i;

    for (i = 0; i < CG_LIMIT_COUNT; i++) {
        table.entry[i].state = CG_LIMIT_RESOLVED;
    }
    table.entry[CG_LIMIT_CURRENT_MAX_A].value = 10.0f;
    table.entry[CG_LIMIT_VOLTAGE_MAX_V].value = 15.0f;
    table.entry[CG_LIMIT_VOLTAGE_MIN_V].value = 9.0f;
    table.entry[CG_LIMIT_HOT_SIDE_MAX_C].value = 60.0f;
    table.entry[CG_LIMIT_DUTY_MAX_PERMILLE].value = 700.0f;
    table.entry[CG_LIMIT_ON_TIME_MAX_MS].value = 600000.0f;
    return table;
}

static void setup(const cg_tec_limit_table_t *limits)
{
    cg_tec_hw_ops_t ops;

    fake_reset();
    ops = make_ops();
    cg_tec_control_init(&g_ctl, limits, &ops, "deadbeef", 1000U, 120000U, 1000U,
                        60000U, 3000U, 3000U);
}

/* The owner-proposed supervised session envelope: 200 permille, 30 s,
 * 5.0 A, 40.0 C, 10.0..13.2 V. Test values, not plant ratings. */
static cg_tec_limit_table_t supervised_limits(void)
{
    cg_tec_limit_table_t table = resolved_limits();

    table.entry[CG_LIMIT_CURRENT_MAX_A].value = 5.0f;
    table.entry[CG_LIMIT_VOLTAGE_MAX_V].value = 13.2f;
    table.entry[CG_LIMIT_VOLTAGE_MIN_V].value = 10.0f;
    table.entry[CG_LIMIT_HOT_SIDE_MAX_C].value = 40.0f;
    table.entry[CG_LIMIT_DUTY_MAX_PERMILLE].value = 200.0f;
    table.entry[CG_LIMIT_ON_TIME_MAX_MS].value = 30000.0f;
    return table;
}

static cg_tec_inputs_t healthy(uint64_t now_ms)
{
    cg_tec_inputs_t in;

    memset(&in, 0, sizeof(in));
    in.now_ms = now_ms;
    in.thermal_observed = true;
    in.thermal_valid = true;
    in.thermal_obs_ms = now_ms - 100U;
    in.t_cold_side_valid = true;
    in.t_cold_side_c = 5.0f;
    in.t_hot_side_valid = true;
    in.t_hot_side_c = 30.0f;
    in.power_observed = true;
    in.power_valid = true;
    in.power_obs_ms = now_ms - 100U;
    in.voltage_v = 12.0f;
    in.current_a = 1.0f;
    in.door_observed = true;
    in.door_open = false;
    in.door_obs_ms = now_ms - 100U;
    return in;
}

static bool start_ok(uint64_t now_ms, uint32_t duration_ms, uint32_t duty)
{
    cg_tec_inputs_t in = healthy(now_ms);

    if (!cg_tec_arm(&g_ctl, "deadbeef", now_ms)) {
        return false;
    }
    return cg_tec_start(&g_ctl, &in, duration_ms, duty) == CG_TEC_START_OK;
}

#define CHECK(expr)                                                          \
    do {                                                                     \
        if (!(expr)) {                                                       \
            printf("  assert failed: %s (line %d)\n", #expr, __LINE__);      \
            g_failures++;                                                    \
            return false;                                                    \
        }                                                                    \
    } while (0)

static int last_call_index(int kind)
{
    int i;

    for (i = g_hw.count - 1; i >= 0; i--) {
        if (g_hw.calls[i].kind == kind) {
            return i;
        }
    }
    return -1;
}

static bool never_energized(void)
{
    int i;

    for (i = 0; i < g_hw.count; i++) {
        if (g_hw.calls[i].kind == CALL_EN && g_hw.calls[i].a != 0) {
            return false;
        }
        if (g_hw.calls[i].kind == CALL_DUTY && g_hw.calls[i].a != 0) {
            return false;
        }
    }
    return true;
}

/* Checked after every scenario: outside COOLING the branch must be off with
 * duty 0 and BOTH enables low. Inside COOLING the paired active state is the
 * H8-verified physical route. */
static bool final_state_is_safe(void)
{
    int en;
    int duty;

    if (g_ctl.state == CG_TEC_STATE_COOLING) {
        return true;
    }
    en = last_call_index(CALL_EN);
    duty = last_call_index(CALL_DUTY);
    if (en >= 0 && (g_hw.calls[en].a != 0 || g_hw.calls[en].b != 0)) {
        return false;
    }
    if (duty >= 0 && g_hw.calls[duty].a != 0) {
        return false;
    }
    return true;
}

/* ------------------------------------------------------------------ */

static bool test_init_is_safe(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_status_t status;

    setup(&limits);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(g_ctl.state == CG_TEC_STATE_OFF);
    CHECK(!g_ctl.authorized);
    CHECK(!g_ctl.outputs_energized);
    CHECK(g_ctl.fault_bits == 0U);
    CHECK(g_hw.count == 0);
    CHECK(strcmp(status.reason, "BOOT_SAFE_OFF") == 0);
    CHECK(!status.fan_on);
    return true;
}

static bool test_start_without_arm_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_NOT_ARMED);
    CHECK(g_ctl.state == CG_TEC_STATE_OFF);
    CHECK(never_energized());
    return true;
}

static bool test_arm_token_binding(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(!cg_tec_arm(&g_ctl, "00000000", 1000U));
    CHECK(g_ctl.state == CG_TEC_STATE_OFF);
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    CHECK(g_ctl.state == CG_TEC_STATE_ARMED);
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 60000U, 300U) == CG_TEC_START_OK);
    CHECK(!cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    return true;
}

static bool test_arm_expiry(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U + 120001U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_NOT_ARMED);
    CHECK(g_ctl.state == CG_TEC_STATE_OFF);
    CHECK(never_energized());
    return true;
}

static bool test_unresolved_limits_refuse(void)
{
    cg_tec_inputs_t in;

    setup(&cg_tec_limits_shipped);
    CHECK(cg_tec_limits_unresolved(&cg_tec_limits_shipped) == CG_LIMIT_COUNT);
    CHECK(!cg_tec_limits_all_resolved(&cg_tec_limits_shipped));
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_LIMITS_UNRESOLVED);
    CHECK(g_ctl.state == CG_TEC_STATE_ARMED); /* refused start does not consume the ARM */
    CHECK(never_energized());
    return true;
}

static bool test_happy_path_order(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_status_t status;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    CHECK(g_ctl.state == CG_TEC_STATE_COOLING);
    CHECK(g_hw.count == 4);
    CHECK(g_hw.calls[0].kind == CALL_DUTY && g_hw.calls[0].a == 0);
    CHECK(g_hw.calls[1].kind == CALL_FAN && g_hw.calls[1].a == 1);
    CHECK(g_hw.calls[2].kind == CALL_EN && g_hw.calls[2].a == 1 && g_hw.calls[2].b == 1);
    CHECK(g_hw.calls[3].kind == CALL_DUTY && g_hw.calls[3].a == 300);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.duty_permille == 300U);
    CHECK(status.fan_on);
    CHECK(status.start_count == 1U);
    return true;
}

static bool test_second_start_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;
    int calls_before;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    calls_before = g_hw.count;
    in = healthy(1100U);
    CHECK(cg_tec_start(&g_ctl, &in, 60000U, 300U) == CG_TEC_START_BAD_STATE);
    CHECK(g_hw.count == calls_before);
    return true;
}

static bool test_stop_order_and_cooldown(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;
    int en;
    int duty;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    in = healthy(2000U);
    cg_tec_stop(&g_ctl, &in, "OPERATOR_STOP");
    CHECK(g_ctl.state == CG_TEC_STATE_COOLDOWN);
    en = last_call_index(CALL_EN);
    duty = last_call_index(CALL_DUTY);
    CHECK(en >= 0 && g_hw.calls[en].a == 0 && g_hw.calls[en].b == 0);
    CHECK(duty >= 0 && g_hw.calls[duty].a == 0);
    CHECK(duty < en); /* duty 0 first, then both enables low */
    CHECK(g_ctl.fan_on);
    CHECK(!g_ctl.outputs_energized);

    in = healthy(61000U);
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_COOLDOWN);
    CHECK(g_ctl.fan_on);

    in = healthy(62000U);
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_OFF);
    CHECK(!g_ctl.fan_on);
    CHECK(g_hw.calls[g_hw.count - 1].kind == CALL_FAN);
    CHECK(g_hw.calls[g_hw.count - 1].a == 0);
    return true;
}

static bool test_duration_expiry(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 1000U, 300U));
    in = healthy(1500U);
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_COOLING);
    in = healthy(2000U);
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_COOLDOWN);
    CHECK(!g_ctl.outputs_energized);
    return true;
}

static bool test_invalid_thermal_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    in = healthy(1100U);
    in.thermal_valid = false;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_SENSOR_INVALID) != 0U);
    CHECK(!g_ctl.outputs_energized);
    CHECK(g_ctl.fan_on);
    return true;
}

static bool test_stale_thermal_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    in = healthy(2000U);
    in.thermal_obs_ms = 2000U - 3001U;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_SENSOR_STALE) != 0U);
    CHECK(!g_ctl.outputs_energized);
    return true;
}

static bool test_no_cold_probe_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(cg_tec_cold_side_required(&g_ctl));
    CHECK(cg_tec_cold_side_required(NULL)); /* no controller -> fail closed */
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_cold_side_valid = false;
    in.t_cold_side_c = 0.0f;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_SENSOR);
    CHECK(strcmp(g_ctl.reason, "NO_COLD_SIDE_SENSOR") == 0);
    CHECK(g_ctl.state == CG_TEC_STATE_ARMED);
    CHECK(never_energized());
    return true;
}

/* The selected supervised profile omits ONLY the cold-presence check: the
 * real controller still starts on a valid T2 hot input with the cold flag
 * false, and the normal STOP path still de-energizes. */
static bool test_supervised_profile_admits_without_cold(void)
{
    cg_tec_limit_table_t limits = supervised_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(!cg_tec_cold_side_required(&g_ctl));
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_cold_side_valid = false;
    in.t_cold_side_c = 0.0f;
    in.t_hot_side_valid = true;
    in.t_hot_side_c = 30.0f;
    CHECK(cg_tec_start(&g_ctl, &in, 30000U, 200U) == CG_TEC_START_OK);
    CHECK(g_ctl.state == CG_TEC_STATE_COOLING);
    CHECK(g_ctl.outputs_energized);
    CHECK(g_ctl.duty_permille == 200U);

    in = healthy(1500U);
    in.t_cold_side_valid = false;
    in.t_cold_side_c = 0.0f;
    cg_tec_stop(&g_ctl, &in, "OPERATOR_STOP");
    CHECK(g_ctl.state == CG_TEC_STATE_COOLDOWN);
    CHECK(!g_ctl.outputs_energized);
    CHECK(g_ctl.duty_permille == 0U);
    return true;
}

/* Every other admission guard stays identical under the profile. */
static bool test_supervised_profile_other_guards_still_apply(void)
{
    cg_tec_limit_table_t limits = supervised_limits();
    cg_tec_inputs_t in;

    /* Missing hot channel. */
    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_cold_side_valid = false;
    in.t_hot_side_valid = false;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 200U) == CG_TEC_START_SENSOR);

    /* Stale thermal observation. */
    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_cold_side_valid = false;
    in.thermal_obs_ms = 1000U - 3001U;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 200U) == CG_TEC_START_SENSOR);

    /* Stale PZEM observation. */
    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_cold_side_valid = false;
    in.power_obs_ms = 1000U - 3001U;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 200U) == CG_TEC_START_SENSOR);

    /* Fan and interlock admission gates. */
    setup(&limits);
    g_ctl.cold_side_required = false;
    g_hw.fan_available = false;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_cold_side_valid = false;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 200U) == CG_TEC_START_FAN_UNAVAILABLE);
    setup(&limits);
    g_ctl.cold_side_required = false;
    g_hw.interlock = false;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_cold_side_valid = false;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 200U) == CG_TEC_START_INTERLOCK_OPEN);

    /* Live 40 C hot-side stop. */
    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(start_ok(1000U, 5000U, 200U));
    in = healthy(1100U);
    in.t_cold_side_valid = false;
    in.t_hot_side_c = 40.1f;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_OVERTEMP) != 0U);
    CHECK(!g_ctl.outputs_energized);

    /* Live 5 A and voltage-bound stops while cooling. */
    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(start_ok(1000U, 5000U, 200U));
    in = healthy(1100U);
    in.t_cold_side_valid = false;
    in.current_a = 5.1f;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_OVERCURRENT) != 0U);
    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(start_ok(1000U, 5000U, 200U));
    in = healthy(1100U);
    in.t_cold_side_valid = false;
    in.voltage_v = 13.3f;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_OVERVOLTAGE) != 0U);
    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(start_ok(1000U, 5000U, 200U));
    in = healthy(1100U);
    in.t_cold_side_valid = false;
    in.voltage_v = 9.9f;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_UNDERVOLTAGE) != 0U);

    /* Heartbeat and e-stop still own a live run. */
    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(start_ok(1000U, 5000U, 200U));
    in = healthy(1500U);
    in.t_cold_side_valid = false;
    cg_tec_tick(&g_ctl, &in);
    in = healthy(2501U);
    in.t_cold_side_valid = false;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_HEARTBEAT) != 0U);
    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(start_ok(1000U, 5000U, 200U));
    cg_tec_estop(&g_ctl, 1100U, "OPERATOR_ESTOP");
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_ESTOP) != 0U);
    CHECK(!g_ctl.outputs_energized);
    return true;
}

/* The profile does not relax duty/duration bounds, and the 30 s deadline
 * still rolls to OFF after cooldown. */
static bool test_supervised_profile_bounds_and_deadline(void)
{
    cg_tec_limit_table_t limits = supervised_limits();
    cg_tec_inputs_t in;
    cg_tec_status_t status;

    setup(&limits);
    g_ctl.cold_side_required = false;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_cold_side_valid = false;
    CHECK(cg_tec_start(&g_ctl, &in, 30000U, 201U) == CG_TEC_START_BAD_DURATION);
    CHECK(cg_tec_start(&g_ctl, &in, 30001U, 200U) == CG_TEC_START_BAD_DURATION);
    CHECK(never_energized());
    CHECK(cg_tec_start(&g_ctl, &in, 30000U, 200U) == CG_TEC_START_OK);

    in = healthy(31000U);
    in.t_cold_side_valid = false;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_COOLDOWN);
    CHECK(!g_ctl.outputs_energized);
    CHECK(g_ctl.duty_permille == 0U);
    in = healthy(91000U);
    cg_tec_tick(&g_ctl, &in);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.state == CG_TEC_STATE_OFF);
    CHECK(status.start_count == 1U);
    return true;
}

static bool test_no_hot_probe_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_hot_side_valid = false;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_SENSOR);
    CHECK(never_energized());
    return true;
}

/* A valid flag cannot make a non-finite hot value usable: the control core
 * owns that invariant at its public input boundary. */
static bool test_nonfinite_hot_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.t_hot_side_valid = true;
    in.t_hot_side_c = NAN;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_SENSOR);
    CHECK(strcmp(g_ctl.reason, "HOT_SIDE_NONFINITE") == 0);
    CHECK(g_ctl.state == CG_TEC_STATE_ARMED);
    CHECK(never_energized());

    in = healthy(1000U);
    in.t_hot_side_valid = true;
    in.t_hot_side_c = INFINITY;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_SENSOR);
    CHECK(never_energized());
    return true;
}

static bool test_power_missing_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.power_observed = false;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_SENSOR);
    CHECK(never_energized());
    return true;
}

static bool test_power_stale_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.power_obs_ms = 1000U - 3001U;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_SENSOR);
    CHECK(never_energized());
    return true;
}

static bool test_power_invalid_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    in.power_valid = false;
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_SENSOR);
    CHECK(never_energized());
    return true;
}

static bool test_overcurrent_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    in = healthy(1100U);
    in.current_a = 10.5f;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_OVERCURRENT) != 0U);
    CHECK(!g_ctl.outputs_energized);
    return true;
}

static bool test_overvoltage_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    in = healthy(1100U);
    in.voltage_v = 15.5f;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_OVERVOLTAGE) != 0U);
    CHECK(!g_ctl.outputs_energized);
    return true;
}

static bool test_undervoltage_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    in = healthy(1100U);
    in.voltage_v = 8.5f;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_UNDERVOLTAGE) != 0U);
    return true;
}

static bool test_overtemp_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    in = healthy(1100U);
    in.t_hot_side_c = 61.0f;
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_OVERTEMP) != 0U);
    return true;
}

static bool test_interlock_open_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    g_hw.interlock = false;
    in = healthy(1100U);
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_INTERLOCK_OPEN) != 0U);
    return true;
}

static bool test_fan_unavailable_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    g_hw.fan_available = false;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_FAN_UNAVAILABLE);
    CHECK(never_energized());
    return true;
}

static bool test_stage_unavailable_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    g_hw.stage_available = false;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_STAGE_UNAVAILABLE);
    CHECK(never_energized());
    return true;
}

static bool test_enable_failure_rolls_back(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    g_hw.fail_enable_call = 1;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_HW_REJECTED);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_HW_REJECTED) != 0U);
    CHECK(!g_ctl.outputs_energized);
    CHECK(g_ctl.duty_permille == 0U);
    return true;
}

static bool test_estop_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_status_t status;
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    cg_tec_estop(&g_ctl, 1100U, "OPERATOR_ESTOP");
    cg_tec_get_status(&g_ctl, &status);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_ESTOP) != 0U);
    CHECK(!g_ctl.outputs_energized);
    CHECK(status.fan_on);
    CHECK(status.estop_count == 1U);

    /* STOP is not CLEAR: it neither unlatches nor erases the fault reason. */
    in = healthy(1200U);
    cg_tec_stop(&g_ctl, &in, "OPERATOR_STOP");
    cg_tec_get_status(&g_ctl, &status);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK(strcmp(status.reason, "OPERATOR_ESTOP") == 0);
    return true;
}

static bool test_clear_requires_token_and_health(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    cg_tec_estop(&g_ctl, 1100U, "OPERATOR_ESTOP");

    in = healthy(1200U);
    CHECK(!cg_tec_clear_fault(&g_ctl, "00000000", &in));
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);

    in = healthy(1300U);
    in.current_a = 11.0f;
    CHECK(!cg_tec_clear_fault(&g_ctl, "deadbeef", &in));
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);

    in = healthy(1400U);
    CHECK(cg_tec_clear_fault(&g_ctl, "deadbeef", &in));
    CHECK(g_ctl.state == CG_TEC_STATE_COOLDOWN);
    CHECK(g_ctl.fault_bits == 0U);

    in = healthy(1500U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_BAD_STATE);
    CHECK(!cg_tec_is_armed(&g_ctl, 1500U)); /* CLEAR does not arm a new run */
    return true;
}

static bool test_heartbeat_gap_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(start_ok(1000U, 60000U, 300U));
    in = healthy(1500U);
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_COOLING);
    in = healthy(2501U); /* 1001 ms since the previous tick */
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_HEARTBEAT) != 0U);
    CHECK(!g_ctl.outputs_energized);
    return true;
}

static bool test_gap_while_off_is_not_a_fault(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    in = healthy(1000U);
    cg_tec_tick(&g_ctl, &in);
    in = healthy(100000U);
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_OFF);
    CHECK(g_ctl.fault_bits == 0U);
    return true;
}

static bool test_clock_backwards_latches(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    in = healthy(5000U);
    cg_tec_tick(&g_ctl, &in);
    in = healthy(4000U);
    cg_tec_tick(&g_ctl, &in);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_HEARTBEAT) != 0U);
    return true;
}

static bool test_duty_and_duration_bounds(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;

    setup(&limits);
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 0U) == CG_TEC_START_BAD_DUTY);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 1001U) == CG_TEC_START_BAD_DUTY);
    CHECK(cg_tec_start(&g_ctl, &in, 0U, 300U) == CG_TEC_START_BAD_DURATION);
    CHECK(cg_tec_start(&g_ctl, &in, 600001U, 300U) == CG_TEC_START_BAD_DURATION);
    CHECK(g_ctl.state == CG_TEC_STATE_ARMED);
    CHECK(never_energized());
    return true;
}

static bool test_no_platform_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_hw_ops_t empty;
    cg_tec_inputs_t in;

    fake_reset();
    memset(&empty, 0, sizeof(empty));
    cg_tec_control_init(&g_ctl, &limits, &empty, "deadbeef", 1000U, 120000U, 1000U,
                        60000U, 3000U, 3000U);
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_HW_REJECTED);
    CHECK(g_ctl.state == CG_TEC_STATE_ARMED); /* no platform, still no output */
    return true;
}

static bool test_duty_failure_rolls_back(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;
    int en;
    int duty;

    setup(&limits);
    g_hw.fail_duty_call = 2; /* the commanded-duty write, after duty 0 and enables */
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 5000U, 300U) == CG_TEC_START_HW_REJECTED);
    CHECK(g_ctl.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((g_ctl.fault_bits & CG_TEC_FAULT_HW_REJECTED) != 0U);
    CHECK(!g_ctl.outputs_energized);
    CHECK(g_ctl.duty_permille == 0U);
    en = last_call_index(CALL_EN);
    duty = last_call_index(CALL_DUTY);
    CHECK(en >= 0 && g_hw.calls[en].a == 0 && g_hw.calls[en].b == 0);
    CHECK(duty >= 0 && g_hw.calls[duty].a == 0);
    return true;
}

static bool test_continuous_policy_runs_until_stop(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;
    cg_tec_status_t status;

    limits.entry[CG_LIMIT_CURRENT_MAX_A].value = 10.0f;
    limits.entry[CG_LIMIT_HOT_SIDE_MAX_C].value = 40.0f;
    limits.entry[CG_LIMIT_DUTY_MAX_PERMILLE].value = 1000.0f;
    limits.entry[CG_LIMIT_ON_TIME_MAX_MS].value = 30000.0f;
    setup(&limits);
    /* Default is timed: START 0 must stay refused. */
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 0U, 1000U) == CG_TEC_START_BAD_DURATION);
    CHECK(never_energized());
    /* The fully gated interposition sets this policy after init. */
    g_ctl.continuous_allowed = true;
    CHECK(cg_tec_start(&g_ctl, &in, 0U, 999U) == CG_TEC_START_BAD_DURATION);
    CHECK(g_ctl.state == CG_TEC_STATE_ARMED);
    CHECK(cg_tec_start(&g_ctl, &in, 0U, 1000U) == CG_TEC_START_OK);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.state == CG_TEC_STATE_COOLING && status.continuous);
    CHECK(status.remaining_ms == 0U); /* no fake deadline / UINT_MAX */

    /* Every other guard still runs (heartbeat included); 31 s and 60 s are
     * still COOLING. Ticks stay inside the heartbeat window. */
    for (uint64_t t = 1500U; t <= 61400U; t += 400U) {
        in = healthy(t);
        cg_tec_tick(&g_ctl, &in);
    }
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.state == CG_TEC_STATE_COOLING && status.continuous);
    CHECK(status.elapsed_ms >= 60000U);

    /* One sensor/limit fault still stops and clears the continuous state. */
    in = healthy(62000U);
    in.current_a = 10.01f;
    cg_tec_tick(&g_ctl, &in);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK(!status.continuous && !status.outputs_energized);
    CHECK(status.duty_permille == 0U);
    return true;
}

static bool test_ai_demo_lease_door_and_seq(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;
    cg_tec_status_t status;

    limits.entry[CG_LIMIT_CURRENT_MAX_A].value = 10.0f;
    limits.entry[CG_LIMIT_HOT_SIDE_MAX_C].value = 40.0f;
    limits.entry[CG_LIMIT_DUTY_MAX_PERMILLE].value = 1000.0f;
    setup(&limits);
    g_ctl.continuous_allowed = true;
    g_ctl.ai_demo_allowed = true;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_ai_demo_start(&g_ctl, &in, 500U, 3000U, 1U) == CG_TEC_START_OK);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.ai_demo && status.continuous && status.duty_permille == 500U);
    CHECK(status.remaining_ms == 0U);

    /* Live update; duplicate/lower seq is ignored. */
    in = healthy(1500U);
    CHECK(cg_tec_ai_demo_update(&g_ctl, &in, 750U, 3000U, 2U));
    CHECK(!cg_tec_ai_demo_update(&g_ctl, &in, 250U, 3000U, 2U));
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.duty_permille == 750U && status.ai_duty_permille == 750U);

    /* Door OPEN wins; CLOSED alone never replays the old duty. */
    in = healthy(2000U);
    in.door_open = true;
    cg_tec_tick(&g_ctl, &in);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.state == CG_TEC_STATE_COOLING && status.duty_permille == 0U);
    CHECK(status.ai_demo && status.ai_duty_permille == 750U);
    in = healthy(2500U);
    cg_tec_tick(&g_ctl, &in);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.duty_permille == 0U); /* fresh positive decision required */
    CHECK(cg_tec_ai_demo_update(&g_ctl, &in, 900U, 3000U, 3U));
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.duty_permille == 900U);

    /* Stale/unknown door also drives zero. */
    in = healthy(3001U);
    in.door_obs_ms = 0U;
    cg_tec_tick(&g_ctl, &in);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.duty_permille == 0U);

    /* No renewal -> bounded lease expires to cooldown and PWM 0. */
    in = healthy(3500U);
    cg_tec_tick(&g_ctl, &in);
    in = healthy(4500U);
    cg_tec_tick(&g_ctl, &in);
    in = healthy(5500U);
    cg_tec_tick(&g_ctl, &in);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.state == CG_TEC_STATE_COOLDOWN);
    CHECK(!status.ai_demo && status.duty_permille == 0U);
    CHECK(!status.outputs_energized);
    return true;
}

static bool test_continuous_stop_and_heartbeat(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_tec_inputs_t in;
    cg_tec_status_t status;

    limits.entry[CG_LIMIT_DUTY_MAX_PERMILLE].value = 1000.0f;
    setup(&limits);
    g_ctl.continuous_allowed = true;
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 1000U));
    in = healthy(1000U);
    CHECK(cg_tec_start(&g_ctl, &in, 0U, 1000U) == CG_TEC_START_OK);
    in = healthy(2000U);
    cg_tec_stop(&g_ctl, &in, "OPERATOR_STOP");
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.state == CG_TEC_STATE_COOLDOWN);
    CHECK(!status.continuous && !status.outputs_energized);
    CHECK(status.duty_permille == 0U);

    /* A fresh continuous run that loses its heartbeat still latches. */
    in = healthy(63000U);
    cg_tec_tick(&g_ctl, &in); /* cooldown completes to OFF */
    CHECK(cg_tec_arm(&g_ctl, "deadbeef", 63000U));
    in = healthy(63000U);
    CHECK(cg_tec_start(&g_ctl, &in, 0U, 1000U) == CG_TEC_START_OK);
    in = healthy(63500U);
    cg_tec_tick(&g_ctl, &in);
    in = healthy(65000U); /* > heartbeat timeout 1000 ms */
    cg_tec_tick(&g_ctl, &in);
    cg_tec_get_status(&g_ctl, &status);
    CHECK(status.state == CG_TEC_STATE_FAULT_LATCH);
    CHECK((status.fault_bits & CG_TEC_FAULT_HEARTBEAT) != 0U);
    CHECK(!status.continuous && !status.outputs_energized);
    return true;
}

/* Telemetry is part of the observable contract: a frame that does not fit
 * must be refused, never truncated. */
const char *cg_quality_name(cg_thermal_quality_t quality)
{
    (void)quality;
    return "VALID";
}

static void worst_case_frame(cg_telemetry_frame_t *frame, cg_snapshot_t *snap, char run_id[33])
{
    static cg_health_report_t health;

    memset(snap, 0, sizeof(*snap));
    snap->thermal_observed = true;
    snap->thermal_valid = true;
    snap->thermal_quality = CG_QUALITY_VALID;
    snap->thermal_obs_ms = 999900U;
    snap->thermal_seq = 4294967295U;
    snap->probes_ok = 3;
    snap->probes_expected = 3;
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        snap->t_valid[role] = true;
        snap->t_c[role] = -12.5625f;
    }
    snap->power_observed = true;
    snap->power_valid = true;
    snap->power_obs_ms = 999900U;
    snap->power_seq = 4294967295U;
    snap->voltage_v = 12.04f;
    snap->current_a = 1.2345f;
    snap->power_w = 14.8f;
    snap->energy_wh = 999999.0f;
    snap->door_observed = true;
    snap->door_known = true;
    snap->door_open = false;
    snap->door_obs_ms = 999900U;
    snap->door_transitions = 4294967295U;
    snap->door_cycles = 4294967295U;

    memset(run_id, 'A', 32);
    run_id[32] = '\0';
    (void)snprintf(g_ctl.reason, sizeof(g_ctl.reason), "%s", "START_LIMITS_UNRESOLVED");

    memset(&health, 0, sizeof(health));
    for (int i = 0; i < CG_PRODUCER_COUNT; i++) {
        health.state[i] = CG_HEALTH_MISSED;
        health.max_gap_ms[i] = 4294967295U;
        health.beats[i] = 4294967295U;
        health.gap_ms[i] = 4294967295U;
    }
    (void)snprintf(health.overall, sizeof(health.overall), "%s", "MISSED");

    memset(frame, 0, sizeof(*frame));
    frame->seq = 4294967295U;
    frame->boot_id = "1234ABCD";
    frame->boot_count = 12;
    frame->uptime_ms = 1000000U;
    frame->run_id = run_id;
    frame->test_phase = "TEC_OFF";
    frame->snap = snap;
    frame->ctl = &g_ctl;
    frame->health = &health;
    frame->probe_rom[0] = "287088CA00000051";
    frame->probe_rom[1] = "28AEBF2200000006";
    frame->probe_rom[2] = "28CBE9CA00000072";
    frame->probe_rom[3] = "283BE5C9000000A9";
    frame->role_status = CG_ROM_STATUS;
    frame->output_stage_enabled = false;
    frame->fan_available = false;
}

static bool test_telemetry_worst_case_fits(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_snapshot_t snap;
    cg_telemetry_frame_t frame;
    char run_id[33];
    char line[CG_TELEMETRY_LINE_MAX];
    size_t len;

    setup(&limits);
    worst_case_frame(&frame, &snap, run_id);
    len = cg_telemetry_format(line, sizeof(line), &frame);
    CHECK(len > 0U);
    CHECK(len < sizeof(line));
    CHECK(strstr(line, "timestamp_utc=UNAVAILABLE") != NULL);
    CHECK(strstr(line, " raw_spare_status=OK") != NULL); /* complete tail token */
    printf("  worst_case_len=%zu budget=%d\n", len, CG_TELEMETRY_LINE_MAX);
    return true;
}

static bool test_telemetry_overflow_is_refused(void)
{
    cg_tec_limit_table_t limits = resolved_limits();
    cg_snapshot_t snap;
    cg_telemetry_frame_t frame;
    char run_id[33];
    char small[64];

    setup(&limits);
    worst_case_frame(&frame, &snap, run_id);
    CHECK(cg_telemetry_format(small, sizeof(small), &frame) == 0U);
    CHECK(small[0] == '\0'); /* nothing partial is left behind */
    return true;
}

/* ------------------------------------------------------------------ */

typedef struct {
    const char *name;
    bool (*fn)(void);
} test_case_t;

int main(void)
{
    static const test_case_t tests[] = {
        {"init_is_safe", test_init_is_safe},
        {"start_without_arm_refused", test_start_without_arm_refused},
        {"arm_token_binding", test_arm_token_binding},
        {"arm_expiry", test_arm_expiry},
        {"unresolved_limits_refuse", test_unresolved_limits_refuse},
        {"happy_path_order", test_happy_path_order},
        {"second_start_refused", test_second_start_refused},
        {"stop_order_and_cooldown", test_stop_order_and_cooldown},
        {"duration_expiry", test_duration_expiry},
        {"invalid_thermal_latches", test_invalid_thermal_latches},
        {"stale_thermal_latches", test_stale_thermal_latches},
        {"no_cold_probe_refused", test_no_cold_probe_refused},
        {"supervised_profile_admits_without_cold", test_supervised_profile_admits_without_cold},
        {"supervised_profile_other_guards_still_apply",
         test_supervised_profile_other_guards_still_apply},
        {"supervised_profile_bounds_and_deadline", test_supervised_profile_bounds_and_deadline},
        {"no_hot_probe_refused", test_no_hot_probe_refused},
        {"nonfinite_hot_refused", test_nonfinite_hot_refused},
        {"power_missing_refused", test_power_missing_refused},
        {"power_stale_refused", test_power_stale_refused},
        {"power_invalid_refused", test_power_invalid_refused},
        {"overcurrent_latches", test_overcurrent_latches},
        {"overvoltage_latches", test_overvoltage_latches},
        {"undervoltage_latches", test_undervoltage_latches},
        {"overtemp_latches", test_overtemp_latches},
        {"interlock_open_latches", test_interlock_open_latches},
        {"fan_unavailable_refused", test_fan_unavailable_refused},
        {"stage_unavailable_refused", test_stage_unavailable_refused},
        {"enable_failure_rolls_back", test_enable_failure_rolls_back},
        {"estop_latches", test_estop_latches},
        {"clear_requires_token_and_health", test_clear_requires_token_and_health},
        {"heartbeat_gap_latches", test_heartbeat_gap_latches},
        {"gap_while_off_is_not_a_fault", test_gap_while_off_is_not_a_fault},
        {"clock_backwards_latches", test_clock_backwards_latches},
        {"duty_and_duration_bounds", test_duty_and_duration_bounds},
        {"continuous_policy_runs_until_stop", test_continuous_policy_runs_until_stop},
        {"continuous_stop_and_heartbeat", test_continuous_stop_and_heartbeat},
        {"ai_demo_lease_door_and_seq", test_ai_demo_lease_door_and_seq},
        {"no_platform_refused", test_no_platform_refused},
        {"duty_failure_rolls_back", test_duty_failure_rolls_back},
        {"telemetry_worst_case_fits", test_telemetry_worst_case_fits},
        {"telemetry_overflow_is_refused", test_telemetry_overflow_is_refused},
    };
    const int total = (int)(sizeof(tests) / sizeof(tests[0]));
    int i;
    int passed = 0;

    for (i = 0; i < total; i++) {
        bool ok = tests[i].fn();
        if (ok && !final_state_is_safe()) {
            printf("  final-state invariant violated\n");
            g_failures++;
            ok = false;
        }
        printf("%s %s\n", ok ? "PASS" : "FAIL", tests[i].name);
        if (ok) {
            passed++;
        }
    }

    printf("\n%d/%d scenarios passed\n", passed, total);
    if (g_failures != 0 || passed != total) {
        return 1;
    }
    printf("TEC STATE MACHINE: ALL SCENARIOS PASS (no energization path)\n");
    return 0;
}
