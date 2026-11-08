/*
 * ColdGuard firmware - ESP-IDF I2C transport for the BME280 producer (A-W02-06).
 *
 * This is the only file in the producer that knows about the I2C driver. The
 * decision logic - what a reading means, when a module counts as absent, when a
 * transaction has to back off - lives in cg_bme280.c behind the injected
 * cg_bme280_port_t, so a host harness can execute that logic unchanged. Keeping
 * the split honest is what lets firmware/tools/tests/cg_bme280_harness.c prove
 * the refusal behaviour without silicon.
 *
 * The error mapping below follows ESP-IDF v6.1 `driver/i2c_master.h` as
 * installed, not as remembered:
 *   i2c_master_transmit / i2c_master_transmit_receive
 *       ESP_ERR_INVALID_RESPONSE -> the slave NACKed the address
 *       ESP_ERR_TIMEOUT          -> bus busy or hardware crash
 *   i2c_master_probe
 *       ESP_ERR_NOT_FOUND        -> no device answered that address
 * A NACK is reported as CG_BME_PORT_NACK, which the producer turns into a
 * declared ABSENT state; a timeout stays separate so "wired but silent" and
 * "not fitted" do not collapse into one another.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "cg_bme280.h"

/* Builds the I2C master bus on the as-built pins, selects the device address by
 * probing the two strap addresses, and fills `port` with the transport the
 * producer calls. `address_out`, when given, receives the address that was
 * selected. Returns false only when the bus or the device could not be created
 * at all - a device that simply does not answer is not an open() failure, it is
 * an ABSENT observation, because the producer must still be able to say so. */
bool cg_bme280_idf_open(cg_bme280_port_t *port, uint8_t *address_out);

/* The address currently bound to the device handle, 0 before a successful open. */
uint8_t cg_bme280_idf_address(void);

/* True once cg_bme280_idf_open() has produced a usable device handle. */
bool cg_bme280_idf_bus_ready(void);
