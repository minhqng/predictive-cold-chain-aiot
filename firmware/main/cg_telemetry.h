/*
 * ColdGuard firmware - raw telemetry line (W04).
 *
 * One `#CG TELEM` line per second carries the measurements the experiment
 * needs. The line is an *observation*: a missing value is printed as `nan`
 * together with an explicit status token, never as 0.0 and never as the
 * previous value. That is what lets the host build a dataset without
 * inventing samples.
 *
 * Field contract (schema 1; see docs/06 and firmware/tools/
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
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "cg_snapshot.h"
#include "cg_tec_control.h"

typedef struct {
    const char *boot_id;
    uint32_t boot_count;
    uint64_t uptime_ms;
    const char *run_id;
    const char *test_phase;
    const cg_snapshot_t *snap;
    const cg_tec_control_t *ctl;
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
