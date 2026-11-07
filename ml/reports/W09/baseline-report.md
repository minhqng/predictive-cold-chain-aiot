# ColdGuard W09 — deterministic baseline and event evaluation

Report schema: `coldguard-w09-baseline-report-v1` · layer `coldguard-w09-deterministic-baselines-v1`

| Provenance | Value |
|---|---|
| Analysis code SHA-256 | `b1c6bef725d7a3be0dc1f1b798b53dff5f9d4fb1152e97f3c1b98b1d50d85fb7` |
| Repository revision | `638d8a3748865c224c4234d3325448ba7e20f453` |
| Generation command | `python scripts/baseline-evaluation-W09.py --source ../evidence/A/W09/exports/CG-S1-H8C-600S.json --a-run-index ../evidence/A/W09/s1-run-index.json --scenario S1 --out reports/W09 --a-w08-manifest reports/W08/gate-b-manifest-W08.json --sensitivity baselines/sensitivity-example-W09.json --repository-revision 638d8a3748865c224c4234d3325448ba7e20f453` |
| Source | `evidence/A/W09/exports/CG-S1-H8C-600S.json` |
| Source SHA-256 | `f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb` |
| A run index SHA-256 | `eb71d3f58004a25e60315b39ed88e33daa7e069a7a1fc3df391713cfce33b5af` |
| W08 manifest SHA-256 | `1dde8ea3d62b4cf7ba8a409108ab3f99b1170656880571c8fa6515af639babd6` |
| W09 parameters | `PARAMETERS_NOT_FROZEN` |
| W08 schema | `coldguard-w08-gate-b-readiness-manifest-v2` |

## 1. Software implementation verdict

```text
W09 SOFTWARE: GREEN (implementation produced the declared artifacts)
PHYSICAL BASELINE EVIDENCE: NOT_ESTABLISHED (no eligible S1 runs)
```

The software verdict is independent of the scientific verdict. The real A W09 capture is A-invalid, so no physical baseline performance is claimed.

## 2. B0 threshold behavior

**PARAMETERS_NOT_FROZEN** — no authoritative B0 replay was executed. The diagnostic trajectory below is an overlay, not a baseline result.

## 3. B1 hysteresis behavior

**PARAMETERS_NOT_FROZEN** — no authoritative B1 replay was executed.

D parity is verified at the pure comparator boundary in `tests/test_baselines.py`; the full D priority/SAFE_LOCAL/fault layer is not mirrored and is not claimed.

## 4. Persistence / dwell version status

No authoritative Controller A reactive persistence/dwell has been frozen. D's `PolicyConfig.persistence_required_s` is the predictive path and is not reused. The optional `B1_PERSISTENCE_CANDIDATE` mode is explicitly exploratory and is not Controller A.

## 5. Synthetic positive-control results

Synthetic controls are software fixtures only. They exercise the threshold, hysteresis, episode and matching logic; they never enter a physical dataset or a scientific denominator.

| Control | Expected branch | Label |
|---|---|---|
| stable no-event | no episode, no crossing | SYNTHETIC_CONTROL_ONLY |
| oscillation around threshold | multiple episodes, chatter diagnostic | SYNTHETIC_CONTROL_ONLY |
| isolated excursion | one episode | SYNTHETIC_CONTROL_ONLY |
| persistent excursion | one sustained episode | SYNTHETIC_CONTROL_ONLY |
| missing-data interruption | refused/unknown interval, censored match | SYNTHETIC_CONTROL_ONLY |
| irregular cadence | interval certainty, no invented instant | SYNTHETIC_CONTROL_ONLY |
| duplicate delivery | no extra crossing or episode | SYNTHETIC_CONTROL_ONLY |
| exact boundary | documented operator outcome | SYNTHETIC_CONTROL_ONLY |

The executable control suite is `tests/test_baselines.py` and `tests/test_event_evaluator.py`.

| Sensitivity run | Baseline | Crossings / transitions | Episodes | Matched | Missed |
|---|---|---|---|---|---|
| `SOFTWARE_ONLY_SENSITIVITY_NOT_EVIDENTIARY` | B0_THRESHOLD | 2 crossings | 2 | 2 | 0 |
| `SOFTWARE_ONLY_SENSITIVITY_NOT_EVIDENTIARY` | B1_HYSTERESIS | 3 ON/OFF | 2 | 2 | 0 |

## 6. Real physical diagnostic replay

- Source: `evidence/A/W09/exports/CG-S1-H8C-600S.json`
- Source SHA-256: `f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb`
- Rows: 957
- Time domain: `BOOT_SCOPED_UPTIME`; clock sync: `NOT_EVIDENCED`
- W05 admission status: `EXCLUDED_OR_BLOCKED`; QA execution: `COMPLETED`; channel quality: `ATTENTION_REQUIRED`
- Run identity: None; boot: '56044b74'; device: None
- Role-qualified chamber-air slots: t1, t3, t4
- Hot-side slots excluded from chamber air: t2
- Diagnostic overlay representation: `DIAGNOSTIC_MEAN_T1_T3_T4` (not a frozen baseline choice)

```text
PARAMETERS_NOT_FROZEN: True
authoritative replay executed: False
sensitivity replay executed: True
```

The device-reported applied state is overlaid separately. It is not an ACK, not an electrical actuation proof and not a thermal response measurement.

## 7. Scientifically eligible S1 evaluation

- W08 run eligibility: `BLOCKED`
- A ledger: `INVALID`
- Gate B physical: `RED`
- Predictive dataset: `NOT_READY`
- Split feasibility: `NOT_FEASIBLE`
- S1 eligibility: `BLOCKED`
- Reasons: ABSOLUTE_TIME_NOT_EVIDENCED, AUTHORITY_A_LEDGER_INVALID, CALIBRATION_UNVERIFIED, CAPTURE_DURATION_NOT_DECLARED, DEVICE_IDENTITY_MISSING, HARDWARE_CONFIG_NOT_VERIFIED, RUN_IDENTITY_UNRESOLVED, RUN_MANIFEST_LINKAGE_NOT_PROVIDED, SCENARIO_VALIDITY_NOT_GRANTED, TIMING_INTEGRITY_FAILED, W08_PHYSICAL_GATE_NOT_GREEN, W08_PHYSICAL_GATE_RED

```text
real S1 false-warning rate = NOT_ESTIMABLE
real S1 stability claim = NOT_ESTABLISHED
real normal-run performance = NOT_ESTIMABLE
```

The 957 measured rows are not 957 independent exposure units. A zero event count on an A-invalid capture is not a zero false-warning rate.

## 8. Event matching and metric denominators

| Label | Baseline | Eligible runs | Event denominator | Matched episodes | Unmatched episodes | Missed events | Precision | Recall |
|---|---|---|---|---|---|---|---|---|
| `SOFTWARE_ONLY_SENSITIVITY_NOT_EVIDENTIARY` | B0_THRESHOLD | 0 | 2 | 2 | 0 | 0 | 1.000000 | 1.000000 |
| `SOFTWARE_ONLY_SENSITIVITY_NOT_EVIDENTIARY` | B1_HYSTERESIS | 0 | 2 | 2 | 0 | 0 | 1.000000 | 1.000000 |

Zero denominators stay undefined. Unmatched episodes are false warning burden only when the run is eligible and fully observed. Matching is a retrospective offline annotation; it is not an online causal warning stream. W09 contains no predictive action stream, so non-intervention is an explicit assumption rather than a measured closed-loop result. Sensitivity precision/recall rows are software-only demonstrations and are not scientific metrics.

## 9. Frozen versus provisional parameters

| W08 completeness dimension | Status | Value | Freeze evidence |
|---|---|---|---|
| `WHOLE_CAPTURE_COMPLETENESS` | PROPOSED | 0.950000 | NOT_RECORDED |
| `CRITICAL_CHANNEL_COMPLETENESS` | PROPOSED | 0.990000 | NOT_RECORDED |
| `PRIMARY_EVENT_WINDOW_COMPLETENESS` | PROPOSED | 0.990000 | NOT_RECORDED |
| `PRE_EVENT_BASELINE_COMPLETENESS` | PROPOSED | 0.950000 | NOT_RECORDED |
| `POST_EVENT_OR_RECOVERY_COMPLETENESS` | PROPOSED | 0.900000 | NOT_RECORDED |
| `TIMING_ALIGNMENT_COMPLETENESS` | UNRESOLVED | NOT_ESTIMABLE | NOT_RECORDED |

W09 authoritative parameters: `PARAMETERS_NOT_FROZEN`.
W09 sensitivity parameters: `SYNTHETIC_ILLUSTRATIVE`.
No W09 threshold, representative temperature, persistence/dwell or association window has been frozen for physical evidence.

## 10. A / C / D owner dependencies

- Member A owns physical sensor calibration, run identity, the validity ledger and measured thermal/electrical evidence.
- Member C owns transport, backend timestamps and command evidence.
- Member D owns the real Controller A policy, safety priority, SAFE_LOCAL and device modes. W09 only mirrors the pure hysteresis comparator for offline analysis.
- The project lead and the named review authority own any threshold freeze decision.

## 11. W10 / W11 / W12 handoff limitations

- W09 does not build W10 features or a causal temporal pipeline.
- W09 does not train or tune XGBoost or implement W11 comparisons.
- W09 does not open or freeze the locked test or implement W12 conclusions.
- W09 produces no real EWT because there is no predictive warning stream; EWT compatibility is tested only on synthetic controls.
- W09 produces no AIW because no command/ACK/electrical/thermal latency chain was measured.

## 12. Limitations

- A baseline criterion detection is not an actuator command.
- The real A W09 capture is A-invalid; no physical baseline performance is established.
- The 957 rows are not independent exposure units.
- No real EWT is computed from a threshold baseline alone.
- No AIW is estimated without measured latency components.
- The locked test is not opened, inspected or frozen.
