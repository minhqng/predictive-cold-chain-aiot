# A-W13 — Plant timing and intervention-physics package (Member A)

Week: **W13** · Branch: `feat/a-w12-physical-readiness` · Owner: Member A
Status: **HOST TIMING ANALYSIS · NO HARDWARE · NO PHYSICAL VERIFICATION · DOOR→CRITICAL NOT COMPUTABLE**

This dossier quantifies the physical delays Members B and D need for prediction
horizon and action-in-window, computed from committed console traces and cooling
captures only. It touches no hardware. Methods follow `docs/01` §20.5 (a slope
names its representation, window and fit method) and §20.6 (recovery is measured
only *after* a defined action reference).

W13 is **not** a GREEN week.

## 1. What W13 delivered

| Requirement | Delivered | Where |
|---|---|---|
| **A-W13-01** command→electrical delay | Measured from the committed H6 console trace with an explicit PZEM register-latency exclusion rule stated in code and output | `cg_w13_timing.py`, `response-delay.csv` |
| **A-W13-02** command→thermal response | Applied-on → first named thermal deviation, method and representation declared | same |
| **A-W13-03** door→critical time | **Refuses to emit a number** — no door-open event exists in any committed capture | `door-critical.csv`, `plant-timing-report.json` |
| **A-W13-04** passive/cooling time-constant proxies | First-order 63.2%-of-swing empirical summaries; recovery measured after the action | `plant-timing-report.json` |

## 2. Files

| File | What it is |
|---|---|
| `README.md` | this file |
| `acceptance.md` | requirement-by-requirement status with the gaps named |
| `plant-timing-report.json` | the full timing report (A-W13-01/02/03/04 + gap register) |
| `response-delay.csv` | per-run command→electrical and command→thermal delays + tau proxies |
| `door-critical.csv` | A-W13-03 as an honest NOT_COMPUTABLE row (never a number) |
| `data-gap-register.csv` | the named gaps that block timing claims |
| `build_w13_artifacts.py` | regenerates every artifact from the committed captures; `--check` compares byte-for-byte |
| `validate_w13.py` | SHA256 pins, LF-only, and fails on any door-timing number or a physical PASS |
| `SHA256SUMS.txt` | byte pins (LF-only), produced by `build_w13_artifacts.py --pins` |
| `handoff.md` | this week's part of the docs/05A section 5 / 6.1-6.3 handover: what B, C and D may use from W13, and what only a session can supply |

## 3. Reproduce

```bash
py firmware/tools/cg_w13_timing.py                     # run on the committed H6 trace + cooling capture
py firmware/tools/run_all_checks_w13.py                # full W13 check chain
py evidence/A/W13/build_w13_artifacts.py --check       # artifacts reproduce byte-for-byte
py evidence/A/W13/validate_w13.py                      # hash pins + door-number honesty
```

## 4. Limits of this dossier

* **The command is a local console START, not a network command.** Production
  firmware has no network command path (the output stage is compiled out), so
  **backend→device latency is NOT COMPUTABLE** and is recorded as a named gap,
  never estimated.
* **Door→critical has no data.** The cooling capture reports `door_open` only as
  `0`/`UNKNOWN` and never a confirmed open; no door-disturbance trajectory was
  recorded. The tool returns `NOT_COMPUTABLE` and the validator fails if a
  numeric door time ever appears.
* **Time constants are proxies.** They use the observed endpoints as the swing,
  so a run that has not reached steady state under-estimates the true tau; the
  limitation is attached to every fit rather than corrected with an invented
  asymptote.
