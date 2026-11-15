/*
 * ColdGuard firmware - minimal 1-Wire bus driver (Member A, W02).
 *
 * The ESP-IDF v6.x tree does not ship a 1-Wire host driver and this
 * repository does not use the online component registry (the documented
 * build is a plain `idf.py build` inside the Espressif image), so the
 * bus is bit-banged on a single open-drain GPIO with the standard
 * DS18B20 timing slots.
 *
 * Only the operations a DS18B20 read needs are implemented: reset,
 * write bit/byte, read bit/byte. No ROM search is implemented in W02;
 * identity comes from the frozen ROM map (docs/01 section 6.5), so an
 * unknown extra device on the bus is not detected and never receives a
 * role. That limitation is declared in evidence/A/W02/.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* Configures `pin` as open-drain input/output (external 4.7k pull-up). */
void cg_onewire_init(int pin);

/* Returns true when at least one device answered the reset pulse. */
bool cg_onewire_reset(void);

void cg_onewire_write_bit(int bit);
int cg_onewire_read_bit(void);
void cg_onewire_write_byte(uint8_t byte);
uint8_t cg_onewire_read_byte(void);
void cg_onewire_write_bytes(const uint8_t *data, int len);
void cg_onewire_read_bytes(uint8_t *out, int len);

/* Dallas/Maxim CRC8 (reflected poly 0x8C). Exposed because both the ROM
 * map self-check and the scratchpad read use it. */
uint8_t cg_onewire_crc8(const uint8_t *data, int len);
