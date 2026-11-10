# W14 EWT / AIW evidence report

**Task:** B-W14-05 · **Layer:** `coldguard-w14-role-correct-ablation-v1`
**Verdicts: `EWT = NOT_ESTIMABLE`; `AIW = NOT_ESTIMABLE`.**
**Scientific class: `BLOCKED_BY_MISSING_EVIDENCE`.**
No numeric EWT or AIW distribution is fabricated.

## 1. Canonical definitions

```text
EWT = t_reactive - t_predictive
AIW = t_critical - t_warning - T_system - T_physical
```

EWT requires an admissible non-predictively-intervened trajectory with a
trusted first persistent predictive warning and an observed reactive crossing in
one trusted event-time domain. AIW requires trusted critical and warning
anchors, a measured system-latency chain and a measured physical-response
chain on coherent clocks. A Controller B intervention destroys the
counterfactual reactive crossing; no fake EWT is computed inside it.

## 2. Evidence inventory

| Fact | Status | Exact source |
|---|---|---|
| Predictive-eligible real runs | **0** | `ml/reports/W13/horizon-manifest-W13.json` (`reconciliation.predictive_eligible_runs = 0`) |
| Accepted S1 windows | 4 (passive thermal/electrical-idle; not cooling/energy) | W13 reconciliation; A-W09-02 |
| Accepted S2 windows | 5 (door + timing) | W13 reconciliation; A-W10-03 |
| Exported rows / segments | 18 rows over **8 distinct boots** | W13 reconciliation |
| Frames | 9293 | W13 reconciliation |
| Device wall clock / absolute UTC | **Absent** (`DEVICE_HAS_NO_WALL_CLOCK`) | W06 timing audit; W13 refusal reasons |
| Clock synchronization | **Not evidenced** | W13 refusal reasons |
| Run identity | **Unresolved** for the `CG-RUN` pattern | W09/W13 |
| Calibration traceability | **Absent** (`calibration_id = UNRECORDED`) | A-W24 registry; W13 |
| Critical criterion / representative T | **Not frozen** | D threshold pending; A-W10-05 / A-W13-03 INCOMPLETE |
| Gate G3 | **NO-GO / FIX DATA** | `ml/reports/W12/gate-g3-W12.md` |
| PR #95 | `OPEN_UNMERGED`, `NOT_VERIFIED_FOR_CANONICAL_USE` | live PR state; W13 `pr95_supplement` |
| PR #95 trial content | passive S1 trial, capture PASS, `actuation = NONE`, `commands_sent = 0` | W13 supplement |
| A command→electrical | 1.094 s, n = 1, console START-accept anchor, ±1 s poll quantization | `evidence/A/W13/plant-timing-report.json` |
| A command→thermal | 51.0 s for 1.0 °C, applied-on anchor, one boot (`56044b74`) | same report |
| A command→ACK | `NOT_ESTIMABLE`; no command-publication anchor | W06 `timing-audit-W06.md` |
| Backend/network command path | **Absent** (`GAP-NETWORK-COMMAND-LATENCY`) | W13 / D-W13 readiness |
| C command-lifecycle / timing evidence | **Absent** from the reviewed tree | `evidence/C/` not committed |
| Physical verification of actuation | `physical_verified = false` | W13 plant timing |

Source pins: W13 manifest SHA-256
`02a76660319f6118900ec54ee3d50fa96968ad14b0a7110f3fdaf1b62417a404`;
W12 EWT assessment SHA-256
`97ce1c40d97642fc0d5f3d546d529ea8deb2b4b508911c18889890018cdfbefa`
(`ml/reports/W12/ewt-assessment-W12.csv`).

## 3. EWT — why not estimable

The canonical interface (`evaluation_contract.compute_ewt`) refuses rather than
invents an anchor. Each distinct reason applies to the current evidence:

1. `EVENT_UTC_UNAVAILABLE_DEVICE_HAS_NO_WALL_CLOCK` — no absolute event time.
2. `HOST_RECEIPT_TIME_IS_NOT_PHYSICAL_EVENT_TIME` — host receipt cannot replace
   device event time.
3. `CLOCK_SYNC_NOT_EVIDENCED_IN_PACKAGE` — no evidence the relevant clocks share
   a domain.
4. `RUN_IDENTITY_UNRESOLVED_FOR_CG_RUN_PATTERN` — one boot carries multiple
   source run ids; segments cannot be counted as independent runs.
5. `CALIBRATION_TRACEABILITY_ABSENT_FROM_PACKAGE_SCHEMA` — warning/reactive
   findings cannot be trusted without calibration provenance.
6. `SEGMENTS_SHARE_BOOTS_ROWS_ARE_NOT_INDEPENDENT_RUNS` — 18 segments span 8
   boots.
7. `CRITICAL_CRITERION_AND_REPRESENTATIVE_T_NOT_FROZEN` — no authoritative
   reactive criterion.

Consequences for the EWT categories:

| Category | Status |
|---|---|
| Earlier warning | not estimable |
| Late warning | not estimable |
| No valid warning | not estimable |
| Incomplete trajectory | not estimable (the population itself is inadmissible) |
| Unavailable critical-event semantics | present (critical definition unfrozen) |

The synthetic EWT cases in W12/W13 (20 s, −10 s, 0 s, 20 s) are **contract
tests**, not physical evidence. A Controller B trajectory is not converted into
a counterfactual no-control trajectory.

## 4. AIW — why not estimable

| AIW component | Required evidence | Actual status |
|---|---|---|
| `t_critical` | frozen critical definition and trusted critical event | **Absent**: critical Tmean/representative temperature unfrozen (D) |
| `t_warning` | admissible warning stream in the same trusted timeline | **Absent**: no eligible non-intervened real trajectory |
| `T_system` | sensing + inference + policy + command publish + device receive, measured end to end | **Absent**: no network command path; console path is not a backend distribution |
| `T_physical` | measured command→electrical→thermal response chain | **Partial**: 1.094 s console command→electrical (n=1); 51.0 s applied-on→thermal (single observation); no command-anchored end-to-end chain |

The frozen `compute_aiw` interface returns `NOT_ESTIMABLE` with `aiw_s = None`
when any component is unmeasured, an empty chain is supplied, or clock domains
are mixed. It does not substitute zero, an ACK, a console delay, or one
observation for a distribution. Overlapping components are rejected before
subtraction. W13's proxy screening (`AIW upper bound = H − 51 s`) is a
**derived screening bound**, not a measured AIW distribution, and is not
reported as an AIW result.

## 5. Cross-member reconciliation

| Fact | Measured / simulated / absent | Owner | What closes it |
|---|---|---|---|
| Accepted S1/S2 scenario windows | measured scenario QA; **not** predictive eligibility | Member A | A valid predictive run with resolved identity and absolute time |
| Device absolute UTC and clock sync | absent | Member A | Device wall-clock/clock-sync evidence or an authoritative common event-time domain |
| Run identity | unresolved | Member A | one resolved run id per independent run |
| Calibration traceability | absent | Member A | calibration id and traceable probe calibration |
| Critical threshold / representative T | unfrozen | Member D | frozen critical definition |
| Door→critical time | `NOT_COMPUTABLE` | A + D | supervised S2 capture under the frozen critical definition |
| command→electrical | 1.094 s, n=1 console | Member A | additional START traces and a distribution |
| command→thermal | 51.0 s single applied-on observation | Member A | command-anchored repeated measurements |
| command→ACK | absent | Member C/D | command publication and ACK anchors in one event-time domain |
| Network command path / T_system | absent (`GAP-NETWORK-COMMAND-LATENCY`) | Member C/D | transport decision and authorized energized session |
| Physical actuation verification | `physical_verified = false` | Member D/A | verified electrical and thermal response chain |
| PR #95 | open, unmerged, not canonical | Leader | merge decision and its restrictions |

## 6. Estimability verdict

```text
EWT: NOT_ESTIMABLE
  primary reason: EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY
  contributing reasons: EVENT_UTC_UNAVAILABLE_DEVICE_HAS_NO_WALL_CLOCK,
    HOST_RECEIPT_TIME_IS_NOT_PHYSICAL_EVENT_TIME,
    CLOCK_SYNC_NOT_EVIDENCED_IN_PACKAGE,
    RUN_IDENTITY_UNRESOLVED_FOR_CG_RUN_PATTERN,
    CALIBRATION_TRACEABILITY_ABSENT_FROM_PACKAGE_SCHEMA,
    SEGMENTS_SHARE_BOOTS_ROWS_ARE_NOT_INDEPENDENT_RUNS,
    CRITICAL_CRITERION_AND_REPRESENTATIVE_T_NOT_FROZEN

AIW: NOT_ESTIMABLE
  primary reason: AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING
  missing components: t_critical, t_warning, T_system, complete T_physical chain
```

## 7. What would make EWT/AIW estimable

1. Member D freezes the critical Tmean/representative temperature.
2. Member A resolves run identity, absolute event time, clock sync and
   calibration traceability, then produces an admissible non-intervened
   predictive trajectory.
3. Member A repeats command→electrical START traces and command-anchored
   command→thermal measurements; performs the offline door→critical rerun after
   D freezes the definition.
4. Member C/D establish the network command path and measure the system latency
   chain end to end.
5. The leader resolves PR #95's merge/non-canonical status.
6. Member B then re-runs EWT/AIW on the admissible population; no numeric
   distribution is assumed before that.

## 8. Boundaries

- No fabricated EWT/AIW number, distribution or confidence interval.
- No ACK-as-actuation, console-as-network, single-observation-as-distribution,
  missing-latency-as-zero or double-counted overlap.
- No predictive-intervened counterfactual.
- No change to W13's scientific decision.
- No A/C/D source or evidence changes.

## 9. Reproduction and binding

```bash
cd ml
uv run --locked --python 3.12 python scripts/w14-ablation-W14.py
```

| Binding | Value |
|---|---|
| W14 manifest | `w14-manifest.json` SHA-256 `e4a0263ead067a10df8d23ffc2bb10d6e750c88e515153fd6f637c733077357d` |
| W13 input manifest | SHA-256 `02a76660319f6118900ec54ee3d50fa96968ad14b0a7110f3fdaf1b62417a404` |
| W12 EWT assessment | `ml/reports/W12/ewt-assessment-W12.csv` (hash bound in the W14 manifest) |
| Base revision | `824a5389c29ade0e56ecef7ef21eb35c2a379a7b` |

## 10. Unresolved questions

- When will D freeze the critical threshold, and will A's offline door→critical
  rerun then be sufficient? **Open A/D dependency.**
- Will C/D adopt a network command path that can be measured end to end?
  **Open C/D dependency.**
- Does the PR #95 passive S1 trial become canonical? **Leader decision; it still
  has no commands, absolute time or calibration.**
