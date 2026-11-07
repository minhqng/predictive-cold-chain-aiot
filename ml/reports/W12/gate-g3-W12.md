# Gate G3 evidence and decision (W12)

**Aggregate decision: `NO-GO / FIX DATA`**

This is Member B's evidence-based input, not a team approval.

## Evidence matrix

| Requirement | Owner | Required evidence | Actual source | Observed result | Quality | Status | Blocking reason | Next evidence | Review authority |
|---|---|---|---|---|---|---|---|---|---|
| `G3-A-PHYSICAL-PLANT` | Member A | hardware configuration/calibration, repeatability, valid S1/S2 runs, electrical qualification and response timing when claimed | evidence/A/W24/acceptance-census.json; evidence/A/W18/pre-run-safety-checklist.json; reports/W08/gate-b-manifest-W08.json | physical_acceptance_status=BLOCKED_ON_HARDWARE_GATES; hardware_posture=DE_ENERGIZED_SAFE_POSTURE_PSU_OFF_FUSE_REMOVED; open_hardware_gates=10; W08 Gate B=RED; eligible real runs=0 | AUTHORITATIVE_A_EVIDENCE + B_GATE_MANIFEST | `BLOCKED_BY_MISSING_EVIDENCE` | A physical acceptance is blocked on hardware gates; W08 physical data gate is RED with 1 candidate run(s); 0 eligible | A-valid physical plant and run evidence: resolved run/device identity, verified hardware/calibration/clock, enough independent S1 and valid S2 runs, and a GREEN Gate B decision | Project lead + Member A (physical evidence) |
| `G3-B-GROUPED-DATASET` | Member B | W08 Gate B, independently valid grouped runs, frozen label protocol, grouped split and leakage audit | reports/W08/gate-b-manifest-W08.json; reports/W10/feature-manifest-W10.json; reports/W11/benchmark-manifest-W11.json | W08 Gate B=RED; predictive dataset=NOT_READY; split=RED; eligible S1=0; eligible S2=0; real development=NOT_FEASIBLE | B_GATE_MANIFEST + REAL_A_ADMISSION | `FAIL_VERIFIED` | no eligible real independent predictive development runs; only deterministic synthetic software-control data exists | a GREEN Gate B and a real grouped development dataset with independent run groups, frozen labels and a locked test | Project lead + Member B; A for physical validity |
| `G3-B-XGB-BENCHMARK` | Member B | grouped XGBoost evaluation with baselines, leakage audit, event-level metrics and a real development population | reports/W11/benchmark-manifest-W11.json; reports/W12/benchmark-synthesis-W12.md; reports/W12/grouped-metrics-W12.csv | synthetic grouped benchmark only: 8 pair groups, 4 folds; mean sample AP by method: B0_THRESHOLD=0.9885, B1_HYSTERESIS=0.6911, XGBOOST_V1_TRAIN_FOLD_CLASS_WEIGHT=1.0000, XGBOOST_V1_UNWEIGHTED=1.0000; no real benchmark | SYNTHETIC_SOFTWARE_CONTROL_ONLY | `BLOCKED_BY_MISSING_EVIDENCE` | synthetic AP cannot establish a physical predictive benchmark; the real benchmark is NOT_ESTABLISHED | real grouped development data and a leakage-safe real XGBoost benchmark with event-level operational metrics | Project lead + Member B |
| `G3-D-CONTROLLER-A` | Member D | committed Controller A policy, thresholds/hysteresis, TTL, idempotency, ACK behavior, applied-state verification and physical electrical/thermal verification | evidence/D/W01–W03 contracts only; no committed D-W12 evidence | no committed Controller A stability or physical verification evidence on the W12 parent; open D PRs are not merged | DESIGN_CONTRACTS_ONLY | `NOT_VERIFIED` | D W12 evidence is absent from the reviewed parent stack | D-committed Controller A stability and physical verification evidence with hash/revision provenance | Project lead + Member D |
| `G3-D-COMMAND-VERIFY` | Member D | command TTL/idempotency, ACK behavior, applied-state verification, electrical response and thermal response evidence | no committed D W12 command-verification evidence | A dry-run status=SOFTWARE_READY, dry_runs=0; A enablement=BLOCKED_ON_PREREQUISITES; final-freeze schema requires 3 open evidence items | A_PRE_ENERGIZATION_CHECKLIST_ONLY | `NOT_VERIFIED` | no physical command→ACK→electrical→thermal verification chain is committed; software policy tests are not physical actuation | D-committed command verification and A-verified electrical/thermal response on the real plant | Project lead + Member D + Member A |
| `G3-C-PLATFORM-BACKUP` | Member C | raw export reproducibility, backup/restore, data lineage, duplicate/replay handling and a platform release signoff | no committed C backup/export evidence | no committed C signoff or operational backup/restore evidence | MISSING | `NOT_VERIFIED` | C platform evidence is absent; software tests do not prove backup | C-committed export/backup/restore and lineage evidence with a platform release signoff | Project lead + Member C |
| `G3-B-EWT-AIW` | Member B | eligible non-intervened physical trajectory with frozen warning/reactive definitions and measured latency chain | reports/W12/ewt-assessment-W12.csv | REAL_EWT=NOT_ESTIMABLE; REAL_AIW=NOT_ESTIMABLE | SOURCE_AUTHORIZED_REFUSAL | `BLOCKED_BY_MISSING_EVIDENCE` | no eligible physical non-intervened event population and no measured system/physical latency chain | a valid non-intervened physical event with frozen timing definitions and a complete measured latency chain | Project lead + Member B; A for timing evidence |
| `G3-B-LEAKAGE` | Member B | leakage audit, grouped split and locked-test discipline | reports/W11/leakage-audit-W11.md | W11 leakage probes all PASS on the synthetic grouped fixture | SOFTWARE_VERIFICATION | `PASS_VERIFIED` | none | none for the synthetic scope; repeat on real data | Project lead + Member B |
| `G3-TEAM-APPROVAL` | Project lead | explicit A/B/C/D review and maintainer authorization | no approval record committed | approval pending; no signatures or dates are invented | MISSING | `NOT_VERIFIED` | team approval is absent | explicit dependency-ordered review and approval by the project lead and A/C/D owners | Project lead |

## Decision precedence

- Hard blockers: `G3-A-PHYSICAL-PLANT`, `G3-B-GROUPED-DATASET`, `G3-B-XGB-BENCHMARK`, `G3-D-CONTROLLER-A`, `G3-D-COMMAND-VERIFY`, `G3-C-PLATFORM-BACKUP`, `G3-TEAM-APPROVAL`
- W12 software: `GREEN`
- Physical: `Gate B RED`
- A hard physical/data failure is not overridden by synthetic ML metrics.
- `GO WITH LIMITATIONS` is not available while the physical dataset gate is RED.

## Rationale

- A hard physical/data prerequisite is not PASS_VERIFIED; synthetic software metrics cannot override it.
- W12 software status is GREEN, but the physical dataset and grouped real benchmark remain invalid.
- GO WITH LIMITATIONS is not available while the physical dataset gate is RED.

## Permitted / forbidden

Permitted:

- offline engineering work, tests and contract refinement
- synthetic software-control experiments clearly labeled as such

Forbidden:

- predictive physical deployment or Controller B actuation
- treating synthetic AP as physical predictive evidence
- unilateral A/C/D signoff

## Human authority

- Member B recommendation only; team-lead approval pending

## Limitations

- The W12 report is Member B's evidence input, not a team approval.
- A/C/D evidence not committed to the reviewed parent stays NOT_VERIFIED.
- A missing C signoff is not evidence of a working backup.
- A D software policy test is not verified physical actuation.
