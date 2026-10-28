/*
 * ColdGuard firmware - W03 power/PZEM + W02 sensor foundation application
 * (Member A).
 *
 * What this application does (and only this):
 *   - forces the cooling actuator inputs OFF at boot (docs/01 11.8);
 *   - prints the log banner, boot identity and the frozen ROM->role map;
 *   - enumerates the four frozen ROMs once per boot (A-W02-02/03);
 *   - runs a deadline-paced ~1 Hz shared-conversion DS18B20 loop and
 *     prints one SAMPLE line per real observation time (A-W02-04/05);
 *   - samples the MC-38 raw level, timestamps every raw edge and prints a
 *     committed DOOR_STATE line after the debounce window (A-W02-07);
 *   - polls the PZEM-017 over Modbus RTU read-only and prints one PZEM line
 *     per real poll, plus the boot config/range readback (A-W03-03/04).
 *
 * Not implemented in W03 on purpose: MQTT/telemetry publishing, cooling
 * control, PWM generation, command handling. Those belong to W04+ and
 * adding them here would create unverified claims. BME280 stays a pending
 * physical test (A-W02-06).
 */
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_random.h"
#include "esp_timer.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "coldguard_config.h"
#include "cg_door.h"
#include "cg_ds18b20.h"
#include "cg_log.h"
#include "cg_power.h"
#include "cg_rom_map.h"
#include "cg_safety.h"

/* Shared door state: the door task mutates it, the sensor task only reads
 * the debounced raw level for the SAMPLE line. The read is a plain int
 * read, so a torn value is impossible on this target. */
static cg_door_t s_door;

static uint32_t boot_count_next(void)
{
    nvs_handle_t handle;
    uint32_t count = 0;

    if (nvs_open(CG_NVS_NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) {
        cg_log_error("nvs=OPEN_FAIL boot_count=unknown");
        return 0;
    }

    if (nvs_get_u32(handle, CG_NVS_KEY_BOOT_COUNT, &count) != ESP_OK) {
        count = 0; /* first boot on this board, or the namespace was erased */
    }
    count++;

    if (nvs_set_u32(handle, CG_NVS_KEY_BOOT_COUNT, count) != ESP_OK) {
        cg_log_error("nvs=WRITE_FAIL key=boot_count");
    }
    (void)nvs_commit(handle);
    nvs_close(handle);

    return count;
}

static void door_task(void *arg)
{
    bool edge = false;
    bool commit = false;
    int level = 0;

    (void)arg;

    cg_door_init(&s_door);
    cg_log_door_polarity(CG_DOOR_POLARITY_CONFIRMED == 1, CG_DOOR_RAW_OPEN_LEVEL);

    while (true) {
        uint64_t now_us = (uint64_t)esp_timer_get_time();

        cg_door_poll(&s_door, now_us, &edge, &level, &commit);

        if (edge) {
            cg_log_line("%s %s uptime_us=%lld raw=%d", CG_LOG_PREFIX, CG_LOG_DOOR_EDGE,
                        (long long)now_us, level);
        }
        if (commit) {
            cg_log_line(
                "%s %s uptime_ms=%lld raw=%d state=%s transitions=%lu cycles=%lu discarded=%lu",
                CG_LOG_PREFIX, CG_LOG_DOOR_STATE, (long long)(now_us / 1000ULL),
                s_door.raw_committed, cg_door_state_name(cg_door_state(&s_door)),
                (unsigned long)s_door.transitions, (unsigned long)s_door.cycles,
                (unsigned long)s_door.discarded_edges);
        }

        /* pdMS_TO_TICKS rounds down: at a 100 Hz FreeRTOS tick a 5 ms poll
         * becomes 0 ticks, and vTaskDelay(0) only yields to equal-priority
         * tasks, so this priority-6 task would never let IDLE0 or the
         * priority-5 sensor task run (observed on real hardware: task WDT
         * spam on IDLE0 and zero #CG SAMPLE lines). One tick is the
         * minimum real sleep; the door state machine measures debounce in
         * esp_timer microseconds, so a coarser poll only widens edge-time
         * granularity, never correctness. */
        TickType_t wait_ticks = pdMS_TO_TICKS(CG_DOOR_POLL_MS);
        vTaskDelay(wait_ticks > 0 ? wait_ticks : 1);
    }
}

static void sensor_task(void *arg)
{
    cg_thermal_snapshot_t snap;
    cg_thermal_quality_t last_quality = CG_QUALITY_INVALID;
    uint8_t last_status[CG_ROLE_COUNT] = {0};
    bool have_quality = false;
    uint32_t seq = 0;
    int64_t next_deadline_us;

    (void)arg;

    memset(&snap, 0, sizeof(snap));
    cg_ds18b20_enumerate(&snap);

    for (size_t i = 0; i < cg_rom_map_size(); i++) {
        const cg_rom_entry_t *entry = &cg_rom_map_entries()[i];
        last_status[entry->role] = snap.probe[entry->role].status;
    }

    next_deadline_us = esp_timer_get_time();

    while (true) {
        char t1[16];
        char t2[16];
        char t3[16];
        char sp[16];
        int64_t now_us;

        if (!cg_ds18b20_convert_all()) {
            cg_log_error("ds18b20=CONVERT_ALL_NO_PRESENCE");
        }

        /* 12-bit conversion: 750 ms worst case. This wait is the real
         * conversion time, not a fake sampling delay. */
        vTaskDelay(pdMS_TO_TICKS(CG_DS18B20_CONVERSION_MS));

        cg_ds18b20_read_all(&snap);
        seq++;

        for (size_t i = 0; i < cg_rom_map_size(); i++) {
            const cg_rom_entry_t *entry = &cg_rom_map_entries()[i];
            cg_role_t role = entry->role;
            if (snap.probe[role].status != last_status[role]) {
                cg_log_error("probe_state role=%s status=%d present=%d", entry->name,
                             snap.probe[role].status, snap.probe[role].present ? 1 : 0);
                last_status[role] = snap.probe[role].status;
            }
        }
        if (!have_quality || snap.quality != last_quality) {
            cg_log_error("thermal_quality from=%s to=%s", cg_quality_name(last_quality),
                         cg_quality_name(snap.quality));
            last_quality = snap.quality;
            have_quality = true;
        }

        cg_log_line(
            "%s %s uptime_ms=%lld seq=%lu T1=%s T2=%s T3=%s SPARE=%s t1=%d t2=%d t3=%d "
            "thermal=%s door_raw=%d door=%s",
            CG_LOG_PREFIX, CG_LOG_SAMPLE, (long long)(esp_timer_get_time() / 1000ULL),
            (unsigned long)seq,
            cg_log_temp_or_nan(snap.probe[CG_ROLE_T1].valid, snap.probe[CG_ROLE_T1].celsius, t1,
                               sizeof(t1)),
            cg_log_temp_or_nan(snap.probe[CG_ROLE_T2].valid, snap.probe[CG_ROLE_T2].celsius, t2,
                               sizeof(t2)),
            cg_log_temp_or_nan(snap.probe[CG_ROLE_T3].valid, snap.probe[CG_ROLE_T3].celsius, t3,
                               sizeof(t3)),
            cg_log_temp_or_nan(snap.probe[CG_ROLE_SPARE].valid,
                               snap.probe[CG_ROLE_SPARE].celsius, sp, sizeof(sp)),
            snap.probe[CG_ROLE_T1].valid ? 1 : 0, snap.probe[CG_ROLE_T2].valid ? 1 : 0,
            snap.probe[CG_ROLE_T3].valid ? 1 : 0, cg_quality_name(snap.quality),
            s_door.raw_committed, cg_door_state_name(cg_door_state(&s_door)));

        /* Deadline pacing: the next observation is scheduled one period
         * after the previous deadline, so uptime_ms in the log is the real
         * observation time. If the loop falls behind, the deadline moves
         * to "now" - the firmware never emits a fake 1 Hz duplicate
         * (docs/01 section 6.7). */
        next_deadline_us += (int64_t)CG_SAMPLE_PERIOD_MS * 1000LL;
        now_us = esp_timer_get_time();
        if (next_deadline_us > now_us) {
            int64_t remaining_us = next_deadline_us - now_us;
            TickType_t ticks = pdMS_TO_TICKS((uint32_t)((remaining_us + 999) / 1000));
            vTaskDelay(ticks > 0 ? ticks : 1);
        } else {
            next_deadline_us = now_us;
        }
    }
}

void app_main(void)
{
    char boot_id[9];
    uint32_t boot_count;
    esp_err_t nvs_status;

    cg_log_init();

    /* Safety first: never leave the cooling branch enabled while the rest
     * of the system initializes. */
    cg_safety_force_actuator_off();

    nvs_status = nvs_flash_init();
    if (nvs_status == ESP_ERR_NVS_NO_FREE_PAGES || nvs_status == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        (void)nvs_flash_erase();
        nvs_status = nvs_flash_init();
    }
    if (nvs_status != ESP_OK) {
        cg_log_error("nvs=INIT_FAIL boot_count=unknown");
    }

    cg_log_banner();

    boot_count = boot_count_next();
    (void)snprintf(boot_id, sizeof(boot_id), "%08lx", (unsigned long)esp_random());
    cg_log_boot(boot_id, boot_count);

    if (!cg_rom_map_self_check()) {
        cg_log_error("rom_map=SELF_CHECK_FAIL identity_claims=suspended");
    }

    if (!cg_ds18b20_init()) {
        cg_log_error("ds18b20=INIT_DEGRADED continuing=1");
    }

    /* W03: PZEM observation task (read-only Modbus polling). It has no path
     * to the cooling branch; the actuator stays in the safe state forced
     * above. */
    cg_power_start();

    (void)xTaskCreate(door_task, "cg_door", 3072, NULL, 6, NULL);
    (void)xTaskCreate(sensor_task, "cg_sensor", 4096, NULL, 5, NULL);
}
