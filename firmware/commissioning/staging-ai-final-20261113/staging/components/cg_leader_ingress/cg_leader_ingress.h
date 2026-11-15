/*
 * ColdGuard firmware - Leader trusted command ingress (integration component).
 *
 * This is a Leader-owned component outside every delivered member file. It
 * adds the device-side transport slice for the docs/02 §28-§32 command
 * contract that Member A reserved and never shipped: "CG_CMD_SOURCE_NETWORK
 * ... reserved: no transport exists in this build" (cg_command.h). The
 * delivered classification rule stays the single admission authority:
 * cg_command.h states that `source` is not a wire field, only the device
 * layer that received the bytes can stamp it, and authentication belongs to
 * the transport slice with Member C - which exists (canonical envelope,
 * QoS1 publish, backend command store). The ingress stamps NETWORK only for
 * the `#CG CMD ` record form, which the Leader gateway serial writer alone
 * emits; every other line keeps the delivered console behavior.
 *
 * How it works without editing member files:
 *
 * - The component exposes the member headers of firmware/main as include
 *   paths and links against the delivered commands/validator/ACK formatting
 *   unchanged (final-link symbol resolution; no component dependency).
 * - `-Wl,--wrap=cg_console_start` lets the Leader reader replace the console
 *   reader task. The Leader reader keeps the delivered byte state machine
 *   and the delivered parse/queue path for every non-envelope line; its one
 *   deliberate delta is the line capacity, because the delivered
 *   CG_CONSOLE_LINE_MAX (96) cannot physically carry a canonical record
 *   (up to CG_COMMAND_RECORD_MAX + prefix). Records the delivered console
 *   discarded are exactly the records this component exists to admit.
 * - `-Wl,--wrap=cg_log_raw_line` observes the device's own TELEM stream. The
 *   command world Member A's `build_cmd_context` reads from private state
 *   (telemetry seq, boot identity, controller mode, fault bits, applied
 *   pair) is published on every TELEM frame; the observer records those
 *   values from the device's real output, never from a request or an
 *   invented substitute. Between frames the observed seq equals Member A's
 *   `s_telem_seq`, because the counter advances at frame emission.
 *
 * Fail-closed scope (unchanged delivered semantics): a canonical record
 * still comes out of cg_command_validate blocked at EPOCH_UNSYNCHRONIZED on
 * this build (no wall clock), then behind the compiled-out output stage and
 * the unresolved limits, exactly as the delivered validator orders the §29
 * conjuncts. ACCEPTED remains unreachable in firmware here, and the ACK
 * continues to report expiry_evaluable=0 rather than inventing a freshness
 * claim. The netcmd path additionally never routes to the actuator: it
 * calls cg_command_validate and nothing else.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "cg_command.h"

/* The three delivered log primitives the core emits through. cg_command.c
 * and cg_log.c implement them on the device; a host harness provides
 * capture stand-ins with these exact signatures. Declared here because the
 * delivered cg_log.h carries GCC format attributes the host MSVC build
 * cannot parse - the core must stay host-replayable exactly like the
 * delivered W06 contract harness. */
void cg_log_line(const char *fmt, ...);
void cg_log_error(const char *fmt, ...);
bool cg_log_raw_line(const char *line);

/* Line kind the Leader gateway serial writer emits. Requires the trailing
 * space so delivered console lines (and a bare "#CG CMD") stay with the
 * member parser. */
#define CG_LEADER_NETCMD_PREFIX "#CG CMD "
#define CG_LEADER_NETCMD_PREFIX_LEN 8

#define CG_LEADER_NETCMD_LOG "NETCMD"

/* The reader carries records up to CG_COMMAND_RECORD_MAX plus the
 * "#CG CMD " prefix, with slack for the terminator. The delivered console
 * capacity (96) stays what it is on the member side. */
#define CG_LEADER_LINE_MAX (CG_COMMAND_RECORD_MAX + 64)

/* The device's own view of "now" expires after this much of its monotonic
 * uptime without a fresh accepted synchronization record. 60 s is several
 * gateway re-sync periods and short against any command TTL in use. */
#define CG_LEADER_SYNC_STALE_MS 60000U

/* The boot advertises its synchronization challenge on the capability line
 * at start and then re-advertises at this interval, so a gateway that
 * starts or reconnects later than the boot (the normal restart case) can
 * still learn the current boot's challenge without a reset. 15 s stays
 * sparse against 1 Hz telemetry and well inside the demo wait. */
#define CG_LEADER_CAPABILITY_REPEAT_MS 15000U

/* The device world a canonical record is validated against. Everything the
 * validator must see comes from the delivered compile-time configuration,
 * public platform/limit APIs, one snapshot read, or the observed device
 * output - the same sources Member A's own context builder reads. */
typedef struct {
    /* Observed from the device's own TELEM frames. */
    uint32_t telemetry_seq;
    char boot_id[16];
    uint32_t boot_count;
    char device_mode[16]; /* the token cg_tec_state_name publishes as tec_state */
    uint32_t fault_bits;
    bool applied_cooling_on;
    uint32_t applied_duty_permille;
    bool world_observed; /* at least one TELEM frame has been seen this boot */
    /* The delivered compile-time world. */
    bool output_stage_enabled;
    bool limits_resolved;
    uint32_t allowed_duty_max_permille;
    bool local_safety_permits;
    /* Live input validity, from one snapshot read. */
    bool inputs_sufficiently_valid;
    /* The device's own monotonic clock, from the caller. */
    uint64_t uptime_ms;
} cg_leader_world_t;

/* Resets the world to its honest "nothing observed" state: explicit
 * zero/UNKNOWN markers, never plausible-looking stand-in values. */
void cg_leader_world_init(cg_leader_world_t *world);

/* True when the line is the Leader canonical envelope form. */
bool cg_leader_line_is_envelope(const char *line);

/* True when the line is the Leader host-time synchronization form. */
bool cg_leader_line_is_sync(const char *line);

/* True when the line is the Leader capability advertisement the gateway
 * reads to learn the boot challenge. */
bool cg_leader_line_is_capability(const char *line);

/* Absorbs the observed world from one raw log line. Only "#CG TELEM " lines
 * carry a canonical world view; CMDACK and every other kind are read and
 * ignored. Returns true when the line changed any field in `world`. When
 * `complete_view` is non-NULL it reports whether the line carried the full
 * TELEM token set (the delivered formatter appends all of them, so a real
 * frame is always a complete view) - the device shell replaces its tracked
 * world only on complete views, so a degraded or truncated line can never
 * regress a good previous observation. */
bool cg_leader_world_observe_line(const char *line, cg_leader_world_t *world,
                                  bool *complete_view);

/* Handles one canonical record (the text after the envelope prefix): parses
 * it with the delivered parser, stamps the receiving-layer source
 * classification, validates against `world` through the delivered §29
 * chain and its own idempotency store, and emits the delivered `#CG CMDACK`
 * evidence line. Failure evidence follows the delivered logging grammar.
 * Pure C: no scheduler, driver or timer calls. */
void cg_leader_netcmd_handle(const char *record, const cg_leader_world_t *world);

/* Handles one host-time synchronization record (the text after the
 * "#CG SYNC " prefix) carrying `host=<epoch ms> challenge=<8 hex>
 * boot=<boot id>`, with `challenge_commentary` being the random value this
 * boot advertised in its capability line and the device's own monotonic
 * uptime at the moment of receipt.
 *
 * The record is trusted ONLY with a live double attestation from the
 * device's own published stream: the boot id the gateway echoes must equal
 * the boot id the device itself is emitting on every TELEM frame, and the
 * challenge must equal the value this boot generated and advertised. A
 * written serial line alone proves nothing - the echo pair proves the
 * writer read THIS boot's console output (the delivered design's own trust
 * model: authentication belongs to the transport slice, the device keeps
 * the independent fail-closed authority).
 *
 * A host time that regresses below the current anchor is ignored (the
 * device never rewinds already-trusted time). On success the anchor is
 * stored and every later command evaluates expiry against
 * `anchor + (uptime - anchor_uptime)`, going stale (fail-closed, back to
 * the delivered EPOCH_UNSYNCHRONIZED behavior) after
 * CG_LEADER_SYNC_STALE_MS without a fresh record. RAM-only: the state dies
 * with the boot. */
void cg_leader_sync_handle(const char *record, const cg_leader_world_t *world,
                           uint32_t own_challenge);

/* Sync liveness: true only while an accepted anchor exists and has not
 * aged past CG_LEADER_SYNC_STALE_MS of device uptime. */
bool cg_leader_sync_live(uint64_t now_uptime_ms);

/* Host-anchored wall time for the current uptime reading, or 0 when
 * unsynchronized. */
uint64_t cg_leader_sync_now_ms(uint64_t now_uptime_ms);

/* Clears the netcmd idempotency store and the sync state (volatile by the
 * delivered decision: nothing survives a reset; the caller regenerates the
 * challenge with esp_random at boot). */
void cg_leader_netcmd_store_init(void);
