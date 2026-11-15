/*
 * ColdGuard firmware - producer liveness (W05, A-W05-01).
 * See cg_health.h for the semantics and for which thresholds are canonical.
 */
#include "cg_health.h"

#include <stdio.h>
#include <string.h>

#define CG_HEALTH_LATE_FACTOR 2ULL
#define CG_HEALTH_MISSED_FACTOR 4ULL

static const char *health_state_name(cg_health_state_t state)
{
    switch (state) {
        case CG_HEALTH_OK:
            return "OK";
        case CG_HEALTH_LATE:
            return "LATE";
        case CG_HEALTH_MISSED:
            return "MISSED";
        case CG_HEALTH_NEVER:
        default:
            /* A producer that has not beaten is not healthy, but it is also not a
             * detected failure: report NEVER and let the quality layer keep the
             * values it owns UNKNOWN. */
            return "NEVER";
    }
}

void cg_health_init(cg_producer_t producers[CG_PRODUCER_COUNT],
                    const uint64_t periods_ms[CG_PRODUCER_COUNT])
{
    for (int i = 0; i < CG_PRODUCER_COUNT; i++) {
        producers[i].last_beat_ms = 0;
        producers[i].period_ms = periods_ms[i];
        producers[i].beats = 0;
        producers[i].max_gap_ms = 0;
    }
}

void cg_health_beat(cg_producer_t producers[CG_PRODUCER_COUNT], cg_producer_id_t id,
                    uint64_t now_ms)
{
    if (id >= CG_PRODUCER_COUNT) {
        return;
    }
    cg_producer_t *p = &producers[id];
    if (p->beats > 0 && now_ms >= p->last_beat_ms) {
        uint64_t gap = now_ms - p->last_beat_ms;
        if (gap > p->max_gap_ms) {
            p->max_gap_ms = (uint32_t)(gap > 0xFFFFFFFFULL ? 0xFFFFFFFFULL : gap);
        }
    }
    p->last_beat_ms = now_ms;
    p->beats++;
}

cg_health_state_t cg_health_producer_state(const cg_producer_t *p, uint64_t now_ms)
{
    if (p->beats == 0 || p->period_ms == 0) {
        return CG_HEALTH_NEVER;
    }
    if (now_ms < p->last_beat_ms) {
        /* Monotonic uptime went backwards: the observation is not trustworthy. */
        return CG_HEALTH_MISSED;
    }
    uint64_t age = now_ms - p->last_beat_ms;
    if (age > p->period_ms * CG_HEALTH_MISSED_FACTOR) {
        return CG_HEALTH_MISSED;
    }
    if (age > p->period_ms * CG_HEALTH_LATE_FACTOR) {
        return CG_HEALTH_LATE;
    }
    return CG_HEALTH_OK;
}

/* Liveness severity. The ordering is deliberate and is NOT the enum order:
 * a producer that has never beaten outranks OK, because a silent task must not
 * be certified healthy by another task's traffic; but a producer that IS
 * speaking and is late or missing outranks a never-beaten one, because that is a
 * detected regression in something that was running. Consequence to keep in
 * mind: while BME280 is unimplemented, `overall` is NEVER even on a perfectly
 * healthy device, so consumers must read the per-producer names, not only
 * `health`. */
static int health_rank(cg_health_state_t state)
{
    switch (state) {
        case CG_HEALTH_MISSED:
            return 3;
        case CG_HEALTH_LATE:
            return 2;
        case CG_HEALTH_NEVER:
            return 1;
        case CG_HEALTH_OK:
        default:
            return 0;
    }
}

void cg_health_eval(const cg_producer_t producers[CG_PRODUCER_COUNT], uint64_t now_ms,
                    cg_health_report_t *out)
{
    if (producers == NULL || out == NULL) {
        return;
    }
    cg_health_state_t worst = CG_HEALTH_OK;
    for (int i = 0; i < CG_PRODUCER_COUNT; i++) {
        cg_health_state_t state = cg_health_producer_state(&producers[i], now_ms);
        out->state[i] = state;
        uint64_t gap = 0;
        if (producers[i].beats > 0 && now_ms >= producers[i].last_beat_ms) {
            gap = now_ms - producers[i].last_beat_ms;
        }
        out->gap_ms[i] = (uint32_t)(gap > 0xFFFFFFFFULL ? 0xFFFFFFFFULL : gap);
        out->max_gap_ms[i] = producers[i].max_gap_ms;
        out->beats[i] = producers[i].beats;
        if (health_rank(state) > health_rank(worst)) {
            worst = state;
        }
    }
    (void)snprintf(out->overall, sizeof(out->overall), "%s", health_state_name(worst));
}

const char *cg_health_state_name(cg_health_state_t state)
{
    return health_state_name(state);
}

/* ------------------------------------------------------------------ */
/* Process-wide registry                                               */
/* ------------------------------------------------------------------ */

/* The array-based API above is pure so the host harness can drive it with its
 * own state. This shared instance is what the firmware tasks beat into.
 *
 * The lock is real on the device and a no-op on the host build, where the
 * harness is single-threaded and the same functions must still be callable.
 * Without the critical section a reader on ESP32-S3 could observe a 64-bit
 * `last_beat_ms` written as two 32-bit halves and compute an age from a torn
 * value, which is exactly the kind of false freshness this layer exists to
 * prevent. */
#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"

static portMUX_TYPE s_registry_mux = portMUX_INITIALIZER_UNLOCKED;
#define CG_HEALTH_LOCK() taskENTER_CRITICAL(&s_registry_mux)
#define CG_HEALTH_UNLOCK() taskEXIT_CRITICAL(&s_registry_mux)
#else
#define CG_HEALTH_LOCK() ((void)0)
#define CG_HEALTH_UNLOCK() ((void)0)
#endif

static cg_producer_t s_registry[CG_PRODUCER_COUNT];

void cg_health_registry_init(const uint64_t periods_ms[CG_PRODUCER_COUNT])
{
    CG_HEALTH_LOCK();
    cg_health_init(s_registry, periods_ms);
    CG_HEALTH_UNLOCK();
}

void cg_health_registry_beat(cg_producer_id_t id, uint64_t now_ms)
{
    CG_HEALTH_LOCK();
    cg_health_beat(s_registry, id, now_ms);
    CG_HEALTH_UNLOCK();
}

void cg_health_registry_eval(uint64_t now_ms, cg_health_report_t *out)
{
    CG_HEALTH_LOCK();
    cg_health_eval(s_registry, now_ms, out);
    CG_HEALTH_UNLOCK();
}

void cg_health_registry_copy(cg_producer_t out[CG_PRODUCER_COUNT])
{
    CG_HEALTH_LOCK();
    for (int i = 0; i < CG_PRODUCER_COUNT; i++) {
        out[i] = s_registry[i];
    }
    CG_HEALTH_UNLOCK();
}
