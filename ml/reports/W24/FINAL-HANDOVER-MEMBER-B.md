# FINAL HANDOVER — MEMBER B (ColdGuard W24)

> **Single entry point for Member B's AI/data contribution.** Start here, then
> follow the links. This document is written for a teammate who has not read the
> previous 23 weeks.
>
> **Verified parent revision:** `c0d8b247291c05cce308feae25b3fedd329af494`
> (PR #114 head). **Package:** `ml/reports/W24/`.
> **Date of preparation:** 2026-11-11.

```text
MEMBER_B_SOFTWARE_HANDOVER = READY
FINAL_PREDICTIVE_SCIENTIFIC_ACCEPTANCE = INCOMPLETE
```

Read this first: the software package is complete and reproducible. The
**scientific** predictive result is not available, because its physical
prerequisites do not exist. These are two different completion states.

## 0. Five-minute path

1. Read §14 for the two completion states.
2. Read §13 for the ten required deliverables and where each one is.
3. Run [`reproduction-runbook-W24.md`](reproduction-runbook-W24.md) if you want
   to verify the package.
4. Read [`scientific-gaps-and-owners-W24.md`](scientific-gaps-and-owners-W24.md)
   before promising any predictive or A/B result.

## 1. What Member B was responsible for

Member B owned the AI/data workstream: data contracts and dictionaries, synthetic
data generation, label/window generation, leakage-safe grouped splitting, causal
feature engineering, model benchmarking and evaluation, model artifacts and
cards, calibration assessment, locked-test readiness, offline shadow parity,
runtime monitoring, paired-campaign integrity, statistical computation, evidence
packaging, reproducibility, and the bounded analysis of existing physical data.

Member B did **not** own: hardware, firmware, sensors, broker deployment, backend
integration, Controller B physical authorization, team release approval, or the
final physical A/B campaign.

## 2. What was implemented during W01–W23

All items below are implemented in `ml/` with reports, manifests and tests:

- Data dictionary and research mapping.
- Synthetic dataset generation and fixture identity.
- Time-window and label generation.
- Leakage-safe grouped splitting (`run_id + pair_id`).
- Statistical analysis plan.
- Physical data QA and schema intake.
- Timing/event alignment.
- Physical exploratory data analysis.
- Dataset readiness verification.
- Deterministic baseline evaluation.
- Causal feature generation.
- XGBoost grouped benchmark.
- Model evaluation and ablation tools.
- Calibration assessment (risk score only).
- Model artifact and model cards.
- Locked-test readiness checks (fail-closed refusal).
- Offline shadow parity.
- Runtime monitoring.
- Paired campaign integrity controls.
- Final analysis authorization gate.
- Diagnosis/resilience evidence assessment.
- Paired statistical computation engine.
- Evidence package and clean-room replay.
- Existing physical-data analysis and 12 real figures.

The layer-by-layer index with hashes is in
[`artifact-integrity-W24.md`](artifact-integrity-W24.md) and
[`artifact-checksums-W24.json`](artifact-checksums-W24.json).

## 3. What the Data Recovery package added

PR #114 added a bounded analysis of the existing A 20261107 physical export:

| Quantity | Value |
|---|---:|
| Exported rows/segments | 18 |
| Physical frames | 9 293 |
| Distinct boots | 8 |
| A-accepted S1 windows | 4 |
| A-accepted S2 windows | 5 |
| Real physical SVG plots | 12 |
| Predictive-eligible independent runs | **0** |

What it shows (real, descriptive):

- S1 passive baselines: mean temperature 29.4624–29.8589 °C; trial2 changes
  0.0417 °C over about 10 minutes.
- Five S2 windows (4 `S2_DOOR` + 1 `S2_TIMING`), each with recorded door
  transitions; frame-based duration 12.9–14.1 s; chamber-temperature change is
  very small (e.g. W10-03-run1: 0.0038 °C).
- H8-C 600 s: chamber air −8.7083 °C; T2 hot side +9.6870 °C.
- H8-E 1800 s: TEC 100%, T2 +7.7500 °C, chamber air only 0.1037 °C.
- W07 500‰: chamber air −2.2500 °C; T2 +3.6875 °C over about 180 frames.

What it does **not** show: predictive accuracy, EWT, AIW or A/B benefit. The 18
segments are not 18 independent experiments; the five S2 windows share one
physical session.

## 4. Which files are required to run the software?

| Purpose | Entry point |
|---|---|
| Environment and tests | `ml/pyproject.toml`, `ml/uv.lock` |
| Feature registry | `ml/feature-registry-v1.yaml` |
| Model configuration | `ml/xgb-v1-config.yaml` |
| Physical QA | `ml/scripts/real-data-qa-v1.py` |
| EDA | `ml/scripts/plant-eda-W07.py` |
| Timing | `ml/scripts/event-alignment-W06.py` |
| Baselines | `ml/scripts/baseline-evaluation-W09.py` |
| Features | `ml/scripts/feature-pipeline-W10.py` |
| Benchmark | `ml/scripts/xgb-benchmark-W11.py` |
| Horizon | `ml/scripts/horizon-study-W13.py` |
| Model artifact | `ml/reports/W15/model/model.ubj` |
| Locked-test gate | `ml/scripts/w16-preflight-W16.py` |
| Shadow parity | `ml/scripts/w17-shadow-replay-W17.py` |
| Runtime audit | `ml/scripts/w18-runtime-audit-W18.py` |
| Campaign audit | `ml/scripts/w19-campaign-audit-W19.py` |
| Analysis gate | `ml/scripts/w20-campaign-preflight-W20.py` |
| Resilience | `ml/scripts/w21-resilience-audit-W21.py` |
| Statistics | `ml/scripts/w22-statistics-contract-W22.py` |
| Evidence audit | `ml/scripts/w23-evidence-audit-W23.py` |
| Physical recovery | `ml/scripts/existing-data-recovery.py` |

No broker, hardware, firmware or Controller B access is required.

## 5. Where are the model and its documentation?

| Item | Path |
|---|---|
| Native artifact | `ml/reports/W15/model/model.ubj` (SHA-256 `25a8ef7a…63f7f`) |
| Secondary JSON | `ml/reports/W15/model/model.json` |
| Model manifest | `ml/reports/W15/model/model-manifest-W15.json` |
| W15 model card | `ml/reports/W15/model-card-W15.md` |
| W23 model card | `ml/reports/W23/model-card-W23.md` |
| Inspection diagnostic | `ml/reports/W15/A3-model-inspection-W15.json` |

The model is `SYNTHETIC_SOFTWARE_CONTROL_ONLY`, `NON_DEPLOYABLE_CANDIDATE`,
`RISK_SCORE_ONLY`. It is not approved for physical Controller B.

## 6. Where are the real physical data results?

| Item | Path |
|---|---|
| Manifest with source pins and plot hashes | `ml/reports/DataRecovery/recovery-manifest.json` |
| Source inventory | `ml/reports/DataRecovery/source-inventory.json` |
| Descriptive table | `ml/reports/DataRecovery/real-observation-summary.csv` |
| Assessment | `ml/reports/DataRecovery/physical-data-assessment.md` |
| Eligibility review | `ml/reports/DataRecovery/predictive-eligibility-review.md` |
| Gate B reassessment | `ml/reports/DataRecovery/gate-b-reassessment.md` |
| Vietnamese summary | `ml/reports/DataRecovery/presentation-summary-vi.md` |

These are `PHYSICAL_RECORDED_DATA`, descriptive only. They are not a predictive
result table and not a physical A/B outcome table.

## 7. Where are the figures?

- W05–W23 figure index: `ml/reports/W23/figure-availability-W23.md`.
- W05: `ml/reports/W05/physical-state-W05.svg`.
- W07: `ml/reports/W07/phase-trajectories-W07.svg`.
- W09: `ml/reports/W09/baseline-comparison-W09.svg`.
- W10: `ml/reports/W10/feature-audit-W10.svg`, `real-diagnostic-W10.svg`.
- W22 TEST_ONLY: `ml/reports/W22/test-only-pair-plot-W22.svg`.
- **12 real physical plots:** `ml/reports/DataRecovery/real-physical-plots/`.

Final physical predictive/A/B figures are withheld; no decorative substitute was
created.

## 8. Which tests have been run?

W24 executed the locked environment from `ml/`:

```text
uv lock --check                                  PASS (lock unchanged)
uv sync --locked --python 3.12 --extra test      PASS (21 packages)
uv run --locked --python 3.12 --extra test pytest -q   1900 passed, 4 skipped, 0 failed (336.29 s)
uv build                                         PASS (wheel + sdist)
```

W24 also executed, twice each:

- W23 evidence audit: 88 verified / 9 unavailable / 0 violations, byte-identical.
- DataRecovery regeneration: 19 artifacts, byte-identical to the committed package.
- W16–W22 replays: byte-identical across two passes; W16 differs only in
  `repository_revision`.

Exact counts, skips and build outputs: [`reproduction-result-W24.md`](reproduction-result-W24.md).
A skipped optional-source test is never counted as a pass.

## 9. How can another member reproduce the results?

Follow [`reproduction-runbook-W24.md`](reproduction-runbook-W24.md). It covers
fresh checkout, locked environment, W15 hash, W16–W22 replays, W23 audit,
real-physical regeneration from the pinned A export, determinism checks and the
independent receipt template. No undocumented local file is required.

## 10. What is scientifically verified?

- The software chain builds, imports and passes its tests in the locked environment.
- The W15 model bytes match the declared SHA-256.
- The W16 gate refuses to open the locked test (`holdout_opened = false`).
- The W20 gate keeps the final analysis locked (`NOT_RUN`).
- The W22 engine computes the prescribed statistics on toy fixtures.
- The W23 package verifies 88 local sources and 9 unavailable, 0 violations.
- The real physical descriptive package reproduces byte-for-byte.
- All 12 real physical plots exist and match their declared hashes.
- T2 is never treated as chamber air.

## 11. What remains incomplete?

- No accepted predictive physical development runs.
- No frozen primary critical target or horizon.
- No approved real predictive model; W15 is synthetic and non-deployable.
- No W16 locked-test performance result.
- No real EWT or AIW.
- No physical Controller B authorization.
- No accepted final A/B campaign.
- No final physical effect, 95% CI or p-value.
- No G4/G5 approval.
- No independent human replay and no team rehearsal.

## 12. Who owns the next action?

| Action | Owner |
|---|---|
| Physical run identity, clock sync, calibration, device identity, accepted runs | A |
| Telemetry time provenance, shadow trace, Controller B lifecycle, broker resilience | C |
| Target, threshold, persistence, safety and A/B policy | D |
| Freeze approvals, release authorization, team rehearsal, final acceptance | Leader |
| B-side support, defect fixes, reproduction answers | Member B |
| Independent replay receipt | Any different team member |

Full ledger: [`scientific-gaps-and-owners-W24.md`](scientific-gaps-and-owners-W24.md).

## 13. Mandatory ten-item handover inventory

| # | Item | Primary path | Class | Disposition |
|---|---|---|---|---|
| 1 | Dataset card | `ml/reports/W23/dataset-card-W23.md` | SOFTWARE_EVIDENCE_PACKAGE | AVAILABLE_WITH_LIMITATIONS |
| 2 | Split manifest | `ml/reports/W11/cv-fold-manifest.yaml` | SYNTHETIC_SOFTWARE_CONTROL_ONLY | AVAILABLE_WITH_LIMITATIONS |
| 3 | Feature registry | `ml/feature-registry-v1.yaml` | SOFTWARE_CONTRACT | COMPLETE_AND_VERIFIED |
| 4 | Model card | `ml/reports/W15/model-card-W15.md`, `ml/reports/W23/model-card-W23.md` | SYNTHETIC_SOFTWARE_CONTROL_ONLY | AVAILABLE_WITH_LIMITATIONS |
| 5 | Model artifact | `ml/reports/W15/model/model.ubj` | SYNTHETIC_SOFTWARE_CONTROL_ONLY | AVAILABLE_WITH_LIMITATIONS |
| 6 | Locked-test report | `ml/reports/W16/locked-test-result.md` (refusal) | SOFTWARE_VERIFICATION | AVAILABLE_WITH_LIMITATIONS |
| 7 | A/B statistics | `ml/reports/W22/w22-manifest.json` | SOFTWARE_VERIFICATION | AVAILABLE_WITH_LIMITATIONS |
| 8 | Analysis scripts | `ml/scripts/` (indexed in the handover manifest) | SOFTWARE_VERIFICATION | COMPLETE_AND_VERIFIED |
| 9 | Figures | `ml/reports/W23/figure-availability-W23.md` + 12 DataRecovery SVGs | MIXED | AVAILABLE_WITH_LIMITATIONS |
| 10 | Limitations | `ml/reports/W24/scientific-gaps-and-owners-W24.md` | SOFTWARE_EVIDENCE_PACKAGE | COMPLETE_AND_VERIFIED |

Machine-readable version with SHA-256, purpose, reproduction and limitations for
every item: [`handover-manifest-W24.json`](handover-manifest-W24.json).

## 14. Two completion states (do not conflate)

```text
MEMBER_B_SOFTWARE_HANDOVER = READY
FINAL_PREDICTIVE_SCIENTIFIC_ACCEPTANCE = INCOMPLETE
```

- **Software handover READY** means: code, artifacts, tests, manifests, figures,
  reproduction instructions and limitations are delivered and hash-verified.
- **Scientific acceptance INCOMPLETE** means: the real predictive model, locked
  test, EWT/AIW, physical A/B effect/CI/p and G4/G5 do not exist.

Software readiness never promotes a scientific gate.

## 15. Scientific limitations

The current absence of the following is structural, not a packaging defect:

- accepted predictive physical development runs;
- frozen primary critical target and horizon;
- an approved real predictive model;
- a W16 locked-test performance result;
- real EWT and AIW;
- physical Controller B authorization;
- an accepted final A/B campaign;
- final physical effect, CI and p-value;
- G4/G5 approval.

Requirements depend on A (physical evidence), C (telemetry/shadow/control),
D (policy/threshold/safety) and the leader (approvals/release).

Additional limitations:

- 18 segments are not 18 independent experiments; independence is bounded by 8 boots.
- The five S2 windows share one physical session.
- The W15 model uses only `time_since_open` for all splits — a synthetic shortcut.
- Hash verification proves byte identity, not scientific validity.
- No human has independently replayed the procedure yet.

## 16. Handover readiness matrix

Every artifact has exactly one disposition.

| Artifact | Disposition |
|---|---|
| Member B W01–W24 software package | COMPLETE_AND_VERIFIED |
| Dataset card | AVAILABLE_WITH_LIMITATIONS |
| Split manifest | AVAILABLE_WITH_LIMITATIONS |
| Feature registry | COMPLETE_AND_VERIFIED |
| Model card | AVAILABLE_WITH_LIMITATIONS |
| Model artifact | AVAILABLE_WITH_LIMITATIONS |
| Locked-test report (refusal) | AVAILABLE_WITH_LIMITATIONS |
| A/B statistics engine | AVAILABLE_WITH_LIMITATIONS |
| Analysis scripts | COMPLETE_AND_VERIFIED |
| Figures | AVAILABLE_WITH_LIMITATIONS |
| Limitations | COMPLETE_AND_VERIFIED |
| Final predictive result CSV | NOT_PRODUCED |
| Final physical A/B result CSV | NOT_PRODUCED |
| Real EWT/AIW | NOT_PRODUCED |
| Independent human replay | BLOCKED_BY_EXTERNAL_EVIDENCE |
| Team rehearsal | BLOCKED_BY_EXTERNAL_EVIDENCE |
| Gate B / G3 / G4 / G5 | BLOCKED_BY_EXTERNAL_EVIDENCE |
| Hardware acceptance | REQUIRES_TEAM_REVIEW |
| Backend deployment | REQUIRES_TEAM_REVIEW |
| Firmware release build | REQUIRES_TEAM_REVIEW |
| Controller B physical authorization | REQUIRES_TEAM_REVIEW |
| Final project release | REQUIRES_TEAM_REVIEW |

## 17. Final claim-to-evidence audit

| Claim | Evidence | Class | Allowed conclusion | Forbidden conclusion |
|---|---|---|---|---|
| The system recorded real door disturbances | DataRecovery source inventory and plots | PHYSICAL_RECORDED_DATA | Door-state and thermal observations were recorded | The AI predicts future thermal failures accurately |
| The project has an XGBoost model | W15 artifact and model card | SYNTHETIC_SOFTWARE_CONTROL_ONLY | The training/inference pipeline exists | The model is approved for physical Controller B |
| The project has paired statistical methods | W22 engine and tests | SOFTWARE_VERIFICATION | Prescribed calculations can run on admitted paired data | Controller B demonstrated a physical benefit |
| The physical package is reproducible | W24 two-process replay | SOFTWARE_VERIFICATION | Anyone with the pinned export can regenerate it | The physical results are a predictive benchmark |
| W16 is complete | W16 refusal report | SOFTWARE_VERIFICATION | The gate correctly refuses to open the test | A locked predictive evaluation was completed |
| 12 real plots exist | recovery-manifest plot hashes | PHYSICAL_RECORDED_DATA | Descriptive figures are available | These plots are AI forecasting results |

Rule: no presentation claim may exceed its evidence class.

## 18. W23 inventory reconciliation

The delivered W23 manifest has **97 sources (88 local, 9 unavailable)**. The W23
receipt records **83 verified**, an earlier 92-source revision. Five local
manifests (W05, W07, W08, W09, W10) were added before delivery. W24 records the
delivered revision and the re-audit result (88/9/0) without rewriting the W23
record. See [`artifact-integrity-W24.md`](artifact-integrity-W24.md) §8.

## 19. Independent review status

- Fresh-context code/evidence review: performed during W24; findings and repairs
  are summarized in the W24 delivery report.
- Independent **human** replay: `PENDING`.
- Team rehearsal: `PENDING`.
- No fake reviewer identity, signature or approval is recorded.

## 20. Final handover decision

1. **Is Member B's W01–W24 software contribution ready to hand to the team?**
   Yes — `MEMBER_B_SOFTWARE_HANDOVER = READY`.
2. **Can another member locate and reproduce the available results?**
   Yes — this document is the entry point, and the runbook is self-contained.
3. **What exact scientific evidence remains missing?**
   Accepted physical runs, frozen target/horizon, W16 result, EWT, AIW,
   Controller B authorization, physical A/B campaign, final effect/CI/p, G4/G5.
4. **Does any incomplete item block software handover?**
   No. The missing items block **scientific acceptance**, not the software package.
5. **What must the leader do next?**
   Assign the gap owners, verify A/B/C/D evidence, issue freeze/release approvals,
   schedule an independent replay and team rehearsal, and only then consider
   W16/W20 and final release.

## 21. Forwardable summary for the project leader

> Member B W24 is delivered: the AI/data software package W01–W24 is complete,
> hash-verified and reproducible, and the existing physical data has a bounded
> descriptive analysis with 12 verified plots. The software handover is READY.
> The final predictive scientific acceptance is INCOMPLETE: Gate B is RED, the
> W16 locked test was not opened, the W20 physical A/B analysis was not run, and
> real EWT/AIW/effect/CI/p do not exist because physical prerequisites are owned
> by A/C/D and the leader. No gate was promoted and no result was fabricated.
> Next actions: close the physical evidence gaps, issue approvals, perform an
> independent human replay, and then authorize W16/W20.

## 22. Git delivery

| Field | Value |
|---|---|
| Branch | `feat/b-w24-final-handover` |
| Parent / expected PR base | `feat/b-existing-physical-data-recovery` (PR #114 head `c0d8b24`) |
| Commit subject | `docs(ml): complete Member B W24 final AI data handover` |
| Changed paths | `ml/reports/W24/` and `ml/tests/test_w24_handover.py` only |
| Prior branches / PRs | PR #112 and PR #114 are not modified, retargeted or merged |
| Release actions | no tag, no merge, no force-push; team release belongs to the leader |

The PR URL and CI status are recorded in the PR itself and in the W24 delivery
report. If the PR head is used for replay, replace `<W24_DELIVERY_COMMIT>` in the
runbook with the PR head SHA; `c0d8b24` remains the generation parent.
