# Member D W04–W13 closure plan without changing A/B/C work

This is an acceptance ledger, not a claim that the ten weeks are physically
complete. Member D changes stay in `control/` and `evidence/D/`; A/B/C deliver
their own measured inputs and integrations through the interfaces in Doc 05D
§30. No other member's evidence is edited or re-labelled.

| Week | D-owned reviewable work | External evidence required for final acceptance |
|---|---|---|
| W04 | Legal action, TTL, safety checklist and reason-code unit contracts | A's first-actuation safety review, boot/reset and branch evidence; G1 approval |
| W05 | Quality/freshness/UNKNOWN semantics and negative tests | Real sensor-channel quality and stale-state integration trace |
| W06 | Pure command rejection/idempotency matrix | A/C device transport test: expired, duplicate, wrong-device, range and invalid-state commands; canonical ACK plus no second physical effect; C UI/log interpretation |
| W07 | Deterministic Controller A and replay tests | A's qualified repeated plant runs, frozen representation/thresholds and one supervised real Controller A run |
| W08 | SAFE_LOCAL entry/exit and reconnect gate logic | A/C broker-loss/reconnect trace showing local protection and stale-desired rejection; G2 review |
| W09 | Staged verifier with applied-state, quality and evidence-age gates | A's qualified OFF/ON current/power envelopes, thermal response and timing across independent runs |
| W10 | Unsafe-injection blacklist and fault oracles | A's safe S4 test mode and attended capture; sensor/PZEM protocol observations |
| W11 | Candidate incident-action map and synthetic negative tests | A's fault captures, D/A review of physical disposition, C persistence of state/reason/evidence window |
| W12 | Controller A replay function and gate inventory | A/B qualified run set, C command lifecycle records, valid real S2 runs and whole-team G3 signoff |
| W13 | WATCH/PREEMPTIVE semantics, config versioning and fail-closed AIW calculator | B warning timing, A response/door→critical timing, C end-to-end latency; shared clock and G3/W14 gate |

For every physical run, use Doc 03 §5's manifest and keep raw command, ACK,
applied-state, electrical, thermal and event records under one `run_id`, with
firmware/hardware/policy versions, validity review and file hashes. A unit
fixture is labelled synthetic and cannot close a physical gate.

**Next D-only actions when external artifacts arrive:** validate their schema
and quality; pin source hashes; replay Controller A and the verifier; compare
expected versus observed state; publish a per-run reasoned PASS/FAIL/UNKNOWN
report. Do not freeze a threshold, envelope, AIW number, G2 or G3 from the
current unqualified/one-session evidence.
