/*
 * ColdGuard firmware - RS-485 UART transport (Member A, W03).
 *
 * The as-built interface is a TTL485-V2.0 running from the 5 V logic rail
 * with an auto-direction transceiver (W01 photos 02/03, CR-A-W01-01 still
 * PENDING). It exposes VCC/GND/RXD/TXD only - no DE//RE pin - so the default
 * build must not toggle a direction pin. The canonical MAX3485 3.3 V module
 * with explicit DE//RE is supported as CG_RS485_DIR_MANUAL, but it is not
 * the as-built configuration.
 *
 * Electrical safety is a wiring concern, not something this driver can fix:
 * the module's TTL output idles at 5 V and MUST reach the ESP32-S3 through a
 * level shifter/divider. Never connect it to a GPIO directly.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    CG_RS485_DIR_AUTO = 0,
    CG_RS485_DIR_MANUAL = 1,
} cg_rs485_dir_mode_t;

/* Configures UART1 from coldguard_config.h. Returns false on any ESP-IDF
 * error; the caller must log the failure and must not transmit blindly. */
bool cg_rs485_init(void);

/* Sends one frame. In MANUAL mode the DE//RE pin is asserted around the
 * transfer and released after the last stop bit. */
bool cg_rs485_write(const uint8_t *data, size_t len);

/* Reads up to `want` bytes, waiting at most `timeout_ms`.
 * Returns the number of bytes read (0 on timeout) or -1 on driver error. */
int cg_rs485_read(uint8_t *buffer, size_t want, uint32_t timeout_ms);

/* Drops stale bytes before a new request. */
void cg_rs485_flush_input(void);

/* Compile-time mode for provenance logging. */
cg_rs485_dir_mode_t cg_rs485_dir_mode(void);
