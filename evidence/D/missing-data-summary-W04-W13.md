# Member D W04-W13: main refresh and remaining acceptance evidence

**Reviewed:** 2026-11-09 against `origin/main` `d22c8d5`

**Scope:** Member D PRs #81-#90, after merging current main

**Decision boundary:** source evidence may move an item from missing to reviewable;
it does not by itself declare a physical PASS, G1/G2/G3, or Controller B enablement.

## What current main newly provides

| Main source | Review result | D weeks helped | What it does not close |
|---|---|---|---|
| A PR #91 S1/S2 source, PR #95 supplementary S1, plus normalized handoff (`manifest.json`, 18 runs/segments, 9,293 frames) | PR heads and raw hashes are pinned: four PASS S1 windows (2,401 frames), four PASS S2 door windows (1,200 frames), plus one PR #95 read-only S1 run (600 frames). The normalized package also provides one S2 timing window and four real cooling captures marked `NOT_SCENARIO_QUALIFIED` | W05, W07, W09, W12, W13 | PR #95's run is supplementary and not admitted to the frozen package. Cooling steps are not the supervised A-W08-03 run; accepted S1/S2 is not a Controller A benchmark |
| A-W04-06 polarity result | `PASS`, hardware source, with measured chamber drop/hot-side rise and operator-recorded orientation | W04 | Boot/reset-OFF, enabled-stage device safety, frozen D limits, and G1 owner approval |
| A-W12-03 mechanical inspection | `PASS`, 5/5 checklist items confirmed with attached evidence | W04, W12 | The result notes that fuse-to-conductor ampacity is not certified; the older `gate-g3-input.json` is stale and no whole-team G3 decision exists |
| A-W21-02 degraded DS18B20 injection | `PASS` on a real ESP32-S3, single-role degradation and recovery observed | W10 | Software injection only; TEC output stage disabled and fuse removed, so it does not prove live actuator fail-safe behavior or C persistence |
| A-W21-03 PZEM transport-boundary injection | `PASS` on a real ESP32-S3, missing current not carried forward and recovery observed | W10-W11 | Software transport disable, not a natural/physical failure; no energized cooling-health diagnosis or incident-runtime trace |

Pinned source hashes are recorded in `main-update-assessment-20261109.md`.

## Remaining blockers after the refresh

| Priority | Remaining source data / decision | Owner | D weeks and acceptance blocked |
|---|---|---|---|
| 1 | Freeze D's physical limits and Controller A v1: representative temperature, upper/lower thresholds, hysteresis, persistence/dwell, hot-side stop, qualified OFF/ON current-power envelopes and policy version. Then run one supervised stage-enabled Controller A/cooling session with requested, applied, electrical and thermal state on one timeline. | A + D | W04, W07, W09, W12 |
| 1 | Resolve and sign the fuse/conductor ampacity deviation, complete enabled-stage boot/reset/interlock review, and record the designated G1/G3 owner decisions. The A-W12-03 inspection closes fixture/V1/terminal/cable confirmation only. | A / hardware owner / team gate owners | W04, W12 |
| 1 | Provide real command-lifecycle traces for expired, duplicate, wrong-device, out-of-range and invalid-state commands, including canonical ACK, dedup across relevant resets, applied state, no second physical effect, C persistence and UI/log interpretation. Main still has no production network command path. | A + C + D | W06, W12 |
| 2 | Run supervised broker/backend loss and reconnect: local thermal input, Controller A state, actuator state, stale desired-command rejection, reconciliation and G2 review. | A + C + D | W08 |
| 2 | Complete the cooling-health fault set under an approved safe protocol: missing electrical response while ON, degraded thermal effectiveness and unexpected current while OFF. Reuse A-W21-02/03 only for sensor/PZEM source cases, and add D oracle output plus C reason/evidence-window/incident persistence. | A + C + D | W10-W11 |
| 2 | Build the real Controller A/S2 replay set with independent admitted `run_id`s, a frozen controller/config, actual applied transitions, common clock, hashes and validity decisions. Current accepted S2 runs are useful door baselines but remain OFF and do not benchmark Controller A. | A + B + C + D | W12 |
| 3 | Close AIW timing: B warning time/EWT with uncertainty, D's frozen critical threshold, A door-open-to-critical distribution under that threshold, and C sensing-to-device-command/applied latency on compatible clocks. Existing A data provides cooling timing and door runs, but no joined project AIW chain. | B + A + C + D | W13 and W14 gate |

## Ten-week status (W04-W13)

| Week | D-owned implementation | Evidence status after main refresh | Final acceptance |
|---|---|---|---|
| W04 | Complete at contract/unit level | Polarity and post-freeze inspection now reviewable | OPEN: enabled-stage safety, fuse/conductor disposition, G1 |
| W05 | Complete at contract/unit level | Qualified real telemetry now exists for replay | OPEN: runtime freshness/stale integration trace |
| W06 | Complete at pure-validator level | No new network command lifecycle evidence | OPEN |
| W07 | Controller A candidate and synthetic replay complete | Passive repeats and non-qualified cooling captures available | OPEN: measured config and supervised Controller A run |
| W08 | SAFE_LOCAL session logic complete | No new broker-loss/reconnect run | OPEN: G2 |
| W09 | Verification state machine complete | Electrical-quality gap in the old 957-row export is superseded; real qualified cooling data exists | OPEN: canonical supervised envelope/healthy-response acceptance |
| W10 | Fault protocol/oracles complete | A-W21 DS18B20 and PZEM cases hash-pinned and matched to D's non-energized source oracles | PARTIAL: runtime diagnosis events and remaining fault cases open |
| W11 | Incident-action candidate complete | PZEM degradation source behavior matches D's oracle | OPEN: energized cooling-health cases, runtime diagnosis and C persistence |
| W12 | Replay contract/G3 inventory complete | Accepted S2 data and mechanical inspection available | OPEN: real Controller A benchmark, lifecycle proof, team G3 |
| W13 | AIW calculator and policy semantics complete | 30.5 C candidate evaluated on 4 accepted S2 runs; none crosses it | OPEN: justified/frozen threshold plus crossing capture, B warning distribution, C end-to-end latency/common clock |

## Minimum package for each new physical run

Provide a Doc 03 section 5 manifest with `run_id`, `pair_id`, `scenario_id`,
`controller_id`, operator/date, hardware/pin-map/firmware/backend/schema and
calibration/policy versions, initial conditions, disturbance protocol,
start/end times and a predeclared validity decision. Preserve raw command,
ACK, device applied-state, electrical, thermal and event records on one run
timeline; attach source file hashes and clock-domain/quality annotations.
Screenshots or a dashboard can supplement this package but cannot replace it.

## Next D actions when owner inputs arrive

1. Freeze the Controller A/safety configuration with A and publish versioned numeric limits.
2. Replay the accepted main datasets through D quality/verifier code and publish per-run `PASS/FAIL/UNKNOWN` without upgrading non-qualified captures.
3. Replay A-W21-02/03 through the D fault oracle, then hand the reason/evidence-window contract to C for persistence.
4. Rebuild the W12 matrix from current sources; do not use the stale A `gate-g3-input.json` as if it reflected the new inspection/data package.
5. Keep the 30.5 C result right-censored unless a longer/hotter admitted S2 run crosses it or the team justifies a threshold revision; compute AIW only after B/A/C timing spans share compatible provenance and non-overlapping clock semantics.

References: `docs/03-verification-experiments-demo-coldguard.md` section 5;
`docs/05D-member-d-control-security-resilience.md` W04-W13;
`evidence/D/closure-plan-W04-W13.md`.
