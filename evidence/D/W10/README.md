# Week 10 – Safe fault‑injection protocol and diagnosis design

## Status summary

| Item | Status | Owner | Evidence needed |
|------|--------|-------|-----------------|
| D‑W10‑01 S4 electrical‑response‑missing fault | **OPEN** | A (test mode) / D (oracle) | Safe test mode implementation and S4 capture evidence |
| D‑W10‑02 Sensor degraded protocol | **DEFINED** | A (hardware) / D (policy) | Physical sensor disconnect procedure and capture |
| D‑W10‑03 PZEM unavailable protocol | **DEFINED** | A (communication) / D (diagnosis) | Communication‑layer removal test and evidence |
| D‑W10‑04 Unsafe injections blacklist | **COMPLETE** | D | Documented blacklist (see docs/05D‑member‑d‑control‑security‑resilience.md) |
| D‑W10‑05 Fault oracle table | **COMPLETE** | D | Oracle definitions in `coldguard_control/faults.py` |
