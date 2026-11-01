/*
 * ColdGuard firmware - local operator console (W04).
 *
 * Reads command lines from UART0 (the same port as the log) and posts
 * parsed commands to the commissioning task. It never calls the controller
 * itself: one task owns the control state.
 */
#pragma once

#include <stdbool.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

#include "cg_tec_command.h"

/* Installs the UART driver and starts the reader task. Returns false when
 * the console is compile-time disabled or the driver cannot be installed. */
bool cg_console_start(QueueHandle_t command_queue);

bool cg_console_available(void);
