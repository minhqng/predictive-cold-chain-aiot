# ColdGuard · Deterministic Baseline Contract v1 (W09, Member B)

Status: **software contract for B-W09-01 … B-W09-04**.
Authority: Doc 03 §§38–55, 46–49, 119–124; Doc 02 §§24–25;
Doc 01 §§18–20, 33; Doc 05B §37. This document does not modify those
canonical sources.

## 1. Scope and scientific boundary

W09 implements deterministic analytical baselines over the W04–W08 data path:

```text
W04 normalized capture
  → W05 timing/channel QA
  → W06 event-time and identity
  → W07 role-qualified representation
  → W08 run eligibility
  → W09 deterministic baseline replay
  → event-level evaluation/report
```

W09 does **not** train XGBoost, build W10 temporal features, open the locked
test, execute hardware, publish a command, or claim physical baseline
performance. A criterion detection is not an actuator command. An offline
replay is not a real Controller A verification.

Every replay carries its parameter status:

```text
FROZEN
PROPOSED
SYNTHETIC_ILLUSTRATIVE
PARAMETERS_NOT_FROZEN
```

A synthetic or illustrative configuration can exercise the software; it never
enters a scientific denominator. The real A W09 capture is A-invalid, so its
authoritative W09 result is `PARAMETERS_NOT_FROZEN` with event/false-warning
metrics `NOT_ESTIMABLE`.

## 2. Representative temperature

The representative is explicit, versioned configuration:

- `SINGLE_PROBE` — one named probe;
- `CHAMBER_AIR_MEAN` — mean over declared chamber-air slots;
- `CHAMBER_AIR_MAX` — max over declared chamber-air slots;
- unit must be `degC`.

Role qualification is enforced from the W04 sensor map. For the current rig:

```text
T1 = CHAMBER_CENTER
T2 = TEC_HOT_SIDE
T3 = CHAMBER_BOTTOM
T4 = CHAMBER_NEAR_DOOR
```

Any slot whose physical position is not chamber air is refused. T2 can never
enter a chamber-air mean/max, and unknown ROM/role records fail closed. A
diagnostic overlay may use the role-qualified T1/T3/T4 mean, but it is labelled
`DIAGNOSTIC_OVERLAY` and is not a frozen baseline choice.

## 3. B0 — stateless threshold baseline

Configuration requires:

```text
representation, threshold_c, operator (GE|GT), time domain,
quality requirement, threshold source, threshold status,
run/scenario provenance, maximum continuity gap
```

Semantics:

- evaluate each sample causally; no future sample and no future state;
- threshold equality follows the declared operator:
  `GE`: `T >= threshold`; `GT`: `T > threshold`;
- the first observed transition from not-satisfied to satisfied is one
  criterion crossing;
- a sample already above threshold at observation start is a left-censored
  crossing (`BEFORE_OBSERVATION_START`);
- a crossing is an interval `(previous evaluable sample, first observed
  satisfied sample]`; only exact equality yields an exact sample time;
- if a gap or refused interval spans a possible crossing, the certainty is
  `WITHIN_GAP` and no precise crossing instant is invented;
- repeated delivery of one sample identity is ignored: it creates neither a
  second crossing nor a second episode;
- INVALID/UNKNOWN thermal quality, missing probes, NaN/inf/bool/malformed
  values and stale probes are not substituted; they become refused intervals;
- mixed boot/device sessions and non-decreasing-time violations refuse the
  whole trajectory;
- the result contains criterion detections, never hardware commands.

## 4. B1 — reactive hysteresis baseline

B1 mirrors Member D's pure comparator exactly:

```text
T >= upper_on_c              → ON
T <= lower_off_c and ON      → OFF
lower_off_c < T < upper_on_c → HOLD prior legal state
```

The replay records the initial legal state and its evidence, prior state, each
transition, source sample, event time, policy version, quality/freshness
configuration and refused/undetermined intervals. An unavailable initial state
is `UNKNOWN` until the upper boundary establishes ON; OFF is never invented.

The offline state is **B's simulated reactive state**, not:
device-reported applied cooling, a command ACK, electrical actuation or a
thermal response. A transition means only that the mirrored policy would emit
that intent.

### D parity scope

Tests compare B1 against D's pure `_hysteresis` comparator on fixed synthetic
inputs. W09 does not mirror or claim D's fault priority, SAFE_LOCAL, device
modes, stale-input handling or the full `evaluate_policy` priority chain. A
pure hysteresis replay is not proof of D safety-layer behavior.

### Persistence / dwell

No source-authoritative Controller A reactive persistence/dwell is frozen.
D's `PolicyConfig.persistence_required_s` belongs to the predictive path and is
not reused. W09 offers an explicitly exploratory
`B1_PERSISTENCE_CANDIDATE` mode:

- persistence accumulates valid continuous elapsed seconds, not sample counts;
- it resets on invalid/missing input, untrusted time, excessive gap or a drop
  below the upper boundary;
- the exact elapsed-time boundary follows `elapsed >= required_s`;
- it is labelled `EXPLORATORY_NOT_CONTROLLER_A`, never Controller A.

## 5. S1 false-warning and stability analysis

Per run:

```text
observation duration     = last known time - first known time
evaluable time           = intervals with two evaluable endpoints inside the
                           declared continuity bound
unknown/untrusted time   = observation time - evaluable time
false-warning episodes   = unmatched warning episodes with trustworthy coverage
episode start/end        = policy-defined warning intervals
transition/toggle count  = observed criterion or ON/OFF changes
chatter                  = declared diagnostic rule over rapid toggles
warning burden           = episodes per eligible run and per eligible hour
```

A sustained warning is one episode, not one false warning per sample. A
no-event run contributes false-warning burden only when the run is eligible and
fully observed. An unknown/censored run is not a negative control.

For the current A W09 source (957 rows, A ledger INVALID, 0 eligible S1 runs):

```text
real S1 false-warning rate = NOT_ESTIMABLE
real S1 stability claim    = NOT_ESTABLISHED
real normal-run performance = NOT_ESTIMABLE
```

The 957 rows are not 957 independent exposure units.

## 6. Event-level evaluator

Typed events:

```text
REACTIVE_CRITERION_CROSSING
REACTIVE_ON_TRANSITION
REACTIVE_OFF_TRANSITION
WARNING_EPISODE
CRITICAL_EVENT
NO_EVENT_OBSERVATION
CENSORED_OBSERVATION
UNTRUSTED_INTERVAL
```

Each event retains its definition version and source/version. An ON transition
is not a thermal critical crossing. B0 criterion crossings may define critical
events only when that criterion is explicitly declared.

### Warning-episode policy

Versioned, explicit parameters:

- first valid warning onset;
- minimum persistence;
- bridging of gaps no longer than the declared gap parameter;
- reset after missing/untrusted data unless unknown-gap bridging is explicitly
  approved;
- episode termination on recovery, gap, run end or censoring;
- multiple warnings become multiple episodes;
- repeated delivery is deduplicated by sample identity only when the canonical
  warning payload (event time, state, quality) is identical; a contradictory
  duplicate identity is refused, never resolved by input order;
- distinct sample identities are never collapsed merely because their
  timestamps are equal;
- episodes are isolated per run/source.

### Association policy

A warning episode matches an observed critical event only when:

- the same eligible run/source is used: run identity and source content hash
  must be equal on both sides, and a missing `run_id` pairs only with another
  missing run identity from the same source — it is never a wildcard;
- the event-time domain is compatible;
- the episode onset lies inside the declared pre/post association window;
- the critical event is truly observed and trusted;
- the trajectory is not predictively intervened;
- matching is one-to-one; extra candidates are recorded as alternatives.

Evidence whose acquisition lineage does not match the evaluation is retained
with `EXCLUDED_PROVENANCE_MISMATCH` (event) or `PROVENANCE_MISMATCH` (episode)
and excluded from every denominator; it can never become a true positive or a
negative-control observation. Time-domain compatibility is established
upstream and is not representable in the W09 event types.

Unmatched episodes are false-warning burden; unmatched observed events are
missed events. Zero denominators remain undefined and include a reason. A
censored event is not an observed negative.

### Metrics

```text
true matched warning episodes
unmatched warning episodes
missed critical events
eligible critical-event denominator
false warning episodes per eligible run
false warning episodes per eligible hour
event-level precision and recall where defined
reactive crossing timestamps
reactive ON/OFF transition timestamps
censored / untrusted / intervened counts
run, event and episode support
undefined reasons
```

## 7. EWT and AIW boundaries

W04 definition remains:

```text
EWT = first persistent predictive warning
    - first reactive criterion time
```

only on the same eligible non-predictively-intervened trajectory. W09 verifies
compatibility with `compute_ewt` on synthetic controlled examples only. A
threshold baseline alone has no predictive warning stream, so W09 reports no
real EWT. Passing a B1 ON transition as the reactive criterion yields a
missing-crossing result, not a fake EWT.

W09 does not synthesize command, ACK, electrical or thermal latencies, so AIW
is `NOT_ESTIMABLE`. W06 timing evidence and W04 AIW contracts remain separate.

## 8. Real-data integration and artifacts

The CLI consumes the A export and run index read-only plus the W08 manifest.
The real diagnostic output includes:

- source-aware schema/role confirmation;
- a diagnostic role-qualified trajectory;
- device-reported applied state as a separate overlay;
- missing/unknown interval annotations;
- W08 exclusion reasons and eligibility gate;
- `PARAMETERS_NOT_FROZEN` when no threshold is frozen;
- optional `SOFTWARE_ONLY_SENSITIVITY_NOT_EVIDENTIARY` replay.

Artifacts:

```text
ml/reports/W09/baseline-report.md
ml/reports/W09/baseline-events-W09.csv
ml/reports/W09/false-warning-summary-W09.csv
ml/reports/W09/baseline-comparison-W09.svg
ml/reports/W09/baseline-manifest-W09.json
```

The manifest records source, A-index, W08-manifest, parameters and analysis-code
hashes, repository revision, generation command, gate context, definitions,
limitations, artifact hashes and `locked_test_access = NONE`. Ordering is
deterministic. The CLI re-reads the artifacts and verifies their hashes before
exiting successfully.

## 9. Freeze discipline

No numeric threshold, representative choice, persistence/dwell, episode gap or
association window is frozen by W09. A `FROZEN` W09 parameter requires
recorded freeze evidence and a W08-eligible matching run; W09 refuses to
freeze a parameter from an A-invalid capture. The project lead and named review
authority own any future freeze decision.
