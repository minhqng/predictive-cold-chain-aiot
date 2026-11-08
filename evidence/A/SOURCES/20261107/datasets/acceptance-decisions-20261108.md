# Acceptance decisions from existing evidence (2026-11-08)

Store: `A-acceptance-app/evidence/A/h8-captures/capture-20261104T092140Z`
(the local acceptance store; per-requirement results in `results/`, history in `results/history/`).

## PASS written this session (validator-controlled, unique evidence)

### A-W15-04 PWM Go/No-Go - recorded NO-GO (decision PASS)
- Basis: `CG_TEC_REQUEST_DUTY_PERMILLE 0` (firmware/main/coldguard_config.h:475, docs/06 rationale), command-matrix CM-23..CM-25, and the absence of any characterized canonical-console duty ladder. NO-GO is the criterion-sanctioned outcome; no new actuation requested. Evidence attached as `pwm-go-no-go.md`.

## PASS considered and correctly withheld (with grounds)

### A-W08-03 hot-side sustainability - remains NOT_RUN
- The real H8-C 600 s TEC step (957 frames, boot 56044b74, max 9.99 A, T2 max 39.94 C, no faults) is exported in `raw/` + `datasets/`.
- A PASS is not recordable offline: the actuation handler refuses the H8S bench grammar replay by design; the six TEC limits are UNRESOLVED and the 55 C hot-side stop is PROVISIONAL pending Member D's freeze; the slot-3 fuse is physically removed pending cold inspection (see `C:/cgb/physical-session-w08-w16-plan.md`).
- The computation is kept in the store as a measurement-only record (`measurements/A-W08-03-*`); an earlier offline PASS was recorded and then reverted within this session (archived in `results/history/`). Requires: one supervised 600 s COOLING_STEP on the stage-enabled W06 image.

### A-W09-04 healthy response reference - remains NOT_RUN
- Prerequisite A-W08-03 open; envelope inputs retained as measurement-only.

## Re-verified existing PASSes (not re-adjudicated)
- A-W09-02 (S1 baseline, 4 runs), A-W10-03 (S2 pilot, 4 door runs), A-W10-04, A-W14-03, A-W15-01/02/03: independent source computations in this handoff (`measurement_summary.csv`) agree with the store records; the raw files and SHA-256 are in `raw/` and `manifest.json`.

## Explicitly kept open - inputs outside Member A's authority
- A-W10-05 / A-W13-03 (INCOMPLETE): the frozen critical Tmean threshold is Member D's safety contract. The 4 qualifying S2 runs already exist; once D freezes the threshold, the evaluation is a pure offline rerun (0 new physical measurements needed).
- A-W14-04: joint freeze with B; pairing evidence (A-W10-04) is complete.
