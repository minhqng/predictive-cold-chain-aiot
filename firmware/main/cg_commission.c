/*
 * ColdGuard firmware - TEC commissioning task (W04).
 *
 * No application source or header calls a network API: no Wi-Fi, HTTP, MQTT,
 * lwIP, TLS or BSD socket use exists. Static check 8 in
 * firmware/tools/cg_check_firmware_w04.py enforces that on this tree. Within
 * these sources the only command path is the local UART console and the only
 * authorization is the boot token printed there, so this application opens no
 * remote way to override a protection. Whether network objects from ESP-IDF
 * default components survive into the linked image is not claimed here: the
 * link map is not part of this delivery.
 */
#include "cg_commission.h"

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include "esp_random.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "sdkconfig.h"

#include "cg_console.h"
#include "cg_health.h"
#include "cg_log.h"
#include "cg_rom_map.h"
#include "cg_snapshot.h"
#include "cg_tec_command.h"
#include "cg_tec_control.h"
#include "cg_tec_limits.h"
#include "cg_tec_platform.h"
#include "cg_telemetry.h"
#include "coldguard_config.h"

#define CG_COMMISSION_STACK_WORDS 6144
#define CG_COMMISSION_TASK_PRIORITY 7
#define CG_COMMAND_QUEUE_LEN 8

static cg_tec_control_t s_ctl;
static QueueHandle_t s_cmd_queue;
static char s_boot_id[9];
static uint32_t s_boot_count;
static char s_run_id[CG_TEC_RUN_ID_LEN] = "UNSET";
static char s_test_phase[CG_TEC_PHASE_LEN] = "UNSET";
/* A-W05-02: the monotonic per-boot frame counter. It starts at 1 and is never
 * reset by a command, a run change or a fault clear, because the backend dedup
 * key is (device_id, boot_id, seq) and a repeated seq inside one boot would
 * make a frame uninsertable rather than merely confusing. */
static uint32_t s_telem_seq;
static char s_probe_rom_hex[CG_ROLE_COUNT][CG_TELEM_ROM_HEX_LEN];

static void render_probe_identity(void)
{
    static const char digits[] = "0123456789ABCDEF";

    for (int role = 0; role < CG_ROLE_COUNT; role++) {
        uint8_t rom[8];
        size_t out = 0;
        cg_rom_map_bytes((cg_role_t)role, rom);
        for (int i = 0; i < 8 && out + 2U < sizeof(s_probe_rom_hex[role]); i++) {
            s_probe_rom_hex[role][out++] = digits[(rom[i] >> 4) & 0xFU];
            s_probe_rom_hex[role][out++] = digits[rom[i] & 0xFU];
        }
        s_probe_rom_hex[role][out] = '\0';
    }
}

static void make_token(char out[CG_TEC_TOKEN_LEN])
{
    (void)snprintf(out, CG_TEC_TOKEN_LEN, "%08lx", (unsigned long)esp_random());
}

static void log_tec(const char *event, const char *result)
{
    cg_tec_status_t status;
    char line[512];

    cg_tec_get_status(&s_ctl, &status);
    (void)snprintf(
        line, sizeof(line),
        "%s %s event=%s result=%s reason=%s state=%s fault=0x%08lX duty=%lu elapsed_ms=%llu "
        "remaining_ms=%llu starts=%lu stops=%lu estops=%lu faults=%lu refusals=%lu fan=%d",
        CG_LOG_PREFIX, CG_LOG_TEC, event, result != NULL ? result : "NA", status.reason,
        cg_tec_state_name(status.state), (unsigned long)status.fault_bits,
        (unsigned long)status.duty_permille, (unsigned long long)status.elapsed_ms,
        (unsigned long long)status.remaining_ms, (unsigned long)status.start_count,
        (unsigned long)status.stop_count, (unsigned long)status.estop_count,
        (unsigned long)status.fault_count, (unsigned long)status.refuse_count,
        status.fan_on ? 1 : 0);
    (void)cg_log_raw_line(line);
}

static void build_inputs(const cg_snapshot_t *snap, uint64_t now_ms, cg_tec_inputs_t *in)
{
    memset(in, 0, sizeof(*in));
    in->now_ms = now_ms;
    in->thermal_observed = snap->thermal_observed;
    in->thermal_valid = snap->thermal_valid;
    in->thermal_obs_ms = snap->thermal_obs_ms;
    /* No probe is physically assigned to the cold side or the hot side yet
     * (docs/06 gate G2). The flags stay false, so the controller refuses to
     * start instead of pretending a chamber probe measures the TEC. */
    in->t_cold_side_valid = false;
    in->t_cold_side_c = 0.0f;
    in->t_hot_side_valid = false;
    in->t_hot_side_c = 0.0f;
    in->power_observed = snap->power_observed;
    in->power_valid = snap->power_valid;
    in->power_obs_ms = snap->power_obs_ms;
    in->voltage_v = snap->voltage_v;
    in->current_a = snap->current_a;
}

static void emit_telemetry(uint64_t now_ms, const cg_snapshot_t *snap)
{
    char line[CG_TELEMETRY_LINE_MAX];
    const cg_tec_hw_ops_t *ops = cg_tec_hw_ops();
    cg_health_report_t health;
    cg_telemetry_frame_t frame = {
        .seq = ++s_telem_seq,
        .boot_id = s_boot_id,
        .boot_count = s_boot_count,
        .uptime_ms = now_ms,
        .run_id = s_run_id,
        .test_phase = s_test_phase,
        .snap = snap,
        .ctl = &s_ctl,
        .health = &health,
        .probe_rom = {s_probe_rom_hex[0], s_probe_rom_hex[1], s_probe_rom_hex[2],
                      s_probe_rom_hex[3]},
        .role_status = CG_ROM_STATUS,
        .output_stage_enabled = ops->output_stage_available(),
        .fan_available = ops->fan_available(),
    };
    size_t len;

    cg_health_registry_beat(CG_PRODUCER_TELEMETRY, now_ms);
    cg_health_registry_eval(now_ms, &health);

    len = cg_telemetry_format(line, sizeof(line), &frame);

    if (len == 0U || len >= sizeof(line)) {
        /* The frame was refused, so no seq was published for it. The counter
         * still advanced, which leaves a gap rather than a duplicate: the
         * backend sees a missing frame instead of two frames claiming to be the
         * same observation. */
        cg_log_error("telem=FORMAT_FAIL seq=%lu len=%u", (unsigned long)frame.seq,
                     (unsigned)len);
        return;
    }
    if (!cg_log_raw_line(line)) {
        cg_log_error("telem=WRITE_FAIL seq=%lu len=%u", (unsigned long)frame.seq,
                     (unsigned)len);
    }
}

static void apply_command(const cg_tec_command_t *command, const cg_tec_inputs_t *in)
{
    switch (command->kind) {
        case CG_TEC_CMD_ARM: {
            const bool ok = cg_tec_arm(&s_ctl, command->arg, in->now_ms);
            log_tec("ARM", ok ? "ARMED" : "REFUSED");
            break;
        }
        case CG_TEC_CMD_START: {
            const uint64_t duration_ms = (uint64_t)command->value * 1000ULL;
            const cg_tec_start_result_t result =
                cg_tec_start(&s_ctl, in, (uint32_t)duration_ms, CG_TEC_REQUEST_DUTY_PERMILLE);
            log_tec("START", cg_tec_start_result_name(result));
            break;
        }
        case CG_TEC_CMD_STOP:
            cg_tec_stop(&s_ctl, in, "OPERATOR_STOP");
            log_tec("STOP", "STOPPED");
            break;
        case CG_TEC_CMD_ESTOP:
            cg_tec_estop(&s_ctl, in->now_ms, "OPERATOR_ESTOP");
            log_tec("ESTOP", "LATCHED");
            break;
        case CG_TEC_CMD_CLEAR: {
            const bool ok = cg_tec_clear_fault(&s_ctl, command->arg, in);
            log_tec("CLEAR", ok ? "CLEARED" : "REFUSED");
            break;
        }
        case CG_TEC_CMD_RUN:
            (void)snprintf(s_run_id, sizeof(s_run_id), "%s", command->arg);
            log_tec("RUN", s_run_id);
            break;
        case CG_TEC_CMD_PHASE:
            /* Parser accepts only the fixed PHASE tokens (<= 7 chars); the
               explicit precision keeps the copy provably in bounds. */
            (void)snprintf(s_test_phase, sizeof(s_test_phase), "%.15s", command->arg);
            log_tec("PHASE", s_test_phase);
            break;
        case CG_TEC_CMD_STATUS:
            log_tec("STATUS", cg_tec_state_name(s_ctl.state));
            break;
        case CG_TEC_CMD_NONE:
        default:
            cg_log_error("console=EMPTY_COMMAND");
            break;
    }
}

static void commission_task(void *arg)
{
    int64_t next_telem_us = esp_timer_get_time();
    cg_tec_state_t last_state = s_ctl.state;
    bool wdt_subscribed = false;

    (void)arg;

    /* esp_task_wdt_add(NULL) subscribes the *calling* task. It must run
     * here, inside cg_commission, and not from cg_commission_start: app_main
     * returns right after that call, its main task is deleted, and a
     * subscription taken there left the deleted task on the TWDT list while
     * this task's resets found no subscription ("task not found"). */
#if defined(CONFIG_ESP_TASK_WDT_EN) && CONFIG_ESP_TASK_WDT_EN
    if (esp_task_wdt_add(NULL) != ESP_OK) {
        cg_log_error("commission=TASK_WDT_ADD_FAIL");
    } else {
        wdt_subscribed = true;
        cg_log_line("%s %s event=WDT result=SUBSCRIBED task=cg_commission timeout_s=%d",
                    CG_LOG_PREFIX, CG_LOG_TEC, CONFIG_ESP_TASK_WDT_TIMEOUT_S);
    }
#endif

    for (;;) {
        cg_snapshot_t snap;
        cg_tec_inputs_t inputs;
        cg_tec_command_t command;
        const uint64_t now_ms = (uint64_t)(esp_timer_get_time() / 1000);

        cg_snapshot_read(&snap);
        build_inputs(&snap, now_ms, &inputs);
        /* A-W05-01: the control producer beats from its own task context, so a
         * stalled loop is visible by name instead of looking like a controller
         * that simply has nothing to say. */
        cg_health_registry_beat(CG_PRODUCER_CONTROL, now_ms);

        while (xQueueReceive(s_cmd_queue, &command, 0) == pdTRUE) {
            apply_command(&command, &inputs);
        }

        cg_tec_tick(&s_ctl, &inputs);
        if (s_ctl.state != last_state) {
            log_tec("STATE", cg_tec_state_name(s_ctl.state));
            last_state = s_ctl.state;
        }

        if (esp_timer_get_time() >= next_telem_us) {
            emit_telemetry(now_ms, &snap);
            next_telem_us += (int64_t)CG_TELEMETRY_PERIOD_MS * 1000LL;
            if (next_telem_us <= esp_timer_get_time()) {
                next_telem_us = esp_timer_get_time() + (int64_t)CG_TELEMETRY_PERIOD_MS * 1000LL;
            }
        }

        if (wdt_subscribed && esp_task_wdt_reset() != ESP_OK) {
            cg_log_error("commission=TASK_WDT_RESET_FAIL");
        }

        TickType_t ticks = pdMS_TO_TICKS(CG_TEC_TICK_MS);
        vTaskDelay(ticks > 0 ? ticks : 1);
    }
}

void cg_commission_start(const char *boot_id, uint32_t boot_count)
{
    char token[CG_TEC_TOKEN_LEN];
    int unresolved;
    uint64_t now_ms;

    (void)snprintf(s_boot_id, sizeof(s_boot_id), "%s", boot_id != NULL ? boot_id : "UNKNOWN");
    s_boot_count = boot_count;
    render_probe_identity();
    make_token(token);
    now_ms = (uint64_t)(esp_timer_get_time() / 1000);

    /* A-W05-02: the identity block the backend keys on, printed once per boot so
     * a capture that never reached a telemetry line still carries the device
     * identity and the calibration state. calibration_id is UNRECORDED until a
     * calibration bundle exists; it is not a placeholder that means "calibrated". */
    cg_log_line(
        "%s %s event=IDENTITY device_id=%s boot_id=%s boot_count=%lu firmware_version=%s "
        "hardware_config_id=%s calibration_id=%s schema=%d seq_start=1",
        CG_LOG_PREFIX, CG_LOG_BOOT, CG_DEVICE_ID, s_boot_id, (unsigned long)s_boot_count,
        CG_FIRMWARE_VERSION, CG_HARDWARE_CONFIG_ID, CG_CALIBRATION_ID,
        CG_TELEMETRY_SCHEMA_VERSION);

    cg_tec_control_init(&s_ctl, &cg_tec_limits_shipped, cg_tec_hw_ops(), token, now_ms,
                        CG_TEC_ARM_TTL_MS, CG_TEC_HEARTBEAT_TIMEOUT_MS, CG_TEC_COOLDOWN_MS,
                        CG_TEC_STALE_THERMAL_MS, CG_TEC_STALE_POWER_MS);

    cg_log_line("%s %s token=%s ttl_ms=%d clear_requires_token=1", CG_LOG_PREFIX, CG_LOG_AUTH,
                token, CG_TEC_ARM_TTL_MS);

    for (int i = 0; i < CG_LIMIT_COUNT; i++) {
        const cg_limit_t *limit = cg_tec_limit(&cg_tec_limits_shipped, (cg_limit_id_t)i);
        cg_log_line("%s %s name=%s state=%s value=%.4f unit=%s source=%s", CG_LOG_PREFIX,
                    CG_LOG_TEC_LIMIT, limit->name, cg_tec_limit_state_name(limit->state),
                    (double)limit->value, limit->unit, limit->source);
    }

    unresolved = cg_tec_limits_unresolved(&cg_tec_limits_shipped);
    log_tec("BOOT", unresolved == 0 ? "LIMITS_RESOLVED" : "LIMITS_UNRESOLVED");

    s_cmd_queue = xQueueCreate(CG_COMMAND_QUEUE_LEN, sizeof(cg_tec_command_t));
    if (s_cmd_queue == NULL) {
        cg_log_error("commission=QUEUE_CREATE_FAIL console=disabled");
        return;
    }
    if (!cg_console_start(s_cmd_queue)) {
        cg_log_error("commission=CONSOLE_DISABLED arming=unavailable");
    }

    (void)xTaskCreate(commission_task, "cg_commission", CG_COMMISSION_STACK_WORDS, NULL,
                      CG_COMMISSION_TASK_PRIORITY, NULL);
}
