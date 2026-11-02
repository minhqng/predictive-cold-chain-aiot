/*
 * ColdGuard firmware - canonical device command contract (W06, Member A half).
 *
 * docs/02 §28-§32 (lines 2051-2216) is the command contract. This module implements
 * the DEVICE side of it: the field set a command must carry, the validation
 * chain, the idempotency memory, and the ACK record. It is transport-free on
 * purpose - there is no network stack in this firmware and W06 does not add one
 * - so the same rules are provable on the host and become callable the moment
 * Member C's gateway delivers a command.
 *
 * What W05 already proved about this device governs two decisions here:
 *
 * 1. FAIL CLOSED ON ABSOLUTE EXPIRY. The device has no wall clock
 *    (docs/01 2253-2259: record uptime/sequence, record synchronization state,
 *    do not manufacture false timestamp precision; and the telemetry line emits
 *    `timestamp_utc=UNAVAILABLE`). A canonical `expires_at` is an absolute
 *    instant in the ISSUER's time base. Without a synchronized clock the device
 *    cannot evaluate `now > expires_at` at all.
 *
 *    It therefore does NOT substitute a receive-time TTL. A TTL measured from
 *    receipt proves only that the device saw the command recently; it says
 *    nothing about how long the command sat in a queue before that, so treating
 *    it as freshness would silently replace the canonical semantics with a
 *    weaker one and could actuate on a command that expired minutes earlier.
 *    An unverifiable expiry is a blocked command, with its own reason token, and
 *    the ACK states `expiry_evaluable=0` so nobody downstream reads the block as
 *    "expired" or as "fresh".
 *
 * 2. IDEMPOTENCY MEMORY IS VOLATILE. The store is RAM, never NVS. After a reset
 *    the device has no memory of a previous command and cannot claim
 *    DUPLICATE_CANONICAL; what it can do - and does - is start from the default
 *    OFF state and re-validate. That is the §31.2/§31.3 requirement ("no retained
 *    commands", "does not blindly reapply an old desired command"), and it is why
 *    cross-reset idempotency is deliberately NOT offered: persisting command
 *    identity would be the mechanism by which a stale actuation could come back.
 *
 * 3. ONLY THE CANONICAL SOURCE IS ADMITTED. A record must say where it came from,
 *    and `SOURCE_UNKNOWN` is the zero value that any incomplete construction
 *    carries. Validation refuses acceptance for anything but
 *    `CG_CMD_SOURCE_NETWORK`, so an unlabelled record cannot be accepted by the
 *    absence of a prohibition. The refusal happens before the duplicate lookup,
 *    which also means an inadmissible source cannot read another path's canonical
 *    result out of the store. This classifies provenance; it does not
 *    authenticate it - `source` is not a wire field, only the device layer that
 *    received the bytes can stamp it, and real authentication belongs to the
 *    transport slice with Member C.
 *
 * An ACK is protocol evidence, never physical evidence (docs/02 §32.2, lines 2188-2197):
 * "the device handled the command according to protocol/local validation", not
 * "the chamber cooled". Applied state is reported separately from the requested
 * action, and in this build the output stage is compiled out, so the applied
 * state an ACK can ever report is OFF. The ACK also names the device it came
 * from, taken from the device's own context rather than echoed from the command
 * (docs/02 §32.3, lines 2200-2215).
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* Canonical UUID form is 36 characters; the local test bridge accepts shorter
 * tokens and labels them, so a test identity can never be mistaken for a
 * backend UUID in the evidence. */
#define CG_COMMAND_ID_MAX 37
#define CG_COMMAND_LABEL_MAX 24
#define CG_COMMAND_REASON_MAX 24
#define CG_COMMAND_ID_UUID_LEN 36

/* Largest key=value record cg_command_parse_fields can hold. The parser copies a
 * line into a buffer of this size before splitting it, so a bound below the real
 * maximum silently refuses a legal command as RECORD_TOO_LONG. 331 bytes is the
 * widest canonical record - schema_version(15+9) + command_id(11+36) +
 * device_id(10+23) + created_at_ms(14+20) + expires_at_ms(14+20) +
 * controller_id(14+23) + policy_version(15+23) + reason_code(12+23) +
 * action_cooling(15+3) + action_duty_permille(21+10) - plus 9 separators and the
 * terminator, rounded up. The first W06 cut used 256, which is under that. */
#define CG_COMMAND_RECORD_MAX 512

/* docs/02 §30.3 (lines 2130-2136) leaves retention size as an implementation
 * detail. Eight
 * entries is the honest bound of this implementation: a command older than the
 * eight most recent ids is no longer recognized as a duplicate. */
#define CG_CMD_STORE_CAPACITY 8

typedef enum {
    CG_CMD_ID_FORM_NONE = 0,
    CG_CMD_ID_FORM_UUID,     /* canonical 36-character UUID string */
    CG_CMD_ID_FORM_TEST_TOKEN, /* local console/test bridge only, never backend */
} cg_command_id_form_t;

typedef enum {
    CG_CMD_SOURCE_UNKNOWN = 0,   /* inadmissible: an unlabelled record is not a command */
    CG_CMD_SOURCE_LOCAL_CONSOLE, /* inadmissible: local test bridge, see CMDTEST */
    CG_CMD_SOURCE_NETWORK,       /* the only admitted source; reserved: no transport exists in this build */
} cg_command_source_t;

typedef enum {
    CG_TIME_SYNC_UNSYNCHRONIZED = 0, /* the shipped state: no wall clock at all */
    CG_TIME_SYNC_SYNCHRONIZED,
} cg_time_sync_state_t;

/* docs/02 §32.1 (lines 2172-2186): the closed ACK status set. Nothing outside it
 * may be
 * emitted, so an unlisted outcome is a contract bug rather than a new string. */
typedef enum {
    CG_CMD_ACK_ACCEPTED = 0,
    CG_CMD_ACK_REJECTED,
    CG_CMD_ACK_DUPLICATE_CANONICAL,
    CG_CMD_ACK_EXPIRED,
    CG_CMD_ACK_SAFETY_BLOCKED,
    CG_CMD_ACK_INVALID_STATE,
    CG_CMD_ACK_OUT_OF_RANGE,
} cg_cmd_ack_status_t;

typedef enum {
    CG_CMD_COOLING_OFF = 0,
    CG_CMD_COOLING_ON,
} cg_cmd_cooling_t;

/* The canonical field set of docs/02 §28.1-§28.2 (lines 2053-2086).
 * `created_at_ms`
 * and `expires_at_ms` are absolute instants in the ISSUER clock domain, in ms;
 * they are only comparable to anything when the device is synchronized. */
typedef struct {
    int schema_version;
    char command_id[CG_COMMAND_ID_MAX];
    cg_command_id_form_t id_form;
    char device_id[CG_COMMAND_LABEL_MAX];
    char controller_id[CG_COMMAND_LABEL_MAX];
    char policy_version[CG_COMMAND_LABEL_MAX];
    char reason_code[CG_COMMAND_REASON_MAX];
    uint64_t created_at_ms;
    uint64_t expires_at_ms;
    bool has_created_at;
    bool has_expires_at;
    cg_cmd_cooling_t cooling;
    uint32_t duty_permille;
    cg_command_source_t source;
} cg_command_t;

/* Everything the device must know to validate a command (§29). Supplied by the
 * caller so the rule set stays host-testable, exactly like the W04 limit table
 * injection: the harness can offer a synchronized, resolved, stage-enabled
 * world, while the firmware passes the real one. */
typedef struct {
    const char *device_id;
    cg_time_sync_state_t time_sync;
    uint64_t now_ms;                  /* issuer-clock "now"; valid only if synced */
    bool output_stage_enabled;
    bool limits_resolved;
    uint32_t allowed_duty_max_permille;
    bool local_safety_permits;
    bool inputs_sufficiently_valid;
    uint64_t uptime_ms;               /* the device's own monotonic clock */
    uint32_t telemetry_seq;           /* docs/02 §32.3 "seq/context", line 2208 */
    const char *device_mode;
    uint32_t fault_bits;              /* local controller faults at ACK time */
    /* The physical truth the ACK must report, independent of what was asked.
     * The caller supplies it from the controller and the output layer, so an
     * ACK never derives applied state from the request it is answering. */
    bool applied_cooling_on;
    uint32_t applied_duty_permille;
} cg_cmd_context_t;

typedef struct {
    cg_cmd_ack_status_t status;
    const char *reason;               /* stable token, never free text */
    char command_id[CG_COMMAND_ID_MAX];
    cg_command_id_form_t id_form;
    cg_command_source_t source;
    bool has_command;                 /* false when the record was unusable */
    cg_cmd_cooling_t desired_cooling;
    uint32_t desired_duty_permille;
    /* What the device is in. For a DUPLICATE_CANONICAL this is the applied pair
     * recorded when the command was FIRST answered - the canonical snapshot, not
     * a live reading - so a replay can be audited against the state that produced
     * the original verdict. The current state is on every telemetry frame. */
    cg_cmd_cooling_t applied_cooling;
    uint32_t applied_duty_permille;
    bool expiry_evaluable;
    bool reapplied;                   /* a duplicate never applies a second time */
    /* For DUPLICATE_CANONICAL: the verdict the first submission of this id
     * received. A replay must report the original decision, not a re-decision
     * of it, otherwise the same id could answer differently as the world moved. */
    cg_cmd_ack_status_t canonical_status;
    uint64_t uptime_ms;
    uint32_t telemetry_seq;
    cg_time_sync_state_t time_sync;
    const char *device_mode;
    uint32_t fault_bits;              /* local controller faults at ACK time */
} cg_cmd_ack_t;

/* One stored result per recognized command_id, volatile. */
typedef struct {
    char command_id[CG_COMMAND_ID_MAX];
    cg_cmd_ack_status_t status;
    const char *reason;
    cg_cmd_cooling_t applied_cooling;
    uint32_t applied_duty_permille;
    uint64_t uptime_ms;
    uint32_t telemetry_seq;
    bool used;
} cg_cmd_record_t;

typedef struct {
    cg_cmd_record_t entry[CG_CMD_STORE_CAPACITY];
    unsigned next;
    unsigned hits;    /* duplicates answered from the store */
    unsigned evicted; /* ids forgotten by retention overflow */
} cg_cmd_store_t;

/* What the device currently wants, kept separate from what it is applying. The
 * telemetry frame publishes this so the desired/applied distinction survives
 * into the dataset instead of only living in the ACK moment. */
typedef struct {
    bool has_command;
    char command_id[CG_COMMAND_ID_MAX];
    cg_cmd_cooling_t desired_cooling;
    uint32_t desired_duty_permille;
    cg_cmd_ack_status_t last_status;
    const char *last_reason;
} cg_cmd_state_t;

/* Classifies a command identity: canonical 36-character UUID, a shorter local
 * test token, or neither. Kept public so the console bridge and the host
 * harness classify a id exactly the way the validator does. */
cg_command_id_form_t cg_command_id_form_for(const char *command_id);

void cg_cmd_store_init(cg_cmd_store_t *store);

/* §29, in the contract's own order. Returns the ACK; `store` records the result
 * so a later duplicate returns the canonical one instead of acting again. */
void cg_command_validate(const cg_command_t *command, const cg_cmd_context_t *ctx,
                         cg_cmd_store_t *store, cg_cmd_ack_t *ack);

/* Formats the `#CG CMDACK` evidence line (no trailing newline). Returns the
 * length, or 0 when the line would not fit `cap` - a truncated ACK is worse
 * than no ACK, because it can be misread as a complete verdict.
 *
 * `schema=` here is the COMMAND envelope version of docs/02 §28.1 (1), which is
 * a different stream from the serial telemetry schema in cg_telemetry.h; the two
 * numbers are not interchangeable and the line names neither as the other. */
int cg_command_ack_format(char *buf, size_t cap, const cg_cmd_ack_t *ack,
                          const cg_cmd_context_t *ctx, const char *boot_id, uint32_t boot_count);

const char *cg_cmd_ack_status_name(cg_cmd_ack_status_t status);
const char *cg_cmd_cooling_name(cg_cmd_cooling_t cooling);
const char *cg_cmd_source_name(cg_command_source_t source);
const char *cg_time_sync_name(cg_time_sync_state_t state);
const char *cg_cmd_id_form_name(cg_command_id_form_t form);

/*
 * Device-side encoding of the canonical command: one space-separated
 * key=value record using the docs/02 §28.1 field names
 * (schema_version, command_id, device_id, created_at_ms, expires_at_ms,
 * controller_id, policy_version, reason_code, action_cooling, action_duty_permille).
 *
 * This is Member A's representation of the field SET, not a new wire schema:
 * docs/02 §28.1 (lines 2053-2073) shows a JSON envelope, and JSON belongs to the gateway
 * side (Member C). The validation rules this module applies are transport
 * independent, which is why they can be proven here and reused unchanged when
 * C's delivery path exists. Flagged as an open contract item, not settled here.
 *
 * Two consequences of keeping it a parser rather than a transport:
 *
 * - every field docs/02 §28.2 requires must be present, by name. Absence is
 *   refused with its own reason token, because `memset` of the record would
 *   otherwise turn a missing `action_cooling` into CG_CMD_COOLING_OFF - an
 *   implicit order to stay off that is not what "no action was given" means.
 *   A field named twice is refused too, so a record cannot carry two expiries
 *   and be judged by whichever the parser reached last.
 * - `source` is deliberately not a field here. Only the layer that actually
 *   received the bytes may stamp it, so a parsed record comes out
 *   CG_CMD_SOURCE_UNKNOWN and is inadmissible until such a layer exists. A
 *   command that could label its own source would not be a provenance check at
 *   all, only a string an issuer chose to write.
 */
bool cg_command_parse_fields(const char *text, cg_command_t *out, const char **error);

/* The local console/test bridge builds a canonical record from the short
 * operator form. The source is stamped LOCAL_CONSOLE and the id form is
 * labelled, and cg_command_validate admits only CG_CMD_SOURCE_NETWORK, so this
 * bridge is refused up front (reason SOURCE_NOT_CANONICAL) and can never
 * impersonate a backend command - even if a later clock or transport makes the
 * rest of the chain pass, and even if its command_id matches one the store
 * already answers. */
bool cg_command_from_local_test(const char *command_id, cg_cmd_cooling_t cooling,
                                uint32_t duty_permille, cg_command_t *out,
                                const char **error);
