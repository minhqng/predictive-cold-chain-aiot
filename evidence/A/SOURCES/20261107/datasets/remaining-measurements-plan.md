# Remaining physical measurements - focused plan (2026-11-08)

Ledger after this session: **79 PASS / 2 FAIL / 7 INCOMPLETE / 26 NOT_RUN** of 114 (baseline was 78/2/7/27; A-W15-04 closed).

## What is genuinely missing, with exact counts

| Requirement | What is missing | New captures needed | Blocking authorization |
|---|---|---|---|
| A-W11-03 Dataset expansion | 1 additional valid S1 session (600 s, coverage >= 0.85) beyond the 4 recorded for A-W09-02 | 1x S1 600 s | none (read-only; collector: `s1` SOURCES flow) |
| A-W08-03 Hot-side sustainability | 1 supervised 600 s COOLING_STEP on the stage-enabled W06 image with qualified V/I/P status | 1x COOLING_STEP 600 s | D freezes hot-side limits; rebuild+flash consent; slot-3 fuse cold inspection; ARM/START consent |
| A-W09-04 Healthy response reference | offline once A-W08-03 PASS exists | 0 | - |
| A-W16-01 Re-characterization | OFF 120 s + ON step 120 s + 1x S2 180 s on stage-enabled W06 | 3 | same session as A-W08-03 (one supervised visit) |
| A-W16-02 / A-W16-03 | offline compares + joint tolerance freeze with B | 0 | B sign-off |
| A-W10-05 / A-W13-03 | frozen critical Tmean threshold (Member D) - then offline rerun over the existing 4 S2 runs | 0 measurements | D |
| A-W14-04 / A-W16-03 | pair-matching tolerance freeze (initial Tmean + gradient) - evidence ready | 0 measurements | B (and D for reset refs) |
| A-W17-01..04 Shadow | S2 trajectories with B/D shadow decisions while Controller A stays the authority | several (4 planned) | B/D shadow models + supervised session |
| A-W19-02 / A-W20-01/02 A/B campaign | real A/B pairs per the W19/W20 campaign wave protocol (runbook + admission validators already in `_w19-guards-local` / `_w20-pair-local`) | per campaign plan | supervised actuation + B |
| A-W06-01/02/03/06 | network command transport (Member B/C/D) | 0 physical | B/C/D |
| A-W23-03 Labels | physical labels (operator-deferred) | 0 measurements | operator |
| A-W24-02/03/04 | final HIL smoke + handover after the above | follow-ups | - |

## One bundled supervised session (no scattered bench work)

All TEC-touching captures above collapse into the already-prepared session plan `C:/cgb/physical-session-w08-w16-plan.md`: D freezes limits -> fuse cold inspection -> authorized rebuild+flash of W06 stage-enabled -> one supervised visit captures A-W08-03 (600 s) + A-W16-01 (3 captures). Everything else is offline once that single session lands plus one read-only S1 session for A-W11-03 (no authorization needed beyond normal read-only capture).

## Auto-evaluation when new raw arrives (existing tooling reused)

- Canonical capture: `A-acceptance-app/tools/acceptance/read_only_capture.py` and the member_a_app GUI runner (`py -3 tools/member_a_app/app.py`) - the run_series handlers validate runs live and write store results directly.
- Offline S1/S2 re-evaluation of a dropped raw log: rerun `_local_handoff/coldguard_real_data_export.py`; it re-parses every raw source, recomputes per-run statistics and flags which entries would now qualify.
- Nothing is flashed, energized or re-limited by these tools; passing requirements are never re-measured.
