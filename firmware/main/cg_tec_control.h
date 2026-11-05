/*
 * ColdGuard firmware - fail-closed cooling-only TEC controller (W04).
 *
 * Pure C: no ESP-IDF, no FreeRTOS, no stdio. Time, hardware and sensor
 * observations are injected, so the whole state machine runs in a host
 * harness. The target build wires it to the as-built adapter, the snapshot
 * module and the fixed 100 ms commissioning task.
 *
 * Mechanism (all gates must pass, in this order):
 *
 *   OFF --ARM token--> ARMED --START--> COOLING --stop/limit--> COOLDOWN --> OFF
 *                                     \--fault--> FAULT_LATCH --CLEAR--> COOLDOWN
 *
 *   START gates: state, one-shot authorization, valid duty, valid duration,
 *   every operating limit RESOLVED, output stage available, thermal/power
 *   observations fresh and valid, a measured hot-side channel, hardware
 *   interlock closed, fan commandable.
 *
 *   START ordering: duty 0 -> fan on -> enables (R_EN on, L_EN off) ->
 *   commanded duty. Any failure rolls back to enables off, duty 0, fan off.
 *
 *   STOP ordering: enables off first, then duty 0. The fan stays on through
 *   the cool-down window.
 *
 * Invariants:
 *   - the controller never passes len=true; there is no reverse path;
 *   - boot, reset, timeout, invalid sensor, command error and unauthorized
 *     requests all end in the safe state, never in an energized one;
 *   - a fault latches until an operator CLEAR with the boot token AND healthy
 *     inputs; clearing does not arm the next run;
 *   - the bounded run duration is enforced every tick;
 *   - a tick gap longer than the heartbeat timeout trips a fault;
 *   - no value is carried forward: a stale observation cannot satisfy a gate.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "cg_tec_limits.h"
#include "cg_tec_platform.h"

#define CG_TEC_DUTY_MAX 1000U
#define CG_TEC_TOKEN_MAX 9
#define CG_TEC_REASON_MAX 40

typedef enum {
    CG_TEC_STATE_OFF = 0,
    CG_TEC_STATE_ARMED,
    CG_TEC_STATE_COOLING,
    CG_TEC_STATE_COOLDOWN,
    CG_TEC_STATE_FAULT_LATCH,
} cg_tec_state_t;

typedef enum {
    CG_TEC_FAULT_NONE = 0,
    CG_TEC_FAULT_UNAUTHORIZED = 1u << 0,
    CG_TEC_FAULT_LIMITS_UNRESOLVED = 1u << 1,
    CG_TEC_FAULT_STAGE_UNAVAILABLE = 1u << 2,
    CG_TEC_FAULT_SENSOR_INVALID = 1u << 3,
    CG_TEC_FAULT_SENSOR_STALE = 1u << 4,
    CG_TEC_FAULT_OVERCURRENT = 1u << 5,
    CG_TEC_FAULT_OVERVOLTAGE = 1u << 6,
    CG_TEC_FAULT_UNDERVOLTAGE = 1u << 7,
    CG_TEC_FAULT_OVERTEMP = 1u << 8,
    CG_TEC_FAULT_INTERLOCK_OPEN = 1u << 9,
    CG_TEC_FAULT_FAN_UNAVAILABLE = 1u << 10,
    CG_TEC_FAULT_HEARTBEAT = 1u << 11,
    CG_TEC_FAULT_HW_REJECTED = 1u << 12,
    CG_TEC_FAULT_ESTOP = 1u << 13,
} cg_tec_fault_t;

typedef enum {
    CG_TEC_START_OK = 0,
    CG_TEC_START_NOT_ARMED,
    CG_TEC_START_BAD_STATE,
    CG_TEC_START_BAD_DUTY,
    CG_TEC_START_BAD_DURATION,
    CG_TEC_START_LIMITS_UNRESOLVED,
    CG_TEC_START_STAGE_UNAVAILABLE,
    CG_TEC_START_SENSOR,
    CG_TEC_START_INTERLOCK_OPEN,
    CG_TEC_START_FAN_UNAVAILABLE,
    CG_TEC_START_HW_REJECTED,
} cg_tec_start_result_t;

/* One observation set. `now_ms` is a monotonic millisecond clock. A missing
 * channel is signalled by its validity flag, never by a placeholder value. */
typedef struct {
    uint64_t now_ms;
    bool thermal_observed;
    bool thermal_valid;     /* every required measurement role valid */
    uint64_t thermal_obs_ms;
    bool t_cold_side_valid; /* a probe actually assigned to the cold side */
    float t_cold_side_c;
    bool t_hot_side_valid;  /* a probe actually assigned to the hot side */
    float t_hot_side_c;
    bool power_observed;
    bool power_valid;
    uint64_t power_obs_ms;
    float voltage_v;
    float current_a;
} cg_tec_inputs_t;

typedef struct {
    cg_tec_state_t state;
    uint32_t fault_bits;
    uint32_t duty_permille;
    /* W05: what the output layer was actually left driving, as distinct from
     * what was requested. A refused START leaves duty_permille at 0 and this
     * false; a fault path that disengaged the outputs clears it even while the
     * state has not yet settled. Telemetry reports it as `cooling_applied` so
     * a command can never be read as a verified physical action. */
    bool outputs_energized;
    uint64_t elapsed_ms;     /* since a successful START, 0 when not cooling */
    uint64_t remaining_ms;   /* bounded-run time left, 0 when not cooling */
    uint32_t start_count;
    uint32_t stop_count;
    uint32_t estop_count;
    uint32_t fault_count;
    uint32_t refuse_count;
    bool fan_on;
    char reason[CG_TEC_REASON_MAX];
} cg_tec_status_t;

typedef struct {
    const cg_tec_limit_table_t *limits;
    cg_tec_hw_ops_t ops;
    char token[CG_TEC_TOKEN_MAX];
    cg_tec_state_t state;
    bool authorized;
    uint64_t authorized_at_ms;
    uint32_t arm_ttl_ms;
    uint32_t heartbeat_timeout_ms;
    uint32_t cooldown_ms;
    uint32_t thermal_stale_ms;
    uint32_t power_stale_ms;
    uint32_t duty_permille;
    uint64_t cooling_start_ms;
    uint64_t cooling_deadline_ms;
    uint64_t cooldown_until_ms;
    uint64_t last_tick_ms;
    bool have_tick;
    uint32_t fault_bits;
    bool outputs_energized;
    bool fan_on;
    uint32_t start_count;
    uint32_t stop_count;
    uint32_t estop_count;
    uint32_t fault_count;
    uint32_t refuse_count;
    char reason[CG_TEC_REASON_MAX];
} cg_tec_control_t;

/* Initializes to OFF with no authorization. Safe to call on a zeroed
 * struct; `boot_token` is the boot-generated operator token. */
void cg_tec_control_init(cg_tec_control_t *ctl, const cg_tec_limit_table_t *limits,
                         const cg_tec_hw_ops_t *ops, const char *boot_token,
                         uint64_t now_ms, uint32_t arm_ttl_ms,
                         uint32_t heartbeat_timeout_ms, uint32_t cooldown_ms,
                         uint32_t thermal_stale_ms, uint32_t power_stale_ms);

/* One-shot authorization. Accepted only in OFF/ARMED with the exact token. */
bool cg_tec_arm(cg_tec_control_t *ctl, const char *token, uint64_t now_ms);

/* True when an unexpired ARM exists. */
bool cg_tec_is_armed(const cg_tec_control_t *ctl, uint64_t now_ms);

/* Starts one bounded cooling run. Consumes the ARM on success. */
cg_tec_start_result_t cg_tec_start(cg_tec_control_t *ctl, const cg_tec_inputs_t *in,
                                   uint32_t duration_ms, uint32_t duty_permille);

/* Operator stop. COOLING -> COOLDOWN (fan stays on); ARMED -> OFF. */
void cg_tec_stop(cg_tec_control_t *ctl, const cg_tec_inputs_t *in, const char *reason);

/* Emergency stop: outputs off immediately, fan on, latching fault. */
void cg_tec_estop(cg_tec_control_t *ctl, uint64_t now_ms, const char *reason);

/* Clears a latched fault with the boot token and healthy inputs. Returns
 * false (with a reason) when refused. Clear does not arm a new run. */
bool cg_tec_clear_fault(cg_tec_control_t *ctl, const char *token, const cg_tec_inputs_t *in);

/* Periodic supervision: heartbeat gap, bounded duration, live limits,
 * sensor freshness, interlock, cool-down completion. */
void cg_tec_tick(cg_tec_control_t *ctl, const cg_tec_inputs_t *in);

void cg_tec_get_status(const cg_tec_control_t *ctl, cg_tec_status_t *out);

const char *cg_tec_state_name(cg_tec_state_t state);
const char *cg_tec_start_result_name(cg_tec_start_result_t result);
