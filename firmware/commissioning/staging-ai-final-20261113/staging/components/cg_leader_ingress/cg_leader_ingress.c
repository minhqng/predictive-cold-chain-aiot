/*
 * ColdGuard firmware - Leader ingress ESP-IDF shell.
 *
 * Hosts the Leader reader task and the two delivered-module interpositions
 * (linker wraps; the delivered member sources are not edited):
 *
 * - `cg_console_start`: the member function installs the console driver and
 *   starts the member reader task. The Leader version keeps the identical
 *   driver install and the identical byte state machine, raises the line
 *   capacity so a canonical record physically fits
 *   (CG_CONSOLE_LINE_MAX=96 refuses CG_COMMAND_RECORD_MAX-sized records),
 *   and routes `#CG CMD ` records to the Leader netcmd handler. Every other
 *   line follows the delivered member path exactly (cg_tec_command_parse
 *   into the same command queue, same PARSE_FAIL/QUEUE_FULL evidence
 *   lines), which is why this shell is the only file in the component that
 *   touches the scheduler or the drivers.
 * - `cg_log_raw_line`: pass-through observation. Every TELEM frame the
 *   device emits replaces the observed command world; nothing is rewritten
 *   or suppressed.
 *
 * The fault-injection grammar rides the delivered console reader, so a test
 * build (CG_FAULT_INJECTION=1) gets the delivered console back unchanged -
 * the ingress steps aside there by construction, never bypasses it.
 */
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include "sdkconfig.h"
#include "esp_err.h"

#ifdef CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#include "driver/usb_serial_jtag.h"
#endif
#include "driver/uart.h"
#include "esp_random.h"
#include "esp_timer.h"

#include "esp_app_desc.h"
#include "esp_ota_ops.h"
#include "esp_partition.h"

#include "cg_leader_ingress.h"
#include "cg_leader_tec_hw.h"
#include "cg_command.h"
#include "cg_console.h"
#include "cg_door.h"
#include "cg_log.h"
#include "cg_snapshot.h"
#include "cg_tec_command.h"
#include "cg_tec_limits.h"
#include "cg_tec_platform.h"
#include "coldguard_config.h"

#ifndef CG_FAULT_INJECTION
#define CG_FAULT_INJECTION 0
#endif

#if CONFIG_CG_LEADER_NETCMD && CG_FAULT_INJECTION
#define CG_LEADER_INGRESS_ACTIVE 0
#else
#define CG_LEADER_INGRESS_ACTIVE CONFIG_CG_LEADER_NETCMD
#endif

extern bool __real_cg_console_start(QueueHandle_t queue);
extern bool __real_cg_log_raw_line(const char *line);
extern void __real_cg_door_attest_polarity(cg_door_t *door);
extern cg_door_state_t __real_cg_door_state(const cg_door_t *door);

/* Both committed raw levels seen on this boot, attest not yet consumed.
 * Lives only until the attestation fires; a reset clears it with everything
 * else static. */
static bool s_door_seen_levels[2];
static bool s_door_attest_done;

static bool cg_leader_door_evidence_live(void)
{
    return s_door_seen_levels[0] && s_door_seen_levels[1]
           && !s_door_attest_done;
}

#if CG_LEADER_INGRESS_ACTIVE

#define CG_LEADER_RX_CHUNK 32
#define CG_LEADER_UART_RX_BUFFER 512
#define CG_LEADER_CONSOLE_STACK_WORDS 4096
#define CG_LEADER_CONSOLE_TASK_PRIORITY 3

/* The delivered reader task is the device's console. The Leader reader uses
 * the same name family so the evidence stays attributable. */
#define CG_LEADER_CONSOLE_TASK_NAME "cg_lconsole"

static QueueHandle_t s_queue;
static portMUX_TYPE s_world_mux = portMUX_INITIALIZER_UNLOCKED;
static cg_leader_world_t s_world;
/* This boot's synchronization challenge. Generated once with the hardware
 * RNG and advertised on the capability line; only a writer that echoes it
 * (and the current boot id) can anchor host time on this boot. */
static uint32_t s_challenge;
/* Boot identity learned from the device's own BOOT/TELEM lines, for the
 * evidence records. Guarded by s_world_mux, never mixed with the challenge. */
static char s_boot_id[16];
static bool s_boot_id_known;

/* Records the boot id from the device's own BOOT line (the same identity the
 * TELEM frames repeat), so evidence can be correlated before the first
 * TELEM arrives. */
static void note_boot_id(const char *line)
{
    static const char prefix[] = CG_LOG_PREFIX " BOOT boot_id=";
    char id[16];
    size_t len = 0U;
    const char *value;

    if (line == NULL || strncmp(line, prefix, sizeof(prefix) - 1U) != 0) {
        return;
    }
    value = line + sizeof(prefix) - 1U;
    while (len + 1U < sizeof(id) && value[len] != '\0' && value[len] != ' ') {
        id[len] = value[len];
        len++;
    }
    if (len == 0U) {
        return;
    }
    id[len] = '\0';
    portENTER_CRITICAL(&s_world_mux);
    memcpy(s_boot_id, id, len + 1U);
    s_boot_id_known = true;
    portEXIT_CRITICAL(&s_world_mux);
}

/* Takes the world from the device's own published output. A TELEM frame is
 * a complete view by construction, so `s_world` always holds the values of
 * (at least) the most recent complete frame - never a merge of partial
 * lines, never a value a request could have seeded. */
static void note_line(const char *line)
{
    cg_leader_world_t view;
    bool complete = false;

    /* Leader MC-38 commissioning evidence, from the device's own published
     * stream (same trust slice as the sync challenge): mark each committed
     * raw level seen on THIS boot. A door sensor that has physically shown
     * both polarities within one boot is the physical open/close observation
     * Member A's D25 contract wants recorded before the delivered
     * raw->semantic mapping may report OPEN/CLOSED. Statics live for the
     * boot only, so every reset starts unattested again (delivered rule). */
    if (line != NULL) {
        note_boot_id(line);
        if (strstr(line, " door_raw=0") != NULL) {
            s_door_seen_levels[0] = true;
        } else if (strstr(line, " door_raw=1") != NULL) {
            s_door_seen_levels[1] = true;
        }
    }

    cg_leader_world_init(&view);
    if (!cg_leader_world_observe_line(line, &view, &complete)) {
        return;
    }
    if (!complete) {
        return;
    }
    portENTER_CRITICAL(&s_world_mux);
    s_world = view;
    /* A complete TELEM view also carries this boot's identity; keep the
     * evidence correlation on the same observed source. */
    memcpy(s_boot_id, view.boot_id, sizeof(s_boot_id));
    s_boot_id_known = view.boot_id[0] != '\0';
    portEXIT_CRITICAL(&s_world_mux);
}

/* Copies the current boot id under the existing world lock. */
static bool boot_id_copy(char out[16])
{
    bool known;

    portENTER_CRITICAL(&s_world_mux);
    known = s_boot_id_known;
    if (known) {
        memcpy(out, s_boot_id, sizeof(s_boot_id));
    }
    portEXIT_CRITICAL(&s_world_mux);
    return known;
}

/* The delivered build_cmd_context reads the same sources: the shipped limit
 * table and platform ops, one snapshot read for input validity, and the
 * counter/state/fault trio the frame already publishes. */
static void snapshot_world(cg_leader_world_t *out)
{
    const cg_tec_hw_ops_t *ops = cg_tec_hw_ops();
    /* The shipped table stays all-UNRESOLVED (the delivered fail-closed
     * posture). A supervised commissioning build opts in through the
     * recorded Kconfig flag: the member control core receives the
     * owner-proposed single-session limit set via the Leader
     * cg_tec_control_init interposition, so this gate reads the same
     * decision the controller will actually run with - the flag IS that
     * record (owner-proposed envelope 2026-11-13, a session value, never a
     * certified plant rating). */
    const cg_tec_limit_table_t *effective = cg_leader_tec_effective_limits();
    const bool limits_resolved =
#if defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS) \
    && CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS
        effective != NULL;
#else
        effective != NULL && cg_tec_limits_all_resolved(effective);
#endif
    /* The admission ceiling is the ACTUAL effective table handed to the
     * member controller, never a local literal. It is 0 (fail closed) until
     * the controller has been initialized with that table. */
    const cg_limit_t *duty_limit = cg_tec_limit(effective, CG_LIMIT_DUTY_MAX_PERMILLE);
    cg_snapshot_t snap;

    portENTER_CRITICAL(&s_world_mux);
    *out = s_world;
    portEXIT_CRITICAL(&s_world_mux);

    out->output_stage_enabled = ops->output_stage_available();
    out->limits_resolved = limits_resolved;
    out->allowed_duty_max_permille =
        limits_resolved && duty_limit != NULL && duty_limit->state == CG_LIMIT_RESOLVED
        ? (uint32_t)duty_limit->value : 0U;
    out->local_safety_permits = ops->output_stage_available() && limits_resolved;

    cg_snapshot_read(&snap);
    out->inputs_sufficiently_valid = snap.thermal_observed && snap.thermal_valid;
    out->uptime_ms = (uint64_t)(esp_timer_get_time() / 1000);
}

/* ---- Passive runtime image/limit evidence -------------------------------
 * Read-only records at the capability repetition cadence. Nothing here
 * actuates, authenticates or changes a command decision; the only shared
 * state is the boot id copy under s_world_mux.
 *
 * The three image digests are deliberately distinct and never presented as
 * equal:
 *   app_elf_sha256       - from esp_app_get_description(), the linked ELF.
 *   partition_image_sha256 - esp_partition_get_sha256() over the running app
 *                          partition. Per esp_partition.h, an app image with
 *                          an appended SHA returns that verified digest of
 *                          the app-image content (the appended digest and
 *                          partition padding are not part of that content);
 *                          without an appended SHA it is the hash of the
 *                          app-image bytes.
 *   whole_bin_sha256     - the flashed .bin file digest; not computed at
 *                          runtime, reported as NOT_COMPUTED.
 * Hashing runs once per boot from cg_console_start(), before the READY line
 * and before the reader task exists - never inside the reader task. */
typedef struct {
    bool elf_ok;
    char elf_sha256[65];
    bool partition_found;
    char partition_label[17];
    uint32_t partition_offset;
    char partition_sha256[65];
    char partition_sha_status[24];
} leader_image_evidence_t;

static leader_image_evidence_t s_image;

static void hex32(const uint8_t in[32], char out[65])
{
    static const char digits[] = "0123456789abcdef";

    for (size_t i = 0U; i < 32U; i++) {
        out[i * 2U] = digits[in[i] >> 4];
        out[i * 2U + 1U] = digits[in[i] & 0x0FU];
    }
    out[64] = '\0';
}

static void image_evidence_build(void)
{
    const esp_app_desc_t *desc = esp_app_get_description();
    const esp_partition_t *running = esp_ota_get_running_partition();

    if (desc != NULL) {
        hex32(desc->app_elf_sha256, s_image.elf_sha256);
        s_image.elf_ok = true;
    }
    if (running != NULL) {
        uint8_t digest[32];
        const esp_err_t err = esp_partition_get_sha256(running, digest);

        s_image.partition_found = true;
        s_image.partition_offset = running->address;
        (void)snprintf(s_image.partition_label,
                       sizeof(s_image.partition_label), "%s", running->label);
        if (err == ESP_OK) {
            hex32(digest, s_image.partition_sha256);
            (void)snprintf(s_image.partition_sha_status,
                           sizeof(s_image.partition_sha_status), "OK");
        } else {
            /* A failed hash must never look like a 64-hex digest. */
            (void)snprintf(s_image.partition_sha256,
                           sizeof(s_image.partition_sha256), "none");
            (void)snprintf(s_image.partition_sha_status,
                           sizeof(s_image.partition_sha_status), "%s",
                           esp_err_to_name(err));
        }
    } else {
        (void)snprintf(s_image.partition_sha_status,
                       sizeof(s_image.partition_sha_status),
                       "PARTITION_UNAVAILABLE");
    }
}

static void emit_elf_evidence(const char *boot_id)
{
    if (s_image.elf_ok) {
        cg_log_line("%s LEADER_FW boot_id=%s app_elf_sha256=%s "
                    "app_elf_sha256_status=OK whole_bin_sha256=NOT_COMPUTED",
                    CG_LOG_PREFIX, boot_id, s_image.elf_sha256);
    } else {
        cg_log_line("%s LEADER_FW boot_id=%s app_elf_sha256=none "
                    "app_elf_sha256_status=UNAVAILABLE "
                    "whole_bin_sha256=NOT_COMPUTED",
                    CG_LOG_PREFIX, boot_id);
    }
}

static void emit_partition_evidence(const char *boot_id)
{
    if (s_image.partition_found) {
        cg_log_line("%s LEADER_FW boot_id=%s partition=%s "
                    "partition_offset=0x%08x partition_image_sha256=%s "
                    "partition_sha256_status=%s",
                    CG_LOG_PREFIX, boot_id, s_image.partition_label,
                    (unsigned)s_image.partition_offset,
                    s_image.partition_sha256, s_image.partition_sha_status);
    } else {
        cg_log_line("%s LEADER_FW boot_id=%s partition=NOT_FOUND "
                    "partition_image_sha256=none "
                    "partition_sha256_status=%s",
                    CG_LOG_PREFIX, boot_id, s_image.partition_sha_status);
    }
}

static void emit_config_evidence(const char *boot_id)
{
    const cg_tec_limit_table_t *limits = cg_leader_tec_effective_limits();
    const cg_limit_t *duty = cg_tec_limit(limits, CG_LIMIT_DUTY_MAX_PERMILLE);
    char duty_text[16];

    if (limits == NULL) {
        (void)snprintf(duty_text, sizeof(duty_text), "UNINITIALIZED");
    } else if (duty != NULL && duty->state == CG_LIMIT_RESOLVED) {
        (void)snprintf(duty_text, sizeof(duty_text), "%u",
                       (unsigned)duty->value);
    } else {
        (void)snprintf(duty_text, sizeof(duty_text), "UNRESOLVED");
    }
    cg_log_line("%s LEADER_CONFIG boot_id=%s requested_duty_permille=%s "
                "compiled_supervised_limits=%d compiled_leader_hw=%d "
                "compiled_output_stage=%d compiled_hw_gates=%d "
                "compiled_actuator_enable=%d cold_probe_required=%d "
                "continuous_allowed=%d",
                CG_LOG_PREFIX, boot_id, duty_text,
#if defined(CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS) \
    && CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS
                1,
#else
                0,
#endif
#if defined(CONFIG_CG_LEADER_TEC_HW) && CONFIG_CG_LEADER_TEC_HW
                1,
#else
                0,
#endif
                (int)(CG_TEC_OUTPUT_STAGE_ENABLED == 1),
                (int)(CG_TEC_HARDWARE_GATES_VERIFIED == 1),
                (int)(CG_ACTUATOR_ENABLE_ALLOWED == 1),
                cg_leader_tec_cold_probe_required() ? 1 : 0,
                cg_leader_tec_continuous_allowed() ? 1 : 0);
}

/* One evidence cycle: ELF, partition, config, limit summary, then one record
 * per limit entry. Returns the step for the next iteration; DONE ends the
 * cycle. Exactly one record is emitted per call. */
#define CG_LEADER_EVIDENCE_LIMIT_BASE 4
#define CG_LEADER_EVIDENCE_DONE (CG_LEADER_EVIDENCE_LIMIT_BASE + CG_LIMIT_COUNT)

static int emit_evidence_record(const char *boot_id, int step)
{
    if (step == 0) {
        emit_elf_evidence(boot_id);
        return 1;
    }
    if (step == 1) {
        emit_partition_evidence(boot_id);
        return 2;
    }
    if (step == 2) {
        emit_config_evidence(boot_id);
        return 3;
    }
    if (step == 3) {
        const cg_tec_limit_table_t *limits = cg_leader_tec_effective_limits();
        const char *source = cg_leader_tec_effective_limits_source();

        if (source == NULL) {
            source = "UNKNOWN";
        }
        if (limits == NULL) {
            cg_log_line("%s LEADER_LIMIT boot_id=%s table=UNINITIALIZED "
                        "limits_ready=0", CG_LOG_PREFIX, boot_id);
            return CG_LEADER_EVIDENCE_DONE;
        }
        cg_log_line("%s LEADER_LIMIT boot_id=%s table=%s limits_ready=1 "
                    "resolved=%d/%d",
                    CG_LOG_PREFIX, boot_id, source,
                    CG_LIMIT_COUNT - cg_tec_limits_unresolved(limits),
                    CG_LIMIT_COUNT);
        return CG_LEADER_EVIDENCE_LIMIT_BASE;
    }
    {
        const cg_tec_limit_table_t *limits = cg_leader_tec_effective_limits();
        const cg_limit_t *entry =
            cg_tec_limit(limits, (cg_limit_id_t)(step - CG_LEADER_EVIDENCE_LIMIT_BASE));

        if (entry == NULL) {
            return CG_LEADER_EVIDENCE_DONE;
        }
        if (entry->state == CG_LIMIT_RESOLVED) {
            cg_log_line("%s LEADER_LIMIT boot_id=%s index=%d/%d name=%s "
                        "state=%s value=%.1f unit=%s",
                        CG_LOG_PREFIX, boot_id, step - CG_LEADER_EVIDENCE_LIMIT_BASE + 1,
                        CG_LIMIT_COUNT, entry->name,
                        cg_tec_limit_state_name(entry->state),
                        (double)entry->value, entry->unit);
        } else {
            cg_log_line("%s LEADER_LIMIT boot_id=%s index=%d/%d name=%s "
                        "state=%s value=nan unit=%s",
                        CG_LOG_PREFIX, boot_id, step - CG_LEADER_EVIDENCE_LIMIT_BASE + 1,
                        CG_LIMIT_COUNT, entry->name,
                        cg_tec_limit_state_name(entry->state), entry->unit);
        }
        return step + 1;
    }
}

/* Delivered reader task parity (cg_console.c): same chunking, same polling,
 * same byte state machine - the only deltas are the line capacity and the
 * envelope dispatch, both the reason this component exists. */
static void handle_line(const char *line)
{
    cg_tec_command_t command;
    const char *error = "OK";

    if (cg_leader_line_is_sync(line)) {
        cg_leader_world_t world;

        snapshot_world(&world);
        cg_leader_sync_handle(line + 9, &world, s_challenge);
        return;
    }
    if (cg_leader_line_is_envelope(line)) {
        cg_leader_world_t world;

        snapshot_world(&world);
        cg_leader_netcmd_handle(line + CG_LEADER_NETCMD_PREFIX_LEN, &world);
        return;
    }
    /* Everything that is not a canonical envelope keeps the delivered
     * member dispatch: parse with the delivered grammar, post to the same
     * queue the commissioning task drains, same evidence lines on failure. */
    if (!cg_tec_command_parse(line, &command, &error)) {
        cg_log_error("console=PARSE_FAIL error=%s", error);
        return;
    }
    if (xQueueSend(s_queue, &command, 0) != pdTRUE) {
        cg_log_error("console=QUEUE_FULL command=%s", cg_tec_command_name(command.kind));
    }
}

static void leader_console_task(void *arg)
{
    uint8_t chunk[CG_LEADER_RX_CHUNK];
    char line[CG_LEADER_LINE_MAX];
    size_t len = 0U;
    bool overflow = false;
    int64_t last_capability_ms = esp_timer_get_time() / 1000;
    int64_t next_evidence_ms = 0;
    int evidence_step = 0;

    (void)arg;

    for (;;) {
        const int received =
#ifdef CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
            usb_serial_jtag_read_bytes(chunk, sizeof(chunk), pdMS_TO_TICKS(50));
#else
            uart_read_bytes(UART_NUM_0, chunk, sizeof(chunk), pdMS_TO_TICKS(50));
#endif
        /* Re-advertise this boot's challenge so a gateway that starts or
         * reconnects later than the boot can still learn it (and restart
         * its sync loop) - a boot-time-only line leaves late readers
         * permanently unsynchronized. */
        const int64_t now_ms = esp_timer_get_time() / 1000;
        if (now_ms - last_capability_ms >= (int64_t)CG_LEADER_CAPABILITY_REPEAT_MS) {
            cg_log_line("%s %s status=READY transport=%s line_max=%d record_max=%d challenge=%08lx",
                        CG_LOG_PREFIX, CG_LEADER_NETCMD_LOG,
#ifdef CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
                        "USB_SERIAL_JTAG",
#else
                        "UART0",
#endif
                        CG_LEADER_LINE_MAX, CG_COMMAND_RECORD_MAX,
                        (unsigned long)s_challenge);
            last_capability_ms = now_ms;
        }
        /* Consume everything already received before writing diagnostics, so
         * an evidence line can never delay an inbound command record. */
        for (int i = 0; i < received; i++) {
            const char c = (char)chunk[i];
            if (c == '\r') {
                continue;
            }
            if (c == '\n') {
                if (overflow) {
                    cg_log_error("console=LINE_TOO_LONG discarded=1");
                } else if (len > 0U) {
                    line[len] = '\0';
                    handle_line(line);
                }
                len = 0U;
                overflow = false;
                continue;
            }
            if (c == '\b' || c == 0x7F) {
                if (len > 0U) {
                    len--;
                }
                continue;
            }
            if (c < 0x20 || c > 0x7E) {
                continue;
            }
            if (len + 1U >= sizeof(line)) {
                overflow = true;
                len = 0U;
                continue;
            }
            line[len++] = c;
        }
        /* One bounded evidence record per iteration, after any received
         * bytes. Stops are paced: one cycle per capability repeat, a full
         * cycle is one record per iteration, then a quiet period. The token
         * and challenge never enter these records. An empty read still
         * reaches this block, so evidence does not depend on commands. */
        if (now_ms >= next_evidence_ms) {
            char evidence_boot_id[16];

            if (boot_id_copy(evidence_boot_id)) {
                evidence_step =
                    emit_evidence_record(evidence_boot_id, evidence_step);
                if (evidence_step >= CG_LEADER_EVIDENCE_DONE) {
                    evidence_step = 0;
                    next_evidence_ms =
                        now_ms + (int64_t)CG_LEADER_CAPABILITY_REPEAT_MS;
                }
            } else {
                next_evidence_ms = now_ms + 1000;
            }
        }
    }
}

#endif /* CG_LEADER_INGRESS_ACTIVE */

bool __wrap_cg_log_raw_line(const char *line)
{
#if CG_LEADER_INGRESS_ACTIVE
    note_line(line);
#endif
    return __real_cg_log_raw_line(line);
}

void __wrap_cg_door_attest_polarity(cg_door_t *door)
{
    __real_cg_door_attest_polarity(door);
}

cg_door_state_t __wrap_cg_door_state(const cg_door_t *door)
{
#if CG_LEADER_INGRESS_ACTIVE
    /* D25 runtime attestation: the delivered constant authorizes the
     * raw->semantic mapping, but the state stays unattested until the
     * physical observation is RECORDed for this boot. This Leader hook
     * performs exactly that call once both committed raw levels have
     * physically appeared on the device stream, then hands the original
     * member function the pointer, so the delivered mapping (and its
     * debounce/commit state machine) answers - nothing member-owned is
     * reimplemented here. Without CG_DOOR_POLARITY_CONFIRMED the member
     * function still returns UNVERIFIED regardless of the attestation. */
    if (door != NULL && cg_leader_door_evidence_live()) {
        /* The caller passes the app's own non-const static door object; the
         * const on cg_state is the read contract, and casting through
         * uintptr_t keeps that *documented* mutation outside the read path
         * while silencing the discarded-qualifiers error. */
        uintptr_t door_address = (uintptr_t)door;
        __real_cg_door_attest_polarity((cg_door_t *)door_address);
        s_door_attest_done = true;
    }
#endif
    return __real_cg_door_state(door);
}

bool __wrap_cg_console_start(QueueHandle_t command_queue)
{
#if !CG_LEADER_INGRESS_ACTIVE
    /* Delivered console, unchanged: test builds and any explicit opt-out
     * keep the member reader as the single console owner. */
    return __real_cg_console_start(command_queue);
#else
    if (command_queue == NULL) {
        return false;
    }
    s_queue = command_queue;

    /* Delivered driver install (cg_console.c), including the tolerance for
     * an already-installed VFS console driver. */
#ifdef CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
    usb_serial_jtag_driver_config_t usj_config = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    esp_err_t usj_err = usb_serial_jtag_driver_install(&usj_config);
    if (usj_err != ESP_OK && usj_err != ESP_ERR_INVALID_STATE) {
        cg_log_error("console=USJ_INSTALL_FAIL commands=disabled err=%s",
                     esp_err_to_name(usj_err));
        return false;
    }
#else
    uart_config_t config = {
        .baud_rate = CG_CONSOLE_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    if (uart_driver_install(UART_NUM_0, CG_LEADER_UART_RX_BUFFER, 0, 0, NULL, 0) != ESP_OK) {
        cg_log_error("console=UART_INSTALL_FAIL commands=disabled");
        return false;
    }
    if (uart_param_config(UART_NUM_0, &config) != ESP_OK) {
        cg_log_error("console=UART_CONFIG_FAIL commands=disabled");
        return false;
    }
#endif

    cg_leader_netcmd_store_init();
    cg_leader_world_init(&s_world);
    s_challenge = (uint32_t)esp_random();

    /* Cache the image identity once, before READY and before the reader task
     * exists: the partition hash never runs in the reader, so it cannot
     * delay inbound command bytes. This runs on the app_main task, which is
     * not subscribed to the task watchdog (commission_task subscribes only
     * when it starts, after this call), so the one startup hash read does
     * not hold a watchdog subscription. */
    image_evidence_build();

    /* Capability advertisement in the delivered log grammar. The gateway's
     * leader-diag mirror publishes this frame, so the operator can verify
     * envelope readiness from the boot record before any downlink session.
     * This boot's challenge rides the same line: only a writer that echoes
     * it back (with the boot id its own frames carry) can anchor host
     * time - a bare serial write anchors nothing. */
    cg_log_line("%s %s status=READY transport=%s line_max=%d record_max=%d challenge=%08lx",
                CG_LOG_PREFIX, CG_LEADER_NETCMD_LOG,
#ifdef CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
                "USB_SERIAL_JTAG",
#else
                "UART0",
#endif
                CG_LEADER_LINE_MAX, CG_COMMAND_RECORD_MAX,
                (unsigned long)s_challenge);

    if (xTaskCreate(leader_console_task, CG_LEADER_CONSOLE_TASK_NAME,
                    CG_LEADER_CONSOLE_STACK_WORDS, NULL,
                    CG_LEADER_CONSOLE_TASK_PRIORITY, NULL) != pdPASS) {
        cg_log_error("console=TASK_CREATE_FAIL commands=disabled");
        return false;
    }
    return true;
#endif
}
