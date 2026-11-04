/*
 * ColdGuard firmware - raw telemetry line (W04 foundation, W05 identity/quality).
 * See cg_telemetry.h for what each field group is evidence of.
 */
#include "cg_telemetry.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "cg_quality.h"
#include "coldguard_config.h"

static void append(char **cursor, size_t *left, bool *overflow, const char *fmt, ...)
{
    va_list args;
    int written;

    if (*overflow) {
        return;
    }
    if (*left == 0U) {
        *overflow = true;
        return;
    }
    va_start(args, fmt);
    written = vsnprintf(*cursor, *left, fmt, args);
    va_end(args);
    if (written < 0) {
        *overflow = true;
        return;
    }
    if ((size_t)written >= *left) {
        /* The token did not fit. Stop writing and report the frame as
         * unformattable: a truncated observation must never be emitted as
         * if it were complete. */
        *overflow = true;
        return;
    }
    *cursor += (size_t)written;
    *left -= (size_t)written;
}

static const char *fmt_float(bool valid, float value, char *buf, size_t cap)
{
    int written;

    if (!valid) {
        (void)snprintf(buf, cap, "%s", CG_INVALID_VALUE_TOKEN);
        return buf;
    }
    written = snprintf(buf, cap, "%.4f", (double)value);
    if (written < 0 || (size_t)written >= cap) {
        /* The value does not fit its field. Emitting the truncated prefix would
         * put a plausible wrong number on the wire, which is the one thing this
         * formatter's refuse-not-truncate rule exists to prevent - so the field
         * becomes a missing value instead, and its *_status companion still
         * decides how the reader treats it. */
        (void)snprintf(buf, cap, "%s", CG_INVALID_VALUE_TOKEN);
    }
    return buf;
}

/* Age of an observation, saturating instead of wrapping if the clock moved
 * backwards. A negative age is not "fresh"; it is reported as the maximum so the
 * reader sees an unusable field rather than a plausible small number. */
static uint64_t obs_age_ms(uint64_t obs_ms, uint64_t now_ms)
{
    if (now_ms < obs_ms) {
        return UINT64_MAX;
    }
    return now_ms - obs_ms;
}

static cg_source_state_t source_state(bool observed, uint64_t obs_ms, uint64_t now_ms,
                                      uint64_t limit_ms, bool ok)
{
    if (!observed) {
        return CG_SRC_EMPTY;
    }
    if (obs_age_ms(obs_ms, now_ms) > limit_ms) {
        return CG_SRC_STALE;
    }
    return ok ? CG_SRC_FRESH_OK : CG_SRC_FRESH_BAD;
}

static const char *thermal_status(const cg_snapshot_t *snap, int role, uint64_t now_ms)
{
    if (!snap->thermal_observed) {
        return CG_TELEM_STATUS_NO_DATA;
    }
    if (now_ms < snap->thermal_obs_ms ||
        now_ms - snap->thermal_obs_ms > (uint64_t)CG_TEC_STALE_THERMAL_MS) {
        return CG_TELEM_STATUS_STALE;
    }
    return snap->t_valid[role] ? CG_TELEM_STATUS_OK : CG_TELEM_STATUS_INVALID;
}

static const char *power_status(const cg_snapshot_t *snap, uint64_t now_ms)
{
    if (!snap->power_observed) {
        return CG_TELEM_STATUS_NO_DATA;
    }
    if (now_ms < snap->power_obs_ms ||
        now_ms - snap->power_obs_ms > (uint64_t)CG_TEC_STALE_POWER_MS) {
        return CG_TELEM_STATUS_STALE;
    }
    return snap->power_valid ? CG_TELEM_STATUS_OK : CG_TELEM_STATUS_INVALID;
}

/*
 * The ambient channel has three different reasons to carry no value, and they
 * must not collapse into one token: no producer cycle has completed yet
 * (NO_DATA), the bus is up but no module acknowledges it
 * (SENSOR_NOT_PRESENT - a declared configuration fact), and a module that
 * answers but produced a refused reading (INVALID). docs/01 forbids a missing
 * reading being presented as a measured one, which is what a single "0.0" or a
 * carried-forward last value would have done.
 */
static const char *env_status(const cg_snapshot_t *snap, uint64_t now_ms)
{
    if (!snap->env_observed) {
        return CG_TELEM_STATUS_NO_DATA;
    }
    if (!snap->env_present) {
        return CG_TELEM_STATUS_NOT_PRESENT;
    }
    if (now_ms < snap->env_obs_ms ||
        now_ms - snap->env_obs_ms > (uint64_t)CG_TELEM_STALE_ENV_MS) {
        return CG_TELEM_STATUS_STALE;
    }
    return snap->env_valid ? CG_TELEM_STATUS_OK : CG_TELEM_STATUS_INVALID;
}

/*
 * Does the electrical observation corroborate the output the control layer was
 * left driving? Only MEASURED_MATCHES_APPLIED and MEASURED_ZERO are statements
 * about the branch; the other two mean the PZEM could not be asked. A stale or
 * absent current reading is never converted into a claim that the branch is
 * idle (docs/01 2237-2249).
 */
static const char *cooling_evidence(const cg_snapshot_t *snap, uint64_t now_ms,
                                    bool applied)
{
    if (!snap->power_observed) {
        return CG_TELEM_EVIDENCE_NONE;
    }
    if (strcmp(power_status(snap, now_ms), CG_TELEM_STATUS_OK) != 0) {
        return CG_TELEM_EVIDENCE_STALE;
    }
    if (applied == (snap->current_a > 0.0f)) {
        /* Either "driving and drawing" or "not driving and not drawing". The
         * measurement is consistent with the output state; it is still not a
         * calibration-grade claim that the branch carries rated current. */
        return applied ? CG_TELEM_EVIDENCE_APPLIED : CG_TELEM_EVIDENCE_IDLE;
    }
    /* Driving with no measured current, or idle current with nothing driven: the
     * two cannot be told apart from this field alone, but either one means the
     * applied state and the electrical observation disagree, which is exactly
     * what must not be smoothed into "OFF looks fine". */
    return CG_TELEM_EVIDENCE_CONTRADICTS;
}

static const char *health_name(const cg_health_report_t *health, cg_producer_id_t id)
{
    if (health == NULL) {
        return CG_TELEM_HEALTH_UNKNOWN;
    }
    return cg_health_state_name(health->state[id]);
}

size_t cg_telemetry_format(char *buf, size_t cap, const cg_telemetry_frame_t *frame)
{
    char *cursor = buf;
    size_t left = cap;
    bool overflow = false;
    char t_inside[24];
    char t_cold[24];
    char t_hot[24];
    char t_ambient[24];
    char rh[24];
    char v_buf[24];
    char i_buf[24];
    char p_buf[24];
    char e_buf[24];
    char raw[CG_ROLE_COUNT][24];
    const char *t_inside_status;
    const char *t_hot_side_status;
    const char *t_status[CG_ROLE_COUNT];
    const char *p_status;
    const char *env_status_text;
    const char *sensor_validity;
    const char *applied;
    const char *evidence;
    cg_quality_set_t quality;
    cg_quality_input_t quality_in;
    cg_tec_status_t tec;
    const cg_snapshot_t *snap;
    uint64_t now_ms;

    if (buf == NULL || cap == 0U) {
        return 0U;
    }
    buf[0] = '\0';
    if (frame == NULL || frame->snap == NULL || frame->ctl == NULL ||
        frame->boot_id == NULL || frame->run_id == NULL || frame->test_phase == NULL) {
        return 0U;
    }

    snap = frame->snap;
    now_ms = frame->uptime_ms;
    cg_tec_get_status(frame->ctl, &tec);

    /* Chamber air and the hot side are bound to their own roles here, once, so
     * no emitter below can quietly pull a heatsink reading into the chamber
     * field: ROM 28AEBF2200000006 sits on the TEC hot side in the operator-frozen
     * as-built map, and in the 2026-11-01 run it peaked at 39.938 C while chamber
     * air fell about 8.7 C - the opposite sign to air. */
    t_inside_status = thermal_status(snap, CG_TELEM_CHAMBER_AIR_ROLE, now_ms);
    t_hot_side_status = thermal_status(snap, CG_TELEM_HOT_SIDE_ROLE, now_ms);
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        t_status[role] = thermal_status(snap, role, now_ms);
    }
    p_status = power_status(snap, now_ms);
    env_status_text = env_status(snap, now_ms);
    sensor_validity = snap->thermal_observed ? cg_quality_name((cg_thermal_quality_t)snap->thermal_quality)
                                             : CG_TELEM_STATUS_NO_DATA;

    memset(&quality_in, 0, sizeof(quality_in));
    memset(&quality, 0, sizeof(quality));
    quality_in.probes_ok = snap->probes_ok;
    quality_in.probes_expected = snap->probes_expected;
    quality_in.thermal_state = source_state(
        snap->thermal_observed, snap->thermal_obs_ms, now_ms, CG_TEC_STALE_THERMAL_MS,
        /* Not `thermal_valid`: that flag is the control gate and is false for a
         * single failed probe, which would make the canonical DEGRADED state
         * (docs/01 924-942) unreachable. The quality layer asks a different
         * question - is the observation itself usable for naming a state - and
         * only a whole-snapshot INVALID read fails that. The probe counts below
         * are what separate DEGRADED from INVALID. */
        snap->thermal_quality != CG_QUALITY_INVALID);
    quality_in.power_state = source_state(snap->power_observed, snap->power_obs_ms, now_ms,
                                          CG_TEC_STALE_POWER_MS, snap->power_valid);
    /* The MC-38 semantic state is uncommissioned (docs/01 1047-1060), so a fresh
     * raw level is a read that cannot be named OPEN or CLOSED: FRESH_BAD makes
     * the quality layer report the door group UNKNOWN while the raw level is
     * still carried in door_raw. */
    quality_in.door_state = source_state(snap->door_observed, snap->door_obs_ms, now_ms,
                                         CG_TELEM_STALE_DOOR_MS, snap->door_known);
    /* The ambient producer publishes a timestamp for every completed cycle,
     * including a cycle that concluded the module is absent, so an absent device
     * reads as DEGRADED by presence and a silent one reads as STALE by age. */
    quality_in.bme_state = source_state(snap->env_observed, snap->env_obs_ms, now_ms,
                                        CG_TELEM_STALE_ENV_MS, snap->env_valid);
    quality_in.bme_present = snap->env_present;
    quality_in.thermal_age_ms = obs_age_ms(snap->thermal_obs_ms, now_ms);
    quality_in.power_age_ms = obs_age_ms(snap->power_obs_ms, now_ms);
    quality_in.door_age_ms = obs_age_ms(snap->door_obs_ms, now_ms);
    quality_in.bme_age_ms = obs_age_ms(snap->env_obs_ms, now_ms);
    quality_in.thermal_age_limit_ms = CG_TEC_STALE_THERMAL_MS;
    quality_in.power_age_limit_ms = CG_TEC_STALE_POWER_MS;
    quality_in.door_age_limit_ms = CG_TELEM_STALE_DOOR_MS;
    quality_in.bme_age_limit_ms = CG_TELEM_STALE_ENV_MS;
    /* Set after the ages and limits above: computing this flag from the
     * zero-initialised struct made the stale-door cross-check always false,
     * which is the one thing the comment on door_age_over_limit forbids. */
    quality_in.door_age_over_limit = quality_in.door_age_ms > quality_in.door_age_limit_ms;
    cg_quality_eval(&quality_in, &quality);

    applied = tec.outputs_energized ? CG_TELEM_APPLIED_ON : CG_TELEM_APPLIED_OFF;
    evidence = cooling_evidence(snap, now_ms, tec.outputs_energized);

    append(&cursor, &left, &overflow,
           "%s %s schema=%d timestamp_utc=UNAVAILABLE "
           "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK "
           "uptime_ms=%llu elapsed_ms=%llu run_elapsed_ms=%llu "
           "run_id=%s device_id=%s boot_id=%s boot_count=%lu seq=%lu "
           "firmware_version=%s hardware_config_id=%s calibration_id=%s test_phase=%s",
           CG_LOG_PREFIX, CG_LOG_TELEM, CG_TELEMETRY_SCHEMA_VERSION,
           (unsigned long long)frame->uptime_ms, (unsigned long long)frame->uptime_ms,
           (unsigned long long)tec.elapsed_ms, frame->run_id, CG_DEVICE_ID, frame->boot_id,
           (unsigned long)frame->boot_count, (unsigned long)frame->seq, CG_FIRMWARE_VERSION,
           CG_HARDWARE_CONFIG_ID, CG_CALIBRATION_ID, frame->test_phase);

    /* A-W05-02 sensor identity. docs/01 6.5 makes the ROM the identity, so the
     * frame names the eight bytes configured behind each channel. They are the
     * frozen map's bytes, not a per-frame detection - which is why the line also
     * carries rom_source; presence/mismatch evidence per boot is in the
     * `#CG ROM ... present=` lines. */
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        static const char *const rom_keys[CG_ROLE_COUNT] = {"t1_rom", "t2_rom", "t3_rom",
                                                            "spare_rom"};
        append(&cursor, &left, &overflow, " %s=%s", rom_keys[role],
               (frame->probe_rom[role] != NULL && frame->probe_rom[role][0] != '\0')
                   ? frame->probe_rom[role]
                   : CG_TELEM_ROM_UNREAD);
    }
    append(&cursor, &left, &overflow, " role_status=%s rom_source=%s",
           frame->role_status != NULL ? frame->role_status : CG_TELEM_ROM_UNREAD,
           CG_TELEM_ROM_SOURCE);

    append(&cursor, &left, &overflow, " t_inside_c=%s t_inside_status=%s t_inside_src=%s",
           fmt_float(strcmp(t_inside_status, CG_TELEM_STATUS_OK) == 0,
                     snap->t_c[CG_TELEM_CHAMBER_AIR_ROLE], t_inside, sizeof(t_inside)),
           t_inside_status, CG_TELEM_CHAMBER_AIR_SRC);

    /* The hot side travels in its own field, which is what the schema has always
     * reserved for it: naming it here stops a heatsink reading from being
     * reachable under a chamber-air name. */
    append(&cursor, &left, &overflow,
           " t_hot_side_c=%s t_hot_side_status=%s t_hot_side_src=%s",
           fmt_float(strcmp(t_hot_side_status, CG_TELEM_STATUS_OK) == 0,
                     snap->t_c[CG_TELEM_HOT_SIDE_ROLE], t_hot, sizeof(t_hot)),
           t_hot_side_status, CG_TELEM_HOT_SIDE_SRC);

    /* The ambient pair travels together: both come from the same BME280
     * transaction, so both carry the same status. A temperature that arrived
     * without humidity (a BMP280 answering 0x57) is refused inside the producer
     * and reaches here as INVALID, never as half a reading. */
    append(&cursor, &left, &overflow,
           " t_cold_side_c=%s t_cold_side_status=%s"
           " t_ambient_c=%s t_ambient_status=%s"
           " relative_humidity_pct=%s relative_humidity_status=%s",
           fmt_float(false, 0.0f, t_cold, sizeof(t_cold)), CG_TELEM_STATUS_NOT_ASSIGNED,
           fmt_float(strcmp(env_status_text, CG_TELEM_STATUS_OK) == 0, snap->env_temperature_c,
                     t_ambient, sizeof(t_ambient)), env_status_text,
           fmt_float(strcmp(env_status_text, CG_TELEM_STATUS_OK) == 0, snap->env_humidity_pct,
                     rh, sizeof(rh)), env_status_text);

    if (!snap->door_known) {
        append(&cursor, &left, &overflow, " door_open=%s door_status=%s door_raw=%d",
               CG_INVALID_VALUE_TOKEN, CG_TELEM_STATUS_UNVERIFIED, snap->door_raw);
    } else {
        append(&cursor, &left, &overflow, " door_open=%d door_status=%s door_raw=%d",
               snap->door_open ? 1 : 0, CG_TELEM_STATUS_OK, snap->door_raw);
    }

    append(&cursor, &left, &overflow,
           " voltage_v=%s voltage_status=%s current_a=%s current_status=%s"
           " power_w=%s power_status=%s energy_wh=%s energy_status=%s",
           fmt_float(strcmp(p_status, CG_TELEM_STATUS_OK) == 0, snap->voltage_v, v_buf,
                     sizeof(v_buf)),
           p_status,
           fmt_float(strcmp(p_status, CG_TELEM_STATUS_OK) == 0, snap->current_a, i_buf,
                     sizeof(i_buf)),
           p_status,
           fmt_float(strcmp(p_status, CG_TELEM_STATUS_OK) == 0, snap->power_w, p_buf,
                     sizeof(p_buf)),
           p_status,
           fmt_float(strcmp(p_status, CG_TELEM_STATUS_OK) == 0, snap->energy_wh, e_buf,
                     sizeof(e_buf)),
           p_status);

    append(&cursor, &left, &overflow,
           " pwm_duty=%lu fan_command=%s fan_status=%s output_stage=%s"
           " tec_state=%s fault_code=0x%08lX fault_reason=%s"
           " sensor_validity=%s power_validity=%s",
           (unsigned long)tec.duty_permille, tec.fan_on ? "ON" : "OFF",
           frame->fan_available ? CG_TELEM_STATUS_OK : "NOT_COMMANDABLE",
           frame->output_stage_enabled ? "ENABLED" : "DISABLED", cg_tec_state_name(tec.state),
           (unsigned long)tec.fault_bits, tec.reason, sensor_validity, p_status);

    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        static const char *const names[CG_ROLE_COUNT] = {"t1", "t2", "t3", "spare"};
        append(&cursor, &left, &overflow, " raw_%s_c=%s raw_%s_status=%s", names[role],
               fmt_float(strcmp(t_status[role], CG_TELEM_STATUS_OK) == 0, snap->t_c[role],
                         raw[role], sizeof(raw[role])),
               names[role], t_status[role]);
    }

    /* A-W05-04 coherence: the frame states the age and producer sequence of each
     * group, so a reader can prove whether a value is new instead of inferring
     * it from the fact that a line was emitted. */
    append(&cursor, &left, &overflow,
           " thermal_age_ms=%llu power_age_ms=%llu door_age_ms=%llu"
           " thermal_seq=%lu power_seq=%lu door_transitions=%lu door_cycles=%lu"
           " probes_valid=%lu probes_expected=%lu",
           (unsigned long long)quality_in.thermal_age_ms,
           (unsigned long long)quality_in.power_age_ms,
           (unsigned long long)quality_in.door_age_ms, (unsigned long)snap->thermal_seq,
           (unsigned long)snap->power_seq, (unsigned long)snap->door_transitions,
           (unsigned long)snap->door_cycles, (unsigned long)snap->probes_ok,
           (unsigned long)snap->probes_expected);

    /* A-W05-05 quality, in the canonical vocabulary (docs/01 2263-2308). */
    append(&cursor, &left, &overflow,
           " thermal_quality=%s environment_quality=%s door_quality=%s electrical_quality=%s"
           " quality=%s",
           quality.thermal, quality.environment, quality.door, quality.electrical,
           quality.overall);

    /* Applied state separated from the request, with the corroboration stated
     * next to it (docs/02, docs/01 2237-2249). */
    append(&cursor, &left, &overflow, " cooling_applied=%s cooling_applied_source=%s"
                                      " cooling_evidence=%s",
           applied, CG_TELEM_APPLIED_SOURCE, evidence);

    /* A-W05-01 producer liveness. `health` is the worst producer; the per-name
     * fields say which one, and the beat/gap counts are the raw evidence the
     * timing study reads. */
    append(&cursor, &left, &overflow,
           " health=%s health_thermal=%s health_bme=%s health_door=%s health_power=%s"
           " health_telemetry=%s health_control=%s",
           frame->health != NULL ? frame->health->overall : CG_TELEM_HEALTH_UNKNOWN,
           health_name(frame->health, CG_PRODUCER_THERMAL),
           health_name(frame->health, CG_PRODUCER_BME),
           health_name(frame->health, CG_PRODUCER_DOOR),
           health_name(frame->health, CG_PRODUCER_POWER),
           health_name(frame->health, CG_PRODUCER_TELEMETRY),
           health_name(frame->health, CG_PRODUCER_CONTROL));

    if (frame->health != NULL) {
        append(&cursor, &left, &overflow,
               " thermal_beats=%lu power_beats=%lu door_beats=%lu"
               " thermal_max_gap_ms=%lu power_max_gap_ms=%lu door_max_gap_ms=%lu",
               (unsigned long)frame->health->beats[CG_PRODUCER_THERMAL],
               (unsigned long)frame->health->beats[CG_PRODUCER_POWER],
               (unsigned long)frame->health->beats[CG_PRODUCER_DOOR],
               (unsigned long)frame->health->max_gap_ms[CG_PRODUCER_THERMAL],
               (unsigned long)frame->health->max_gap_ms[CG_PRODUCER_POWER],
               (unsigned long)frame->health->max_gap_ms[CG_PRODUCER_DOOR]);
    }

    /* A-W06-04: the desired/applied distinction survives into the dataset.
     * `cooling_applied` (above) is what the device is doing; these are what it
     * was last asked to do and how that request was answered. */
    if (frame->cmd_state != NULL && frame->cmd_state->has_command) {
        append(&cursor, &left, &overflow,
               " command_id=%s desired_cooling=%s desired_duty_permille=%lu"
               " last_ack_status=%s last_ack_reason=%s",
               frame->cmd_state->command_id,
               cg_cmd_cooling_name(frame->cmd_state->desired_cooling),
               (unsigned long)frame->cmd_state->desired_duty_permille,
               cg_cmd_ack_status_name(frame->cmd_state->last_status),
               frame->cmd_state->last_reason != NULL ? frame->cmd_state->last_reason : "NONE");
    } else {
        append(&cursor, &left, &overflow,
               " command_id=NONE desired_cooling=NONE desired_duty_permille=nan"
               " last_ack_status=NONE last_ack_reason=NO_COMMAND_RECEIVED");
    }

    if (overflow) {
        buf[0] = '\0';
        return 0U;
    }
    return strlen(buf);
}
