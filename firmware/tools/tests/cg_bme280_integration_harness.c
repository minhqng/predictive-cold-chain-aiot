/*
 * Host harness for the BME280 producer's firmware integration (A-W02-06).
 *
 * cg_bme280_harness.c proves the decision logic against a scripted port. This
 * file proves the half that only exists once the producer is wired in: the real
 * publication path, the real snapshot copy, the real quality evaluation and the
 * real telemetry formatter. The scenarios assert the ambient channel through
 * the same four states the device can actually be in - never sampled, absent,
 * fresh and valid, fresh but refused, and stale - because each of those must
 * reach the serial line with a different name and, critically, must never reach
 * it carrying a number the producer did not measure.
 *
 * Built by firmware/tools/tests/test_cg_bme280_integration.py against the
 * unchanged firmware/main sources.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cg_bme280.h"
#include "cg_health.h"
#include "cg_quality.h"
#include "cg_snapshot.h"
#include "cg_tec_control.h"
#include "cg_tec_limits.h"
#include "cg_telemetry.h"
#include "coldguard_config.h"

/* Same stub the W05 harness uses: cg_ds18b20.c pulls in the OneWire driver and
 * is not part of a host build, and cg_telemetry.c only needs the thermal label
 * helper to link. Every scenario here keeps thermal_quality=VALID, so a fixed
 * label cannot mask an ambient result. */
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

/* Renders one TELEM line after driving the real snapshot publication path.
 * `env_mode` selects the ambient state under test. */
typedef enum {
    ENV_NEVER = 0,   /* the producer task has not completed a cycle            */
    ENV_ABSENT,      /* a cycle completed and no module acknowledges the bus   */
    ENV_FRESH_OK,    /* a module answered with a reading inside range          */
    ENV_REFUSED,     /* a module answered but the reading was rejected         */
    ENV_STALE        /* a module answered once and has not been heard since    */
} env_mode_t;

static size_t render(char *line, size_t cap, env_mode_t env_mode)
{
    cg_thermal_snapshot_t thermal;
    cg_snapshot_t snap;
    cg_tec_control_t ctl;
    cg_health_report_t health;
    cg_telemetry_frame_t frame;
    uint64_t env_obs_ms;
    bool env_present;
    bool env_valid;
    static const char roms[CG_ROLE_COUNT][CG_TELEM_ROM_HEX_LEN] = {
        "287088CA00000051", "28AEBF2200000006", "28CBE9CA00000072", "283BE5C9000000A9"};

    cg_snapshot_init();
    memset(&thermal, 0, sizeof(thermal));
    memset(&ctl, 0, sizeof(ctl));
    memset(&health, 0, sizeof(health));
    memset(&frame, 0, sizeof(frame));

    thermal.measurement_expected = 3;
    thermal.measurement_ok = 3;
    thermal.quality = CG_QUALITY_VALID;
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        thermal.probe[role].valid = true;
        thermal.probe[role].celsius = 25.0625f;
    }
    /* Everything except the ambient channel is deliberately healthy, so a name
     * change in the output can only have come from the mode under test. */
    cg_snapshot_publish_thermal(&thermal, 7U, 999000U);
    cg_snapshot_publish_power(true, 11.9f, 0.0f, 0.0f, 12.0f, 33U, 999500U);
    cg_snapshot_publish_door(true, false, 1, 999990U, 2U, 1U);

    env_obs_ms = 999999U;
    env_present = true;
    env_valid = true;
    switch (env_mode) {
        case ENV_NEVER:
            break; /* publish nothing at all: the channel was never observed */
        case ENV_ABSENT:
            env_present = false;
            env_valid = false;
            cg_snapshot_publish_env(false, false, 0.0f, 0.0f, (uint8_t)CG_BME_STATE_ABSENT,
                                    (uint8_t)CG_BME_READ_ABSENT, 0x76U, 0U, env_obs_ms);
            break;
        case ENV_FRESH_OK:
            cg_snapshot_publish_env(true, true, 30.41f, 68.51f, (uint8_t)CG_BME_STATE_READY,
                                    (uint8_t)CG_BME_READ_OK, 0x76U, 14U, env_obs_ms);
            break;
        case ENV_REFUSED:
            env_valid = false;
            cg_snapshot_publish_env(true, false, 30.41f, 68.51f, (uint8_t)CG_BME_STATE_FAULT,
                                    (uint8_t)CG_BME_READ_OUT_OF_RANGE, 0x76U, 14U, env_obs_ms);
            break;
        case ENV_STALE:
            /* Older than the ambient freshness bound by construction, so the
             * bound itself is what the scenario pins. */
            env_obs_ms = 1000000U - (uint64_t)CG_TELEM_STALE_ENV_MS - 5000U;
            cg_snapshot_publish_env(true, true, 30.41f, 68.51f, (uint8_t)CG_BME_STATE_READY,
                                    (uint8_t)CG_BME_READ_OK, 0x76U, 14U, env_obs_ms);
            break;
    }
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

static bool test_never_observed_ambient_is_not_a_measurement(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    CHECK(render(line, sizeof(line), ENV_NEVER) > 0U);
    /* No cycle has completed, so there is no measurement and no number. The
     * group is reported DEGRADED rather than UNKNOWN because
     * `environment_quality` is part of the vocabulary Members B and C parse,
     * and splitting "known absent" from "not asked yet" changes that shared
     * contract - it is raised as a handoff decision, not taken here. What this
     * scenario pins is the part Member A owns: the channel must never reach the
     * line with a value it did not measure. */
    CHECK(has(line, "t_ambient_status=NO_DATA"));
    CHECK(has(line, "relative_humidity_status=NO_DATA"));
    CHECK(has(line, "t_ambient_c=" CG_INVALID_VALUE_TOKEN));
    CHECK(has(line, "environment_quality=DEGRADED"));
    return true;
}

static bool test_absent_module_is_a_fact_not_a_failure(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    CHECK(render(line, sizeof(line), ENV_ABSENT) > 0U);
    /* A definitive "no device at this address" is a configuration fact, so the
     * value is missing but the group is DEGRADED rather than UNKNOWN or
     * INVALID - and the seq stays 0 because a refusal mints no sequence. */
    CHECK(has(line, "t_ambient_status=" CG_TELEM_STATUS_NOT_PRESENT));
    CHECK(has(line, "relative_humidity_status=" CG_TELEM_STATUS_NOT_PRESENT));
    CHECK(has(line, "t_ambient_c=" CG_INVALID_VALUE_TOKEN));
    CHECK(has(line, "environment_quality=DEGRADED"));
    return true;
}

static bool test_fresh_ambient_publishes_measured_values(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    CHECK(render(line, sizeof(line), ENV_FRESH_OK) > 0U);
    CHECK(has(line, "t_ambient_status=OK"));
    CHECK(has(line, "relative_humidity_status=OK"));
    CHECK(has(line, "t_ambient_c=30.41"));
    CHECK(has(line, "relative_humidity_pct=68.51"));
    CHECK(has(line, "environment_quality=VALID"));
    CHECK(!has(line, "t_ambient_c=" CG_INVALID_VALUE_TOKEN));
    return true;
}

static bool test_refused_reading_never_reaches_the_line(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    CHECK(render(line, sizeof(line), ENV_REFUSED) > 0U);
    /* The producer holds a temperature and humidity from an earlier framing of
     * the same transaction; a refused cycle must still publish neither of them.
     * This is docs/01's rule that a value the device did not measure cannot
     * stand in for one it did. */
    CHECK(has(line, "t_ambient_status=INVALID"));
    CHECK(has(line, "t_ambient_c=" CG_INVALID_VALUE_TOKEN));
    CHECK(has(line, "relative_humidity_pct=" CG_INVALID_VALUE_TOKEN));
    CHECK(!has(line, "30.41"));
    CHECK(!has(line, "68.51"));
    return true;
}

static bool test_stale_ambient_loses_its_number(void)
{
    char line[CG_TELEMETRY_LINE_MAX];

    CHECK(render(line, sizeof(line), ENV_STALE) > 0U);
    /* Present and once-valid, but past the freshness bound: the reading is a
     * determined failure of freshness, so it names INVALID at the quality layer
     * and STALE at the field, and the number disappears rather than being
     * carried forward as the current room temperature. */
    CHECK(has(line, "t_ambient_status=STALE"));
    CHECK(has(line, "t_ambient_c=" CG_INVALID_VALUE_TOKEN));
    CHECK(has(line, "relative_humidity_pct=" CG_INVALID_VALUE_TOKEN));
    CHECK(has(line, "environment_quality=INVALID"));
    CHECK(!has(line, "30.41"));
    return true;
}

static bool test_absent_still_advances_the_observation_time(void)
{
    /* The producer beats and timestamps an absence, so liveness and presence
     * stay separable downstream: a quiet module must not be mistaken for a
     * crashed producer, and a crashed producer must not be mistaken for a quiet
     * module. The snapshot is what carries that separation. */
    cg_snapshot_t snap;
    uint64_t first;

    cg_snapshot_init();
    cg_snapshot_publish_env(false, false, 0.0f, 0.0f, (uint8_t)CG_BME_STATE_ABSENT,
                            (uint8_t)CG_BME_READ_ABSENT, 0x76U, 0U, 5000U);
    cg_snapshot_read(&snap);
    CHECK(snap.env_observed);
    CHECK(!snap.env_present);
    CHECK(!snap.env_valid);
    first = snap.env_obs_ms;

    cg_snapshot_publish_env(false, false, 0.0f, 0.0f, (uint8_t)CG_BME_STATE_ABSENT,
                            (uint8_t)CG_BME_READ_ABSENT, 0x76U, 0U, 6000U);
    cg_snapshot_read(&snap);
    CHECK(snap.env_obs_ms > first);
    CHECK(snap.env_seq == 0U);
    return true;
}

static bool test_driver_state_names_are_distinct(void)
{
    /* Five states, five names: the log line is evidence only if a reader can
     * tell which of them the producer was in. */
    CHECK(strcmp(cg_bme280_state_name(CG_BME_STATE_ABSENT), "ABSENT") == 0);
    CHECK(strcmp(cg_bme280_state_name(CG_BME_STATE_UNPROBED), "UNPROBED") == 0);
    CHECK(strcmp(cg_bme280_state_name(CG_BME_STATE_READY), "READY") == 0);
    CHECK(strcmp(cg_bme280_state_name(CG_BME_STATE_FAULT), "FAULT") == 0);
    CHECK(strcmp(cg_bme280_state_name(CG_BME_STATE_IDENTITY_BAD), "IDENTITY_BAD") == 0);
    CHECK(strcmp(cg_bme280_read_result_name(CG_BME_READ_IM_NOT_READY), "IM_NOT_READY") == 0);
    return true;
}

typedef bool (*test_fn)(void);

typedef struct {
    const char *name;
    test_fn fn;
} test_case_t;

static const test_case_t k_tests[] = {
    {"never_observed_ambient_is_not_a_measurement",
     test_never_observed_ambient_is_not_a_measurement},
    {"absent_module_is_a_fact_not_a_failure", test_absent_module_is_a_fact_not_a_failure},
    {"fresh_ambient_publishes_measured_values", test_fresh_ambient_publishes_measured_values},
    {"refused_reading_never_reaches_the_line", test_refused_reading_never_reaches_the_line},
    {"stale_ambient_loses_its_number", test_stale_ambient_loses_its_number},
    {"absent_still_advances_the_observation_time", test_absent_still_advances_the_observation_time},
    {"driver_state_names_are_distinct", test_driver_state_names_are_distinct},
};

int main(void)
{
    size_t i;
    int failed = 0;

    for (i = 0; i < sizeof(k_tests) / sizeof(k_tests[0]); i++) {
        g_failures = 0;
        if (!k_tests[i].fn() || g_failures != 0) {
            printf("FAIL %s\n", k_tests[i].name);
            failed++;
        } else {
            printf("ok   %s\n", k_tests[i].name);
        }
    }
    if (failed != 0) {
        printf("BME280 INTEGRATION HARNESS: %d SCENARIO(S) FAILED\n", failed);
        return 1;
    }
    printf("BME280 INTEGRATION HARNESS: ALL SCENARIOS PASS\n");
    return 0;
}
