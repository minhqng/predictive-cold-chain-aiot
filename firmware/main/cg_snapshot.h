/*
 * ColdGuard firmware - last-observation snapshot (W04).
 *
 * The sensor, PZEM and door tasks publish their latest *timestamped*
 * observation here; the commissioning task reads one consistent copy. The
 * timestamps are what let the controller reject stale data: the snapshot
 * never carries a value forward on its own, and the control module treats an
 * old observation as missing, not as current.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "cg_ds18b20.h"

typedef struct {
    bool thermal_observed;
    bool thermal_valid;
    uint8_t thermal_quality; /* cg_thermal_quality_t */
    uint64_t thermal_obs_ms;
    bool t_valid[CG_ROLE_COUNT];
    float t_c[CG_ROLE_COUNT];
    uint8_t t_status[CG_ROLE_COUNT];

    bool power_observed;
    bool power_valid;
    uint64_t power_obs_ms;
    float voltage_v;
    float current_a;
    float power_w;

    bool door_known;
    bool door_open;
    int door_raw;
} cg_snapshot_t;

void cg_snapshot_init(void);

void cg_snapshot_publish_thermal(const cg_thermal_snapshot_t *snap, uint64_t obs_ms);
void cg_snapshot_publish_power(bool valid, float voltage_v, float current_a, float power_w,
                               uint64_t obs_ms);
void cg_snapshot_publish_door(bool known, bool open, int raw);

/* Copies the latest snapshot. Every field keeps its own observation time. */
void cg_snapshot_read(cg_snapshot_t *out);
