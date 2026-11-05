/*
 * ColdGuard H6 - read-only PZEM-017 poller.
 *
 * Wire behaviour on this bench unit (preserved W03 TTL485 logs, 2026-10-20):
 * the auto-direction TTL485 module echoes the 8-byte request onto RX
 * (7-8 prefix bytes in 595/595 successful samples) and the module's reply
 * completes roughly 72-92 ms after the request. A read therefore has to keep
 * waiting through the echo until the reply arrives; it must not end at the
 * first inter-byte gap.
 *
 * Protocol: one 8-byte FC04 request for six input registers, CRC16/MODBUS,
 * tail-independent frame scan, 250 ms per-attempt window, 2 attempts. There
 * is no write function code in this module.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    H6_PZEM_OK = 0,
    H6_PZEM_TIMEOUT,
    H6_PZEM_CRC_ERR,
    H6_PZEM_BAD_SLAVE,
    H6_PZEM_BAD_FUNCTION,
    H6_PZEM_BAD_LENGTH,
    H6_PZEM_EXCEPTION,
    H6_PZEM_UART_ERR,
} h6_pzem_status_t;

typedef struct {
    bool valid;
    h6_pzem_status_t status;
    float voltage_v;
    float current_a;
    float power_w;
} h6_pzem_sample_t;

/* Byte-stream class of one attempt. */
typedef enum {
    H6_PZEM_CLASS_NONE = 0,
    H6_PZEM_CLASS_OK,             /* CRC-valid FC04 reply with >= 6 data registers */
    H6_PZEM_CLASS_NO_RESPONSE,    /* no byte received */
    H6_PZEM_CLASS_ECHO_ONLY,      /* request echo, no reply */
    H6_PZEM_CLASS_PARTIAL,        /* bytes received, no complete frame */
    H6_PZEM_CLASS_FULL_WRONG_COUNT, /* CRC-valid reply with < 12 data bytes */
    H6_PZEM_CLASS_CRC_INVALID,    /* full-shape reply, CRC mismatch */
    H6_PZEM_CLASS_EXCEPTION,      /* CRC-valid FC84 exception */
    H6_PZEM_CLASS_BAD_SLAVE,      /* CRC-valid reply from another slave */
    H6_PZEM_CLASS_AMBIGUOUS,      /* two different CRC-valid replies */
} h6_pzem_class_t;

#define H6_PZEM_TRACE_RX_MAX 32
#define H6_PZEM_TRACE_CHUNKS 8

typedef struct {
    uint8_t tx[8];
    size_t tx_len;
    uint8_t rx[H6_PZEM_TRACE_RX_MAX];
    size_t rx_len;
    uint8_t chunk_len[H6_PZEM_TRACE_CHUNKS];
    uint16_t chunk_at_ms[H6_PZEM_TRACE_CHUNKS];
    uint8_t chunk_count;
    uint32_t first_byte_ms;
    uint32_t last_byte_ms;
    int frame_off;   /* -1 when no usable frame */
    int frame_len;   /* -1 when no usable frame */
    int slave;       /* -1 when no frame header was seen */
    int function;    /* -1 when no frame header was seen */
    int byte_count;  /* -1 when no frame header was seen */
    uint8_t echo_bytes;
    bool crc_ok;
    bool usable;
    bool uart_error;
    bool early_exit;
    h6_pzem_class_t cls;
} h6_pzem_trace_t;

/* Result of scanning a received byte stream for a Modbus frame. */
typedef struct {
    bool usable;     /* CRC-valid FC04 from H6_PZEM_SLAVE with >= 12 data bytes */
    bool crc_valid;  /* some complete frame passed CRC */
    bool has_header; /* slave/function/byte_count were filled from a frame */
    bool ambiguous;  /* more than one distinct usable frame */
    size_t offset;
    size_t len;
    uint8_t slave;
    uint8_t function;
    uint8_t byte_count;
    uint8_t echo_bytes;
} h6_pzem_frame_t;

typedef void (*h6_pzem_trace_fn)(uint8_t attempt, const h6_pzem_trace_t *trace, void *ctx);

bool h6_pzem_init(void);

/* Optional per-attempt raw trace. Called after every attempt, including
 * failed ones. Passing NULL disables it. */
void h6_pzem_set_trace(h6_pzem_trace_fn fn, void *ctx);

/* Pure classification of a received buffer against a transmitted request.
 * Used by the poller and by the on-device self-test. */
h6_pzem_class_t h6_pzem_classify(const uint8_t *rx, size_t rx_len, const uint8_t *tx,
                                 size_t tx_len, h6_pzem_frame_t *frame);

/* Decode the first six input registers (voltage, current, power, energy low). */
bool h6_pzem_parse_registers(const uint8_t *frame, size_t len, uint16_t regs[6]);

/* One poll, up to 2 attempts. On failure `valid` is false and the values are
 * zero; a failed poll never reuses an earlier reading. */
h6_pzem_sample_t h6_pzem_poll(void);

const char *h6_pzem_status_name(h6_pzem_status_t status);
const char *h6_pzem_class_name(h6_pzem_class_t cls);
