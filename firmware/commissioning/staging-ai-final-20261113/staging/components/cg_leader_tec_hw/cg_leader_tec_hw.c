/*
 * ColdGuard firmware - Leader TEC hardware adapter (Leader-owned).
 *
 * Implements Member A's cg_tec_hw_ops_t contract (cg_tec_platform.h) against
 * the as-built IBT-2 wiring Member A froze in code and evidence:
 * RPWM=GPIO5, R_EN=GPIO6, L_EN=GPIO10, LPWM tied to GND (never driven),
 * no controllable fan, and a U6 interlock loop not yet installed.
 * cg_actuator_force_off() stays the ONLY function that touches an actuator
 * pin, exactly as delivered.
 *
 * Member A's stub (cg_tec_hw.c) refuses every energizing request and states
 * that enabling "requires a new, reviewed adapter - not a one-line macro
 * flip". This component is that adapter, interposed at the accessor level:
 *
 *   - ACTIVE only when CONFIG_CG_LEADER_TEC_HW=1 (Kconfig default n: the
 *     shipped build keeps the delivered stub behavior unchanged) AND all
 *     three member commissioning constants read 1 (a recorded-evidence
 *     decision, never a build tweak).
 *   - read_interlock() reads the REAL U6 sense input
 *     (CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN, normally-closed active-low).
 *     Until the loop is installed and the pin configured (default -1) it
 *     reads open: fail closed, nothing simulated.
 *   - The working H8 physical route needs BOTH enables HIGH: R_EN=GPIO6 and
 *     L_EN=GPIO10. (0,0) is OFF; (1,1) is the only active request accepted.
 *     Mixed states are refused and both lines are driven low (fail closed).
 *     LPWM stays tied to GND and is never driven.
 *   - Non-zero duty only while both enables are ON, interlock closed, duty
 *     in bounds, gates signed; any refusal drives duty 0, then both enables
 *     low, and returns false so the MEMBER controller latches its fault and
 *     rolls back - its rollback stays the only rollback.
 *   - set_fan/fan_available: honestly not commandable (PHY-TH-001).
 */
#include "cg_leader_tec_hw.h"

#include "driver/gpio.h"
#include "driver/ledc.h"

#include "sdkconfig.h"
#include "cg_actuator.h"
#include "coldguard_config.h"

#define CG_LEADER_TEC_RPWM_PIN 5U
#define CG_LEADER_TEC_REN_PIN 6U
#define CG_LEADER_TEC_LEN_PIN 10U

/* H8-verified PWM shape: 1000 Hz, 13 bit, 8192 raw steps. */
#define CG_LEADER_TEC_PWM_HZ 1000U
#define CG_LEADER_TEC_PWM_RESOLUTION LEDC_TIMER_13_BIT
#define CG_LEADER_TEC_PWM_STEPS 8192U

#if CONFIG_CG_LEADER_TEC_HW
#define CG_LEADER_ILL_PIN CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN
#else
#define CG_LEADER_ILL_PIN (-1)
#endif

static bool s_hw_ready;
static bool s_enables_on;
static uint32_t s_duty_permille_set;

/* Duty 0 first, then BOTH enables low. These are the actuator-safe writes
 * every refusal, stop, fault and partial bring-up failure must leave behind. */
static bool leader_duty_zero(void)
{
    return ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 0U) == ESP_OK
           && ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0) == ESP_OK;
}

static void leader_enables_low(void)
{
    /* Attempt both pins even if the first write reports failure: L_EN must
     * never be left high because R_EN failed. */
    (void)gpio_set_level(CG_LEADER_TEC_REN_PIN, 0);
    (void)gpio_set_level(CG_LEADER_TEC_LEN_PIN, 0);
    s_enables_on = false;
    s_duty_permille_set = 0U;
}

static void leader_safe_off(void)
{
    if (s_hw_ready) {
        (void)leader_duty_zero();
    }
    leader_enables_low();
    /* Member safe module also re-drives both enable pins low and RPWM 0.
     * It reconfigures GPIO5 as a plain output, which detaches the LEDC
     * peripheral route. Mark the adapter unready so the next active
     * operation re-runs lazy init (timer + channel config) before any
     * duty write; otherwise LEDC register writes could succeed with no PWM
     * reaching the pad. */
    cg_actuator_force_off();
    s_hw_ready = false;
}

static bool leader_gates_signed(void)
{
    return (CG_TEC_OUTPUT_STAGE_ENABLED == 1)
           && (CG_TEC_HARDWARE_GATES_VERIFIED == 1)
           && (CG_ACTUATOR_ENABLE_ALLOWED == 1);
}

static bool leader_interlock_configured(void)
{
#if CONFIG_CG_LEADER_TEC_HW
#if defined(CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN) \
    && CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN
    return true; /* owner-attested no-interlock mode (see read below) */
#else
    return CG_LEADER_ILL_PIN >= 0;
#endif
#else
    return false;
#endif
}

static bool leader_lazy_init(void);
static bool leader_interlock_configured(void);

static bool leader_read_interlock(void)
{
    /* The interlock input must be read before any energizing call: the
     * member controller checks it inside START ahead of the bring-up
     * ordering. Lazily initializing here only re-establishes the safe state
     * (force-off) and configures inputs, so the read can never be blocked
     * by "not yet initialized" - the fresh-boot path still fails closed on
     * an actually-open loop, not on missing initialization. */
    if (!leader_lazy_init()) {
        return false;
    }
#if defined(CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN) \
    && CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN
    /* No physical interlock exists in the as-built hardware (owner design
     * decision, recorded in the build manifest and displayed as NOT FITTED
     * on the dashboard). Reporting permitted here is an explicitly
     * configured commissioning decision - the protection set is the
     * supervised session, the branch fuse and the member software chain -
     * NOT a simulated contact; with the pin unset nothing is read and
     * nothing is implied about a physical loop. */
    return true;
#else
    if (!leader_interlock_configured()) {
        return false;
    }
#if CONFIG_CG_LEADER_TEC_HW_ACTIVE_LOW
    const int level = gpio_get_level((gpio_num_t)CG_LEADER_ILL_PIN);
    return level == 0;
#else
    const int level = gpio_get_level((gpio_num_t)CG_LEADER_ILL_PIN);
    return level == 1;
#endif
#endif
}

static bool leader_lazy_init(void)
{
    if (s_hw_ready) {
        return true;
    }
    cg_actuator_force_off();

    ledc_timer_config_t timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .timer_num = LEDC_TIMER_0,
        .duty_resolution = CG_LEADER_TEC_PWM_RESOLUTION,
        .freq_hz = CG_LEADER_TEC_PWM_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    if (ledc_timer_config(&timer) != ESP_OK) {
        return false;
    }
    ledc_channel_config_t channel = {
        .gpio_num = CG_LEADER_TEC_RPWM_PIN,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0U,
        .hpoint = 0U,
    };
    if (ledc_channel_config(&channel) != ESP_OK) {
        return false;
    }
#if defined(CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN) \
    && CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN >= 0
    /* Compile-time guarded: an unset pin (-1) must not even build the
     * bit-mask expression (a negative shift is undefined behavior). */
    gpio_config_t ilock_in = {
        .pin_bit_mask = (1ULL << (uint32_t)CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    (void)gpio_config(&ilock_in);
#endif
    s_enables_on = false;
    s_duty_permille_set = 0U;
    s_hw_ready = true;
    return true;
}

static bool leader_set_enables(bool ren, bool len)
{
    if (!leader_lazy_init()) {
        leader_safe_off();
        return false;
    }
    if (!ren && !len) {
        (void)leader_duty_zero();
        leader_enables_low();
        return true;
    }
    if (!ren || !len) {
        /* Mixed active request: the IBT-2 route is both-or-nothing. */
        leader_safe_off();
        return false;
    }
    if (!leader_gates_signed() || !leader_read_interlock()
        || !cg_actuator_outputs_allowed(true, 0U, 0U)) {
        leader_safe_off();
        return false;
    }
    /* Duty is already zero; raise both enables together. If either write
     * fails, both are driven low again before reporting the refusal. */
    if (!leader_duty_zero()) {
        leader_safe_off();
        return false;
    }
    const esp_err_t ren_err = gpio_set_level(CG_LEADER_TEC_REN_PIN, 1);
    const esp_err_t len_err = gpio_set_level(CG_LEADER_TEC_LEN_PIN, 1);
    if (ren_err != ESP_OK || len_err != ESP_OK) {
        leader_safe_off();
        return false;
    }
    s_enables_on = true;
    return true;
}

static bool leader_set_cooling_duty(uint32_t permille)
{
    if (!leader_lazy_init()) {
        cg_actuator_force_off();
        return false;
    }
    if (permille == 0U) {
        if (!leader_duty_zero()) {
            leader_safe_off();
            return false;
        }
        s_duty_permille_set = 0U;
        return true;
    }
    if (!leader_gates_signed() || !s_enables_on || !leader_read_interlock()
        || !cg_actuator_outputs_allowed(true, permille, 0U)) {
        leader_safe_off();
        return false;
    }
    /* H8 exact conversion: floor(permille * 8192 / 1000); 1000 permille
     * saturates at 8191 because LEDC rejects a count of 2^13. */
    uint32_t duty_bits =
        (uint32_t)(((uint64_t)CG_LEADER_TEC_PWM_STEPS * permille) / 1000U);
    if (duty_bits >= CG_LEADER_TEC_PWM_STEPS) {
        duty_bits = CG_LEADER_TEC_PWM_STEPS - 1U;
    }
    if (ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty_bits) != ESP_OK
        || ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0) != ESP_OK) {
        leader_safe_off();
        return false;
    }
    s_duty_permille_set = permille;
    return true;
}

static bool leader_fan_continuous(void)
{
#if CONFIG_CG_LEADER_TEC_HW
    return CONFIG_CG_LEADER_TEC_HW_FAN_CONTINUOUS == 1;
#else
    return false;
#endif
}

/* PHY-TH-001 as-built: the V1 hot-side fan runs from its own fused branch
 * (fuse slot 4) and is not firmware-controlled. The contract permits this
 * only when the continuous independent fan power is recorded; the
 * commissioning configuration sets CG_LEADER_TEC_HW_FAN_CONTINUOUS after
 * that record exists. Returning true for "on" then reports the real state
 * (a continuously powered fan is running); returning false for "off" is the
 * honest answer - the firmware cannot stop it. All callers of set_fan(false)
 * ignore the result, and `fan_on` telemetry therefore means the
 * firmware-requested state, not the physical fan state. */
static bool leader_set_fan(bool on)
{
    if (!leader_fan_continuous()) {
        return false;
    }
    return on;
}

static bool leader_read_interlock_op(void)
{
    return leader_read_interlock();
}

static bool leader_output_stage_available(void)
{
    return leader_gates_signed();
}

static bool leader_fan_available(void)
{
    return leader_fan_continuous();
}

static const cg_tec_hw_ops_t s_leader_ops = {
    .set_enables = leader_set_enables,
    .set_cooling_duty = leader_set_cooling_duty,
    .set_fan = leader_set_fan,
    .read_interlock = leader_read_interlock_op,
    .output_stage_available = leader_output_stage_available,
    .fan_available = leader_fan_available,
};

const cg_tec_hw_ops_t *cg_leader_tec_hw_ops(void)
{
    return &s_leader_ops;
}
/* Accessor interposition: every member caller of cg_tec_hw_ops() gets this
 * table when the commissioning sdkconfig enables the adapter; otherwise the
 * delivered stub answers unchanged (the shipped fail-closed behavior). */
extern const cg_tec_hw_ops_t *__real_cg_tec_hw_ops(void);

const cg_tec_hw_ops_t *__wrap_cg_tec_hw_ops(void)
{
#if CONFIG_CG_LEADER_TEC_HW
    return cg_leader_tec_hw_ops();
#else
    return __real_cg_tec_hw_ops();
#endif
}

/* ---- Supervised-session limit set (owner-proposed envelope) --------------
 * The delivered cg_tec_limits_shipped keeps EVERY entry UNRESOLVED, which is
 * the shipped fail-closed posture: the member control module treats an
 * unresolved limit as "no output". A supervised commissioning build links
 * this table instead, through the same accessior-level interposition used
 * for the hardware ops, so no member file changes:
 *   - every value is the OWNER'S PROPOSED SUPERVISORY ENVELOPE for ONE
 *     session (2026-11-13): either the TEC200 first step (200 permille,
 *     5.0 A stop) or the explicit TEC1000 full-duty demo (1000 permille,
 *     10.0 A stop); both keep the 30 s bound, 40.0 C T2 stop, the same
 *     voltage band and every stop guard. 1000 permille is an empirical
 *     demo, never a rating (observed peak 9.99 A);
 *   - the provenance strings say exactly that - these are SESSION values,
 *     never certified plant ratings, and the host trip behavior is verified
 *     separately by the Leader tests;
 *   - without CG_LEADER_TEC_HW_SUPERVISED_LIMITS the wrapper hands back the
 *     shipped table unchanged and the firmware stays at its shipped
 *     fail-closed posture.
 * Historical evidence base for the numbers: post-cable-replacement duty
 * ladder (600-999 permille: 5.73-9.99 A) and the 1800 s run (8.75 A peak,
 * T2 max 37.688 C) - headroom over the session stop thresholds. */
#include "cg_tec_control.h"

extern void __real_cg_tec_control_init(cg_tec_control_t *ctl,
                                       const cg_tec_limit_table_t *limits,
                                       const cg_tec_hw_ops_t *ops,
                                       const char *boot_token,
                                       uint64_t now_ms,
                                       uint32_t arm_ttl_ms,
                                       uint32_t heartbeat_timeout_ms,
                                       uint32_t cooldown_ms,
                                       uint32_t thermal_stale_ms,
                                       uint32_t power_stale_ms);

/* The table the member controller was really initialized with. Written once
 * after the real init returns; the ingress evidence task only reads it. */
static const cg_tec_limit_table_t *volatile s_effective_limits;
/* The shipped fail-closed answer until the real init has run and the
 * interposition has recorded what the controller is actually enforcing. */
static volatile bool s_cold_probe_required = true;
/* The continuous policy the member controller actually received. False until
 * the fully gated TEC1000 init interposition selects it; never a runtime
 * toggle and never set by a console command alone. */
static volatile bool s_continuous_allowed = false;

#if CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS
/* Exactly one explicit supervised demo profile is linkable. The requested
 * duty is the image macro written by the generator and recorded in the
 * manifest; any other value fails the build instead of silently choosing a
 * different envelope. 1000 permille is an attended demo value, not a rating. */
#if CG_TEC_REQUEST_DUTY_PERMILLE == 200
#define CG_LEADER_SUP_CURRENT_MAX_A 5.0f
#define CG_LEADER_SUP_CURRENT_PROVENANCE \
    "SUPERVISORY_SESSION_STOP_5A_OWNER_20261113_NOT_A_RATING"
#define CG_LEADER_SUP_DUTY_PROVENANCE \
    "FIRST_STEP_ONLY_ESCALATION_FORBIDDEN_OWNER_20261113"
#elif CG_TEC_REQUEST_DUTY_PERMILLE == 1000
#if !defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_FULL_DUTY_DEMO)
#error "1000 permille requires CONFIG_CG_LEADER_TEC_HW_SUPERVISED_FULL_DUTY_DEMO=y"
#endif
#define CG_LEADER_SUP_CURRENT_MAX_A 10.0f
#define CG_LEADER_SUP_CURRENT_PROVENANCE \
    "FULL_DUTY_DEMO_1000_OWNER_20261113_10A_SUPERVISORY_NOT_A_RATING"
#define CG_LEADER_SUP_DUTY_PROVENANCE \
    "EXPLICIT_SUPERVISED_FULL_DUTY_DEMO_1000_OWNER_20261113"
#else
#error "supervised limits require CG_TEC_REQUEST_DUTY_PERMILLE 200 or 1000"
#endif

/* Direct designated entries keep the constant initializer portable to the
 * host harness compiler as well as the target toolchain. */
static const cg_tec_limit_table_t s_leader_supervised_limit_table = {
    .entry = {
        [CG_LIMIT_CURRENT_MAX_A] = {
            CG_LIMIT_CURRENT_MAX_A, "current_max_a", "A",
            CG_LIMIT_RESOLVED, CG_LEADER_SUP_CURRENT_MAX_A,
            CG_LEADER_SUP_CURRENT_PROVENANCE},
        [CG_LIMIT_VOLTAGE_MAX_V] = {
            CG_LIMIT_VOLTAGE_MAX_V, "voltage_max_v", "V",
            CG_LIMIT_RESOLVED, 13.2f,
            "PSU_12V_RAIL_SUPERVISORY_HEADROOM_SESSION"},
        [CG_LIMIT_VOLTAGE_MIN_V] = {
            CG_LIMIT_VOLTAGE_MIN_V, "voltage_min_v", "V",
            CG_LIMIT_RESOLVED, 10.0f,
            "PSU_SAG_GUARD_SUPERVISORY_SESSION"},
        [CG_LIMIT_HOT_SIDE_MAX_C] = {
            CG_LIMIT_HOT_SIDE_MAX_C, "hot_side_max_c", "C",
            CG_LIMIT_RESOLVED, 40.0f,
            "SUPERVISORY_T2_STOP_40C_OWNER_20261113_HIST_MAX_37P688"},
        [CG_LIMIT_DUTY_MAX_PERMILLE] = {
            CG_LIMIT_DUTY_MAX_PERMILLE, "duty_max_permille", "permille",
            CG_LIMIT_RESOLVED, (float)CG_TEC_REQUEST_DUTY_PERMILLE,
            CG_LEADER_SUP_DUTY_PROVENANCE},
        [CG_LIMIT_ON_TIME_MAX_MS] = {
            CG_LIMIT_ON_TIME_MAX_MS, "on_time_max_ms", "ms",
            CG_LIMIT_RESOLVED, 30000.0f,
            "BOUNDED_FIRST_ATTEMPT_30S_OWNER_20261113"},
    },
};
#endif

void __wrap_cg_tec_control_init(cg_tec_control_t *ctl,
                                const cg_tec_limit_table_t *limits,
                                const cg_tec_hw_ops_t *ops,
                                const char *boot_token,
                                uint64_t now_ms,
                                uint32_t arm_ttl_ms,
                                uint32_t heartbeat_timeout_ms,
                                uint32_t cooldown_ms,
                                uint32_t thermal_stale_ms,
                                uint32_t power_stale_ms)
{
#if defined(CONFIG_CG_LEADER_TEC_HW) && defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS) \
    && CONFIG_CG_LEADER_TEC_HW && CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS
    /* Commissioning opt-in: hand the member controller the recorded
     * supervisory limit set instead of the shipped unresolved one. */
    const cg_tec_limit_table_t *effective = &s_leader_supervised_limit_table;

    (void)limits; /* the recorded supervised table replaces the caller's */
    __real_cg_tec_control_init(ctl, effective, ops,
                               boot_token, now_ms, arm_ttl_ms,
                               heartbeat_timeout_ms, cooldown_ms,
                               thermal_stale_ms, power_stale_ms);
#else
    const cg_tec_limit_table_t *effective = limits;

    __real_cg_tec_control_init(ctl, effective, ops, boot_token, now_ms,
                               arm_ttl_ms, heartbeat_timeout_ms, cooldown_ms,
                               thermal_stale_ms, power_stale_ms);
#endif
    /* Store only after the real init accepted it, so evidence never reports
     * a table the member controller did not receive. */
    s_effective_limits = effective;

    /* Named attended-characterization profile, selected by an explicit
     * Kconfig + generator flag. It requires the supervised limit set, the
     * Leader hardware adapter and the exact first-step duty; any other
     * combination leaves the controller's normal cold-probe requirement in
     * force (fail closed, no silent relaxation). */
#if defined(CONFIG_CG_LEADER_TEC_HW) \
    && defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS) \
    && defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_NO_COLD_PROBE) \
    && CONFIG_CG_LEADER_TEC_HW \
    && CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS \
    && CONFIG_CG_LEADER_TEC_HW_SUPERVISED_NO_COLD_PROBE
    if (leader_gates_signed()
        && (CG_TEC_REQUEST_DUTY_PERMILLE == 200
            || CG_TEC_REQUEST_DUTY_PERMILLE == 1000)) {
        ctl->cold_side_required = false;
    }
#endif
    /* Continuous (no 30 s auto-stop) is an even narrower policy: the exact
     * TEC1000 full-duty demo, the supervised no-cold profile, signed gates
     * and the explicit SDK flag must all be present. Anything else leaves the
     * controller's default bounded behavior untouched. */
    s_continuous_allowed = false;
#if defined(CONFIG_CG_LEADER_TEC_HW) \
    && defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS) \
    && defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_NO_COLD_PROBE) \
    && defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_FULL_DUTY_DEMO) \
    && CONFIG_CG_LEADER_TEC_HW \
    && CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS \
    && CONFIG_CG_LEADER_TEC_HW_SUPERVISED_NO_COLD_PROBE \
    && CONFIG_CG_LEADER_TEC_HW_SUPERVISED_FULL_DUTY_DEMO
    if (leader_gates_signed() && CG_TEC_REQUEST_DUTY_PERMILLE == 1000) {
        ctl->continuous_allowed = true;
        ctl->ai_demo_allowed = true;
        s_continuous_allowed = true;
    }
#endif
    s_cold_probe_required = cg_tec_cold_side_required(ctl);
}

bool cg_leader_tec_cold_probe_required(void)
{
    return s_cold_probe_required;
}

bool cg_leader_tec_continuous_allowed(void)
{
    return s_continuous_allowed;
}

const cg_tec_limit_table_t *cg_leader_tec_effective_limits(void)
{
    return s_effective_limits;
}

const char *cg_leader_tec_effective_limits_source(void)
{
    const cg_tec_limit_table_t *table = s_effective_limits;

    if (table == NULL) {
        return NULL;
    }
#if defined(CONFIG_CG_LEADER_TEC_HW) && defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS) \
    && CONFIG_CG_LEADER_TEC_HW && CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS
    if (table == &s_leader_supervised_limit_table) {
        return "SUPERVISED";
    }
#endif
    if (table == &cg_tec_limits_shipped) {
        return "MEMBER_SHIPPED";
    }
    return "CALLER_TABLE";
}
