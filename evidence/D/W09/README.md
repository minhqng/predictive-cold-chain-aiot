# Member D W09 — Cooling-response verification candidate

**Status:** pure verification tracker and synthetic tests; physical envelope qualification remains OPEN.

`control/src/coldguard_control/verification.py` separates command ACK, electrical observation and thermal response. `control/tests/test_verification.py` exercises the state machine. `verification-envelope-candidate-v0.json` contains **synthetic test values** (`source: test`), not Member A's frozen limits. A candidate or unresolved envelope must return `UNKNOWN`; `VERIFIED` requires qualified evidence.

| Item | Evidence now | Remaining gate |
|---|---|---|
| D-W09-01 OFF envelope | Field and gate represented | A must qualify OFF-current evidence and resolve exceptions. |
| D-W09-02 healthy ON envelope | Field and gate represented | A must qualify current/power and response timing across independent runs. |
| D-W09-03/04 HEALTHY_RESPONSE vs UNKNOWN | Pure state logic | Join real applied action with qualified electrical and thermal windows. |
| D-W09-05 timer | Staged electrical/thermal windows in tracker | Freeze timing from A's characterized response, then test against real traces. |

A's `evidence/A/W09/healthy-ranges.json` explicitly marks all 957 electrical rows `UNKNOWN` because source status fields are empty. Its active range is unqualified; it cannot establish a healthy physical response. Source: Doc 05D §41, Doc 01 physical correctness contract. No physical verification success is claimed.
