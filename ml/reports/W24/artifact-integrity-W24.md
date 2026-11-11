# W24 artifact integrity and checksum report

> **Task:** B-W24-01. Machine-readable inventory:
> [`artifact-checksums-W24.json`](artifact-checksums-W24.json).
> **Scope:** Member B deliverables through W23 plus the existing physical-data
> recovery package. **No W01–W23 artifact was modified.**

```text
B-W24-01 ARTIFACT CHECKSUMS = COMPLETE
W15_MODEL_SHA256 = 25A8EF7A71817D4D45A2D9BC3B4D6889C2DBF576C4DA514D59FAB1F6FC263F7F (MATCH)
REAL_PHYSICAL_PLOTS = 12/12 PRESENT AND HASH-MATCHED
FINAL_PREDICTIVE_RESULT_CSV = NOT_PRODUCED
FINAL_PHYSICAL_AB_RESULT_CSV = NOT_PRODUCED
```

## 1. Method and hash semantics

All checksums are `FILE_CONTENT_SHA256` over the exact committed file bytes,
recomputed in the W24 worktree at parent revision
`c0d8b247291c05cce308feae25b3fedd329af494` (PR #114 head). Git commit IDs are
recorded separately per artifact and are **not** treated as file checksums. The
inventory does not hash itself; no self-referential manifest hash is used.

`source_commit` is the last commit that touched the path on this branch. It is a
provenance pointer, not a content pin. The W24 delivery commit is intentionally
not embedded (it cannot contain its own hash).

## 2. Inventory result

| Field | Value |
|---|---:|
| Category entries | 82 |
| Unique artifacts | 68 |
| Verified entries | 78 `VERIFIED` + 4 `VERIFIED_REFUSAL_RECORD` |
| Missing declared artifacts | 0 |
| Fabricated or unresolved hashes | 0 |

Categories covered: dataset export (A), split manifest (B), feature registry (C),
model artifact (D), final result files (E), key analysis artifacts W03–W23 (F),
and the 12 real physical figures (G).

## 3. Dataset identities

### 3.1 W11 synthetic dataset

| Field | Value |
|---|---|
| Dataset ID | `W11_EXPANDED_SYNTHETIC_GROUPED` |
| Fixture | `coldguard-w11-synthetic-grouped-v1` |
| Evidence class | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` |
| Population | 20 runs / 10 pairs; 16 development runs, 4 synthetic locked-test runs |
| Windows | 2 896 generated (1 936 evaluable + 960 censored) |
| Identity manifest | `ml/reports/W11/benchmark-manifest-W11.json`, SHA-256 `855c5beb55f15c6e5bcd38640ff3a6ff02a41a525bf3f1601722abdeca2d47f0` |
| Raw payload | none; deterministic in-memory fixture, no locked-test payload file |
| Permitted use | offline software-control experiments only |
| Missing information | physical run identity, physical sensor population, frozen target and horizon |

### 3.2 Existing real physical A 20261107 export

| Field | Value |
|---|---|
| Source revision | `d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85` |
| Export command | `git archive d22c8d5b… evidence/A/SOURCES/20261107/datasets` |
| A manifest pin | `5273e528e6505caf55dec79a5fccbe0e6407161c1fedb864b52a7160706cc72d` |
| A run-index pin | `53d476747c4a865ddec09492c9c49601a72ab766e9862faac0a2c9a43a22bbb4` |
| Timing-report pin | `2826a71026e7d4b8dc2cf3413efb5e4983785fc59ae760586569b91279fb2169` |
| W05 export pin | `f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb` |
| W21 manifest pin | `5b78141deca1d3f5fd5e16ac10b3344541261d66b5aaa6e49bb3169758fae2c3` |
| Source inventory | `ml/reports/DataRecovery/source-inventory.json`, SHA-256 `bd451f9dc4d99ae6a8cf88c8e16dbe6a44f0e67affaec7c390a59505f3130fb5` |
| Segments / frames / boots | 18 / 9 293 / 8 |
| A-accepted S1 / S2 windows | 4 / 5 |
| Predictive-eligible independent runs | **0** |
| Permitted use | descriptive analysis and diagnostic QA only |
| Raw data copied into W24 | no (22 MB export remains external; pinned by hash) |
| Missing information | wall clock/clock sync, calibration identity, certified device identity, absolute event UTC, independent held-out group, frozen critical threshold |

The 18 segments are **not** 18 independent experiments. The five S2 windows share
one physical session. Repeated windows within a boot are never independent runs.
The canonical W08 validator was rerun against the **W05 candidate capture**, not
against the 18-row normalized package; the 18-segment package was assessed
separately as a bounded descriptive package and was **not** formally admitted by
the canonical W08 validator.

## 4. Split manifest and feature registry

| Field | Value |
|---|---|
| Split manifest | `ml/reports/W11/cv-fold-manifest.yaml`, SHA-256 `702623f12e04cdc0162cb5517e691fbf62cee85d25b0c651a267ff46cc91e8c6` |
| Grouping key | `run_id + pair_id` (one effective group per pair) |
| Effective independent groups | 8 development pairs |
| Folds / seed | 4 / 42 |
| Train / validation / locked test | 8 runs / 8 runs / 4 synthetic runs (2 pairs) |
| Test partition used | `false` |
| Locked-test handling | W16 pre-registration only; `holdout_opened = false`; `evaluation_status = NOT_RUN` |
| Scientific eligibility | synthetic only; **no physical predictive split approved** |

| Field | Value |
|---|---|
| Feature registry | `ml/feature-registry-v1.yaml`, SHA-256 `f1c716a61c1d5c8eeaf0ff6e9596320c6df0bb47bce11ece0e67c038c72ffdbb` |
| Feature version | `CG-FEAT-1.0`, `FROZEN_DEFINITIONS` |
| Registry schema hash | `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9` |
| Ordered features | 28, order hash `98491993d95ba78292cc245d637a1832ebdfb80b1eb026361e39926fb331223c` |
| Missing values | explicit missing, never zero-filled |
| Sensor roles | T1 = CHAMBER_CENTER; T2 = **TEC_HOT_SIDE**; T3 = CHAMBER_BOTTOM; T4 = CHAMBER_NEAR_DOOR |
| T2 in chamber-air aggregate | **false** |

## 5. Final result files

| Artifact | Status |
|---|---|
| `ml/reports/DataRecovery/real-observation-summary.csv` | Present, SHA-256 `605234075507e539fc98e8e7cefa06ca3fcb1fc4fdcfc932d5d4c5276f8592ff` — **real physical descriptive table**, not a predictive or A/B result |
| Synthetic benchmark metrics | Present (W11/W12 CSVs), `SYNTHETIC_SOFTWARE_CONTROL_ONLY` |
| Statistical test-fixture results | Present (W22), `SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY` |
| `FINAL_PREDICTIVE_RESULT_CSV` | **NOT_PRODUCED** |
| `FINAL_PHYSICAL_AB_RESULT_CSV` | **NOT_PRODUCED** |

No placeholder numerical rows were invented. No synthetic result substitutes for
a missing physical result.

## 6. Model artifact (W15)

| Field | Value |
|---|---|
| Artifact | `ml/reports/W15/model/model.ubj` |
| Observed SHA-256 | `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f` |
| Expected SHA-256 | identical |
| Secondary JSON | `67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd` |
| Model manifest | `85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e` |
| Model card paths | `ml/reports/W15/model-card-W15.md`; `ml/reports/W23/model-card-W23.md` |
| Training population | 1 936 synthetic rows / 16 development runs; locked test unused |
| Feature order / config | `98491993…` / `4369f39f…` |
| Model version | `coldguard-xgb-v1-development-v1` |
| Output semantics | **risk score only** (not a calibrated probability) |
| Release eligibility | `NON_DEPLOYABLE_CANDIDATE` |
| Native diagnostic | 1 of 28 features used (`time_since_open`, 60 splits); 27 unused |

The artifact was **not refit**. W24 verifies bytes only; the W15 fitting driver is
not executed because W24 is a feature-freeze milestone.

## 7. Real physical figures (12)

All 12 SVG files exist, match the hashes declared by
`recovery-manifest.json`, embed `PHYSICAL_RECORDED_DATA`, the A source revision,
a source SHA-256 pin, `degC` units and the boot-scoped time domain.

| Plot | SHA-256 |
|---|---|
| `ml/reports/DataRecovery/real-physical-plots/chamber-air-a20261107-trial2.svg` | `b3b41f3276df58572b374126e6b8ed915c9ff18bfc4f4f26361ee7e19cc10550` |
| `ml/reports/DataRecovery/real-physical-plots/chamber-air-a20261107-w10-03-run1.svg` | `a2788e204916e00aa73e28514e7bc72f03ab86251a37fd8794f917b48ff90488` |
| `ml/reports/DataRecovery/real-physical-plots/cooling-a20261107-a-w07-03-trial-2-be89bf4a.svg` | `8e17498c77e2164f3e677fbfcc56d62000a529802d75f37fa87fc9c19a69b2b5` |
| `ml/reports/DataRecovery/real-physical-plots/cooling-a20261107-h8-c-600s-tec-100pct.svg` | `716a9925475d2e78439644d380ccc806dda9d30dc3d611655c292b3a6207a52b` |
| `ml/reports/DataRecovery/real-physical-plots/cooling-a20261107-h8-e-1800s-tec-100pct.svg` | `152fa879eb67af8ef706271f6d5daa65754ec1cfbf9a200c42f4d53ed18488b3` |
| `ml/reports/DataRecovery/real-physical-plots/door-a20261107-w10-02.svg` | `87d980e801c39bed6c95a8086869c30e26d990027fbbb1a75c0224b53a9439a7` |
| `ml/reports/DataRecovery/real-physical-plots/door-a20261107-w10-03-run1.svg` | `d21c2c16b55d8da7986aaef2fcc7dfcc0a65a80c7c69541a91323d0477379648` |
| `ml/reports/DataRecovery/real-physical-plots/door-a20261107-w10-03-run2.svg` | `aaba23872eb5e4d40f4934faf4a9b9ad6c4d70472a7ded3d0a352d75d8d008f2` |
| `ml/reports/DataRecovery/real-physical-plots/door-a20261107-w10-03-run3.svg` | `810e1d418a955fd0d375a45c6ed21c12bd16ab52238cf2936caed0d4fb55f30e` |
| `ml/reports/DataRecovery/real-physical-plots/door-a20261107-w10-03-run4.svg` | `5a43a1d3a00d38ccbae0e381ae871fe56210c7ad1e98d422a375dd2b10435e39` |
| `ml/reports/DataRecovery/real-physical-plots/missingness-inventory.svg` | `fe3f5022d9595d849a98f55f87f1498b7857c97192069657397d295247dc75b3` |
| `ml/reports/DataRecovery/real-physical-plots/w05-diagnostic.svg` | `5d6c60ddf9f74a68b3f147be222ad9cd599554719163bafd87e82c2d0b537054` |

## 8. W23 inventory reconciliation (97 / 88 / 9 versus 83)

The delivered W23 package declares **97 source entries: 88 local, 9 unavailable**.
Re-running `scripts/w23-evidence-audit-W23.py` in W24 verifies **88 local sources,
9 unavailable, 0 violations**. The W23 clean-room receipt records an earlier
**83 verified** line.

Reconciliation: 83 + 9 = 92 entries, which is the earlier 92-source package
revision. Five local manifest sources were subsequently added to the final
manifest: W05 QA, W07 EDA, W08 Gate B, W09 baseline and W10 feature manifests.
The delivered 97-source manifest therefore verifies 88 local sources. The W23
receipt was **not rewritten** — W24 records the delivered revision and the
re-audit result instead of copying a stale count.

## 9. W16 refusal record

`ml/reports/W16/locked-test-result.md` is a **refusal report**, not a completed
evaluation. It records `NOT_EXECUTED_PREREQUISITES_UNMET`,
`holdout_opened = false`, `evaluation_status = NOT_RUN`, and states that no AP,
precision, recall, EWT, AIW or calibration metric exists. It must never be
cited as a locked-test result.

## 10. Scientific status retained

| Gate / state | Value |
|---|---|
| GATE_B_PHYSICAL_DATA | RED |
| PREDICTIVE_DATASET_READINESS | NOT_READY |
| G3 | NO-GO / FIX DATA |
| PRIMARY_HORIZON | NOT_FROZEN |
| REAL_PREDICTIVE_BENCHMARK | NOT_ESTABLISHED |
| REAL_EWT / REAL_AIW | NOT_ESTIMABLE / NOT_ESTIMABLE |
| W15 model | SYNTHETIC_NON_DEPLOYABLE_CANDIDATE |
| W16 locked test | NOT_OPENED |
| W20 physical A/B analysis | NOT_RUN |
| G4 / G5 | NOT_READY / NOT_ESTABLISHED |

## 11. Limitations

- Hash verification proves byte identity, not scientific validity.
- `source_commit` identifies the last path-touching commit, not a W24 rebuild.
- The physical export remains external; W24 pins its identity but does not copy
  raw data into the package.
- The W15 artifact is verified, not recalibrated; its dominant feature shortcut
  remains a non-deployability reason.
- No independent human has replayed the W24 procedure
  (`INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING`).

## 12. Reproduction

```bash
cd ml
uv lock --check
uv sync --locked --python 3.12 --extra test
uv run --locked --python 3.12 --extra test pytest -q
uv build
```

Deterministic checks executed in W24:

```text
W23 evidence audit, two processes       -> byte-identical; 88 verified / 9 unavailable / 0 violations
DataRecovery regeneration, two processes -> byte-identical; 19 artifacts; matches committed package
W16-W22 layer replays, two passes        -> byte-identical; W16 differs only in repository_revision
```

The full receipt is [`reproduction-result-W24.md`](reproduction-result-W24.md).
