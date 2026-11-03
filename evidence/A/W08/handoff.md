# W08 handoff — electrical envelope (Member A input only)

Week: **A-W08-01…A-W08-05** · Branch `feat/a-w08-envelope-gate-a` · Dossier
`evidence/A/W08/` · Host analysis only: no firmware change, no build, no port, no
energization. Nothing in this file authorises energising the branch; each powered
session needs the operator's explicit case-by-case GO.

Source contract for this file: `evidence/A/HANDOFF/` as published on the **W07**
branch `feat/a-w07-plant-repeatability` — those paths are not present in this
checkout (`coverage-matrix.md` A-W08 rows, `a-to-bcd-fields.md` §6.3,
`supervised-session-plan.md` §1-§4). Only W08's own rows are carried here; that
directory is read-only and nothing is copied into it.

## 1. What W08 delivers, requirement by requirement

| ID | Canonical ask | State today | Where | What is still missing |
|---|---|---|---|---|
| A-W08-01 | Safe operating envelope from W4–W7 | observed, **NOT FROZEN** | `operating-envelope-v1.yaml`, `envelope-by-duty.csv`, `source-summary.csv`, `holdover-frames.csv`, `duty-zero-current-frames.csv` | one duty level committed (999 ‰); the 20–100 % ladder is `LOCAL_BENCH` only; the two wiring regimes are not poolable; an envelope is an observation, not a rating |
| A-W08-02 | Fuse finalization 10/15/20 A with rationale | **BLOCKED_HARDWARE** (+ TEAM_DEPENDENCY) | `fuse-selection.md`, verdict **NO_FREEZE** | the installed conductor's ampacity basis and a photographed fuse body marking — see §3 |
| A-W08-03 | Hot-side sustainability over a long run | REAL_DATA_ANALYZED for three of four bullets; **NEED_USER_ACTION** for the fourth | `thermal-sustainability.csv` | no recorded frame measures the terminals, the IBT-2 case or the cable; no continuous TEC rating exists, so the margin to the provisional 55 °C ceiling is not headroom |
| A-W08-04 | SAFE_LOCAL support with Member D | **TEAM_DEPENDENCY** | `safe-local-physical-inputs.csv` (SL-01…SL-14), `Gate-A-report.md` §4 | the mode, its entry/exit rule and its limits are Member D's; there is no transport, no wall clock, no fan observation and no interlock |
| A-W08-05 | Gate A package | delivered, verdict **GATE A NOT CLOSED** | `Gate-A-report.md`, `gate-a-artifact-index.csv`, `gate-a-operator-queue.csv` | the pass criteria that need hardware or another member stay open; the high-current row is deliberately **NOT PRE-JUDGED** — see §4 |

## 2. §6.3 fields this week supplies to Member D

| Field | State | What D can rely on, and the limit |
|---|---|---|
| OFF electrical envelope | **AVAILABLE with one unresolved exception** | 355 steady duty-0 frames with current never above **0.02 A** (one PZEM LSB) plus 2 duty-0 frames above that floor, named individually. The exception is §4: this is a measured value, not a verified unenergized state |
| Healthy ON current / power range | **ONE SESSION, UNQUALIFIED** | 600 driven frames in one 600 s block. Mean current 7.2247 A over all 600 (7.2367 A over the 599 that drop the pre-run holdover frame), peak 9.99 A, mean power 85.1593 W over the same all-600 population and 85.3015 W over the 599 holdover-excluded frames published in `operating-envelope-v1.yaml` — the two means differ only because of that one holdover frame. A range from one session is an observation, not a rating |
| Thermal response window | **ONE SESSION**, hot side only | TEC_HOT_SIDE plateaus at 37.688 °C in H8-B/C/D/E and reached 39.938 °C, still creeping, in the committed 600 s box run. Chamber-air response windows come from W13, not from W08 |
| Default-off behaviour | **AVAILABLE** | the delivered build has the output stage compiled out, requested duty 0 and actuator enable disallowed; the enable state is *commanded but never observed* (`enable_readback=ren:0,len:0` in all 957 frames while `ren_command=1`) |
| Physical failure evidence | **AVAILABLE, sparse** | no `fault_bits` anywhere, no fault ever injected (`fault_latency_us=-1`), fan not electronically observable, no interlock installed, and the §4 duty-0 frame |

## 3. Conductor and fuse: the two corrections that changed this week's wording

* **Conductor.** The record said "1.75 mm²". Operator correction 2026-11-02: that was
  a **unit error** — 1.75 is the **copper core diameter in mm**. Read as a round solid
  core it is `π × (1.75/2)² ≈ 2.405 mm²`, a **~3.8 % area gap** to the canonical
  `2 × 2.5 mm²` ask rather than the ~30 % the old wording implied, and it sits inside
  the FDD2-250 termination's 1.5–2.5 mm² rating. **The solid-round assumption is
  stated, not proven:** a stranded core is not one round wire, only the printed
  marking settles what is installed, and no marking has been photographed. So no
  nominal 2.5 mm² compliance is claimed, `evidence/A/W01/bom-audit.csv` HW-19 stays
  `UNVERIFIED`, the deviation stays open, and the verdict stays **NO_FREEZE** — the
  gap narrowed geometrically, it did not close.
* **Fuse.** The **15 A value is operator-reported only**. Nothing is legible on the
  installed body — no current rating, no 250 V, no glass/ceramic, no blade size
  (`evidence/A/W04/fuse-commissioning-note.md`). A shop listing or catalogue entry for
  a fuse of that rating is **not** evidence about installed hardware and is not treated
  as one here. Suitability is unproven; freezing a rating is NO-GO.
* **Out of this slice's namespace.** `evidence/A/W04/fuse-commissioning-note.md`
  (W04, PR #13) still records the conductor as **1.75 mm² of cross-section** at its
  table rows `:36`, `:37`, `:41`, `:50`, `:51` and `:59`, which contradicts the
  corrected reading above; the `evidence/A/HANDOFF/` files on the W07 branch already
  carry the correction. W08 references both and edits neither — the coordinator needs
  one pass over the W04 note so the corrected reading is consistent across Member A's
  branches.

## 4. The duty-0 frame stays open, and W08 does not close it

`device_ms=826894` (`seq=827`, COOLDOWN, requested and applied duty 0) reports
**7.15 A / 84.2 W / 122 Wh** with an empty electrical status cell. The applied duty
then **stayed 0** while the PZEM-reported current decayed
**7.15 → 0.56 → 0.02 → 0.0 A, reaching zero at `device_ms=829894`** (frames at 827894
and 828894 in between). That sequence is re-derived from the committed capture in this
repository, and the W07 branch's `evidence/A/W07/reset-criterion-evaluation.json`
carries it as `operator_confirmed_zero_duty_current_sequence_a`, `frames_after_suspect`
and `current_returns_to_zero_at_device_ms`.

What it does and does not mean:

* The decay **supports** register/transition lag and **weakens** sustained
  energization — it is evidence, and it is now recorded instead of being asserted away.
* It is a **PZEM-reported trace with no independent instrument behind it**. A measured
  value and a verified physical current are different claims; nothing here proves the
  branch was de-energized.
* docs/01 §22.4 "Commanded OFF + unexpected current" and §23.4 "current while state
  should be OFF" make this a candidate **`CONTROL_ELECTRICAL_ANOMALY`** at **high
  severity**. Classifying it is a supervised firmware/operator decision, so the Gate A
  row and the acceptance row read **NOT PRE-JUDGED — CANDIDATE OPEN IN W15**, and
  `validate_w08.py` / `validate_w15.py` require the token to stay published.
* Consequence for scheduling: this frame **should be classified before** further
  energized runs. Re-energizing a branch while it is unexplained whether current flows
  at zero duty is the unsafe case, not the safe one.

## 5. Sessions W08 depends on

* **GO/NO-GO (§1 of the session plan).** Not passed: no conductor marking, no fuse
  marking, one unresolved high-severity electrical question.
* **S-0, unpowered inspection (~10 min).** The cheapest unblock in the campaign:
  photograph the fuse body (installed + spare), the conductor's printed marking, the
  routing/bundling and the terminations. **Necessary, not sufficient** — it produces
  markings; it clears **no** energized-session gate, because those also need the §4
  anomaly classification and Member D's unresolved thresholds. Nothing in W08 says
  otherwise.
* **S-1, passive repeats ×3** (TEC off): owned by W07; W08 inherits no envelope benefit
  from them.
* **S-2, cooling repeats ×3** (energized, explicit operator GO): prerequisites are S-0
  done **and** the fuse/conductor question answered **and** the duty-0 frame classified
  or explicitly accepted as a known open risk by the operator and Member D; duty stays
  at the already-demonstrated 999 ‰ and length at the already-observed ~600 s. This is
  the session that would give A-W08-01 more than one sample.
* **OQ-W08-2** (≥ 1800 s supervised run with touch-free terminal / IBT-2 / cable
  temperatures) is the only path to A-W08-03's fourth bullet.
* **OQ-W08-4**: commit the local H7/H8 captures, or accept that the ladder rows stay
  `LOCAL_BENCH` and unreproducible for a reviewer.

## 6. Verification state of this handoff

`py -m unittest discover -s firmware/tools/tests -t firmware/tools/tests`,
`run_all_checks_w08.py`, `validate_w08.py` and `build_w08_artifacts.py --check` were
executed on this branch before commit; the results are in the PR description, not
asserted here. Where the bench tree is absent, the validators print
`local-bench original byte-checks: NOT RUN (bench tree absent)` and the runners surface
it as NOT RUN instead of folding it into a pass count.

## 7. What does not exist yet

A frozen envelope, any fuse decision, an ampacity basis, a rated continuous duty, a
classified anomaly, an energized-session GO, Member D's thresholds, a transport, a
SAFE_LOCAL mode, a calibration of the PZEM, and any physically verified claim — W08
publishes none of them and no host test here can produce them.
