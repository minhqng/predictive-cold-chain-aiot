/*
 * ColdGuard firmware - serial log primitives (Member A, W02).
 */
#include "cg_log.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "cg_rom_map.h"
#include "coldguard_config.h"

static SemaphoreHandle_t s_log_mutex;

void cg_log_init(void)
{
    if (s_log_mutex == NULL) {
        s_log_mutex = xSemaphoreCreateMutex();
    }
}

static void log_lock(void)
{
    if (s_log_mutex != NULL) {
        (void)xSemaphoreTake(s_log_mutex, portMAX_DELAY);
    }
}

static void log_unlock(void)
{
    if (s_log_mutex != NULL) {
        (void)xSemaphoreGive(s_log_mutex);
    }
}

void cg_log_line(const char *fmt, ...)
{
    va_list args;
    char line[256];

    va_start(args, fmt);
    int n = vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);

    if (n < 0) {
        return;
    }
    if ((size_t)n >= sizeof(line)) {
        /* A truncated machine line can still look well-formed to a parser,
         * so it is dropped and replaced by a fixed error line. */
        static const char overflow_line[] = CG_LOG_PREFIX " " CG_LOG_ERROR " msg=log_line_overflow\n";
        log_lock();
        (void)fwrite(overflow_line, 1, sizeof(overflow_line) - 1, stdout);
        (void)fflush(stdout);
        log_unlock();
        return;
    }

    log_lock();
    (void)fwrite(line, 1, (size_t)n, stdout);
    (void)fputc('\n', stdout);
    (void)fflush(stdout);
    log_unlock();
}

const char *cg_log_rom_hex(const uint8_t rom[8], char out[17])
{
    static const char hex[] = "0123456789ABCDEF";
    for (int i = 0; i < 8; i++) {
        out[i * 2] = hex[(rom[i] >> 4) & 0x0F];
        out[i * 2 + 1] = hex[rom[i] & 0x0F];
    }
    out[16] = '\0';
    return out;
}

const char *cg_log_temp_or_nan(bool valid, float celsius, char *buf, size_t buf_len)
{
    if (!valid) {
        (void)snprintf(buf, buf_len, "%s", CG_INVALID_VALUE_TOKEN);
    } else {
        (void)snprintf(buf, buf_len, "%.4f", (double)celsius);
    }
    return buf;
}

void cg_log_banner(void)
{
    cg_log_line("%s %s v=%d fw=%s hw=%s device=%s pin_map=%d grammar=%d",
                CG_LOG_PREFIX, CG_LOG_BANNER, CG_LOG_GRAMMAR_VERSION,
                CG_FIRMWARE_VERSION, CG_HARDWARE_CONFIG_ID, CG_DEVICE_ID,
                CG_PIN_MAP_VERSION, CG_LOG_GRAMMAR_VERSION);
}

void cg_log_safety_actuator_off(void)
{
    cg_log_line("%s %s actuator=OFF pwm=%d en=%d", CG_LOG_PREFIX, CG_LOG_SAFETY,
                CG_PIN_IBT2_COOLING_PWM, CG_PIN_IBT2_ENABLE);
}

void cg_log_boot(const char *boot_id, uint32_t boot_count)
{
    cg_log_line("%s %s boot_id=%s boot_count=%lu", CG_LOG_PREFIX, CG_LOG_BOOT,
                boot_id, (unsigned long)boot_count);
}

void cg_log_rom(const char *role, const uint8_t rom[8], bool present, const char *status)
{
    char hex[17];
    cg_log_line("%s %s role=%s rom=%s present=%d status=%s", CG_LOG_PREFIX, CG_LOG_ROM,
                role, cg_log_rom_hex(rom, hex), present ? 1 : 0, status);
}

void cg_log_rom_summary(int required_present, int known_present)
{
    /* known = every role in the frozen map. W02 has no bus scan, so there
     * is no "unknown devices" counter to print - an unmeasurable number
     * would look like a measurement. */
    cg_log_line("%s %s required_present=%d/3 known=%d known_present=%d",
                CG_LOG_PREFIX, CG_LOG_ROMS, required_present, CG_ROLE_COUNT,
                known_present);
}

void cg_log_door_polarity(bool confirmed, int raw_open_level)
{
    cg_log_line("%s %s state=%s raw_open_level=%d", CG_LOG_PREFIX, CG_LOG_DOOR_POLARITY,
                confirmed ? "CONFIRMED" : "UNVERIFIED", raw_open_level);
}

void cg_log_error(const char *fmt, ...)
{
    va_list args;
    char body[192];

    va_start(args, fmt);
    int n = vsnprintf(body, sizeof(body), fmt, args);
    va_end(args);
    if (n < 0) {
        return;
    }
    cg_log_line("%s %s msg=%s", CG_LOG_PREFIX, CG_LOG_ERROR, body);
}
