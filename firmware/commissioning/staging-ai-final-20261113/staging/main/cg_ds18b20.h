/*
 * ColdGuard firmware - DS18B20 acquisition (Member A, W02).
 *
 * Contract highlights (docs/01):
 *   - section 6.6 PHY-DS-006: one shared broadcast conversion for all
 *     probes, then scratchpad reads. Sequential per-probe conversions
 *     would pretend that three different physical times are one snapshot.
 *   - section 6.6 PHY-DS-004: a failed read is reported as invalid, never
 *     as 0.0 C and never as a stale previous value.
 *   - section 6.5: probes are addressed by their frozen ROM code.
 *   - section 6.8: one invalid probe = DEGRADED, two or more = INVALID.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "cg_rom_map.h"

typedef enum {
    CG_READ_OK = 0,
    CG_READ_NO_PRESENCE,    /* no device answered the reset pulse */
    CG_READ_CRC_FAIL,       /* scratchpad CRC8 mismatch */
    CG_READ_POWER_ON_RESET, /* classic 85.0 C power-on value */
    CG_READ_OUT_OF_RANGE,   /* outside the datasheet envelope */
} cg_read_status_t;

typedef struct {
    bool present;              /* a MATCH_ROM read answered this boot */
    bool valid;                /* celsius is a fresh, plausible reading */
    uint8_t status;            /* cg_read_status_t of the latest read */
    float celsius;
    uint32_t fail_count;       /* consecutive failures, reset on success */
} cg_probe_t;

typedef enum {
    CG_QUALITY_VALID = 0,  /* all three measurement roles valid */
    CG_QUALITY_DEGRADED,   /* exactly one measurement role invalid */
    CG_QUALITY_INVALID,    /* two or more measurement roles invalid */
    /* W05 adds the fourth canonical state (docs/01 2263-2308). The driver never
     * derives it - read_all() always resolves to one of the three above - so it
     * exists for the snapshot's pre-first-publication state, where nothing has
     * been observed yet and "invalid" would claim more than the evidence. */
    CG_QUALITY_UNKNOWN,
} cg_thermal_quality_t;

typedef struct {
    cg_probe_t probe[CG_ROLE_COUNT]; /* index == cg_role_t */
    cg_thermal_quality_t quality;
    uint8_t required_present;        /* T1..T3 present at last enumeration */
    uint8_t known_present;           /* all four frozen ROMs present */
    /* W05: how many of the measurement roles (T1..T3, per the frozen map)
     * returned a valid reading on the last shared conversion. Counted from the
     * map's is_measurement_role flag, never from an index, so SPARE can never
     * be counted into a chamber-air figure by accident. */
    uint8_t measurement_ok;
    uint8_t measurement_expected;
} cg_thermal_snapshot_t;

/* Configures the bus and writes the 12-bit resolution configuration to
 * every frozen ROM. Returns false if the bus self-check fails. */
bool cg_ds18b20_init(void);

/* Presence sweep of the frozen ROMs (T1,T2,T3,SPARE). Emits the
 * "#CG ROM ..." lines so a reboot-identity capture carries the mapping. */
void cg_ds18b20_enumerate(cg_thermal_snapshot_t *out);

/* Broadcast Convert T (SKIP_ROM + 0x44). false when the bus is silent. */
bool cg_ds18b20_convert_all(void);

/* Reads one frozen ROM: MATCH_ROM + READ_SCRATCHPAD with CRC and
 * plausibility checks. `out` keeps valid=false on any failure. */
void cg_ds18b20_read_probe(cg_role_t role, cg_probe_t *out);

/* Reads T1,T2,T3 and SPARE from one shared conversion and derives the
 * thermal quality. Registration order is the role order, never the bus
 * order. */
void cg_ds18b20_read_all(cg_thermal_snapshot_t *snap);

/* Quality label used verbatim in the serial log. */
const char *cg_quality_name(cg_thermal_quality_t quality);
