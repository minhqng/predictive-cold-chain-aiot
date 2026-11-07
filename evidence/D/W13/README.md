# Week 13 – Predictive‑policy semantics and latency budget

## Status summary

| Item | Status | Owner | Evidence needed |
|------|--------|-------|-----------------|
| D‑W13‑01 AIW inputs | **CONTRACT + TESTED CALCULATOR; MEASURED INPUTS OPEN** | D | `aiw-input-contract.md` and `aiw.py` require qualified B/A/C timing and a shared clock; no project number generated |
| D‑W13‑02 WATCH semantics | **DEFINED** | D | Mapping of elevated risk to WATCH state (policy code already implements) |
| D‑W13‑03 PREEMPTIVE semantics | **DEFINED** | D | Mapping of risk above threshold & persistence to PREEMPTIVE_COOLING (policy code) |
| D‑W13‑04 Hard protection dominance | **DEFINED** | D | CRITICAL_PROTECTION dominance already in policy logic |
| D‑W13‑05 Policy config versioning | **DEFINED** | D | `policy_version` and explicit numeric inputs exist; a measured predictive configuration is not frozen |
| AIW gap – door→critical, network latency | **OPEN** | A / C | Not computable; see `evidence/A/W13/plant-timing-report.json` |

WATCH and PREEMPTIVE are unit-level policy semantics from W03. Enabling Controller B remains blocked by G3, model/feature version agreement, B's warning evidence and a measured AIW budget. No new predictive intervention is claimed.
