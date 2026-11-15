/*
 * ColdGuard firmware - W04 TEC commissioning + W03 power/PZEM + W02 sensors
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
 *     per real poll, plus the boot config/range readback (A-W03-03/04);
 *   - runs the W04 TEC commissioning controller: fail-closed state machine,
 *     local-token authorization, fault latch, bounded run duration and the
 *     raw `#CG TELEM` experiment stream. The output stage is compiled out,
 *     so the delivered build cannot energize the branch (docs/06).
 *
 * Not implemented on purpose: MQTT/telemetry publishing, cloud commands and
 * cooling actuation. The BME280 producer is implemented; its physical
 * mounting/self-heating half of A-W02-06 remains an open bench question.
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
#include "cg_bme280.h"
#include "cg_bme280_idf.h"
#include "cg_commission.h"
#include "cg_door.h"
#include "cg_ds18b20.h"
#include "cg_health.h"
#include "cg_log.h"
#include "cg_power.h"
#include "cg_rom_map.h"
#include "cg_safety.h"
#include "cg_snapshot.h"

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

static void bme_task(void *arg)
{
    static cg_bme280_t state;
    static cg_bme280_port_t port;
    static cg_bme280_obs_t obs;
    cg_bme_read_result_t result;
    uint8_t address = 0u;
    int last_state = -1;
    int last_reason = -1;
    uint64_t now_ms;

    (void)arg;

    if (!cg_bme280_idf_open(&port, &address)) {
        cg_log_error("bme280=BUS_INIT_FAIL sda=%d scl=%d", CG_PIN_BME280_SDA,
                     CG_PIN_BME280_SCL);
        vTaskDelete(NULL);
        return;
    }

    cg_bme280_reset(&state);
    cg_log_line("%s %s event=BME280_BUS bus=UP addr=0x%02X sda=%d scl=%d", CG_LOG_PREFIX,
                CG_LOG_TEC, (unsigned)address, CG_PIN_BME280_SDA, CG_PIN_BME280_SCL);

    /* One-shot fitted-device diagnostic: emit the raw calibration bytes and one
     * raw measurement context so a host can decode the SAME bytes independently.
     * It configures the same control registers the producer does and publishes
     * nothing; the trim gate is untouched. */
    {
        cg_bme280_diag_t diag;
        char tphex[2 * CG_BME280_CALIB_T_BYTES + 1];
        char hbhex[2 * CG_BME280_CALIB_H_BLOCK + 1];
        cg_bme_read_result_t dr = cg_bme280_collect_diag(&port, &state, &diag);
        int i;
        for (i = 0; i < (int)sizeof(diag.tp); i++) {
            (void)snprintf(&tphex[i * 2], 3, "%02X", diag.tp[i]);
        }
        tphex[sizeof(diag.tp) * 2] = '\0';
        for (i = 0; i < (int)sizeof(diag.hb); i++) {
            (void)snprintf(&hbhex[i * 2], 3, "%02X", diag.hb[i]);
        }
        hbhex[sizeof(diag.hb) * 2] = '\0';
        cg_log_line("%s %s event=BME280_DIAG_CAL result=%s chip=0x%02X tp=%s",
                    CG_LOG_PREFIX, CG_LOG_TEC, cg_bme280_read_result_name(dr),
                    (unsigned)diag.chip_id, tphex);
        cg_log_line("%s %s event=BME280_DIAG_TRIM h1=0x%02X hb=%s t1=%u t2=%d t3=%d "
                    "h1d=%u h2=%d h3=%u h4=%d h5=%d h6=%d",
                    CG_LOG_PREFIX, CG_LOG_TEC, (unsigned)diag.h1, hbhex,
                    (unsigned)diag.calib.dig_t1, (int)diag.calib.dig_t2, (int)diag.calib.dig_t3,
                    (unsigned)diag.calib.dig_h1, (int)diag.calib.dig_h2,
                    (unsigned)diag.calib.dig_h3, (int)diag.calib.dig_h4,
                    (int)diag.calib.dig_h5, (int)diag.calib.dig_h6);
        cg_log_line("%s %s event=BME280_DIAG_OBS result=%s adc_t=%lu adc_h=%lu temp_dc=%ld "
                    "rh_q2210=%lu",
                    CG_LOG_PREFIX, CG_LOG_TEC, cg_bme280_read_result_name(dr),
                    (unsigned long)diag.adc_t, (unsigned long)diag.adc_h,
                    (long)diag.temp_dc, (unsigned long)diag.hum_q2210);
    }

    for (;;) {
        char trim_diag[64];
        result = cg_bme280_sample(&port, &state, &obs);
        cg_bme280_trim_gate(&obs, &result, trim_diag, sizeof(trim_diag));
        now_ms = (uint64_t)(esp_timer_get_time() / 1000);
        cg_snapshot_publish_env(cg_bme280_is_present(&state), obs.valid, obs.temperature_c,
                                obs.relative_humidity_pct, (uint8_t)state.state,
                                (uint8_t)result, address, state.seq, obs.obs_ms);
        cg_health_registry_beat(CG_PRODUCER_BME, now_ms);

        if ((int)state.state != last_state || (int)result != last_reason) {
            cg_log_line("%s %s event=BME280_STATE state=%s reason=%s addr=0x%02X seq=%lu "
                        "t_c=%s rh_pct=%s",
                        CG_LOG_PREFIX, CG_LOG_TEC, cg_bme280_state_name(state.state),
                        cg_bme280_read_result_name(result), (unsigned)address,
                        (unsigned long)state.seq,
                        obs.valid ? "MEASURED" : CG_INVALID_VALUE_TOKEN,
                        obs.valid ? "MEASURED" : CG_INVALID_VALUE_TOKEN);
            last_state = (int)state.state;
            last_reason = (int)result;
        }
        if (trim_diag[0] != '\0') {
            /* The only place the discarded compensated values may appear: an
             * explicitly UNVALIDATED diagnostic, never a published field. */
            cg_log_line("%s %s event=BME280_TRIM_DIAG reason=TRIM_UNCONFIRMED %s",
                        CG_LOG_PREFIX, CG_LOG_TEC, trim_diag);
        }

        vTaskDelay(pdMS_TO_TICKS(CG_SAMPLE_PERIOD_MS));
    }
}

static void door_task(void *arg)
{
    bool edge = false;
    bool commit = false;
    int level = 0;

    (void)arg;

    cg_door_init(&s_door);
    cg_log_door_polarity(cg_door_polarity_attested(&s_door), CG_DOOR_RAW_OPEN_LEVEL);

    while (true) {
        uint64_t now_us = (uint64_t)esp_timer_get_time();

        cg_door_poll(&s_door, now_us, &edge, &level, &commit);
        /* W05: the door publication now carries its own observation time and
         * its edge counters, so the telemetry can state a door age and prove
         * the debounce state machine is still advancing. D25: door-known is the
         * per-boot polarity attestation, not the compile-time constant, so a
         * reset boot reports the door as unattested until it is attested again. */
        cg_snapshot_publish_door(cg_door_polarity_attested(&s_door),
                                 cg_door_state(&s_door) == CG_DOOR_OPEN, s_door.raw_committed,
                                 now_us / 1000ULL, s_door.transitions, s_door.cycles);
        cg_health_registry_beat(CG_PRODUCER_DOOR, now_us / 1000ULL);

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
        {
            const uint64_t obs_ms = (uint64_t)(esp_timer_get_time() / 1000);
            cg_snapshot_publish_thermal(&snap, seq, obs_ms);
            cg_health_registry_beat(CG_PRODUCER_THERMAL, obs_ms);
        }

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
    cg_snapshot_init();

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

    /* A-W05-01: every producer declares its nominal cadence before any task
     * that beats starts, so the registry is never read while uninitialized and
     * a producer that has not beaten yet is reported as NEVER rather than OK.
     * The boot line records which periods the liveness verdicts were judged
     * against - without it, a later `health=LATE` is not reproducible. */
    {
        const uint64_t periods[CG_PRODUCER_COUNT] = {
            CG_HEALTH_THERMAL_PERIOD_MS, CG_HEALTH_BME_PERIOD_MS, CG_HEALTH_DOOR_PERIOD_MS,
            CG_HEALTH_POWER_PERIOD_MS,   CG_HEALTH_TELEMETRY_PERIOD_MS,
            CG_HEALTH_CONTROL_PERIOD_MS,
        };
        cg_health_registry_init(periods);
        cg_log_line(
            "%s %s event=REGISTRY_INIT thermal_ms=%d bme_ms=%d door_ms=%d power_ms=%d "
            "telemetry_ms=%d control_ms=%d door_request_ms=%d",
            CG_LOG_PREFIX, CG_LOG_TEC, CG_HEALTH_THERMAL_PERIOD_MS, CG_HEALTH_BME_PERIOD_MS,
            CG_HEALTH_DOOR_PERIOD_MS, CG_HEALTH_POWER_PERIOD_MS, CG_HEALTH_TELEMETRY_PERIOD_MS,
            CG_HEALTH_CONTROL_PERIOD_MS, CG_DOOR_POLL_MS);
    }

    /* W03: PZEM observation task (read-only Modbus polling). It has no path
     * to the cooling branch; the actuator stays in the safe state forced
     * above. */
    cg_power_start();

    (void)xTaskCreate(door_task, "cg_door", 3072, NULL, 6, NULL);
    (void)xTaskCreate(sensor_task, "cg_sensor", 4096, NULL, 5, NULL);
    (void)xTaskCreate(bme_task, "cg_bme", 4096, NULL, 5, NULL);

    /* W04: controller + local console + raw telemetry. It starts in OFF and
     * cannot energize anything in this build (output stage compiled out). */
    cg_commission_start(boot_id, boot_count);
}
