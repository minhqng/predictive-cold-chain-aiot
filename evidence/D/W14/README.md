# Week 14 — Predictive threshold, persistence and AIW gate

**Current status: SOFTWARE GATE READY; POLICY INPUT BLOCKED.**

Upstream inputs were inspected at B PR #102
`824a5389c29ade0e56ecef7ef21eb35c2a379a7b`, B PR #103
`9027c469a82859b4eb2dcf5b4d8255bf1f59c641`, and C PR #70
`8803b29008b80aa9917fd514aff479db44650537`.

The B handoff currently says:

- primary horizon is not frozen; 60/120/300 s are provisional and 30 s is
  deprioritized;
- no operating score threshold or persistence is supplied;
- model output is `risk_score`, not a calibrated probability;
- real eligible predictive runs = 0;
- EWT and AIW are `NOT_ESTIMABLE`.

`predictive_gate.py` implements a fail-closed intake gate. On the current B
evidence it returns `BLOCKED_MISSING_POLICY`, forbids probability wording and
keeps `physical_enablement=false`. A fully populated future input can become
only `ACTUATION_REVIEW_CANDIDATE`; the gate itself never enables hardware.

Still required: B threshold/persistence/horizon freeze, model and feature
freeze, real eligible runs, positive qualified AIW, G3 GREEN and G4 GREEN.
