# ColdGuard Member A — W18 Controller B Physical Enablement Signoff

**Requirement Authority:** `docs/05A §27` (`A-W18-01` through `A-W18-05`)  
**Status:** **BLOCKED_ON_PREREQUISITES (G4, B_MODEL_FROZEN, D_POLICY_FROZEN, PHYSICAL_BENCH_INSPECTION)**

---

## 1. Requirement & Audit Status

- **A-W18-01 (Pre-run Safety Audit):**
  - Software audit implementation in `firmware/tools/cg_w18_enablement_audit.py` with 14 passing automated tests (`firmware/tools/tests/test_cg_w18_enablement.py`).
  - Bench checks (fuse rating 15 A verified, fan operation, terminal torque, sensor discovery, PZEM communication, default-off output stage) require live, unenergized bench inspection by the operator.
  - Cross-team prerequisites: G4 gate signoff, Member B frozen model candidate, and Member D frozen policy candidate are strictly required before any physical enablement.
- **A-W18-02 (Predictive Dry Runs):**
  - Software framework and dry-run telemetry validation ready.
  - Physical closed-loop Controller B actuation has **NOT** been performed on hardware.
- **A-W18-03 / A-W18-04 (Electrical & Thermal Bounds):**
  - Current ceiling reconciled with physical evidence: peak current observed during H8-C endurance run was **9.99 A** (15 A blade fuse rating). Host trip recommendation set to **10.0 A** (avoiding false trip on normal H8 operation).
  - Thermal ceiling reconciled with provisional envelope: **55.0 °C** provisional hot-side ceiling (from W08 / W16). Note that firmware table `cg_tec_limits.c` marks `hot_side_max_c` as `CG_LIMIT_UNRESOLVED` (`source = "HOT_SIDE_LIMIT_NOT_ESTABLISHED"`). Formal Gate A approval remains pending.
- **A-W18-05 (Abort Criteria):**
  - Instant trip recommendation on limit violation.
  - Enforces **fail-closed** trip recommendation immediately upon missing, NaN, negative, or out-of-range sensor readings.
  - Clear architectural distinction maintained: host tool emits `HOST_TRIP_RECOMMENDATION` (advising PWM=0), while actual physical fail-closed shutdown is enforced on-device by firmware (`cg_tec_control.c` hardware pin isolation).

---

## 2. Hard Stop / Precondition Gate

Physical Controller B enablement on hardware remains **BLOCKED** until all of the following conditions are met:
1. Operator bench execution of unenergized checklist (`pre-run-safety-checklist.json`).
2. Gate G4 formal signoff.
3. Member B delivers frozen model candidate.
4. Member D delivers frozen policy candidate.
5. Fuse installation verified (15 A fuse is currently removed; PSU is powered OFF; `CG_TEC_OUTPUT_STAGE_ENABLED = 0`).
