/*
 * Host harness for the ColdGuard W05 telemetry foundation.
 *
 * Compiles firmware/main/cg_quality.c, cg_health.c and cg_telemetry.c unchanged
 * and drives them with synthetic observations. Nothing here is a physical
 * measurement: the point is that the *rules* A-W05-01/-04/-05 claim are
 * executable and falsifiable on the host, so a bench capture is not the first
 * place a wrong quality verdict appears.
 *
 * It also prints the worst-case schema-2 line length, which is what the
 * CG_TELEMETRY_LINE_MAX budget assertion in test_cg_w05_harness.py reads.
 *
 * Exit code: 0 when every scenario passes, 1 otherwise.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cg_health.h"
#include "cg_quality.h"
#include "cg_snapshot.h"
#include "cg_tec_control.h"
#include "cg_tec_limits.h"
#include "cg_telemetry.h"
#include "coldguard_config.h"

/* cg_ds18b20.c is not part of this build; cg_telemetry.c only calls the name
 * helper, and this harness never puts an invalid thermal_quality in the
 * snapshot, so a fixed label is enough to link. */
const char *cg_quality_name(cg_thermal_quality_t quality)
{
    (void)quality;
    return "VALID";
}

static int g_failures;

#define CHECK(cond)                                                                              \
    do {                                                                                         \
        if (!(cond)) {                                                                           \
            printf("  line %4d: %s\n", __LINE__, #cond);                                         \
            g_failures++;                                                                        \
            return false;                                                                        \
        }                                                                                        \
    } while (0)

static bool has(const char *line, const char *token)
{
    return strstr(line, token) != NULL;
}

/* ------------------------------------------------------------------ */
/* A-W05-05 quality rules                                              */
/* ------------------------------------------------------------------ */

static cg_quality_input_t base_input(void)
{
    cg_quality_input_t in;

    memset(&in, 0, sizeof(in));
    in.probes_ok = 3;
    in.probes_expected = 3;
    in.thermal_state = CG_SRC_FRESH_OK;
    in.power_state = CG_SRC_FRESH_OK;
    in.door_state = CG_SRC_FRESH_OK;
    in.bme_state = CG_SRC_FRESH_OK;
    in.bme_present = true;
    in.thermal_age_ms = 10;
    in.thermal_age_limit_ms = 3000;
    in.power_age_ms = 10;
    in.power_age_limit_ms = 3000;
    in.door_age_ms = 10;
    in.door_age_limit_ms = 80;
    return in;
}

static bool test_all_fresh_is_valid(void)
{
    cg_quality_input_t in = base_input();
    cg_quality_set_t out;

    cg_quality_eval(&in, &out);
    CHECK(strcmp(out.thermal, "VALID") == 0);
    CHECK(strcmp(out.electrical, "VALID") == 0);
    CHECK(strcmp(out.door, "VALID") == 0);
    CHECK(strcmp(out.environment, "VALID") == 0);
    CHECK(strcmp(out.overall, "VALID") == 0);
    return true;
}

static bool test_never_observed_is_unknown_not_invalid(void)
{
    cg_quality_input_t in = base_input();
    cg_quality_set_t out;

    in.thermal_state = CG_SRC_EMPTY;
    cg_quality_eval(&in, &out);
    /* docs/01 2302-2306: an unobserved source must not be reported as a
     * determined failure, and must not be treated as normal either. */
    CHECK(strcmp(out.thermal, "UNKNOWN") == 0);
    CHECK(strcmp(out.overall, "UNKNOWN") == 0);
    return true;
}

static bool test_stale_is_invalid(void)
{
    cg_quality_input_t in = base_input();
    cg_quality_set_t out;

    in.thermal_state = CG_SRC_STALE;
    cg_quality_eval(&in, &out);
    CHECK(strcmp(out.thermal, "INVALID") == 0);
    CHECK(strcmp(out.overall, "INVALID") == 0);

    /* A caller that labels an old observation "fresh" is overridden by the age:
     * the state alone cannot hide staleness. */
    in = base_input();
    in.thermal_state = CG_SRC_FRESH_OK;
    in.thermal_age_ms = 5000;
    cg_quality_eval(&in, &out);
    CHECK(strcmp(out.thermal, "INVALID") == 0);
    return true;
}

static bool test_one_bad_probe_is_degraded(void)
{
    cg_quality_input_t in = base_input();
    cg_quality_set_t out;

    in.probes_ok = 2;
    cg_quality_eval(&in, &out);
    /* docs/01 924-942: exactly one measurement role invalid keeps a defined
     * degraded path. */
    CHECK(strcmp(out.thermal, "DEGRADED") == 0);
    CHECK(strcmp(out.overall, "DEGRADED") == 0);

    in.probes_ok = 1;
    cg_quality_eval(&in, &out);
    CHECK(strcmp(out.thermal, "INVALID") == 0);

    in.probes_ok = 0;
    cg_quality_eval(&in, &out);
    CHECK(strcmp(out.thermal, "INVALID") == 0);
    return true;
}

static bool test_failed_read_is_invalid(void)
{
    cg_quality_input_t in = base_input();
    cg_quality_set_t out;

    in.power_state = CG_SRC_FRESH_BAD;
    cg_quality_eval(&in, &out);
    CHECK(strcmp(out.electrical, "INVALID") == 0);
    CHECK(strcmp(out.overall, "INVALID") == 0);
    return true;
}

static bool test_uncommissioned_door_is_unknown(void)
{
    cg_quality_input_t in = base_input();
    cg_quality_set_t out;

    /* The MC-38 polarity is not commissioned, so a fresh raw level has no
     * OPEN/CLOSED meaning: UNKNOWN, not INVALID and definitely not VALID. */
    in.door_state = CG_SRC_FRESH_BAD;
    cg_quality_eval(&in, &out);
    CHECK(strcmp(out.door, "UNKNOWN") == 0);
    CHECK(strcmp(out.overall, "UNKNOWN") == 0);
    return true;
}

static bool test_absent_bme_is_degraded(void)
{
    cg_quality_input_t in = base_input();
    cg_quality_set_t out;

    in.bme_present = false;
    cg_quality_eval(&in, &out);
    CHECK(strcmp(out.environment, "DEGRADED") == 0);
    /* Humidity is not a chamber-air mandatory source, but its absence still
     * keeps the frame from being fully VALID. */
    CHECK(strcmp(out.overall, "DEGRADED") == 0);
    return true;
}

static bool test_collapse_order(void)
{
    cg_quality_set_t set;

    memset(&set, 0, sizeof(set));
    (void)snprintf(set.thermal, CG_SRC_NAME_LEN, "%s", "INVALID");
    (void)snprintf(set.environment, CG_SRC_NAME_LEN, "%s", "UNKNOWN");
    (void)snprintf(set.door, CG_SRC_NAME_LEN, "%s", "DEGRADED");
    (void)snprintf(set.electrical, CG_SRC_NAME_LEN, "%s", "VALID");
    /* INVALID > UNKNOWN > DEGRADED > VALID, so one determined failure names the
     * frame even while another source is merely undetermined. */
    CHECK(strcmp(cg_quality_collapse(&set), "INVALID") == 0);

    (void)snprintf(set.thermal, CG_SRC_NAME_LEN, "%s", "DEGRADED");
    CHECK(strcmp(cg_quality_collapse(&set), "UNKNOWN") == 0);

    (void)snprintf(set.environment, CG_SRC_NAME_LEN, "%s", "DEGRADED");
    CHECK(strcmp(cg_quality_collapse(&set), "DEGRADED") == 0);

    (void)snprintf(set.door, CG_SRC_NAME_LEN, "%s", "VALID");
    (void)snprintf(set.electrical, CG_SRC_NAME_LEN, "%s", "VALID");
    CHECK(strcmp(cg_quality_collapse(&set), "DEGRADED") == 0);

    /* Only an all-VALID set collapses to VALID. */
    (void)snprintf(set.thermal, CG_SRC_NAME_LEN, "%s", "VALID");
    (void)snprintf(set.environment, CG_SRC_NAME_LEN, "%s", "VALID");
    CHECK(strcmp(cg_quality_collapse(&set), "VALID") == 0);
    return true;
}

/* ------------------------------------------------------------------ */
/* A-W05-01 producer liveness                                          */
/* ------------------------------------------------------------------ */

static void periods_all(uint64_t periods[CG_PRODUCER_COUNT], uint64_t value)
{
    for (int i = 0; i < CG_PRODUCER_COUNT; i++) {
        periods[i] = value;
    }
}

static bool test_health_states(void)
{
    cg_producer_t producers[CG_PRODUCER_COUNT];
    uint64_t periods[CG_PRODUCER_COUNT];
    cg_health_report_t report;

    periods_all(periods, 1000);
    cg_health_init(producers, periods);
    cg_health_eval(producers, 5000, &report);
    CHECK(strcmp(report.overall, "NEVER") == 0);
    CHECK(report.beats[CG_PRODUCER_THERMAL] == 0U);

    cg_health_beat(producers, CG_PRODUCER_THERMAL, 5000);

    /* 1.5 periods of silence: still inside the 2x bound, so OK, but the reported
     * age is the measured gap, not the nominal period. */
    cg_health_eval(producers, 6500, &report);
    CHECK(report.state[CG_PRODUCER_THERMAL] == CG_HEALTH_OK);
    CHECK(report.gap_ms[CG_PRODUCER_THERMAL] == 1500U);
    /* One OK producer does not make the registry OK: nothing else has beaten. */
    CHECK(strcmp(report.overall, "NEVER") == 0);

    cg_health_eval(producers, 7001, &report);
    CHECK(report.state[CG_PRODUCER_THERMAL] == CG_HEALTH_LATE);

    cg_health_eval(producers, 9001, &report);
    CHECK(report.state[CG_PRODUCER_THERMAL] == CG_HEALTH_MISSED);
    CHECK(strcmp(report.overall, "MISSED") == 0);
    return true;
}

static bool test_health_never_outranks_ok(void)
{
    cg_producer_t producers[CG_PRODUCER_COUNT];
    uint64_t periods[CG_PRODUCER_COUNT];
    cg_health_report_t report;

    periods_all(periods, 1000);
    cg_health_init(producers, periods);
    cg_health_beat(producers, CG_PRODUCER_THERMAL, 0);
    cg_health_eval(producers, 100, &report);
    /* One healthy producer must not certify the whole registry: the control and
     * telemetry producers have not started yet. */
    CHECK(report.state[CG_PRODUCER_THERMAL] == CG_HEALTH_OK);
    CHECK(strcmp(report.overall, "NEVER") == 0);
    return true;
}

static bool test_health_gap_and_backwards_clock(void)
{
    cg_producer_t producers[CG_PRODUCER_COUNT];
    uint64_t periods[CG_PRODUCER_COUNT];
    cg_health_report_t report;

    periods_all(periods, 100);
    cg_health_init(producers, periods);
    cg_health_beat(producers, CG_PRODUCER_POWER, 1000);
    cg_health_beat(producers, CG_PRODUCER_POWER, 1500);
    cg_health_beat(producers, CG_PRODUCER_POWER, 1600);
    CHECK(producers[CG_PRODUCER_POWER].max_gap_ms == 500U);
    CHECK(producers[CG_PRODUCER_POWER].beats == 3U);

    cg_health_eval(producers, 1400, &report);
    /* Uptime cannot go backwards; if it appears to, the producer is not
     * trustworthy and is reported MISSED rather than OK. */
    CHECK(report.state[CG_PRODUCER_POWER] == CG_HEALTH_MISSED);
    CHECK(report.gap_ms[CG_PRODUCER_POWER] == 0U);
    return true;
}

static bool test_health_registry(void)
{
    uint64_t periods[CG_PRODUCER_COUNT];
    cg_producer_t copy[CG_PRODUCER_COUNT];
    cg_health_report_t report;

    periods_all(periods, CG_TELEMETRY_PERIOD_MS);
    cg_health_registry_init(periods);
    cg_health_registry_eval(10, &report);
    CHECK(strcmp(report.overall, "NEVER") == 0);

    cg_health_registry_beat(CG_PRODUCER_THERMAL, 20);
    cg_health_registry_copy(copy);
    CHECK(copy[CG_PRODUCER_THERMAL].beats == 1U);
    CHECK(copy[CG_PRODUCER_THERMAL].period_ms == (uint64_t)CG_TELEMETRY_PERIOD_MS);

    /* An out-of-range id must be ignored, not wrap into another producer. */
    cg_health_registry_beat((cg_producer_id_t)CG_PRODUCER_COUNT, 30);
    cg_health_registry_copy(copy);
    CHECK(copy[CG_PRODUCER_THERMAL].beats == 1U);
    return true;
}

/* ------------------------------------------------------------------ */
/* A-W05-02/-04/-05 telemetry frame                                    */
/* ------------------------------------------------------------------ */

typedef struct {
    cg_tec_control_t ctl;
    cg_snapshot_t snap;
    cg_health_report_t health;
    cg_telemetry_frame_t frame;
    char run_id[33];
} fixture_t;

static void fixture_init(fixture_t *fx)
{
    static const char roms[CG_ROLE_COUNT][CG_TELEM_ROM_HEX_LEN] = {
        "287088CA00000051", "28AEBF2200000006", "28CBE9CA00000072", "283BE5C9000000A9"};

    memset(fx, 0, sizeof(*fx));
    fx->snap.thermal_observed = true;
    fx->snap.thermal_valid = true;
    fx->snap.thermal_quality = CG_QUALITY_VALID;
    fx->snap.thermal_obs_ms = 999000U;
    fx->snap.thermal_seq = 42U;
    fx->snap.probes_ok = 3;
    fx->snap.probes_expected = 3;
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        fx->snap.t_valid[role] = true;
        fx->snap.t_c[role] = 25.0625f;
    }
    fx->snap.power_observed = true;
    fx->snap.power_valid = true;
    fx->snap.power_obs_ms = 999500U;
    fx->snap.power_seq = 999U;
    fx->snap.voltage_v = 11.9f;
    fx->snap.current_a = 0.0f;
    fx->snap.power_w = 0.0f;
    fx->snap.energy_wh = 12.0f;
    fx->snap.door_observed = true;
    fx->snap.door_known = false;
    fx->snap.door_raw = 1;
    fx->snap.door_obs_ms = 999990U;
    (void)snprintf(fx->run_id, sizeof(fx->run_id), "%s", "CG-S1-A-001");
    /* Consistent with cg_health_eval(): no producer has beaten yet, so the
     * worst-rank overall is NEVER. The fixture must not show overall=OK with
     * every producer NEVER - that is a state the firmware cannot produce. */
    (void)snprintf(fx->health.overall, sizeof(fx->health.overall), "%s", "NEVER");

    fx->ctl.state = CG_TEC_STATE_OFF;
    (void)snprintf(fx->ctl.reason, sizeof(fx->ctl.reason), "%s", "BOOT_SAFE_OFF");
    fx->frame.seq = 1U;
    fx->frame.boot_id = "abcd0123";
    fx->frame.boot_count = 7;
    fx->frame.uptime_ms = 1000000U;
    fx->frame.run_id = fx->run_id;
    fx->frame.test_phase = "IDLE";
    fx->frame.snap = &fx->snap;
    fx->frame.ctl = &fx->ctl;
    fx->frame.health = &fx->health;
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        fx->frame.probe_rom[role] = roms[role];
    }
    fx->frame.role_status = CG_ROM_STATUS;
    fx->frame.output_stage_enabled = false;
    fx->frame.fan_available = false;
}

static size_t render(fixture_t *fx, char *line, size_t cap)
{
    return cg_telemetry_format(line, cap, &fx->frame);
}

static bool test_identity_fields_are_present(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "schema=2 "));
    CHECK(has(line, "device_id=coldguard-001 "));
    CHECK(has(line, "seq=1 "));
    CHECK(has(line, "boot_id=abcd0123 "));
    CHECK(has(line, "calibration_id=UNRECORDED "));
    CHECK(has(line, "hardware_config_id=CG-HW-001 "));
    CHECK(has(line, "firmware_version=" CG_FIRMWARE_VERSION " "));
    CHECK(has(line, "t1_rom=287088CA00000051 "));
    CHECK(has(line, "t2_rom=28AEBF2200000006 "));
    CHECK(has(line, "role_status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING "));
    /* The device still has no wall clock; W05 must not introduce one. */
    CHECK(has(line, "timestamp_utc=UNAVAILABLE "));
    CHECK(!has(line, "timestamp_utc=20"));
    return true;
}

static bool test_coherence_fields_are_present(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "thermal_age_ms=1000 "));
    CHECK(has(line, "power_age_ms=500 "));
    CHECK(has(line, "thermal_seq=42 "));
    CHECK(has(line, "power_seq=999 "));
    CHECK(has(line, "probes_valid=3 probes_expected=3"));
    return true;
}

static bool test_door_age_is_reported(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    /* 1000000 - 999990 = 10 ms, inside the 4-period door bound. */
    CHECK(has(line, "door_age_ms=10 "));
    CHECK(has(line, "door_quality=UNKNOWN"));
    return true;
}

static bool test_stale_power_ages_saturate(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    fx.snap.power_obs_ms = 0U; /* last publication at boot, long ago */
    fx.snap.power_observed = true;
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "power_age_ms=1000000 "));
    CHECK(has(line, "electrical_quality=INVALID"));
    CHECK(has(line, "current_status=STALE"));
    /* A stale electrical observation must not be presented as an observed idle
     * branch. */
    CHECK(has(line, "cooling_evidence=UNOBSERVED_STALE"));
    return true;
}

static bool test_backwards_clock_saturates(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    fx.frame.uptime_ms = 500000U; /* below the observation times */
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "thermal_age_ms=18446744073709551615"));
    CHECK(has(line, "thermal_status=STALE") || has(line, "t_inside_status=STALE"));
    CHECK(has(line, "thermal_quality=INVALID"));
    return true;
}

static bool test_quality_vocabulary_in_line(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "thermal_quality=VALID "));
    CHECK(has(line, "environment_quality=DEGRADED "));
    CHECK(has(line, "door_quality=UNKNOWN "));
    CHECK(has(line, "electrical_quality=VALID "));
    CHECK(has(line, "quality=UNKNOWN"));
    return true;
}

static bool test_applied_state_is_not_the_request(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    /* Nothing energized, zero measured current: consistent idle. */
    fx.ctl.outputs_energized = false;
    fx.snap.current_a = 0.0f;
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "cooling_applied=OFF "));
    CHECK(has(line, "cooling_applied_source=FIRMWARE_OUTPUT_STATE "));
    CHECK(has(line, "cooling_evidence=MEASURED_IDLE_AND_ZERO"));

    /* Duty requested but the output layer never engaged: the line must still
     * say OFF, because the applied state is not the request. */
    fx.frame.ctl = &fx.ctl;
    fx.ctl.duty_permille = 250U;
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "pwm_duty=250 "));
    CHECK(has(line, "cooling_applied=OFF "));

    /* Outputs driven with no measured current: a contradiction, not an OFF. */
    fx.ctl.outputs_energized = true;
    fx.snap.current_a = 0.0f;
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "cooling_applied=ON "));
    CHECK(has(line, "cooling_evidence=MEASURED_CONTRADICTS_APPLIED"));

    /* Idle outputs with measured current: also a contradiction. */
    fx.ctl.outputs_energized = false;
    fx.snap.current_a = 3.5f;
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "cooling_evidence=MEASURED_CONTRADICTS_APPLIED"));

    fx.snap.current_a = 4.25f;
    fx.ctl.outputs_energized = true;
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "cooling_evidence=MEASURED_APPLIED_AND_DRAWING"));
    return true;
}

static bool test_no_electrical_observation_is_unobserved(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    fx.snap.power_observed = false;
    fx.snap.power_valid = false;
    fx.ctl.outputs_energized = true;
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "cooling_evidence=UNOBSERVED_NO_DATA"));
    CHECK(has(line, "electrical_quality=UNKNOWN"));
    return true;
}

static bool test_missing_thermal_is_unknown_not_invalid(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    fx.snap.thermal_observed = false;
    fx.snap.thermal_valid = false;
    memset(fx.snap.t_valid, 0, sizeof(fx.snap.t_valid));
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "t_inside_status=NO_DATA"));
    CHECK(has(line, "thermal_quality=UNKNOWN"));
    CHECK(has(line, "sensor_validity=NO_DATA"));
    return true;
}

static bool test_energy_is_published(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "energy_wh=12.0000 energy_status=OK"));
    return true;
}

static bool test_health_absent_is_unknown(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    fx.frame.health = NULL;
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    /* No liveness report is not a healthy device. */
    CHECK(has(line, "health=UNKNOWN "));
    CHECK(has(line, "health_thermal=UNKNOWN "));
    CHECK(has(line, "health_control=UNKNOWN"));
    CHECK(!has(line, "thermal_beats="));
    return true;
}

static bool test_liveness_and_counters_are_published(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    fx.health.state[CG_PRODUCER_THERMAL] = CG_HEALTH_MISSED;
    fx.health.beats[CG_PRODUCER_THERMAL] = 3U;
    fx.health.max_gap_ms[CG_PRODUCER_THERMAL] = 7000U;
    (void)snprintf(fx.health.overall, sizeof(fx.health.overall), "%s", "MISSED");
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "health=MISSED "));
    CHECK(has(line, "health_thermal=MISSED "));
    CHECK(has(line, "thermal_beats=3 "));
    CHECK(has(line, "thermal_max_gap_ms=7000"));
    return true;
}

static bool test_unread_rom_is_named(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    fx.frame.probe_rom[CG_ROLE_SPARE] = NULL;
    fx.frame.role_status = NULL;
    CHECK(render(&fx, line, sizeof(line)) > 0U);
    CHECK(has(line, "spare_rom=UNREAD"));
    CHECK(has(line, "role_status=UNREAD"));
    return true;
}

static size_t g_worst_case_len;

static bool test_worst_case_fits_the_budget(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];
    size_t len;

    fixture_init(&fx);
    /* Every variable-width token at its widest: 10-digit seqs, 20-digit ages,
     * the longest reason/state/quality names, a full 32-character run id. */
    memset(fx.run_id, 'A', 32);
    fx.run_id[32] = '\0';
    fx.frame.seq = 4294967295U;
    fx.frame.boot_count = 4294967295U;
    fx.frame.uptime_ms = 18446744073709551615ULL;
    fx.frame.test_phase = "TEC_COOLING";
    fx.snap.thermal_seq = 4294967295U;
    fx.snap.power_seq = 4294967295U;
    fx.snap.door_transitions = 4294967295U;
    fx.snap.door_cycles = 2147483647U;
    fx.snap.voltage_v = -1234.5678f;
    fx.snap.current_a = -1234.5678f;
    fx.snap.power_w = -1234.5678f;
    fx.snap.energy_wh = 12345678.0f;
    fx.snap.t_c[CG_ROLE_T1] = -123.4567f;
    (void)snprintf(fx.ctl.reason, sizeof(fx.ctl.reason), "%s", "ESTOP_LATCHED_WAITING_CLEAR");
    for (int i = 0; i < CG_PRODUCER_COUNT; i++) {
        fx.health.state[i] = CG_HEALTH_MISSED;
        fx.health.beats[i] = 4294967295U;
        fx.health.max_gap_ms[i] = 4294967295U;
    }
    (void)snprintf(fx.health.overall, sizeof(fx.health.overall), "%s", "MISSED");

    len = render(&fx, line, sizeof(line));
    g_worst_case_len = len;
    printf("  worst_case_len=%zu budget=%d\n", len, CG_TELEMETRY_LINE_MAX);
    CHECK(len > 0U);
    CHECK(len < (size_t)CG_TELEMETRY_LINE_MAX);
    CHECK(has(line, " raw_spare_status=")); /* tail token intact */
    CHECK(line[len - 1] != ' ');
    return true;
}

static bool test_overflow_refuses_whole_line(void)
{
    fixture_t fx;
    char small[64];

    fixture_init(&fx);
    CHECK(cg_telemetry_format(small, sizeof(small), &fx.frame) == 0U);
    CHECK(small[0] == '\0');
    return true;
}

static bool test_zero_cap_and_missing_strings(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    CHECK(cg_telemetry_format(line, 0U, &fx.frame) == 0U);
    fx.frame.boot_id = NULL;
    CHECK(cg_telemetry_format(line, sizeof(line), &fx.frame) == 0U);
    fx.frame.boot_id = fx.run_id;
    fx.frame.run_id = NULL;
    CHECK(cg_telemetry_format(line, sizeof(line), &fx.frame) == 0U);
    return true;
}

/* ------------------------------------------------------------------ */
/* End-to-end: the REAL publication path, not a hand-written snapshot   */
/* ------------------------------------------------------------------ */

/* These scenarios exist because an earlier revision of this harness wrote
 * cg_snapshot_t fields directly. That bypassed cg_snapshot_publish_thermal()
 * and hid a defect in which the probe counts were never copied into the
 * snapshot, so every real frame reported probes_valid=0 and
 * thermal_quality=UNKNOWN. Driving the publish/read copy is the only way to
 * cover that class of bug on the host. */

static size_t render_from_publication(char *line, size_t cap, uint32_t probe_ok,
                                      uint8_t quality, bool power_valid, bool door_known,
                                      uint64_t door_obs_ms, float energy_wh)
{
    cg_thermal_snapshot_t thermal;
    cg_snapshot_t snap;
    cg_tec_control_t ctl;
    cg_health_report_t health;
    cg_telemetry_frame_t frame;
    static const char roms[CG_ROLE_COUNT][CG_TELEM_ROM_HEX_LEN] = {
        "287088CA00000051", "28AEBF2200000006", "28CBE9CA00000072", "283BE5C9000000A9"};

    cg_snapshot_init();
    memset(&thermal, 0, sizeof(thermal));
    memset(&ctl, 0, sizeof(ctl));
    memset(&health, 0, sizeof(health));
    memset(&frame, 0, sizeof(frame));

    thermal.measurement_expected = 3;
    thermal.measurement_ok = (uint8_t)probe_ok;
    thermal.quality = (cg_thermal_quality_t)quality;
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        thermal.probe[role].valid = (uint32_t)role < probe_ok || role == CG_ROLE_SPARE;
        thermal.probe[role].celsius = 25.0625f;
    }
    cg_snapshot_publish_thermal(&thermal, 7U, 999000U);
    cg_snapshot_publish_power(power_valid, power_valid ? 11.9f : 0.0f,
                              power_valid ? 0.0f : 0.0f, power_valid ? 0.0f : 0.0f,
                              energy_wh, 33U, 999500U);
    cg_snapshot_publish_door(door_known, false, 1, door_obs_ms, 2U, 1U);
    cg_snapshot_read(&snap);

    ctl.state = CG_TEC_STATE_OFF;
    (void)snprintf(ctl.reason, sizeof(ctl.reason), "%s", "BOOT_SAFE_OFF");
    (void)snprintf(health.overall, sizeof(health.overall), "%s", "OK");

    frame.seq = 5U;
    frame.boot_id = "abcd0123";
    frame.boot_count = 7;
    frame.uptime_ms = 1000000U;
    frame.run_id = "CG-S1-A-001";
    frame.test_phase = "IDLE";
    frame.snap = &snap;
    frame.ctl = &ctl;
    frame.health = &health;
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        frame.probe_rom[role] = roms[role];
    }
    frame.role_status = CG_ROM_STATUS;
    return cg_telemetry_format(line, cap, &frame);
}

static bool test_publication_copies_probe_counts(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    CHECK(render_from_publication(line, sizeof(line), 3U, CG_QUALITY_VALID, true, true,
                                 999990U, 12.0f) > 0U);
    /* The defect this scenario exists for: without the copy the frame would say
     * probes_valid=0 probes_expected=0 and collapse chamber air to UNKNOWN. */
    CHECK(has(line, " probes_valid=3 probes_expected=3"));
    CHECK(has(line, "thermal_quality=VALID "));
    CHECK(has(line, "thermal_seq=7 "));
    CHECK(has(line, "power_seq=33 "));
    CHECK(has(line, "door_transitions=2 door_cycles=1"));
    CHECK(has(line, "rom_source=FROZEN_CONFIG_MAP"));
    return true;
}

static bool test_degraded_is_reachable_through_publication(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    /* One failed measurement role: the driver sets quality=DEGRADED and
     * thermal_valid=false (the control gate stays strict). The quality layer
     * must still name DEGRADED - docs/01 924-942. */
    CHECK(render_from_publication(line, sizeof(line), 2U, CG_QUALITY_DEGRADED, true, true,
                                 999990U, 12.0f) > 0U);
    CHECK(has(line, "thermal_quality=DEGRADED"));
    CHECK(has(line, " probes_valid=2 probes_expected=3"));

    /* Two failed roles: INVALID, and the collapse must follow. */
    CHECK(render_from_publication(line, sizeof(line), 1U, CG_QUALITY_INVALID, true, true,
                                 999990U, 12.0f) > 0U);
    CHECK(has(line, "thermal_quality=INVALID"));
    return true;
}

static bool test_failed_power_poll_through_publication(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    CHECK(render_from_publication(line, sizeof(line), 3U, CG_QUALITY_VALID, false, true,
                                 999990U, 0.0f) > 0U);
    CHECK(has(line, "electrical_quality=INVALID"));
    CHECK(has(line, "current_status=INVALID"));
    /* A failed decode is not evidence about the branch, so it must not be
     * reported as a measured zero. */
    CHECK(has(line, "cooling_evidence=MEASURED_CONTRADICTS_APPLIED") == 0);
    CHECK(!has(line, "cooling_evidence=MEASURED_IDLE_AND_ZERO"));
    return true;
}

static bool test_door_staleness_through_publication(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    /* Door published at 900000 while the frame clock is 1000000: 100 s old, far
     * past the 80 ms bound, so the age overrides any freshness claim. */
    CHECK(render_from_publication(line, sizeof(line), 3U, CG_QUALITY_VALID, true, true,
                                 900000U, 12.0f) > 0U);
    CHECK(has(line, "door_age_ms=100000 "));
    CHECK(has(line, "door_quality=INVALID"));
    return true;
}

static bool test_max_register_energy_renders_in_full(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    /* 4294967295 Wh is the widest value the PZEM energy registers can decode.
     * Rendered as %.4f it is 16 characters, which did NOT fit the 16-byte field
     * the W04 formatter used: the value would have been cut mid-digit. The
     * buffers are 24 bytes now, so the full register range must appear intact. */
    CHECK(render_from_publication(line, sizeof(line), 3U, CG_QUALITY_VALID, true, true,
                                 999990U, 4294967295.0f) > 0U);
    CHECK(has(line, "energy_wh=4294967296.0000 energy_status=OK"));
    return true;
}

/* ------------------------------------------------------------------ */

typedef struct {
    const char *name;
    bool (*fn)(void);
} test_case_t;

size_t cg_w05_worst_case_len(void);

size_t cg_w05_worst_case_len(void)
{
    return g_worst_case_len;
}

int main(void)
{
    const test_case_t tests[] = {
        {"all_fresh_is_valid", test_all_fresh_is_valid},
        {"never_observed_is_unknown_not_invalid", test_never_observed_is_unknown_not_invalid},
        {"stale_is_invalid", test_stale_is_invalid},
        {"one_bad_probe_is_degraded", test_one_bad_probe_is_degraded},
        {"failed_read_is_invalid", test_failed_read_is_invalid},
        {"uncommissioned_door_is_unknown", test_uncommissioned_door_is_unknown},
        {"absent_bme_is_degraded", test_absent_bme_is_degraded},
        {"collapse_order", test_collapse_order},
        {"health_states", test_health_states},
        {"health_never_outranks_ok", test_health_never_outranks_ok},
        {"health_gap_and_backwards_clock", test_health_gap_and_backwards_clock},
        {"health_registry", test_health_registry},
        {"identity_fields_are_present", test_identity_fields_are_present},
        {"coherence_fields_are_present", test_coherence_fields_are_present},
        {"door_age_is_reported", test_door_age_is_reported},
        {"stale_power_ages_saturate", test_stale_power_ages_saturate},
        {"backwards_clock_saturates", test_backwards_clock_saturates},
        {"quality_vocabulary_in_line", test_quality_vocabulary_in_line},
        {"applied_state_is_not_the_request", test_applied_state_is_not_the_request},
        {"no_electrical_observation_is_unobserved", test_no_electrical_observation_is_unobserved},
        {"missing_thermal_is_unknown_not_invalid", test_missing_thermal_is_unknown_not_invalid},
        {"energy_is_published", test_energy_is_published},
        {"health_absent_is_unknown", test_health_absent_is_unknown},
        {"liveness_and_counters_are_published", test_liveness_and_counters_are_published},
        {"unread_rom_is_named", test_unread_rom_is_named},
        {"publication_copies_probe_counts", test_publication_copies_probe_counts},
        {"degraded_is_reachable_through_publication",
         test_degraded_is_reachable_through_publication},
        {"failed_power_poll_through_publication", test_failed_power_poll_through_publication},
        {"door_staleness_through_publication", test_door_staleness_through_publication},
        {"max_register_energy_renders_in_full",
         test_max_register_energy_renders_in_full},
        {"worst_case_fits_the_budget", test_worst_case_fits_the_budget},
        {"overflow_refuses_whole_line", test_overflow_refuses_whole_line},
        {"zero_cap_and_missing_strings", test_zero_cap_and_missing_strings},
    };
    const int total = (int)(sizeof(tests) / sizeof(tests[0]));
    int passed = 0;

    for (int i = 0; i < total; i++) {
        const int before = g_failures;
        const bool ok = tests[i].fn();
        if (ok && g_failures == before) {
            passed++;
            printf("PASS %s\n", tests[i].name);
        } else {
            printf("FAIL %s\n", tests[i].name);
        }
    }

    printf("\n%d/%d W05 scenarios passed\n", passed, total);
    if (passed != total) {
        return 1;
    }

    /* One realistic frame, printed verbatim so the Python schema tests parse the
     * bytes the formatter actually produces instead of a hand-written imitation.
     * This is the source of evidence/A/W05/schema-fixture.json. */
    {
        fixture_t fx;
        char line[CG_TELEMETRY_LINE_MAX];

        fixture_init(&fx);
        if (render(&fx, line, sizeof(line)) > 0U) {
            printf("FIXTURE_V2 %s\n", line);
        } else {
            printf("FIXTURE_V2_RENDER_REFUSED\n");
            return 1;
        }
    }
    printf("W05 TELEMETRY FOUNDATION: ALL SCENARIOS PASS\n");
    return 0;
}
