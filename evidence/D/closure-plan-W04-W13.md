# Member D W04–W13 closure plan without changing A/B/C work

This is an acceptance ledger, refreshed against `origin/main` `d22c8d5` on
2026-11-09, not a claim that the ten weeks are physically complete. Member D
changes stay in `control/` and `evidence/D/`; A/B/C deliver
their own measured inputs and integrations through the interfaces in Doc 05D
§30. No other member's evidence is edited or re-labelled.

| Week | D-owned reviewable work | External evidence required for final acceptance |
|---|---|---|
| W04 | Legal action, TTL, safety checklist and reason-code unit contracts | A-W04-06 polarity and A-W12-03 inspection now exist; enabled-stage boot/reset/interlock, fuse/conductor disposition and G1 approval remain |
| W05 | Quality/freshness/UNKNOWN semantics and negative tests | Qualified real telemetry now exists; runtime stale/fresh integration trace and frozen bounds remain |
| W06 | Pure command rejection/idempotency matrix | A/C device transport test: expired, duplicate, wrong-device, range and invalid-state commands; canonical ACK plus no second physical effect; C UI/log interpretation |
| W07 | Deterministic Controller A and replay tests | A's qualified repeated plant runs, frozen representation/thresholds and one supervised real Controller A run |
| W08 | SAFE_LOCAL entry/exit and reconnect gate logic | A/C broker-loss/reconnect trace showing local protection and stale-desired rejection; G2 review |
| W09 | Staged verifier with applied-state, quality and evidence-age gates | New main handoff supplies qualified measurements, but canonical supervised OFF/ON envelopes, applied-state trace and A-W09-04 acceptance remain open |
| W10 | Unsafe-injection blacklist and fault oracles | A-W21-02/03 are now hash-pinned and matched to D's non-energized source oracles; runtime diagnosis/C persistence and remaining S4 cases remain |
| W11 | Candidate incident-action map and synthetic negative tests | Energized missing-response, thermal-degradation and unexpected-OFF-current captures; C persistence of state/reason/evidence window |
| W12 | Controller A replay function and gate inventory | Accepted S2 data and inspection now exist; frozen Controller A run set, C lifecycle records and whole-team G3 signoff remain |
| W13 | WATCH/PREEMPTIVE semantics, config versioning and fail-closed AIW calculator | The 30.5 C candidate was evaluated on four accepted S2 runs; none crossed it, so a justified freeze/crossing capture plus B warning timing and C latency still need a compatible clock chain |

For every physical run, use Doc 03 §5's manifest and keep raw command, ACK,
applied-state, electrical, thermal and event records under one `run_id`, with
firmware/hardware/policy versions, validity review and file hashes. A unit
fixture is labelled synthetic and cannot close a physical gate.

**Next D-only actions when external artifacts arrive:** validate their schema
and quality; pin source hashes; replay Controller A and the verifier; compare
expected versus observed state; publish a per-run reasoned PASS/FAIL/UNKNOWN
report. Do not freeze a threshold, envelope, AIW number, G2 or G3 from the
current unqualified/one-session evidence.
