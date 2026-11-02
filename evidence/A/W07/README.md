# A-W07 — Geometry freeze and physical repeatability study (Member A)

Week: **W07** · Branch: `feat/a-w07-plant-repeatability` · Stacked on
`feat/a-w06-command-ack` (PR #17, OPEN) → `feat/a-w05-telemetry` (PR #16) →
`feat/a-w04-tec-commissioning` (PR #13)
Owner: Member A · Status: **ANALYSIS DELIVERED · PHYSICAL STUDY NOT STARTED · GEOMETRY NOT FROZEN**

W07 makes the chamber measurable. It does not make it measured: docs/05A §16 asks
for at least three passive and three cooling runs on a frozen geometry, and this
repository holds one cooling run plus one passive segment from the same boot. The
tools, the definitions, the statistics and the criterion candidate are delivered;
the runs are an operator request recorded in `acceptance.md` §4.

## 1. What W07 adds

| Piece | What it is |
|---|---|
| `firmware/tools/cg_thermal_repeatability.py` | turns committed bench captures into per-phase trajectories, slopes with declared window and method, electrical summaries, and cross-run mean/SD(sample)/CV/min/max. Reports `INSUFFICIENT_RUNS` with the number of runs still needed instead of dressing up n=1 |
| `firmware/tools/cg_reset_criterion.py` | the A-W07-05 state criterion as an executable evaluator with three-way output: `READY`, `NOT_READY` (contradicted), `UNKNOWN` (unmeasurable or unevidenced). An unresolved gate can never yield READY |
| `evidence/A/W07/reset-criterion-v0.yaml` | the candidate itself: three gates frozen from canonical state semantics, two numeric gates `UNRESOLVED` with the measurement they are waiting on named in `source` |
| `evidence/A/W07/geometry-v1.md` | what is frozen from committed evidence (pins, ROM roles, conductor, output posture) with citations, and what is not (every physical placement, because no configuration photo exists) |
| `evidence/A/W07/repeatability-report.md` | generated verdict: not established, with the one run's numbers and the representation disagreement quantified |
| `warmup-runs.jsonl`, `cooling-step-runs.jsonl` | the run registry derived from real captures, each entry carrying its capture, `boot_id` and an explicit `independent_session: false` |
| `repeatability-*.json`, `repeatability-overlay.csv` | full per-run metrics for both `Tmean` definitions, and the trajectory overlay |
| `build_w07_artifacts.py`, `validate_w07.py`, `SHA256SUMS.txt` | regeneration, byte pins and the honesty re-checker |
| `firmware/tools/run_all_checks_w07.py` | seven layers including the W04-W06 regressions |

## 2. Definitions are named, never implied

- `tmean_chamber3_v0` = mean(T1,T2,T3) — the docs/01 chamber-air freeze.
- `tmean_t2excluded_v0` = mean(T1,T3) — because the captures label T2 `HOT_SIDE`.
- `tmean_all4_v0` — sensitivity check only.
- slope = trailing 120-sample least squares, plus whole-phase least squares, always
  published with the representation and window that produced them (docs/01 §20.5).
- spread = **sample** (n-1) formula, stated (docs/01 §20.4); CV is undefined at a
  zero mean and reported as such.
- `nan`, absent and non-`OK` readings are excluded and counted, never read as zero.

Publishing one unlabelled `Tmean` would hide a live contract dispute: on the single
available run the two definitions differ by 3.4× in measured cooling effect
(-2.5627 °C versus -8.6875 °C). See `acceptance.md` §2.

## 3. Reproduce

```bash
py firmware/tools/run_all_checks_w07.py                 # seven layers
py firmware/tools/tests/test_cg_thermal_repeatability.py
py firmware/tools/tests/test_cg_reset_criterion.py
py evidence/A/W07/build_w07_artifacts.py --check        # artifacts reproduce byte-for-byte
py evidence/A/W07/validate_w07.py
py firmware/tools/cg_thermal_repeatability.py evidence/A/W04/tec-cooling-response-600s.csv --representation tmean_t2excluded_v0
py firmware/tools/cg_reset_criterion.py evidence/A/W07/reset-criterion-v0.yaml --state '{"representation":"tmean_chamber3_v0","tmean_c":29.9,"door_state":"CLOSED","cooling_state":"OFF","quality":"VALID","slope_c_per_min":0.02}'
```

## 4. Limits of this dossier

* **Host analysis of old captures.** Nothing here measured anything new: no flash,
  no energized stage, no bench session, no sensor moved.
* **One run is one run.** No repeatability claim, no CV, no plant-variation
  verdict; the report says `NOT ESTABLISHED` and the validator fails if it ever
  stops saying that while the registry still holds one segment.
* **The geometry is not frozen.** `geometry-v1.md` freezes electrical identity from
  committed files and states plainly that physical placement has no photo or
  drawing behind it. A-W07-01 stays PARTIAL.
* **The criterion's numbers are open on purpose.** `tmean_band_c` and
  `gradient_bound_c_per_min` are `UNRESOLVED`; the evaluator answers `UNKNOWN` for
  any state while they are, and `reset-criterion-evaluation.json` shows a READY
  result only under numbers explicitly labelled as a test injection.
* **`Tmean` is contested, not decided.** Both definitions are computed and every
  artifact names which one it used. Choosing between them is a project decision
  about docs/01, and it is recorded as blocking the interpretation of this week's
  numbers.
