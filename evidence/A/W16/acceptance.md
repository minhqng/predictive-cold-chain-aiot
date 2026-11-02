# A-W16 acceptance

Slice: W16 final physical drift/response freeze framework · Branch
`feat/a-w12-physical-readiness` · Owner: Member A
Hardware touched: **NO** · Flashed: **NO** · Freeze asserted: **NO** · Team G4 claimed: **NO**

W16 is **not** a GREEN week. It is the comparability framework and the freeze
schema; the actual freeze is a physical act this host slice performs never.

## 1. Requirement matrix (docs/05A §25)

| ID | Canonical ask | Status | Value / evidence |
|---|---|---|---|
| **A-W16-01** | Re-run short characterization (OFF envelope, core ON point, response delay, S2 disturbance) | **NEED_USER_ACTION** | `w16-rerun-requirements.csv`: all four sub-captures are physical re-runs on the frozen geometry; `host_can_compute: false`. The committed baseline (W04 H8-C, image `01cedce3…`) is the *pre-W16* anchor, not the W16 re-run. |
| **A-W16-02** | Compare W7/W8 vs W16 (current/power shift, response shift, gradient, recovery) | **BLOCKED — no W16 snapshot, and the baseline is only partly evidenced** | `comparability-framework.json.cross_era_comparison`: `comparison_allowed: false`, verdict `BLOCKED`. The current (W16) side is entirely `MISSING_SIDE` (no re-measurement exists). The **baseline is NOT fully populated**: cadence (1.0 Hz) and image (`01cedce3…`) are present, but only T2 is role-labelled (T1/T3/T4 null), the `physical_output` column is empty (`UNQUALIFIED(empty column)`), so the geometry is `UNLABELLED` and the derived config identity is `UNVERIFIED` — those baseline dimensions are `MISSING_SIDE` too. Comparability now fails on **absence of evidence on both sides**, never on a match of nulls (H3 fix: null/unlabelled/`UNQUALIFIED`/`UNVERIFIED` are `MISSING_SIDE`, the config id is derived not constant, and absence can no longer read as COMPARABLE). |
| **A-W16-03** | Final pair tolerances (initial state, gradient, reset criterion, disturbance tolerance) signed off with B | **HOST FRAMEWORK — values NOT_MEASURED** | `response-tolerance-format.json`: the four fields exist as a format with `value: NOT_MEASURED`; policy: no field may be filled from host evidence. Gradient is defined as docs/01 §20.3 (chamber-air `Tmax−Tmin`); reset criterion as §20.6 (recovery after action). |
| **A-W16-04** | Controller B physical readiness certified with D (allowed action valid, no hardware safety issue, H8 reactive verification stable) | **OPEN** | `final-freeze-evidence-schema.json`: required_evidence items all `OPEN`; `host_slice_may_set_frozen: false`; forbidden labels `PHYSICALLY_VERIFIED` (from host) and `TEAM_GATE_G4_GREEN`. |

## 2. Gate contribution — honoured, not claimed

`docs/05A §25` states **G4 cannot pass if physical response has drifted beyond
the understood range.** This slice provides the comparison *framework* and the
drift detector, and explicitly **does not** declare G4 (or G3) GREEN — that is a
whole-team decision outside Member A W16's authority. `validate_w16.py` re-runs
`assert_no_freeze` against the committed artifact and refuses to accept a build
that carries a freeze, a `PHYSICALLY_VERIFIED` status, or a whole-team gate passed
in the framework's place.

## 3. Configuration-drift detection

`configuration_drift` is `[]` today only because a single baseline is committed;
the detector compares every one of the six dimensions across supplied snapshots.
When W07/W08 era snapshots and a W16 snapshot are handed in, any changed
`image_sha256`, `limits_policy`, `cadence_hz`, `physical_output`, role geometry,
or config id surfaces as `CONFIGURATION_DRIFT` and blocks the freeze.

## 4. What could NOT be computed, and why

* **The freeze itself.** No W16 re-measurement exists; it is a physical action
  (`NEED_USER_ACTION`). The framework refuses to set `frozen`.
* **W7/W8 → W16 response shift.** Requires both era snapshots under the six
  dimensions; the W16 side is empty by design, so the comparison is BLOCKED, not
  zero-difference.
* **Tolerance values.** NOT_MEASURED until a real re-run supplies them; the format
  does not estimate a limit.

## 5. OPERATOR_ACTION_QUEUE (W16)

The W16 re-run (A-W16-01) is the single session that unlocks A-W16-02/03/04. It
reuses the W12/W13 prerequisites and must not skip required repetitions.

| # | Requirement | Exact physical action | Existing valid evidence | Safety prerequisites | Expected capture | Downstream unlock |
|---|---|---|---|---|---|---|
| 1 | A-W16-01 → 02 OFF envelope | Supervised short idle (duty-0) capture on the frozen geometry, same installed image as baseline | W04 H8-C baseline (`01cedce3…`) | two-step flash/energize gate; stop on zero/abnormal current | W16 OFF frames with qualified current_status | enables OFF-envelope drift comparison vs W7/W8 |
| 2 | A-W16-01 → 02 core ON point | Supervised short core-ON run at the frozen duty on the same image | H8 100% endurance data (sibling), provisional 55 °C hot-side limit | supervision; hot-side ≤ provisional limit; no wiring change | W16 ON frames (current/power/thermal) | enables current/power/response shift check |
| 3 | A-W16-01 → 03 response delay + S2 disturbance | Re-measure the console START→thermal response and one S2 disturbance on the same geometry | W13 delay 1.094 s / thermal 0.85 min | supervision; door handled by operator only | W16 response + disturbance captures | fills the A-W16-03 tolerances; feeds the door→critical closure from W13 |
| 4 | A-W16-04 Controller B readiness | After 1–3, joint A+D review: allowed action still valid, no hardware safety issue, H8 reactive verification stable | items 1–3 outputs + W12 mechanical signoff (still open) | the fuse/conductor deviation must be resolved or explicitly accepted first | freeze evidence satisfying `final-freeze-evidence-schema.json` | lets A contribute the physical half of the G4 input to the team |

Items 1–3 should be captured in one supervised characterization session on a
single unchanged installed image so the W16 snapshot shares all six comparison
dimensions with itself; item 4 is a review, not a bench act. **No item may be
compressed into a freeze before its capture exists, and none may be pooled across
configurations** (the W12 dataset-validity rule applies to every W16 capture).
