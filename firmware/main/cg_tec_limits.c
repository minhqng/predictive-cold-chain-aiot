/*
 * ColdGuard firmware - TEC operating limits and their provenance (W04).
 *
 * Every shipped entry is UNRESOLVED. Do not replace a provenance token with
 * a number unless the measurement and its evidence file exist; the control
 * module treats UNRESOLVED as "no output", which is the intended behaviour
 * until the hardware is characterized.
 */
#include "cg_tec_limits.h"

#include <stddef.h>

const cg_tec_limit_table_t cg_tec_limits_shipped = {
    .entry = {
        [CG_LIMIT_CURRENT_MAX_A] = {
            .id = CG_LIMIT_CURRENT_MAX_A,
            .name = "current_max_a",
            .unit = "A",
            .state = CG_LIMIT_UNRESOLVED,
            .value = 0.0f,
            .source = "TEC_CONTINUOUS_RATING_NOT_ESTABLISHED",
        },
        [CG_LIMIT_VOLTAGE_MAX_V] = {
            .id = CG_LIMIT_VOLTAGE_MAX_V,
            .name = "voltage_max_v",
            .unit = "V",
            .state = CG_LIMIT_UNRESOLVED,
            .value = 0.0f,
            .source = "TEC_VMAX_NOT_ESTABLISHED",
        },
        [CG_LIMIT_VOLTAGE_MIN_V] = {
            .id = CG_LIMIT_VOLTAGE_MIN_V,
            .name = "voltage_min_v",
            .unit = "V",
            .state = CG_LIMIT_UNRESOLVED,
            .value = 0.0f,
            .source = "PSU_LOAD_REGULATION_NOT_MEASURED",
        },
        [CG_LIMIT_HOT_SIDE_MAX_C] = {
            .id = CG_LIMIT_HOT_SIDE_MAX_C,
            .name = "hot_side_max_c",
            .unit = "C",
            .state = CG_LIMIT_UNRESOLVED,
            .value = 0.0f,
            .source = "HOT_SIDE_LIMIT_NOT_ESTABLISHED",
        },
        [CG_LIMIT_DUTY_MAX_PERMILLE] = {
            .id = CG_LIMIT_DUTY_MAX_PERMILLE,
            .name = "duty_max_permille",
            .unit = "permille",
            .state = CG_LIMIT_UNRESOLVED,
            .value = 0.0f,
            .source = "DUTY_NOT_CHARACTERISED",
        },
        [CG_LIMIT_ON_TIME_MAX_MS] = {
            .id = CG_LIMIT_ON_TIME_MAX_MS,
            .name = "on_time_max_ms",
            .unit = "ms",
            .state = CG_LIMIT_UNRESOLVED,
            .value = 0.0f,
            .source = "ON_TIME_NOT_CHARACTERISED",
        },
    },
};

const cg_limit_t *cg_tec_limit(const cg_tec_limit_table_t *table, cg_limit_id_t id)
{
    if (table == NULL || (unsigned)id >= (unsigned)CG_LIMIT_COUNT) {
        return NULL;
    }
    return &table->entry[id];
}

bool cg_tec_limits_all_resolved(const cg_tec_limit_table_t *table)
{
    if (table == NULL) {
        return false;
    }
    for (int i = 0; i < CG_LIMIT_COUNT; i++) {
        const cg_limit_t *limit = &table->entry[i];
        if (limit->state != CG_LIMIT_RESOLVED || limit->source == NULL ||
            limit->source[0] == '\0') {
            return false;
        }
    }
    return true;
}

int cg_tec_limits_unresolved(const cg_tec_limit_table_t *table)
{
    int unresolved = 0;

    if (table == NULL) {
        return CG_LIMIT_COUNT;
    }
    for (int i = 0; i < CG_LIMIT_COUNT; i++) {
        if (table->entry[i].state != CG_LIMIT_RESOLVED) {
            unresolved++;
        }
    }
    return unresolved;
}

const char *cg_tec_limit_state_name(cg_limit_state_t state)
{
    return state == CG_LIMIT_RESOLVED ? "RESOLVED" : "UNRESOLVED";
}
