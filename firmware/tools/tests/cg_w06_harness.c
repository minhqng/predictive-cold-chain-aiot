/*
 * Host harness for the ColdGuard W06 command/ACK contract.
 *
 * Compiles firmware/main/cg_command.c, cg_telemetry.c, cg_snapshot.c and
 * cg_tec_command.c unchanged and drives them with an explicit validation
 * context. Nothing here is a physical actuation: the point is that the
 * device-side rules of docs/02 §28-§32 (lines 2051-2216) are executable and
 * falsifiable on the host, including the verdicts that are unreachable on the
 * shipped board (the output stage is compiled out and the clock is
 * unsynchronized, so ACCEPTED cannot occur in firmware today).
 *
 * The permissive contexts below are harness fixtures, exactly like the W04
 * harness's injected resolved-limit table. They prove the mechanism; they are
 * not a claim that any board has satisfied those preconditions.
 *
 * Exit code: 0 when every scenario passes, 1 otherwise.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cg_command.h"
#include "cg_snapshot.h"
#include "cg_tec_command.h"
#include "cg_tec_control.h"
#include "cg_tec_limits.h"
#include "cg_telemetry.h"
#include "coldguard_config.h"

/* cg_ds18b20.c is device-only; the telemetry formatter only needs the name. */
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

#define UUID_A "00000000-0000-4000-8000-00000000000a"
#define UUID_B "00000000-0000-4000-8000-00000000000b"
/* The boot identity the scenario emitter and the ACK formatter agree on, so a
 * log line is self-describing instead of depending on the reader knowing which
 * boot produced it. */
#define SCENARIO_BOOT_ID "abcd0123"
#define SCENARIO_BOOT_ID_AFTER_RESET "ef567890"

static bool has(const char *line, const char *token)
{
    return strstr(line, token) != NULL;
}

/* The shipped world: no wall clock, no output stage, unresolved limits. */
static cg_cmd_context_t shipped_context(void)
{
    cg_cmd_context_t ctx;

    memset(&ctx, 0, sizeof(ctx));
    ctx.device_id = CG_DEVICE_ID;
    ctx.time_sync = CG_TIME_SYNC_UNSYNCHRONIZED;
    ctx.now_ms = 0U;
    ctx.output_stage_enabled = false;
    ctx.limits_resolved = false;
    ctx.allowed_duty_max_permille = 0U;
    ctx.local_safety_permits = false;
    ctx.inputs_sufficiently_valid = true;
    ctx.uptime_ms = 123456U;
    ctx.telemetry_seq = 42U;
    ctx.device_mode = "OFF";
    ctx.fault_bits = 0U;
    ctx.applied_cooling_on = false;
    ctx.applied_duty_permille = 0U;
    return ctx;
}

/* A harness-only world in which every §29 conjunct can hold. */
static cg_cmd_context_t permissive_context(void)
{
    cg_cmd_context_t ctx = shipped_context();

    ctx.time_sync = CG_TIME_SYNC_SYNCHRONIZED;
    ctx.now_ms = 1000000ULL;
    ctx.output_stage_enabled = true;
    ctx.limits_resolved = true;
    ctx.allowed_duty_max_permille = 500U;
    ctx.local_safety_permits = true;
    return ctx;
}

static cg_command_t make_command(const char *command_id, const char *device_id,
                                 cg_cmd_cooling_t cooling, uint32_t duty, uint64_t created_ms,
                                 uint64_t expires_ms)
{
    cg_command_t cmd;

    memset(&cmd, 0, sizeof(cmd));
    cmd.schema_version = 1;
    (void)snprintf(cmd.command_id, sizeof(cmd.command_id), "%s", command_id);
    (void)snprintf(cmd.device_id, sizeof(cmd.device_id), "%s", device_id);
    (void)snprintf(cmd.controller_id, sizeof(cmd.controller_id), "%s", "PREDICTIVE");
    (void)snprintf(cmd.policy_version, sizeof(cmd.policy_version), "%s", "policy-1");
    (void)snprintf(cmd.reason_code, sizeof(cmd.reason_code), "%s", "PREDICTED_CRITICAL");
    cmd.id_form = cg_command_id_form_for(command_id);
    cmd.source = CG_CMD_SOURCE_NETWORK;
    cmd.cooling = cooling;
    cmd.duty_permille = duty;
    cmd.created_at_ms = created_ms;
    cmd.expires_at_ms = expires_ms;
    cmd.has_created_at = true;
    cmd.has_expires_at = expires_ms != 0ULL;
    return cmd;
}

/* ------------------------------------------------------------------ */
/* §29 validation chain, conjunct by conjunct                          */
/* ------------------------------------------------------------------ */

static bool test_unsupported_schema_rejected(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                    1100000ULL);

    cg_cmd_store_init(&store);
    cmd.schema_version = 2; /* docs/02 §28.1 (2053-2073) publishes envelope version 1 only */
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_REJECTED);
    CHECK(strcmp(ack.reason, "UNSUPPORTED_SCHEMA") == 0);
    CHECK(ack.applied_cooling == CG_CMD_COOLING_OFF);
    return true;
}

static bool test_wrong_device_rejected(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, "coldguard-002", CG_CMD_COOLING_ON, 250U,
                                    900000ULL, 1100000ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    /* Pass criterion "wrong-device rejected": a topic- or bus-wide broadcast
     * must not actuate a board it was not addressed to. */
    CHECK(ack.status == CG_CMD_ACK_REJECTED);
    CHECK(strcmp(ack.reason, "DEVICE_ID_MISMATCH") == 0);
    return true;
}

static bool test_missing_command_id_rejected(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command("", CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                    1100000ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_REJECTED);
    CHECK(strcmp(ack.reason, "MISSING_COMMAND_ID") == 0);
    /* Nothing memorable means nothing stored: an id-less record must not occupy
     * a retention slot and push a real command out of memory. */
    CHECK(store.entry[0].used == false);
    return true;
}

static bool test_missing_expiry_is_not_treated_as_unbounded(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                    0ULL);

    cg_cmd_store_init(&store);
    cmd.has_expires_at = false;
    cg_command_validate(&cmd, &ctx, &store, &ack);
    /* §28.2 makes expiry required. Reading "absent" as "never expires" would
     * turn a malformed command into the most dangerous kind: an unbounded one. */
    CHECK(ack.status == CG_CMD_ACK_REJECTED);
    CHECK(strcmp(ack.reason, "MISSING_EXPIRY") == 0);
    return true;
}

static bool test_missing_created_at_rejected(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 0ULL,
                                    1100000ULL);

    cg_cmd_store_init(&store);
    cmd.has_created_at = false;
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_REJECTED);
    CHECK(strcmp(ack.reason, "MISSING_CREATED_AT") == 0);
    return true;
}

static bool test_inverted_validity_window_rejected(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 1100000ULL,
                                    900000ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_OUT_OF_RANGE);
    CHECK(strcmp(ack.reason, "BAD_VALIDITY_WINDOW") == 0);
    return true;
}

/* ------------------------------------------------------------------ */
/* The freshness decision this slice exists for                         */
/* ------------------------------------------------------------------ */

static bool test_unsync_clock_blocks_instead_of_assuming_fresh(void)
{
    cg_cmd_context_t ctx = shipped_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    /* An expiry far in the future: the naive reading is "obviously not expired".
     * The device cannot know that, because its clock is not in the issuer's time
     * domain at all. */
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 1000000ULL,
                                    4000000000ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_SAFETY_BLOCKED);
    CHECK(strcmp(ack.reason, "EPOCH_UNSYNCHRONIZED") == 0);
    CHECK(ack.expiry_evaluable == false);
    /* Not applied, and the applied state stays what the board is actually in. */
    CHECK(ack.applied_cooling == CG_CMD_COOLING_OFF);
    CHECK(ack.applied_duty_permille == 0U);
    return true;
}

static bool test_unsync_clock_blocks_even_a_past_expiry(void)
{
    cg_cmd_context_t ctx = shipped_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 1ULL, 2ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    /* Reporting EXPIRED would claim to have measured an age the device cannot
     * measure. Blocked is the honest verdict in both directions. */
    CHECK(ack.status == CG_CMD_ACK_SAFETY_BLOCKED);
    CHECK(strcmp(ack.reason, "EPOCH_UNSYNCHRONIZED") == 0);
    CHECK(ack.expiry_evaluable == false);
    return true;
}

static bool test_expired_when_synchronized(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                    950000ULL);

    cg_cmd_store_init(&store);
    /* ctx.now_ms is 1000000 > expires_at 950000. */
    CHECK(ctx.now_ms > cmd.expires_at_ms);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_EXPIRED);
    CHECK(strcmp(ack.reason, "EXPIRED") == 0);
    CHECK(ack.expiry_evaluable == true);
    return true;
}

static bool test_fresh_when_synchronized_reaches_later_checks(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                    1100000ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    /* Every conjunct holds in this fixture, so the contract allows ACCEPTED -
     * which is protocol evidence only, never "the chamber cooled". */
    CHECK(ack.status == CG_CMD_ACK_ACCEPTED);
    CHECK(strcmp(ack.reason, "NONE") == 0);
    CHECK(ack.desired_cooling == CG_CMD_COOLING_ON);
    CHECK(ack.desired_duty_permille == 250U);
    CHECK(ack.applied_cooling == CG_CMD_COOLING_OFF);
    return true;
}

/* ------------------------------------------------------------------ */
/* Range, safety, state                                                 */
/* ------------------------------------------------------------------ */

static bool test_duty_above_allowed_max_out_of_range(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 900U, 900000ULL,
                                    1100000ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_OUT_OF_RANGE);
    CHECK(strcmp(ack.reason, "DUTY_ABOVE_ALLOWED_MAX") == 0);
    return true;
}

static bool test_duty_not_a_permille_value(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 1001U, 900000ULL,
                                    1100000ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_OUT_OF_RANGE);
    CHECK(strcmp(ack.reason, "DUTY_NOT_A_PERCENT") == 0);
    return true;
}

static bool test_on_with_zero_duty_and_off_with_duty_rejected(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;

    cg_cmd_store_init(&store);

    {
        cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 0U, 900000ULL,
                                       1100000ULL);
        cg_command_validate(&cmd, &ctx, &store, &ack);
        CHECK(ack.status == CG_CMD_ACK_OUT_OF_RANGE);
        CHECK(strcmp(ack.reason, "ON_WITH_ZERO_DUTY") == 0);
    }
    cg_cmd_store_init(&store);
    {
        cg_command_t cmd = make_command(UUID_B, CG_DEVICE_ID, CG_CMD_COOLING_OFF, 200U,
                                       900000ULL, 1100000ULL);
        cg_command_validate(&cmd, &ctx, &store, &ack);
        CHECK(ack.status == CG_CMD_ACK_OUT_OF_RANGE);
        CHECK(strcmp(ack.reason, "OFF_WITH_NONZERO_DUTY") == 0);
    }
    return true;
}

static bool test_shipped_board_blocks_on_request_even_when_fresh(void)
{
    /* Same clock state, so freshness is evaluable: this isolates the safety and
     * limit conjuncts from the epoch one. */
    cg_cmd_context_t ctx = shipped_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 1000000ULL,
                                    1100000ULL);

    ctx.time_sync = CG_TIME_SYNC_SYNCHRONIZED;
    ctx.now_ms = 1000500ULL;
    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    /* Pass criterion "default OFF preserved": the allowed duty maximum is 0
     * while the limits are unresolved, so any ON request is out of range before
     * the stage question is even reached. */
    CHECK(ack.status == CG_CMD_ACK_OUT_OF_RANGE);
    CHECK(strcmp(ack.reason, "DUTY_ABOVE_ALLOWED_MAX") == 0);
    CHECK(ack.applied_cooling == CG_CMD_COOLING_OFF);

    /* With a resolved duty limit but the stage still compiled out, the block
     * comes from local safety instead. */
    ctx.allowed_duty_max_permille = 500U;
    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_SAFETY_BLOCKED);
    CHECK(strcmp(ack.reason, "OUTPUT_STAGE_COMPILED_OUT") == 0);

    ctx.output_stage_enabled = true;
    ctx.limits_resolved = false;
    ctx.local_safety_permits = false;
    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_SAFETY_BLOCKED);
    CHECK(strcmp(ack.reason, "LIMITS_UNRESOLVED") == 0);
    return true;
}

static bool test_invalid_local_state_rejected(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_OFF, 0U, 900000ULL,
                                    1100000ULL);

    ctx.inputs_sufficiently_valid = false;
    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_INVALID_STATE);
    CHECK(strcmp(ack.reason, "SENSORS_INVALID_OR_STALE") == 0);
    return true;
}

/* ------------------------------------------------------------------ */
/* A-W06-04: applied state is reported, never inferred                 */
/* ------------------------------------------------------------------ */

static bool test_applied_state_comes_from_the_device(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_OFF, 0U, 900000ULL,
                                    1100000ULL);

    /* A board that is genuinely cooling, asked to stop. The ACK must report the
     * cooling state it is in, not the OFF it was asked for - otherwise an
     * "OFF acknowledged" line would hide a branch that is still drawing. */
    ctx.applied_cooling_on = true;
    ctx.applied_duty_permille = 350U;
    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_ACCEPTED);
    CHECK(ack.desired_cooling == CG_CMD_COOLING_OFF);
    CHECK(ack.desired_duty_permille == 0U);
    CHECK(ack.applied_cooling == CG_CMD_COOLING_ON);
    CHECK(ack.applied_duty_permille == 350U);
    return true;
}

/* ------------------------------------------------------------------ */
/* A-W06-02 idempotency                                                */
/* ------------------------------------------------------------------ */

static bool test_duplicate_returns_canonical_and_does_not_reapply(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t first;
    cg_cmd_ack_t second;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                    1100000ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &first);
    CHECK(first.status == CG_CMD_ACK_ACCEPTED);

    /* The world moves on: duty ceiling drops and the stage disappears. A replay
     * of the same command_id must not be re-decided against the new world. */
    ctx.allowed_duty_max_permille = 10U;
    ctx.output_stage_enabled = false;
    ctx.local_safety_permits = false;
    ctx.uptime_ms = 999999ULL;
    cg_command_validate(&cmd, &ctx, &store, &second);
    CHECK(second.status == CG_CMD_ACK_DUPLICATE_CANONICAL);
    CHECK(second.canonical_status == CG_CMD_ACK_ACCEPTED);
    CHECK(second.reapplied == false);
    /* The canonical applied state travels with the answer. */
    CHECK(second.applied_cooling == first.applied_cooling);
    CHECK(store.hits == 1U);
    return true;
}

static bool test_pre_identity_rejection_cannot_clobber_the_canonical_result(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t first;
    cg_cmd_ack_t intruder;
    cg_cmd_ack_t replay;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                    1100000ULL);
    cg_command_t foreign;
    cg_command_t bad_schema;

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &first);
    CHECK(first.status == CG_CMD_ACK_ACCEPTED);

    /* Same id, two records this contract does not own: one addressed to another
     * device, one in a schema the device does not speak. Neither may take the
     * remembered result with it. */
    foreign = cmd;
    (void)snprintf(foreign.device_id, sizeof(foreign.device_id), "%s", "coldguard-999");
    cg_command_validate(&foreign, &ctx, &store, &intruder);
    CHECK(intruder.status == CG_CMD_ACK_REJECTED);
    CHECK(strcmp(intruder.reason, "DEVICE_ID_MISMATCH") == 0);

    bad_schema = cmd;
    bad_schema.schema_version = 2U;
    cg_command_validate(&bad_schema, &ctx, &store, &intruder);
    CHECK(intruder.status == CG_CMD_ACK_REJECTED);
    CHECK(strcmp(intruder.reason, "UNSUPPORTED_SCHEMA") == 0);

    cg_command_validate(&cmd, &ctx, &store, &replay);
    CHECK(replay.status == CG_CMD_ACK_DUPLICATE_CANONICAL);
    CHECK(replay.canonical_status == CG_CMD_ACK_ACCEPTED);
    CHECK(replay.reapplied == false);
    return true;
}

static bool test_local_console_source_is_gated_before_acceptance(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    /* A locally issued record given every canonical field, including a real
     * expiry: the shipped bridge cannot reach this state, so the refusal here is
     * the gate itself and not a side effect of a missing field. */
    cg_command_t cmd = make_command("local:w06-selftest", CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U,
                                    900000ULL, 1100000ULL);

    cg_cmd_store_init(&store);
    cmd.source = CG_CMD_SOURCE_LOCAL_CONSOLE;
    cmd.id_form = CG_CMD_ID_FORM_TEST_TOKEN;
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_SAFETY_BLOCKED);
    CHECK(strcmp(ack.reason, "LOCAL_TEST_NOT_CANONICAL") == 0);
    return true;
}

static bool test_blocked_duplicate_stays_blocked_canonical(void)
{
    cg_cmd_context_t ctx = shipped_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 1000000ULL,
                                    4000000000ULL);
    cg_command_t again;

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_SAFETY_BLOCKED);

    again = cmd;
    (void)snprintf(again.command_id, sizeof(again.command_id), "%s", UUID_A);
    cg_command_validate(&again, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_DUPLICATE_CANONICAL);
    CHECK(ack.canonical_status == CG_CMD_ACK_SAFETY_BLOCKED);
    CHECK(strcmp(ack.reason, "EPOCH_UNSYNCHRONIZED") == 0);
    return true;
}

static bool test_new_id_same_action_is_a_new_instruction(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;

    cg_cmd_store_init(&store);
    {
        cg_command_t a = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                     1100000ULL);
        cg_command_validate(&a, &ctx, &store, &ack);
        CHECK(ack.status == CG_CMD_ACK_ACCEPTED);
    }
    {
        /* §30.2: identical action, different id, so it is a new logical command
         * and is evaluated on its own terms. */
        cg_command_t b = make_command(UUID_B, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                     1100000ULL);
        cg_command_validate(&b, &ctx, &store, &ack);
        CHECK(ack.status == CG_CMD_ACK_ACCEPTED);
        CHECK(ack.status != CG_CMD_ACK_DUPLICATE_CANONICAL);
    }
    return true;
}

static bool test_retention_bound_is_explicit(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    char id[CG_COMMAND_ID_MAX];

    cg_cmd_store_init(&store);
    for (unsigned i = 0; i < CG_CMD_STORE_CAPACITY; i++) {
        cg_command_t cmd;
        (void)snprintf(id, sizeof(id), "local-%u", i);
        cmd = make_command(id, CG_DEVICE_ID, CG_CMD_COOLING_ON, 100U, 900000ULL, 1100000ULL);
        cg_command_validate(&cmd, &ctx, &store, &ack);
        CHECK(ack.status == CG_CMD_ACK_ACCEPTED);
    }
    /* The window is full but nothing has been forgotten yet: all eight ids are
     * still recognized, so replaying any of them must be a duplicate, not a new
     * instruction. */
    {
        cg_command_t inside = make_command("local-3", CG_DEVICE_ID, CG_CMD_COOLING_ON, 100U,
                                          900000ULL, 1100000ULL);
        cg_command_validate(&inside, &ctx, &store, &ack);
        CHECK(ack.status == CG_CMD_ACK_DUPLICATE_CANONICAL);
        CHECK(store.evicted == 0U);
    }
    /* One past the window the oldest id is displaced, so a replay of it is now
     * treated as new. That is the documented retention bound, and the eviction
     * counter is the evidence it was crossed - a duplicate silently accepted as
     * new is exactly the failure mode this makes visible. */
    {
        cg_command_t ninth = make_command("local-8", CG_DEVICE_ID, CG_CMD_COOLING_ON, 100U,
                                         900000ULL, 1100000ULL);
        cg_command_validate(&ninth, &ctx, &store, &ack);
        CHECK(ack.status == CG_CMD_ACK_ACCEPTED);
        CHECK(store.evicted == 1U);
        CHECK(strcmp(store.entry[0].command_id, "local-8") == 0);
    }
    {
        cg_command_t evicted = make_command("local-0", CG_DEVICE_ID, CG_CMD_COOLING_ON, 100U,
                                           900000ULL, 1100000ULL);
        cg_command_validate(&evicted, &ctx, &store, &ack);
        CHECK(ack.status == CG_CMD_ACK_ACCEPTED);
        CHECK(ack.status != CG_CMD_ACK_DUPLICATE_CANONICAL);
    }
    return true;
}

static bool test_store_is_volatile_across_reset(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                    1100000ULL);

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_ACCEPTED);

    /* A-W06-06. Re-initialising is what a reset does: the store is RAM, never
     * NVS. After the reset the device cannot claim DUPLICATE_CANONICAL, and it
     * must not resume the previous desire: the applied state comes from the
     * board, which boots default-OFF with the stage compiled out. */
    cg_cmd_store_init(&store);
    ctx.applied_cooling_on = false;
    ctx.applied_duty_permille = 0U;
    ctx.allowed_duty_max_permille = 0U; /* limits unresolved again on a fresh boot */
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_OUT_OF_RANGE);
    CHECK(ack.applied_cooling == CG_CMD_COOLING_OFF);
    CHECK(ack.applied_duty_permille == 0U);
    return true;
}

/* ------------------------------------------------------------------ */
/* ACK line format                                                     */
/* ------------------------------------------------------------------ */

static bool test_ack_line_carries_the_required_payload(void)
{
    cg_cmd_context_t ctx = shipped_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 1000000ULL,
                                    4000000000ULL);
    char line[512];
    int len;

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    len = cg_command_ack_format(line, sizeof(line), &ack, &ctx, "abcd0123", 9U);
    CHECK(len > 0);
    CHECK((size_t)len == strlen(line));
    /* docs/02 §32.3 (lines 2200-2215) payload list, plus the identity and clock state
     * makes the verdict interpretable. */
    CHECK(has(line, "#CG CMDACK schema=1 event=ACK "));
    CHECK(has(line, "command_id=" UUID_A " "));
    CHECK(has(line, "command_id_form=UUID "));
    CHECK(has(line, "source=NETWORK "));
    CHECK(has(line, "boot_id=abcd0123 boot_count=9 "));
    CHECK(has(line, "uptime_ms=123456 ack_seq=42 "));
    CHECK(has(line, "status=SAFETY_BLOCKED reason=EPOCH_UNSYNCHRONIZED "));
    CHECK(has(line, "desired_cooling=ON desired_duty_permille=250 "));
    CHECK(has(line, "applied_cooling=OFF applied_duty_permille=0 "));
    CHECK(has(line, "reapplied=0 expiry_evaluable=0 "));
    CHECK(has(line, "time_sync_state=UNSYNCHRONIZED "));
    CHECK(has(line, "output_stage=DISABLED allowed_duty_max_permille=0"));
    /* schema=1 here is the COMMAND envelope of docs/02 line 2057, not the serial
     * telemetry schema; a reader must be able to tell them apart. */
    CHECK(!has(line, "schema=3"));
    return true;
}

static bool test_ack_duplicate_names_canonical_status(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL,
                                   1100000ULL);
    char line[512];

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(cg_command_ack_format(line, sizeof(line), &ack, &ctx, "abcd0123", 1U) > 0);
    CHECK(has(line, "status=DUPLICATE_CANONICAL"));
    CHECK(has(line, " canonical_status=ACCEPTED"));
    CHECK(has(line, "reapplied=0"));
    return true;
}

static bool test_ack_refuses_truncation_and_anonymous_records(void)
{
    cg_cmd_context_t ctx = shipped_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 1000000ULL,
                                    4000000000ULL);
    char small[64];
    char line[512];

    cg_cmd_store_init(&store);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(cg_command_ack_format(small, sizeof(small), &ack, &ctx, "abcd0123", 1U) == 0);
    CHECK(small[0] == '\0');
    /* An ACK that names no command is not evidence about anything. */
    memset(&ack.command_id, 0, sizeof(ack.command_id));
    CHECK(cg_command_ack_format(line, sizeof(line), &ack, &ctx, "abcd0123", 1U) == 0);
    CHECK(cg_command_ack_format(line, sizeof(line), NULL, &ctx, "abcd0123", 1U) == 0);
    return true;
}

static bool test_ack_status_vocabulary_is_closed(void)
{
    CHECK(strcmp(cg_cmd_ack_status_name(CG_CMD_ACK_ACCEPTED), "ACCEPTED") == 0);
    CHECK(strcmp(cg_cmd_ack_status_name(CG_CMD_ACK_REJECTED), "REJECTED") == 0);
    CHECK(strcmp(cg_cmd_ack_status_name(CG_CMD_ACK_DUPLICATE_CANONICAL),
                 "DUPLICATE_CANONICAL") == 0);
    CHECK(strcmp(cg_cmd_ack_status_name(CG_CMD_ACK_EXPIRED), "EXPIRED") == 0);
    CHECK(strcmp(cg_cmd_ack_status_name(CG_CMD_ACK_SAFETY_BLOCKED), "SAFETY_BLOCKED") == 0);
    CHECK(strcmp(cg_cmd_ack_status_name(CG_CMD_ACK_INVALID_STATE), "INVALID_STATE") == 0);
    CHECK(strcmp(cg_cmd_ack_status_name(CG_CMD_ACK_OUT_OF_RANGE), "OUT_OF_RANGE") == 0);
    /* An out-of-range status is a firmware defect, and must be named UNKNOWN
     * rather than defaulted into a plausible verdict. */
    CHECK(strcmp(cg_cmd_ack_status_name((cg_cmd_ack_status_t)99), "UNKNOWN") == 0);
    return true;
}

/* ------------------------------------------------------------------ */
/* Field encoding and the local console bridge                          */
/* ------------------------------------------------------------------ */

static bool test_fields_record_parses_canonical_set(void)
{
    cg_command_t cmd;
    const char *error = "OK";
    static const char record[] =
        "schema_version=1 command_id=" UUID_A " device_id=" CG_DEVICE_ID
        " created_at_ms=900000 expires_at_ms=1100000 controller_id=PREDICTIVE"
        " policy_version=policy-7 reason_code=PREDICTED_CRITICAL"
        " action_cooling=ON action_duty_permille=250";

    CHECK(cg_command_parse_fields(record, &cmd, &error));
    CHECK(strcmp(error, "OK") == 0);
    CHECK(cmd.schema_version == 1);
    CHECK(cmd.id_form == CG_CMD_ID_FORM_UUID);
    CHECK(cmd.source == CG_CMD_SOURCE_UNKNOWN); /* not stated: not assumed */
    CHECK(cmd.has_created_at && cmd.has_expires_at);
    CHECK(cmd.created_at_ms == 900000ULL && cmd.expires_at_ms == 1100000ULL);
    CHECK(cmd.cooling == CG_CMD_COOLING_ON);
    CHECK(cmd.duty_permille == 250U);
    CHECK(strcmp(cmd.policy_version, "policy-7") == 0);
    CHECK(strcmp(cmd.reason_code, "PREDICTED_CRITICAL") == 0);
    return true;
}

static bool test_fields_record_refers_unknown_and_malformed(void)
{
    cg_command_t cmd;
    const char *error = "OK";

    CHECK(!cg_command_parse_fields("schema_version=1 command_id=x device_id=d surprise=1", &cmd,
                                   &error));
    CHECK(strcmp(error, "UNKNOWN_FIELD") == 0);
    CHECK(!cg_command_parse_fields("schema_version=1 device_id=" CG_DEVICE_ID
                                   " command_id=abc action_cooling=OPEN",
                                   &cmd, &error));
    CHECK(strcmp(error, "BAD_ACTION_COOLING") == 0);
    CHECK(!cg_command_parse_fields("schema_version=1 device_id=" CG_DEVICE_ID
                                   " command_id=abc expires_at_ms=-5",
                                   &cmd, &error));
    CHECK(strcmp(error, "BAD_EXPIRES_AT") == 0);
    CHECK(!cg_command_parse_fields("schema_version=1 command_id=abc", &cmd, &error));
    CHECK(strcmp(error, "MISSING_REQUIRED_FIELD") == 0);
    /* A 37-character identity does not fit the canonical UUID buffer and must be
     * refused outright rather than cut down to a shorter, different id. */
    CHECK(!cg_command_parse_fields(
        "schema_version=1 device_id=d command_id=00000000-0000-4000-8000-00000000000aa", &cmd,
        &error));
    CHECK(strcmp(error, "COMMAND_ID_TOO_LONG") == 0);
    return true;
}

static bool test_local_test_bridge_is_labelled_and_unbounded_by_choice(void)
{
    cg_command_t cmd;
    const char *error = "OK";

    CHECK(cg_command_from_local_test("w06-selftest", CG_CMD_COOLING_ON, 250U, &cmd, &error));
    CHECK(cmd.source == CG_CMD_SOURCE_LOCAL_CONSOLE);
    CHECK(cmd.id_form == CG_CMD_ID_FORM_TEST_TOKEN);
    CHECK(strcmp(cmd.device_id, CG_DEVICE_ID) == 0);
    /* No clock to stamp with, and no operator-typed instant pretending to be one:
     * the record carries no absolute expiry, which the validator turns into the
     * fail-closed path instead of an unbounded command. */
    CHECK(cmd.has_created_at == false);
    CHECK(cmd.has_expires_at == false);

    CHECK(!cg_command_from_local_test("bad id with spaces", CG_CMD_COOLING_ON, 1U, &cmd,
                                      &error));
    CHECK(strcmp(error, "BAD_TEST_ID") == 0);
    CHECK(!cg_command_from_local_test("ok-id", CG_CMD_COOLING_ON, 1001U, &cmd, &error));
    CHECK(strcmp(error, "BAD_TEST_DUTY") == 0);
    return true;
}

static bool test_local_console_command_is_blocked_by_the_validator(void)
{
    /* End to end through the shipped context: the console bridge cannot obtain an
     * acceptance, and the ACK says why. This is the live behaviour on the board,
     * so the reject path is the one that is physically reachable today. */
    cg_cmd_context_t ctx = shipped_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd;
    const char *error = "OK";

    cg_cmd_store_init(&store);
    CHECK(cg_command_from_local_test("w06-selftest", CG_CMD_COOLING_ON, 250U, &cmd, &error));
    cg_command_validate(&cmd, &ctx, &store, &ack);
    CHECK(ack.status == CG_CMD_ACK_REJECTED);
    CHECK(strcmp(ack.reason, "MISSING_CREATED_AT") == 0 ||
          strcmp(ack.reason, "MISSING_EXPIRY") == 0);
    CHECK(ack.applied_cooling == CG_CMD_COOLING_OFF);
    return true;
}

/* ------------------------------------------------------------------ */
/* Console grammar                                                      */
/* ------------------------------------------------------------------ */

static bool test_console_cmdtest_grammar(void)
{
    cg_tec_command_t command;
    const char *error = "OK";

    CHECK(cg_tec_command_parse("CMDTEST w06-selftest ON 250", &command, &error));
    CHECK(command.kind == CG_TEC_CMD_CMDTEST);
    CHECK(strcmp(command.arg, "w06-selftest") == 0);
    CHECK(command.flag == 1U);
    CHECK(command.value == 250U);

    CHECK(cg_tec_command_parse("cmdtest off-run off 0", &command, &error));
    CHECK(command.kind == CG_TEC_CMD_CMDTEST);
    CHECK(command.flag == 0U);

    CHECK(!cg_tec_command_parse("CMDTEST only-two ON", &command, &error));
    CHECK(strcmp(error, "CMDTEST_ARITY") == 0);
    CHECK(!cg_tec_command_parse("CMDTEST id MAYBE 10", &command, &error));
    CHECK(strcmp(error, "CMDTEST_BAD_COOLING") == 0);
    CHECK(!cg_tec_command_parse("CMDTEST id ON 1001", &command, &error));
    CHECK(strcmp(error, "CMDTEST_BAD_DUTY") == 0);
    CHECK(!cg_tec_command_parse("CMDTEST id ON 10 extra", &command, &error));
    CHECK(strcmp(error, "CMDTEST_EXTRA_FIELDS") == 0);
    CHECK(!cg_tec_command_parse("CMDTEST id ON x10", &command, &error));
    CHECK(strcmp(error, "CMDTEST_BAD_DUTY") == 0);
    return true;
}

static bool test_existing_console_verbs_unchanged(void)
{
    cg_tec_command_t command;
    const char *error = "OK";

    /* W06 added a verb; it must not have loosened the arity rules around it. */
    CHECK(!cg_tec_command_parse("ARM deadbeef extra", &command, &error));
    CHECK(strcmp(error, "BAD_ARITY") == 0);
    CHECK(cg_tec_command_parse("ARM deadbeef", &command, &error));
    CHECK(command.kind == CG_TEC_CMD_ARM);
    CHECK(cg_tec_command_parse("START 60", &command, &error));
    CHECK(command.kind == CG_TEC_CMD_START && command.value == 60U);
    CHECK(cg_tec_command_parse("ESTOP", &command, &error));
    CHECK(command.kind == CG_TEC_CMD_ESTOP);
    CHECK(!cg_tec_command_parse("STOP now", &command, &error));
    CHECK(strcmp(error, "BAD_ARITY") == 0);
    return true;
}

/* ------------------------------------------------------------------ */
/* Telemetry frame                                                      */
/* ------------------------------------------------------------------ */

typedef struct {
    cg_tec_control_t ctl;
    cg_snapshot_t snap;
    cg_health_report_t health;
    cg_cmd_state_t state;
    cg_telemetry_frame_t frame;
    char run_id[33];
} fixture_t;

static void fixture_init(fixture_t *fx)
{
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
    fx->snap.door_observed = true;
    fx->snap.door_obs_ms = 999990U;
    fx->ctl.state = CG_TEC_STATE_OFF;
    (void)snprintf(fx->ctl.reason, sizeof(fx->ctl.reason), "%s", "BOOT_SAFE_OFF");
    (void)snprintf(fx->health.overall, sizeof(fx->health.overall), "%s", "NEVER");
    (void)snprintf(fx->run_id, sizeof(fx->run_id), "%s", "CG-S1-A-001");

    fx->frame.seq = 1U;
    fx->frame.boot_id = "abcd0123";
    fx->frame.boot_count = 7;
    fx->frame.uptime_ms = 1000000U;
    fx->frame.run_id = fx->run_id;
    fx->frame.test_phase = "IDLE";
    fx->frame.snap = &fx->snap;
    fx->frame.ctl = &fx->ctl;
    fx->frame.health = &fx->health;
    fx->frame.probe_rom[0] = "287088CA00000051";
    fx->frame.probe_rom[1] = "28AEBF2200000006";
    fx->frame.probe_rom[2] = "28CBE9CA00000072";
    fx->frame.probe_rom[3] = "283BE5C9000000A9";
    fx->frame.role_status = CG_ROM_STATUS;
    fx->frame.cmd_state = &fx->state;
    fx->frame.output_stage_enabled = false;
    fx->frame.fan_available = false;
}

static bool test_no_command_is_named_not_zeroed(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    CHECK(cg_telemetry_format(line, sizeof(line), &fx.frame) > 0U);
    /* "nothing was requested" must not be readable as "was asked to stay off". */
    CHECK(has(line, "command_id=NONE desired_cooling=NONE desired_duty_permille=nan"));
    CHECK(has(line, "last_ack_status=NONE last_ack_reason=NO_COMMAND_RECEIVED"));
    return true;
}

static bool test_desired_and_applied_are_both_published(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];

    fixture_init(&fx);
    fx.state.has_command = true;
    (void)snprintf(fx.state.command_id, sizeof(fx.state.command_id), "%s", UUID_A);
    fx.state.desired_cooling = CG_CMD_COOLING_ON;
    fx.state.desired_duty_permille = 250U;
    fx.state.last_status = CG_CMD_ACK_SAFETY_BLOCKED;
    fx.state.last_reason = "EPOCH_UNSYNCHRONIZED";
    CHECK(cg_telemetry_format(line, sizeof(line), &fx.frame) > 0U);
    CHECK(has(line, "command_id=" UUID_A " desired_cooling=ON desired_duty_permille=250 "
                    "last_ack_status=SAFETY_BLOCKED last_ack_reason=EPOCH_UNSYNCHRONIZED"));
    /* The applied pair is unchanged by the request: still OFF, still 0. */
    CHECK(has(line, "cooling_applied=OFF "));
    CHECK(has(line, "pwm_duty=0 "));
    return true;
}

static bool test_worst_case_fits_after_w06_fields(void)
{
    fixture_t fx;
    char line[CG_TELEMETRY_LINE_MAX];
    size_t len;

    fixture_init(&fx);
    memset(fx.run_id, 'A', 32);
    fx.run_id[32] = '\0';
    fx.frame.seq = 4294967295U;
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
    (void)snprintf(fx.ctl.reason, sizeof(fx.ctl.reason), "%s", "ESTOP_LATCHED_WAITING_CLEAR");
    for (int i = 0; i < CG_PRODUCER_COUNT; i++) {
        fx.health.state[i] = CG_HEALTH_MISSED;
        fx.health.beats[i] = 4294967295U;
        fx.health.max_gap_ms[i] = 4294967295U;
    }
    (void)snprintf(fx.health.overall, sizeof(fx.health.overall), "%s", "MISSED");
    fx.state.has_command = true;
    (void)snprintf(fx.state.command_id, sizeof(fx.state.command_id), "%s", UUID_A);
    fx.state.desired_cooling = CG_CMD_COOLING_ON;
    fx.state.desired_duty_permille = 1000U;
    fx.state.last_status = CG_CMD_ACK_DUPLICATE_CANONICAL;
    fx.state.last_reason = "EPOCH_UNSYNCHRONIZED";

    len = cg_telemetry_format(line, sizeof(line), &fx.frame);
    printf("  w06_worst_case_len=%zu budget=%d\n", len, CG_TELEMETRY_LINE_MAX);
    CHECK(len > 0U);
    CHECK(len < (size_t)CG_TELEMETRY_LINE_MAX);
    /* The widest reason token the command layer can emit still fits. */
    CHECK(has(line, "last_ack_reason=EPOCH_UNSYNCHRONIZED"));
    CHECK(has(line, " raw_spare_status="));
    return true;
}

/* ------------------------------------------------------------------ */
/* Parser hardening (W06 review findings)                              */
/* ------------------------------------------------------------------ */

static bool test_oversized_numbers_are_refused(void)
{
    cg_command_t cmd;
    const char *error = "OK";

    /* 4294967296 duty would be truncated by the uint32_t cast into 0, and
     * 4294967297 into 1: an out-of-range request arriving as "no duty" is the
     * kind of silent narrowing that turns a rejection into an acceptance. */
    CHECK(!cg_command_parse_fields("schema_version=1 device_id=" CG_DEVICE_ID
                                   " command_id=abc action_duty_permille=4294967296",
                                   &cmd, &error));
    CHECK(strcmp(error, "BAD_ACTION_DUTY") == 0);
    /* A 21-digit expiry cannot be represented and must not wrap into range: that
     * would convert a far-future expiry into an apparently valid one. */
    CHECK(!cg_command_parse_fields("schema_version=1 device_id=" CG_DEVICE_ID
                                   " command_id=abc expires_at_ms=99999999999999999999",
                                   &cmd, &error));
    CHECK(strcmp(error, "BAD_EXPIRES_AT") == 0);
    CHECK(!cg_command_parse_fields("schema_version=9999999999 device_id=" CG_DEVICE_ID
                                   " command_id=abc", &cmd, &error));
    CHECK(strcmp(error, "BAD_SCHEMA_VERSION") == 0);
    /* In range, and parsed exactly. */
    CHECK(cg_command_parse_fields("schema_version=1 device_id=" CG_DEVICE_ID
                                  " command_id=abc action_duty_permille=4294967295",
                                  &cmd, &error));
    CHECK(cmd.duty_permille == 4294967295U);
    return true;
}

static bool test_worst_case_ack_fits_its_budget(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_ack_t ack;
    char line[CG_COMMAND_ACK_LINE_MAX];
    int len;

    memset(&ack, 0, sizeof(ack));
    (void)snprintf(ack.command_id, sizeof(ack.command_id), "%s",
                   "00000000-0000-4000-8000-00000000000a");
    ack.id_form = CG_CMD_ID_FORM_UUID;
    ack.source = CG_CMD_SOURCE_LOCAL_CONSOLE;
    ack.status = CG_CMD_ACK_DUPLICATE_CANONICAL;
    ack.canonical_status = CG_CMD_ACK_SAFETY_BLOCKED;
    ack.reason = "OUTPUT_STAGE_COMPILED_OUT";
    ack.desired_cooling = CG_CMD_COOLING_ON;
    ack.desired_duty_permille = 1000U;
    ack.applied_cooling = CG_CMD_COOLING_ON;
    ack.applied_duty_permille = 1000U;
    ack.expiry_evaluable = true;
    ack.uptime_ms = 18446744073709551615ULL;
    ack.telemetry_seq = 4294967295U;
    ack.time_sync = CG_TIME_SYNC_UNSYNCHRONIZED;
    ack.device_mode = "FAULT_LATCH";
    ack.fault_bits = 0xFFFFFFFFU;
    ctx.allowed_duty_max_permille = 4294967295U;

    len = cg_command_ack_format(line, sizeof(line), &ack, &ctx, "abcd0123", 4294967295U);
    printf("  ack_worst_case_len=%d budget=%d\n", len, CG_COMMAND_ACK_LINE_MAX);
    CHECK(len > 0);
    CHECK((size_t)len < sizeof(line));
    /* Ten percent headroom, because the cost of getting this wrong is a silently
     * missing audit record, not a visible failure. */
    CHECK(len * 10 < CG_COMMAND_ACK_LINE_MAX * 9);
    return true;
}

/* ------------------------------------------------------------------ */

typedef struct {
    const char *name;
    bool (*fn)(void);
} test_case_t;

/* ------------------------------------------------------------------ */
/* Derived artifacts: real ACK lines and scenario traces, printed for    */
/* build_contract_artifacts.py to capture. Every byte here comes out of the   */
/* delivered formatter and validator, so the evidence files are generated and  */
/* not typed. They are host scenarios: synthetic commands, injected contexts,    */
/* never a physical actuation and never a captured bench session.                */
/* ------------------------------------------------------------------ */

static void emit_fixture_acks(void)
{
    struct scenario {
        const char *label;
        cg_cmd_context_t ctx;
        cg_cmd_cooling_t cooling;
        uint32_t duty;
        uint64_t created;
        uint64_t expires;
        int repeat;
    } scenarios[5];
    /* Distinct ids per fixture: sharing one id across unrelated fixtures made a
     * demo trace report a phantom replay, because the aggregation key is the
     * command_id itself. */
    const char *ids[5] = {UUID_A, UUID_B, "00000000-0000-4000-8000-00000000000c",
                          "00000000-0000-4000-8000-00000000000d",
                          "00000000-0000-4000-8000-00000000000e"};

    memset(scenarios, 0, sizeof(scenarios));
    scenarios[0].label = "shipped-unsynchronized";
    scenarios[0].ctx = shipped_context();
    scenarios[0].cooling = CG_CMD_COOLING_ON;
    scenarios[0].duty = 250U;
    scenarios[0].created = 1000000ULL;
    scenarios[0].expires = 4000000000ULL;

    scenarios[1].label = "synchronized-accepted";
    scenarios[1].ctx = permissive_context();
    scenarios[1].cooling = CG_CMD_COOLING_ON;
    scenarios[1].duty = 250U;
    scenarios[1].created = 900000ULL;
    scenarios[1].expires = 1100000ULL;

    scenarios[2].label = "synchronized-expired";
    scenarios[2].ctx = permissive_context();
    scenarios[2].cooling = CG_CMD_COOLING_ON;
    scenarios[2].duty = 250U;
    scenarios[2].created = 900000ULL;
    scenarios[2].expires = 950000ULL;

    scenarios[3].label = "wrong-device";
    scenarios[3].ctx = permissive_context();
    scenarios[3].cooling = CG_CMD_COOLING_ON;
    scenarios[3].duty = 250U;
    scenarios[3].created = 900000ULL;
    scenarios[3].expires = 1100000ULL;

    scenarios[4].label = "duplicate-replay";
    scenarios[4].ctx = permissive_context();
    scenarios[4].cooling = CG_CMD_COOLING_ON;
    scenarios[4].duty = 250U;
    scenarios[4].created = 900000ULL;
    scenarios[4].expires = 1100000ULL;
    scenarios[4].repeat = 1;

    for (int index = 0; index < 5; index++) {
        cg_cmd_store_t store;
        cg_cmd_ack_t ack;
        cg_command_t cmd;
        char line[512];
        const char *device = index == 3 ? "coldguard-002" : CG_DEVICE_ID;

        cg_cmd_store_init(&store);
        cmd = make_command(ids[index], device, scenarios[index].cooling, scenarios[index].duty,
                           scenarios[index].created, scenarios[index].expires);
        cg_command_validate(&cmd, &scenarios[index].ctx, &store, &ack);
        if (scenarios[index].repeat) {
            cg_command_validate(&cmd, &scenarios[index].ctx, &store, &ack);
        }
        if (cg_command_ack_format(line, sizeof(line), &ack, &scenarios[index].ctx, "abcd0123",
                                  9U) > 0) {
            printf("FIXTURE_ACK scenario=%s %s\n", scenarios[index].label, line);
        }
    }
}

/* Scenario traces for the three command logs the canonical deliverable list
 * names. Each line is one event: submission, verdict, and the applied state the
 * device reported at that moment. */
static void emit_scenario_traces(void)
{
    cg_cmd_context_t ctx = permissive_context();
    cg_cmd_store_t store;
    cg_cmd_ack_t ack;
    cg_command_t cmd;

    printf("SCENARIO_BEGIN duplicate\n");
    cg_cmd_store_init(&store);
    cmd = make_command(UUID_A, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL, 1100000ULL);
    for (int attempt = 0; attempt < 3; attempt++) {
        ctx.uptime_ms = 1000000ULL + (uint64_t)attempt * 5ULL;
        ctx.telemetry_seq = (uint32_t)(42U + attempt);
        cg_command_validate(&cmd, &ctx, &store, &ack);
        printf("SCENARIO_EVENT scenario=duplicate command_id=%s boot_id=%s attempt=%d "
               "uptime_ms=%llu seq=%u status=%s "
               "reason=%s applied_cooling=%s applied_duty=%lu reapplied=%d\n",
               ack.command_id, SCENARIO_BOOT_ID, attempt,
               (unsigned long long)ack.uptime_ms, ack.telemetry_seq,
               cg_cmd_ack_status_name(ack.status), ack.reason,
               cg_cmd_cooling_name(ack.applied_cooling),
               (unsigned long)ack.applied_duty_permille, ack.reapplied ? 1 : 0);
    }
    printf("SCENARIO_END duplicate applications=%u\n",
           (unsigned)(store.hits == 2U ? 1U : 0U));

    printf("SCENARIO_BEGIN expired\n");
    cg_cmd_store_init(&store);
    ctx.now_ms = 1000000ULL;
    cmd = make_command("00000000-0000-4000-8000-00000000000d", CG_DEVICE_ID, CG_CMD_COOLING_ON,
                       250U, 900000ULL, 950000ULL);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    printf("SCENARIO_EVENT scenario=expired command_id=%s boot_id=%s status=%s reason=%s "
           "expiry_evaluable=%d "
           "applied_cooling=%s\n", ack.command_id, SCENARIO_BOOT_ID,
           cg_cmd_ack_status_name(ack.status), ack.reason,
           ack.expiry_evaluable ? 1 : 0, cg_cmd_cooling_name(ack.applied_cooling));
    printf("SCENARIO_END expired actuation_issued=%d\n", ack.applied_cooling == CG_CMD_COOLING_ON
                                                     ? 1 : 0);

    printf("SCENARIO_BEGIN reset\n");
    cg_cmd_store_init(&store);
    cmd = make_command(UUID_B, CG_DEVICE_ID, CG_CMD_COOLING_ON, 250U, 900000ULL, 1100000ULL);
    cg_command_validate(&cmd, &ctx, &store, &ack);
    printf("SCENARIO_EVENT scenario=reset command_id=%s boot_id=%s phase=before_reset "
           "status=%s applied_cooling=%s\n", ack.command_id, SCENARIO_BOOT_ID,
           cg_cmd_ack_status_name(ack.status), cg_cmd_cooling_name(ack.applied_cooling));
    /* The reset path: a fresh boot re-initialises the volatile store and the
     * controller comes up default-OFF with unresolved limits. */
    cg_cmd_store_init(&store);
    ctx = shipped_context();
    ctx.time_sync = CG_TIME_SYNC_SYNCHRONIZED;
    ctx.now_ms = 1000000ULL;
    cg_command_validate(&cmd, &ctx, &store, &ack);
    printf("SCENARIO_EVENT scenario=reset command_id=%s boot_id=%s phase=after_reset "
           "status=%s reason=%s "
           "duplicate_recognized=%d applied_cooling=%s\n", ack.command_id,
           SCENARIO_BOOT_ID_AFTER_RESET,
           cg_cmd_ack_status_name(ack.status), ack.reason,
           ack.status == CG_CMD_ACK_DUPLICATE_CANONICAL ? 1 : 0,
           cg_cmd_cooling_name(ack.applied_cooling));
    printf("SCENARIO_END reset resumed_actuation=%d\n",
           ack.applied_cooling == CG_CMD_COOLING_ON ? 1 : 0);
}

int main(void)
{
    const test_case_t tests[] = {
        {"unsupported_schema_rejected", test_unsupported_schema_rejected},
        {"wrong_device_rejected", test_wrong_device_rejected},
        {"missing_command_id_rejected", test_missing_command_id_rejected},
        {"missing_expiry_is_not_treated_as_unbounded",
         test_missing_expiry_is_not_treated_as_unbounded},
        {"missing_created_at_rejected", test_missing_created_at_rejected},
        {"inverted_validity_window_rejected", test_inverted_validity_window_rejected},
        {"unsync_clock_blocks_instead_of_assuming_fresh",
         test_unsync_clock_blocks_instead_of_assuming_fresh},
        {"unsync_clock_blocks_even_a_past_expiry",
         test_unsync_clock_blocks_even_a_past_expiry},
        {"expired_when_synchronized", test_expired_when_synchronized},
        {"fresh_when_synchronized_reaches_later_checks",
         test_fresh_when_synchronized_reaches_later_checks},
        {"duty_above_allowed_max_out_of_range", test_duty_above_allowed_max_out_of_range},
        {"duty_not_a_permille_value", test_duty_not_a_permille_value},
        {"on_with_zero_duty_and_off_with_duty_rejected",
         test_on_with_zero_duty_and_off_with_duty_rejected},
        {"shipped_board_blocks_on_request_even_when_fresh",
         test_shipped_board_blocks_on_request_even_when_fresh},
        {"invalid_local_state_rejected", test_invalid_local_state_rejected},
        {"applied_state_comes_from_the_device", test_applied_state_comes_from_the_device},
        {"duplicate_returns_canonical_and_does_not_reapply",
         test_duplicate_returns_canonical_and_does_not_reapply},
        {"pre_identity_rejection_cannot_clobber_the_canonical_result",
         test_pre_identity_rejection_cannot_clobber_the_canonical_result},
        {"local_console_source_is_gated_before_acceptance",
         test_local_console_source_is_gated_before_acceptance},
        {"blocked_duplicate_stays_blocked_canonical",
         test_blocked_duplicate_stays_blocked_canonical},
        {"new_id_same_action_is_a_new_instruction",
         test_new_id_same_action_is_a_new_instruction},
        {"retention_bound_is_explicit", test_retention_bound_is_explicit},
        {"store_is_volatile_across_reset", test_store_is_volatile_across_reset},
        {"ack_line_carries_the_required_payload",
         test_ack_line_carries_the_required_payload},
        {"ack_duplicate_names_canonical_status", test_ack_duplicate_names_canonical_status},
        {"ack_refuses_truncation_and_anonymous_records",
         test_ack_refuses_truncation_and_anonymous_records},
        {"ack_status_vocabulary_is_closed", test_ack_status_vocabulary_is_closed},
        {"fields_record_parses_canonical_set", test_fields_record_parses_canonical_set},
        {"fields_record_refers_unknown_and_malformed",
         test_fields_record_refers_unknown_and_malformed},
        {"local_test_bridge_is_labelled_and_unbounded_by_choice",
         test_local_test_bridge_is_labelled_and_unbounded_by_choice},
        {"local_console_command_is_blocked_by_the_validator",
         test_local_console_command_is_blocked_by_the_validator},
        {"oversized_numbers_are_refused", test_oversized_numbers_are_refused},
        {"worst_case_ack_fits_its_budget", test_worst_case_ack_fits_its_budget},
        {"console_cmdtest_grammar", test_console_cmdtest_grammar},
        {"existing_console_verbs_unchanged", test_existing_console_verbs_unchanged},
        {"no_command_is_named_not_zeroed", test_no_command_is_named_not_zeroed},
        {"desired_and_applied_are_both_published",
         test_desired_and_applied_are_both_published},
        {"worst_case_fits_after_w06_fields", test_worst_case_fits_after_w06_fields},
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

    printf("\n%d/%d W06 scenarios passed\n", passed, total);
    if (passed != total) {
        return 1;
    }
    printf("W06 COMMAND/ACK CONTRACT: ALL SCENARIOS PASS (no actuation path)\n");
    /* Only after every assertion has passed, so an artifact can never be
     * generated from a tree that fails its own tests. */
    emit_fixture_acks();
    emit_scenario_traces();
    return 0;
}
