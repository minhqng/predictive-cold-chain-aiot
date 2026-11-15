/*
 * ColdGuard H6 - state-machine self-test.
 *
 * The same assertions that would run on a host are compiled into the image
 * and executed once at boot, before ARM is possible, against local instances
 * only. It never touches s_sm, the GPIOs, the LEDC or the PZEM.
 *
 * This exists because the build machine has no host C toolchain (esp-clang
 * has only the ESP backends); running on the target proves the shipped
 * machine code, not a re-implementation.
 */
#pragma once

#include <stdbool.h>

/* Returns true when every check passed. Outputs are always written. */
bool h6_selftest_run(unsigned *checks, unsigned *failures, int *first_failure_line);
