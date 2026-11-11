# Week 13 – Predictive‑policy semantics and latency budget

## Status summary

| Item | Status | Owner | Evidence needed |
|------|--------|-------|-----------------|
| D‑W13‑01 AIW inputs | **CONTRACT + TESTED CALCULATOR; MEASURED INPUTS OPEN** | D | `aiw-input-contract.md` and `aiw.py` require qualified B/A/C timing and a shared clock; no project number generated |
| D‑W13‑02 WATCH semantics | **DEFINED** | D | Mapping of elevated risk to WATCH state (policy code already implements) |
| D‑W13‑03 PREEMPTIVE semantics | **DEFINED** | D | Mapping of risk above threshold & persistence to PREEMPTIVE_COOLING (policy code) |
| D‑W13‑04 Hard protection dominance | **DEFINED** | D | CRITICAL_PROTECTION dominance already in policy logic |
| D‑W13‑05 Policy config versioning | **DEFINED** | D | `policy_version` and explicit numeric inputs exist; a measured predictive configuration is not frozen |
| AIW gap – door→critical, network latency | **30.5 C CANDIDATE EVALUATED; TIMING STILL OPEN** | A / C / D | All four accepted S2 door runs remain below 30.5 C, so only right-censored lower bounds exist; C network command/applied latency is also absent |

## Main integration refresh — 2026-11-11

Main `557e887` now carries the integrated command/ACK software path and the
B→D dependency-closure sidecar. The hash-bound result is recorded in
`main-integration-crosscheck-20261111.json`.

The software lifecycle is `TRACED`, but its own provenance states that firmware
was not executed and its post-ACK frames are synthetic. A's observational
`ELECTRICAL_VERIFIED` / `THERMAL_VERIFIED` stage names therefore do not become
D `HEALTHY_RESPONSE`; D remains `UNKNOWN`. The B closure admits 3,721 rows but
produces zero positive labels and only `UNAVAILABLE` prediction views, so AIW
is still `NOT_ESTIMABLE` and Controller B remains disabled.

WATCH and PREEMPTIVE are unit-level policy semantics from W03. The team-supplied
30.5 C candidate is recorded in `critical-threshold-candidate-v0.json` and
evaluated by `s2-critical-threshold-evaluation.json` against A PR #91's
hash-bound S2 source: 0/4 accepted door runs
cross it; maximum post-door Tmean is 30.0000 C and each capture provides only
a roughly 235–237 s right-censored lower bound. A longer/hotter admitted S2
capture or a justified threshold revision is required for door-to-critical
timing. These runs also do not supply B's warning-time distribution or C's
end-to-end latency.
Enabling Controller B remains blocked by G3, model/feature version agreement,
B's warning evidence and a measured joined AIW budget. No predictive
intervention is claimed.
