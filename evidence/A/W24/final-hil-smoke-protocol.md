# ColdGuard Member A — W24 Final HIL Smoke Protocol

**Requirement Authority:** `docs/05A §33: A-W24-02`  
**Status:** **OPERATOR_RUNBOOK_READY**

---

## 1. Sequence of Operations

1. **Passive Verification:** Verify DS18B20 temperatures (T1, T2, T3, T4), BME280 humidity/pressure, door reed switch open/closed transitions, and PZEM idle readings.
2. **Boot Default Verification:** Assert `pwm_applied_permille = 0` on clean startup.
3. **Controlled Step Smoke:** Execute short legal duty pulse (duty 200 permille, 5 seconds) under operator supervision; verify PZEM current rise and immediate return to 0.
