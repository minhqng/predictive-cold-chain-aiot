# ColdGuard Member A — W21 SAFE_LOCAL Final Test Support

**Requirement Authority:** `docs/05A §30: A-W21-04`  
**Audience:** Joint Member A / C / D  
**Status:** **READY_FOR_INTEGRATION**

---

## 1. Scope & Verification

When communication with backend/cloud drops:
1. Member C flags broker disconnect.
2. Member D activates `SAFE_LOCAL` policy.
3. Member A firmware guarantees local telemetry generation continues via UART, local safety trip limits remain operational in hardware, and no unbounded actuator commands are accepted.
