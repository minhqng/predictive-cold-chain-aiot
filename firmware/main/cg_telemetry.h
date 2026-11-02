/*
 * ColdGuard firmware - raw telemetry line (W04 foundation, W05 identity/quality).
 *
 * One `#CG TELEM` line per second carries the measurements the experiment
 * needs. The line is an *observation*: a missing value is printed as `nan`
 * together with an explicit status token, never as 0.0 and never as the
 * previous value. That is what lets the host build a dataset without
 * inventing samples.
 *
 * Field contract (schema 2; see docs/06 and firmware/tools/
 * cg_telemetry_schema.py):
 *   timestamp_utc is UNAVAILABLE: the ESP32 has no wall clock and no network
 *   time. The host adds a capture timestamp when it converts the capture;
 *   the device time axis is elapsed_ms/run_elapsed_ms.
 *
 * Channel assignment is explicit and does not exceed the evidence:
 *   T1/T2/T3 are chamber probes; T2 is reported as t_inside_c (src=T2).
 *   No probe is assigned to the cold side, the hot side or the ambient, so
 *   those fields are nan with status NOT_ASSIGNED.
 *   The BME280 is not implemented (A-W02-06 pending), so relative humidity
 *   is nan with status SENSOR_NOT_PRESENT.
 *
 * What W05 adds, and why each group is here:
 *   A-W05-02 identity  device_id + boot_id + seq is the dedup key the backend
 *                      enforces (docs/02 633-646, 845); calibration_id is
 *                      emitted as UNRECORDED because no calibration bundle has
 *                      been measured (docs/01 2855-2876). Each probe's frozen
 *                      ROM travels in the line because docs/01 6.5 makes the
 *                      ROM - not an enumeration index - the sensor identity.
 *   A-W05-04 coherence *_age_ms and *_seq per producer state, in the frame,
 *                      whether this line carried a new observation or a repeat.
 *                      Without them "coherent snapshot" is an assertion.
 *   A-W05-05 quality   the four canonical per-source names plus the collapsed
 *                      overall name, derived by cg_quality.c from the same
 *                      snapshot the values come from.
 *   A-W05-01 liveness  producer health names, beat counts and worst observed
 *                      gap, so a stopped task shows up as a named producer
 *                      rather than as a sensor that keeps reporting.
 *   applied state      cooling_applied reports what the output layer was left
 *                      driving, and cooling_evidence reports whether the PZEM
 *                      corroboration agrees, was zero, or could not be observed
 *                      at all. A command is never presented as a physical fact.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "cg_health.h"
#include "cg_snapshot.h"
#include "cg_tec_control.h"

#define CG_TELEM_ROM_HEX_LEN 17 /* 16 hex characters + NUL */

typedef struct {
    /* A-W05-02: monotonic per-boot frame counter. The backend dedup key is
     * (device_id, boot_id, seq), so seq must never repeat inside a boot and
     * must never be reset by a command. */
    uint32_t seq;
    const char *boot_id;
    uint32_t boot_count;
    uint64_t uptime_ms;
    const char *run_id;
    const char *test_phase;
    const cg_snapshot_t *snap;
    const cg_tec_control_t *ctl;
    /* A-W05-01. NULL means liveness was not evaluated for this frame, which is
     * reported as health=UNKNOWN rather than as a healthy device. */
    const cg_health_report_t *health;
    /* Pre-rendered identity so this module keeps no driver dependency and stays
     * host-testable. NULL element prints as UNREAD. */
    const char *probe_rom[CG_ROLE_COUNT];
    const char *role_status;
    bool output_stage_enabled;
    bool fan_available;
} cg_telemetry_frame_t;

/* Formats one complete line (no trailing newline). Returns the line length;
 * the result is always NUL-terminated when cap > 0. Returns 0 (and writes an
 * empty buffer) when the frame does not fit cap, so a partial observation is
 * never handed to the raw writer. */
size_t cg_telemetry_format(char *buf, size_t cap, const cg_telemetry_frame_t *frame);

/* Stable status tokens used in the line. */
#define CG_TELEM_STATUS_OK "OK"
#define CG_TELEM_STATUS_INVALID "INVALID"
#define CG_TELEM_STATUS_STALE "STALE"
#define CG_TELEM_STATUS_NO_DATA "NO_DATA"
#define CG_TELEM_STATUS_NOT_ASSIGNED "NOT_ASSIGNED"
#define CG_TELEM_STATUS_NOT_PRESENT "SENSOR_NOT_PRESENT"
#define CG_TELEM_STATUS_UNVERIFIED "UNVERIFIED"

/* W05 tokens. `cooling_evidence` is deliberately five-valued: the PZEM can
 * corroborate an applied output, corroborate an idle branch, contradict either
 * one, be too old to say anything, or have never answered at all. Only the
 * first two are evidence about the branch, and a contradiction is never
 * smoothed into "OFF looks fine". */
#define CG_TELEM_APPLIED_ON "ON"
#define CG_TELEM_APPLIED_OFF "OFF"
#define CG_TELEM_EVIDENCE_APPLIED "MEASURED_APPLIED_AND_DRAWING"
#define CG_TELEM_EVIDENCE_IDLE "MEASURED_IDLE_AND_ZERO"
#define CG_TELEM_EVIDENCE_CONTRADICTS "MEASURED_CONTRADICTS_APPLIED"
#define CG_TELEM_EVIDENCE_STALE "UNOBSERVED_STALE"
#define CG_TELEM_EVIDENCE_NONE "UNOBSERVED_NO_DATA"
#define CG_TELEM_APPLIED_SOURCE "FIRMWARE_OUTPUT_STATE"
/* The ROM values on the line come from the frozen configuration table
 * (cg_rom_map.c), not from a per-frame 1-Wire match. Per-boot detection
 * evidence is the `#CG ROM ... present=` line family. Naming the source keeps
 * downstream from reading a configured identity as a freshly detected one. */
#define CG_TELEM_ROM_SOURCE "FROZEN_CONFIG_MAP"
#define CG_TELEM_HEALTH_UNKNOWN "UNKNOWN"
#define CG_TELEM_ROM_UNREAD "UNREAD"
