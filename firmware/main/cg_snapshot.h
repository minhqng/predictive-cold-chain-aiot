/*
 * ColdGuard firmware - last-observation snapshot (W04 foundation, W05 identity).
 *
 * The sensor, PZEM and door tasks publish their latest *timestamped*
 * observation here; the commissioning task reads one consistent copy. The
 * timestamps are what let the controller reject stale data: the snapshot
 * never carries a value forward on its own, and the control module treats an
 * old observation as missing, not as current.
 *
 * W05 adds the fields the coherence claim in A-W05-04 needs. Each producer
 * carries its own sequence number and observation time into the snapshot, so a
 * telemetry line can state - not merely imply - whether a value is new:
 *
 *   thermal_seq / power_seq  advance when that producer actually polled again.
 *                            A telemetry line whose power_seq repeats has
 *                            carried no new electrical observation, whatever
 *                            the voltage field looks like.
 *   *_obs_ms                 the producer's own esp_timer sample time, so the
 *                            reader can compute a real age instead of trusting
 *                            the emitter's cadence.
 *   door_obs_ms              was missing in W04: the door publication had no
 *                            time at all, so door age could not be evaluated.
 *   energy_wh                the PZEM register was decoded and logged in W03 but
 *                            never reached the snapshot, so the telemetry could
 *                            not carry accumulated energy.
 *
 * The struct is copied under a critical section, which is what makes one read
 * one coherent view: fields may still differ in age from each other - they are
 * reported with their ages rather than being presented as one simultaneous
 * physical instant.
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
    uint32_t thermal_seq;
    uint8_t probes_ok;       /* measurement roles that returned a valid reading */
    uint8_t probes_expected; /* measurement roles in the frozen map (T1..T3) */
    bool t_valid[CG_ROLE_COUNT];
    float t_c[CG_ROLE_COUNT];
    uint8_t t_status[CG_ROLE_COUNT];

    bool power_observed;
    bool power_valid;
    uint64_t power_obs_ms;
    uint32_t power_seq;
    float voltage_v;
    float current_a;
    float power_w;
    float energy_wh;

    bool door_observed;
    bool door_known;
    bool door_open;
    int door_raw;
    uint64_t door_obs_ms;
    uint32_t door_transitions;
    uint32_t door_cycles;

    /* Ambient environment (A-W02-06). `env_observed` becomes true once the
     * producer has completed a cycle with the bus up - including a cycle whose
     * answer was "no device acknowledged". Absence is therefore an observation
     * with a time, not the absence of one, which is what lets the reader tell a
     * quiet module from a dead producer. */
    bool env_observed;
    bool env_present;
    bool env_valid;
    uint64_t env_obs_ms;
    uint32_t env_seq;
    float env_temperature_c;
    float env_humidity_pct;
    uint8_t env_state;  /* cg_bme280_state_t  */
    uint8_t env_reason; /* cg_bme_read_result_t */
    uint8_t env_i2c_addr;
} cg_snapshot_t;

void cg_snapshot_init(void);

void cg_snapshot_publish_thermal(const cg_thermal_snapshot_t *snap, uint32_t seq,
                                 uint64_t obs_ms);
void cg_snapshot_publish_power(bool valid, float voltage_v, float current_a, float power_w,
                               float energy_wh, uint32_t seq, uint64_t obs_ms);
void cg_snapshot_publish_door(bool known, bool open, int raw, uint64_t obs_ms,
                              uint32_t transitions, uint32_t cycles);

/* Publishes one ambient cycle. `present` is the producer's belief that a module
 * is on the bus; `valid` is false for every refusal path, so the last good value
 * is never carried forward as if it were current - the same rule
 * cg_snapshot_publish_power() applies to a failed electrical poll. */
void cg_snapshot_publish_env(bool present, bool valid, float temperature_c,
                             float humidity_pct, uint8_t state, uint8_t reason,
                             uint8_t i2c_addr, uint32_t seq, uint64_t obs_ms);

/* Copies the latest snapshot. Every field keeps its own observation time. */
void cg_snapshot_read(cg_snapshot_t *out);
