/*
 * ColdGuard firmware - PZEM-017 polling task and serial log lines
 * (Member A, W03).
 */
#include "cg_power.h"

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_timer.h"

#include "coldguard_config.h"
#include "cg_crc16.h"
#include "cg_log.h"
#include "cg_pzem.h"
#include "cg_rs485.h"

#define CG_POWER_STACK_WORDS 4096
#define CG_POWER_TASK_PRIORITY 4

static uint32_t s_seq;
static uint32_t s_ok_count;
static uint32_t s_fail_count;
static bool s_range_read_done;
static int64_t s_last_range_try_us;

typedef struct {
    cg_pzem_status_t status;
    uint8_t attempts;
    uint8_t rx_len;
    uint8_t rx[CG_PZEM_RX_MAX];
} cg_link_result_t;

static void hex_encode(const uint8_t *data, size_t len, char *out, size_t cap)
{
    static const char digits[] = "0123456789ABCDEF";
    size_t written = 0;

    if (out == NULL || cap == 0U) {
        return;
    }
    for (size_t i = 0; i < len && written + 2U < cap; i++) {
        out[written++] = digits[(data[i] >> 4) & 0x0F];
        out[written++] = digits[data[i] & 0x0F];
    }
    out[written] = '\0';
}

static void framing_string(char *out, size_t cap)
{
    const char parity = (CG_RS485_PARITY == 1) ? 'E' : ((CG_RS485_PARITY == 2) ? 'O' : 'N');
    (void)snprintf(out, cap, "%d%c%d", CG_RS485_DATA_BITS, parity, CG_RS485_STOP_BITS);
}

static void log_config_line(void)
{
    char framing[8];
    framing_string(framing, sizeof(framing));
    cg_log_line("%s %s slave=%d baud=%d framing=%s dir=%s read_only=1", CG_LOG_PREFIX,
                CG_LOG_PZEM_CFG, CG_PZEM_SLAVE_ADDRESS, CG_RS485_BAUD, framing,
                cg_rs485_dir_mode() == CG_RS485_DIR_MANUAL ? "MANUAL" : "AUTO");
}

/* Sends one request and returns the raw link outcome. Bytes received are
 * handed to the protocol parser; the transport does not interpret them. */
static cg_link_result_t link_transaction(const uint8_t *request, size_t request_len,
                                         size_t read_len)
{
    cg_link_result_t result;

    memset(&result, 0, sizeof(result));
    result.status = CG_PZEM_TIMEOUT;

    for (uint8_t attempt = 1; attempt <= CG_PZEM_MAX_ATTEMPTS; attempt++) {
        result.attempts = attempt;
        result.rx_len = 0;

        cg_rs485_flush_input();
        if (!cg_rs485_write(request, request_len)) {
            result.status = CG_PZEM_UART_ERR;
            continue;
        }

        const int received = cg_rs485_read(result.rx, read_len, CG_PZEM_RESPONSE_TIMEOUT_MS);
        if (received < 0) {
            result.status = CG_PZEM_UART_ERR;
            continue;
        }
        if (received == 0) {
            result.status = CG_PZEM_TIMEOUT;
            continue;
        }

        result.rx_len = (uint8_t)received;
        return result; /* the parser classifies the frame */
    }

    return result;
}

static const char *value_token(bool valid, float value, const char *format, char *buffer,
                               size_t buffer_len)
{
    if (!valid) {
        return CG_INVALID_VALUE_TOKEN;
    }
    (void)snprintf(buffer, buffer_len, format, (double)value);
    return buffer;
}

static void poll_once(void)
{
    uint8_t request[8];
    char tx_hex[17];
    char rx_hex[CG_PZEM_RX_MAX * 2 + 1];
    char v_buf[16];
    char i_buf[16];
    char p_buf[16];
    char e_buf[16];
    uint16_t regs[6] = {0};
    cg_pzem_values_t values = {0};
    bool values_valid = false;
    uint8_t exception_code = 0;

    const size_t request_len = cg_pzem_build_read_input(CG_PZEM_SLAVE_ADDRESS, request);
    const cg_link_result_t link = link_transaction(request, request_len, 17U);

    cg_pzem_status_t status = link.status;
    if (link.rx_len > 0) {
        status = cg_pzem_parse_input(link.rx, link.rx_len, CG_PZEM_SLAVE_ADDRESS, regs);
        if (status == CG_PZEM_OK) {
            cg_pzem_decode_input(regs, &values);
            values_valid = true;
        } else if (status == CG_PZEM_EXCEPTION && link.rx_len >= 3U) {
            exception_code = link.rx[2];
        }
    }

    const bool crc_ok =
        link.rx_len >= 4U && cg_crc16_check(link.rx, (size_t)link.rx_len);

    hex_encode(request, request_len, tx_hex, sizeof(tx_hex));
    hex_encode(link.rx, link.rx_len, rx_hex, sizeof(rx_hex));

    s_seq++;
    if (status == CG_PZEM_OK) {
        s_ok_count++;
    } else {
        s_fail_count++;
    }

    cg_log_line(
        "%s %s uptime_ms=%lld seq=%lu status=%s slave=%d v=%s i=%s p=%s e=%s crc_ok=%d "
        "attempts=%d exc=%d ok=%lu fail=%lu tx=%s rx=%s",
        CG_LOG_PREFIX, CG_LOG_PZEM, (long long)(esp_timer_get_time() / 1000LL),
        (unsigned long)s_seq, cg_pzem_status_name(status), CG_PZEM_SLAVE_ADDRESS,
        value_token(values_valid, values.voltage_v, "%.2f", v_buf, sizeof(v_buf)),
        value_token(values_valid, values.current_a, "%.2f", i_buf, sizeof(i_buf)),
        value_token(values_valid, values.power_w, "%.1f", p_buf, sizeof(p_buf)),
        value_token(values_valid, values.energy_wh, "%.0f", e_buf, sizeof(e_buf)), crc_ok ? 1 : 0,
        link.attempts, exception_code, (unsigned long)s_ok_count, (unsigned long)s_fail_count,
        tx_hex, rx_hex);
}

static void maybe_read_range(void)
{
    uint8_t request[8];
    char tx_hex[17];
    char rx_hex[CG_PZEM_RX_MAX * 2 + 1];
    char value_hex[7] = "nan";
    const char *profile = "nan";
    uint16_t raw_value = 0;
    uint8_t exception_code = 0;

    if (s_range_read_done) {
        return;
    }

    const int64_t now_us = esp_timer_get_time();
    if (s_last_range_try_us != 0 &&
        now_us - s_last_range_try_us < (int64_t)CG_PZEM_RANGE_RETRY_MS * 1000LL) {
        return;
    }
    s_last_range_try_us = now_us;

    const size_t request_len = cg_pzem_build_read_range(CG_PZEM_SLAVE_ADDRESS, request);
    const cg_link_result_t link = link_transaction(request, request_len, 7U);

    cg_pzem_status_t status = link.status;
    if (link.rx_len > 0) {
        status = cg_pzem_parse_range(link.rx, link.rx_len, CG_PZEM_SLAVE_ADDRESS, &raw_value);
        if (status == CG_PZEM_OK) {
            cg_pzem_range_hex(raw_value, value_hex);
            profile = cg_pzem_profile_name(raw_value);
            /* A valid readback is evidence even when the profile is not the
             * expected 50 A one: retrying cannot change the register, and a
             * mismatch is a finding, not a link problem. */
            s_range_read_done = true;
        } else if (status == CG_PZEM_EXCEPTION && link.rx_len >= 3U) {
            exception_code = link.rx[2];
        }
    }

    const bool crc_ok =
        link.rx_len >= 4U && cg_crc16_check(link.rx, (size_t)link.rx_len);

    hex_encode(request, request_len, tx_hex, sizeof(tx_hex));
    hex_encode(link.rx, link.rx_len, rx_hex, sizeof(rx_hex));

    cg_log_line("%s %s uptime_ms=%lld status=%s value=%s profile=%s crc_ok=%d exc=%d tx=%s rx=%s",
                CG_LOG_PREFIX, CG_LOG_PZEM_RANGE, (long long)(esp_timer_get_time() / 1000LL),
                cg_pzem_status_name(status), value_hex, profile, crc_ok ? 1 : 0, exception_code,
                tx_hex, rx_hex);
}

static void power_task(void *arg)
{
    int64_t next_deadline_us;

    (void)arg;

    if (!cg_rs485_init()) {
        cg_log_error("pzem=RS485_INIT_FAIL poll=disabled");
        vTaskDelete(NULL);
        return;
    }

    log_config_line();
    maybe_read_range();

    next_deadline_us = esp_timer_get_time();

    while (true) {
        poll_once();
        maybe_read_range();

        /* Deadline pacing like the sensor task: uptime_ms in each line is
         * the real observation time. */
        next_deadline_us += (int64_t)CG_PZEM_POLL_PERIOD_MS * 1000LL;
        const int64_t now_us = esp_timer_get_time();
        if (next_deadline_us > now_us) {
            TickType_t ticks = pdMS_TO_TICKS((uint32_t)((next_deadline_us - now_us + 999) / 1000));
            vTaskDelay(ticks > 0 ? ticks : 1);
        } else {
            next_deadline_us = now_us;
        }
    }
}

void cg_power_start(void)
{
    (void)xTaskCreate(power_task, "cg_power", CG_POWER_STACK_WORDS, NULL, CG_POWER_TASK_PRIORITY,
                      NULL);
}
