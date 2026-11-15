/*
 * ColdGuard firmware - PZEM-017 Modbus RTU protocol (Member A, W03).
 *
 * Scope: build READ-ONLY requests, validate/classify responses and decode
 * the manual-derived register map of docs/01 section 9.3. Transport (UART,
 * direction control, retries, logging) lives in cg_rs485.c / cg_power.c.
 *
 * There is intentionally no write builder here: A-W03-04 is a READ-ONLY
 * profile verification, and an accidental write to a PZEM configuration
 * register is not an acceptable risk on this bench. The static checker
 * enforces that function codes 0x06/0x10 never appear in this module.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    CG_PZEM_OK = 0,
    CG_PZEM_TIMEOUT,
    CG_PZEM_CRC_ERR,
    CG_PZEM_BAD_SLAVE,
    CG_PZEM_BAD_FUNCTION,
    CG_PZEM_BAD_LENGTH,
    CG_PZEM_EXCEPTION,
    CG_PZEM_UART_ERR,
#if defined(CG_FAULT_INJECTION) && CG_FAULT_INJECTION
    /* Test-only: the RS-485 transport was deliberately disabled by fault
     * injection. Distinct from TIMEOUT so a suppressed transaction is never
     * reported as a natural response timeout or a physical link failure. */
    CG_PZEM_INJECT_DISABLED,
#endif
} cg_pzem_status_t;

/* Wire lengths used by the extractor and the poll loop. */
#define CG_PZEM_INPUT_FRAME_LEN 17U     /* slave + fc + count + 12 data + crc */
#define CG_PZEM_RANGE_FRAME_LEN 7U      /* slave + fc + count + 2 data + crc */
#define CG_PZEM_EXCEPTION_FRAME_LEN 5U  /* slave + fc|0x80 + code + crc */

typedef struct {
    float voltage_v;
    float current_a;
    float power_w;
    float energy_wh;
} cg_pzem_values_t;

/* Builds a 8-byte read-input-registers request (0x0000..0x0005, FC 0x04).
 * Returns the frame length, or 0 when `out` is NULL. */
size_t cg_pzem_build_read_input(uint8_t slave, uint8_t *out);

/* Builds a 8-byte read-holding-register request for the current-range
 * profile (holding 0x0003, FC 0x03). READ ONLY. */
size_t cg_pzem_build_read_range(uint8_t slave, uint8_t *out);

/* Finds the single complete read response that ends at the end of `rx`.
 *
 * Echo bytes and other prefix bytes before the response are ignored. A
 * candidate must be a complete 0x03/0x04 response (length derived from its
 * byte count) or a complete 5-byte exception, and its CRC must validate.
 * Exactly one candidate is accepted; more than one is ambiguous and is
 * rejected as CG_PZEM_BAD_LENGTH rather than guessing. A stale frame followed
 * by a newer response cannot qualify because it does not end at the tail; a
 * lone late response is indistinguishable from a current one without
 * transaction timing. The expected slave, function and byte count are then
 * checked by cg_pzem_parse_input() or cg_pzem_parse_range(). On success
 * `*frame` points into `rx` and remains
 * valid only while `rx` is alive. On failure both outputs are cleared. This
 * function does not decode registers.
 */
cg_pzem_status_t cg_pzem_extract_response(const uint8_t *rx, size_t rx_len,
                                          const uint8_t **frame, size_t *frame_len);

/* Parses a read-input response into 6 raw registers. On any non-OK status
 * the output registers are left untouched and must not be decoded. */
cg_pzem_status_t cg_pzem_parse_input(const uint8_t *frame, size_t len, uint8_t expected_slave,
                                     uint16_t regs[6]);

/* Parses a read-holding response into the raw range value. */
cg_pzem_status_t cg_pzem_parse_range(const uint8_t *frame, size_t len, uint8_t expected_slave,
                                     uint16_t *raw_value);

/* Applies the canonical scaling. The caller must only call this on a CG_PZEM_OK
 * sample; a failed poll must stay `nan`, never reuse the previous value. */
void cg_pzem_decode_input(const uint16_t regs[6], cg_pzem_values_t *values);

/* Stable tokens used by the serial log and by the host tools. */
const char *cg_pzem_status_name(cg_pzem_status_t status);

/* 0x0001 -> "50A"; unknown codes -> "UNKNOWN". */
const char *cg_pzem_profile_name(uint16_t raw_value);

/* Raw hex of the profile value for the readback evidence line: 0x0001. */
void cg_pzem_range_hex(uint16_t raw_value, char out[7]);
