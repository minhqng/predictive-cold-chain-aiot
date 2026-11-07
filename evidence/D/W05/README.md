# W05 evidence — Physical-quality integration and stale-state prevention

**Date:** 2026-11-07
**Owner:** Member D (control / safety / security / resilience)
**Parent issues:** 05D D-W05-01 through D-W05-04

## Goal

Ensure policy consumes quality/freshness, not bare numbers (Doc 01 section 19; Doc 02 sections 40.1 and 67):
* Policy input type includes quality states;
* Stale-state tests;
* Missing-channel behavior;
* UNKNOWN semantics (never mapped to healthy).

## Deliverables

| Deliverable | Location | State |
|---|---|---|
| Quality assessment module | `control/src/coldguard_control/quality.py` | Implemented |
| ChannelObservation type | `control/src/coldguard_control/quality.py` | Implemented |
| QualityAssessment result | `control/src/coldguard_control/quality.py` | Implemented |
| Quality unit tests | `control/tests/test_quality.py` | 12 tests |
| Config freshness bounds | `control/src/coldguard_control/config.py` | Added |

## Test results

From `control/`:

```powershell
uv run --locked --extra test pytest tests/test_quality.py -v
```

```text
12 passed
```

## Key design decisions

### Three questions separated (05D section 5)

The quality assessment layer explicitly separates:

```text
thermal_safety_usable
    Can local deterministic protection still act on the thermal state?

predictive_inputs_available
    Are all channels the predictive path consumes present, VALID and fresh?

verification_confidence
    How much independent evidence exists for an electrical/thermal claim?
```

### UNKNOWN is never healthy (Doc 01 section 19.4)

A missing PZEM does not become a measured zero. It makes electrical evidence `UNKNOWN` and blocks the predictive path until a frozen model contract says the model can run without it.

### Freshness requires explicit bounds

A VALID quality with no age is not control-fresh. The caller must supply the observation age, and the matching maximum age must be explicitly configured (no hidden freshness constants). When the age is supplied but no bound exists, the channel is not considered fresh (fail closed).

### Degraded thermal keeps safety usable

A DEGRADED thermal state (e.g., one probe failed out of three) can still support local thermal protection. However, predictive action is prohibited unless a frozen model contract explicitly supports the missing-channel state.

### Verification confidence collapse

Electrical and thermal evidence combine into a single `verification_confidence` state:
* Both VALID and fresh → `VALID`
* Either INVALID → `INVALID`
* Either DEGRADED (with fresh VALID other) → `DEGRADED`
* Missing/stale evidence → `UNKNOWN`

## Test scenarios

| Test | Purpose |
|---|---|
| `test_all_fresh_valid_is_predictive_available` | Baseline: all channels VALID and fresh |
| `test_unknown_thermal_is_not_treated_as_healthy` | UNKNOWN never becomes VALID |
| `test_stale_thermal_is_not_control_fresh` | Age exceeds bound → not fresh |
| `test_degraded_thermal_keeps_safety_usable` | DEGRADED supports local protection |
| `test_missing_electrical_is_unknown_not_invalid` | PZEM unavailable → UNKNOWN, not INVALID |
| `test_invalid_electrical_is_control_invalid` | Determined failure → INVALID |
| `test_door_never_defaults_to_closed` | Door UNKNOWN never treated as CLOSED |
| `test_age_without_bound_is_not_fresh` | No configured bound → not fresh |
| `test_negative_age_is_rejected` | Negative age → error |
| `test_non_finite_age_is_rejected` | NaN/inf age → error |
| `test_non_enum_quality_is_rejected` | Raw string quality → error |
| `test_verification_confidence_collapses_correctly` | Quality combination matrix |

## Acceptance status

| Requirement | Status | Evidence |
|---|---|---|
| D-W05-01 Policy input type | PASS | `quality.py`, `config.py` freshness bounds |
| D-W05-02 Stale-state tests | PASS | `test_quality.py` (12 tests) |
| D-W05-03 Missing-channel behavior | PASS | `test_missing_electrical_is_unknown_not_invalid` |
| D-W05-04 UNKNOWN semantics | PASS | `test_unknown_thermal_is_not_treated_as_healthy` |

## Open items

| Item | Owner | Next action |
|---|---|---|
| Characterize electrical_max_age_s | A/C | Measure PZEM polling latency and staleness tolerance |
| Characterize door_max_age_s | A/C | Measure door sensor update frequency and latency |
| Model contract for degraded channels | B | Define which missing-channel states the model can handle |
| Integration with policy input | D | Wire `assess_quality()` into `evaluate_policy()` |

## Read order

1. `quality.py` — physical-quality input contract
2. `config.py` — freshness bound fields
3. `test_quality.py` — test scenarios
4. Doc 01 section 19 — quality state definitions
5. 05D section 5 — policy input requirements
