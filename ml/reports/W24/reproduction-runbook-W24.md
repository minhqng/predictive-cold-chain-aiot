# W24 reproduction runbook — Member B final handover

> **Task:** B-W24-02. This runbook reproduces the **available** Member B
> software and the **real physical descriptive** package. It does not authorize
> model retraining, locked-test opening, physical A/B analysis, firmware or
> actuator work.

```text
SOFTWARE_CHAIN = REPRODUCIBLE
REAL_PHYSICAL_DESCRIPTIVE_PACKAGE = REPRODUCIBLE
FINAL_PREDICTIVE_TABLE = NOT_AVAILABLE
FINAL_PHYSICAL_AB_TABLE = NOT_AUTHORIZED
INDEPENDENT_HUMAN_REPLAY = PENDING
```

## 1. Scope

| Question | Reproducible now? | Where |
|---|---|---|
| Clean environment builds and tests the software | yes | §4 |
| W15 model bytes match the declared artifact | yes | §5 |
| W16–W22 layer outputs regenerate | yes | §6 |
| W23 evidence audit verifies the package | yes | §7 |
| Real physical descriptive tables and 12 plots regenerate | yes | §8 |
| Final predictive locked-test result | **no** — `NOT_PRODUCED` | §9 |
| Final physical A/B effect/CI/p | **no** — `NOT_AUTHORIZED` | §9 |
| Another human ran this procedure | **not yet** — `PENDING` | §11 |

## 2. Prerequisites

- Git and a POSIX shell (Linux/macOS, or Git Bash on Windows).
- `uv` on `PATH` (`uv --version`). The repository does not vendor `uv`.
- Network access for the first locked dependency sync.
- Python 3.12 is selected by `uv`; no system Python is required.
- Disk: the A export is about 22 MB; test/build outputs are small.
- No broker, hardware, firmware or Controller B access is needed or permitted.

## 3. Fresh checkout

Use the W24 delivery branch/commit recorded in the PR. Do **not** reuse an
existing `.venv`, `dist/`, pytest cache or report output as proof.

```bash
git fetch origin
git worktree add ../worktree-b-w24-clean <W24_DELIVERY_COMMIT>
cd ../worktree-b-w24-clean
```

The verified generation parent is
`c0d8b247291c05cce308feae25b3fedd329af494` (PR #114 head). The W24 delivery
commit is recorded in the PR and final report, not embedded here (avoids a
circular revision dependency).

## 4. Environment and full verification

```bash
cd ml

uv lock --check
uv sync --locked --python 3.12 --extra test
uv run --locked --python 3.12 --extra test pytest -q
uv build
```

Expected:

| Check | Expected |
|---|---|
| `uv lock --check` | resolves; `uv.lock` unchanged |
| dependency lock SHA-256 | `dae6cae255b6cdd7c8ca0ded7e902124c0dac467215f309feb45642ad649e5a5` |
| full suite | all pass, only the 4 documented optional-source skips |
| `uv build` | wheel and sdist produced |
| model bytes | unchanged by the test run |

A skipped optional-source test is never counted as a pass. The four documented
skips are three W13 CLI tests (pinned A 20261107 export not exported to the
environment) and one W21 optional live A-checkout test.

## 5. W15 model artifact

```bash
sha256sum reports/W15/model/model.ubj reports/W15/model/model.json \
          reports/W15/model/model-manifest-W15.json
```

Expected:

```text
model.ubj             25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f
model.json            67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd
model-manifest-W15   85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e
```

**Do not run the W15 fitting driver.** W24 is a feature freeze; the artifact is
verified by bytes, not refit.

## 6. W16–W22 layer replays

Run from `ml/`. Write only to a temporary directory. Never point `--out` or
`--out-dir` at `reports/W05…W23`.

```bash
TMP="$(mktemp -d)"

uv run --locked --python 3.12 python scripts/w16-preflight-W16.py --out "$TMP/W16"
uv run --locked --python 3.12 python scripts/w17-shadow-replay-W17.py --out-dir "$TMP/W17"
uv run --locked --python 3.12 python scripts/w18-runtime-audit-W18.py --out-dir "$TMP/W18"
uv run --locked --python 3.12 python scripts/w19-campaign-audit-W19.py --out-dir "$TMP/W19"
uv run --locked --python 3.12 python scripts/w20-campaign-preflight-W20.py --out-dir "$TMP/W20"
uv run --locked --python 3.12 python scripts/w21-resilience-audit-W21.py --out-dir "$TMP/W21"
uv run --locked --python 3.12 python scripts/w22-statistics-contract-W22.py --out "$TMP/W22"
```

Expected results:

| Layer | Expected |
|---|---|
| W16 | exit 0; `REFUSED_PREREQUISITES_UNMET`; 47 requirements, 24 refused; `holdout_opened = false`; `evaluation_status = NOT_RUN` |
| W17 | exit 0; software verified; `LIVE_SHADOW_NOT_ESTABLISHED`; holdout not opened |
| W18 | exit 0; `SIGNOFF_WITHHELD`; holdout not opened |
| W19 | exit 0; `W20_ANALYSIS = NOT_UNLOCKED` |
| W20 | exit 0; `ANALYSIS_PREFLIGHT_BLOCKED`; `W20_FINAL_ANALYSIS = NOT_RUN` |
| W21 | exit 0; bounded on-device evidence; recorded checks `NOT_VERIFIED` |
| W22 | exit 0; toy fixtures only; physical analysis `NOT_AUTHORIZED` |

Committed-output comparison:

```bash
diff -r "$TMP/W17" reports/W17
diff -r "$TMP/W19" reports/W19
diff -r "$TMP/W21" reports/W21
diff -r "$TMP/W22" reports/W22
```

Expected: byte-identical. W18/W20 additionally contain committed input metadata
files (`freeze-baseline-W18.json`, `campaign-metadata-W20.json`) that the
drivers do not regenerate. W16's generated manifest differs only in
`repository_revision`; its four companion reports
(`holdout-readiness-W16.md`, `locked-test-protocol-W16.md`,
`locked-test-result.md`, `model-card-rc.md`) are committed inputs that the
preflight does not regenerate.

## 7. W23 evidence audit

```bash
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

Expected: exit 0 both times; `integrity_ok = true`; **88 VERIFIED, 9
SOURCE_UNAVAILABLE, 0 violations**; two-process output byte-identical.

The historical W23 receipt line of 83 verified reflects an earlier 92-source
package revision; the delivered manifest has 97 sources. See
[`artifact-integrity-W24.md`](artifact-integrity-W24.md) §8.

## 8. Real physical descriptive reproduction

The A 20261107 export is pinned by a repository commit, not by a local file.

```bash
# From the repository root
TMP="$(mktemp -d)"
mkdir -p "$TMP/a-export"
git archive d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85 \
  evidence/A/SOURCES/20261107/datasets | tar -x -C "$TMP/a-export"

cd ml

uv run --locked --python 3.12 --extra test python scripts/existing-data-recovery.py \
  --a-dataset-dir "$TMP/a-export/evidence/A/SOURCES/20261107/datasets" \
  --source-inventory reports/DataRecovery/source-inventory.json \
  --out "$TMP/DataRecovery-run1" \
  --repository-revision a9dacbe984b3287c7b7b0cdce8416552f66d3808

uv run --locked --python 3.12 --extra test python scripts/existing-data-recovery.py \
  --a-dataset-dir "$TMP/a-export/evidence/A/SOURCES/20261107/datasets" \
  --source-inventory reports/DataRecovery/source-inventory.json \
  --out "$TMP/DataRecovery-run2" \
  --repository-revision a9dacbe984b3287c7b7b0cdce8416552f66d3808

diff -r "$TMP/DataRecovery-run1" reports/DataRecovery
diff -r "$TMP/DataRecovery-run1" "$TMP/DataRecovery-run2"
```

Expected:

- each run reports
  `audit=COMPLETE descriptive=VERIFIED door=VERIFIED sensor=PARTIAL gate_b=RED/NOT_READY demo=READY artifacts=19`;
- 19 artifacts: 4 reports + 1 CSV + 12 SVG plots + 2 JSON manifests;
- both runs byte-identical;
- both runs byte-identical to the committed `ml/reports/DataRecovery/` package.

Do not substitute a different A export. Do not treat the descriptive CSV as a
predictive result.

## 9. Expected scientific absences

These are correct outcomes, not reproduction failures:

```text
FINAL_PREDICTIVE_RESULT_CSV = NOT_PRODUCED
FINAL_PHYSICAL_AB_RESULT_CSV = NOT_PRODUCED
REAL_EWT = NOT_ESTIMABLE
REAL_AIW = NOT_ESTIMABLE
W16_LOCKED_TEST = NOT_OPENED
W20_PHYSICAL_AB_ANALYSIS = NOT_RUN
FINAL_PHYSICAL_EFFECT = NOT_ESTABLISHED
FINAL_PHYSICAL_CI = NOT_COMPUTED
FINAL_PHYSICAL_P_VALUE = NOT_COMPUTED
```

Never replace a missing physical quantity with zero, a synthetic metric or a toy
fixture.

## 10. Determinism

Run the W23 audit and the DataRecovery regeneration in two independent
processes. Compare generated files byte-for-byte (`diff -r`). The generated
outputs contain no timestamps and no machine-specific absolute paths. The W24
handover JSON is deterministic: stable key ordering, no timestamps, no absolute
local paths.

## 11. Independent human replay

The W23 independent-team-member requirement remains open. A different human team
member should:

1. perform §3–§8 from a fresh checkout;
2. record the environment, commands, exit codes, test counts and diff outcomes;
3. fill [`independent-replay-receipt-template-W24.json`](independent-replay-receipt-template-W24.json);
4. return the receipt to Member B and the project leader.

Until a real receipt exists:

```text
INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING
```

An AI agent running twice is not an independent human reviewer. Do not invent a
name, signature, machine, timestamp or approval.

## 12. Prohibited actions

- No W15 refit, no new architecture, features, horizon, calibration or threshold.
- No locked-test opening; no W16 evaluation.
- No W20 physical outcome analysis; no physical A/B statistic.
- No firmware, actuator, broker or Controller B operation.
- No writes to `reports/W01…W23` or `reports/DataRecovery`.
- No Gate B/G3/G4/G5 promotion.
- No editing of A/C/D or team release records.
