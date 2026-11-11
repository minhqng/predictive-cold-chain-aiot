# W24 reproduction result

> **Task:** B-W24-02. Actual execution record for the available Member B
> software and the real physical descriptive package. This is not a physical
> analysis receipt and not an independent human replay.

```text
B-W24-02 CLEAN_SOFTWARE_REPRODUCTION = PASS
B-W24-02 REAL_PHYSICAL_DESCRIPTIVE_REPRODUCTION = PASS
B-W24-02 FINAL_PREDICTIVE_TABLE = NOT_AVAILABLE
B-W24-02 FINAL_PHYSICAL_AB_TABLE = NOT_AUTHORIZED
INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING
```

## 1. Checkout and environment

| Item | Value |
|---|---|
| Checkout | isolated Git worktree for W24, created from the verified parent |
| Parent revision | `c0d8b247291c05cce308feae25b3fedd329af494` (PR #114 head) |
| Revision semantics | `W24_PARENT_COMMIT_NOT_DELIVERY_COMMIT` |
| Platform | Windows 11 `10.0.26200` x64, Git Bash |
| Python | 3.12.16 (uv-selected CPython) |
| uv | 0.13.7 |
| Dependency lock | `ml/uv.lock`, SHA-256 `dae6cae255b6cdd7c8ca0ded7e902124c0dac467215f309feb45642ad649e5a5` |
| Prior build outputs | none reused as proof; `dist/` regenerated |
| Network | used only for the locked dependency sync |

The worktree was clean at the parent revision before W24 files were added. The
uv-managed `.venv` was resolved from the lockfile; no stale report, wheel or
cache was used as evidence.

## 2. Environment verification

| Command | Result |
|---|---|
| `uv lock --check` | **PASS** — lock resolves unchanged |
| `uv sync --locked --python 3.12 --extra test` | **PASS** — 21 packages resolved; Python 3.12.16 |
| `uv run --locked --python 3.12 --extra test pytest -q` | **PASS** — see §3 |
| `uv build` | **PASS** — wheel and sdist produced |

Build outputs (not committed):

| Artifact | SHA-256 |
|---|---|
| `coldguard_ml-0.1.0-py3-none-any.whl` | `73cf81d803dc89a1c4195fe5ffc7a1f68c5369b89f5228400dfa74f0278407bc` |
| `coldguard_ml-0.1.0.tar.gz` | `519999bc41288541ee8e942b3577beb5d9b95c9c8a778d9763990ff65f7affe5` |

## 3. Test results

| Field | Value |
|---|---:|
| Collected | 1 904 |
| Passed | 1 900 |
| Failed | 0 |
| Skipped | 4 |
| Duration | 336.29 s |

The four skips are optional external-source tests; they are not counted as
passes and are not physical-data failures:

1. `tests/test_horizon_engineering.py::test_cli_writes_consistent_manifest_with_honest_statuses` — pinned A 20261107 export absent (`COLDGUARD_W13_A_DATASET_DIR`).
2. `tests/test_horizon_engineering.py::test_cli_replay_is_byte_deterministic` — same pinned export absent.
3. `tests/test_horizon_engineering.py::test_cli_refuses_a_tampered_timing_report` — same pinned export absent.
4. `tests/test_w21_delivery.py::test_live_source_verification_accepts_the_pinned_a_checkout` — optional A-W21 evidence checkout absent.

No other test was skipped, xfailed or deselected. The W24 handover tests add 24
checks (artifact hashes, model identity, descriptive classification, 12 plots,
T2 exclusion, refusal records, missing outputs, unchanged prior artifacts,
deterministic manifest, links and replay status).

## 4. Layer replay results

All replays wrote to temporary directories, never into `ml/reports/W05…W23`.
Every layer was executed in two independent processes; the two passes were
byte-identical.

| Layer | Exit | Result | Comparison with committed reports |
|---|---:|---|---|
| W16 | 0 | `REFUSED_PREREQUISITES_UNMET`; 47 requirements, 24 refused; `holdout_opened = False`; `evaluation_status = NOT_RUN` | generated manifest differs only in `repository_revision`; four companion reports are committed inputs not regenerated |
| W17 | 0 | software verified; `LIVE_SHADOW_NOT_ESTABLISHED` | byte-identical |
| W18 | 0 | `SIGNOFF_WITHHELD`; holdout not opened | generated files byte-identical; committed input `freeze-baseline-W18.json` not regenerated |
| W19 | 0 | `W20_ANALYSIS = NOT_UNLOCKED` | byte-identical |
| W20 | 0 | `ANALYSIS_PREFLIGHT_BLOCKED`; `W20_FINAL_ANALYSIS = NOT_RUN` | generated files byte-identical; committed input `campaign-metadata-W20.json` not regenerated |
| W21 | 0 | bounded on-device evidence; recorded checks `NOT_VERIFIED` | byte-identical |
| W22 | 0 | 56/56 adversarial probes; 21/21 reference checks; toy only | byte-identical |

W15 was **not refit**. The artifact was verified by bytes:

| File | Observed SHA-256 | Declared | Match |
|---|---|---|---|
| `reports/W15/model/model.ubj` | `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f` | same | yes |
| `reports/W15/model/model.json` | `67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd` | same | yes |
| `reports/W15/model/model-manifest-W15.json` | `85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e` | same | yes |

## 5. W23 evidence audit

Executed twice with `scripts/w23-evidence-audit-W23.py`:

| Field | Result |
|---|---:|
| Declared sources | 97 |
| Verified | 88 |
| Source unavailable | 9 |
| Violations | 0 |
| Two-process output | byte-identical |

Historical reconciliation: the W23 receipt records 83 verified, which
corresponds to the earlier 92-entry package revision. Five local manifests
(W05, W07, W08, W09, W10) were added before delivery; the delivered 97-source
manifest verifies 88 local sources. The W23 receipt was not rewritten. See
[`artifact-integrity-W24.md`](artifact-integrity-W24.md) §8.

## 6. Real physical descriptive reproduction

The A export was generated from the pinned source commit:

```text
git archive d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85 evidence/A/SOURCES/20261107/datasets
```

The recovery driver was executed twice with the committed source inventory and
the recorded repository revision:

```text
audit=COMPLETE descriptive=VERIFIED door=VERIFIED sensor=PARTIAL
gate_b=RED/NOT_READY demo=READY artifacts=19
```

| Comparison | Result |
|---|---|
| Run 1 vs run 2 | byte-identical |
| Run 1 vs committed `ml/reports/DataRecovery/` | byte-identical |
| Real plots | 12/12 present and hash-matched |
| Segments / frames / boots | 18 / 9 293 / 8 |
| Predictive-eligible runs | 0 |

The descriptive package regenerates exactly; it remains descriptive only.

## 7. Determinism

- W23 audit: two processes, byte-identical output.
- DataRecovery: two processes, byte-identical output; identical to the committed package.
- W16–W22: two passes, byte-identical; the W16 generated manifest differs from the committed report only in `repository_revision`, and its four companion reports are committed inputs that the preflight does not regenerate.
- W24 JSON manifests: stable serialization, sorted artifacts, no timestamps and no absolute local paths.
- The W24 checksum inventory and handover manifest were each regenerated in two separate processes; the outputs were byte-identical.
- Generated CSV/SVG outputs contain no controlled timestamps or machine-specific paths.

## 8. Unexpected manual steps and environment assumptions

- `uv` is not on `PATH` on this operator machine; the explicit
  `uv` executable was used. On a clean machine, install `uv` normally.
- The A export had to be materialised from the pinned Git commit because raw
  data is not copied into the W24 package.
- No hidden environment variable is required by the W24 tests.
- No manual editing of reports was used to make a check pass.

## 9. Boundaries

| Boundary | Evidence |
|---|---|
| No W16 locked-test feature/label/outcome read | W16 preflight refused; `holdout_opened = False` |
| No W20 physical outcome read | W20 preflight blocked; `outcome_access = False` |
| No model refit | W15 fitting driver not executed; model bytes unchanged |
| No physical experiment or actuator command | not performed |
| No firmware flash or broker connection | not performed |
| No prior W01–W23 or DataRecovery mutation | hash checks pass |
| No gate promotion | Gate B RED, G3 NO-GO, G4 NOT_READY, G5 NOT_ESTABLISHED |

## 10. Independent human replay

```text
INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING
```

No other human has executed this procedure in this session. The template at
[`independent-replay-receipt-template-W24.json`](independent-replay-receipt-template-W24.json)
is unfilled by design. An AI agent running twice does not count as a different
human reviewer.

## 11. Disposition

```text
CLEAN SOFTWARE REPRODUCTION = PASS
REAL PHYSICAL DESCRIPTIVE REPRODUCTION = PASS
FINAL PREDICTIVE TABLE = NOT_AVAILABLE
FINAL PHYSICAL A/B TABLE = NOT_AUTHORIZED
INDEPENDENT HUMAN REPLAY = PENDING
NO FICTITIOUS RECEIPT OR APPROVAL
```
