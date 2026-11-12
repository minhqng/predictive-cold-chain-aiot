# W17 online/offline shadow parity — software replay

- Layer: `coldguard-w17-shadow-parity-v1`
- Source basis: W16 stack head `c2b62234466b09585cf4e868c67a4d49ae06597f` (W16_STACK_HEAD_BASE_NOT_W17_DELIVERY_COMMIT)
- Dataset: `W11_EXPANDED_SYNTHETIC_GROUPED` / `coldguard-w11-synthetic-grouped-v1` (synthetic development population)
- Development runs: 16
- W10 registry: `CG-FEAT-1.0` `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9`
- W15 model: `coldguard-w15-synthetic-xgb-candidate-v1` `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f`
- Evidence class: `SYNTHETIC_SOFTWARE_CONTROL_ONLY` (data origin); `OFFLINE_REPLAY_VERIFIED` (verification level)

## Verdicts

- B-W17-01 feature parity: `OFFLINE_FEATURE_PARITY_VERIFIED`
- B-W17-01 prediction parity: `OFFLINE_PREDICTION_PARITY_VERIFIED`
- Real online shadow: `LIVE_SHADOW_NOT_ESTABLISHED`
- Physical shadow: `PHYSICAL_SHADOW_BLOCKED`

## Method

The offline reference is the canonical W10 causal batch pipeline over the history authorized at the anchor: event time at or before the anchor *and* deterministic receipt at or before prediction emission. The online path independently assembles the same authorized set incrementally: it ingests frames in deterministic arrival order, deduplicates identical deliveries, rejects contradictory identities, classifies late/out-of-order delivery, enforces the event-time and arrival-time cuts, sanitizes stale channels to missing values and only then calls the same W10 formulas on the accepted prefix. Both paths share the canonical W10 formula implementation by design; W17 does not create a competing feature definition.

- Feature tolerance: `1e-09` absolute (identical float64 formula and authorized sample order; the observed maximum deviation is 0, the tolerance covers future serialization drift only)
- Score tolerance: `1e-12` absolute (same guarded model instance, same library version, deterministic single-threaded booster; W15 reload parity uses the same bound)
- Wider tolerances are refused by the comparison API, so a changed formula cannot be hidden by relaxing the tolerance.

## Results

| Metric | Value |
|---|---|
| Replay runs | 16 |
| Anchors | 784 |
| Compared anchors | 783 |
| Defined feature values compared | 19428 |
| Missing feature values compared | 2496 |
| Feature comparisons failed | 0 |
| Prediction comparisons failed | 0 |
| Maximum feature deviation | 0 |
| Maximum risk-score deviation | 0 |
| Rejected anchors | 1 |
| Excluded degraded windows | 0 |
| First mismatch | none |
| Late observations recorded | 1 |
| Unconsumed trailing records | 0 |
| Replay input records | 2896 |
| Replay input hash | `e18ef867ded9684d0e5b3b9db35a3c5e7ed64e8223f93c9c77db17ffa3eac4f2` |

One deterministic late delivery was injected in run `CG-W11-S2-003` for frame `cg-synthetic-001:CG-W11-S2-003-BOOT-1:30` at scheduled arrival 60 s (default 0.25 s transport delay). The reference applies the same availability cut, so the frame is excluded from earlier anchors and included only after receipt; the recorded late count above is real, not structural.

| Refusal disposition | Count |
|---|---|
| `REFUSED_STALE_INPUT` | 1 |


### Refused anchor detail

| Run | Anchor | Disposition | Reasons |
|---|---|---|---|
| `CG-W11-S2-003` | 30 | `REFUSED_STALE_INPUT` | `ANCHOR_OBSERVATION_MISSING` |

## Unused-feature mutation proof

The W15 synthetic model uses only `time_since_open`; every other feature is unused. A deliberate +0.5 mutation to an unused, defined feature must fail feature parity while leaving the score unchanged.

- Performed: True
- Mutated feature: `T_chamber_max_c`
- Mutation delta: 0.5
- Feature-parity failure detected: True
- Score unchanged: True
- First mismatch: T_chamber_max_c: |5.351299853538284 - 5.851299853538284| = 0.5 > 1e-09

This prevents a misleading score-only PASS: score equality alone is never accepted as feature evidence.

## Independence of the two paths

The online path owns the arrival queue, deduplication, identity checks, boot boundary, late classification, availability cut and channel sanitization; the offline path filters the declared authorized history and recomputes the canonical batch formulas. Parity is only reported after both paths are exercised, and the harness rejects any online input that was not available at prediction time.

This is authorization/assembly parity over a shared canonical formula implementation, not formula independence. A defect inside the shared W10 formula would not be detected here; W10's own formula tests remain the authority for that risk.

Discriminating negative controls in the test suite: a future-event frame leaves a past anchor byte-identical; a late packet cannot change an emitted anchor and only enters a later prediction after its receipt; a contradictory duplicate identity fails closed; a boot transition clears door/observation state; the unused-feature mutation above fails feature parity while the score stays equal. These controls fail if the online assembly ignores availability, boot boundaries, duplicate identity or channel staleness.

## Provenance and boundaries

- Fixture identity: `68b981e642bc0309a8c7aa7cb8499b503da97a2b1946ce509c7eea81bc4d78d0`
- The W11 synthetic fixture is generated as declared by W11/W15; only development trajectories are passed to the replay. The W16 locked test runs were never evaluated, inspected or included; development/test overlap: `[]`.
- The W15 artifact remains `NON_DEPLOYABLE_CANDIDATE`, `SYNTHETIC_SOFTWARE_CONTROL_ONLY`, `RISK_SCORE_ONLY`.
- No command, broker, actuator, backend or network capability is reachable from this path; no subprocess is executed during replay.

## Limitations

- Synthetic fixture only; no physical predictive claim.
- Parity verifies availability/assembly parity over the shared canonical formula implementation; it cannot detect a pure formula defect.
- The clean population contains no stale channel; stale PZEM/door behavior is demonstrated by the dedicated probes and adversarial tests, not by the delivered parity run.
- A raw frame without an explicit channel timestamp is treated as if its channels were observed at the frame event time; this is a declared synthetic assumption, not a physical attestation.
- The primary horizon, operating threshold, warning persistence and runtime freshness policy remain unfrozen.
- Offline replay parity does not imply live online shadow acceptance.
