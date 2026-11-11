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

A's older `evidence/A/W09/healthy-ranges.json` explicitly marks its 957 rows
`UNKNOWN`; that statement remains true for that export. Current main also
contains a newer normalized handoff with qualified electrical fields, four
accepted S1 runs, five accepted S2 windows and real cooling captures. The
cooling captures are explicitly `NOT_SCENARIO_QUALIFIED`, A-W08-03 and
A-W09-04 remain `NOT_RUN`, and the accepted S1/S2 windows do not constitute a
frozen Controller A command/applied-state benchmark. The source gap has
improved, but physical verification success is still not claimed.

The exact A source is PR #91 (`feat/a-s1-s2-source-evidence`, head
`63982e9592e0687099afb53fa1e4422f57761d74`). The ref is fetched locally as
`origin/pr/91-a-s1-s2`. `a-pr91-s1-s2-source-binding.json` verifies the raw
publication hashes and records four PASS S1 windows (2,401 frames) plus four
PASS S2 door windows (1,200 frames). The S1 classification is passive
thermal/electrical-idle, not cooling or energy evidence.

A's newer PR #95 (`fix/a-main-acceptance-integrity`, head `815387d`) adds one
genuine read-only passive S1 run from 2026-11-09: 600 frames, 599.003 s,
thermal valid rate 0.99833, electrical valid rate 0.99667, zero commands and
zero bytes written. D copied the hash-pinned package into
`evidence/A/SOURCES/20261109/s1/` and verifies it with
`a-pr95-supplementary-s1-binding.json`. Per PR #95, it is supplementary and is
**not admitted** into the frozen 18-run dataset; it is not cooling-response
evidence and is not counted as extra independent windows.

`a-w09-source-crosscheck.json` is a reproducible historical negative control
over A's older row-validity CSV and S1 index. Rebuild it with `python
control/scripts/a_w09_crosscheck.py evidence/A/W09/exports/CG-S1-H8C-600S.row-validity.csv
evidence/A/W09/s1-run-index.json evidence/D/W09/a-w09-source-crosscheck.json`.
Do not use that historical `UNKNOWN` result as a current inventory of all main
evidence; see `../main-update-assessment-20261109.md` for the new handoff and
its pinned hashes.
