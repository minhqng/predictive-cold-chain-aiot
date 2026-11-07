/*
 * ColdGuard firmware - physical source quality derivation (W05).
 *
 * docs/01 section 19 freezes the vocabulary: VALID, DEGRADED, INVALID,
 * UNKNOWN. The rule set implemented here is the canonical one and nothing
 * else:
 *
 *   VALID     every mandatory source for the intended computation satisfies
 *             its quality and freshness condition.
 *   DEGRADED  a non-critical or redundant source is unavailable, but a
 *             defined degraded path still exists. One of three chamber probes
 *             bad is the canonical example (docs/01 924-942).
 *   INVALID   the source must not drive the intended predictive or control
 *             action.
 *   UNKNOWN   the state cannot be determined confidently. docs/01 2302-2306:
 *             UNKNOWN must never be silently treated as normal, and it is
 *             preferred to invented certainty.
 *
 * This module is deliberately free of FreeRTOS and driver dependencies so the
 * host harness can drive it directly: it takes observation timestamps and
 * per-source states and returns names. It never repairs, repeats or interpolates
 * a value - a stale or missing observation degrades the quality and the value
 * itself stays `nan` in the telemetry layer (A-W05-05 prohibition: a missing
 * current must not be replaced by the previous fresh value).
 */
#pragma once

#include <stdint.h>

#define CG_SRC_NAME_LEN 12

typedef enum {
    CG_SRC_EMPTY = 0,   /* nothing published yet: UNKNOWN, never INVALID-by-default */
    CG_SRC_FRESH_OK,    /* published, valid, inside the freshness window */
    CG_SRC_FRESH_BAD,   /* published, inside the window, but the read itself failed */
    CG_SRC_STALE,       /* last publication older than the freshness bound */
} cg_source_state_t;

/* Per-source quality for the four physical families the snapshot carries. */
typedef struct {
    char thermal[CG_SRC_NAME_LEN];
    char environment[CG_SRC_NAME_LEN];
    char door[CG_SRC_NAME_LEN];
    char electrical[CG_SRC_NAME_LEN];
    char overall[CG_SRC_NAME_LEN];
} cg_quality_set_t;

/* Number of chamber-air probes (T1..T3) that are currently fresh and valid. */
typedef struct {
    int probes_ok;
    int probes_expected;
    uint64_t thermal_age_ms;
    uint64_t thermal_age_limit_ms;
    uint64_t power_age_ms;
    uint64_t power_age_limit_ms;
    uint64_t door_age_ms;
    uint64_t door_age_limit_ms;
    uint64_t bme_age_ms;
    uint64_t bme_age_limit_ms;
    /* The door and environment groups get the same independent age
     * cross-check as thermal and power: a caller must not be able to hide a
     * stale observation by labelling it fresh. */
    int door_age_over_limit;
    int bme_present;
    /* A module answered, but board policy refused the value (the fitted trim
     * layout has never been confirmed against a reference instrument). That is
     * a known configuration limitation, not a failed reading, so the group is
     * DEGRADED rather than INVALID - the same treatment as a declared absence. */
    int bme_refused_by_policy;
    cg_source_state_t thermal_state;
    cg_source_state_t power_state;
    cg_source_state_t door_state;
    cg_source_state_t bme_state;
} cg_quality_input_t;

/* Fills `out` with the canonical names. `overall` collapses per docs/01:
 * INVALID wins over UNKNOWN, UNKNOWN wins over DEGRADED, DEGRADED over VALID. */
void cg_quality_eval(const cg_quality_input_t *in, cg_quality_set_t *out);

/* Names, exposed for tests and for the telemetry layer. */
const char *cg_source_quality_name(cg_source_state_t state, int age_over_limit);
const char *cg_quality_collapse(const cg_quality_set_t *set);
