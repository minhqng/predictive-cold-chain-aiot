# ColdGuard Member A — W19 Final Paired Campaign Wave 1 Runbook

**Requirement Authority:** `docs/05A §28` (`A-W19-01` through `A-W19-04`)  
**Status:** **SOFTWARE_READY / PENDING_OPERATOR_RUN**

---

## 1. Execution Protocol

1. **A-W19-01 (Pre-Run Verification):** Verify hardware config ID, baseline chamber temp, door closed, PZEM status OK, and storage ready before initializing each run.
2. **A-W19-02 (Physical Invariants):** Follow the randomized run sequence provided in the campaign plan. Never modify door disturbance duration, sensor placement, or physical hardware between paired runs.
3. **A-W19-03 (Attempt Invalidation):** If a sensor drops, PZEM communication times out, or the door is left open prematurely, log the run with standard reason codes. Never discard failed attempts silently.
4. **A-W19-04 (State-Based Reset):** Between paired runs, allow the chamber to naturally return to equilibrium within +/- 0.5 °C of ambient before initiating the next run.
