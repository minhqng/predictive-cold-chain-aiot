/*
 * ColdGuard firmware - raw telemetry line (W04).
 */
#include "cg_telemetry.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

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
    if (!valid) {
        (void)snprintf(buf, cap, "%s", CG_INVALID_VALUE_TOKEN);
    } else {
        (void)snprintf(buf, cap, "%.4f", (double)value);
    }
    return buf;
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

size_t cg_telemetry_format(char *buf, size_t cap, const cg_telemetry_frame_t *frame)
{
    char *cursor = buf;
    size_t left = cap;
    bool overflow = false;
    char t_inside[16];
    char t_cold[16];
    char t_hot[16];
    char t_ambient[16];
    char rh[16];
    char v_buf[16];
    char i_buf[16];
    char p_buf[16];
    char raw[CG_ROLE_COUNT][16];
    const char *t_inside_status;
    const char *t_status[CG_ROLE_COUNT];
    const char *p_status;
    const char *sensor_validity;
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

    t_inside_status = thermal_status(snap, CG_ROLE_T2, now_ms);
    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        t_status[role] = thermal_status(snap, role, now_ms);
    }
    p_status = power_status(snap, now_ms);
    sensor_validity = snap->thermal_observed ? cg_quality_name((cg_thermal_quality_t)snap->thermal_quality)
                                             : CG_TELEM_STATUS_NO_DATA;

    append(&cursor, &left, &overflow,
           "%s %s schema=%d timestamp_utc=UNAVAILABLE "
           "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK "
           "uptime_ms=%llu elapsed_ms=%llu run_elapsed_ms=%llu "
           "run_id=%s boot_id=%s boot_count=%lu "
           "firmware_version=%s hardware_config_id=%s test_phase=%s",
           CG_LOG_PREFIX, CG_LOG_TELEM, CG_TELEMETRY_SCHEMA_VERSION,
           (unsigned long long)frame->uptime_ms, (unsigned long long)frame->uptime_ms,
           (unsigned long long)tec.elapsed_ms, frame->run_id, frame->boot_id,
           (unsigned long)frame->boot_count, CG_FIRMWARE_VERSION, CG_HARDWARE_CONFIG_ID,
           frame->test_phase);

    append(&cursor, &left, &overflow, " t_inside_c=%s t_inside_status=%s t_inside_src=T2",
           fmt_float(strcmp(t_inside_status, CG_TELEM_STATUS_OK) == 0, snap->t_c[CG_ROLE_T2],
                     t_inside, sizeof(t_inside)),
           t_inside_status);

    append(&cursor, &left, &overflow,
           " t_cold_side_c=%s t_cold_side_status=%s"
           " t_hot_side_c=%s t_hot_side_status=%s"
           " t_ambient_c=%s t_ambient_status=%s"
           " relative_humidity_pct=%s relative_humidity_status=%s",
           fmt_float(false, 0.0f, t_cold, sizeof(t_cold)), CG_TELEM_STATUS_NOT_ASSIGNED,
           fmt_float(false, 0.0f, t_hot, sizeof(t_hot)), CG_TELEM_STATUS_NOT_ASSIGNED,
           fmt_float(false, 0.0f, t_ambient, sizeof(t_ambient)), CG_TELEM_STATUS_NOT_ASSIGNED,
           fmt_float(false, 0.0f, rh, sizeof(rh)), CG_TELEM_STATUS_NOT_PRESENT);

    if (!snap->door_known) {
        append(&cursor, &left, &overflow, " door_open=%s door_status=%s door_raw=%d",
               CG_INVALID_VALUE_TOKEN, CG_TELEM_STATUS_UNVERIFIED, snap->door_raw);
    } else {
        append(&cursor, &left, &overflow, " door_open=%d door_status=%s door_raw=%d",
               snap->door_open ? 1 : 0, CG_TELEM_STATUS_OK, snap->door_raw);
    }

    append(&cursor, &left, &overflow,
           " voltage_v=%s voltage_status=%s current_a=%s current_status=%s"
           " power_w=%s power_status=%s",
           fmt_float(strcmp(p_status, CG_TELEM_STATUS_OK) == 0, snap->voltage_v, v_buf,
                     sizeof(v_buf)),
           p_status,
           fmt_float(strcmp(p_status, CG_TELEM_STATUS_OK) == 0, snap->current_a, i_buf,
                     sizeof(i_buf)),
           p_status,
           fmt_float(strcmp(p_status, CG_TELEM_STATUS_OK) == 0, snap->power_w, p_buf,
                     sizeof(p_buf)),
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

    if (overflow) {
        buf[0] = '\0';
        return 0U;
    }
    return strlen(buf);
}
