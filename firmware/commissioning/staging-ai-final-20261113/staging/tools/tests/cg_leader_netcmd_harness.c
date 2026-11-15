/*
 * Host harness for the Leader netcmd ingress (integration component).
 *
 * Links the real, unchanged W06 member sources (cg_command.c, cg_telemetry.c,
 * cg_snapshot.c, cg_tec_command.c plus the control core) together with the
 * Leader core (cg_leader_ingress_core.c) and asserts, offline:
 *
 * - envelope routing (exactly the "#CG CMD " form, never a delivered verb);
 * - the receiving-layer source classification (NETWORK) and the unchanged
 *   delivered §29 chain behind it, through a handler that can pin no other
 *   world than the shipped one;
 * - the idempotency memory and the not-stored rule of a target mismatch;
 * - the world observation from the device's own TELEM stream, including the
 *   no-self-pollution rule (an ACK never becomes the world it answered) and
 *   the complete-view policy that keeps a partial line from regressing a
 *   good previous observation;
 * - the record-capacity parity the reader task relies on.
 *
 * Nothing here is a physical actuation. The shipped world cannot accept a
 * canonical command (no wall clock), and the harness pins that as the
 * observable outcome of the ingress on the delivered build.
 *
 * Exit code: 0 when every scenario passes, 1 otherwise.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#include "cg_leader_ingress.h"
#include "cg_command.h"
#include "cg_snapshot.h"
#include "coldguard_config.h"

/* cg_ds18b20.c is device-only; the telemetry formatter needs the name only. */
const char *cg_quality_name(cg_thermal_quality_t quality)
{
    (void)quality;
    return "VALID";
}

/* Host capture of the delivered log primitives (cg_log.c is device-linked
 * and stdout has no place in a scenario): raw lines are the device's
 * published stream (the TELEM observer sees these too, so a scenario that
 * feeds telemetry clears the capture first), fmt/err lines are the
 * cg_log_line / cg_log_error evidence. */
#define CG_HARNESS_CAPTURE 8
#define CG_HARNESS_RAW_CAP CG_COMMAND_ACK_LINE_MAX
#define CG_HARNESS_FMT_CAP 256

static char g_raw[CG_HARNESS_CAPTURE][CG_HARNESS_RAW_CAP];
static int g_raw_count;
static char g_fmt[CG_HARNESS_CAPTURE][CG_HARNESS_FMT_CAP];
static int g_fmt_count;
static char g_err[CG_HARNESS_CAPTURE][CG_HARNESS_FMT_CAP];
static int g_err_count;

void cg_log_line(const char *fmt, ...)
{
    va_list args;

    va_start(args, fmt);
    (void)vsnprintf(g_fmt[g_fmt_count++ % CG_HARNESS_CAPTURE],
                    sizeof(g_fmt[0]), fmt, args);
    va_end(args);
}

void cg_log_error(const char *fmt, ...)
{
    va_list args;

    va_start(args, fmt);
    (void)vsnprintf(g_err[g_err_count++ % CG_HARNESS_CAPTURE],
                    sizeof(g_err[0]), fmt, args);
    va_end(args);
}

bool cg_log_raw_line(const char *line)
{
    if (line == NULL) {
        return false;
    }
    (void)snprintf(g_raw[g_raw_count++ % CG_HARNESS_CAPTURE],
                   sizeof(g_raw[0]), "%s", line);
    return true;
}

static int g_failures;

#define CHECK(cond)                                                                          \
    do {                                                                                     \
        if (!(cond)) {                                                                       \
            printf("  line %4d: %s\n", __LINE__, #cond);                                     \
            g_failures++;                                                                    \
            return false;                                                                    \
        }                                                                                    \
    } while (0)

#define UUID_A "00000000-0000-4000-8000-00000000000a"
#define UUID_B "00000000-0000-4000-8000-00000000000b"

static bool has_raw(const char *token)
{
    for (int i = 0; i < CG_HARNESS_CAPTURE; i++) {
        if (g_raw[i][0] != '\0' && strstr(g_raw[i], token) != NULL) {
            return true;
        }
    }
    return false;
}

static void capture_clear(void)
{
    memset(g_raw, 0, sizeof(g_raw));
    memset(g_fmt, 0, sizeof(g_fmt));
    memset(g_err, 0, sizeof(g_err));
    g_raw_count = 0;
    g_fmt_count = 0;
    g_err_count = 0;
}

/* A realistic schema-3 TELEM frame carrying every watched token. */
static const char *TELEM_VIEW =
    "#CG TELEM schema=3 timestamp_utc=UNAVAILABLE "
    "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK uptime_ms=1000 "
    "run_id=UNSET device_id=" CG_DEVICE_ID " boot_id=deadbeef boot_count=3 "
    "seq=42 t1_rom=aa t2_rom=bb t3_rom=cc spare_rom=dd "
    "thermal_age_ms=0 power_age_ms=0 door_age_ms=0 thermal_seq=1 power_seq=1 "
    "pwm_duty=0 output_stage=DISABLED tec_state=OFF fault_code=0x80000003 "
    "fault_reason=NONE sensor_validity=VALID power_validity=INVALID "
    "cooling_applied=OFF cooling_applied_source=DEVICE_TEC_STATE "
    "health=UNKNOWN health_thermal=UNKNOWN health_bme=UNKNOWN health_door=UNKNOWN "
    "health_power=UNKNOWN health_telemetry=UNKNOWN health_control=UNKNOWN";

/* The world through a complete TELEM view: observed streams for the device
 * trio and the shipped compile-time world for the gates. Returns true and
 * fills `world` on success; scenario functions may CHECK on it. */
static bool fill_world_from_telem(cg_leader_world_t *world)
{
    bool complete = false;

    cg_leader_world_init(world);
    CHECK(cg_leader_world_observe_line(TELEM_VIEW, world, &complete));
    CHECK(complete);
    world->output_stage_enabled = false; /* shipped: compiled out */
    world->limits_resolved = false;      /* shipped: no resolved limit table */
    world->allowed_duty_max_permille = 0U;
    world->local_safety_permits = false;
    world->inputs_sufficiently_valid = true;
    world->uptime_ms = 1500U;
    return true;
}

static const char *CANONICAL_A =
    "schema_version=1 command_id=" UUID_A " device_id=" CG_DEVICE_ID
    " created_at_ms=1730000000000 expires_at_ms=1730000000600"
    " controller_id=cg-controller-1 policy_version=policy-1 reason_code=PREDICTIVE_MAINTENANCE"
    " action_cooling=OFF action_duty_permille=0";

/* Widest realistic legal record: every capped label at its bound. */
static const char *CANONICAL_WIDE =
    "schema_version=1 command_id=" UUID_A " device_id=" CG_DEVICE_ID
    " created_at_ms=17300000000000000000 expires_at_ms=17300000006000000000"
    " controller_id=cg-controller-123456789 policy_version=policy-version-123456"
    " reason_code=PREDICTIVE-MAINTENANC action_cooling=OFF action_duty_permille=0";

static bool world_observed_fields_carry(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    CHECK(world.telemetry_seq == 42U);
    CHECK(strcmp(world.boot_id, "deadbeef") == 0);
    CHECK(world.boot_count == 3U);
    CHECK(strcmp(world.device_mode, "OFF") == 0);
    CHECK(world.fault_bits == 0x80000003U);
    CHECK(world.applied_cooling_on == false);
    CHECK(world.applied_duty_permille == 0U);
    CHECK(world.world_observed);
    return true;
}

static bool a_partial_frame_never_regresses_the_view(void)
{
    cg_leader_world_t world;
    bool complete = true;

    CHECK(fill_world_from_telem(&world));
    /* A degraded line that parses the seq but misses the world tokens: the
     * observer reports its partial update and names the view incomplete, so
     * the device shell discards it instead of merging it in. */
    const char *partial = "#CG TELEM schema=3 device_id=" CG_DEVICE_ID
                          " boot_id=deadbeef seq=43";
    CHECK(cg_leader_world_observe_line(partial, &world, &complete));
    CHECK(complete == false);
    CHECK(world.telemetry_seq == 43U); /* the caller copy alone was touched */
    return true;
}

static bool an_ack_never_seeds_the_world(void)
{
    cg_leader_world_t world;
    bool complete = false;

    cg_leader_world_init(&world);
    const char *ack =
        "#CG CMDACK schema=1 event=ACK command_id=" UUID_A " command_id_form=UUID "
        "source=NETWORK device_id=" CG_DEVICE_ID " boot_id=0102device0304 "
        "boot_count=3 uptime_ms=1 ack_seq=1 status=SAFETY_BLOCKED "
        "reason=EPOCH_UNSYNCHRONIZED desired_cooling=OFF desired_duty_permille=0 "
        "applied_cooling=OFF applied_duty_permille=0 reapplied=0 expiry_evaluable=0";
    CHECK(cg_leader_world_observe_line(ack, &world, &complete) == false);
    CHECK(complete == false);
    CHECK(world.world_observed == false);
    CHECK(strcmp(world.boot_id, "UNKNOWN") == 0);
    return true;
}

static bool routing_is_the_exact_envelope_form(void)
{
    static const char *const delivered_verbs[] = {
        "ARM 0123abcd", "CLEAR 0123abcd", "RUN exp-1", "PHASE G0", "START 60",
        "STOP", "ESTOP", "STATUS", "CMDTEST t1 OFF 0",
    };
    for (size_t i = 0; i < sizeof(delivered_verbs) / sizeof(delivered_verbs[0]); i++) {
        CHECK(cg_leader_line_is_envelope(delivered_verbs[i]) == false);
    }
    CHECK(cg_leader_line_is_envelope("#CG CMD schema_version=1 command_id=x"));
    CHECK(cg_leader_line_is_envelope("#CG CMD") == false);   /* no trailing space */
    CHECK(cg_leader_line_is_envelope("#CG CMDACK schema=1 event=ACK") == false);
    CHECK(cg_leader_line_is_envelope("#CG TELEM schema=3") == false);
    CHECK(cg_leader_line_is_envelope("") == false);
    CHECK(cg_leader_line_is_envelope(NULL) == false);
    return true;
}

static bool the_shipped_world_blocks_a_canonical_command(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    capture_clear();
    cg_leader_netcmd_handle(CANONICAL_A, &world);
    CHECK(g_raw_count == 1);
    CHECK(has_raw("#CG CMDACK schema=1 event=ACK"));
    CHECK(has_raw("source=NETWORK"));
    CHECK(has_raw("command_id=" UUID_A));
    CHECK(has_raw("command_id_form=UUID"));
    CHECK(has_raw("device_id=" CG_DEVICE_ID));
    CHECK(has_raw("boot_id=deadbeef"));
    CHECK(has_raw("boot_count=3"));
    CHECK(has_raw("uptime_ms=1500"));
    CHECK(has_raw("ack_seq=42"));
    CHECK(has_raw("status=SAFETY_BLOCKED"));
    CHECK(has_raw("reason=EPOCH_UNSYNCHRONIZED"));
    CHECK(has_raw("expiry_evaluable=0"));
    CHECK(has_raw("time_sync_state=UNSYNCHRONIZED"));
    CHECK(has_raw("device_mode=OFF"));
    CHECK(has_raw("fault_code=0x80000003"));
    CHECK(has_raw("output_stage=DISABLED"));
    /* The "not observed" markers must not reach a world-backed ACK. */
    CHECK(!has_raw("UNKNOWN"));
    return true;
}

static bool a_replay_returns_the_canonical_result(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    capture_clear();
    cg_leader_netcmd_handle(CANONICAL_A, &world);
    CHECK(g_raw_count == 1);
    CHECK(has_raw("status=SAFETY_BLOCKED"));
    CHECK(has_raw("reason=EPOCH_UNSYNCHRONIZED"));
    cg_leader_netcmd_handle(CANONICAL_A, &world);
    CHECK(g_raw_count == 2);
    CHECK(has_raw("status=DUPLICATE_CANONICAL"));
    CHECK(has_raw("reason=EPOCH_UNSYNCHRONIZED"));
    CHECK(has_raw("canonical_status=SAFETY_BLOCKED"));
    CHECK(has_raw("reapplied=0"));
    return true;
}

static bool a_target_mismatch_is_never_stored(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    capture_clear();
    {
        char mismatch[CG_COMMAND_RECORD_MAX];
        const char *tail = CANONICAL_A + strlen("schema_version=1 command_id=" UUID_A
                                                " device_id=" CG_DEVICE_ID);

        (void)snprintf(mismatch, sizeof(mismatch),
                       "schema_version=1 command_id=" UUID_B " device_id=another-device%s",
                       tail);
        cg_leader_netcmd_handle(mismatch, &world);
        CHECK(g_raw_count == 1);
        CHECK(has_raw("status=REJECTED"));
        CHECK(has_raw("reason=DEVICE_ID_MISMATCH"));
    }
    /* The same id then addressed to this device: the mismatch verdict must
     * not have created canonical memory - an id the device never owned
     * would otherwise let one submission answer for another. */
    cg_leader_netcmd_handle("schema_version=1 command_id=" UUID_B
                            " device_id=" CG_DEVICE_ID
                            " created_at_ms=1730000000000 expires_at_ms=1730000000600"
                            " policy_version=policy-1 reason_code=PREDICTIVE_MAINTENANCE"
                            " action_cooling=OFF action_duty_permille=0",
                            &world);
    CHECK(g_raw_count == 2);
    CHECK(has_raw("status=SAFETY_BLOCKED"));
    CHECK(has_raw("reason=EPOCH_UNSYNCHRONIZED"));
    CHECK(!has_raw("DUPLICATE_CANONICAL"));
    return true;
}

static bool a_malformed_record_leaves_no_ack(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    capture_clear();
    cg_leader_netcmd_handle("schema_version=1 command_id=" UUID_A
                            " device_id=" CG_DEVICE_ID
                            " created_at_ms=1730000000000 expires_at_ms=1730000000600"
                            " policy_version=policy-1 action_cooling=OFF action_duty_permille=0",
                            &world);
    CHECK(g_raw_count == 0); /* the delivered formatter refuses a commandless ACK */
    CHECK(g_fmt_count == 1);
    CHECK(strstr(g_fmt[0], "event=NETCMD result=PARSE_FAIL") != NULL);
    CHECK(strstr(g_fmt[0], "error=MISSING_REASON_CODE") != NULL);
    /* NULL records take the same path (the member parser owns the refusal). */
    cg_leader_netcmd_handle(NULL, &world);
    CHECK(g_raw_count == 0);
    CHECK(g_fmt_count == 2);
    return true;
}

static bool the_clock_gate_still_outruns_the_safety_gates(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    /* Fixture world with the stage and the limits notionally delivered: the
     * ingress passes them to the validator untouched, and the delivered
     * §29 order still blocks at the clock first. The fixture proves the
     * ordering; it is not a claim that the board has satisfied anything. */
    world.output_stage_enabled = true;
    world.limits_resolved = true;
    world.allowed_duty_max_permille = 600U;
    world.local_safety_permits = true;

    capture_clear();
    cg_leader_netcmd_handle(CANONICAL_A, &world);
    CHECK(g_raw_count == 1);
    CHECK(has_raw("status=SAFETY_BLOCKED"));
    CHECK(has_raw("reason=EPOCH_UNSYNCHRONIZED"));
    CHECK(!has_raw("OUTPUT_STAGE_COMPILED_OUT"));
    CHECK(!has_raw("LIMITS_UNRESOLVED"));
    return true;
}

static bool the_widest_record_parses_and_fits_the_reader(void)
{
    cg_leader_world_t world;

    CHECK(CG_LEADER_NETCMD_PREFIX_LEN == 8);
    CHECK(CG_LEADER_LINE_MAX - CG_LEADER_NETCMD_PREFIX_LEN >= CG_COMMAND_RECORD_MAX);
    CHECK(strlen(CANONICAL_WIDE) < CG_COMMAND_RECORD_MAX);
    CHECK(CG_LEADER_NETCMD_PREFIX_LEN + strlen(CANONICAL_WIDE) + 1U <= CG_LEADER_LINE_MAX);

    CHECK(fill_world_from_telem(&world));
    capture_clear();
    cg_leader_netcmd_handle(CANONICAL_WIDE, &world);
    CHECK(g_raw_count == 1);
    CHECK(has_raw("status=SAFETY_BLOCKED"));
    CHECK(has_raw("reason=EPOCH_UNSYNCHRONIZED"));
    return true;
}

/* ---- host→device time anchor (challenge echo, staleness, reboot) ------- */

#define HARNESS_CHALLENGE 0x1A2B3C4DUL
#define ANCHOR_HOST_MS 1730000000000ULL
/* Command records anchored against ANCHOR_HOST_MS: fresh = expires 600 ms
 * after the anchor; stale/expired = expires 100 ms after it. */
#define CANONICAL_FRESH_CANONICAL_A \
    "schema_version=1 command_id=" UUID_A " device_id=" CG_DEVICE_ID \
    " created_at_ms=1730000000000 expires_at_ms=1730000000600" \
    " controller_id=cg-controller-1 policy_version=policy-1 reason_code=PREDICTIVE_MAINTENANCE" \
    " action_cooling=OFF action_duty_permille=0"
#define CANONICAL_EXPIRED_AFTER_ANCHOR \
    "schema_version=1 command_id=" UUID_B " device_id=" CG_DEVICE_ID \
    " created_at_ms=1730000000000 expires_at_ms=1730000000100" \
    " controller_id=cg-controller-1 policy_version=policy-1 reason_code=PREDICTIVE_MAINTENANCE" \
    " action_cooling=OFF action_duty_permille=0"

static bool sync_accepts_the_live_challenge_echo(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world)); /* uptime 1500, boot deadbeef */
    capture_clear();
    cg_leader_sync_handle("host=1730000000000 challenge=1a2b3c4d boot=deadbeef",
                          &world, HARNESS_CHALLENGE);
    CHECK(g_fmt_count == 1);
    CHECK(strstr(g_fmt[0], "event=SYNC result=ACCEPTED") != NULL);
    CHECK(strstr(g_fmt[0], "host=1730000000000") != NULL);
    CHECK(cg_leader_sync_live(world.uptime_ms));
    /* 500 ms of device uptime later, the device's issuer-clock "now" is
     * the anchor exactly advanced by the elapsed monotonic time. */
    CHECK(cg_leader_sync_now_ms(2000U) == ANCHOR_HOST_MS + 500U);
    return true;
}

static bool aan_appropriately_authorized_off_command_is_admitted_in_a_stage_fixture(void)
{
    /* Fixture world: the stage and the limits notionally delivered (this is
     * the only world in which ACCEPTED can occur - the shipped board keeps
     * those FALSE). It proves the anchor flows into the delivered chain:
     * the clock gate now passes and the delivered admission (with its
     * remaining conjuncts intact) is what answers. */
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    world.output_stage_enabled = true;
    world.limits_resolved = true;
    world.allowed_duty_max_permille = 600U;
    world.local_safety_permits = true;
    capture_clear();
    cg_leader_sync_handle("host=1730000000000 challenge=1a2b3c4d boot=deadbeef",
                          &world, HARNESS_CHALLENGE);
    cg_leader_netcmd_handle(CANONICAL_FRESH_CANONICAL_A, &world);
    CHECK(g_raw_count == 1);
    CHECK(has_raw("status=ACCEPTED"));
    CHECK(has_raw("reason=NONE"));
    CHECK(has_raw("expiry_evaluable=1"));
    CHECK(has_raw("time_sync_state=SYNCHRONIZED"));
    return true;
}

static bool the_device_rejects_a_truly_expired_command_when_synced(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    world.output_stage_enabled = true;
    world.limits_resolved = true;
    world.allowed_duty_max_permille = 600U;
    world.local_safety_permits = true;
    capture_clear();
    cg_leader_sync_handle("host=1730000000000 challenge=1a2b3c4d boot=deadbeef",
                          &world, HARNESS_CHALLENGE);
    /* Issuer-clock "now" at deadline is anchor+500: this command expired
     * 400 ms before the device ever judged it. */
    world.uptime_ms = 2000U;
    cg_leader_netcmd_handle(CANONICAL_EXPIRED_AFTER_ANCHOR, &world);
    CHECK(g_raw_count == 1);
    CHECK(has_raw("status=EXPIRED"));
    CHECK(has_raw("reason=EXPIRED"));
    CHECK(has_raw("expiry_evaluable=1"));
    return true;
}

static bool the_anchor_goes_stale_fail_closed(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    capture_clear();
    cg_leader_sync_handle("host=1730000000000 challenge=1a2b3c4d boot=deadbeef",
                          &world, HARNESS_CHALLENGE);
    /* Uptime far beyond the stale window - a lost gateway session. The
     * device is UNSYNCHRONIZED again and every command is blocked at the
     * delivered clock gate, expiry declared unevaluable. */
    world.uptime_ms = 1500U + CG_LEADER_SYNC_STALE_MS + 1U;
    CHECK(cg_leader_sync_live(world.uptime_ms) == false);
    cg_leader_netcmd_handle(CANONICAL_FRESH_CANONICAL_A, &world);
    CHECK(g_raw_count == 1);
    CHECK(has_raw("status=SAFETY_BLOCKED"));
    CHECK(has_raw("reason=EPOCH_UNSYNCHRONIZED"));
    CHECK(has_raw("expiry_evaluable=0"));
    return true;
}

static bool a_wrong_challenge_or_boot_never_anchors(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    capture_clear();
    /* A stale/replayed capability echo from another boot (or a counterfeit
     * writer that never read this boot's stream): rejected, nothing is
     * applied, and the device stays UNSYNCHRONIZED. */
    cg_leader_sync_handle("host=1730000000000 challenge=deadbeef boot=deadbeef",
                          &world, HARNESS_CHALLENGE);
    CHECK(strstr(g_fmt[0], "result=REJECTED reason=CHALLENGE_MISMATCH") != NULL);
    CHECK(g_fmt_count == 1);
    CHECK(!has_raw("CMDACK"));
    CHECK(cg_leader_sync_live(world.uptime_ms) == false);

    /* The right challenge but the wrong boot id: equally rejected. */
    capture_clear();
    cg_leader_sync_handle("host=1730000000000 challenge=1a2b3c4d boot=0000ffff",
                          &world, HARNESS_CHALLENGE);
    CHECK(strstr(g_fmt[0], "result=REJECTED reason=BOOT_MISMATCH") != NULL);
    CHECK(cg_leader_sync_live(world.uptime_ms) == false);
    return true;
}

static bool a_host_time_regression_is_counted_not_applied(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    capture_clear();
    cg_leader_sync_handle("host=1730000000000 challenge=1a2b3c4d boot=deadbeef",
                          &world, HARNESS_CHALLENGE);
    capture_clear();
    /* A later attempt claims an earlier host instant (host clock stepped
     * back or a replayed fresh-looking record from a genuine prior state):
     * rejected, and the farther anchor stays authoritative. */
    cg_leader_sync_handle("host=1729990000000 challenge=1a2b3c4d boot=deadbeef",
                          &world, HARNESS_CHALLENGE);
    CHECK(strstr(g_fmt[0], "result=REJECTED reason=HOST_TIME_BACKWARD") != NULL);
    CHECK(cg_leader_sync_now_ms(world.uptime_ms) == ANCHOR_HOST_MS);
    CHECK(cg_leader_sync_live(world.uptime_ms));
    return true;
}

static bool a_reset_forgets_every_anchor(void)
{
    cg_leader_world_t world;

    CHECK(fill_world_from_telem(&world));
    cg_leader_sync_handle("host=1730000000000 challenge=1a2b3c4d boot=deadbeef",
                          &world, HARNESS_CHALLENGE);
    CHECK(cg_leader_sync_live(world.uptime_ms));
    /* The delivered volatility rule: a reset (boot) forgets the anchor and
     * every command identity. The next boot starts UNSYNCHRONIZED and the
     * gateway must re-earn the anchor with the new challenge. */
    cg_leader_netcmd_store_init();
    CHECK(cg_leader_sync_live(world.uptime_ms) == false);
    return true;
}

int main(void)
{
    typedef bool (*scenario_fn)(void);
    const scenario_fn scenarios[] = {
        world_observed_fields_carry,
        a_partial_frame_never_regresses_the_view,
        an_ack_never_seeds_the_world,
        routing_is_the_exact_envelope_form,
        the_shipped_world_blocks_a_canonical_command,
        a_replay_returns_the_canonical_result,
        a_target_mismatch_is_never_stored,
        a_malformed_record_leaves_no_ack,
        the_clock_gate_still_outruns_the_safety_gates,
        the_widest_record_parses_and_fits_the_reader,
        sync_accepts_the_live_challenge_echo,
        aan_appropriately_authorized_off_command_is_admitted_in_a_stage_fixture,
        the_device_rejects_a_truly_expired_command_when_synced,
        the_anchor_goes_stale_fail_closed,
        a_wrong_challenge_or_boot_never_anchors,
        a_host_time_regression_is_counted_not_applied,
        a_reset_forgets_every_anchor,
    };
    const int total = (int)(sizeof(scenarios) / sizeof(scenarios[0]));
    int passed = 0;

    printf("LEADER NETCMD INGRESS scenarios:\n");
    for (int i = 0; i < total; i++) {
        cg_leader_netcmd_store_init(); /* RAM-only contract, each scenario starts volatile-clean */
        const bool ok = scenarios[i]();
        printf("scenario %2d: %s\n", i + 1, ok ? "pass" : "FAIL");
        if (ok) {
            passed++;
        }
    }
    printf("%d/%d LEADER NETCMD scenarios passed\n", passed, total);
    if (passed < total) {
        printf("LEADER NETCMD CONTRACT: FAILURES PRESENT\n");
        return 1;
    }
    printf("LEADER NETCMD CONTRACT: ALL SCENARIOS PASS\n");
    return 0;
}
