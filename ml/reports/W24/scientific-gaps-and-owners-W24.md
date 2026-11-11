# W24 scientific gaps and owners

> **Task:** B-W24-04. This file separates what Member B can close from what
> requires A, C, D or the project leader. It is an evidence ledger, not a plan
> authorization.

```text
GATE_B_PHYSICAL_DATA = RED
PREDICTIVE_DATASET_READINESS = NOT_READY
G3 = NO-GO / FIX DATA
REAL_PREDICTIVE_BENCHMARK = NOT_ESTABLISHED
W16_LOCKED_TEST = NOT_OPENED
W20_PHYSICAL_AB_ANALYSIS = NOT_RUN
G4 = NOT_READY
G5 = NOT_ESTABLISHED
SCIENTIFIC_ACCEPTANCE = INCOMPLETE
```

## 1. Resume order

The gates are sequential. Skipping a gate would invalidate the downstream result.

```text
A physical evidence
  -> Gate B GREEN
  -> predictive dataset readiness
  -> G3 GO
  -> frozen target/horizon/threshold/persistence
  -> W16 one-time locked test
  -> G4
  -> authorized physical A/B campaign
  -> W20 final analysis (effect, CI, p)
  -> G5
  -> team release
```

## 2. Gap ledger

| # | Gap | Current state | Why it blocks | Owner | Required evidence | Resume gate |
|---|---|---|---|---|---|---|
| G-01 | Device wall clock and clock synchronization | `ABSOLUTE_TIME_NOT_EVIDENCED` | Physical event time cannot be established; only boot-scoped uptime exists | A (with C telemetry) | Synchronized device/host clock trace and declared time domain | Gate B |
| G-02 | Measurement calibration identity | `CALIBRATION_UNVERIFIED` | Temperature/power values have no traceable calibration | A | Calibration record with identity and validity | Gate B |
| G-03 | Certified device identity and hardware configuration | Device identity missing; `HARDWARE_CONFIG_NOT_VERIFIED` | Runs cannot be tied to a verified rig configuration | A | Device serial/asset identity and as-built configuration record | Gate B |
| G-04 | Run identity and manifest linkage | Run IDs `UNSET` or segment-only; one boot contains multiple unresolved run IDs | Segments cannot be treated as independent runs | A | Unique run IDs linked to manifests and source hashes | Gate B |
| G-05 | Independent predictive-eligible run population | 18 segments / 8 boots / 0 eligible runs | No independent held-out group; no split is feasible | A | ≥3 evidence-grade independent runs per partition, with source pins | Gate B / readiness |
| G-06 | Critical target and representative temperature | `DEVELOPMENT_CANDIDATE_NOT_FROZEN` / `NOT_SELECTED` | No valid critical-event label can be defined | D (with B) | Frozen threshold, representative temperature, label definition | Freeze / G3 |
| G-07 | Primary horizon | `NOT_FROZEN`; 60 s is an engineering reference | Label and evaluation are not final | D (with B) | Frozen primary horizon with rationale | Freeze / G3 |
| G-08 | Operating threshold and warning persistence | `ILLUSTRATIVE_NOT_FROZEN` / `NOT_FROZEN` | No valid warning rule; AP alone is insufficient | D (with B) | Frozen threshold and persistence on development data | W16 preregistration |
| G-09 | Event matching and association policy | `SYNTHETIC_ILLUSTRATIVE` | Event recall/EWT matching is undefined | D (with B) | Frozen matching policy and tolerance | W16 preregistration |
| G-10 | Approvals and release authorization | 5 approvals absent; no release record | Locked test and Controller B cannot be authorized | Leader with A/B/C/D | Signed approval ledger and release authorization | W16 |
| G-11 | Locked-test evaluation | `NOT_OPENED`, `NOT_RUN` | No AP, recall, EWT, AIW or calibration result | B (operator) after G-01…G-10 | One authorized one-time evaluation receipt | W16 |
| G-12 | Real EWT / AIW | `NOT_ESTIMABLE` | No lead-time or action-window evidence | B (with A/C/D) | Qualified non-intervened trajectory and measured latency chain | G4 |
| G-13 | Physical Controller B authorization and safety | `NOT_READY`, `NOT_AUTHORIZED` | Physical control cannot be enabled | D + A + C + leader | Policy freeze, safety evidence, controller lifecycle and signoff | G4 |
| G-14 | Physical A/B campaign | `NOT_AUTHORIZED`, `NOT_STARTED_BLOCKED` | No accepted pairs; no final comparison | Leader + A + C + D | Authorized campaign, valid pair ledger, frozen outcome definition | W20 |
| G-15 | Final physical effect, 95% CI and p-value | `NOT_ESTABLISHED`, `NOT_COMPUTED`, `NOT_COMPUTED` | No real paired outcomes | B (computation) after G-14 | Admitted paired outcome table and executed W22 engine | W20 / G5 |
| G-16 | Live shadow and runtime evidence | `LIVE_SHADOW_NOT_ESTABLISHED`; no physical intervention trace | G4 requires shadow-capable inference and monitoring | C (with A/D) | Real synchronized shadow trace and signed runtime record | G4 |
| G-17 | Broker outage/resynchronization security | C PRs open/unmerged; no physical broker-loss trace | G4 requires reconnect and security baseline | C + D | Merged, tested implementation and physical outage evidence | G4 |
| G-18 | W21 raw diagnostic log | `SOURCE_UNAVAILABLE` | Recorded diagnostic checks remain `NOT_VERIFIED` | A | Raw W21 log with source hash | W21 evidence |
| G-19 | PR #95 supplement | Open/unmerged | Cannot be used as canonical evidence | A + leader | Merged canonical evidence | Gate B support |
| G-20 | Independent human replay | `PENDING` | Software handover lacks a second human receipt | Team member (any) | Completed replay receipt per the W24 template | Handover acceptance |
| G-21 | Team rehearsal and final release | Not recorded / not authorized | Member B cannot self-approve team events | Leader | Real rehearsal record and release decision | Project closeout |

## 3. Member B-owned actions

Member B's development scope ends with W24. Remaining B actions are support, not
new science:

- Keep the W24 inventory and handover manifest consistent with the delivered branch.
- Answer reproduction questions and fix defects inside `ml/` if the independent
  replay exposes one.
- Re-run the W24 deterministic checks after any accepted B-side fix.
- Provide the evidence map and Vietnamese defense material to the team.
- Do **not** refit the model, open W16, run W20, invent human receipts, or
  promote any gate.

## 4. Dependencies that are not Member B's to close

| Owner | Cannot be substituted by B | Consequence if absent |
|---|---|---|
| A | Clock, calibration, device identity, run identity, accepted runs, raw W21 log, PR #95 | Gate B stays RED; no predictive dataset |
| C | Telemetry time provenance, shadow trace, Controller B lifecycle, broker resilience | G4 stays NOT_READY; no live shadow |
| D | Target/threshold/persistence policy, safety rules, final campaign policy | No valid label; no W16/W20 authorization |
| Leader | Freeze approvals, release authorization, team rehearsal, final acceptance | No scientific acceptance or release |

## 5. What is verified now

- Software chain W01–W23 is implemented, tested and hash-pinned.
- The W15 model artifact matches its declared SHA-256.
- The real physical descriptive package reproduces byte-for-byte.
- 12 real physical plots exist and match their declared hashes.
- W16 correctly refuses to open the locked test; W20 correctly keeps analysis locked.
- W22 implements the prescribed paired statistics on toy fixtures.
- No prior artifact or gate was overridden by W24 packaging.

## 6. What remains unavailable

```text
FINAL_PREDICTIVE_RESULT_CSV = NOT_PRODUCED
FINAL_PHYSICAL_AB_RESULT_CSV = NOT_PRODUCED
REAL_LOCKED_PREDICTIVE_TEST = NOT_RUN
REAL_EWT = NOT_ESTIMABLE
REAL_AIW = NOT_ESTIMABLE
FINAL_PHYSICAL_EFFECT = NOT_ESTABLISHED
FINAL_PHYSICAL_CI = NOT_COMPUTED
FINAL_PHYSICAL_P_VALUE = NOT_COMPUTED
INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING
LIVE_TEAM_REHEARSAL = PENDING
```

These are not W24 packaging defects. They are missing scientific prerequisites
owned upstream in the chain above.
