/*
 * ColdGuard firmware - Modbus RTU CRC16 (Member A, W03).
 */
#include "cg_crc16.h"

uint16_t cg_crc16_modbus(const uint8_t *data, size_t len)
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

size_t cg_crc16_append(uint8_t *frame, size_t payload_len, size_t cap)
{
    if (frame == NULL || payload_len + 2U > cap) {
        return 0;
    }
    uint16_t crc = cg_crc16_modbus(frame, payload_len);
    frame[payload_len] = (uint8_t)(crc & 0xFFU);        /* low byte first */
    frame[payload_len + 1U] = (uint8_t)(crc >> 8);
    return payload_len + 2U;
}

bool cg_crc16_check(const uint8_t *frame, size_t len)
{
    if (frame == NULL || len < 4U) {
        return false;
    }
    uint16_t crc = cg_crc16_modbus(frame, len - 2U);
    uint16_t received = (uint16_t)frame[len - 2U] | ((uint16_t)frame[len - 1U] << 8);
    return crc == received;
}
