# ColdGuard · Data-Readiness Contract v1 (W08, Member B)

Status: **draft implementation contract for B-W08-01 … B-W08-04**.
Authority: Doc 03 §§5–8, 46–49, 119–123; Doc 01 §§18–20, 33; Doc 05B §36;
Doc 04 W08 / Gate G2. This document does not modify those canonical sources.

## 1. Scope and authority

W08 decides whether the physical/digital data path is ready for a real dataset
campaign. It does **not** train a model, implement W09 baselines, select W10
features, freeze a lock, or replace W12 evaluation.

- A's validity ledger is authoritative. B never promotes A-INVALID to A-VALID.
- A-valid evidence without matching source identity, quality and event coverage
  does not automatically pass Gate B.
- Conflicting A ledger/source identities fail closed.
- A scientific `RED` is a successful CLI result, not a software exception.

## 2. Separated status domains

The report keeps these domains distinct; a GREEN one never erases a RED one.

```text
STRUCTURAL_VALIDITY
DIAGNOSTIC_USABILITY
PHYSICAL_RUN_VALIDITY
SCENARIO_ELIGIBILITY
DATASET_READINESS
SPLIT_FEASIBILITY
```

`W08_SOFTWARE_VERIFICATION`, `GATE_B_PHYSICAL_DATA`,
`PREDICTIVE_DATASET_READINESS` and `SPLIT_FEASIBILITY` are reported as
separate gates. W08 software may be GREEN while Gate B is RED.

## 3. Run validation (B-W08-01)

Every candidate is evaluated read-only. Stable reason codes come from the
failing check; no evidence is rewritten.

### Identity and lineage

- source SHA-256 and recognized schema namespace;
- physical provenance;
- authoritative `run_id`, `boot_id` and `device_id`;
- unique `(device, boot, seq)` and monotonic sequence;
- run manifest linkage (run, boot, device, scenario, hardware, calibration,
  source hash, optional pair/controller);
- declared planned capture duration;
- scenario designation and A-ledger scenario scope.

### Physical configuration

- verified hardware-configuration identity;
- one authoritative `run_id` per physical source; the same `run_id` on two
  physical sources is a suite-level contradiction and blocks Gate B;
- firmware identity and controller identity where the analysis needs it;
- verified calibration identity;
- probe ROM identity, positions and chamber-air roles; at least three
  distinct chamber-air roles are required for the canonical thermal
  population (a hot-side-only sensor block cannot pass vacuously);
- declared physical units for required channels.

### Measurements

- required thermal/door/electrical channel presence;
- source-quality states, missing and invalid values counted separately;
- sequence/timestamp reversals, resets and impossible intervals; the window
  axis is event UTC or boot uptime, matching W05, and must be non-decreasing;
- trusted time domain and clock synchronization for an absolute-time claim;
- PZEM qualification only where the declared analysis claims electrical
  evidence;
- door qualification only where the scenario requires a disturbance.

### Protocol and events

- planned versus observed scenario;
- required event anchor (S2: first qualified CLOSED→OPEN transition);
- pre-event baseline, primary event window and recovery/follow-up coverage;
- command/ACK/applied chain only when the declared analysis requires it;
- intervention and censoring status.

A passive telemetry diagnostic does not need a command chain. An analysis that
claims command/electrical evidence does.

## 4. Completeness policy (B-W08-02)

Dimensions:

```text
WHOLE_CAPTURE_COMPLETENESS
PRIMARY_EVENT_WINDOW_COMPLETENESS
PRE_EVENT_BASELINE_COMPLETENESS
POST_EVENT_OR_RECOVERY_COMPLETENESS
CRITICAL_CHANNEL_COMPLETENESS
TIMING_ALIGNMENT_COMPLETENESS
```

Rules:

- expected counts use the observed acquisition cadence, never a filename;
- whole-capture completeness uses the **declared planned capture duration**,
  never the observed partial window;
- rows outside the declared planned interval are excluded from the numerator,
  and a capture ending before the planned end cannot pass;
- event-window completeness is evaluated separately and cannot be hidden by a
  high whole-run percentage;
- missing, INVALID and untrusted critical samples are counted distinctly;
- missing event anchors are `NOT_ESTIMABLE` or blocked;
- an `UNRESOLVED` threshold is not replaced by zero;
- numeric defaults in the draft policy are `PROPOSED`, not frozen;
- `FROZEN` requires recorded `freeze_evidence`; a status string alone is not
  an approval.

A `PROPOSED` blocking cutoff never silently becomes an approved scientific
cutoff. A measured dataset evaluated under an unfrozen policy is at most
`YELLOW`: diagnostic analysis remains allowed, while a frozen-dataset,
predictive-campaign or benchmark claim is prohibited and the unresolved owner
and review authority are named. A frozen, evidenced policy may reach `GREEN`.

A synthetic fixture passed with `synthetic_control=True` may exercise the
GREEN software branch as a contract positive control. It is reported as
`DATA_ORIGIN = SYNTHETIC_CONTROL_ONLY`, its predictive dataset stays
`NOT_READY`, and it never certifies measured physical data.

The draft policy lives in `coldguard-w08-completeness-policy-draft-v2` and is
rendered as `completeness-policy-W08.md`. A report may not combine validation
results computed under one policy with a different reported policy: a
threshold/status/equality mismatch is a RED gate reason
(`THRESHOLD_POLICY_MISMATCH`).

## 5. Gate decision model (B-W08-03)

- **RED** — a hard scientific prerequisite is missing or violated: A-INVALID,
  unresolved/contradictory run identity, uncertified scenario, required event
  absent, critical channel unqualified, no eligible runs, unresolvable
  schema/timing lineage, insufficient independent-run population, or a
  required contract not met.
- **YELLOW** — the declared limited purpose is supported, but a named
  noncritical/provisional condition remains. Allowed and prohibited uses are
  explicit; it never overrides a RED blocker.
- **GREEN** — all hard requirements for the declared purpose are satisfied
  with authoritative evidence. Script success alone is not GREEN.

Aggregation is fail-closed: a hard RED cannot be outvoted by GREEN supporting
checks, and a higher-quality source value cannot erase a contradictory A
ledger.

## 6. Split planning (B-W08-04)

- split independent physical runs, not rows or windows;
- group by `run_id`; a `pair_id` keeps both arms in one group;
- repeated views of one physical source are one group;
- contradictory run identities on one physical source cannot create groups;
- conflicting eligibility, reason, scenario, controller, pair or hardware
  values on one physical source exclude the whole group from every partition;
  every disputed value is retained in the exclusion report and pair lineage is
  never silently overwritten;
- source filenames and input ordering never decide scientific eligibility;
- direct `SplitCandidate` inputs are a trust boundary: `eligible=True` is
  honoured only with an A-Ledger `VALID` verdict and the deterministic W08
  eligibility receipt; bare booleans and missing provenance fail closed;
- P1 = training/fitting, P2 = held-back development validation,
  P3 = future locked test; development = P1 ∪ P2;
- P3 is **not frozen** and no locked-test manifest is created or inspected;
- insufficient population yields `NOT_FEASIBLE` with no assignments;
- the illustrative ~16/4/4 shape for ~24 runs is a planning candidate only.

## 7. Artifacts and provenance

```text
gate-b-readiness-W08.md
run-validation-W08.csv
completeness-policy-W08.md
development-split-plan-W08.md
gate-b-manifest-W08.json
```

The manifest records source SHA-256 values, the A-index SHA-256, analysis-code
SHA-256, repository revision, generation command, schema/layer versions,
completeness-policy version, run groups, decisions and reason codes. Output
ordering and numerical formatting are deterministic.

After writing, the CLI re-reads the manifest and CSV, verifies every artifact
hash and the gate/eligibility agreement, and fails with a software error if the
written artifacts disagree. Scientific RED still exits 0.

## 8. Current real-data expectation

Absent newer independently verifiable A evidence:

```text
W08 software: GREEN (validator produced a complete report)
A physical validity: INVALID
eligible S1: 0
eligible S2: 0
Gate B physical data: RED
predictive dataset: NOT_READY
split feasibility: NOT_FEASIBLE
```

This is the scientifically correct result. A synthetic GREEN fixture proves
the software logic only and is never physical dataset readiness.
