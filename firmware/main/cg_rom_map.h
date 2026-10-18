/*
 * ColdGuard firmware - ROM -> role mapping (Member A, W02).
 *
 * Identity is the ROM code (docs/01 section 6.5). The lookup below never
 * depends on 1-Wire discovery order: a role is resolved by comparing the
 * eight ROM bytes, so a library/bus enumeration order cannot silently
 * remap a probe (docs/01 PHY-DS-002).
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    CG_ROLE_T1 = 0,
    CG_ROLE_T2 = 1,
    CG_ROLE_T3 = 2,
    CG_ROLE_SPARE = 3,
    CG_ROLE_COUNT = 4,
} cg_role_t;

typedef struct {
    cg_role_t role;
    const char *name;         /* "T1", "T2", "T3", "SPARE" */
    const uint8_t *rom;       /* 8 bytes in wire order */
    bool is_measurement_role; /* false for SPARE */
} cg_rom_entry_t;

typedef enum {
    CG_ROM_MATCH_T1 = 0,
    CG_ROM_MATCH_T2,
    CG_ROM_MATCH_T3,
    CG_ROM_MATCH_SPARE,
    CG_ROM_UNKNOWN, /* not in the frozen map - never assigned a role */
} cg_rom_match_t;

/* Returns the frozen table (CG_ROLE_COUNT entries) and its size. */
const cg_rom_entry_t *cg_rom_map_entries(void);
size_t cg_rom_map_size(void);

/* Exact-byte ROM match. CG_ROM_UNKNOWN is a normal, non-fatal answer:
 * an unknown ROM never replaces a known missing sensor (PHY-DS-002). */
cg_rom_match_t cg_rom_map_match(const uint8_t rom[8]);

/* Configuration self-check at boot: the four ROMs must be pairwise
 * distinct and every entry must carry a valid Dallas CRC8. Returns true
 * when the frozen map is usable; logs the reason otherwise. */
bool cg_rom_map_self_check(void);

/* Copy the frozen 8 ROM bytes for a role into `out`. */
void cg_rom_map_bytes(cg_role_t role, uint8_t out[8]);

/* Stable role name ("T1".."SPARE") used verbatim in serial lines. */
const char *cg_role_name(cg_role_t role);
