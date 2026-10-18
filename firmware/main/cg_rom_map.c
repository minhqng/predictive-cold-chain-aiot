/*
 * ColdGuard firmware - ROM -> role mapping implementation (Member A, W02).
 *
 * The table content mirrors evidence/A/W02/sensor-rom-map.yaml. The
 * Python source checker (firmware/tools/cg_check_firmware.py) compares
 * both files so they cannot drift apart silently.
 */
#include "cg_rom_map.h"

#include <string.h>

#include "coldguard_config.h"
#include "cg_log.h"

static const uint8_t CG_ROM_T1[8] = CG_ROM_T1_BYTES;
static const uint8_t CG_ROM_T2[8] = CG_ROM_T2_BYTES;
static const uint8_t CG_ROM_T3[8] = CG_ROM_T3_BYTES;
static const uint8_t CG_ROM_SPARE[8] = CG_ROM_SPARE_BYTES;

static const cg_rom_entry_t CG_TABLE[CG_ROLE_COUNT] = {
    {CG_ROLE_T1, "T1", CG_ROM_T1, true},
    {CG_ROLE_T2, "T2", CG_ROM_T2, true},
    {CG_ROLE_T3, "T3", CG_ROM_T3, true},
    {CG_ROLE_SPARE, "SPARE", CG_ROM_SPARE, false},
};

/* Dallas/Maxim CRC8 (reflected polynomial 0x8C) over the first `len`
 * bytes; a valid DS18B20 ROM has crc8(rom[0..6]) == rom[7]. */
static uint8_t crc8_dallas(const uint8_t *data, size_t len)
{
    uint8_t crc = 0;
    for (size_t i = 0; i < len; i++) {
        uint8_t byte = data[i];
        for (int bit = 0; bit < 8; bit++) {
            uint8_t mix = (uint8_t)((crc ^ byte) & 0x01);
            crc >>= 1;
            if (mix) {
                crc ^= 0x8C;
            }
            byte >>= 1;
        }
    }
    return crc;
}

const cg_rom_entry_t *cg_rom_map_entries(void)
{
    return CG_TABLE;
}

size_t cg_rom_map_size(void)
{
    return (size_t)CG_ROLE_COUNT;
}

cg_rom_match_t cg_rom_map_match(const uint8_t rom[8])
{
    for (size_t i = 0; i < CG_ROLE_COUNT; i++) {
        if (memcmp(rom, CG_TABLE[i].rom, 8) == 0) {
            return (cg_rom_match_t)i;
        }
    }
    return CG_ROM_UNKNOWN;
}

void cg_rom_map_bytes(cg_role_t role, uint8_t out[8])
{
    for (size_t i = 0; i < CG_ROLE_COUNT; i++) {
        if (CG_TABLE[i].role == role) {
            memcpy(out, CG_TABLE[i].rom, 8);
            return;
        }
    }
    memset(out, 0, 8);
}

const char *cg_role_name(cg_role_t role)
{
    for (size_t i = 0; i < CG_ROLE_COUNT; i++) {
        if (CG_TABLE[i].role == role) {
            return CG_TABLE[i].name;
        }
    }
    return "UNKNOWN";
}

bool cg_rom_map_self_check(void)
{
    bool ok = true;

    for (size_t i = 0; i < CG_ROLE_COUNT; i++) {
        const uint8_t *rom = CG_TABLE[i].rom;
        if (crc8_dallas(rom, 7) != rom[7]) {
            cg_log_error("rom_map=BAD_CRC role=%s", CG_TABLE[i].name);
            ok = false;
        }
        if (rom[0] != 0x28) {
            cg_log_error("rom_map=BAD_FAMILY role=%s", CG_TABLE[i].name);
            ok = false;
        }
    }

    for (size_t i = 0; i < CG_ROLE_COUNT; i++) {
        for (size_t j = i + 1; j < CG_ROLE_COUNT; j++) {
            if (memcmp(CG_TABLE[i].rom, CG_TABLE[j].rom, 8) == 0) {
                cg_log_error("rom_map=DUPLICATE %s %s", CG_TABLE[i].name, CG_TABLE[j].name);
                ok = false;
            }
        }
    }

    return ok;
}
