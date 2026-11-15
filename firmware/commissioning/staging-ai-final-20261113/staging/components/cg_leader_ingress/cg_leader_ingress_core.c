/*
 * ColdGuard firmware - Leader netcmd core (pure C, host-replayable).
 *
 * Everything here can be compiled and falsified on the host exactly like the
 * W06 contract harness compiles firmware/main/cg_command.c unchanged. The
 * ESP-IDF shell (cg_leader_ingress.c) supplies observations, the boot
 * challenge and the call site; this file holds the rules.
 */
#include "cg_leader_ingress.h"

#include <string.h>

#include "coldguard_config.h"

/* Presence bits for one TELEM parse pass. A genuine frame carries every
 * watched token (the delivered formatter appends them unconditionally), so
 * presence indicates a complete, internally consistent view rather than a
 * partially legible line; the caller may replace its tracked world only on
 * a complete view. */
#define CG_PRES_SEQ (1U << 0)
#define CG_PRES_BOOT_ID (1U << 1)
#define CG_PRES_BOOT_COUNT (1U << 2)
#define CG_PRES_MODE (1U << 3)
#define CG_PRES_FAULT (1U << 4)
#define CG_PRES_DUTY (1U << 5)
#define CG_PRES_APPLIED (1U << 6)
#define CG_PRES_ALL \
    (CG_PRES_SEQ | CG_PRES_BOOT_ID | CG_PRES_BOOT_COUNT | CG_PRES_MODE | \
     CG_PRES_FAULT | CG_PRES_DUTY | CG_PRES_APPLIED)

/* The delivered command idempotency memory (volatile, cg_command.h
 * decision 2). The member store is private to the commission task, so the
 * netcmd path keeps its own instance of the SAME delivered store type and
 * semantics. The two stores cannot cross-contaminate: the local console
 * bridge builds TEST_TOKEN labels (cg_command_from_local_test) and the
 * envelopes never enter the member bridge - its 33-byte argument cannot
 * carry the canonical field set. */
static cg_cmd_store_t s_store;

/* Host-time state. The PC/gateway/backend clock is the UTC authority; the
 * device keeps only an anchor (the trusted host instant at the last
 * accepted synchronization record) and advances it on its own monotonic
 * uptime - no wall clock is invented, and nothing survives a reset. */
typedef struct {
    bool anchor_valid;
    uint64_t anchor_host_ms;
    uint64_t anchor_uptime_ms; /* device monotonic uptime when accepted */
    uint32_t rejected_challenges; /* wrong/absent/unplausible echoes */
    uint32_t rejected_backsteps;  /* host time older than the anchor */
    uint32_t accepted;
} cg_leader_sync_state_t;

static cg_leader_sync_state_t s_sync;

void cg_leader_world_init(cg_leader_world_t *world)
{
    if (world == NULL) {
        return;
    }
    memset(world, 0, sizeof(*world));
    /* Explicit "not observed" markers. An unobserved world must never look
     * like a plausible one: the ACK echoes these markers instead of
     * claiming a seq, a boot identity or a controller mode it has not
     * read. */
    memcpy(world->boot_id, "UNKNOWN", sizeof("UNKNOWN"));
    memcpy(world->device_mode, "UNKNOWN", sizeof("UNKNOWN"));
}

void cg_leader_netcmd_store_init(void)
{
    cg_cmd_store_init(&s_store);
    memset(&s_sync, 0, sizeof(s_sync));
}

/* Sync liveness: an accepted anchor that has not aged out. After the stale
 * window the device is UNSYNCHRONIZED again by construction - the member
 * fail-closed rule, not a weakening of it. */
bool cg_leader_sync_live(uint64_t now_uptime_ms)
{
    if (!s_sync.anchor_valid) {
        return false;
    }
    return (now_uptime_ms - s_sync.anchor_uptime_ms) <= CG_LEADER_SYNC_STALE_MS;
}

uint64_t cg_leader_sync_now_ms(uint64_t now_uptime_ms)
{
    return s_sync.anchor_host_ms + (now_uptime_ms - s_sync.anchor_uptime_ms);
}

bool cg_leader_line_is_envelope(const char *line)
{
    if (line == NULL) {
        return false;
    }
    /* The trailing space is part of the prefix: it is what separates the
     * envelope form from any delivered console verb. */
    return strncmp(line, "#CG CMD ", 8) == 0;
}

bool cg_leader_line_is_sync(const char *line)
{
    if (line == NULL) {
        return false;
    }
    return strncmp(line, "#CG SYNC ", 9) == 0;
}

bool cg_leader_line_is_capability(const char *line)
{
    if (line == NULL) {
        return false;
    }
    return strncmp(line, "#CG NETCMD status=READY", 23) == 0;
}

/* Copies a bounded token starting after `key` into `dst` (dst capacity in
 * bytes). Returns false when the value is absent, empty or oversized - a
 * truncated identity is a false identity, same rule as the member parser.
 * `terminator` says where the token ends (space by default). */
static bool copy_value_after(const char *line, const char *key,
                             char *dst, size_t cap)
{
    const char *found = strstr(line, key);
    const char *value;
    size_t len = 0U;

    if (found == NULL) {
        return false;
    }
    value = found + strlen(key);
    while (value[len] != '\0' && value[len] != ' ') {
        len++;
    }
    if (len == 0U || len + 1U > cap) {
        return false;
    }
    memcpy(dst, value, len);
    dst[len] = '\0';
    return true;
}

/* Unsigned decimal field: digits only, capped to avoid a silent truncation. */
static bool parse_uint_after(const char *line, const char *key,
                             uint64_t max, uint32_t *out)
{
    const char *found = strstr(line, key);
    const char *value;
    uint64_t value64 = 0U;

    if (found == NULL) {
        return false;
    }
    value = found + strlen(key);
    if (*value < '0' || *value > '9') {
        return false;
    }
    while (*value >= '0' && *value <= '9') {
        value64 = value64 * 10U + (uint64_t)(*value - '0');
        if (value64 > max) {
            return false;
        }
        value++;
    }
    *out = (uint32_t)value64;
    return true;
}

/* Unsigned 64-bit decimal value scanned from the start of `value` (the
 * host epoch milliseconds). The sync record's fields are positional, so
 * the caller slices the value start itself - start-of-record ("host=")
 * and mid-record (" host=") forms are handled at the call site. */
static bool parse_u64_value(const char *value, uint64_t *out)
{
    uint64_t value64 = 0U;

    if (*value < '0' || *value > '9') {
        return false;
    }
    while (*value >= '0' && *value <= '9') {
        if (value64 > (~0ULL - 9ULL) / 10ULL) {
            return false;
        }
        value64 = value64 * 10U + (uint64_t)(*value - '0');
        value++;
    }
    *out = value64;
    return true;
}

/* Hex field rendered as "0x%08lX" (the TELEM fault_code form). */
static bool parse_hex_after(const char *line, const char *key, uint32_t *out)
{
    const char *found = strstr(line, key);
    const char *value;
    uint64_t value64 = 0U;
    unsigned digits = 0U;

    if (found == NULL) {
        return false;
    }
    value = found + strlen(key);
    while ((*value >= '0' && *value <= '9') || (*value >= 'A' && *value <= 'F') ||
           (*value >= 'a' && *value <= 'f')) {
        const char c = *value;
        const uint64_t digit = (uint64_t)(c <= '9' ? c - '0'
                                                   : (c | 0x20U) - 'a' + 10U);
        value64 = (value64 << 4) | digit;
        digits++;
        if (digits > 8U) {
            return false; /* not the published 8-digit hex form; refuse, never mask */
        }
        value++;
    }
    if (digits == 0U) {
        return false;
    }
    *out = (uint32_t)value64;
    return true;
}

/* Bare-8-hex form (the capability challenge echo). */
static bool parse_hex8_value(const char *value, uint32_t *out)
{
    uint64_t value64 = 0U;
    size_t digits = 0U;

    while ((*value >= '0' && *value <= '9') || (*value >= 'A' && *value <= 'F') ||
           (*value >= 'a' && *value <= 'f')) {
        const char c = *value;
        value64 = (value64 << 4) | (uint64_t)(c <= '9' ? c - '0'
                                                       : (c | 0x20U) - 'a' + 10U);
        digits++;
        value++;
    }
    if (digits != 8U) {
        return false;
    }
    *out = (uint32_t)value64;
    return true;
}

bool cg_leader_world_observe_line(const char *line, cg_leader_world_t *world,
                                  bool *complete_view)
{
    const uint64_t max32 = (uint64_t)UINT32_MAX;
    uint32_t value = 0U;
    char token[16];
    unsigned present = 0U;
    bool any = false;

    if (complete_view != NULL) {
        *complete_view = false;
    }
    if (line == NULL || world == NULL) {
        return false;
    }
    /* Only the TELEM frames carry a canonical world view. The CMDACK lines
     * the same stream carries also name boot_id - they are ignored here so
     * an ACK never becomes the source of the world it answered. */
    if (strncmp(line, "#CG TELEM ", 10) != 0) {
        return false;
    }

    if (parse_uint_after(line, " seq=", max32, &value)) {
        world->telemetry_seq = value;
        world->world_observed = true;
        any = true;
        present |= CG_PRES_SEQ;
    }
    if (copy_value_after(line, " boot_id=", token, sizeof(token))) {
        memcpy(world->boot_id, token, strlen(token) + 1U);
        present |= CG_PRES_BOOT_ID;
        any = true;
    }
    if (copy_value_after(line, " tec_state=", token, sizeof(token))) {
        memcpy(world->device_mode, token, strlen(token) + 1U);
        present |= CG_PRES_MODE;
        any = true;
    }
    if (parse_uint_after(line, " boot_count=", max32, &value)) {
        world->boot_count = value;
        present |= CG_PRES_BOOT_COUNT;
        any = true;
    }
    if (parse_hex_after(line, " fault_code=0x", &value)) {
        world->fault_bits = value;
        present |= CG_PRES_FAULT;
        any = true;
    }
    if (parse_uint_after(line, " pwm_duty=", max32, &value)) {
        world->applied_duty_permille = value;
        present |= CG_PRES_DUTY;
        any = true;
    }
    if (strstr(line, " cooling_applied=ON") != NULL) {
        world->applied_cooling_on = true;
        present |= CG_PRES_APPLIED;
        any = true;
    } else if (strstr(line, " cooling_applied=OFF") != NULL) {
        world->applied_cooling_on = false;
        present |= CG_PRES_APPLIED;
        any = true;
    }
    if (complete_view != NULL) {
        *complete_view = present == CG_PRES_ALL;
    }
    return any;
}

void cg_leader_sync_handle(const char *record, const cg_leader_world_t *world,
                           uint32_t own_challenge)
{
    uint64_t host_ms = 0U;
    uint32_t challenge = 0U;
    char boot[16];

    /* Live double attestation from the device's own published stream. A
     * written serial line alone is not a proof of anything; the echo pair
     * proves the writer read THIS boot's console output. The delivered
     * trust model puts authentication in the transport slice - the device
     * keeps its independent fail-closed authorities on top. */
    /* The peeled record starts with its first field: accept "host=" at the
     * start of the record (the shell strips "#CG SYNC ") and the
     * conventional " host=" mid-record form, so a genuine field can never
     * produce a missing-time rejection merely for position. */
    const char *value = NULL;

    if (strncmp(record, "host=", 5) == 0) {
        value = record + 5;
    } else {
        const char *found = strstr(record, " host=");

        if (found != NULL) {
            value = found + strlen(" host=");
        }
    }
    if (value == NULL || parse_u64_value(value, &host_ms) == false) {
        cg_log_line("%s %s event=SYNC result=REJECTED reason=MISSING_HOST_TIME",
                    CG_LOG_PREFIX, CG_LEADER_NETCMD_LOG);
        s_sync.rejected_challenges++;
        return;
    }
    {
        const char *found = strstr(record, " challenge=");
        if (found == NULL || !parse_hex8_value(found + strlen(" challenge="), &challenge)) {
            cg_log_line("%s %s event=SYNC result=REJECTED reason=CHALLENGE_MISMATCH",
                        CG_LOG_PREFIX, CG_LEADER_NETCMD_LOG);
            s_sync.rejected_challenges++;
            return;
        }
    }
    if (challenge != own_challenge) {
        /* An echo from another boot (or an outright counterfeit) cannot
         * anchor this one - fail closed and stay UNSYNCHRONIZED. */
        cg_log_line("%s %s event=SYNC result=REJECTED reason=CHALLENGE_MISMATCH",
                    CG_LOG_PREFIX, CG_LEADER_NETCMD_LOG);
        s_sync.rejected_challenges++;
        return;
    }
    if (!copy_value_after(record, " boot=", boot, sizeof(boot)) ||
        strcmp(boot, world->boot_id) != 0) {
        cg_log_line("%s %s event=SYNC result=REJECTED reason=BOOT_MISMATCH",
                    CG_LOG_PREFIX, CG_LEADER_NETCMD_LOG);
        s_sync.rejected_challenges++;
        return;
    }
    if (s_sync.anchor_valid && host_ms < s_sync.anchor_host_ms) {
        /* Trusted time never rewinds: a regression claim is counted and
         * ignored, and the previous anchor stays authoritative. */
        cg_log_line("%s %s event=SYNC result=REJECTED reason=HOST_TIME_BACKWARD",
                    CG_LOG_PREFIX, CG_LEADER_NETCMD_LOG);
        s_sync.rejected_backsteps++;
        return;
    }
    s_sync.anchor_valid = true;
    s_sync.anchor_host_ms = host_ms;
    s_sync.anchor_uptime_ms = world->uptime_ms;
    s_sync.accepted++;
    cg_log_line("%s %s event=SYNC result=ACCEPTED host=%llu anchor_uptime=%llu",
                CG_LOG_PREFIX, CG_LEADER_NETCMD_LOG,
                (unsigned long long)host_ms,
                (unsigned long long)s_sync.anchor_uptime_ms);
}

void cg_leader_netcmd_handle(const char *record, const cg_leader_world_t *world)
{
    cg_command_t command;
    cg_cmd_context_t ctx;
    cg_cmd_ack_t ack;
    const char *error = "OK";
    char ack_line[CG_COMMAND_ACK_LINE_MAX];
    const bool synced = cg_leader_sync_live(world->uptime_ms);
    int len;

    if (!cg_command_parse_fields(record, &command, &error)) {
        /* No command identity survived the parse, so there is nothing to
         * answer with an ACK (cg_command_ack_format refuses a commandless
         * ACK at the formatter). One stable-token log line is the whole
         * evidence of the refusal. */
        cg_log_line("%s %s event=NETCMD result=PARSE_FAIL error=%s",
                    CG_LOG_PREFIX, CG_LEADER_NETCMD_LOG, error);
        return;
    }

    /* Receiving-layer source classification (cg_command.h: source is not a
     * wire field; the device layer that received the bytes stamps it). The
     * envelope prefix is emitted only by the Leader gateway serial writer,
     * so this stamp says exactly what Member A's contract lets it say: the
     * record arrived through the transport slice. It classifies provenance;
     * authentication stays with the delivering transport. */
    command.source = CG_CMD_SOURCE_NETWORK;

    /* The validator views the world through the same rules Member A's own
     * context builder applies; no conjunct is weakened or skipped. */
    memset(&ctx, 0, sizeof(ctx));
    ctx.device_id = CG_DEVICE_ID;
    /* cg_command.h decision 1: expiry is evaluated only in the issuer clock
     * domain, which the device holds ONLY while a challenge-attested host
     * anchor is live. Without it the device is UNSYNCHRONIZED and every
     * canonical command is blocked rather than honoured - the delivered
     * fail-closed state, unchanged. */
    ctx.time_sync = synced ? CG_TIME_SYNC_SYNCHRONIZED : CG_TIME_SYNC_UNSYNCHRONIZED;
    ctx.now_ms = synced ? cg_leader_sync_now_ms(world->uptime_ms) : 0U;
    ctx.output_stage_enabled = world->output_stage_enabled;
    ctx.limits_resolved = world->limits_resolved;
    ctx.allowed_duty_max_permille = world->allowed_duty_max_permille;
    ctx.local_safety_permits = world->local_safety_permits;
    ctx.inputs_sufficiently_valid = world->inputs_sufficiently_valid;
    ctx.uptime_ms = world->uptime_ms;
    ctx.telemetry_seq = world->telemetry_seq;
    ctx.device_mode = world->device_mode;
    ctx.fault_bits = world->fault_bits;
    ctx.applied_cooling_on = world->applied_cooling_on;
    ctx.applied_duty_permille = world->applied_duty_permille;

    cg_command_validate(&command, &ctx, &s_store, &ack);

    len = cg_command_ack_format(ack_line, sizeof(ack_line), &ack, &ctx,
                                world->boot_id, world->boot_count);
    if (len <= 0 || (size_t)len >= sizeof(ack_line)) {
        cg_log_error("netcmd=ACK_FORMAT_FAIL command_id=%.32s len=%d",
                     command.command_id, len);
        return;
    }
    if (!cg_log_raw_line(ack_line)) {
        cg_log_error("netcmd=ACK_WRITE_FAIL command_id=%.32s", command.command_id);
    }
}
