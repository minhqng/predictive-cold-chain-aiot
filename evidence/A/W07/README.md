# A-W07 — Geometry freeze and physical repeatability study (Member A)

Week: **W07** · Branch: `feat/a-w07-plant-repeatability` · Stacked on
`feat/a-w06-command-ack` (PR #17, OPEN) → `feat/a-w05-telemetry` (PR #16) →
`feat/a-w04-tec-commissioning` (PR #13)
Owner: Member A · Status: **SENSORS FROZEN BY IDENTIFICATION · ANALYSIS DELIVERED ·
PHYSICAL STUDY NOT STARTED · CONFIGURATION PHOTO STILL MISSING**

W07 makes the chamber measurable. It does not make it measured: docs/05A §16 asks
for at least three passive and three cooling runs on a frozen geometry, and this
repository holds one cooling run plus one passive and one recovery segment from the
same boot. The tools, definitions, statistics, identification record, criterion
candidate and the exact ask are delivered; the runs are not invented.

## 1. What W07 adds

| Piece | What it is |
|---|---|
| `probe-identification-v0.md` + `probe-identification/` | the 2026-11-02 operator-confirmed slot→position mapping (T1 centre, T2 hot side, T3 bottom, T4 near door) with its six raw captures, labelled `PROBE_IDENTIFICATION` and excluded from S1/S2/S4 |
| `geometry-v1.md` | what is frozen and from which line of which file; what is not; the `docs/01` naming discrepancy and the minimum coherent transition, with no silent remap |
| `firmware/tools/cg_thermal_repeatability.py` | captures → per-phase trajectories, direction-aware thresholds, slopes with declared representation/window/method, cross-run mean / sample SD / CV / min / max, and `INSUFFICIENT_RUNS` naming how many runs are missing instead of inventing a distribution |
| `firmware/tools/cg_reset_criterion.py` | A-W07-05 as an executable evaluator: `READY` / `NOT_READY` / `UNKNOWN` kept strictly apart, unresolved gates unable to produce `READY`, and a state measured on the wrong mean refused |
| `reset-criterion-v0.yaml` | three gates FROZEN from canonical state semantics, two numeric gates `UNRESOLVED` with the measurement each waits for named in `source` |
| `repeatability-report.md`, `repeatability-*.json`, `repeatability-overlay.csv` | the generated verdict, every analysed definition, and trajectory overlays on two time bases |
| `warmup-runs.jsonl`, `cooling-step-runs.jsonl`, `recovery-runs.jsonl` | one phase per file, each entry carrying provenance, its own row tallies and `independent_session: false` |
| `build_w07_artifacts.py`, `validate_w07.py`, `SHA256SUMS.txt` | regeneration with `--check`, byte pins and the honesty re-checker |
| `firmware/tools/run_all_checks_w07.py` | seven layers including the W04-W06 regressions |

## 2. Definitions are named, never implied

- `tmean_airroles_v0` = mean(T1,T3,T4) — the as-built chamber-air mean, primary here.
- `tmean_chamber3_v0` = mean(T1,T2,T3) — what `docs/01` §20.1 writes literally, and
  on this rig it averages hot-side metal into an air temperature.
- `tmean_t2excluded_v0`, `tmean_all4_v0` — degraded and sensitivity variants.
- Slope always names representation, window and method; the trailing-window figure
  is never presented as a phase summary (it reads **+0.0701 °C/min** during the
  cooling phase whose whole-phase slope is **-0.854771 °C/min**, because the curve
  rebounds inside the driven block).
- Spread is the **sample** (n-1) formula and says so; CV is withheld at a zero mean.
- `nan`, absent and non-`OK` readings are excluded **and counted**; an empty status
  cell is used but counted as `unqualified` — the H8 capture left
  `current_status`/`voltage_status` empty on all 957 rows, so its electrical
  figures carry no recorded validity and are labelled as such.
- Rows with no usable applied duty are `undetermined` and join no phase.

On the single run available the two candidate air means differ by a factor of
**3.40** (-8.7083 °C against -2.5627 °C). Both are published; neither is passed off
as *the* answer, and the open `docs/01` naming question is recorded rather than
decided here.

## 3. Reproduce

```bash
py firmware/tools/run_all_checks_w07.py
py firmware/tools/tests/test_cg_thermal_repeatability.py
py firmware/tools/tests/test_cg_reset_criterion.py
py evidence/A/W07/build_w07_artifacts.py --check
py evidence/A/W07/validate_w07.py
py firmware/tools/cg_thermal_repeatability.py evidence/A/W04/tec-cooling-response-600s.csv --representation tmean_airroles_v0
py firmware/tools/cg_reset_criterion.py evidence/A/W07/reset-criterion-v0.yaml --state '{"representation":"tmean_airroles_v0","tmean_c":29.9,"door_state":"CLOSED","cooling_state":"OFF","quality":"VALID","slope_c_per_min":0.02}'
```

## 4. Limits of this dossier

* **Host analysis of old captures.** Nothing here measured anything new: no flash,
  no energized stage, no bench session, no probe moved beyond the accepted
  hand-hold identification.
* **One run is one run.** No repeatability claim, no CV, no plant-variation
  verdict; the report says `NOT ESTABLISHED` and the validator fails if it ever
  stops saying that while the registries still hold one segment.
* **Geometry is frozen for sensor positions only.** V1 position, cable paths, door
  alignment, internal load, conductor/termination evidence and the configuration
  photo are open, so A-W07-01 stays **PARTIAL**.
* **The ROM ids are by-source.** The response evidence fixes slot→position; the
  ROM labels come from the firmware's frozen map, and the installed image hash was
  not read back off flash.
* **The criterion's numbers are open on purpose.** `tmean_band_c` and
  `gradient_bound_c_per_min` are `UNRESOLVED`, the evaluator answers `UNKNOWN`
  while they are, and `reset-criterion-evaluation.json` reaches `READY` only under
  values explicitly labelled a test injection.
* **The touch-test data is `PROBE_IDENTIFICATION`.** It must never enter S1/S2/S4 or
  any thermal-response statistic; the validator re-checks that all 233 of its
  frames were captured with applied duty 0.
