# Week 19 — Paired A/B campaign wave 1 control integrity

**Current status: HOST INTEGRITY GATE TESTED; PHYSICAL CAMPAIGN WAVE 1 NOT RUN.**

`campaign_integrity.py` freezes the exact Controller A/B identity, policy
version, configuration SHA-256, action profile and failure policy used by a
campaign run. It flags, without modifying evidence:

- controller/policy/config drift;
- action or failure-behavior drift;
- adaptive tuning;
- duplicate logical commands;
- nonsensical verification state;
- missing expected controller action;
- an incomplete command → ACK → applied-state → physical-response trace;
- control anomalies.

Each decision preserves an immutable `pair_id`/run/policy record for Member
B's pair ledger. Pair mismatches and a flagged arm flag the pair; data is never
silently corrected or discarded by this layer. The module is pure and never
emits a physical command.

`verification_sensible=true` alone is not sufficient. Still required: frozen
real Controller A/B configurations, live command traces, physical verification
evidence and the supervised wave-1 A/B campaign. No run has been accepted or
invalidated by this host-only preparation.
