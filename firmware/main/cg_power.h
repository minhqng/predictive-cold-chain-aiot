/*
 * ColdGuard firmware - PZEM-017 polling task and serial log lines
 * (Member A, W03).
 *
 * This module owns the poll loop, the bounded retry behaviour, the
 * read-only range verification and the `#CG PZEM*` log lines that the host
 * tools consume. It produces observations only: it never writes a PZEM
 * configuration register and it never touches the cooling branch.
 *
 * Failure semantics (docs/01 PHY-PZ-001): a poll that fails is logged with
 * its classified status and `nan` values. The previous value is never
 * carried forward, so a stale number can never look like a live one.
 */
#pragma once

/* Creates the poll task. Returns immediately; on RS-485 init failure the
 * task logs `#CG ERR` and exits without polling. */
void cg_power_start(void);
