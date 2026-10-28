/*
 * ColdGuard firmware - DS18B20 acquisition (Member A, W02).
 */
#include "cg_ds18b20.h"

#include <string.h>

#include "coldguard_config.h"
#include "cg_log.h"
#include "cg_onewire.h"

#define DS18B20_CMD_CONVERT_T 0x44
#define DS18B20_CMD_WRITE_SCRATCHPAD 0x4E
#define DS18B20_CMD_READ_SCRATCHPAD 0xBE
#define DS18B20_CMD_MATCH_ROM 0x55
#define DS18B20_CMD_SKIP_ROM 0xCC

#define DS18B20_SCRATCHPAD_LEN 9
#define DS18B20_ALARM_HIGH 0x7F /* +127 C, alarm search not used in W02 */
#define DS18B20_ALARM_LOW 0xC9  /* -55 C */
#define DS18B20_CONFIG_12BIT 0x7F

const char *cg_quality_name(cg_thermal_quality_t quality)
{
    switch (quality) {
        case CG_QUALITY_VALID:
            return "VALID";
        case CG_QUALITY_DEGRADED:
            return "DEGRADED";
        case CG_QUALITY_INVALID:
        default:
            return "INVALID";
    }
}

bool cg_ds18b20_init(void)
{
    bool all_ok = true;

    cg_onewire_init(CG_ONEWIRE_PIN);

    if (!cg_onewire_reset()) {
        cg_log_error("ds18b20=NO_PRESENCE pin=%d", CG_ONEWIRE_PIN);
        return false;
    }

    /* Deterministic 12-bit resolution for every frozen ROM: the scratchpad
     * configuration is volatile across power loss (it survives reset only
     * when copied to EEPROM), so it is written on every boot. */
    for (size_t i = 0; i < cg_rom_map_size(); i++) {
        const cg_rom_entry_t *entry = &cg_rom_map_entries()[i];
        uint8_t cmd[4] = {DS18B20_CMD_WRITE_SCRATCHPAD, DS18B20_ALARM_HIGH,
                          DS18B20_ALARM_LOW, DS18B20_CONFIG_12BIT};

        if (!cg_onewire_reset()) {
            cg_log_error("ds18b20=NO_PRESENCE during config role=%s", entry->name);
            all_ok = false;
            break;
        }
        cg_onewire_write_byte(DS18B20_CMD_MATCH_ROM);
        cg_onewire_write_bytes(entry->rom, 8);
        cg_onewire_write_bytes(cmd, 4);
        (void)cg_onewire_reset(); /* release the bus */
    }

    return all_ok;
}

static void read_scratchpad(const uint8_t rom[8], uint8_t out[DS18B20_SCRATCHPAD_LEN])
{
    cg_onewire_write_byte(DS18B20_CMD_MATCH_ROM);
    cg_onewire_write_bytes(rom, 8);
    cg_onewire_write_byte(DS18B20_CMD_READ_SCRATCHPAD);
    cg_onewire_read_bytes(out, DS18B20_SCRATCHPAD_LEN);
}

void cg_ds18b20_read_probe(cg_role_t role, cg_probe_t *out)
{
    uint8_t rom[8];
    uint8_t sp[DS18B20_SCRATCHPAD_LEN];
    int16_t raw;
    float celsius;

    cg_rom_map_bytes(role, rom);

    out->valid = false;

    if (!cg_onewire_reset()) {
        out->status = CG_READ_NO_PRESENCE;
        out->present = false;
        out->fail_count++;
        return;
    }

    read_scratchpad(rom, sp);

    if (cg_onewire_crc8(sp, 8) != sp[8]) {
        out->status = CG_READ_CRC_FAIL;
        out->fail_count++;
        return;
    }

    out->present = true;
    raw = (int16_t)(((uint16_t)sp[1] << 8) | sp[0]);
    celsius = (float)raw / 16.0f;

    if ((uint16_t)raw == (uint16_t)CG_DS18B20_POWER_ON_RAW) {
        /* Documented power-on reset value: a real chamber at 85.0 C is not
         * a plausible bench condition, and reporting it would be worse
         * than reporting a missing sample. */
        out->status = CG_READ_POWER_ON_RESET;
        out->celsius = celsius;
        out->fail_count++;
        return;
    }

    if (celsius < CG_DS18B20_MIN_C || celsius > CG_DS18B20_MAX_C) {
        out->status = CG_READ_OUT_OF_RANGE;
        out->celsius = celsius;
        out->fail_count++;
        return;
    }

    out->status = CG_READ_OK;
    out->valid = true;
    out->celsius = celsius;
    out->fail_count = 0;
}

bool cg_ds18b20_convert_all(void)
{
    if (!cg_onewire_reset()) {
        return false;
    }
    cg_onewire_write_byte(DS18B20_CMD_SKIP_ROM);
    cg_onewire_write_byte(DS18B20_CMD_CONVERT_T);
    return true;
}

void cg_ds18b20_enumerate(cg_thermal_snapshot_t *out)
{
    out->required_present = 0;
    out->known_present = 0;

    for (size_t i = 0; i < cg_rom_map_size(); i++) {
        const cg_rom_entry_t *entry = &cg_rom_map_entries()[i];
        bool present = cg_onewire_reset();

        if (present) {
            uint8_t sp[DS18B20_SCRATCHPAD_LEN];
            read_scratchpad(entry->rom, sp);
            present = (cg_onewire_crc8(sp, 8) == sp[8]);
        }

        out->probe[entry->role].present = present;
        out->probe[entry->role].valid = false;
        out->probe[entry->role].status = present ? CG_READ_OK : CG_READ_NO_PRESENCE;

        if (present) {
            out->known_present++;
            if (entry->is_measurement_role) {
                out->required_present++;
            }
        }

        cg_log_rom(entry->name, entry->rom, present, CG_ROM_STATUS);
    }

    cg_log_rom_summary(out->required_present, out->known_present);
}

void cg_ds18b20_read_all(cg_thermal_snapshot_t *snap)
{
    int invalid_roles = 0;

    for (size_t i = 0; i < cg_rom_map_size(); i++) {
        const cg_rom_entry_t *entry = &cg_rom_map_entries()[i];
        cg_ds18b20_read_probe(entry->role, &snap->probe[entry->role]);
    }

    for (size_t i = 0; i < cg_rom_map_size(); i++) {
        const cg_rom_entry_t *entry = &cg_rom_map_entries()[i];
        if (entry->is_measurement_role && !snap->probe[entry->role].valid) {
            invalid_roles++;
        }
    }

    if (invalid_roles == 0) {
        snap->quality = CG_QUALITY_VALID;
    } else if (invalid_roles == 1) {
        snap->quality = CG_QUALITY_DEGRADED;
    } else {
        snap->quality = CG_QUALITY_INVALID;
    }
}
