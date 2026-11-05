# ColdGuard Member A — W24 Final HIL Smoke Protocol

**Requirement Authority:** `docs/05A §33: A-W24-02`  
**Status:** **OPERATOR_RUNBOOK_READY / PHYSICAL_ACTUATION_FORBIDDEN**

---

## 1. Safety Posture & Explicit Actuation Prohibition

> [!CAUTION]
> **TEC OUTPUT STAGE ENERGIZATION IS STRICTLY FORBIDDEN** while:
> 1. Hardware acceptance gates `H-GATE-1` through `H-GATE-10` remain open (`evidence/A/RC/remaining-hardware-gates.md`).
> 2. Slot-3 15 A fuse is removed.
> 3. Ground-loop / USB backfeed mitigation (`H-GATE-6`) has not been attested by the operator.
> 4. PSU 12 V is OFF.
> 
> No automated script or test runner is permitted to assert non-zero PWM duty on physical hardware.

---

## 2. Sequence of Operations (Supervised Bench Inspection Only)

1. **Step 1 (Passive Unenergized Verification):**
   - Read DS18B20 temperatures across all 4 probes (T1 Chamber Center, T2 TEC Hot Side, T3 Chamber Bottom, T4 Near Door).
   - Read BME280 ambient temperature, humidity, and pressure over I2C.
   - Verify MC-38 door reed switch open/closed transitions on GPIO 35.
   - Verify PZEM-017 Modbus RTU communication idle response on GPIO 36/37.
2. **Step 2 (Boot Default Verification):**
   - Assert `pwm_applied_permille = 0` on clean startup.
   - Verify IBT-2 control pins remain pulled low (RPWM=GPIO 5, R_EN=GPIO 6, L_EN=GPIO 10, LPWM=GND).
3. **Step 3 (Controlled Step Smoke — PENDING GATES RESOLUTION):**
   - **BLOCKED / PENDING:** Controlled duty pulse execution requires operator presence, resolution of `H-GATE-1` through `H-GATE-10`, fuse installation, and explicit two-step written operator authorization.
