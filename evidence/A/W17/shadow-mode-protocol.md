# ColdGuard Member A — W17 Shadow Mode Protocol & Safeguards

**Requirement Authority:** `docs/05A §26` (`A-W17-01` through `A-W17-04`)  
**Status:** **SOFTWARE_READY / PENDING_OPERATOR_RUN**

---

## 1. Operating Rules

1. **A-W17-01 (Authority Preservation):** Controller A (local fallback/baseline) retains 100% physical authority over the TEC and fan. Controller B/D decisions run purely in shadow observation mode.
2. **A-W17-02 (Leak Prevention):** The applied actuator PWM duty must strictly reflect Controller A logic or fail-closed safe state (0 duty). Any execution of a predictive action is treated as a critical safety violation.
3. **A-W17-03 (Channel Alignment):** Real live telemetry channels are verified against Member B's modeling contracts before physical runs are started.
4. **A-W17-04 (Plant Anomaly Monitoring):** Live rate-of-change checks flag unexpected thermal drift (>0.5 °C/s) or sensor drops, immediately invalidating the candidate run.
