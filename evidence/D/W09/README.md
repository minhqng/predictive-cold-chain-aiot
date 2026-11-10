# Member D W09 — Cooling-response verification candidate

**Status:** pure verification tracker and synthetic tests; physical envelope qualification remains OPEN.

`control/src/coldguard_control/verification.py` separates command ACK, electrical observation and thermal response. `control/tests/test_verification.py` exercises the state machine. `verification-envelope-candidate-v0.json` contains **synthetic test values** (`source: test`), not Member A's frozen limits. A candidate or unresolved envelope must return `UNKNOWN`; `VERIFIED` requires qualified evidence.

Review correction: a physical health verdict also requires observed applied state (separate from requested action), valid current and power in a qualified ON envelope, and a quality-tagged thermal baseline plus follow-up. A bare constructor temperature is only a replay hint. Timeout fault classifications require explicit evidence-age bounds; gaps at the deadline return `UNKNOWN`.

| Item | Evidence now | Remaining gate |
|---|---|---|
| D-W09-01 OFF envelope | Field and gate represented | A must qualify OFF-current evidence and resolve exceptions. |
| D-W09-02 healthy ON envelope | Field and gate represented | A must qualify current/power and response timing across independent runs. |
| D-W09-03/04 HEALTHY_RESPONSE vs UNKNOWN | Pure state logic and negative tests for missing applied state, power, baseline and deadline coverage | Join real applied-action feedback with qualified electrical and thermal windows. |
| D-W09-05 timer | Staged electrical/thermal windows in tracker | Freeze timing from A's characterized response, then test against real traces. |

A's `evidence/A/W09/healthy-ranges.json` explicitly marks all 957 electrical rows `UNKNOWN` because source status fields are empty. Its active range is unqualified; it cannot establish a healthy physical response. Source: Doc 05D §41, Doc 01 physical correctness contract. No physical verification success is claimed.

`a-w09-source-crosscheck.json` is a reproducible read-only negative control over A's row-validity CSV and S1 run index. Rebuild it with `python control/scripts/a_w09_crosscheck.py evidence/A/W09/exports/CG-S1-H8C-600S.row-validity.csv evidence/A/W09/s1-run-index.json evidence/D/W09/a-w09-source-crosscheck.json`. The output pins both source SHA-256 values, row count, quality counts and eligible run IDs. It reports `UNKNOWN`; it does not qualify the ON/OFF envelope.
