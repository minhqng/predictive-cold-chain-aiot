# Member D W08 — SAFE_LOCAL and G2 readiness

**Status:** deterministic session logic and unit tests only; real broker/backend loss and G2 report remain OPEN.

`control/src/coldguard_control/safe_local.py` models entry, local operation and exit. `control/tests/test_safe_local_session.py` uses synthetic sequences to check local decisions and prevent immediate trust restoration on reconnect. It does not remove a broker or operate a device.

| Item | Evidence now | Remaining gate |
|---|---|---|
| D-W08-01 disconnect trigger | Pure timing/entry logic | A/C transport event and clock semantics. |
| D-W08-02 real SAFE_LOCAL | Synthetic test only | A/C/D supervised broker/backend removal with valid local sensor and actuator trace. |
| D-W08-03 local-state-only proof | Core has no DB/prediction/frontend I/O | Device-level proof that protection continues offline. |
| D-W08-04 reconnect | Unit gate requires reconciled trust | Real reconnect, stale desired-command and state-sync test. |
| D-W08-05 G2 report | This readiness inventory | Controller A stability and physical SAFE_LOCAL evidence before signoff. |

A's `evidence/A/W08/handoff.md` marks SAFE_LOCAL support a team dependency and reports no transport/wall-clock/fan/interlock observation. Therefore G2 is **NOT SIGNED OFF**. Source: Doc 05D §40 and Doc 02 SAFE_LOCAL requirements.
