# W23 reproducibility runbook — Member B offline software chain

> **Task:** B-W23-04. This runbook covers the **Member B offline
> evidence-reproduction subset only**. It does not authorize firmware flashing,
> actuator control, broker/device control, Controller B enablement or any
> physical experiment.

## 1. Three different reproduction questions

| # | Question | Owner | W23 status |
|---|---|---|---|
| 1 | Can a clean environment reproduce the permitted Member B software chain? | B | **EXECUTED** (see `clean-room-replay-W23.md`) |
| 2 | Has another **human team member** executed the procedure? | independent member | **PENDING** — not claimed |
| 3 | Can the final physical analysis be reproduced? | B with A/C/D/leader authorization | **NOT_AUTHORIZED** — W20 gate locked |

```text
TECHNICAL_CLEAN_ROOM_REPLAY = PASS / PARTIAL / FAIL   (receipt)
INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING
SCIENTIFIC_ANALYSIS_NOT_AUTHORIZED
```

## 2. Prerequisites

- Windows/Linux/macOS with Git and a network connection for the first dependency
  sync.
- `uv` available on `PATH`. On this operator machine it is
  `D:\iot\.tools\uv\uv.exe`; the repository does not vendor it.
- Python 3.12 is selected by `uv`; the project declares `requires-python >= 3.12`
  and `uv.lock` pins the environment.
- No optional A/C/D evidence checkout is required for the committed W23 package.
  Optional pinned A evidence enables additional tests; absence is recorded as a
  skip, never as a pass.

## 3. Fresh checkout

Create an isolated checkout at the verified base. The W23 generation base is the
W22 head `cf0716df90a1b9a617df0e61166e218a4f263374`. The W23 delivery commit is
recorded in the PR and final report; the package uses the repository
`GENERATION_BASE_NOT_DELIVERY_COMMIT` convention.

```bash
git fetch origin
git worktree add ../worktree-b-w23-clean cf0716df90a1b9a617df0e61166e218a4f263374
cd ../worktree-b-w23-clean
# For the W23 packaged content, check out the W23 delivery commit or apply the
# W23 working tree; do not reuse an old .venv or generated caches as proof.
```

Do not reuse the development worktree’s `.venv`, `dist/`, test caches or report
outputs as a clean build. The W23 audit treats a stale duplicate as a failure.

## 4. Locked environment and package build

```bash
cd ml

uv lock --check

uv sync --locked --python 3.12 --extra test

uv run --locked --python 3.12 --extra test pytest -q

uv build
```

Expected: `uv lock --check` resolves without changing `uv.lock`; the full test
suite passes with only the documented optional skips; `uv build` produces a wheel
and sdist. Record the exact counts and skip reasons in
`clean-room-replay-W23.md`.

## 5. Layer replay commands (temp output, no prior-artifact mutation)

Run from `ml/`. Each command writes to a temporary directory. **Never** point
`--out`/`--out-dir` at `reports/W05…W22` during verification; that would mutate
prior-layer artifacts.

```bash
TMP="$(mktemp -d)"

# W16 readiness preflight (metadata only; fail-closed gate)
uv run --locked --python 3.12 python scripts/w16-preflight-W16.py \
  --out "$TMP/W16"

# W17 offline feature/prediction parity and shadow trace (synthetic)
uv run --locked --python 3.12 python scripts/w17-shadow-replay-W17.py \
  --out-dir "$TMP/W17"

# W18 runtime monitoring and trace-integrity audit (synthetic)
uv run --locked --python 3.12 python scripts/w18-runtime-audit-W18.py \
  --out-dir "$TMP/W18"

# W19 pair-ledger, validity and no-peeking gates (fixtures)
uv run --locked --python 3.12 python scripts/w19-campaign-audit-W19.py \
  --out-dir "$TMP/W19"

# W20 campaign-lock preflight (metadata only; must stay blocked)
uv run --locked --python 3.12 python scripts/w20-campaign-preflight-W20.py \
  --out-dir "$TMP/W20"

# W21 resilience/diagnosis audit (recorded checks NOT_VERIFIED without a pinned A checkout)
uv run --locked --python 3.12 python scripts/w21-resilience-audit-W21.py \
  --out-dir "$TMP/W21"

# W22 paired-statistics software contract (toy fixtures only)
uv run --locked --python 3.12 python scripts/w22-statistics-contract-W22.py \
  --out "$TMP/W22"
```

### W15 model artifact

The W15 driver (`scripts/w15-electrical-ablation-W15.py`) **refits** the model.
W23 is a feature-freeze milestone and does not perform new model fitting, so W23
does not re-execute the fitting driver. The artifact is instead verified by:

```bash
sha256sum reports/W15/model/model.ubj reports/W15/model/model.json \
          reports/W15/model/model-manifest-W15.json
# expected:
# model.ubj          25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f
# model.json         67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd
# model-manifest     85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e

uv run --locked --python 3.12 --extra test pytest -q tests/test_w15_artifact.py
```

The W15 model bytes are deterministic in process; the fresh-process reload and
probe parity are recorded in the W15 model manifest (`max_abs_diff = 0.0`,
tolerance `1e-12`).

### W13 replay

W13’s driver requires the pinned A 20261107 dataset export
(`COLDGUARD_W13_A_DATASET_DIR`). That export is **not present** in this checkout,
so the W13 CLI replay is `REPRODUCTION_PENDING_SOURCE_ACCESS`. Three W13 tests
skip for this reason. The committed W13 manifest and horizon decision remain
hash-bound and are verified by the W23 audit; their absence from a live replay is
not treated as a failed physical dataset.

## 6. W23 evidence package verifier

```bash
cd ml

uv run --locked --python 3.12 python scripts/w23-evidence-audit-W23.py \
  --manifest reports/W23/evidence-package-W23.json \
  --root .. \
  --out "$TMP/W23-audit-run1"

uv run --locked --python 3.12 python scripts/w23-evidence-audit-W23.py \
  --manifest reports/W23/evidence-package-W23.json \
  --root .. \
  --out "$TMP/W23-audit-run2"

diff -r "$TMP/W23-audit-run1" "$TMP/W23-audit-run2"
```

The verifier:

1. reads only the explicit allowlisted manifest;
2. resolves each permitted source path;
3. recomputes accessible file hashes;
4. compares declared hash and source identity;
5. reports exact missing/mismatched files;
6. distinguishes locally present, external pinned and withheld artifacts;
7. exits non-zero on integrity violations;
8. never opens locked-test outcomes or final physical A/B outcomes.

## 7. Skip and failure semantics

| Situation | Correct report |
|---|---|
| 3 W13 tests without the pinned A 20261107 export | `SKIPPED — REPRODUCTION_PENDING_SOURCE_ACCESS` |
| 1 W21 test without an optional live A checkout | `SKIPPED — SOURCE_UNAVAILABLE` |
| W13 script without the A export | `REPRODUCTION_PENDING_SOURCE_ACCESS` (not a physical-data failure) |
| W16 preflight refusal | `EXPECTED_FAIL_CLOSED` — the gate must refuse |
| W20 preflight blocked | `EXPECTED_FAIL_CLOSED` — analysis remains locked |
| A/C/D unmerged PR | `UNMERGED_EXTERNAL_REFERENCE` (not accepted evidence) |
| Physical analysis | `SCIENTIFIC_ANALYSIS_NOT_AUTHORIZED` |
| Another human has not run this | `INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING` |

A skipped test is never reported as a pass. A missing optional export is never
reported as a failed physical dataset.

## 8. Physical boundary

Do **not** perform the canonical full-system physical demo procedure. W23 does
not flash firmware, command actuators, enable Controller B, connect to the broker,
or run a physical experiment. Member A/C/D own integration and physical
authorization. The present procedure is the Member B offline software subset.

## 9. Expected external dependencies

| Dependency | State | Effect on W23 |
|---|---|---|
| A PR #95 (`fix/a-main-acceptance-integrity`) | OPEN, unmerged | PR95 supplement remains `NOT_VERIFIED_FOR_CANONICAL_USE` |
| A W21 result payload (`evidence/A/W21/results/`) | `SOURCE_UNAVAILABLE` | W21 recorded checks stay `NOT_VERIFIED`; summary metadata consumed |
| C PR #72 outage/resync | OPEN, unmerged | no accepted C trace/export evidence |
| C PR #98 resilience/security | OPEN, unmerged | host software simulation only; refused as physical |
| D final policy version | `NOT_FROZEN` | Controller B authorization remains withheld |
| W16 locked test | `NOT_OPENED` | no locked metrics |
| W20 final analysis | `LOCKED` | no real paired statistics |

## 10. After the run

Record in `clean-room-replay-W23.md`:

```text
clean checkout SHA
Python/uv versions
dependency-lock hash
test collection and passed/failed/skipped counts
skip reasons
wheel/sdist outcome
model artifact hash result
replay outputs
artifact hash comparisons
environment assumptions
unexpected manual steps
```

No fictional final-analysis receipt. No invented human reproduction.
