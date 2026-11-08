# PWM Go/No-Go (A-W15-04) - decision: NO-GO

Recorded by Member A, offline, no new actuation requested.

## Basis (all OBSERVED in-tree today)

1. Canonical console command set: the firmware gate constant is `CG_TEC_REQUEST_DUTY_PERMILLE 0` (firmware/main/coldguard_config.h:475): the as-built TEC has no established continuous rating, so no duty is claimed safe. A console START therefore cannot request a characterized duty; the canonical command matrix defines duty acceptance only for a PWM-enabled configuration and rejects duty outside the characterized range (CM-23..CM-25, evidence/D/W03/command-matrix.md).
2. No characterized duty ladder exists for the canonical console: no multi-duty  settlements under CG-HW-001 with the canonical firmware were captured (the only multi-duty data is the H8 bench grammar fixture set: 500 permille trials and 100 % 60 s/600 s/1800 s steps, a different return path with BENCH_ENDURANCE test mode).
3. Measured PWM-adjacent behaviour available: H8-C 600 s at 100 % duty (9.99 A max, hot-side max 39.94 C, no faults, chamber drop measured), H8-E 1800 s at 100 % duty, and the 500 permille W07-03 trials referenced by A-W08-02 (peak 5.03 A).
4. Limitation recorded: no energy-aware duty mapping (power vs duty monotonicity, aliasing at 1000 Hz PWM under the PZEM sampling cadence) has been characterized on the canonical console.

## Decision

**NO-GO** for energy-aware duty control now; revisit after the W16 re-characterization captures exist (A-W16-01) and only with an authorized supervised campaign. NO-GO is the criterion-sanctioned outcome and does not block other work.
