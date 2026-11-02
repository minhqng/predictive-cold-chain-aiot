# A-W05 — Telemetry foundation (Member A)

Week: **W05** · Branch: `feat/a-w05-telemetry` · Stacked on `feat/a-w04-tec-commissioning` (PR #13, OPEN)
Owner: Member A (embedded / thermal / hardware) · Compiled: ESP-IDF v6.1, esp32s3
Status: **SOFTWARE DELIVERED · PHYSICAL TELEMETRY CAPTURE NOT YET AUTHORIZED**

This dossier contains what W05 proves about the *observation contract*, and
states plainly what it does not prove. Nothing in this directory was captured
from the chamber during W05: the firmware was not flashed, so every behavioural
claim here comes from host execution of the delivered C sources plus a static
read of those sources.

## 1. What W05 changed

| Requirement | Delivered | Where |
|---|---|---|
| A-W05-01 Firmware task boundaries | Producer liveness registry: thermal / BME / door / power / telemetry / control each beat from their own task context, and telemetry names the worst producer plus its beat count and worst observed gap | `firmware/main/cg_health.h`, `cg_health.c`, beats in `app_main.c`, `cg_power.c`, `cg_commission.c` |
| A-W05-02 Device identity | `device_id`, per-boot monotonic `seq`, `calibration_id`, and the frozen ROM of every thermal channel added to the frame; `boot_id` and `hardware_config_id` were already present | `cg_telemetry.c`, `coldguard_config.h` |
| A-W05-03 1 Hz timing study | `firmware/tools/cg_timing_analysis.py` measures real cadence (gap mean/median/p95/p99/max, histogram, late/early/non-positive, seq continuity, producer stalls, status tallies). Pilot executed against a committed 60 s capture | `timing-pilot.json`, `timing-pilot-jitter.csv`, `timing-pilot.md` |
| A-W05-04 Coherent snapshot | Door observation time, per-producer sequence numbers, probe counts, and the PZEM energy register added to the snapshot; every group now reports an age in the frame | `cg_snapshot.h/.c`, `cg_ds18b20.c` |
| A-W05-05 Quality flags | Canonical `VALID / DEGRADED / INVALID / UNKNOWN` derivation per source plus the collapsed overall name, on the wire | `cg_quality.h/.c` |

Serial line schema raised **1 → 2**. The W04 field set is unchanged and still
parses: `evidence/A/W04/g1/40-g1-boot-60s.log` is re-parsed by the W05 parser in
the test suite and no line is rejected.

## 2. What is in this directory

| File | What it is | How it was made |
|---|---|---|
| `README.md` | This file | written |
| `schema-fixture.json` | One real schema-2 line, its per-field map, its length and the budget | rendered by `firmware/main/cg_telemetry.c` through the host C harness |
| `quality-test.md` | The A-W05-05 quality/liveness test matrix: 33 host C scenarios, 125 static checks, 31 mutations + 1 must-not-fire control | derived from `cg_w05_harness.c`, `test_cg_check_firmware_w05.py` |
| `timing-pilot.md` | The measured cadence result and what it does *not* cover | derived |
| `timing-pilot.json`, `timing-pilot-jitter.csv` | The pilot numbers, per frame | `build_timing_pilot.py` |
| `build_timing_pilot.py` | Regenerates both derived artifacts and compares on `--check` | committed tool |
| `handoff-w05.md` | What Members B, C and D can consume now, and the field semantics they must honour | written |
| `acceptance.md` | Requirement-by-requirement status with the honest gaps | written |
| `build/` | `20-idf-py-build.log` (full ESP-IDF v6.1 compile), `21-artifact-hashes.txt` (bootloader / partition table / app image + sizes), `22-source-hashes.txt` (every compiled source, verifiable with `sha256sum -c` from `firmware/`), `30-host-suite-run.log` (the 10/10 suite run) | recorded by the build and the runner |
| `SHA256SUMS.txt`, `validate_w05.py` | Byte pins over this dossier and the re-checker | generated / committed |

## 3. Reproduce

```bash
py firmware/tools/run_all_checks_w05.py            # whole W05 + regression suite
py firmware/tools/cg_check_firmware_w05.py         # 125 static contract checks
py firmware/tools/tests/test_cg_w05_harness.py     # 33 C scenarios on the real sources
py evidence/A/W05/build_timing_pilot.py --check    # artifacts reproduce byte-for-byte
```

The compile check is separate: `evidence/A/W05/build/` records the ESP-IDF v6.1
`idf.py build` of exactly these sources and the SHA-256 of the resulting image.

## 4. Limits of this dossier

* **No W05 capture exists.** `30min-telemetry.csv` and a real `timing-jitter.csv`
  from the W05 image are not here, because producing them needs a flash of an
  image that has never run on this device plus a supervised bench session. Both
  are listed as NEED_USER_ACTION in `acceptance.md`, not as missing files.
* **The pilot is a W04 stream.** It measures real device cadence from committed
  bytes, but schema 1 carried no `seq`, no producer sequence and no quality
  vocabulary, so those columns are absent — not zero, not passing.
* **The quality and liveness tests are host tests.** They execute the delivered
  C functions against synthetic observation states. No sensor was disconnected,
  no bus was interrupted and no fault was injected on hardware in this slice.
  Physical fault validation stays UNVERIFIED, as it has been since H8.
* **Identity is provenance, not verification.** The frame now carries each
  probe's ROM, and `role_status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` still
  states that the physical label was never applied. `evidence/A/W02/sensor-rom-map.yaml`
  keeps `physical_position_verified: false`. W05 makes the claim visible; it does
  not retire it.
* **`calibration_id=UNRECORDED` is a status token, not an identifier.** No
  calibration bundle exists (docs/01 §29). Host converters must map it to `null`
  for Member C's nullable column; inventing a `CG-CAL-…` value would be the only
  thing downstream that could be silently trusted.
* **T2 semantics are untouched.** The delivered firmware still emits
  `t_hot_side_c=nan t_hot_side_status=NOT_ASSIGNED` and `t_inside_src=T2`. The
  operator has stated the physical T2 probe is on the hot side, while `docs/01`
  freezes T1/T2/T3 as chamber-air roles; that conflict is a project decision, and
  W05 deliberately does not resolve it by moving a value between fields.
* **W04's build pins do not describe this branch.** Thirteen files in
  `evidence/A/W04/build-2026-11-01/22-source-hashes.txt` were changed by W05, so
  that list verifies the W04 commit only. This branch's own compile chain is
  `build/22-source-hashes.txt` → `build/20-idf-py-build.log` →
  `build/21-artifact-hashes.txt` (app image `7487cc81…`, 248 512 bytes). See
  `acceptance.md` §6.
* **No output stage.** `CG_TEC_OUTPUT_STAGE_ENABLED 0`,
  `CG_TEC_REQUEST_DUTY_PERMILLE 0`, all seven operating limits still
  `UNRESOLVED`. `cooling_applied` in the frame is therefore always `OFF` in this
  build, and `cooling_evidence` is what the PZEM says about the branch.
