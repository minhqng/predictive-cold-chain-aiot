/*
 * ColdGuard firmware - physical source quality derivation (W05).
 * See cg_quality.h for the canonical rule set this implements.
 */
#include "cg_quality.h"

#include <stdio.h>
#include <string.h>

static void copy_name(char *dst, const char *src)
{
    (void)snprintf(dst, CG_SRC_NAME_LEN, "%s", src);
}

#define CG_Q_VALID "VALID"
#define CG_Q_DEGRADED "DEGRADED"
#define CG_Q_INVALID "INVALID"
#define CG_Q_UNKNOWN "UNKNOWN"

/*
 * One source, one name. `age_over_limit` is passed separately from the state for
 * thermal and power, where the snapshot does carry an observation time: a caller
 * cannot hide a stale observation by labelling it fresh. A fresh-but-failed read
 * and a stale read are both unusable (docs/01 2288-2298), while an observation
 * that was never published is not "invalid", it is unknown.
 */
const char *cg_source_quality_name(cg_source_state_t state, int age_over_limit)
{
    switch (state) {
        case CG_SRC_FRESH_OK:
            return age_over_limit ? CG_Q_INVALID : CG_Q_VALID;
        case CG_SRC_FRESH_BAD:
            /* A read that came back failed or corrupt must not drive the
             * intended action (docs/01 2288-2298). */
            return CG_Q_INVALID;
        case CG_SRC_STALE:
            /* The value is known to be old, so it is a determined failure of the
             * freshness condition, not an unknown. */
            return CG_Q_INVALID;
        case CG_SRC_EMPTY:
        default:
            /* Never published: report UNKNOWN rather than inventing certainty. */
            return CG_Q_UNKNOWN;
    }
}

/*
 * Chamber air is a three-probe measurement. docs/01 924-942 counts the rule by
 * *failed* probes: exactly one temporarily invalid keeps a defined degraded
 * path, two or more do not. Counting the good probes instead gets it wrong in
 * the middle - one valid probe out of three is two failures, which is INVALID,
 * not DEGRADED.
 */
static const char *thermal_quality(const cg_quality_input_t *in)
{
    const char *base = cg_source_quality_name(in->thermal_state,
                                              in->thermal_age_ms > in->thermal_age_limit_ms);

    if (strcmp(base, CG_Q_VALID) != 0) {
        return base;
    }
    if (in->probes_expected <= 0) {
        /* No measurement roles were configured, so there is nothing to certify
         * chamber air from. */
        return CG_Q_UNKNOWN;
    }
    const int failed = in->probes_expected - in->probes_ok;
    if (failed <= 0) {
        return CG_Q_VALID;
    }
    if (failed == 1) {
        return CG_Q_DEGRADED;
    }
    return CG_Q_INVALID;
}

static const char *environment_quality(const cg_quality_input_t *in)
{
    if (!in->bme_present) {
        /* Humidity is not a mandatory chamber-air source and its absence here
         * is a *known* configuration fact, not an undetermined one: docs/01
         * §19.2 DEGRADED ("a defined degraded path remains legal") is the right
         * name, and §19.4 UNKNOWN would wrongly imply the firmware cannot tell
         * whether the sensor is there. It still keeps the collapsed `quality`
         * from reading VALID while the module is absent. */
        return CG_Q_DEGRADED;
    }
    if (in->bme_refused_by_policy) {
        return CG_Q_DEGRADED;
    }
    return cg_source_quality_name(in->bme_state,
                                  in->bme_age_ms > in->bme_age_limit_ms);
}

static const char *door_quality(const cg_quality_input_t *in)
{
    /* The MC-38 raw level is readable while its polarity is uncommissioned
     * (docs/01 1047-1060), so the semantic state cannot be determined:
     * UNKNOWN, not INVALID, and never a guessed OPEN/CLOSED. */
    if (in->door_state == CG_SRC_FRESH_BAD) {
        return CG_Q_UNKNOWN;
    }
    return cg_source_quality_name(in->door_state, in->door_age_over_limit);
}

void cg_quality_eval(const cg_quality_input_t *in, cg_quality_set_t *out)
{
    if (in == NULL || out == NULL) {
        return;
    }
    copy_name(out->thermal, thermal_quality(in));
    copy_name(out->environment, environment_quality(in));
    copy_name(out->door, door_quality(in));
    copy_name(out->electrical, cg_source_quality_name(in->power_state,
                                                      in->power_age_ms > in->power_age_limit_ms));
    copy_name(out->overall, cg_quality_collapse(out));
}

const char *cg_quality_collapse(const cg_quality_set_t *set)
{
    if (set == NULL) {
        return CG_Q_UNKNOWN;
    }
    const char *names[4] = {set->thermal, set->environment, set->door, set->electrical};

    int saw_invalid = 0;
    int saw_unknown = 0;
    int saw_degraded = 0;
    for (int i = 0; i < 4; i++) {
        if (strcmp(names[i], CG_Q_INVALID) == 0) {
            saw_invalid = 1;
        } else if (strcmp(names[i], CG_Q_UNKNOWN) == 0) {
            saw_unknown = 1;
        } else if (strcmp(names[i], CG_Q_DEGRADED) == 0) {
            saw_degraded = 1;
        }
    }
    if (saw_invalid) {
        return CG_Q_INVALID;
    }
    if (saw_unknown) {
        return CG_Q_UNKNOWN;
    }
    if (saw_degraded) {
        return CG_Q_DEGRADED;
    }
    return CG_Q_VALID;
}
