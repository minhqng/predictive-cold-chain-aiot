# W13 primary horizon decision

**Category: PROVISIONAL_CANDIDATE_ONLY**

- Study completeness: 3 of 4 horizons evaluated under the grouped pipeline; H=300 s refused (NOT_RUN_HORIZON_REFUSED)
- Primary horizon: undefined (NOT_FROZEN)
- Provisional candidates (s): 60, 120, 300
- Deprioritized by physics proxy (s): 30

## Selection preconditions

| precondition | satisfied |
|---|---|
| real_eligible_predictive_runs | false |
| critical_criterion_frozen | false |
| door_to_critical_measured | false |
| measured_latency_chain | false |
| selection_rule_frozen_before_outcomes | false |
| locked_test_untouched | true |

## Blockers

- `real_eligible_predictive_runs`
- `critical_criterion_frozen`
- `door_to_critical_measured`
- `measured_latency_chain`
- `selection_rule_frozen_before_outcomes`

## Rationale

- candidate set comes from the canonical 30/60/120/300 s exploratory horizons for the fast six-litre plant; no longer horizon is invented because the measured tau proxies are truncation-biased
- physics screening deprioritizes horizons at or below the measured applied-on->thermal response proxy (AIW upper bound <= 0 even with zero system latency); the screening is DERIVED, not a measured verdict
- synthetic per-horizon AP is a software control; the highest synthetic AP never selects a primary horizon
- real predictive eligibility is refused (0 eligible runs); real prevalence, AP, event recall, false warnings, EWT and AIW are NOT_ESTIMABLE, not zero
- T_critical, representative temperature and the primary horizon remain unfrozen ledger items; D's critical-Tmean threshold freeze and A's offline door->critical rerun are outstanding

## What would close the blockers (owners, not B unilateral actions)

- Member D: freeze the critical Tmean threshold / candidate critical definition (safety contract; A-W10-05 / A-W13-03 INCOMPLETE).
- Member A: once D freezes, the door->critical evaluation is a pure offline rerun on the existing S2 windows (0 new physical measurements); supervised captures remain A's authority.
- Member C / D: transport decision for the network command path (GAP-NETWORK-COMMAND-LATENCY) before any measured latency chain.
- Leader: PR #95 merge decision; until merged it stays NOT_VERIFIED_FOR_CANONICAL_USE.
- Member B (next W13 cycle, only after the above): freeze the selection rule before outcomes, re-run the real grouped evaluation, and only then consider PRIMARY_CANDIDATE_SELECTED.

## Boundaries honored

- Synthetic AP (fixture `W11_EXPANDED_SYNTHETIC_GROUPED`) was never decision-grade; no horizon was chosen on the locked test.
- Real predictive eligibility: 0 runs; real metrics are NOT_ESTIMABLE, not zero.
- This decision freezes nothing: T_critical, representative temperature and the primary horizon remain open ledger items.
