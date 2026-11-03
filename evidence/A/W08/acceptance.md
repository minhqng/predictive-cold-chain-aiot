# A-W08 acceptance

Slice: W08 Gate A physical characterization + SAFE_LOCAL support · Branch
`feat/a-w08-envelope-gate-a` · Host analysis only (no firmware change, no
build, no port, no energization).

Gate A: **NOT CLOSED**.
PHYSICAL MEASUREMENT TAKEN BY THIS DOSSIER: **NONE**.

W08 is **not** a GREEN week. It is delivered as **observed-envelope-complete,
physically open**: the analyzer exists, runs against authentic captures, and
names every frame and every input it cannot close. Where a capture cannot answer
the question, this file records the gap instead of a number.

## 1. Requirement matrix (docs/05A section 17)

| ID | Canonical ask | Status | Evidence | What is still missing |
|---|---|---|---|---|
| **A-W08-01** | Safe operating envelope derived from W4–W7: allowed action state, healthy current range, healthy power range, OFF current envelope, thermal response window, stop conditions; do not extrapolate | **REAL_DATA_ANALYZED** (observed) — **not frozen** | `operating-envelope-v1.yaml`, `envelope-by-duty.csv`, `source-summary.csv`, `holdover-frames.csv`, `duty-zero-current-frames.csv`, `electrical-status-coverage.csv` | one duty level committed (999 ‰); the 20–100 % ladder is local-bench only; the two wiring regimes are not poolable; a frozen envelope needs the resolved limits (D) and the ampacity basis below |
| **A-W08-02** | Fuse finalization among 10 / 15 / 20 A with rationale; if none is defensibly suitable, the gate fails and no one improvises | **BLOCKED_HARDWARE** (+ **TEAM_DEPENDENCY** for the conductor deviation) | `fuse-selection.md` — verdict **NO_FREEZE**; observed peak 9.99 A committed (9.35 A H8-A, 9.16 A H7-100 %, declared) | photographed fuse marking (installed + spare) — the 15 A is **operator-reported only** and nothing is legible on the installed body, and a shop listing or catalogue entry is not evidence about installed hardware — plus the conductor's insulation class / run length / bundling and an ampacity table. Conductor record corrected 2026-11-02: the old "1.75 mm²" was a **unit error** for a **1.75 mm copper core diameter**, i.e. ≈2.405 mm² **if the core is round solid** — a ~4 % area gap to `2 × 2.5 mm²`, not ~30 %, and inside the FDD2-250 1.5–2.5 mm² termination rating. The assumption is stated, not proven, so no nominal 2.5 mm² compliance is claimed and `evidence/A/W01/bom-audit.csv` HW-19 stays `UNVERIFIED` |
| **A-W08-03** | Long cooling test to observe whether response stays stable, performance collapses, protection triggers, terminals/IBT-2 behave abnormally | **REAL_DATA_ANALYZED** for three of the four bullets; **NEED_USER_ACTION** for the fourth | `thermal-sustainability.csv` — H8-B/C/D/E at 420/600/900/1800 s all plateau with TEC_HOT_SIDE max **37.688 °C** and final-minute drift within 0.032 K; the committed 600 s box run reached **39.938 °C** and was still creeping +0.176 K/min; H8-A at 178 s was still warming +1.457 K/min; `fault_bits=0` and `off_verify=PASS` in the recorded sessions | nothing in any frame measures the terminals, the IBT-2 case or the cable: that is an operator, touch-free observation during a supervised long run; and no continuous rating may be claimed, so the 55 °C margin is a distance to a provisional number |
| **A-W08-04** | SAFE_LOCAL integration support with D: remove broker/backend, verify local Controller A input sensors remain available, verify local output behaviour | **TEAM_DEPENDENCY** | `safe-local-physical-inputs.csv` (SL-01…SL-14) and `Gate-A-report.md` §4 | the delivered firmware has no transport (`cloud=NOT_PROVISIONED`), no wall clock, no fan observation (`fan_readback=NOT_ELECTRONICALLY_VERIFIED`), no interlock (`interlock_state=NOT_INSTALLED`) — and the SAFE_LOCAL mode, its entry/exit rule and its limits belong to Member D |
| **A-W08-05** | Gate A package indexing all H0–H7 artifacts | **IMPLEMENTED / HOST_VERIFIED** | `Gate-A-report.md`, `gate-a-artifact-index.csv` — 23 curated entries resolved against this checkout, 20 present, 3 recorded absent | `evidence/A/W07/**` is not in this checkout (it ships on `feat/a-w07-plant-repeatability`, PR #18); the H7/H8 raw originals are not committed here; W04's own deviation rows stay open |
| Deliverable | `operating-envelope-v1.yaml` | REAL_DATA_ANALYZED | generated, `--check` reproduces it byte-for-byte | — |
| Deliverable | `fuse-selection.md` | BLOCKED_HARDWARE | generated | — |
| Deliverable | `thermal-sustainability.csv` | REAL_DATA_ANALYZED | generated | — |
| Deliverable | `Gate-A-report.md` | HOST_VERIFIED | generated | — |

## 2. Pass-criteria walk (docs/05A section 17)

| Criterion | Result | Basis |
|---|---|---|
| safe physical envelope known | **NOT MET** | the *observed* envelope is known and published; "safe" additionally needs the conductor ampacity basis, the fuse decision and the resolved limits — none exists |
| repeatable enough plant | **NOT MET HERE** | repeatability is W07's question and its evidence is not in this checkout; one capture per condition cannot answer it |
| fuse selected | **NOT MET** | **NO_FREEZE**, deliberately: `docs/05A` says do not improvise silently |
| no unresolved high-current anomaly | **NOT PRE-JUDGED — CANDIDATE OPEN IN W15** | `fault_bits=0` in all 957 committed frames; steady OFF current never above **0.02 A** (meter LSB floor) against the bench image's simulated 0.200 A gate; the duty-0 frames above the floor are the **2** PZEM register-latency frames, individually listed and excluded, and W15 deliberately leaves them open between the register-holdover reading and the canonical **CONTROL_ELECTRICAL_ANOMALY** class (docs/01 §22.4/§23.4, high severity). This row does not decide that safety classification, and no frame measures terminals, IBT-2 case or cable temperature, so it is not a claim about hot hardware either |
| SAFE_LOCAL physically possible | **NOT DEMONSTRATED** | the inputs exist (SL-01…SL-08), the mode does not; four of the twelve prerequisites are hardware or Member D work |

## 3. Findings a reviewer should not have to dig for

1. **The committed 600 s CSV publishes unqualified electrical values.**
   `voltage_status`/`current_status` are empty in **957/957** rows;
   `power_status`, `energy_status` and `door_status` are not columns at all. The
   same session's raw line does carry `voltage_v_status=OK`,
   `current_a_status=OK`, `power_w_status=OK` with ages **636–666 ms**. So the
   CSV lost the validity, not the device. Every figure derived from it is
   labelled `electrical_status_recorded: false`.
2. **`energy_wh` is unqualified by construction**: no validity token exists on
   the bench wire in any frame, and the counter is 1 Wh quantised.
3. **The register-latency rule is now explicit code, not folklore.** The frame
   at `device_ms=826894` (`seq=827`, state COOLDOWN, requested and applied duty
   0) reports **7.15 A / 84.2 W / 122 Wh** and is byte-identical to the two
   preceding driven frames on **every measured field** — voltage, current,
   power, energy and T1/T2/T3/T4 — with only the BME air/RH/pressure readings
   and the duty/state bookkeeping changed. It is named
   `OUTPUTS_OFF_REGISTER`, excluded from both the drive envelope and the OFF
   envelope, and listed row-by-row. It is never averaged. **What the record now
   also carries:** the applied duty stayed 0 across the following frames while the
   **PZEM-reported** current decayed **7.15 → 0.56 → 0.02 → 0.0 A**, reaching zero
   at `device_ms=829894` (the same sequence is recorded as
   `operator_confirmed_zero_duty_current_sequence_a` in
   `evidence/A/W07/reset-criterion-evaluation.json` on the W07 branch, with the
   frames after the suspect). That decay supports register/transition lag and
   weakens sustained-energization, but it is the meter's own trace with **no
   independent instrument behind it**: a measured value and a verified physical
   current are different claims, and the docs/01 §22.4/§23.4
   `CONTROL_ELECTRICAL_ANOMALY` classification stays open.
4. **A first-post-OFF holdover is not always byte-identical.** In H8-B/C/E the
   same pattern is one LSB off (7.13 A where the previous driven frame said
   7.12 A), which a pure byte-identity rule would have silently classified as
   "steady OFF with 7.13 A". The classifier therefore keys on *one frame period
   after the last driven frame with current above the steady floor*, and keeps
   the byte-identity note when it applies. This changed the published H8-B OFF
   row from `steady_max 7.13 A` to `steady_max 0.00 A` with one excluded latency
   frame.
5. **V×I is internally consistent everywhere it was checked.** Worst absolute
   deviation **0.099 W** over 957 frames against a
   **0.18 W** register-quantisation tolerance; aggregate mean power 85.3015 W
   versus mean-V × mean-I 85.3565 W (−0.064 %). The H8-A reproduction (mean
   86.3933 W, mean-V×mean-I 86.445 W) matches the endurance report's own
   arithmetic check, which is the cross-validation this slice needed.
6. **Energy is consistent to its quantum.** 108 → 122 Wh (Δ14 Wh) against a
   14.219 Wh trapezoidal integral of reported power; monotonic, no decreases,
   15 distinct counter values in 957 frames.
7. **The driver enable state is commanded but not observed.**
   `enable_readback=ren:0,len:0` in every frame including all 600 driven ones,
   where `ren_command=1`. Output verification currently rests on current alone.
8. **The hot side plateaus at 100 % duty, and that is the strongest thing this
   slice can say about sustainability**: 37.688 °C in B (420 s), C (600 s),
   D (900 s) and E (1800 s) — the same ceiling at four durations — while the
   2026-11-01 box run (probes repositioned in the box) reached 39.938 °C and was
   still rising slowly. No collapse, no protection trigger, no fault in any of
   them. None of it establishes a rating.

## 4. Physical actions still owed (W08 half of the queue)

| Queue | Requirement | Session | Status |
|---|---|---|---|
| OQ-W08-1 | A-W08-02 | cold inspection: photograph the fuse body (installed + spare) and the cable marking, record insulation class, length, routing | NEED_USER_ACTION |
| OQ-W08-2 | A-W08-03 | one supervised ≥ 1800 s run at 100 % duty with touch-free terminal / IBT-2 / cable temperatures at 300 s checkpoints | NEED_USER_ACTION |
| OQ-W08-3 | A-W08-04 | SAFE_LOCAL session (broker/backend removed and restored) — needs D's mode and C's transport first | TEAM_DEPENDENCY |
| OQ-W08-4 | A-W08-01/05 | commit (hash-pin) the local H7/H8 captures so a reviewer can reproduce the ladder rows | NEED_USER_ACTION |

Merged session plan and the W15 half: `evidence/A/W15/acceptance.md` §4 (on the W15
branch `feat/a-w15-pzem-integrity`, PR #26 — not present in this checkout) and
`gate-a-operator-queue.csv`.

**OQ-W08-1 is necessary, not sufficient.** A short unpowered inspection produces the
conductor and fuse markings; on its own it clears none of the energized-session gates.
Those also require the duty-0-with-current frame to be classified (the open
`CONTROL_ELECTRICAL_ANOMALY` candidate, docs/01 §22.4/§23.4 — a supervised call, not a
host-tool call) and Member D's thresholds to exist. No photo answers either of them.

## 5. Items this slice does not own

* `docs/00`…`docs/06` (referenced, not edited). `.gitattributes` is owned by the
  coordinator, and this slice adds exactly two additive rules to it, one per week's
  commit: `evidence/A/W08/** -text` and `evidence/A/W15/** -text`, because
  `* text=auto eol=lf` with `core.autocrlf=true` would rewrite the pinned bytes.
* `firmware/main/**`: no firmware changed, so no ESP-IDF build was run or needed.
* The W04 deviation registers (`CR-A-W04-01/02`, HW-19) — referenced, not edited.
* The W15 PZEM analyzer duplicate: `firmware/tools/cg_pzem_quality.py` and
  `tests/test_cg_pzem_quality.py` appeared in this worktree from a concurrent
  worker. W08's own generator imports `cg_w15_pzem_quality.py`, so that is the
  keeper; the duplicate was deleted and its still-load-bearing rules (zero versus
  absent, device-clock semantics, the duty-0 ON/OFF anomaly, undocumented bitmasks,
  the physical-claim guard) now live in the keeper and are tested by
  `firmware/tools/tests/test_cg_w15_pzem_quality.py`.

## 6. Verification record

| Check | Result |
|---|---|
| `py firmware/tools/run_all_checks_w08.py` | see `README.md` §3; all layers PASS |
| `py -m unittest discover -s tests -t tests` | PASS — the W08/W15 additions are listed in `firmware/tools/tests/test_cg_w08_*.py` and `test_cg_w15_*.py` |
| `py evidence/A/W08/build_w08_artifacts.py --check` | 12 artifacts reproduce byte-for-byte |
| `py evidence/A/W08/validate_w08.py` | PASS: pins verified, spine re-derived from the committed CSV, no physical claim present |
| `--verify-bench` (local tree present) | declaration matches a fresh derivation, 18 sessions |
| ESP-IDF build | not run: this slice changes no firmware |

## 7. Status vocabulary used here

IMPLEMENTED · HOST_VERIFIED · REAL_DATA_ANALYZED · NEED_USER_ACTION ·
TEAM_DEPENDENCY · BLOCKED_HARDWARE. `PHYSICALLY_VERIFIED` is never assigned by
this slice: no host artifact in this dossier may claim it, and
`validate_w08.py` fails if one ever appears.
