# ColdGuard · Dataset/Analysis Artifact Naming & Versioning Convention (W01, Member B)

> Deliverable of task **B-W01-04** (Doc `05B` §29). Lightweight identity/versioning for
> Member-B analysis artifacts: what gets an identifier, what versions bump, when artifacts become
> immutable, what seeds/hashes get recorded. It defines FILE/FOLDER + manifest discipline only —
> **no registry service, no database schema, no MLflow** (§8 explicit non-goals).

| Field | Value |
|---|---|
| Owner | Member B |
| Reviewer focus | Dataset/split reviewer: A or C (Doc `04` §3.3) |
| Parent docs | Doc `00` §5.4 · Doc `02` §§14.9, 51–52, 60–61, 63 · Doc `03` §§31, 42–44, 47, 49, 79, 92–93, 97, 125–127, 133, 135, 158–159, 190, 201 · Doc `04` §§3.3, 10 · Doc `05B` §§4–9, 24, 28–32, 38–39 |
| Status | v0 (W01 contract; extensions PROVISIONAL until each domain's predeclared freeze) |

Tier legend shared with the other three W01 files.

---

## 1. Design principles (each traceable)

1. **Regenerability before convenience** — L0 raw is immutable; L2/L3 artifacts must be regenerable from L0/L1 + recorded config (`05B` §4 CANONICAL). Reproducible regeneration beats hand-edited correctness.
2. **Identity stable, content hashed, edits make NEW versions** — an artifact's identifier never changes meaning and never mutates in place once frozen (§4); mutable copies are an anti-pattern at evidence scale (`03` §190 final artifact checksums CANONICAL).
3. **Version granularity per artifact class** — a shared version schema for datasets/splits/features/models/analysis keeps failure forensics possible (`02` §60 versioning rules CANONICAL).
4. **Only what is evaluated-or-referenced must be frozen** — freeze pressure comes from events (`03` §§49, 92, 97, 133), not from preference; draft churn is legal.
5. **Manifests are text files in-repo** — they enter version control and PR review; nothing depends on notebook memory (`05B` §8 explicit; `02` §51.1 no hidden filters CANONICAL).
6. **Seeds recorded at consumption point** — every stochastic step writes the seed it consumed (`03` §79 bootstrap seed CANONICAL; `05B` §24 random seeds + environment record).

## 2. Identifier vocabulary (canonical reuse; extensions provisional)

Identifiers below exist in the CANONICAL docs; B reuses them, never invents parallel namespaces:

| Identifier | Pattern family | Canonical anchor | B-side binding |
|---|---|---|---|
| `hardware_config_id` | `CG-HW-…` (e.g., `CG-HW-001`) + `pin_map_version` | `01` §39.1 | dataset/split manifest field |
| `calibration_id` | `CG-CAL-…` | `01` §39.2 | dataset manifest field |
| `operating_envelope_id` | `CG-OE-…` (blank until commissioning) | `01` §39.3 | referenced context, PROVISIONAL values |
| run id | `CG-S<scenario>-<arm>-<serial>` exemplars (`CG-S2-A-001`, `CG-S2-B-004`) | `05B` §7; `02` §63 example; C fixtures | dataset `source_runs` list |
| scenario ids | `S1 NORMAL_BASELINE`, `S2 DOOR_DISTURBANCE`, `S3 THERMAL_EFFECTIVENESS_DEGRADATION`, `S4 ACTUATION_RESPONSE_FAULT`, `S5 CONNECTIVITY_LOSS`, `S6 SENSOR/OBSERVATION_DEGRADED` | `03` §31 | run metadata |
| `dataset_id` | `CG-DATA-…` | `05B` §7 | §3.1 |
| `split_id` | `CG-SPLIT-…` (e.g., `CG-SPLIT-001`) | `05B` §8 | §3.2 |
| `feature_version` | exact definition/order/window identity | `02` §60.5; `05B` §9 | §3.3 — naming grammar PROVISIONAL (§6) |
| `model_version` | model artifact identity | `02` §60.6, §14.9 | §3.4 — first minted at `05B` §39 XGBoost v1 (SCHEDULED_DEBT) |
| `policy_version` | controller policy identity | `02` §60.7 | owned by D; referenced in A/B analyses |
| `prediction_id` | backend prediction record key | `02` §14.6 | L4-side linkage (C realization) |
| verification/experiment ids | `AI-…`, `DIAG-…`, `RES-…`, `PERF-…`, test-id namespaces per class | `03` §155 verification-id namespace | referenced in analysis manifests |

**B-owned extension grammar (all PROVISIONAL, may be corrected before first minting):**

- `feature_version`: `CG-FEAT-<major>.<minor>` — the registry file IS the version (feature_checksum auto-recorded); minted when the first registered feature set sees evaluation (`05B` §30–32, §38). One feature_version per evaluation context, never per week.
- `analysis_version`: `CG-EVAL-<serial>` — freezes ONE evaluation context (metric manifest + split_id + feature_version + seed set + analysis code hash).
- `analysis code hash` and artifact hashes are SHA-256 everywhere (consistency with the backend raw-store `payload_sha256` discipline — TEAM_DEPENDENCY precedent, `telemetry_raw`).

No other spontaneous namespace. The moment an identifier pattern is needed that is absent here, this convention becomes the PR that records it (§10) BEFORE an artifact bearing it ships.

---

## 3. Artifact classes and their version identity

### 3.1 Dataset artifact (`dataset_id = CG-DATA-…`)

Manifest fields (CANONICAL shapes from `05B` §7; `03` §126 dataset card complement):

```yaml
dataset_id: CG-DATA-001
source_runs:            # run-level, never row-level
  - CG-S2-A-001
hardware_configs:       # comparability guard (register LRK-15)
  - CG-HW-001
schema_version: 1
calibration_ids: []
export_query_hash: <sha256 of canonical export query>
created_at: <utc>
created_by: member-b
git_commit: <repo sha>
status: draft            # draft | locked | final   (§4)
content_sha256: <sha256> # at lock/freeze
synthetic: false         # fixture provenance flag (dictionary §11)
```

Row-level data files (parquet/csv) are NOT hand-edited after `content_sha256` exists. The manifest cites the export that produced them.

### 3.2 Split artifact (`split_id = CG-SPLIT-…`)

Canonical fields (`05B` §8):

```yaml
split_id: CG-SPLIT-001
dataset_id: CG-DATA-001        # sourced dataset (B-referenced binding)
train_runs: []
validation_runs: []
test_runs:
  - CG-S2-A-004
grouping:
  key: run_id                  # CANONICAL (03 §47)
hardware_lineage:              # LRK-15 coupling; single value unless a documented, A-reviewed exception
  hardware_config_id: CG-HW-001
locked_test:
  frozen_at: <utc or null>
  opened_at: null              # stays null through the whole tuning campaign (03 §49; register LRK-11)
controller_context: all-reactive-or-observational   # LRK-09 coupling; predictive-closed-loop requires explicit variant tag
created_at: <utc>
created_by: member-b
git_commit: <repo sha>
status: draft | locked | final
content_sha256: <sha256>
split_seed: <int>              # recorded whenever any stochastic assignment was used (03 §79; 05B §24)
```

No split may exist only in notebook memory (CANONICAL, `05B` §8). Locked test run IDs get recorded once and inspected never-before-unlock (`03` §49).

### 3.3 Feature artifact (`feature_version`)

Registry entry shape (`05B` §9; `03` §125):

```yaml
name: tmean_slope_30s
feature_version: CG-FEAT-1.0     # registry version, not per-feature
sources: [t1_c, t2_c, t3_c]
window_s: 30
method: linear_regression
causal: true                     # past-only assertion (02 §19.4)
missing_behavior: explicit_missing_flag  # one of dictionary §13's four legal strategies
units: c_per_s
```

The registry is a folder of per-version YAML files (`ml/features/registry/`); a version is immutable once any split/model/evaluation references it. `feature_version` identity covers: ordered feature list + formula set + window grammar + missing-behavior choices (CANONICAL scope, `02` §60.5).

### 3.4 Model artifact (`model_version`)

Record shape aligns with `03` §127 model card + `02` §14.9 minimal registry concepts (no service — §8):

```yaml
model_version: CG-MODEL-001      # first mint at 05B §39 (SCHEDULED_DEBT)
feature_version: CG-FEAT-1.0
dataset_id: CG-DATA-001
split_id: CG-SPLIT-001
horizon_s: <frozen single value>  # PROVISIONAL until 03 §44 freeze; no "inferred from filename" (02 §19.6)
training_commit: <repo sha>
artifact_path: ml/artifacts/model/<model_version>/
artifact_sha256: <sha256>
training_seed: <int>
metrics_summary: {dev_only: true} # locked-test results attach only via a separate evaluation record (03 §92)
calibration_version: <id or none>  # none ⇒ score-only semantics (03 §59)
status: candidate                  # 02 §52 lifecycle: candidate → offline_eval → shadow → controller-B (realized by records, not a service)
```

Long-term serialization uses official XGBoost serialization, not pickle-only (`02` §19.2 CANONICAL). Final inference determinism within numerical tolerance is required (`05B` §24).

### 3.5 Analysis artifact (`analysis_version`)

Freezes an evaluation context:

```yaml
analysis_version: CG-EVAL-001
kind: locked-predictive-test | ablation-A1 | AB-paired | calibration-check | ...
split_id: CG-SPLIT-001
feature_version: CG-FEAT-1.0
model_version: <id>
metric_manifest_id: <statistical-freeze record id>   # 03 §133 freeze: primary metric, sign convention, CI level, bootstrap seed/iterations, test family
analysis_code: path/to/script.py
analysis_code_sha256: <sha256>
environment_record: <py version; lib versions from lockfile (05B §24)>
inputs: [<artifact ids consumed>]
outputs: [<paths produced>]
seed_lineage: [split_seed?, training_seed?, bootstrap_seed, ...]  # every seed any step consumed (03 §79)
```

The reproduction recipe is: dataset + split + feature/model + analysis_version + environment ⇒ regenerate outputs. `03` §135 reproducibility-package fields all map to these five artifact classes.

---

## 4. Lifecycle and immutability rules (bind to canonical freeze events)

Statuses: `draft → locked → final`.

- **draft**: mutable; may be regenerated/replaced at will. Nothing may cite a draft artifact as evidence (except scratch tests that themselves stay draft).
- **locked**: an artifact that is EITHER referenced by another artifact's evaluation OR hit by one of the freeze events below. On locking: compute/record `content_sha256`, `locked_at`, `git_commit` and forbid in-place edits forever; any change version-bumps. Verification on load: recompute hash, fail on mismatch (§5).
- **final**: a locked artifact whose referenced evaluation is complete and reported (e.g., locked-test result attached). Forensics can only add annotations, never rewrite cells (`03` §159 campaign-log discipline applies to edits).

Canonical freeze events that promote artifacts to `locked` (all CANONICAL, Doc `03`):

| Event | Frozen artifact | Freeze clause |
|---|---|---|
| locked test run IDs chosen | split artifact test_runs + locked_test.frozen_at | `03` §49 |
| model goes to locked test | model artifact (feature_version, hyperparameters, artifact hash, threshold, persistence, calibration method, primary horizon) | `03` §92 |
| Controller settings for A/B | controller/policy records (D-owned; B-referenced) | `03` §97 |
| statistics plan for a campaign | metric manifest (metric, sign convention, CI level, seeds, test family, invalid-pair rule) | `03` §133 |
| label definition for final splits | label-spec identity (boundary, representative temperature, horizon) | `03` §§42–43 |
| campaign code | analysis_code_sha256 + environment record | `03` §158 change freeze |

Post-test correction path: if a locked/final artifact must change for a bugfix, the OLD version is kept and a NEW version is minted; locked-test reuse of the old evaluation is invalid unless fresh test data replaces it (`03` §93 CANONICAL).

## 5. Content identity recipe (practical, service-free)

1. **What a hash covers**: the serialized content of the artifact itself (data file bytes; manifest YAML canonicalized in key order) + the identity of its declared inputs (child artifact ids + their own `content_sha256`). This makes tampering with any upstream artifact detectable transitively.
2. **When computed**: at `locked` / `final` promotion; recomputed at every load and on demand by an audit command; mismatch fails hard (audit printout names the offending artifact).
3. **Where stored**: inside the artifact's own manifest (`content_sha256` field); aggregate checks live in QA reports (`03` §190 checksums evidence; `03` §135 reproducibility package lists dataset export manifest + model artifact + policy config).
4. **Provenance requirements**: every manifest carries `git_commit` + `created_by` + `created_at` (`03` §135 source commit; `00` §5.4 "an experiment without sufficient provenance is not report-grade evidence" CANONICAL).

## 6. Naming discipline

- **Folders** follow `05B` §5's conceptual skeleton (exact folder names may vary — CANONICAL permission; boundaries stay visible):

```text
ml/
├─ contracts/                 # W01 transition: the four W01 contract files live at ml/ root today (§7)
├─ data/
├─ manifests/
├─ splits/
├─ qa/
├─ exports/
├─ features/
│  ├─ registry/               # per-version YAML files (§3.3)
│  ├─ transforms/
│  └─ tests/
├─ baselines/
├─ training/
├─ evaluation/
├─ calibration/
├─ ablation/
├─ artifacts/
│  └─ model/                  # §3.4
└─ reports/
```

- **File naming**: `<artifact-class>-<id>-<optional-role>.<ext>`; optional role suffixes useful in practice (`dataset-CG-DATA-001-telemetry.parquet`, `split-CG-SPLIT-001-manifest.yaml`, `report-locked-test-CG-EVAL-004.md`).
- **Forbidden names/practices**: `final_v2`, `REAL_USE_THIS`, `latest(2)`, dates-based "versions" masking identity, notebook-memory-only splits, unrecorded filters, renames of locked artifacts, and any name that hides a version jump (`02` §51.1 no hidden filters; `05B` §8; convention §4).
- **Evidence recorder**: weekly evidence README at `evidence/B/Wxx/` citing the used ids per `05B` §28 (goal / dataset-run ids / split id / feature version / model version / seed / commands / metrics / result / pass-fail / limitations).

## 7. W01 tree reality and transition note

W01 delivers exactly four contract documents at the `ml/` root (exact `05B` §29 filenames): `claim-data-matrix.md`, `data-dictionary-v0.md`, `leakage-risk-register.md`, this file. When the first runnable data/feature/split machinery lands (W02+ synthetic harness), these four move under `ml/contracts/` **without identifier or content changes** (path-only move; the documents' authority is `git_commit` provenance, not payload hashes of peer artifacts). Gate: the move happens in a PR subject to the reviewer matrix (`04` §3.3).

## 8. Explicit non-goals (per W01 scope)

- **No model-registry service / database**: `02` §14.9/§52 lifecycle concepts map to the file-based statuses above; a service realization is a later, D/C-scope decision. Nothing here creates a DB schema.
- **No MLflow/DVC/W&B adoption**; reproducibility rides on repository-committed manifests + lockfiles (`03` §135; `05B` §24 dependency-lock version requirement).
- **No artifact signing/infra, no object store**: in-repo version control is the audit trail.
- **No ML feature store service**: dataset export + feature_registry suffices for P0 scale.

## 9. Consistency bindings (audit rules)

A binding is a cross-artifact identity fact; violation = invalid artifact:

| # | Binding | Enforced on |
|---|---|---|
| B1 | `split.dataset_id` resolves to exactly one dataset manifest, and split run-set union (train ∪ validation ∪ test) == `dataset.source_runs` | split & dataset manifests |
| B2 | `model.feature_version` == the referenced feature-registry version; `model.split_id` run set ⊆ `model.dataset_id` `source_runs` | model + feature/versioned registry |
| B3 | analysis_version references EXISTING locked split + feature/model + metric manifest (all `locked`/`final` status) | analysis manifest |
| B4 | no calibration/threshold artifact cites `locked_test.opened_at != null` unless a compatible fresh-test disclosure is present | pre-report QA |
| B5 | hardware lineage inside one split family = single `hardware_config_id` value unless registered exception w/ A delivered invalidation note | split manifest |
| B6 | every seed consumed is listed in `seed_lineage` of the consuming artifact | all manifest writers |
| B7 | synthetic fixture flag propagation: `synthetic: true` data never merges into a dataset manifest with `synthetic: false` without a distinct dataset_id | export QA |

These bindings are audited by a future small checker script (SCHEDULED_DEBT, B-side, first runnable at the W02 harness — no W01 code).

---

## 10. Change control for this convention

- The convention (and the whole W01 contract set) changes via Member-B PR; reviewers per Doc `04` §3.3 (dataset/split: A or C).
- Identifier-pattern additions (new `CG-…` namespaces) must be recorded here with a tier tag BEFORE the first artifact carrying the pattern commits.
- No relaxation of an immutability rule without a review-disclosed `revision-history` entry; the rule set exists to make silent drift impossible (`03` §201 prohibited shortcuts spirit).

## 11. Seed policy summary

- One seed lineage per artifact: stochastic consumers record the exact integer seed AND the consuming artifact id in their own manifest (`03` §79 seed recorded CANONICAL; `05B` §24 record list CANONICAL).
- Split assignment (if stochastic, e.g., `GroupShuffleSplit`-shaped): split artifact `split_seed`, plus grouping key + counts; deterministic pipeline check via harness replay (register LRK-01/02 tests).
- Training (XGBoost): `training_seed` recorded with model_version; RQ-REQUIRED acceptance is reproducible deterministic inference within numerical tolerance (`05B` §24 CANONICAL).
- Bootstrap/statistical resampling: `bootstrap_seed` + iterations frozen pre-campaign in the metric manifest (`03` §§79–80, §133 iterations/seed CANONICAL).
- Environment reproducibility: Python/library versions come from the committed lockfile (`ml/uv.lock`) — that same file already gates the W01 package tests (`03` §135 dependency-lock CANONICAL; `05B` §24).

## 12. Pass-criterion connection (Doc `05B` §29)

With this convention, a reviewer must be able to ask "which split_id ran, with which feature/model/analysis version, which seeds, and which hash?" and receive answers only from committed artifacts — the same question set that closes the pass-criterion circle over claim↔data (matrix §6), field↔semantics (dictionary), and risk↔detection (register). The convention deliberately stops at identity discipline; mechanics belong to later-week implementers respecting these ids.

---

Convention ends. Anchor citations above are the authority chain; no rule herein may be read as overriding Docs `00`–`03`.
