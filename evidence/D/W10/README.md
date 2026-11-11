# Week 10 – Safe fault‑injection protocol and diagnosis design

## Status summary

| Item | Status | Owner | Evidence needed |
|------|--------|-------|-----------------|
| D‑W10‑01 S4 electrical‑response‑missing fault | **OPEN** | A (test mode) / D (oracle) | Safe test mode implementation and S4 capture evidence |
| D‑W10‑02 Sensor degraded protocol | **SOURCE CASE MATCHES D ORACLE** | A (hardware) / D (policy) | A-W21-02 reversible single-DS18B20 software injection matches the non-energized source oracle; runtime D event and C persistence remain open |
| D‑W10‑03 PZEM unavailable protocol | **SOURCE CASE MATCHES D ORACLE** | A (communication) / D (diagnosis) | A-W21-03 PZEM transport-boundary software injection matches the non-energized source oracle; runtime D event and C persistence remain open |
| D‑W10‑04 Unsafe injections blacklist | **COMPLETE** | D | Documented blacklist (see docs/05D‑member‑d‑control‑security‑resilience.md) |
| D‑W10‑05 Fault oracle table | **COMPLETE** | D | Oracle definitions in `coldguard_control/faults.py` |

A-W21-02/03 used a real ESP32-S3, but the TEC output stage was compiled out
and the fuse was removed. They are source cases for sensor/PZEM degradation,
not proof of enabled-actuator fail-safe behavior, missing electrical response
while ON, or an end-to-end incident action. `a-w21-oracle-crosscheck.json`
pins the three source hashes, admits the two test-only software techniques in
D's protocol table, and records both cases as
`MATCHED_NON_ENERGIZED_SOURCE_CASE`.
