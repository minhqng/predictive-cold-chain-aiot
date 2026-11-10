# W16 Model Release-Candidate Disposition (B-W16-04)

> **Task:** B-W16-04 — Freeze the model release candidate (Doc `05B` §44).
> **MODEL_RC_STATUS = `NOT_ISSUED`**
> **MODEL_RELEASE_ELIGIBILITY = `BLOCKED`**
> **Canonical output `model-rc/` is deliberately withheld.**
> **Pre-registration manifest:** `ml/reports/W16/locked-test-manifest-W16.json`
> **Manifest SHA-256:** `6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165`

## 1. Statement

**There is no actual approved model release candidate.** The only model artifact
produced by Member B through W15 is a synthetic software control with
`release_eligibility = NON_DEPLOYABLE_CANDIDATE`. Copying it into `model-rc/`,
creating an empty release directory, or minting a dummy artifact would fabricate
release evidence and is explicitly prohibited (W16 packet §12; Doc `03` §137).

The directory `ml/reports/W16/model-rc/` **does not exist** — not empty, not
placeholder. The W16 delivery test enforces its absence.

## 2. Current candidate identity (verified read-only, not modified)

| Field | Value |
|---|---|
| Artifact ID | `coldguard-w15-synthetic-xgb-candidate-v1` |
| Native artifact | `ml/reports/W15/model/model.ubj` |
| Native SHA-256 | `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f` |
| Secondary artifact SHA-256 | `67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd` |
| Model library | XGBoost `3.4.1`, native `ubj` serialization |
| Feature version | `CG-FEAT-1.0` (registry `FROZEN_DEFINITIONS`) |
| Feature schema hash | `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9` |
| Ordered feature hash | `98491993d95ba78292cc245d637a1832ebdfb80b1eb026361e39926fb331223c` |
| Model config | `coldguard-xgb-v1-development-v1`, hash `4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84` |
| Evidence class | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` |
| Release class | `NON_DEPLOYABLE_CANDIDATE` |
| Target | `coldguard-w11-development-label-v1`, `DEVELOPMENT_CANDIDATE_NOT_FROZEN`, `boundary_c = null` |
| Horizon | `60.0 s` — `ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN` |
| Operating threshold | `0.5` — `ILLUSTRATIVE_NOT_FROZEN` |
| Warning persistence | `NOT_FROZEN` |
| Calibration | `RISK_SCORE_ONLY`; no calibrated-probability semantics |
| Training population | `W11_EXPANDED_SYNTHETIC_GROUPED`; 16 synthetic development runs; `locked_test_used = false` |

The model inspects as a door-time rule: all 60 native splits are on
`time_since_open` (threshold `60.0`), and 27 of 28 features are unused. That is a
synthetic-fixture shortcut, not physical predictive capability.

## 3. Release-blocking ledger

| Requirement | Observed state | Status |
|---|---|---|
| Real predictive-eligible development population | `0` eligible runs; Gate B `RED` | BLOCKED |
| Grouped real benchmark | `NOT_ESTABLISHED` | BLOCKED |
| Frozen primary horizon | `NOT_FROZEN` (W13) | BLOCKED |
| Frozen critical target + representative temperature | both unfrozen | BLOCKED |
| Frozen operating threshold | illustrative `0.5` only | BLOCKED |
| Frozen warning persistence | no value | BLOCKED |
| Calibration | `RISK_SCORE_ONLY`; no calibrated probability | BLOCKED for probability semantics |
| Locked predictive evidence | `NOT_EXECUTED_PREREQUISITES_UNMET` | BLOCKED |
| Real EWT / AIW | `NOT_ESTIMABLE` (W14) | BLOCKED |
| Required approvals | all five roles missing | BLOCKED |
| Gate G4 | `NOT_READY` | BLOCKED |

## 4. Conditions required before a release candidate may be issued

A genuine W16-style RC requires, in order (Doc `03` §§92-93; Doc `05B` §54):

1. an admissible physical dataset with evidence-grade runs (Gate B `GREEN`);
2. a frozen, grouped development/test split with immutable membership;
3. one frozen primary horizon, frozen critical target and representative
   temperature selected by their authorities;
4. a frozen operating threshold and warning persistence chosen on development
   data only;
5. calibration semantics confirmed (calibrated probability, or risk-score-only
   with all probability wording prohibited);
6. the model artifact, feature schema and analysis code frozen by hash;
7. all five approvals above issued and bound to the registered identities;
8. one authorized locked evaluation with an immutable receipt;
9. an interpretation derived without retuning;
10. team-lead release authorization.

Items 1–7 are the preflight gate; items 8–10 are the future one-time operation
defined in `locked-test-protocol-W16.md`. A preflight `PASS` would authorize
none of them by itself.

## 5. Non-claims

- No backend registration, inference deployment, shadow activation or
  Controller B enablement has occurred or is proposed.
- The W15 model card's `NON_DEPLOYABLE_CANDIDATE` classification is unchanged.
- This disposition is not a model card approval, not a safety case and not a
  Gate G4 contribution beyond documenting the blocker.
