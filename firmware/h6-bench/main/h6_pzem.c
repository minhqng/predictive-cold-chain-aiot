/*
 * ColdGuard H6 - read-only PZEM-017 poller implementation.
 *
 * Read policy: write the FC04 request, then keep collecting bytes until a
 * CRC-valid reply is present or the per-attempt window expires. Line idle is
 * NOT a reason to stop: the transceiver echoes the request and the module's
 * reply follows tens of milliseconds later.
 */
#include "h6_pzem.h"

#include <stddef.h>
#include <string.h>

#include "driver/uart.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "h6_config.h"

#define H6_UART_PORT ((uart_port_t)H6_PZEM_UART_PORT)
#define H6_PZEM_ECHO_MIN_BYTES 7U
#define H6_PZEM_MIN_DATA_BYTES 12U

static bool s_ready;
static h6_pzem_trace_fn s_trace_fn;
static void *s_trace_ctx;

static uint16_t crc16_modbus(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFF;

    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i];
        for (int bit = 0; bit < 8; bit++) {
            if ((crc & 0x0001U) != 0U) {
                crc = (uint16_t)((crc >> 1) ^ 0xA001U);
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

static bool crc16_check(const uint8_t *frame, size_t len)
{
    if (frame == NULL || len < 4U) {
        return false;
    }
    const uint16_t crc = crc16_modbus(frame, len - 2U);
    const uint16_t received = (uint16_t)frame[len - 2U] | ((uint16_t)frame[len - 1U] << 8);
    return crc == received;
}

static size_t build_read_input(uint8_t slave, uint8_t *out)
{
    out[0] = slave;
    out[1] = 0x04U; /* read input registers; READ ONLY */
    out[2] = 0x00U;
    out[3] = 0x00U;
    out[4] = 0x00U;
    out[5] = 0x06U;
    const uint16_t crc = crc16_modbus(out, 6U);
    out[6] = (uint8_t)(crc & 0xFFU);
    out[7] = (uint8_t)(crc >> 8);
    return 8U;
}

/* Length of the transmitted request visible at the start of RX. The proven
 * bench unit echoes all 8 bytes, or 7 when the first echoed byte is lost in
 * the transceiver turnaround. Shorter coincidental prefixes are ignored. */
static uint8_t echo_prefix_len(const uint8_t *rx, size_t rx_len, const uint8_t *tx,
                               size_t tx_len)
{
    if (rx == NULL || tx == NULL || tx_len < H6_PZEM_ECHO_MIN_BYTES) {
        return 0U;
    }
    size_t k = rx_len < tx_len ? rx_len : tx_len;
    for (; k >= H6_PZEM_ECHO_MIN_BYTES; k--) {
        if (memcmp(rx, tx, k) == 0) {
            return (uint8_t)k;
        }
        if (memcmp(rx, tx + (tx_len - k), k) == 0) {
            return (uint8_t)k;
        }
    }
    return 0U;
}

h6_pzem_class_t h6_pzem_classify(const uint8_t *rx, size_t rx_len, const uint8_t *tx,
                                 size_t tx_len, h6_pzem_frame_t *frame)
{
    h6_pzem_frame_t local;

    if (frame == NULL) {
        frame = &local;
    }
    memset(frame, 0, sizeof(*frame));

    if (rx == NULL || rx_len == 0U) {
        return H6_PZEM_CLASS_NO_RESPONSE;
    }

    unsigned usable_count = 0U;
    bool bad_crc_seen = false;
    bool wrong_count_seen = false;
    bool exception_seen = false;
    h6_pzem_frame_t usable = {0};
    h6_pzem_frame_t diagnostic = {0};

    /* Scan every offset: the echo prefix precedes the reply, and a trailing
     * byte after the reply must not hide it. */
    for (size_t start = 0U; start + H6_PZEM_EXCEPTION_FRAME_LEN <= rx_len; start++) {
        const uint8_t function = rx[start + 1U];
        size_t candidate_len = 0U;

        if ((function & 0x80U) != 0U) {
            candidate_len = H6_PZEM_EXCEPTION_FRAME_LEN;
        } else if (function == 0x04U) {
            const uint8_t count = rx[start + 2U];
            if ((count & 1U) != 0U || count < 2U) {
                continue;
            }
            candidate_len = H6_PZEM_EXCEPTION_FRAME_LEN + (size_t)count;
        } else {
            continue;
        }

        if (start + candidate_len > rx_len) {
            continue;
        }

        if ((function & 0x80U) != 0U) {
            if (function == 0x84U && crc16_check(rx + start, candidate_len)) {
                exception_seen = true;
                diagnostic.has_header = true;
                diagnostic.crc_valid = true;
                diagnostic.offset = start;
                diagnostic.len = candidate_len;
                diagnostic.slave = rx[start];
                diagnostic.function = function;
                diagnostic.byte_count = 0U;
            }
            continue;
        }

        const uint8_t count = rx[start + 2U];
        if (count < H6_PZEM_MIN_DATA_BYTES) {
            /* Too short to hold six registers. A CRC hit here is a diagnostic
             * finding, not telemetry. */
            if (crc16_check(rx + start, candidate_len)) {
                wrong_count_seen = true;
                diagnostic.has_header = true;
                diagnostic.crc_valid = true;
                diagnostic.offset = start;
                diagnostic.len = candidate_len;
                diagnostic.slave = rx[start];
                diagnostic.function = function;
                diagnostic.byte_count = count;
            }
            continue;
        }

        if (!crc16_check(rx + start, candidate_len)) {
            bad_crc_seen = true;
            diagnostic.has_header = true;
            diagnostic.crc_valid = false;
            diagnostic.offset = start;
            diagnostic.len = candidate_len;
            diagnostic.slave = rx[start];
            diagnostic.function = function;
            diagnostic.byte_count = count;
            continue;
        }

        h6_pzem_frame_t candidate = {0};
        candidate.has_header = true;
        candidate.crc_valid = true;
        candidate.offset = start;
        candidate.len = candidate_len;
        candidate.slave = rx[start];
        candidate.function = function;
        candidate.byte_count = count;

        if (rx[start] == H6_PZEM_SLAVE) {
            candidate.usable = true;
            if (usable_count == 0U) {
                usable = candidate;
            }
            usable_count++;
        } else {
            diagnostic = candidate;
        }
    }

    const uint8_t echo = echo_prefix_len(rx, rx_len, tx, tx_len);
    frame->echo_bytes = echo;

    if (usable_count > 1U) {
        frame->ambiguous = true;
        frame->has_header = usable.has_header;
        frame->crc_valid = true;
        frame->slave = usable.slave;
        frame->function = usable.function;
        frame->byte_count = usable.byte_count;
        frame->offset = usable.offset;
        frame->len = usable.len;
        return H6_PZEM_CLASS_AMBIGUOUS;
    }
    if (usable_count == 1U) {
        *frame = usable;
        frame->echo_bytes = echo;
        return H6_PZEM_CLASS_OK;
    }
    if (exception_seen) {
        *frame = diagnostic;
        frame->echo_bytes = echo;
        return H6_PZEM_CLASS_EXCEPTION;
    }
    if (diagnostic.has_header && diagnostic.slave != H6_PZEM_SLAVE) {
        *frame = diagnostic;
        frame->echo_bytes = echo;
        return H6_PZEM_CLASS_BAD_SLAVE;
    }
    if (wrong_count_seen) {
        *frame = diagnostic;
        frame->echo_bytes = echo;
        return H6_PZEM_CLASS_FULL_WRONG_COUNT;
    }
    if (bad_crc_seen) {
        frame->crc_valid = false;
        frame->has_header = diagnostic.has_header;
        frame->slave = diagnostic.slave;
        frame->function = diagnostic.function;
        frame->byte_count = diagnostic.byte_count;
        frame->offset = diagnostic.offset;
        frame->len = diagnostic.len;
        return H6_PZEM_CLASS_CRC_INVALID;
    }
    if (echo > 0U && rx_len <= tx_len + 1U) {
        return H6_PZEM_CLASS_ECHO_ONLY;
    }
    return H6_PZEM_CLASS_PARTIAL;
}

bool h6_pzem_parse_registers(const uint8_t *frame, size_t len, uint16_t regs[6])
{
    if (frame == NULL || regs == NULL || len < 3U) {
        return false;
    }
    if (!crc16_check(frame, len)) {
        return false;
    }
    if (frame[1] != 0x04U) {
        return false;
    }
    const uint8_t count = frame[2];
    if ((count & 1U) != 0U || count < H6_PZEM_MIN_DATA_BYTES || len != (size_t)count + 5U) {
        return false;
    }
    for (size_t i = 0; i < 6U; i++) {
        regs[i] = ((uint16_t)frame[3U + i * 2U] << 8) | frame[4U + i * 2U];
    }
    return true;
}

static uint32_t ms_since(int64_t t0_us)
{
    return (uint32_t)((esp_timer_get_time() - t0_us) / 1000);
}

/* One request/response attempt. Collects until a usable frame is present or
 * the attempt window closes; never stops on line idle. */
static h6_pzem_status_t poll_attempt(const uint8_t *tx, size_t tx_len, h6_pzem_trace_t *trace)
{
    memset(trace, 0, sizeof(*trace));
    trace->frame_off = -1;
    trace->frame_len = -1;
    trace->slave = -1;
    trace->function = -1;
    trace->byte_count = -1;
    trace->tx_len = tx_len;
    memcpy(trace->tx, tx, tx_len);

    uart_flush_input(H6_UART_PORT);
    const int written = uart_write_bytes(H6_UART_PORT, tx, tx_len);
    if (written != (int)tx_len ||
        uart_wait_tx_done(H6_UART_PORT, pdMS_TO_TICKS(H6_PZEM_TX_CMD_MS)) != ESP_OK) {
        trace->uart_error = true;
        return H6_PZEM_UART_ERR;
    }

    const int64_t t0 = esp_timer_get_time();
    const int64_t deadline = t0 + (int64_t)H6_PZEM_TIMEOUT_MS * 1000LL;
    size_t total = 0U;

    while (total < sizeof(trace->rx)) {
        size_t available = 0U;
        if (uart_get_buffered_data_len(H6_UART_PORT, &available) != ESP_OK) {
            trace->uart_error = true;
            break;
        }
        if (available > 0U) {
            size_t take = available;
            if (take > sizeof(trace->rx) - total) {
                take = sizeof(trace->rx) - total;
            }
            const int received = uart_read_bytes(H6_UART_PORT, trace->rx + total, (uint32_t)take, 0);
            if (received < 0) {
                trace->uart_error = true;
                break;
            }
            if (received > 0) {
                const uint32_t at_ms = ms_since(t0);
                if (trace->chunk_count < H6_PZEM_TRACE_CHUNKS) {
                    trace->chunk_len[trace->chunk_count] = (uint8_t)received;
                    trace->chunk_at_ms[trace->chunk_count] = (uint16_t)at_ms;
                }
                if (trace->chunk_count < UINT8_MAX) {
                    trace->chunk_count++;
                }
                total += (size_t)received;
                trace->last_byte_ms = at_ms;

                h6_pzem_frame_t frame;
                if (h6_pzem_classify(trace->rx, total, tx, tx_len, &frame) == H6_PZEM_CLASS_OK) {
                    trace->early_exit = true;
                    break;
                }
                continue;
            }
        }

        if (esp_timer_get_time() >= deadline) {
            break;
        }
        vTaskDelay(1);
    }

    trace->rx_len = total;
    if (trace->chunk_count > 0U) {
        trace->first_byte_ms = trace->chunk_at_ms[0];
    }

    h6_pzem_frame_t frame;
    const h6_pzem_class_t cls = h6_pzem_classify(trace->rx, total, tx, tx_len, &frame);
    trace->cls = cls;
    trace->echo_bytes = frame.echo_bytes;
    trace->crc_ok = frame.crc_valid;
    trace->usable = frame.usable;
    if (frame.has_header) {
        trace->slave = frame.slave;
        trace->function = frame.function;
        trace->byte_count = frame.byte_count;
    }
    if (frame.usable) {
        trace->frame_off = (int)frame.offset;
        trace->frame_len = (int)frame.len;
    }

    if (trace->uart_error) {
        return H6_PZEM_UART_ERR;
    }
    switch (cls) {
    case H6_PZEM_CLASS_OK:
        return H6_PZEM_OK;
    case H6_PZEM_CLASS_NO_RESPONSE:
        return H6_PZEM_TIMEOUT;
    case H6_PZEM_CLASS_CRC_INVALID:
        return H6_PZEM_CRC_ERR;
    case H6_PZEM_CLASS_BAD_SLAVE:
        return H6_PZEM_BAD_SLAVE;
    case H6_PZEM_CLASS_EXCEPTION:
        return H6_PZEM_EXCEPTION;
    case H6_PZEM_CLASS_ECHO_ONLY:
    case H6_PZEM_CLASS_PARTIAL:
    case H6_PZEM_CLASS_FULL_WRONG_COUNT:
    case H6_PZEM_CLASS_AMBIGUOUS:
    case H6_PZEM_CLASS_NONE:
    default:
        return H6_PZEM_BAD_LENGTH;
    }
}

void h6_pzem_set_trace(h6_pzem_trace_fn fn, void *ctx)
{
    s_trace_fn = fn;
    s_trace_ctx = ctx;
}

/* Same initialization order as the production RS-485 transport
 * (param_config, set_pin, driver_install). */
bool h6_pzem_init(void)
{
    const uart_config_t config = {
        .baud_rate = H6_PZEM_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    if (uart_param_config(H6_UART_PORT, &config) != ESP_OK) {
        return false;
    }
    if (uart_set_pin(H6_UART_PORT, H6_PZEM_TX, H6_PZEM_RX, UART_PIN_NO_CHANGE,
                     UART_PIN_NO_CHANGE) != ESP_OK) {
        return false;
    }
    if (uart_driver_install(H6_UART_PORT, 256, 256, 0, NULL, 0) != ESP_OK) {
        return false;
    }
    uart_flush_input(H6_UART_PORT);
    s_ready = true;
    return true;
}

h6_pzem_sample_t h6_pzem_poll(void)
{
    h6_pzem_sample_t sample = {
        .valid = false,
        .status = H6_PZEM_UART_ERR,
        .voltage_v = 0.0f,
        .current_a = 0.0f,
        .power_w = 0.0f,
    };
    uint8_t request[8];
    h6_pzem_trace_t trace;

    if (!s_ready) {
        return sample;
    }

    (void)build_read_input(H6_PZEM_SLAVE, request);

    for (uint8_t attempt = 1U; attempt <= H6_PZEM_ATTEMPTS; attempt++) {
        sample.status = poll_attempt(request, sizeof(request), &trace);
        if (s_trace_fn != NULL) {
            s_trace_fn(attempt, &trace, s_trace_ctx);
        }
        if (sample.status != H6_PZEM_OK) {
            continue;
        }

        uint16_t regs[6] = {0};
        if (!h6_pzem_parse_registers(trace.rx + trace.frame_off, (size_t)trace.frame_len, regs)) {
            sample.status = H6_PZEM_BAD_LENGTH;
            continue;
        }

        const uint32_t power_raw = ((uint32_t)regs[3] << 16) | (uint32_t)regs[2];
        sample.voltage_v = (float)regs[0] * 0.01f;
        sample.current_a = (float)regs[1] * 0.01f;
        sample.power_w = (float)power_raw * 0.1f;
        sample.valid = true;
        return sample;
    }
    return sample;
}

const char *h6_pzem_status_name(h6_pzem_status_t status)
{
    switch (status) {
    case H6_PZEM_OK:
        return "OK";
    case H6_PZEM_TIMEOUT:
        return "TIMEOUT";
    case H6_PZEM_CRC_ERR:
        return "CRC_ERR";
    case H6_PZEM_BAD_SLAVE:
        return "BAD_SLAVE";
    case H6_PZEM_BAD_FUNCTION:
        return "BAD_FUNCTION";
    case H6_PZEM_BAD_LENGTH:
        return "BAD_LENGTH";
    case H6_PZEM_EXCEPTION:
        return "EXCEPTION";
    case H6_PZEM_UART_ERR:
    default:
        return "UART_ERR";
    }
}

const char *h6_pzem_class_name(h6_pzem_class_t cls)
{
    switch (cls) {
    case H6_PZEM_CLASS_OK:
        return "OK";
    case H6_PZEM_CLASS_NO_RESPONSE:
        return "NO_RESPONSE";
    case H6_PZEM_CLASS_ECHO_ONLY:
        return "ECHO_ONLY";
    case H6_PZEM_CLASS_PARTIAL:
        return "PARTIAL";
    case H6_PZEM_CLASS_FULL_WRONG_COUNT:
        return "FULL_WRONG_COUNT";
    case H6_PZEM_CLASS_CRC_INVALID:
        return "CRC_INVALID";
    case H6_PZEM_CLASS_EXCEPTION:
        return "EXCEPTION";
    case H6_PZEM_CLASS_BAD_SLAVE:
        return "BAD_SLAVE";
    case H6_PZEM_CLASS_AMBIGUOUS:
        return "AMBIGUOUS";
    case H6_PZEM_CLASS_NONE:
    default:
        return "NONE";
    }
}
