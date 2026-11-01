/*
 * ColdGuard firmware - serial log primitives (Member A, W02/W03).
 *
 * Every machine line starts with the "#CG" prefix so that a host tool can
 * parse a raw Serial Monitor capture without guessing. Lines are written
 * under a mutex so that a line is never interleaved with another task's
 * line (a partially interleaved line would corrupt the evidence).
 *
 * Grammar (version 2 = version 1 kinds unchanged, plus the W03 PZEM kinds):
 *   #CG LOG v=<n> fw=<fw> hw=<hw> device=<dev> pin_map=<n> grammar=<n>
 *   #CG SAFETY actuator=OFF pwm=5 en=6 len=10
 *   #CG BOOT boot_id=<hex> boot_count=<n>
 *   #CG ROM role=<T1|T2|T3|SPARE> rom=<16 hex> present=<0|1> status=<ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING>
 *   #CG ROMS required_present=<n>/3 known=<n> known_present=<n>
 *   #CG DOOR_POLARITY state=<UNVERIFIED|CONFIRMED> raw_open_level=<0|1>
 *   #CG DOOR_EDGE uptime_us=<n> raw=<0|1>
 *   #CG DOOR_STATE uptime_ms=<n> raw=<0|1> state=<OPEN|CLOSED|UNVERIFIED> transitions=<n> cycles=<n> discarded=<n>
 *   #CG SAMPLE uptime_ms=<n> seq=<n> T1=<f|nan> T2=<f|nan> T3=<f|nan> SPARE=<f|nan> t1=<0|1> t2=<0|1> t3=<0|1> thermal=<VALID|DEGRADED|INVALID> door_raw=<0|1> door=<OPEN|CLOSED|UNVERIFIED>
 *   #CG PZEM_CFG slave=<n> baud=<n> framing=<8N1|8N2|8E1|8O1> dir=<AUTO|MANUAL> read_only=1
 *   #CG PZEM_RANGE uptime_ms=<n> status=<token> value=<0xNNNN|nan> profile=<50A|100A|200A|300A|UNKNOWN|nan> crc_ok=<0|1> exc=<n> tx=<hex> rx=<hex>
 *   #CG PZEM uptime_ms=<n> seq=<n> status=<OK|TIMEOUT|CRC_ERR|BAD_SLAVE|BAD_FUNCTION|BAD_LENGTH|EXCEPTION|UART_ERR> slave=<n> v=<f|nan> i=<f|nan> p=<f|nan> e=<f|nan> crc_ok=<0|1> attempts=<n> exc=<n> ok=<n> fail=<n> tx=<hex> rx=<hex>
 *   #CG AUTH token=<8 hex> ttl_ms=<n> clear_requires_token=1
 *   #CG TEC event=<token> ...          (state machine events and status)
 *   #CG TEC_LIMIT name=<token> state=<UNRESOLVED|RESOLVED> value=<f> unit=<token> source=<token>
 *   #CG TELEM schema=1 ...             (raw experiment telemetry, cg_telemetry.h)
 *   #CG ERR msg=<token>
 *
 * `nan` means "no valid reading"; it is never 0.0 and never a stale value.
 * A failed PZEM poll therefore prints `nan` for v/i/p/e - the previous value
 * is never carried forward. The ROM summary counts the frozen map only
 * (known=<CG_ROLE_COUNT>); W02 has no bus scan and therefore prints no
 * "unknown devices" counter.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

void cg_log_init(void);

/* Writes one line. fmt must be a literal CSV-free single-line format. */
void cg_log_line(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

/* Writes a preformatted machine line (no trailing newline) without the
 * 256-byte reformatting limit. The line must fit CG_TELEMETRY_LINE_MAX;
 * returns false and writes nothing when it does not, so a truncated raw
 * observation can never look complete. */
bool cg_log_raw_line(const char *line);

void cg_log_banner(void);
void cg_log_safety_actuator_off(void);
void cg_log_boot(const char *boot_id, uint32_t boot_count);
void cg_log_rom(const char *role, const uint8_t rom[8], bool present, const char *status);
void cg_log_rom_summary(int required_present, int known_present);
void cg_log_door_polarity(bool confirmed, int raw_open_level);
void cg_log_error(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

/* Formats a temperature for a SAMPLE line: "nan" when invalid
 * (docs/01 PHY-DS-004 - a failed read must stay visible as missing). */
const char *cg_log_temp_or_nan(bool valid, float celsius, char *buf, size_t buf_len);

const char *cg_log_rom_hex(const uint8_t rom[8], char out[17]);
