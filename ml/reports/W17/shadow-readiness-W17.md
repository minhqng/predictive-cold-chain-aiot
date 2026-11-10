# W17 shadow readiness assessment

- Layer: `coldguard-w17-shadow-parity-v1`
- Evidence class: `SYNTHETIC_SOFTWARE_CONTROL_ONLY` (data origin); `OFFLINE_REPLAY_VERIFIED` (verification level)

## Four levels

| Level | Verdict |
|---|---|
| 1. Offline feature parity | `OFFLINE_FEATURE_PARITY_VERIFIED` |
| 2. Offline prediction parity | `OFFLINE_PREDICTION_PARITY_VERIFIED` |
| 3. Software shadow-trace readiness | `SHADOW_TRACE_SOFTWARE_VERIFIED` |
| 4. Real online shadow acceptance | `LIVE_SHADOW_NOT_ESTABLISHED` |

Physical shadow: `PHYSICAL_SHADOW_BLOCKED`.

Levels 1-3 are software-verifiable. Level 4 stays blocked by the scientific and cross-member prerequisites below; no replay result overrides them.

## W16 prerequisite relationship

| Item | State |
|---|---|
| W16 manifest | `6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165` |
| Holdout access | `NOT_AUTHORIZED` |
| Holdout opened | `False` |
| Locked evaluation | `NOT_EXECUTED_PREREQUISITES_UNMET` |
| Model release candidate | `NOT_ISSUED` |
| W16 readiness decision | `REFUSED_PREREQUISITES_UNMET` |
| G4 ready | `False` |
| W13 primary horizon | `ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN` |
| W15 model release eligibility | `NON_DEPLOYABLE_CANDIDATE` |
| W15 score semantics | `risk_score` (`RISK_SCORE_ONLY`) |

W17 software replay does not issue a model release candidate, does not open the holdout and does not change Gate G4.

## W16 test-count reconciliation (preflight evidence)

| Metric | Value |
|---|---|
| W16 head | `c2b62234466b09585cf4e868c67a4d49ae06597f` |
| W15 base collected | 992 |
| W16-added test functions | 105 |
| W16 collected | 1097 |
| Actual passed | 1094 |
| Actual skipped | 3 |
| PR #105 body passed | 1088 |
| PR #105 body skipped | 3 |
| Conclusion | `STALE_PR_BODY_NOT_A_DELIVERED_REGRESSION` |

No test file changed between daf85e0 and c2b6223; the delivered W16 tree contains all 105 added tests. The PR body count is six tests below the reproducible collection, consistent with a description written before the final six W16 tests were added. Correct the PR #105 body factually to 1094 passed, 3 skipped; no W16 history rewrite and no W16 code change are required.

## Acceptance terminology

| Term | Status |
|---|---|
| `OFFLINE_FEATURE_PARITY_VERIFIED` | `yes` |
| `OFFLINE_PREDICTION_PARITY_VERIFIED` | `yes` |
| `SHADOW_TRACE_SOFTWARE_VERIFIED` | `yes` |
| `LIVE_SHADOW_NOT_ESTABLISHED` | yes |
| `PHYSICAL_SHADOW_BLOCKED` | yes |

The ambiguous standalone verdict `SHADOW PASS` is not used.

## Distinction

- `OFFLINE_SOFTWARE_REPLAY`: the W17 result. Synthetic fixture, offline harness, no live telemetry.
- `REAL_ONLINE_SHADOW_ACCEPTANCE`: not established. It requires a physical dataset, frozen model release, frozen policy/freshness semantics, accepted C integration and D safety evidence.

## Team dependencies

| Owner | Needed evidence | Current state |
|---|---|---|
| Member A | physically valid live/observational runs; trusted sensor and event-time provenance; shadow isolation | not available in the W16 base; A W17 audit reports data insufficient |
| Member C | accepted online inference integration; durable prediction/trace schema; prediction input identity and freshness | PR #73 open/unmerged; not treated as the final runtime contract |
| Member D | frozen shadow-policy semantics; hypothetical-decision safety rules; proof predictive output cannot bypass Controller A | not frozen; W17 does not invent policy |
| Member B | feature/model identity; offline/online parity; freshness and input correctness; reproducible trace; limitations | this delivery |
| Leader | cross-member acceptance and integration ordering | not established |

## External dependency snapshot

| Dependency | State |
|---|---|
| `gate_g4` | `NOT_READY` |
| `member_a_w17_shadow_audit` | `DATA_INSUFFICIENT_ZERO_SYNCHRONIZED_RUNS` |
| `member_c_pr_73_shadow_trace` | `OPEN_UNMERGED_NOT_INTEGRATION_ACCEPTANCE` |
| `member_d_shadow_policy` | `NOT_FROZEN` |
| `model_release_candidate` | `NOT_ISSUED` |
| `runtime_freshness_policy` | `PENDING_C_D` |
| `team_lead_cross_member_acceptance` | `NOT_ESTABLISHED` |

The dependency states are a read-only interface-audit snapshot at implementation time; they are not runtime monitoring.

## One next Member B action

Prepare the W18 runtime monitoring harness against the frozen W15 artifact contract (hash, feature version, threshold and freshness status checks) while keeping Controller B physically disabled; do not enable predictive actuation until G4 is established.
