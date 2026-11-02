/*
 * ColdGuard firmware - canonical device command contract (W06).
 * See cg_command.h for the two decisions this module encodes and why.
 */
#include "cg_command.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "coldguard_config.h"

#define CG_CMD_FIELDS_MAX 24 /* key=value tokens per record */

static const char *copy_token(char *dst, size_t cap, const char *src)
{
    size_t len = strlen(src);
    if (len + 1U > cap) {
        return NULL; /* refuse: a truncated identity is a false identity */
    }
    memcpy(dst, src, len + 1U);
    return dst;
}

const char *cg_cmd_ack_status_name(cg_cmd_ack_status_t status)
{
    switch (status) {
        case CG_CMD_ACK_ACCEPTED:
            return "ACCEPTED";
        case CG_CMD_ACK_REJECTED:
            return "REJECTED";
        case CG_CMD_ACK_DUPLICATE_CANONICAL:
            return "DUPLICATE_CANONICAL";
        case CG_CMD_ACK_EXPIRED:
            return "EXPIRED";
        case CG_CMD_ACK_SAFETY_BLOCKED:
            return "SAFETY_BLOCKED";
        case CG_CMD_ACK_INVALID_STATE:
            return "INVALID_STATE";
        case CG_CMD_ACK_OUT_OF_RANGE:
            return "OUT_OF_RANGE";
        default:
            /* The status set is closed (docs/02 §32.1, lines 2172-2186). An unlisted value is
             * a firmware defect, and naming it UNKNOWN keeps it visible instead
             * of defaulting it into a plausible verdict. */
            return "UNKNOWN";
    }
}

const char *cg_cmd_cooling_name(cg_cmd_cooling_t cooling)
{
    return cooling == CG_CMD_COOLING_ON ? "ON" : "OFF";
}

const char *cg_cmd_source_name(cg_command_source_t source)
{
    switch (source) {
        case CG_CMD_SOURCE_LOCAL_CONSOLE:
            return "LOCAL_CONSOLE";
        case CG_CMD_SOURCE_NETWORK:
            return "NETWORK";
        case CG_CMD_SOURCE_UNKNOWN:
        default:
            return "UNKNOWN";
    }
}

const char *cg_time_sync_name(cg_time_sync_state_t state)
{
    return state == CG_TIME_SYNC_SYNCHRONIZED ? "SYNCHRONIZED" : "UNSYNCHRONIZED";
}

const char *cg_cmd_id_form_name(cg_command_id_form_t form)
{
    switch (form) {
        case CG_CMD_ID_FORM_UUID:
            return "UUID";
        case CG_CMD_ID_FORM_TEST_TOKEN:
            return "TEST_TOKEN";
        case CG_CMD_ID_FORM_NONE:
        default:
            return "NONE";
    }
}

void cg_cmd_store_init(cg_cmd_store_t *store)
{
    memset(store, 0, sizeof(*store));
}

static const cg_cmd_record_t *store_find(const cg_cmd_store_t *store, const char *command_id)
{
    for (unsigned i = 0; i < CG_CMD_STORE_CAPACITY; i++) {
        if (store->entry[i].used && strcmp(store->entry[i].command_id, command_id) == 0) {
            return &store->entry[i];
        }
    }
    return NULL;
}

static void store_put(cg_cmd_store_t *store, const cg_cmd_ack_t *ack)
{
    cg_cmd_record_t *slot = &store->entry[store->next];

    /* Overwriting a live slot means an id has left the retention window. The
     * count is evidence, not decoration: it states how often this device could
     * no longer recognize a replay, which is the bound docs/02 §30.3 (2130-2136) leaves
     * to implementation. */
    if (slot->used && strcmp(slot->command_id, ack->command_id) != 0) {
        store->evicted++;
    }
    memcpy(slot->command_id, ack->command_id, sizeof(slot->command_id));
    slot->status = ack->status;
    slot->reason = ack->reason;
    slot->applied_cooling = ack->applied_cooling;
    slot->applied_duty_permille = ack->applied_duty_permille;
    slot->uptime_ms = ack->uptime_ms;
    slot->telemetry_seq = ack->telemetry_seq;
    slot->used = true;
    store->next = (store->next + 1U) % CG_CMD_STORE_CAPACITY;
}

static bool id_is_uuid_form(const char *text)
{
    size_t len = strlen(text);

    if (len != CG_COMMAND_ID_UUID_LEN) {
        return false;
    }
    /* 8-4-4-4-12 with hyphens at 8, 13, 18, 23. */
    if (text[8] != '-' || text[13] != '-' || text[18] != '-' || text[23] != '-') {
        return false;
    }
    for (size_t i = 0; i < len; i++) {
        if (i == 8U || i == 13U || i == 18U || i == 23U) {
            continue;
        }
        const char c = text[i];
        const bool hex = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') ||
                         (c >= 'a' && c <= 'f');
        if (!hex) {
            return false;
        }
    }
    return true;
}

static bool id_is_test_token_form(const char *text)
{
    size_t len = strlen(text);

    if (len == 0U || len >= CG_COMMAND_ID_MAX) {
        return false;
    }
    for (size_t i = 0; i < len; i++) {
        const char c = text[i];
        const bool ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                        (c >= '0' && c <= '9') || c == '_' || c == '-';
        if (!ok) {
            return false;
        }
    }
    return true;
}

cg_command_id_form_t cg_command_id_form_for(const char *command_id)
{
    if (command_id == NULL || command_id[0] == '\0') {
        return CG_CMD_ID_FORM_NONE;
    }
    if (id_is_uuid_form(command_id)) {
        return CG_CMD_ID_FORM_UUID;
    }
    if (id_is_test_token_form(command_id)) {
        return CG_CMD_ID_FORM_TEST_TOKEN;
    }
    return CG_CMD_ID_FORM_NONE;
}

static void ack_start(cg_cmd_ack_t *ack, const cg_command_t *command,
                      const cg_cmd_context_t *ctx, const char *reason)
{
    memset(ack, 0, sizeof(*ack));
    ack->reason = reason;
    ack->status = CG_CMD_ACK_REJECTED;
    ack->has_command = command != NULL && ctx != NULL;
    if (command != NULL) {
        memcpy(ack->command_id, command->command_id, sizeof(ack->command_id));
        ack->id_form = command->id_form;
        ack->source = command->source;
        ack->desired_cooling = command->cooling;
        ack->desired_duty_permille = command->duty_permille;
    }
    if (ctx != NULL) {
        ack->uptime_ms = ctx->uptime_ms;
        ack->telemetry_seq = ctx->telemetry_seq;
        ack->time_sync = ctx->time_sync;
        ack->device_mode = ctx->device_mode != NULL ? ctx->device_mode : "UNKNOWN";
        ack->fault_bits = ctx->fault_bits;
        /* Reported, never inferred from the request. */
        ack->applied_cooling = ctx->applied_cooling_on ? CG_CMD_COOLING_ON : CG_CMD_COOLING_OFF;
        ack->applied_duty_permille = ctx->applied_duty_permille;
    } else {
        ack->device_mode = "UNKNOWN";
    }
}

void cg_command_validate(const cg_command_t *command, const cg_cmd_context_t *ctx,
                         cg_cmd_store_t *store, cg_cmd_ack_t *ack)
{
    if (ack == NULL) {
        return;
    }
    if (command == NULL || ctx == NULL) {
        ack_start(ack, command, ctx, "MISSING_CONTEXT");
        return;
    }

    ack_start(ack, command, ctx, "NONE");

    /* §29 conjunct 1: schema valid. */
    if (command->schema_version != 1) {
        ack->status = CG_CMD_ACK_REJECTED;
        ack->reason = "UNSUPPORTED_SCHEMA";
        /* Not stored: the record is not a command this contract recognises, so
         * it has no canonical result to remember. Storing it under its id would
         * let a malformed submission clobber the verdict a valid earlier attempt
         * of the same id earned, and the next replay would return the wrong
         * canonical status. */
        return;
    }

    /* §29 conjunct 2: target device. A command addressed to another device is
     * rejected even if every other condition holds, so a bus- or topic-wide
     * broadcast cannot actuate this board. Not stored, for the same reason as
     * above: this device never owned that command identity. */
    if (ctx->device_id == NULL || command->device_id[0] == '\0' ||
        strcmp(ctx->device_id, command->device_id) != 0) {
        ack->status = CG_CMD_ACK_REJECTED;
        ack->reason = "DEVICE_ID_MISMATCH";
        return;
    }

    if (command->command_id[0] == '\0' || command->id_form == CG_CMD_ID_FORM_NONE) {
        ack->status = CG_CMD_ACK_REJECTED;
        ack->reason = "MISSING_COMMAND_ID";
        return; /* nothing to remember, so nothing is stored */
    }

    /* Admission. docs/02 §29 does not list a source conjunct, because it assumes
     * the record arrived through §28's contract; on this device that assumption
     * has to be tested, since a record can be built by the local console bridge
     * or by a parser that never saw a transport at all. Only the canonical
     * network source is admitted, so UNKNOWN (the zero value, and what any
     * incomplete construction carries) and LOCAL_CONSOLE both fail closed instead
     * of being accepted by absence of a prohibition.
     *
     * This classifies provenance, it does not authenticate it: nothing here
     * proves a NETWORK-labelled record really came from the gateway. Authentication
     * belongs to the transport slice with Member C, and until that exists this
     * field is trusted input, not a security boundary. */
    if (command->source != CG_CMD_SOURCE_NETWORK) {
        ack->status = CG_CMD_ACK_SAFETY_BLOCKED;
        ack->reason = "SOURCE_NOT_CANONICAL";
        return; /* refused before the store: see the ordering note below */
    }

    /* §29 conjunct 3 + §30.1: recognized or new. A duplicate must not create a
     * second independent application; it returns the canonical stored result.
     * The check runs before freshness and range, because re-deciding them for a
     * command already answered would let a replayed id reach a different verdict
     * as the world moved on. */
    if (store != NULL) {
        const cg_cmd_record_t *seen = store_find(store, command->command_id);
        if (seen != NULL) {
            store->hits++;
            ack->status = CG_CMD_ACK_DUPLICATE_CANONICAL;
            ack->reason = seen->reason;
            ack->applied_cooling = seen->applied_cooling;
            ack->applied_duty_permille = seen->applied_duty_permille;
            /* The canonical status is the ORIGINAL verdict, carried so a replay
             * cannot reach a different decision as the world moved on.
             * expiry_evaluable still describes this command's own clock. */
            ack->reapplied = false;
            ack->canonical_status = seen->status;
            return;
        }
    }

    /* §29 conjunct 4 + §31.1: freshness, and only if it can be evaluated. */
    if (!command->has_expires_at) {
        /* §28.2 makes expiry a required field. Absent expiry is not "never
         * expires" - that reading would turn a malformed command into the most
         * dangerous kind, an unbounded one. */
        ack->status = CG_CMD_ACK_REJECTED;
        ack->reason = "MISSING_EXPIRY";
        if (store != NULL) {
            store_put(store, ack);
        }
        return;
    }
    if (!command->has_created_at) {
        ack->status = CG_CMD_ACK_REJECTED;
        ack->reason = "MISSING_CREATED_AT";
        if (store != NULL) {
            store_put(store, ack);
        }
        return;
    }
    if (command->expires_at_ms <= command->created_at_ms) {
        ack->status = CG_CMD_ACK_OUT_OF_RANGE;
        ack->reason = "BAD_VALIDITY_WINDOW";
        if (store != NULL) {
            store_put(store, ack);
        }
        return;
    }

    if (ctx->time_sync != CG_TIME_SYNC_SYNCHRONIZED) {
        /* THE fail-closed case this slice exists for. The device cannot compare
         * its clock to the issuer's, so it cannot honour nor disprove the
         * expiry. Acting would assume freshness; discarding as EXPIRED would
         * claim an age it cannot measure. It is blocked, explicitly labelled
         * unevaluable, and no receive-time TTL is substituted. */
        ack->status = CG_CMD_ACK_SAFETY_BLOCKED;
        ack->reason = "EPOCH_UNSYNCHRONIZED";
        ack->expiry_evaluable = false;
        if (store != NULL) {
            store_put(store, ack);
        }
        return;
    }

    ack->expiry_evaluable = true;
    if (ctx->now_ms > command->expires_at_ms) {
        ack->status = CG_CMD_ACK_EXPIRED;
        ack->reason = "EXPIRED";
        if (store != NULL) {
            store_put(store, ack);
        }
        return;
    }

    /* §29 conjunct 5: action inside the allowed range. */
    if (command->duty_permille > 1000U) {
        ack->status = CG_CMD_ACK_OUT_OF_RANGE;
        ack->reason = "DUTY_NOT_A_PERCENT";
        if (store != NULL) {
            store_put(store, ack);
        }
        return;
    }
    if (command->cooling == CG_CMD_COOLING_ON) {
        if (command->duty_permille == 0U) {
            ack->status = CG_CMD_ACK_OUT_OF_RANGE;
            ack->reason = "ON_WITH_ZERO_DUTY";
            if (store != NULL) {
                store_put(store, ack);
            }
            return;
        }
        if (command->duty_permille > ctx->allowed_duty_max_permille) {
            ack->status = CG_CMD_ACK_OUT_OF_RANGE;
            ack->reason = "DUTY_ABOVE_ALLOWED_MAX";
            if (store != NULL) {
                store_put(store, ack);
            }
            return;
        }
    } else if (command->duty_permille != 0U) {
        ack->status = CG_CMD_ACK_OUT_OF_RANGE;
        ack->reason = "OFF_WITH_NONZERO_DUTY";
        if (store != NULL) {
            store_put(store, ack);
        }
        return;
    }

    /* §29 conjuncts 6 and 7: local safety and local state. Backend
     * authorization does not replace either (docs/02 §29, line 2110). */
    if (!ctx->local_safety_permits) {
        ack->status = CG_CMD_ACK_SAFETY_BLOCKED;
        ack->reason = !ctx->output_stage_enabled
                          ? "OUTPUT_STAGE_COMPILED_OUT"
                          : (!ctx->limits_resolved ? "LIMITS_UNRESOLVED" : "LOCAL_SAFETY_BLOCKED");
        if (store != NULL) {
            store_put(store, ack);
        }
        return;
    }
    if (!ctx->inputs_sufficiently_valid) {
        ack->status = CG_CMD_ACK_INVALID_STATE;
        ack->reason = "SENSORS_INVALID_OR_STALE";
        if (store != NULL) {
            store_put(store, ack);
        }
        return;
    }

    /* Every conjunct held, and the source was admitted at the top. The device
     * records the desired state and answers
     * ACCEPTED - which is protocol evidence only (§32.2). Physical application
     * stays behind the existing controller, which is what actually enforces the
     * bounded duration, the faults and the compile-out guards. */
    ack->status = CG_CMD_ACK_ACCEPTED;
    ack->reason = "NONE";
    if (store != NULL) {
        store_put(store, ack);
    }
}

static void append(char **cursor, size_t *left, bool *overflow, const char *fmt, ...)
{
    va_list args;
    int written;

    if (*overflow || *left == 0U) {
        *overflow = true;
        return;
    }
    va_start(args, fmt);
    written = vsnprintf(*cursor, *left, fmt, args);
    va_end(args);
    if (written < 0 || (size_t)written >= *left) {
        *overflow = true;
        return;
    }
    *cursor += (size_t)written;
    *left -= (size_t)written;
}

int cg_command_ack_format(char *buf, size_t cap, const cg_cmd_ack_t *ack,
                          const cg_cmd_context_t *ctx, const char *boot_id, uint32_t boot_count)
{
    char *cursor = buf;
    size_t left = cap;
    bool overflow = false;

    if (buf == NULL || cap == 0U) {
        return 0;
    }
    buf[0] = '\0';
    if (ack == NULL || ack->command_id[0] == '\0') {
        return 0; /* an ACK that names no command is not evidence of anything */
    }

    append(&cursor, &left, &overflow,
           "#CG CMDACK schema=1 event=ACK command_id=%s command_id_form=%s source=%s "
           "device_id=%s boot_id=%s boot_count=%lu uptime_ms=%llu ack_seq=%lu status=%s reason=%s "
           "desired_cooling=%s desired_duty_permille=%lu applied_cooling=%s "
           "applied_duty_permille=%lu reapplied=%d expiry_evaluable=%d "
           "time_sync_state=%s device_mode=%s fault_code=0x%08lX",
           ack->command_id, cg_cmd_id_form_name(ack->id_form), cg_cmd_source_name(ack->source),
           /* docs/02 §32.3 (2200-2215) requires device_id in the ACK payload. It
            * comes from the device's own context, never from the command's
            * device_id field: echoing a requested identity back would make the
            * ACK evidence of a name the device only repeated. */
           (ctx != NULL && ctx->device_id != NULL && ctx->device_id[0] != '\0')
               ? ctx->device_id
               : "MISSING_CONTEXT",
           boot_id != NULL ? boot_id : "UNKNOWN", (unsigned long)boot_count,
           (unsigned long long)ack->uptime_ms, (unsigned long)ack->telemetry_seq,
           cg_cmd_ack_status_name(ack->status), ack->reason != NULL ? ack->reason : "NONE",
           cg_cmd_cooling_name(ack->desired_cooling), (unsigned long)ack->desired_duty_permille,
           cg_cmd_cooling_name(ack->applied_cooling), (unsigned long)ack->applied_duty_permille,
           ack->reapplied ? 1 : 0, ack->expiry_evaluable ? 1 : 0,
           cg_time_sync_name(ack->time_sync),
           ack->device_mode != NULL ? ack->device_mode : "UNKNOWN",
           (unsigned long)ack->fault_bits);

    if (ack->status == CG_CMD_ACK_DUPLICATE_CANONICAL) {
        append(&cursor, &left, &overflow, " canonical_status=%s",
               cg_cmd_ack_status_name(ack->canonical_status));
    }

    if (ctx != NULL) {
        append(&cursor, &left, &overflow, " output_stage=%s allowed_duty_max_permille=%lu",
               ctx->output_stage_enabled ? "ENABLED" : "DISABLED",
               (unsigned long)ctx->allowed_duty_max_permille);
    }

    if (overflow) {
        buf[0] = '\0';
        return 0;
    }
    return (int)strlen(buf);
}

/* ------------------------------------------------------------------ */
/* Device-side field encoding                                          */
/* ------------------------------------------------------------------ */

/* Digits beyond this length cannot be represented in uint64_t, and a parser that
 * silently wrapped would turn a far-future `expires_at` into an in-range one -
 * the exact inversion of fail-closed that this slice exists to prevent. */
#define CG_CMD_MAX_DIGITS 20U

static bool value_is_number(const char *text, size_t max_digits)
{
    size_t len = 0U;

    if (text == NULL || *text == '\0') {
        return false;
    }
    while (*text != '\0') {
        if (*text < '0' || *text > '9') {
            return false;
        }
        len++;
        if (len > max_digits) {
            return false;
        }
        text++;
    }
    return true;
}

/* Decimal parse with the overflow check inside it. A digit-count bound alone is
 * not enough: 20 digits can still exceed UINT64_MAX, and a wrapped `expires_at`
 * could turn a far-future expiry into an in-range one - the precise inversion of
 * the fail-closed rule this slice exists to enforce. */
static bool parse_u64_checked(const char *text, uint64_t *out)
{
    uint64_t value = 0U;

    while (*text != '\0') {
        const uint64_t digit = (uint64_t)(*text - '0');
        if (value > (UINT64_MAX - digit) / 10ULL) {
            return false;
        }
        value = value * 10ULL + digit;
        text++;
    }
    *out = value;
    return true;
}

/* Field slots in the order the parser tests them. A record that names one field
 * twice is refused: a later copy silently overwriting an earlier one would let a
 * malformed command carry two expiries and be judged by whichever the parser
 * reached last. */
enum cg_cmd_field {
    CG_FIELD_SCHEMA_VERSION = 0,
    CG_FIELD_COMMAND_ID,
    CG_FIELD_DEVICE_ID,
    CG_FIELD_CREATED_AT,
    CG_FIELD_EXPIRES_AT,
    CG_FIELD_CONTROLLER_ID,
    CG_FIELD_POLICY_VERSION,
    CG_FIELD_REASON_CODE,
    CG_FIELD_ACTION_COOLING,
    CG_FIELD_ACTION_DUTY,
    CG_FIELD_COUNT
};

static int cg_command_field_index(const char *key)
{
    static const char *const names[CG_FIELD_COUNT] = {
        "schema_version", "command_id", "device_id", "created_at_ms", "expires_at_ms",
        "controller_id", "policy_version", "reason_code", "action_cooling",
        "action_duty_permille",
    };

    for (int i = 0; i < (int)CG_FIELD_COUNT; i++) {
        if (strcmp(key, names[i]) == 0) {
            return i;
        }
    }
    return -1;
}

/* Why each field is mandatory. docs/02 §28.2 (2075-2086) lists the required set:
 * stable command_id, target device, issue/create time, expiry, requested action,
 * policy provenance, reason. controller_id is §28.3 optional, so its token is
 * empty and its absence never refuses a record. */
static const char *const cg_command_required_tokens[CG_FIELD_COUNT] = {
    "MISSING_SCHEMA_VERSION",
    "MISSING_COMMAND_ID",
    "MISSING_DEVICE_ID",
    "MISSING_CREATED_AT",
    "MISSING_EXPIRES_AT",
    "",                    /* controller_id: optional per §28.3 */
    "MISSING_POLICY_VERSION",
    "MISSING_REASON_CODE",
    "MISSING_ACTION_COOLING",
    "MISSING_ACTION_DUTY",
};

bool cg_command_parse_fields(const char *text, cg_command_t *out, const char **error)
{
    char buffer[256];
    size_t len;
    size_t seen = 0U;
    int field = -1;
    unsigned seen_fields = 0U;
    char *cursor;

    if (error != NULL) {
        *error = "OK";
    }
    if (text == NULL || out == NULL) {
        if (error != NULL) {
            *error = "NULL_RECORD";
        }
        return false;
    }
    len = strlen(text);
    if (len == 0U || len >= sizeof(buffer)) {
        if (error != NULL) {
            *error = len == 0U ? "EMPTY_RECORD" : "RECORD_TOO_LONG";
        }
        return false;
    }
    memcpy(buffer, text, len + 1U);
    memset(out, 0, sizeof(*out));

    cursor = buffer;
    for (;;) {
        char *space;
        char *eq;
        char *key;
        char *value;

        while (*cursor == ' ') {
            cursor++;
        }
        if (*cursor == '\0') {
            break;
        }
        if (seen >= CG_CMD_FIELDS_MAX) {
            if (error != NULL) {
                *error = "TOO_MANY_FIELDS";
            }
            return false;
        }
        space = strchr(cursor, ' ');
        if (space != NULL) {
            *space = '\0';
        }
        eq = strchr(cursor, '=');
        if (eq == NULL || eq == cursor || eq[1] == '\0') {
            if (error != NULL) {
                *error = "BAD_FIELD";
            }
            return false;
        }
        *eq = '\0';
        key = cursor;
        value = eq + 1;
        seen++;

        field = cg_command_field_index(key);
        if (field >= 0) {
            if (seen_fields & (1U << (unsigned)field)) {
                if (error != NULL) {
                    *error = "DUPLICATE_FIELD";
                }
                return false;
            }
            seen_fields |= 1U << (unsigned)field;
        }

        if (strcmp(key, "schema_version") == 0) {
            if (!value_is_number(value, 9U)) {
                if (error != NULL) {
                    *error = "BAD_SCHEMA_VERSION";
                }
                return false;
            }
            {
                uint64_t wide_schema;
                if (!parse_u64_checked(value, &wide_schema) || wide_schema > 2147483647ULL) {
                    if (error != NULL) {
                        *error = "BAD_SCHEMA_VERSION";
                    }
                    return false;
                }
                out->schema_version = (int)wide_schema;
            }
        } else if (strcmp(key, "command_id") == 0) {
            if (copy_token(out->command_id, sizeof(out->command_id), value) == NULL) {
                if (error != NULL) {
                    *error = "COMMAND_ID_TOO_LONG";
                }
                return false;
            }
            if (id_is_uuid_form(out->command_id)) {
                out->id_form = CG_CMD_ID_FORM_UUID;
            } else if (id_is_test_token_form(out->command_id)) {
                out->id_form = CG_CMD_ID_FORM_TEST_TOKEN;
            } else {
                if (error != NULL) {
                    *error = "BAD_COMMAND_ID_FORM";
                }
                return false;
            }
        } else if (strcmp(key, "device_id") == 0) {
            if (copy_token(out->device_id, sizeof(out->device_id), value) == NULL) {
                if (error != NULL) {
                    *error = "DEVICE_ID_TOO_LONG";
                }
                return false;
            }
        } else if (strcmp(key, "created_at_ms") == 0) {
            if (!value_is_number(value, CG_CMD_MAX_DIGITS)) {
                if (error != NULL) {
                    *error = "BAD_CREATED_AT";
                }
                return false;
            }
            if (!parse_u64_checked(value, &out->created_at_ms)) {
                if (error != NULL) {
                    *error = "BAD_CREATED_AT";
                }
                return false;
            }
            out->has_created_at = true;
        } else if (strcmp(key, "expires_at_ms") == 0) {
            if (!value_is_number(value, CG_CMD_MAX_DIGITS)) {
                if (error != NULL) {
                    *error = "BAD_EXPIRES_AT";
                }
                return false;
            }
            if (!parse_u64_checked(value, &out->expires_at_ms)) {
                if (error != NULL) {
                    *error = "BAD_EXPIRES_AT";
                }
                return false;
            }
            out->has_expires_at = true;
        } else if (strcmp(key, "controller_id") == 0 || strcmp(key, "policy_version") == 0 ||
                   strcmp(key, "reason_code") == 0) {
            char *dst = strcmp(key, "controller_id") == 0
                            ? out->controller_id
                            : (strcmp(key, "policy_version") == 0 ? out->policy_version
                                                                  : out->reason_code);
            size_t cap = strcmp(key, "reason_code") == 0 ? CG_COMMAND_REASON_MAX
                                                         : CG_COMMAND_LABEL_MAX;
            if (copy_token(dst, cap, value) == NULL) {
                if (error != NULL) {
                    *error = "LABEL_TOO_LONG";
                }
                return false;
            }
        } else if (strcmp(key, "action_cooling") == 0) {
            if (strcmp(value, "ON") == 0) {
                out->cooling = CG_CMD_COOLING_ON;
            } else if (strcmp(value, "OFF") == 0) {
                out->cooling = CG_CMD_COOLING_OFF;
            } else {
                /* OPEN/CLOSED/1/0 are not the canonical cooling vocabulary
                 * (docs/01 2174-2189 fixes it at ON/OFF). */
                if (error != NULL) {
                    *error = "BAD_ACTION_COOLING";
                }
                return false;
            }
        } else if (strcmp(key, "action_duty_permille") == 0) {
            uint64_t wide;

            /* The field is uint32_t; a value that would be truncated into range
             * by the cast must be refused, not narrowed. 4294967296 would
             * otherwise arrive as duty 0, and 4294967297 as duty 1. */
            if (!value_is_number(value, 10U)) {
                if (error != NULL) {
                    *error = "BAD_ACTION_DUTY";
                }
                return false;
            }
            if (!parse_u64_checked(value, &wide) || wide > 4294967295ULL) {
                if (error != NULL) {
                    *error = "BAD_ACTION_DUTY";
                }
                return false;
            }
            out->duty_permille = (uint32_t)wide;
        } else {
            if (error != NULL) {
                *error = "UNKNOWN_FIELD";
            }
            return false; /* §29 conjunct 1: only the supported schema is accepted */
        }

        if (space == NULL) {
            break;
        }
        cursor = space + 1;
    }

    /* Refuse an incomplete record in the parser rather than downstream. Without
     * this, `memset(out, 0, ...)` at the top made an absent action_cooling read
     * as CG_CMD_COOLING_OFF - a zero value that is a real, executable command to
     * stay off - and a record missing policy provenance or reason still reached
     * the validator. docs/01 §19 is explicit that an unknown must not silently
     * become normal, and §28.2 makes these fields required, so absence is its own
     * stable reason token and never an inferred intent. */
    for (int i = 0; i < (int)CG_FIELD_COUNT; i++) {
        if (((seen_fields & (1U << (unsigned)i)) == 0U) &&
            cg_command_required_tokens[i][0] != '\0') {
            if (error != NULL) {
                *error = cg_command_required_tokens[i];
            }
            return false;
        }
    }
    return true;
}

bool cg_command_from_local_test(const char *command_id, cg_cmd_cooling_t cooling,
                                uint32_t duty_permille, cg_command_t *out, const char **error)
{
    if (error != NULL) {
        *error = "OK";
    }
    if (out == NULL) {
        if (error != NULL) {
            *error = "NULL_RECORD";
        }
        return false;
    }
    memset(out, 0, sizeof(*out));
    if (command_id == NULL || !id_is_test_token_form(command_id)) {
        if (error != NULL) {
            *error = "BAD_TEST_ID";
        }
        return false;
    }
    if (duty_permille > 1000U) {
        if (error != NULL) {
            *error = "BAD_TEST_DUTY";
        }
        return false;
    }
    out->schema_version = 1;
    memcpy(out->command_id, command_id, strlen(command_id) + 1U);
    /* Labelled TEST_TOKEN so a locally issued identity can never be read as a
     * backend UUID in the evidence, and source-stamped so the two command paths
     * stay distinguishable in the log. */
    out->id_form = CG_CMD_ID_FORM_TEST_TOKEN;
    out->source = CG_CMD_SOURCE_LOCAL_CONSOLE;
    (void)copy_token(out->device_id, sizeof(out->device_id), CG_DEVICE_ID);
    (void)copy_token(out->controller_id, sizeof(out->controller_id), "LOCAL_TEST");
    (void)copy_token(out->policy_version, sizeof(out->policy_version), "local-0");
    (void)copy_token(out->reason_code, sizeof(out->reason_code), "OPERATOR_TEST");
    out->cooling = cooling;
    out->duty_permille = duty_permille;
    /* created_at/expires_at are deliberately NOT set: the device has no clock to
     * stamp them with and an operator-typed instant is not a synchronized time
     * base. The validator's fail-closed path is what handles that, which is the
     * point of the local bridge rather than a limitation of it. */
    return true;
}
