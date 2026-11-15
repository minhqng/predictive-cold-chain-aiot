/*
 * ColdGuard firmware - TEC commissioning task (W04).
 *
 * Owns the controller, the command queue and the telemetry cadence. The
 * local console only posts commands; every state transition happens here,
 * on one task, at a fixed cadence, so the bounded duration and the heartbeat
 * supervision are real.
 */
#pragma once

#include <stdint.h>

/* Starts the controller in OFF, prints the boot authorization token, the
 * limit table and the TEC state, then creates the console and the 100 ms
 * supervision task. The output stage stays compiled out. */
void cg_commission_start(const char *boot_id, uint32_t boot_count);
