# Week 17 — Predictive shadow mode

**Current status: SHADOW ADAPTER TESTED; LIVE SHADOW RUN PENDING.**

C PR #73 was inspected at
`fb71b3c87bf140732cc85c520baf630d38ae18cb`. It stores prediction provenance,
hypothetical policy output and timing without a command transport.

`shadow.py` adapts D's existing pure policy to W17. It records the hypothetical
state/action/reason, emits a deterministic SHA-256 decision identity, blocks
stale/unavailable predictions, compares Controller A and hypothetical B timing
only when both anchors exist, and has a fixed
`physical_command_emitted=false` invariant.

`ShadowExitReport` aggregates false policy transitions, stale-state issues,
unresolved ambiguity and safety-block reasons while enforcing zero emitted
commands. It is an evidence structure, not a claim that the pending live
shadow campaign has exited successfully.

The tests use synthetic policy values solely to verify logic. A live W17 exit
report still needs a frozen B model/feature contract and policy candidate,
running C experiment/telemetry stream, qualified A timing anchors, and an
observed shadow campaign. No physical B command has been issued.
