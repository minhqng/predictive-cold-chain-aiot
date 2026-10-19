/*
 * ColdGuard firmware - PZEM-017 Modbus RTU protocol (Member A, W03).
 */
#include "cg_pzem.h"

#include <stdio.h>

#include "coldguard_config.h"
#include "cg_crc16.h"

#define CG_PZEM_INPUT_FRAME_LEN 17U /* 1 slave + 1 fc + 1 count + 12 data + 2 crc */
#define CG_PZEM_RANGE_FRAME_LEN 7U  /* 1 slave + 1 fc + 1 count + 2 data + 2 crc */

static size_t build_read(uint8_t slave, uint8_t function, uint16_t reg, uint16_t count,
                         uint8_t *out)
{
    const size_t payload = 6U;

    if (out == NULL || count == 0U) {
        return 0;
    }
    out[0] = slave;
    out[1] = function;
    out[2] = (uint8_t)(reg >> 8);
    out[3] = (uint8_t)(reg & 0xFFU);
    out[4] = (uint8_t)(count >> 8);
    out[5] = (uint8_t)(count & 0xFFU);
    return cg_crc16_append(out, payload, 8U);
}

size_t cg_pzem_build_read_input(uint8_t slave, uint8_t *out)
{
    return build_read(slave, CG_PZEM_FC_READ_INPUT, CG_PZEM_REG_VOLTAGE,
                      CG_PZEM_REG_INPUT_COUNT, out);
}

size_t cg_pzem_build_read_range(uint8_t slave, uint8_t *out)
{
    return build_read(slave, CG_PZEM_FC_READ_HOLDING, CG_PZEM_HOLDING_CURRENT_RANGE, 1U, out);
}

cg_pzem_status_t cg_pzem_parse_input(const uint8_t *frame, size_t len, uint8_t expected_slave,
                                     uint16_t regs[6])
{
    if (frame == NULL || regs == NULL || len < 4U) {
        return CG_PZEM_BAD_LENGTH;
    }
    if (!cg_crc16_check(frame, len)) {
        return CG_PZEM_CRC_ERR;
    }
    if (frame[0] != expected_slave) {
        return CG_PZEM_BAD_SLAVE;
    }
    if ((frame[1] & 0x80U) != 0U) {
        return CG_PZEM_EXCEPTION;
    }
    if (frame[1] != CG_PZEM_FC_READ_INPUT) {
        return CG_PZEM_BAD_FUNCTION;
    }
    if (len != CG_PZEM_INPUT_FRAME_LEN || frame[2] != 12U) {
        return CG_PZEM_BAD_LENGTH;
    }
    for (size_t i = 0; i < 6U; i++) {
        regs[i] = ((uint16_t)frame[3U + i * 2U] << 8) | frame[4U + i * 2U];
    }
    return CG_PZEM_OK;
}

cg_pzem_status_t cg_pzem_parse_range(const uint8_t *frame, size_t len, uint8_t expected_slave,
                                     uint16_t *raw_value)
{
    if (frame == NULL || raw_value == NULL || len < 4U) {
        return CG_PZEM_BAD_LENGTH;
    }
    if (!cg_crc16_check(frame, len)) {
        return CG_PZEM_CRC_ERR;
    }
    if (frame[0] != expected_slave) {
        return CG_PZEM_BAD_SLAVE;
    }
    if ((frame[1] & 0x80U) != 0U) {
        return CG_PZEM_EXCEPTION;
    }
    if (frame[1] != CG_PZEM_FC_READ_HOLDING) {
        return CG_PZEM_BAD_FUNCTION;
    }
    if (len != CG_PZEM_RANGE_FRAME_LEN || frame[2] != 2U) {
        return CG_PZEM_BAD_LENGTH;
    }
    *raw_value = ((uint16_t)frame[3] << 8) | frame[4];
    return CG_PZEM_OK;
}

void cg_pzem_decode_input(const uint16_t regs[6], cg_pzem_values_t *values)
{
    if (regs == NULL || values == NULL) {
        return;
    }
    const uint32_t power_raw = ((uint32_t)regs[3] << 16) | (uint32_t)regs[2];
    const uint32_t energy_raw = ((uint32_t)regs[5] << 16) | (uint32_t)regs[4];

    values->voltage_v = (float)regs[0] * CG_PZEM_VOLT_LSB;
    values->current_a = (float)regs[1] * CG_PZEM_CURRENT_LSB;
    values->power_w = (float)power_raw * CG_PZEM_POWER_LSB;
    values->energy_wh = (float)energy_raw * CG_PZEM_ENERGY_LSB;
}

const char *cg_pzem_status_name(cg_pzem_status_t status)
{
    switch (status) {
    case CG_PZEM_OK:
        return "OK";
    case CG_PZEM_TIMEOUT:
        return "TIMEOUT";
    case CG_PZEM_CRC_ERR:
        return "CRC_ERR";
    case CG_PZEM_BAD_SLAVE:
        return "BAD_SLAVE";
    case CG_PZEM_BAD_FUNCTION:
        return "BAD_FUNCTION";
    case CG_PZEM_BAD_LENGTH:
        return "BAD_LENGTH";
    case CG_PZEM_EXCEPTION:
        return "EXCEPTION";
    case CG_PZEM_UART_ERR:
    default:
        return "UART_ERR";
    }
}

const char *cg_pzem_profile_name(uint16_t raw_value)
{
    switch (raw_value) {
    case CG_PZEM_RANGE_50A:
        return "50A";
    case CG_PZEM_RANGE_100A:
        return "100A";
    case CG_PZEM_RANGE_200A:
        return "200A";
    case CG_PZEM_RANGE_300A:
        return "300A";
    default:
        return "UNKNOWN";
    }
}

void cg_pzem_range_hex(uint16_t raw_value, char out[7])
{
    if (out == NULL) {
        return;
    }
    (void)snprintf(out, 7, "0x%04X", raw_value);
}
