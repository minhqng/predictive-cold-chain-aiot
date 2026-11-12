# W23 clean-room replay receipt

> **Task:** B-W23-04. This receipt records what was actually executed in the
> isolated W23 checkout. It is not a physical-analysis receipt and it is not a
> human reproduction record.

```text
TECHNICAL_CLEAN_ROOM_REPLAY = PASS
INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING
FINAL PHYSICAL ANALYSIS = NOT_AUTHORIZED
```

## 1. Checkout and environment

| Item | Value |
|---|---|
| Clean checkout | `D:\iot\worktree-b-w23` (fresh git worktree) |
| Base revision | `cf0716df90a1b9a617df0e61166e218a4f263374` (W22 head) |
| Revision semantics | `GENERATION_BASE_NOT_DELIVERY_COMMIT` |
| Python | 3.12.16 (uv-selected CPython, `uv.lock` environment) |
| uv | 0.13.7 |
| Dependency lock | `ml/uv.lock`, SHA-256 `dae6cae255b6cdd7c8ca0ded7e902124c0dac467215f309feb45642ad649e5a5` |
| Platform | Windows 10 x64, Git Bash |
| Prior caches | none reused; `.venv` created by `uv sync` in the W23 checkout |
| Network | used only for the initial locked dependency sync |

The isolated worktree was created directly from the verified W22 remote head.
The W23 working-tree content is the delivery candidate; the final delivery commit
is recorded in the PR and final report, not inside this receipt (avoids a circular
revision dependency).

## 2. Commands and outcomes

```bash
cd ml
uv lock --check
uv sync --locked --python 3.12 --extra test
uv run --locked --python 3.12 --extra test pytest -q
uv build
```

| Command | Result |
|---|---|
| `uv lock --check` | PASS — lockfile resolves unchanged |
| `uv sync --locked --python 3.12 --extra test` | PASS — 21 packages, Python 3.12.16 |
| full `pytest -q` | PASS — see JSON below |
| `uv build` | PASS — wheel and sdist produced |

## 3. Test results

| Field | Value |
|---|---:|
| Collected | 1 841 |
| Passed | 1 837 |
| Failed | 0 |
| Skipped | 4 |

The four skips are optional external-source tests. They are not counted as passes
and are not treated as physical-data failures. No other test was skipped, marked
xfail or deselected. Exact skip reasons are recorded in the machine-readable
summary in §10.

## 4. Layer replay results

All replays wrote into temporary directories (`D:\iot\tmp-b-w23-replay\*`), never
into `ml/reports/W05…W22`.

| Layer | Command | Exit | Result | Comparison to committed reports |
|---|---|---:|---|---|
| W16 | `w16-preflight-W16.py --out <tmp>` | 0 | `REFUSED_PREREQUISITES_UNMET`; 24 refusal reasons; `holdout_opened = False`; `evaluation_status = NOT_RUN` | manifest identical except `repository_revision` (W23 base vs W16 base) |
| W17 | `w17-shadow-replay-W17.py --out-dir <tmp>` | 0 | software complete; `LIVE_SHADOW_NOT_ESTABLISHED`; holdout not opened | byte-identical |
| W18 | `w18-runtime-audit-W18.py --out-dir <tmp>` | 0 | software complete; `SIGNOFF_WITHHELD`; holdout not opened | generated files byte-identical (committed input `freeze-baseline-W18.json` not regenerated) |
| W19 | `w19-campaign-audit-W19.py --out-dir <tmp>` | 0 | software verified; `W20_ANALYSIS = NOT_UNLOCKED` | byte-identical |
| W20 | `w20-campaign-preflight-W20.py --out-dir <tmp>` | 0 | `ANALYSIS_PREFLIGHT_BLOCKED`; `FINAL_CAMPAIGN = NOT_AUTHORIZED` | generated files byte-identical (committed input `campaign-metadata-W20.json` not regenerated) |
| W21 | `w21-resilience-audit-W21.py --out-dir <tmp>` | 0 | bounded on-device evidence; recorded checks `NOT_VERIFIED` without a pinned A checkout | byte-identical |
| W22 | `w22-statistics-contract-W22.py --out <tmp>` | 0 | 56/56 adversarial probes; 21/21 reference checks; toy only | byte-identical |
| W23 | `w23-evidence-audit-W23.py` × 2 | 0 | integrity PASS; 83 verified, 9 unavailable, 0 violations | two independent processes byte-identical |

### W15 artifact

The W15 fitting driver was **not re-executed**: W23 is feature-freeze and does not
perform new model fitting. The artifact was verified by recomputation:

| File | Observed SHA-256 | Declared SHA-256 | Match |
|---|---|---|---|
| `model.ubj` | `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f` | same | yes |
| `model.json` | `67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd` | same | yes |
| `model-manifest-W15.json` | `85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e` | same | yes |

The W15 tests (`tests/test_w15_artifact.py`) pass within the full suite,
including the fresh-process reload and probe-parity checks.

### W13 replay

W13’s driver requires the pinned A 20261107 dataset export
(`COLDGUARD_W13_A_DATASET_DIR`). The export is not present in this checkout, so
the W13 CLI replay is `REPRODUCTION_PENDING_SOURCE_ACCESS`, not `NOT_REPRODUCIBLE`
and not a physical-data failure. The committed W13 manifest and horizon decision
remain hash-bound by the W23 audit.

## 5. Build

| Artifact | Result |
|---|---|
| sdist `coldguard_ml-0.1.0.tar.gz` | PASS |
| wheel `coldguard_ml-0.1.0-py3-none-any.whl` | PASS |

`dist/` and `build/` are generated outputs and are not part of the W23 commit.

## 6. Determinism and hash comparisons

- Two independent W23 audit processes produced byte-identical
  `audit-result.json` and `audit-summary.md`; exit code 0 both times.
- W17/W19/W21/W22 regenerated reports are byte-identical to the committed
  reports.
- W18/W20 regenerated files are byte-identical; the only committed files not
  regenerated are their input metadata files.
- W16 regenerated manifest differs only in `repository_revision`
  (`cf0716d…` W23 base vs `daf85e0…` W16 base); all other fields are equal.
- The W15 model and registry/config hashes match the W15 declaration exactly.
- No prior W11–W22 report was modified by the replay commands.

## 7. Boundaries and no-access proof

| Boundary | Evidence |
|---|---|
| No W16 locked-test feature/label/outcome read | W16 replay `holdout_opened = False`, `evaluation_status = NOT_RUN`; audit forbids locked payloads |
| No W20 real paired-outcome read | W20 preflight `ANALYSIS_PREFLIGHT_BLOCKED`, `outcome_access = False` |
| No new model fitting | W15 driver not executed; no model bytes changed |
| No actuator command / physical control | Replays are offline software only |
| No firmware flash or broker connection | Not performed |
| No policy mutation | D policy `NOT_FROZEN`; no D files changed |
| No Gate G4/G5 promotion | `G4 = NOT_READY`, `G5 = NOT_ESTABLISHED` |
| No physical experiment | Not performed |

## 8. Independent team-member requirement

```text
INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING
```

An AI fresh-context review and an isolated worktree are technical evidence only.
No other human team member has executed this procedure in this session; that is
not claimed. No name, signature, machine, timestamp or approval is invented. This
remains an explicit W24 handover action.

## 9. Unexpected manual steps and environment assumptions

- `uv` is not on `PATH` on this operator machine; the explicit executable
  `D:\iot\.tools\uv\uv.exe` was used. This is an environment prerequisite, not a
  repository defect. On a clean machine, install `uv` normally.
- Python 3.12.16 is uv-managed from a local cache/temporary interpreter path; no
  repository-absolute interpreter path is recorded or required.
- No hidden environment variable is required by the W23 verifier (tested with a
  minimal environment).
- No manual report editing, cache reuse or stale artifact was used as proof.

## 10. Machine-readable summary

```json
{
  "technical_clean_room_replay": "PASS",
  "independent_team_member_replay": "PENDING",
  "final_physical_analysis": "NOT_AUTHORIZED",
  "clean_checkout_sha": "cf0716df90a1b9a617df0e61166e218a4f263374",
  "source_revision_semantics": "GENERATION_BASE_NOT_DELIVERY_COMMIT",
  "python": "3.12.16",
  "uv": "0.13.7",
  "tests": {
    "collected": 1841,
    "passed": 1837,
    "failed": 0,
    "skipped": 4,
    "skip_reasons": [
      "tests/test_horizon_engineering.py::test_cli_writes_consistent_manifest_with_honest_statuses — pinned A 20261107 export absent (COLDGUARD_W13_A_DATASET_DIR)",
      "tests/test_horizon_engineering.py::test_cli_replay_is_byte_deterministic — pinned A 20261107 export absent (COLDGUARD_W13_A_DATASET_DIR)",
      "tests/test_horizon_engineering.py::test_cli_refuses_a_tampered_timing_report — pinned A 20261107 export absent (COLDGUARD_W13_A_DATASET_DIR)",
      "tests/test_w21_delivery.py::test_live_source_verification_accepts_the_pinned_a_checkout — optional A-W21 evidence checkout absent"
    ]
  },
  "build": {"wheel": "PASS", "sdist": "PASS"},
  "model_artifact": {
    "path": "ml/reports/W15/model/model.ubj",
    "observed_sha256": "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f",
    "declared_sha256": "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f",
    "matches_declared_sha256": true
  },
  "artifact_lock": {
    "path": "ml/uv.lock",
    "sha256": "dae6cae255b6cdd7c8ca0ded7e902124c0dac467215f309feb45642ad649e5a5"
  },
  "audit": {
    "runs": 2,
    "deterministic": true,
    "integrity_ok": true,
    "verified_sources": 83,
    "unavailable_sources": 9,
    "violations": 0
  },
  "replays": {
    "w13": "REPRODUCTION_PENDING_SOURCE_ACCESS",
    "w15_fitting_driver": "NOT_EXECUTED_NO_NEW_MODEL_FITTING",
    "w16": "EXPECTED_FAIL_CLOSED_EXIT_0",
    "w17": "PASS_BYTE_IDENTICAL",
    "w18": "PASS_GENERATED_FILES_IDENTICAL",
    "w19": "PASS_BYTE_IDENTICAL",
    "w20": "EXPECTED_BLOCKED_EXIT_0",
    "w21": "PASS_BYTE_IDENTICAL",
    "w22": "PASS_BYTE_IDENTICAL"
  },
  "environment_assumptions": [
    "Windows 10 x64 with Git Bash",
    "uv 0.13.7 available (explicit D:\\iot\\.tools\\uv\\uv.exe path used)",
    "Python 3.12.16 selected by uv from the locked environment",
    "no A/C/D optional checkout required for the committed W23 package",
    "no hardware, broker or firmware access"
  ],
  "unexpected_manual_steps": [
    "uv was not on PATH; the operator used D:\\iot\\.tools\\uv\\uv.exe as the launcher"
  ]
}
```

## 11. Disposition

```text
CLEAN-ROOM SOFTWARE REPLAY = PASS
INDEPENDENT HUMAN REPLAY = PENDING
FINAL PHYSICAL ANALYSIS = NOT_AUTHORIZED
NO FICTITIOUS RECEIPT OR HUMAN APPROVAL
```
