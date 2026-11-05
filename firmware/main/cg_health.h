/*
 * ColdGuard firmware - producer liveness (W05, A-W05-01).
 *
 * W05 separates the concerns the commissioning loop drives and makes each one
 * observable: if the thermal, PZEM or door producer stops publishing, that has
 * to be visible in the telemetry rather than looking like a stable sensor that
 * simply reports the same number. A producer that stops beating is reported as
 * MISSED; the values it owned go stale and the quality layer marks them
 * accordingly, so nothing is carried forward silently.
 *
 * No FreeRTOS here: the host harness drives the same functions the firmware
 * uses.
 */
#pragma once

#include <stdint.h>

typedef enum {
    CG_PRODUCER_THERMAL = 0,
    CG_PRODUCER_BME,
    CG_PRODUCER_DOOR,
    CG_PRODUCER_POWER,
    CG_PRODUCER_TELEMETRY,
    CG_PRODUCER_CONTROL,
    CG_PRODUCER_COUNT
} cg_producer_id_t;

typedef enum {
    CG_HEALTH_NEVER = 0,
    CG_HEALTH_OK,
    CG_HEALTH_LATE,
    CG_HEALTH_MISSED
} cg_health_state_t;

typedef struct {
    uint64_t last_beat_ms;
    uint64_t period_ms;
    uint32_t beats;
    uint32_t max_gap_ms;
} cg_producer_t;

typedef struct {
    cg_health_state_t state[CG_PRODUCER_COUNT];
    uint32_t gap_ms[CG_PRODUCER_COUNT];
    /* Historical extremes since boot, copied under the same lock as the state,
     * so telemetry can report a producer's worst observed gap without handing
     * out a mutable pointer into the shared registry. */
    uint32_t max_gap_ms[CG_PRODUCER_COUNT];
    uint32_t beats[CG_PRODUCER_COUNT];
    char overall[10];
} cg_health_report_t;

void cg_health_init(cg_producer_t producers[CG_PRODUCER_COUNT],
                    const uint64_t periods_ms[CG_PRODUCER_COUNT]);

/* One beat for `id`. Records the gap since the previous beat of that producer. */
void cg_health_beat(cg_producer_t producers[CG_PRODUCER_COUNT], cg_producer_id_t id,
                    uint64_t now_ms);

/* Liveness of a single producer, exposed for the harness and for the telemetry
 * layer so it can name the worst producer without re-deriving the thresholds. */
cg_health_state_t cg_health_producer_state(const cg_producer_t *p, uint64_t now_ms);

/* Evaluates liveness. A producer is LATE past 2x and MISSED past 4x its period.
 * Those multipliers are a firmware-internal observability choice, not a frozen
 * canonical threshold: docs/01 2237-2249 leaves the control freshness threshold
 * to policy configuration. */
void cg_health_eval(const cg_producer_t producers[CG_PRODUCER_COUNT], uint64_t now_ms,
                    cg_health_report_t *out);

const char *cg_health_state_name(cg_health_state_t state);

/* ------------------------------------------------------------------ */
/* Process-wide registry                                               */
/* ------------------------------------------------------------------ */

/* The functions above are pure so the host harness can drive them with its own
 * arrays. The firmware uses this one shared registry, which the producer tasks
 * beat into from their own context and the commissioning task reads when it
 * formats telemetry. A task that stops calling cg_health_registry_beat() is
 * reported by name instead of leaving the telemetry to imply that a producer is
 * still running. */
void cg_health_registry_init(const uint64_t periods_ms[CG_PRODUCER_COUNT]);
void cg_health_registry_beat(cg_producer_id_t id, uint64_t now_ms);
void cg_health_registry_eval(uint64_t now_ms, cg_health_report_t *out);
/* Copies the per-producer counters into caller-owned memory under the lock. */
void cg_health_registry_copy(cg_producer_t out[CG_PRODUCER_COUNT]);
