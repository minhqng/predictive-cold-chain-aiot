# ColdGuard Member A — W19 Final Paired Campaign Wave 1 Runbook

**Requirement Authority:** `docs/05A §28` (`A-W19-01` through `A-W19-04`), `docs/03 §34-36`  
**Status:** **SOFTWARE_READY / PENDING_OPERATOR_RUN**

---

## 1. Execution Protocol

1. **A-W19-01 (Pre-Run Verification):**
   - Verify hardware config ID (`BENCH_HW_V2`), state-based initial thermal equilibrium, door closed reed state, PZEM telemetry validity, and local storage readiness.
   - Confirm explicit controller identity (`CONTROLLER_A` vs `CONTROLLER_B`).
2. **A-W19-02 (Physical Invariants & Pair Randomization):**
   - Follow randomized run pair order (A then B, or B then A per `docs/03 §36`).
   - Maintain physical invariants between paired runs: identical scenario protocol, hardware setup, disturbance duration, and sensor positions.
   - Enforce pair identity linkage (`pair_id`, `run_a_id`, `run_b_id`).
3. **A-W19-03 (All-Attempt Invalidation & Retention):**
   - If an invalidating condition occurs (sensor dropout, PZEM timeout, door ajar at start, out-of-band initial state), log the attempt with structured taxonomy reason codes.
   - **Crucial Rule:** Never silently discard or delete an invalid attempt. Every physical run attempt must be preserved in the campaign attempt log (`attempt_seq`, `session_id`, `pair_id`, `is_valid_attempt`, `reason_code`).
4. **A-W19-04 (State-Based Thermal Reset):**
   - Between paired runs, reset is governed by physical state criteria under `docs/03 §34`, **not** elapsed clock time or unsupported +/- 0.5 °C defaults.
   - State reset requires:
     - Chamber $T_{\text{mean}}$ within frozen start band $[T_{\text{min}}, T_{\text{max}}]$.
     - Thermal gradient below frozen maximum $|dT/dt| \le \text{grad}_{\text{max}}$.
     - Door closed and verified.
     - Cooling state known (PWM=0 cooldown).
     - PZEM and sensor health flags valid.
   - Tolerances must be formally frozen from pilot repeatability before campaign execution.
