# ColdGuard Member A - real data handoff (20261108T102646Z)

Export pipeline: `_local_handoff/coldguard_real_data_export.py` (rerunnable, stdlib only).

## Contents
- `raw/` - verbatim copies (SHA-256 in manifest.json) of every real capture used.
- `datasets/` - one normalized CSV per run/segment: T1/T2/T3/T4 with per-field status,
  Tmean air (mean T1/T3/T4, all-OK rule; T2 is hot-side and never averaged in), door,
  PWM, U/I/P, energy, state/stage/fault.
- `datasets/published/` - committed derived CSVs (W04 600 s, W13 timing, W05 jitter).
- `run_index.csv` - one row per run/segment: source, boot_id, device run_id, firmware,
  hardware_config_id, host clock window, frame count, dataset SHA-256, classification.
- `measurement_summary.csv` - per-run derived statistics (means, gradient, chamber drop,
  electrical response delay, door events, quality counts).
- `quality_report.md` - coverage, independence caveats, scenario gates.
- `manifest.json` - SHA-256 and provenance for every input and output.

## Classification
DATASET_ACCEPTED_S1 (4 runs) - backs A-W09-02 PASS in the authoritative store.
DATASET_ACCEPTED_S2 (5 windows: 1 timing + 4 door) - backs A-W10-03 PASS.
REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED - H8-C 600 s and H8-E 1800 s real
TEC bench steps (cannot close A-W08-03 offline; see acceptance-decisions file).
REAL_FRAMES_OUTSIDE_TIMED_WINDOWS - kept, flagged, not independent runs.
WARMUP_SEGMENT moments are kept and flagged; nothing measured was discarded.

## Acceptance updates written to the authoritative store this session
See the final report. Writes used the app's own SessionStore API with automatic
history preservation (results/history/).
