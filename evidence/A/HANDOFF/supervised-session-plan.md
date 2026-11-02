# Member A — supervised session plan and physical acceptance queue

Status: **Member A input only.** Nothing here authorises energisation. Each powered
session requires the operator's explicit case-by-case GO, and the safety gate in §1
must be closed first. The conductor/fuse reasoning this plan rests on is recorded in
`evidence/A/W04/fuse-commissioning-note.md` §3-§4 on this branch.

## 1. GO / NO-GO — read this before any powered session

| Question | Answer today | Evidence |
|---|---|---|
| Is the TEC branch conductor known? | **No.** Installed as 1.75 mm2 (operator-confirmed), but no marking photographed, no ampacity, no insulation class, no routing/bundling recorded | `evidence/A/W04/fuse-commissioning-note.md` §3; `evidence/A/W01/bom-audit.csv:20` HW-19 still `UNVERIFIED` |
| Does that matter for a fuse choice? | **Yes, decisively.** A branch fuse protects the weakest element, which is the cable | same note §3 |
| Is 15 A defensible? | **No, not today.** "Without the installed current-carrying capacity of a 1.75 mm2 conductor at its actual insulation class and routing, no rating below or above 15 A can be justified" | same note §3 closing paragraph |
| Is the conductor canonical-compliant? | **No.** Canonical ask is `2 x 2.5 mm2` (docs/05A A-W04-02, docs/01 PHY-SAFE-004). 1.75 mm2 is a live deviation and must not be silently certified | note §3, `bom-audit.csv:20` |
| Peak current already observed | 9.99 A (single 600 s cooling session, unqualified status columns), 9.16 A / 60 s at 100 % duty in the H7 ladder | `evidence/A/W04/tec-cooling-response-600s.csv`, `evidence/A/W07/repeatability-report.md` |
| Unresolved high-severity anomaly | **Yes.** `device_ms=826894`: applied duty 0 with 7.15 A / 84.2 W, all 14 measured fields identical to the two preceding driven frames. docs/01 §22.4 makes a commanded-OFF-with-current frame a candidate `CONTROL_ELECTRICAL_ANOMALY` (high severity, "indicates physical energization outside expected intent"); the competing reading is PZEM register holdover (`evidence/A/W04/README.md:20`) | `evidence/A/W07/reset-criterion-evaluation.json`, `evidence/A/W07/repeatability-report.md` |

**Verdict:**
- **GO without any power:** the unpowered inspection in §2. No TEC, no START.
- **GO after §2 only** (TEC stays off): the passive repeats in §3. No stage enable, no duty.
- **CONDITIONAL, needs an explicit fresh operator GO and a resolved fuse/conductor
  answer:** every session that closes the stage (§4 onward). The commanded-OFF-with-current
  frame should be classified **before** further energised runs, because re-energising a
  branch while it is unexplained whether current flows at zero duty is the unsafe case,
  not the safe one.
- **NO-GO from Member A tooling at any time:** raising duty, PWM, current or temperature
  limits beyond what has already been demonstrated; changing the fuse; changing wiring;
  extending a powered run past the already-observed ~600 s without a new authorization.

## 2. Session S-0 — unpowered inspection (~10 min, no energisation, do first)

**Purpose:** closes the single input that blocks every powered session, plus the A-W07-01
and A-W12 photo asks. It is the cheapest unblock in the whole campaign.

Actions (camera only, board unpowered, branch not energised):
1. Photograph the installed fuse body so its rating, `250 V` and glass/ceramic are legible;
   photograph the spare 10 A fuse.
2. Photograph the TEC branch conductor's printing along the run; record whatever marking it
   carries (cross-section, `H05VV-F`/`PV` class, temperature class). If nothing is printed,
   say so.
3. Photograph the routing: is the branch bundled with other conductors, clipped against a
   warm surface, or run free-air? Note the length.
4. Photograph the termination on the branch (FDD2-250 faston is already recorded as in-range
   for 1.75 mm2).
5. Photograph sensor mounting: each probe tip's height above the floor, whether it hangs in
   air or touches a wall or rack, and the cable path. Do **not** move any probe — the slot
   to position map is frozen (`evidence/A/W07/geometry-v1.md` §1: T1 centre, T2 hot side,
   T3 bottom, T4 near door) and no re-identification is wanted.
6. Confirm by eye, without powering, that the hot-side probe (T2) is still on the hot-side
   metal.

**Outputs:** photo set into `evidence/A/W12/` on that branch, fuse/conductor table, and the
A-W07-01 / A-W12-03 items move from open to closed. **Nothing in this session produces a
measurement**, so it cannot be mistaken for a run.

## 3. Session S-1 — passive warm-up repeats ×3 (TEC stays OFF)

**Purpose:** A-W07-02 (`>=3` valid passive runs) and the two numbers the reset criterion is
waiting on: `tmean_band_c` and `gradient_bound_c_per_min`
(`evidence/A/W07/reset-criterion-v0.yaml`, both `UNRESOLVED`).

Prerequisites: S-0 done; chamber at room conditions; door closed; no hand near any probe.

Actions, three times as three **independent** sessions:
1. Open the capture port. **Note: opening the port resets the board, so each session must be
   a new `boot_id`** — three windows inside one boot are three phases of one run, which is
   exactly what today's data is and why A-W07-02 is not met.
2. Let the chamber sit untouched for >= 10 minutes at power-on (today's passive segment is
   226 samples / 224.99 s, which is under the 3.75 min mark and too short to set a band).
3. Close the capture. Do not touch anything during it.

Capture mechanism: serial 115200, read-only, the `#CG H8S schema=3` frame stream.

Validation rules (what invalidates a passive run): any applied duty above 0; any hand-touch;
any door state that is not attested CLOSED; any probe status other than the valid state; a
`boot_id` shared with another run. Never delete an invalid attempt — log it
(`docs/05A` A-W09-03: "Never delete invalid attempt").

Outputs and who consumes them:
- W07: repeatability of the passive mean and drift → the reset criterion can stop answering
  `UNKNOWN` only after this.
- W13: the passive response constant.
- W09: the first genuinely passive S1-like material (still not a full S1, which is a normal
  operation baseline).

## 4. Session S-2 — cooling-step repeats ×3 (energised: needs explicit GO)

**Purpose:** A-W07-03 (`>=3` valid cooling-step runs) and the plant variation the W07 pass
criterion needs, so that a deliberate S2 disturbance can be told apart from setup drift.

Prerequisites: S-0 complete **and** the fuse/conductor question answered; the zero-duty
current frame classified (or explicitly accepted as a known open risk by the operator and
Member D); duty stays at the already-demonstrated 999 permille, not higher; run length
bounded at the already-observed ~600 s.

Actions, three independent sessions (each a fresh boot, each starting from the reset state):
1. Confirm the chamber is at the reset baseline before START (`cg_reset_criterion.py`
   evaluates the recorded state; today it answers `UNKNOWN`, so use the observed pre-run mean
   and say so in the log).
2. START, hold the cooling step ~600 s, STOP.
3. Let it recover and record the recovery segment too — one capture yields cooling **and**
   recovery, but still counts as **one** run.

Expected signals: applied duty at the commanded value, current rising into the observed
7.2 A mean / 9.99 A peak region, chamber-air mean falling by roughly 8.7 C over ~10 min as
in the committed session, and the hot-side probe (T2) **rising** while air falls — that
opposition is the whole reason T2 is excluded from chamber-air means.

Stop rules (abort, log, do not retry automatically): zero or abnormal current against a
commanded ON state; any current at zero applied duty that is not explainable as the last
sample of a transition; a probe going INVALID or stale; any smell, heat or discoloration on
the branch.

Invalidation: a run whose electrical columns carry no recorded validity is usable for
observation and **not** for a qualified claim; a run sharing another run's `boot_id` is not
independent.

Outputs: W07 repeatability; W08 observed envelope with more than one sample; W09 S1 baseline
material; W13 cooling constants; W16 comparability baseline.

## 5. Session S-3 — S2 door disturbances ×4-6 (energised: needs explicit GO)

**Purpose:** A-W10-03 `>=4-6` valid pilot disturbances, which is the only path to the
door-to-critical and controller-response distributions docs/05A A-W10-05 requires for
Member B, and to A-W10-04 pairing-tolerance evidence.

Today there is **no real door-open event anywhere in committed data**: in the 957-row H8
capture `door_open` is `0` in 940 rows and `UNKNOWN` in 17, with `door_polarity`
CONFIRMED/UNCONFIRMED to match. Everything W10 currently publishes about doors is a
reported-by-frame value, not a named physical state.

Prerequisites: S-2 method established; Member D supplies the time-to-critical definition
(a project threshold, not Member A's to choose); MC-38 transition is the machine ground
truth and an operator timer is the secondary check (docs/05A A-W10-02).

Actions per disturbance, from a repeatable cooled starting state:
1. Record the stable pre-open mean for at least 30 s.
2. Open the door fully for a bounded, recorded duration (target variety: short and long,
   so duration is not constant across runs).
3. Close it, and record recovery to the pre-open level plus margin.
4. Log the operator timer alongside the MC-38 edge for every event.

Measure per event: door duration, initial T, peak, gradient, time-to-critical candidate,
recovery (docs/05A A-W10-03).

Outputs: the door-event evidence Member B needs to freeze matching tolerances and to choose
a horizon — and per A-W10-05, **Member A supplies the distributions, Member B chooses the
horizon**.

## 6. Session S-4 — S4 refusal evidence (conditional)

Needs Member D's threshold and allowed-range decisions in place first, so a refusal has
something defined to refuse against. Capture the command intent, the device ACK, and the
applied state, and keep refusal evidence separate from physical-effect evidence: an ACK that
says refused proves the device declined, it does not by itself prove the branch stayed
unenergised — that still needs the electrical columns, which today carry no recorded
validity.

## 7. What stays blocked even after S-0..S-4

- **Conductor/fuse continuous rating.** Sessions produce observations, not an ampacity
  rating. A defensible fuse selection needs the installed conductor's current-carrying
  capacity at its real insulation class and routing; that is §2 plus a stated table, or a
  documented `2 x 2.5 mm2` replacement.
- **PZEM absolute accuracy.** Everything electrical here is self-consistent, not referenced.
  A trusted independent meter is a genuine external gap (W15 A-W15-03).
- **The Tmean definition.** Choosing between `mean(T1,T2,T3)` as docs/01:823-825 literally
  says and the as-built air roles is a project-level decision. Until it is made, W07 keeps
  publishing both and the reset criterion keeps refusing to judge across them.
- **Any physical verification of the door polarity mapping** beyond the touch attestation
  already recorded.

## 8. Minimum-number schedule

If the operator has one visit available, the order that unlocks the most downstream work is:
**S-0 (10 min, no power) → S-1 passive x3 → S-2 cooling x3 (each also yielding a recovery
segment) → S-3 door x4-6 (can attach to the tail of S-2 runs only if the reset baseline is
proven stable) → S-4 later.** Sessions must not be merged where merging would destroy
independence: three phases inside one boot is one run, not three.
