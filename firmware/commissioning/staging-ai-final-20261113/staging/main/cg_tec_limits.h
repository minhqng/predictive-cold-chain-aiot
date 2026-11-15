/*
 * ColdGuard firmware - TEC operating limits and their provenance (W04).
 *
 * The TEC1-12715 SR marking is a part number, not a rating. No continuous
 * current, voltage, hot-side temperature, duty or on-time figure has been
 * established for the as-built assembly, and the final branch fuse has not
 * been selected (docs/01 sections 13 and 16). This table therefore ships
 * every operating limit as UNRESOLVED with an explicit provenance token.
 *
 * The control module refuses to start while any limit is unresolved, so the
 * shipped build cannot energize the branch even if the output stage were
 * compiled in. A limit becomes RESOLVED only by replacing the entry with a
 * measured/datasheet-backed value and recording the source and the evidence
 * file; that change is a commissioning decision, not a code cleanup.
 *
 * Limits are data, not policy: the shipped table is a constant, and the
 * offline harness injects a resolved table to exercise the mechanism.
 */
#pragma once

#include <stdbool.h>

typedef enum {
    CG_LIMIT_CURRENT_MAX_A = 0,   /* branch current, amps */
    CG_LIMIT_VOLTAGE_MAX_V,       /* branch voltage, volts */
    CG_LIMIT_VOLTAGE_MIN_V,       /* branch voltage under load, volts */
    CG_LIMIT_HOT_SIDE_MAX_C,      /* hot-side temperature, Celsius */
    CG_LIMIT_DUTY_MAX_PERMILLE,   /* commanded duty, 0..1000 */
    CG_LIMIT_ON_TIME_MAX_MS,      /* bounded command duration, ms */
    CG_LIMIT_COUNT,
} cg_limit_id_t;

typedef enum {
    CG_LIMIT_UNRESOLVED = 0, /* no measured/datasheet-backed value exists */
    CG_LIMIT_RESOLVED = 1,   /* value and source are recorded evidence */
} cg_limit_state_t;

typedef struct {
    cg_limit_id_t id;
    const char *name;   /* stable token used in the TEC_LIMIT log line */
    const char *unit;   /* "A", "V", "C", "permille", "ms" */
    cg_limit_state_t state;
    float value;        /* meaningless while state is UNRESOLVED */
    const char *source; /* why the state is what it is */
} cg_limit_t;

typedef struct {
    cg_limit_t entry[CG_LIMIT_COUNT];
} cg_tec_limit_table_t;

/* The table the firmware ships with: every operating limit unresolved. */
extern const cg_tec_limit_table_t cg_tec_limits_shipped;

const cg_limit_t *cg_tec_limit(const cg_tec_limit_table_t *table, cg_limit_id_t id);

/* True only when every entry is RESOLVED with a non-empty source. */
bool cg_tec_limits_all_resolved(const cg_tec_limit_table_t *table);

/* Number of unresolved entries; logged at boot so the operator sees why the
 * branch cannot start. */
int cg_tec_limits_unresolved(const cg_tec_limit_table_t *table);

const char *cg_tec_limit_state_name(cg_limit_state_t state);
