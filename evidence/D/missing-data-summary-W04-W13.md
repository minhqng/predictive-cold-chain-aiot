# Member D W04-W13: missing data and acceptance evidence

Status as reviewed for PRs #81-#90. This is a request for source evidence, not
an assertion that a physical test passed. D code and synthetic tests are
reviewable; the items below still prevent final physical acceptance. Owners
retain their own source artifacts; D will pin hashes and publish a derived
PASS/FAIL/UNKNOWN review when those artifacts exist.

| Priority | Missing source data / decision | Owner | D weeks and acceptance blocked |
|---|---|---|---|
| 1 | Qualified current and voltage channel status for each sampled frame, valid OFF current and ON current/power envelopes, applied cooling state, and thermal baseline/follow-up over independent runs. The A W09 export has **957 `UNKNOWN` electrical rows** and no eligible S1 run. | A | W05, W07, W09, W11, W12; physical cooling verification and G3 |
| 1 | Post-freeze inspection record for sensor fixtures, V1 mounting, terminals and cable routing; resolved fuse/conductor deviation; first-actuation safety review and G1 owner decision. | A / hardware owner | W04, W12; physical safety and G3 |
| 1 | Frozen Controller A representation and measured thresholds, hysteresis, persistence/dwell and policy version; repeated comparable plant runs and one supervised real Controller A run. | A + D | W07, W12; measured controller benchmark |
| 2 | Device command lifecycle traces for expired, duplicate, wrong-device, out-of-range and invalid-state commands: canonical command, device receipt, rejection/ACK, dedup across relevant resets, applied state and no second physical effect. Include C persistence and UI/log interpretation. | A + C + D | W06, W12; end-to-end command proof |
| 2 | Supervised broker/backend-loss and reconnect run: local thermal inputs, controller state, actuator state, stale desired-command rejection, reconciliation and G2 owner review. | A + C + D | W08; SAFE_LOCAL physical proof and G2 |
| 2 | Safe S4 fault-injection captures for missing electrical response, degraded thermal effectiveness, unexpected current while OFF, sensor degradation and PZEM loss. Each capture needs an approved test-mode/protocol record, expected oracle and observed diagnosis; C must persist the reason, evidence window and incident state. | A + C + D | W10-W11; live diagnosis and incident actions |
| 2 | Admissible S2 benchmark runs and replay inputs: independent `run_id`s, validity decisions, raw files with SHA-256, qualified sensor/electrical data, initial conditions, actual applied transitions and a common clock. The current D replay contract has no admitted real run set. | A + B + C + D | W12; benchmark and G3 |
| 3 | AIW timing chain: B's qualified warning time/EWT with per-component span, clock, method and uncertainty; A's door-open-to-critical trajectory and physical response distribution under frozen configuration; C's sensing-to-device-command/applied latency. Join on event/run/hardware provenance and reject overlapping spans. | B + A + C + D | W13 and W14 gate; project AIW and Controller B enablement |

## Minimum package for each new physical run

Provide a Doc 03 section 5 manifest with `run_id`, `pair_id`, `scenario_id`,
`controller_id`, operator/date, hardware/pin-map/firmware/backend/schema and
calibration/policy versions, initial conditions, disturbance protocol,
start/end times and a predeclared validity decision. Preserve raw command,
ACK, device applied-state, electrical, thermal and event records on one run
timeline; attach source file hashes and clock-domain/quality annotations.
Screenshots or a dashboard can supplement this package but cannot replace it.

## Current source facts and decisions

- A W09 `CG-S1-H8C-600S.row-validity.csv` and `s1-run-index.json` are pinned in
  `evidence/D/W09/a-w09-source-crosscheck.json`: 957 rows have electrical
  quality `UNKNOWN`; source-admission verdict is `UNKNOWN`.
- A W12 `gate-g3-input.json` lists unqualified electrical measurements,
  post-freeze inspection and fuse/conductor deviation as open. D's
  `evidence/D/W12/g3-evidence-matrix.json` is `NOT_VERIFIED`; no team G3
  decision is claimed.
- A W13 `plant-timing-report.json` has no door-open-to-critical value and no
  backend-command-to-device latency. Command-to-electrical timing has **n=1**
  local console observation, not a distribution or network-command result.
- D's W13 AIW scalar calculation is a synthetic arithmetic candidate. B's
  component-span uncertainty and non-overlap conditions and A/C alignment
  are not yet demonstrated for one project run.

Once an owner supplies a package, D's next action is to validate schema and
quality, pin source hashes, replay the controller/verifier, compare intent
with observed applied and physical state, and publish a per-run reasoned
PASS/FAIL/UNKNOWN record. Do not infer G1, G2, G3 or predictive enablement
from the present synthetic tests.

References: `docs/03-verification-experiments-demo-coldguard.md` section 5;
`docs/05D-member-d-control-security-resilience.md` W04-W13;
`evidence/D/closure-plan-W04-W13.md`.
