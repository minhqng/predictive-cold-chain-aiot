/*
 * ColdGuard firmware - last-observation snapshot (W04 foundation, W05 identity).
 * See cg_snapshot.h for what each group of fields is evidence of.
 */
#include "cg_snapshot.h"

#include <string.h>

#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#endif

/* The lock is real on the device and a no-op in the host harness, where the
 * same functions must be callable single-threaded. Compiling the publication
 * path on the host is what lets a test drive the frame through the copy that
 * firmware actually performs, instead of hand-writing snapshot fields - the gap
 * that let the probe counts go unpublished for a whole review cycle. */
#ifdef ESP_PLATFORM
static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;
#define CG_SNAP_LOCK() taskENTER_CRITICAL(&s_mux)
#define CG_SNAP_UNLOCK() taskEXIT_CRITICAL(&s_mux)
#else
#define CG_SNAP_LOCK() ((void)0)
#define CG_SNAP_UNLOCK() ((void)0)
#endif

static cg_snapshot_t s_snap;

void cg_snapshot_init(void)
{
    CG_SNAP_LOCK();
    memset(&s_snap, 0, sizeof(s_snap));
    /* Before the first thermal publication nothing has been observed, so the
     * quality is UNKNOWN. W04 initialised this to INVALID, which stated a
     * determined failure the firmware had no evidence for (docs/01 2302-2306). */
    s_snap.thermal_quality = CG_QUALITY_UNKNOWN;
    CG_SNAP_UNLOCK();
}

void cg_snapshot_publish_thermal(const cg_thermal_snapshot_t *snap, uint32_t seq,
                                 uint64_t obs_ms)
{
    CG_SNAP_LOCK();
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        s_snap.t_valid[role] = snap->probe[role].valid;
        s_snap.t_c[role] = snap->probe[role].celsius;
        s_snap.t_status[role] = snap->probe[role].status;
    }
    s_snap.thermal_quality = (uint8_t)snap->quality;
    /* Control stays strict: only an all-roles-valid thermal snapshot is
     * "valid" for the fail-closed gate. The degraded detail is carried
     * separately by the probe counts below, so the quality layer can name
     * DEGRADED without loosening what the controller is willing to act on. */
    s_snap.thermal_valid = snap->quality == CG_QUALITY_VALID;
    s_snap.thermal_observed = true;
    s_snap.thermal_seq = seq;
    s_snap.thermal_obs_ms = obs_ms;
    /* Counted by the driver from the frozen map's is_measurement_role flag.
     * Without this copy the snapshot would report 0/0 probes and every frame
     * would collapse to UNKNOWN even with three healthy probes. */
    s_snap.probes_ok = snap->measurement_ok;
    s_snap.probes_expected = snap->measurement_expected;
    CG_SNAP_UNLOCK();
}

void cg_snapshot_publish_power(bool valid, float voltage_v, float current_a, float power_w,
                               float energy_wh, uint32_t seq, uint64_t obs_ms)
{
    CG_SNAP_LOCK();
    /* A failed poll publishes valid=false with its own timestamp and sequence.
     * The previous reading is deliberately not carried forward, so the reader
     * sees a new attempt that failed rather than an old success that looks
     * current (docs/01 2288-2298). */
    s_snap.power_valid = valid;
    s_snap.voltage_v = voltage_v;
    s_snap.current_a = current_a;
    s_snap.power_w = power_w;
    s_snap.energy_wh = energy_wh;
    s_snap.power_observed = true;
    s_snap.power_seq = seq;
    s_snap.power_obs_ms = obs_ms;
    CG_SNAP_UNLOCK();
}

void cg_snapshot_publish_door(bool known, bool open, int raw, uint64_t obs_ms,
                              uint32_t transitions, uint32_t cycles)
{
    CG_SNAP_LOCK();
    s_snap.door_observed = true;
    s_snap.door_known = known;
    s_snap.door_open = open;
    s_snap.door_raw = raw;
    s_snap.door_obs_ms = obs_ms;
    s_snap.door_transitions = transitions;
    s_snap.door_cycles = cycles;
    CG_SNAP_UNLOCK();
}

void cg_snapshot_read(cg_snapshot_t *out)
{
    CG_SNAP_LOCK();
    *out = s_snap;
    CG_SNAP_UNLOCK();
}
