# A-W13 acceptance

Slice: W13 plant timing + intervention-physics package · Branch
`feat/a-w12-physical-readiness` · Owner: Member A
Hardware touched: **NO** · Flashed: **NO** · Serial opened: **NO**

W13 is **not** a GREEN week. Two of its four asks are computable from committed
traces and two are named data gaps; the tool is written so a gap can never
silently produce a number.

## 1. Requirement matrix (docs/05A §22)

| ID | Canonical ask | Status | Value / evidence |
|---|---|---|---|
| **A-W13-01** | Command→electrical delay: median, P95, max useful observed | **REAL_DATA_ANALYZED (host), single observation** | Committed H6 trace `evidence/A/W04/h6/first-tec-trace.csv`. **Onset = the first post-command SAMPLE at or above the 0.1 A threshold** — the rule never force-drops the first sample. The 5.704 s SAMPLE (0.000 A) is below threshold and is annotated stale only because its own sub-poll `elapsed_ms` matches the documented pre-ramp reading (`evidence/A/W04/h6/41-h6-run-analysis.md:28`); electrical onset is the 0.970 A SAMPLE at 6.329 s ⇒ **delay 1.094 s**. median = P95 = max = 1.094 s with **n=1** — a single committed trace is *not* yet a distribution. **Clock:** the bracket column is the **device log uptime** (seconds since boot in the console line), the anchor is the device's `START accepted` line, and the operator keystroke→accept transport/echo (~0.156 s) is **excluded** from this interval. **Quantization:** onset is the first 1 Hz poll at/above threshold, so the true delay is **1.094 s ± 1 s** (one poll period). Boot guard: an interval that crosses a `boot_id` change is refused (the H6 trace carries no boot column, so continuity there is UNVERIFIED). |
| **A-W13-02** | Command→thermal response: define method with B/D, measure across valid step runs | **REAL_DATA_ANALYZED (host), A-side candidate method** | Committed cooling capture `evidence/A/W04/tec-cooling-response-600s.csv`: applied-on (first duty-999 frame) → first 1 °C chamber-air deviation = **0.85 min** (51 s). Representation `mean(T1,T3,T4)` (chamber air; hot side excluded), window = driven block, method = raw first-crossing, no filter — declared per docs/01 §20.5. Anchored on the applied-on frame inside the capture, not a host command. |
| **A-W13-03** | Door→critical time: distribution under the frozen candidate critical definition | **NOT COMPUTABLE — BLOCKED_HARDWARE** | `door-critical.csv` / `plant-timing-report.json.door_to_critical`: status `NOT_COMPUTABLE`, `value_s: null`, `number_emitted: false`. No door-open event exists in any committed capture (door_open ∈ {0, UNKNOWN}; door_polarity never a confirmed open). A supervised S2 door-disturbance run under the frozen critical definition is required. |
| **A-W13-04** | Passive/cooling time-constant proxies (empirical summaries only) | **REAL_DATA_ANALYZED (host), proxies with limitations** | cooling tau proxy **174 s** (whole-window slope −0.8548 °C/min, the W13 tool's **own** OLS figure on the trio mean — the earlier "matching the documented −0.854771" citation pointed at `evidence/A/W07/**`, which is not on this branch, so it is re-anchored to this computed value); recovery tau proxy **86 s** measured over the **130 s** post-`STAGE_DEADLINE` window (rise **5.333 °C**), i.e. recovery after the action per docs/01 §20.6; passive pre-drive drift **0.104 °C** over **3.63 min** (reported as a drift rate, no tau asserted — a flat signal has no first-order swing). Every proxy takes the trio mean only over frames whose probe tokens are valid (all 957 are `OK` today) and is refused if the window crosses a `boot_id` change. |

## 2. Onset rule and clock (stated in code and output)

The command→electrical onset is **the first post-command SAMPLE at or above the
current threshold**; the rule does not unconditionally drop the first sample. A
sample is annotated as a stale pre-run PZEM register read only when **the record
itself** carries that evidence (a sub-poll `elapsed_ms`, the pre-ramp reading
documented at `evidence/A/W04/h6/41-h6-run-analysis.md:28`); such a sample is
below threshold in practice, so the annotation never shifts a genuine onset.
On the committed H6 trace the first sample is 0.000 A, so the naive threshold
crossing and the annotated rule give the **identical 1.094 s** — the exclusion is
not what makes the number right, the threshold is. The interval is measured on the
**device log uptime** clock from the device `START accepted` line; the operator
keystroke→accept echo (~0.156 s) is excluded, and the 1 Hz poll quantises onset
to **±1 s**. The rule text ships in every artifact (`latency_exclusion_rule`); the
prior citation to a non-existent `H8_CURRENT_PATH_AND_SHUTDOWN_ANALYSIS` doc is
replaced by the committed `41-h6-run-analysis.md:28`.

## 3. Data-gap register (identifiable, in `data-gap-register.csv`)

| Gap | Ask | Why |
|---|---|---|
| `GAP-DOOR-CRITICAL` | A-W13-03 | no door-open event in any committed capture |
| `GAP-NETWORK-COMMAND-LATENCY` | backend→device latency | production firmware has no network command path |
| `GAP-COMMAND-ELECTRICAL-DISTRIBUTION` | A-W13-01 median/P95 | one committed console trace = one event; H7 run logs live in a sibling commissioning worktree (read-only), not in this branch |

## 4. What could NOT be computed, and why

* **Door→critical distribution** — no recorded door-open disturbance; the tool
  refuses and the validator enforces refusal. Not estimated.
* **Backend→device latency** — no network command path exists; only the console
  START→electrical hop is observable. Not estimated.
* **A robust command→electrical distribution** — only one committed console trace;
  more clean START traces (converted to the H6 schema) are needed before median/P95
  mean anything. The n=1 caveat ships in the output.

## 5. OPERATOR_ACTION_QUEUE (W13)

| # | Requirement | Exact physical action | Existing valid evidence | Safety prerequisites | Expected capture | Downstream unlock |
|---|---|---|---|---|---|---|
| 1 | A-W13-01 distribution | Repeat the console START→ON→OFF step 3–5 times on the *same* installed image, capturing an H6-schema trace each time | 1 committed H6 trace (1.094 s, n=1) | supervised bench; stop on zero/abnormal current; no flash needed (installed image already physical_output-capable) | 3+ `first-tec-trace`-style CSVs | turns median/P95/max from a single observation into a distribution |
| 2 | A-W13-03 door→critical | One supervised S2 door-open disturbance run under the frozen candidate critical definition (Member D supplies the definition) | none (no door event exists) | supervised bench; door opened by operator only; no probe/wiring change; bounded duration | a cooling capture with `door_open=1` and a confirmed polarity | lets B/D get the door→critical distribution they need for horizon + safety margin |
| 3 | A-W13-04 tau refinement | Optional: extend the post-deadline recovery window and add a longer steady-state cooling run so tau reaches true steady state | driven 600 s + 130 s recovery already fit | supervised bench | longer cooling/recovery capture | replaces the biased-low tau proxies with steady-state-valid fits |

Item 2 is the only path to a door→critical number and is BLOCKED_HARDWARE until
performed; item 3 is optional and does not gate A-W13-01/02. Items 1 and 3 can
share one supervised session only if the same installed image is used; the door
run (item 2) must be a separate, distinctly labelled S2 session and must not be
pooled with the characterization runs (W12 dataset-validity rule).
