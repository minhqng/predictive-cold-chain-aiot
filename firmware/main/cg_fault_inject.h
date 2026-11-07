/*
 * ColdGuard firmware - test-only reversible fault injection (A-W21-02/03).
 *
 * This module exists so ONE supervised device session can exercise the two W21
 * degraded-input scenarios without disconnecting any sensor or wiring:
 *   - A-W21-02: make exactly one selected DS18B20 ROM report unavailable,
 *     leaving the shared conversion, the other probes and the frozen ROM-to-role
 *     map untouched.
 *   - A-W21-03: make the PZEM producer's poll fail so the real missing-data
 *     path runs (no synthetic voltage/current/power, no carried-forward value).
 *
 * Safety contract:
 *   - Entirely disabled unless CG_FAULT_INJECTION is set by an explicit test
 *     build. With the flag 0 every predicate is false, the console line is never
 *     consumed, and no injected state exists at all (see the #else branch), so a
 *     production image cannot activate or even reach this path.
 *   - The only control path is the local operator console line. There is no
 *     network or TEC-command entry point into these setters, and the console
 *     hook in cg_console.c is itself compiled out when the flag is 0.
 *   - State lives in RAM only, so a reboot clears it (cg_fault_inject_reset is
 *     also the explicit "FAULT CLEAR" path). Nothing is persisted to NVS.
 *   - It never touches the actuator: enabling cooling is not part of any
 *     injection and the output stage stays compiled out in the default build.
 *
 * The module is pure C with no ESP-IDF dependency so the host harness
 * firmware/tools/tests/cg_fault_inject_harness.c can execute the real decision
 * logic (selection, single-ROM isolation, console parsing, reboot-clear and the
 * production-disabled case) without silicon.
 */
#pragma once

#include <stdbool.h>

/* True only in a test build (CG_FAULT_INJECTION=1). */
bool cg_fault_inject_enabled(void);

/* True when the given cg_role_t index is the single injected-down DS18B20. */
bool cg_fault_inject_ds_active(int role);

/* True when the PZEM producer poll must be forced to fail. */
bool cg_fault_inject_pzem_down(void);

/* The currently injected DS role index, or -1 when none. Test-build only;
 * used solely to echo state for operator confirmation, never for actuation. */
int cg_fault_inject_ds_role(void);

/* If `line` is a FAULT command, apply it and return true so the caller does not
 * forward it to the TEC command parser. Non-FAULT lines return false. */
bool cg_fault_inject_console_line(const char *line);

/* Clear all injected state (explicit reset and the model of a reboot). */
void cg_fault_inject_reset(void);
