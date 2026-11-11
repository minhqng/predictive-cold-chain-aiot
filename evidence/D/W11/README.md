# Week 11 – Cooling‑health integration

## Status summary

| Item | Status | Owner | Evidence needed |
|------|--------|-------|-----------------|
| D‑W11‑01 Electrical response missing | **OPEN** | A (S4 test) / D (policy) | Capture of ON command with no electrical response under safe test mode |
| D‑W11‑02 Thermal effectiveness degraded | **OPEN** | A (thermal test) / D (policy) | Controlled degraded thermal response evidence |
| D‑W11‑03 Unexpected current while OFF | **OPEN** | A (hardware) / D (policy) | Safe emulation of OFF current anomaly evidence |
| D‑W11‑04 Incident actions mapping | **CANDIDATE DEFINED; RUNTIME OPEN** | D | `incident-action-candidate-v1.md` and `incident.py` cover every health state; physical approval and runtime enforcement remain open |
| D‑W11‑05 Integration with C | **HANDOFF CONTRACT DEFINED; INTEGRATION OPEN** | C (backend) / D (policy) | `diagnosis-event-handoff.md`; C persistence and end-to-end evidence remain open |

Current main adds A-W21-03 on-device PZEM-unavailable evidence. D's read-only
cross-check now confirms that its observed invalid/missing-current and recovery
behavior matches the non-energized PZEM oracle. It does not show an energized missing
response, thermal ineffectiveness, unexpected OFF current, C persistence or a
runtime incident action or a persisted D diagnosis event. The current code defines vocabulary, fault protocols
and a pure candidate action map; it does not classify live cooling health or
apply incident actions. See Doc 05D §43 before choosing a physical action.
