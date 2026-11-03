/*
 * ColdGuard firmware - last-observation snapshot (W04).
 */
#include "cg_snapshot.h"

#include <string.h>

#include "freertos/FreeRTOS.h"

static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;
static cg_snapshot_t s_snap;

void cg_snapshot_init(void)
{
    taskENTER_CRITICAL(&s_mux);
    memset(&s_snap, 0, sizeof(s_snap));
    s_snap.thermal_quality = CG_QUALITY_INVALID;
    taskEXIT_CRITICAL(&s_mux);
}

void cg_snapshot_publish_thermal(const cg_thermal_snapshot_t *snap, uint64_t obs_ms)
{
    taskENTER_CRITICAL(&s_mux);
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        s_snap.t_valid[role] = snap->probe[role].valid;
        s_snap.t_c[role] = snap->probe[role].celsius;
        s_snap.t_status[role] = snap->probe[role].status;
    }
    s_snap.thermal_quality = (uint8_t)snap->quality;
    s_snap.thermal_valid = snap->quality == CG_QUALITY_VALID;
    s_snap.thermal_observed = true;
    s_snap.thermal_obs_ms = obs_ms;
    taskEXIT_CRITICAL(&s_mux);
}

void cg_snapshot_publish_power(bool valid, float voltage_v, float current_a, float power_w,
                               uint64_t obs_ms)
{
    taskENTER_CRITICAL(&s_mux);
    s_snap.power_valid = valid;
    s_snap.voltage_v = voltage_v;
    s_snap.current_a = current_a;
    s_snap.power_w = power_w;
    s_snap.power_observed = true;
    s_snap.power_obs_ms = obs_ms;
    taskEXIT_CRITICAL(&s_mux);
}

void cg_snapshot_publish_door(bool known, bool open, int raw)
{
    taskENTER_CRITICAL(&s_mux);
    s_snap.door_known = known;
    s_snap.door_open = open;
    s_snap.door_raw = raw;
    taskEXIT_CRITICAL(&s_mux);
}

void cg_snapshot_read(cg_snapshot_t *out)
{
    taskENTER_CRITICAL(&s_mux);
    *out = s_snap;
    taskEXIT_CRITICAL(&s_mux);
}
