/*
 * ColdGuard firmware - MC-38 door contact (Member A, W02).
 *
 * docs/01 section 8:
 *   - the raw electrical level -> OPEN/CLOSED mapping must be physically
 *     commissioned; while CG_DOOR_POLARITY_CONFIRMED is 0 the semantic
 *     state is UNVERIFIED and only the raw level is evidence;
 *   - debounce is allowed but must not erase a deliberately controlled
 *     door-open interval (CG_DOOR_DEBOUNCE_MS is orders of magnitude
 *     shorter than a controlled disturbance window);
 *   - transition time and resulting state must survive into the record,
 *     which is why every raw edge is timestamped in microseconds and
 *     every committed transition carries the debounced counters.
 *
 * The module keeps one counter pair on committed transitions only, so the
 * cycle count is a property of debounced door motion, not of contact
 * bounce. Raw edge counts and discarded edges are exposed separately as
 * reliability evidence.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    CG_DOOR_UNVERIFIED = 0, /* polarity not commissioned */
    CG_DOOR_OPEN,
    CG_DOOR_CLOSED,
} cg_door_state_t;

typedef struct {
    int raw_committed;        /* debounced raw level */
    int raw_last;             /* last sampled raw level */
    uint64_t stable_since_us; /* when raw_last started being stable */
    uint32_t transitions;     /* committed transitions */
    uint32_t cycles;          /* floor(transitions / 2) */
    uint32_t raw_edges;       /* every raw change, bounce included */
    uint32_t discarded_edges; /* raw edges not explained by a commit:
                                 raw_edges - transitions (never negative) */
    bool initialised;
    /* D25: raw level -> OPEN/CLOSED is only a valid measurement once the
     * polarity has been attested for THIS boot. cg_door_init()'s memset
     * clears it, so a reset returns the door to unattested regardless of the
     * build-time CG_DOOR_POLARITY_CONFIRMED constant. */
    bool polarity_attested;
} cg_door_t;

/* Configures CG_PIN_MC38 (GPIO35 as-built) as a pulled input and
 * initialises the debouncer with the first observed level. */
void cg_door_init(cg_door_t *door);

/* Samples the pin. `now_us` is a monotonic microsecond timestamp.
 *
 * Reports:
 *   - edge_out   : the raw level changed (bounce included) -> the caller
 *                  logs a DOOR_EDGE line with this timestamp;
 *   - commit_out : the debounced level changed -> the caller logs
 *                  DOOR_STATE with transitions/cycles/discarded counts.
 */
void cg_door_poll(cg_door_t *door, uint64_t now_us, bool *edge_out,
                  int *raw_edge_level_out, bool *commit_out);

/* Semantic state. While polarity is not commissioned the answer is
 * CG_DOOR_UNVERIFIED - never a guess (docs/01 section 8.2). */
cg_door_state_t cg_door_state(const cg_door_t *door);

/* True only when the polarity is BOTH a commissioned capability
 * (CG_DOOR_POLARITY_CONFIRMED) and attested for this boot. Drives the
 * snapshot door-known flag and the DOOR_POLARITY line so a reader can tell
 * "confirmed this boot" apart from "unattested after a reset" (D25). */
bool cg_door_polarity_attested(const cg_door_t *door);

/* Records a per-boot polarity attestation made by a physical open/close
 * observation. Nothing in the shipped build calls it - the MC-38 polarity is
 * not commissioned (docs/01 8.2) - so the door stays UNVERIFIED. It exists so
 * the compile-time constant alone can never authorize a confirmed reading. */
void cg_door_attest_polarity(cg_door_t *door);

const char *cg_door_state_name(cg_door_state_t state);
