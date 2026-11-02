# W15 handoff — PZEM data quality, A3 provenance and the PWM method (Member A input only)

Week: **A-W15-01…A-W15-04** · Branch `feat/a-w08-electrical-envelope` · Dossier
`evidence/A/W15/` · Host analysis only: no instrument was measured, nothing was
calibrated, no port was opened and nothing was energized. This file authorises no
session; every powered session needs the operator's explicit case-by-case GO.

Source contract: `evidence/A/HANDOFF/` on `feat/a-handoff-contracts`
(`coverage-matrix.md` A-W15 rows, `a-to-bcd-fields.md` §6.1/§6.3,
`supervised-session-plan.md` §1 GO/NO-GO and §4). Only W15's rows are carried here;
that directory is read-only and nothing is copied into it.

## 1. What W15 delivers, requirement by requirement

| ID | Canonical ask | State today | Where | What is still missing |
|---|---|---|---|---|
| A-W15-01 | Audit missing PZEM samples, cadence, ON/OFF separation, power consistency | **REAL_DATA_ANALYZED** | `pzem-quality-report.md`, `electrical-frame-quality.csv`, `pzem-quality.json` — 23 sources / 11 242 frames, 31 latency rows classified | a producer that publishes its own freshness **and** failure into the derived CSV; a stated staleness budget (Member D) |
| A-W15-02 | Which runs carry command + applied + V/I/P + thermal response, for B's electrical ablation | **REAL_DATA_ANALYZED** | `A3-run-index.csv` (19/23 usable, **1/23 committed in git**), `a3-feature-provenance.csv` | the ladder runs exist only in Member A's local tree; H7 rows are electrical-only images — the index now carries a `caveats` column per row so an H7 row cannot be read as a thermal response |
| A-W15-03 | PZEM reference check against a trusted meter; if none, report plausibility/consistency and **not certified calibration** | **NEED_USER_ACTION** (consistency half REAL_DATA_ANALYZED) | `pzem-quality-report.md` §8 | **one trusted independent meter** — self-consistency is not accuracy, and no calibration statement is possible until a reference is read beside the PZEM |
| A-W15-04 | PWM go/no-go for optional energy-aware duty control | **BLOCKED_HARDWARE**, delivered as **methodology**, decision **NOT_DECIDED** | `pwm-go-no-go.md`, `pwm-criteria.csv`, `pwm-preconditions.csv`, `pwm-limits-unresolved.csv` | Member D's limit values; a build with the output stage compiled in; a conductor/fuse decision; an interlock or an explicitly accepted risk; PSU continuous rating; fan observability; a randomized dwell campaign |

## 2. PZEM and reference-meter position (A-W15-03)

* Published today: **plausibility and internal consistency only.** V×I worst absolute
  deviation `0.099 W` against a 0.18 W register-quantisation tolerance over 957 frames,
  0 frames beyond; energy counter 108 → 122 Wh (Δ14 Wh) against a 14.219 Wh trapezoidal
  integral of the reported power; LSB table 0.01 V / 0.01 A / 0.1 W / 1 Wh.
* Not published, and not publishable from this repository: any calibration statement,
  any accuracy claim, any "the PZEM reads right" conclusion. There is no trusted
  reference meter and no calibrated shunt channel here — that is a genuine external
  gap, not a code gap.
* Every electrical figure in W15 inherits W08's qualification problem: the committed
  capture's `voltage_status`/`current_status` cells are empty in all 957 rows, so the
  values are published as `electrical_status_recorded: false`.

## 3. Duty-0 with current: the open question W15 refuses to close

`device_ms=826894` (committed 600 s capture, applied duty 0) reports **7.15 A / 84.2 W**
with an empty status cell. docs/01 §22.4 ("Commanded OFF + unexpected current") and
§23.4 ("current while state should be OFF") make that a candidate
**`CONTROL_ELECTRICAL_ANOMALY`** at **high severity**; the competing reading is PZEM
register holdover. W15 publishes both and decides neither — and `validate_w15.py` now
**requires the token** in the report and the JSON, so the safety candidate cannot
silently vanish from the evidence again.

What the record now also carries, re-derived from the committed capture and published
as `zero_duty_current_sequence_a`, `frames_after_suspect` and
`current_returns_to_zero_at_device_ms` (the W07 branch's
`evidence/A/W07/reset-criterion-evaluation.json` holds the same as
operator-confirmed): the applied duty **stayed 0** while the reported current decayed
**7.15 → 0.56 → 0.02 → 0.0 A, reaching zero at `device_ms=829894`**.

Limits of that evidence, stated in the report itself:

* the decay **supports** register/transition lag and **weakens** sustained
  energization — it is evidence, not proof;
* it is a **PZEM-reported** trace with **no independent instrument** behind it, so a
  measured value and a verified physical current stay different claims;
* the safety qualification therefore **remains open**, and classifying it is a
  supervised firmware/operator decision, not a host-tool output.

## 4. Go / No-Go and the sessions W15 depends on

* **§1 GO/NO-GO today: not passed.** No photographed conductor marking, no
  photographed fuse marking, and one unresolved high-severity electrical question.
* **S-0, the unpowered inspection, is necessary and not sufficient.** It produces the
  markings that W08 A-W08-02 needs. It does **not** clear any energized-session gate:
  those also require the §3 anomaly classification and Member D's unresolved
  thresholds. Nothing in W15 says a short unpowered inspection discharges them, and the
  same limit is now printed in `Gate-A-report.md` §6 and `pzem-quality-report.md`.
* **S-2 cooling repeats** require, before any energized run: S-0 done **and** the
  fuse/conductor question answered **and** the duty-0 frame classified (or explicitly
  accepted as a known open risk by the operator and Member D). Duty stays at the
  already-demonstrated 999 ‰ and length at the already-observed ~600 s.
* **OQ-W15-2** (reference-meter session) and **OQ-W15-3** (PWM characterization, ≥3
  randomized dwells per point) are mergeable into one supervised bench day — one
  energized visit serves both — but that merge saves sessions, it does not lower a
  single prerequisite.
* **PWM decision:** `NOT_DECIDED`, all six decision parameters `UNRESOLVED`, seven of
  nine preconditions FAIL/OPEN, and the delivered build cannot actuate at all (output
  stage compiled out, requested duty 0, actuator enable disallowed), so no criterion is
  measurable on it. PWM-P4 fails specifically because W08 returns **NO_FREEZE**.

## 5. Corrections carried into this week's wording

* **Conductor (operator, 2026-11-02).** The recorded "1.75 mm²" was a **unit error**:
  1.75 is the **copper core diameter in mm**, i.e. `π × (1.75/2)² ≈ 2.405 mm²` for a
  round solid core — a ~4 % area gap to the canonical `2 × 2.5 mm²` and inside the
  FDD2-250 1.5–2.5 mm² termination rating, rather than ~30 %. The solid-round
  assumption is stated, not proven (a stranded core is not one round wire; only the
  printed marking settles it), so `pwm-criteria.csv` PWM-C6, `pwm-preconditions.csv`
  PWM-P4 and `pwm-go-no-go.md` record **no** nominal 2.5 mm² compliance and HW-19 stays
  `UNVERIFIED`.
* **Fuse.** The 15 A value is **operator-reported only** — nothing is legible on the
  installed body (`evidence/A/W04/fuse-commissioning-note.md`). A shop listing or
  catalogue entry is not evidence about installed hardware and is not used as one.
  Suitability stays unproven and freezing a rating stays NO-GO.

## 6. Verification state

`build_w15_artifacts.py --check` reproduces all 11 generated artifacts byte-for-byte
from tracked state; `validate_w15.py` re-derives the quality spine from the committed
capture, re-hashes every declared local-bench original when the bench tree is present
and prints `local-bench original byte-checks: NOT RUN (bench tree absent)` when it is
not — `run_all_checks_w15.py` surfaces that as NOT RUN instead of folding it into the
pass count. Every pinned path in `SHA256SUMS.txt` is repository-relative; a
`__pycache__` or `.pyc` entry is rejected by the validator, and every dossier file
must be pinned.

## 7. What does not exist yet

A calibration of the PZEM, a trusted reference meter, a resolved PWM threshold, a GO
decision, a classified duty-0 anomaly, an energized-session GO, any thermal response
from the H7 ladder (electrical-only image), more than one committed run for the A3
index, and any physically verified claim. W15 publishes none of them.
