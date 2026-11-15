/*
 * ColdGuard firmware - Modbus RTU CRC16 (Member A, W03).
 *
 * The CRC is the only integrity check the PZEM-017 provides at the frame
 * level: a valid-looking frame with a bad CRC must never be decoded into
 * voltage/current values (docs/01 PHY-PZ-001). The implementation is a
 * table-free bitwise CRC (poly 0xA001, init 0xFFFF) so the same code is
 * trivial to mirror in the host tools and in the tests.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* CRC16/MODBUS over `len` bytes. */
uint16_t cg_crc16_modbus(const uint8_t *data, size_t len);

/* Appends the CRC as low byte then high byte (Modbus wire order).
 * Returns the new total length, or 0 when `cap` is too small. */
size_t cg_crc16_append(uint8_t *frame, size_t payload_len, size_t cap);

/* True when the last two bytes of `frame` equal the CRC of the preceding
 * bytes. A frame shorter than 4 bytes is never valid. */
bool cg_crc16_check(const uint8_t *frame, size_t len);
