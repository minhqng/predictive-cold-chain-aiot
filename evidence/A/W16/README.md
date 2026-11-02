# A-W16 — Final physical drift/response freeze framework (before predictive control)

Week: **W16** · Branch: `feat/a-w12-physical-readiness` · Owner: Member A
Status: **HOST FRAMEWORK ONLY · NO FREEZE ASSERTED · NO TEAM GATE DECLARED · W16 RE-MEASUREMENT NOT PRESENT**

This dossier delivers the *framework* that decides when behaviour captured in an
earlier era (W07/W08) may be compared to the W16-era behaviour, and the schema a
physical freeze must satisfy before Member A can certify Controller B readiness
with D. Running it on authentic committed data today it has only the W04/H8-C
baseline; the W16-era re-measurement is a physical action this host slice cannot
perform, so the honest result is **no comparison closed and no freeze asserted**.

W16 is **not** a GREEN week.

## 1. What W16 delivered

| Requirement | Delivered | Where |
|---|---|---|
| **A-W16-01** re-run short characterization | The framework lists which sub-captures a W16 run must provide (OFF envelope, core ON point, response delay, S2 disturbance) with status; absent them = NEED_USER_ACTION | `w16-rerun-requirements.csv` |
| **A-W16-02** compare W7/W8 vs W16 | `compare_snapshots`: per-dimension match table + verdict across the six comparison dimensions | `comparability-framework.json` |
| **A-W16-03** final pair tolerances | The analysis **format** (initial state, gradient, reset criterion, disturbance tolerance) as NOT_MEASURED placeholders | `response-tolerance-format.json` |
| **A-W16-04** Controller B physical readiness | The final physical **freeze evidence schema** + `assert_no_freeze` guard | `final-freeze-evidence-schema.json` |

## 2. The six comparison dimensions

A cross-era response comparison is legal only when every dimension matches:
`geometry_roles`, `cadence_hz`, `limits_policy`, `image_sha256`,
`physical_output`, `hardware_config_id`. A mismatch or a missing side is
**configuration drift** and blocks the freeze.

## 3. Files

| File | What it is |
|---|---|
| `README.md` | this file |
| `acceptance.md` | requirement-by-requirement status with the gaps named |
| `comparability-framework.json` | dimensions, baseline signature, cross-era verdict, drift detection, no-freeze verdict |
| `response-tolerance-format.json` | A-W16-03 tolerance format (placeholders only) |
| `final-freeze-evidence-schema.json` | A-W16-04 freeze evidence schema + allowed/forbidden status labels |
| `w16-rerun-requirements.csv` | A-W16-01 required re-runs with status |
| `build_w16_artifacts.py` | regenerates every artifact by running the framework; `--check` compares byte-for-byte |
| `validate_w16.py` | SHA256 pins, LF-only, re-runs `assert_no_freeze`, and fails on a host freeze or a G4 GREEN |
| `SHA256SUMS.txt` | byte pins (LF-only) |

## 4. Reproduce

```bash
py firmware/tools/cg_w16_comparability.py               # run on the authentic baseline; asserts no freeze
py firmware/tools/run_all_checks_w16.py                 # full W16 check chain
py evidence/A/W16/build_w16_artifacts.py --check        # artifacts reproduce byte-for-byte
py evidence/A/W16/validate_w16.py                       # hash pins + no-freeze re-assert
```

## 5. Limits of this dossier

* **No freeze may come from host bytes.** The framework ships with
  `frozen: false` and `no_g4_claim: true`, and `assert_no_freeze` runs on every
  build. A future freeze requires a real W16 re-measurement, not this analysis.
* **The W16 side is empty on purpose.** With no W16 snapshot present the
  cross-era comparison is BLOCKED and `physical_verified` is false. The
  response-tolerance fields stay `NOT_MEASURED` until a W16 run fills them with
  measured values.
* **W07/W08 baselines are sibling workstreams.** Their dossiers are referenced,
  not read or copied here; comparing them requires those era snapshots to be
  handed in under the six dimensions.
