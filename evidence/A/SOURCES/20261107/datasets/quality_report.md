# ColdGuard real-data quality report

Generated: 2026-11-08T10:41:48.235+00:00

Interpretation rules: Tmean air = mean(T1,T3,T4) only when all three report OK; T2 is hot-side and never enters the air mean; nan means missing; quality from the frame's own *_status tokens. Host wall-clock stamps come from the monitor log (host-side), while the device reports timestamp_utc=UNAVAILABLE (no wall clock).

- Total real runs/segments exported: 18
- S1 runs: 4 (trial1 standalone boot c20d17f6, trials 2-4 contiguous on one boot 4a21a645)
- S2 door runs: 4 single boot 73311d0c
- Cooling steps (real TEC actuation): 1

## Independence caveats (carried, not hidden)

- S1 trials 2-4 are contiguous windows of one boot; the S1 acceptance result A-W09-02 (2026-11-07) is recorded in the authoritative store with these windows counted per the Doc 03 plan. Do not recount these windows anywhere as additional independent sessions.
- All four S2 door runs share one boot (73311d0c); A-W10-03 counts them as the canonical repeated pilot series per its recorded criterion.

## Per-run quality

| run | scenario | frames | thermal OK | elec OK | door UNVERIFIED | max gap s | faults |
|---|---|---:|---:|---:|---:|---:|---|
| W10-02 | S2_TIMING | 120 | 120 | 120 | 0 | 1.114 | {"0x00000000": 120} |
| W10-03-run1 | S2_DOOR | 300 | 300 | 300 | 0 | 1.119 | {"0x00000000": 300} |
| W10-03-run2 | S2_DOOR | 300 | 300 | 300 | 0 | 1.113 | {"0x00000000": 300} |
| W10-03-run3 | S2_DOOR | 300 | 300 | 300 | 0 | 1.119 | {"0x00000000": 300} |
| W10-03-run4 | S2_DOOR | 300 | 300 | 300 | 0 | 1.18 | {"0x00000000": 300} |
| S2-20261107-between-window | S2_OUTSIDE | 346 | 345 | 344 | 1 | 300.987 | {"0x00000000": 346} |
| trial2 | S1 | 600 | 600 | 600 | 0 | 1.115 | {"0x00000000": 600} |
| trial3 | S1 | 600 | 600 | 600 | 0 | 1.115 | {"0x00000000": 600} |
| trial4 | S1 | 601 | 601 | 601 | 0 | 1.115 | {"0x00000000": 601} |
| S1-20261107-between-window | S1_OUTSIDE | 62 | 61 | 60 | 1 | 1.03 | {"0x00000000": 62} |
| trial1-imported | S1 | 600 | 599 | 598 | 1 | 1.112 | {"0x00000000": 600} |
| H8-C-600s-TEC-100pct | COOLING_STEP | 957 | 957 | 957 | 17 | 1.0 | {} |
| H8-E-1800s-TEC-100pct | COOLING_STEP_1800S | 2915 | 2915 | 2913 | 14 | 1.0 | {} |
| a-w07-02-run-1-4b555191 | W07_PASSIVE_REPEAT | 300 | 0 | 0 | 0 | 1.034 | {"0x00000000": 300} |
| a-w07-02-run-2-4b555191 | W07_PASSIVE_REPEAT | 300 | 0 | 0 | 0 | 1.079 | {"0x00000000": 300} |
| a-w07-02-run-3-4b555191 | W07_PASSIVE_REPEAT | 300 | 0 | 0 | 0 | 1.037 | {"0x00000000": 300} |
| a-w07-03-trial-2-be89bf4a | COOLING_STEP_500PERMILLE | 196 | 196 | 196 | 196 | 1.038 | {"0x00000000": 196} |
| a-w07-03-trial-3-f44c9bed | COOLING_STEP_500PERMILLE | 196 | 196 | 196 | 196 | 1.035 | {"0x00000000": 196} |

## Scenario gates

- S1 trial2: 600 frames, coverage(3-of-3 thermal OK) 1.0000 (gate >=0.85), tmean mean 29.8021 C, gradient max 0.4375 C
- S1 trial3: 600 frames, coverage(3-of-3 thermal OK) 1.0000 (gate >=0.85), tmean mean 29.8453 C, gradient max 0.4375 C
- S1 trial4: 601 frames, coverage(3-of-3 thermal OK) 1.0000 (gate >=0.85), tmean mean 29.8589 C, gradient max 0.4375 C
- S1 trial1-imported: 600 frames, coverage(3-of-3 thermal OK) 0.9983 (gate >=0.85), tmean mean 29.4624 C, gradient max 0.4375 C
- S2 W10-03-run1: door durations [13.029], rise peak 0.041 C, baseline 29.8132 C
- S2 W10-03-run2: door durations [13.973], rise peak 0.0534 C, baseline 29.8424 C
- S2 W10-03-run3: door durations [13.999], rise peak 0.0309 C, baseline 29.9274 C
- S2 W10-03-run4: door durations [13.979], rise peak 0.0215 C, baseline 29.9785 C
- H8-C-600s-TEC-100pct: 957 frames / 955.99 s, current mean 4.5378 A max 9.99 A, hot-side max 39.938 C (gate <= 55 C), chamber drop 8.7083 C, faults {}

## Classification policy

- DATASET_ACCEPTED_S1 / DATASET_ACCEPTED_S2: runs backing PASS results in the authoritative store (A-W09-02, A-W10-03) - usable now for scenario analysis.
- REAL_PHYSICAL_RAW / RESEARCH_ONLY: real TEC-actuated bench captures (H8S bench grammar, test_mode=BENCH_ENDURANCE). Real cooling physics, but the canonical actuation acceptance (A-W08-03) requires the supervised stage-enabled W06 session; these captures cannot close it offline.
- WARMUP_SEGMENT: real frames preceding a timed run window; kept, never deleted, not counted as independent runs.