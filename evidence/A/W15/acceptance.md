# A-W15 acceptance

Slice: W15 A3 electrical-observability support + the PWM characterization
decision · Branch `feat/a-w08-electrical-envelope` · Host analysis only (no
firmware change, no build, no port, no energization).

A-W15-04 decision: **NOT_DECIDED**.
calibration **NOT certified** — there is **no trusted independent meter** in this
repository, so A-W15-03 reports plausibility and internal consistency only.
PHYSICAL MEASUREMENT TAKEN BY THIS DOSSIER: **NONE**.

W15 is **not** a GREEN week. It is delivered as **observability quantified,
dataset indexed, decision method specified, nothing decided**. The two things it
cannot do are stated as gaps rather than numbers: it cannot calibrate the PZEM,
and it cannot resolve a single PWM threshold.

## 1. Requirement matrix (docs/05A section 24)

| ID | Canonical ask | Status | Evidence | What is still missing |
|---|---|---|---|---|
| **A-W15-01** | Audit missing PZEM samples, sampling cadence, ON/OFF separation, power consistency | **REAL_DATA_ANALYZED** | `pzem-quality-report.md`, `electrical-frame-quality.csv` (23 sources, 11 242 frames): 85 frames with no value; **16 stamped `IO_ERROR`** with age `-1`; 7 host-side `INVALID` polls of 601; 62/62 valueless frames in the production build; gap median 1000 ms with 0 late gaps; ages 636-666 ms; 31 latency frames classified; V×I worst 0.099 W against a 0.18 W quantisation tolerance, 0 frames beyond | a producer that publishes its own freshness **and** failure into the derived CSV (today the CSV drops both), and a stated staleness budget (D) |
| **A-W15-02** | Identify runs containing command, applied, V/I/P and thermal response for B's electrical ablation | **REAL_DATA_ANALYZED** | `A3-run-index.csv`: **19/23** runs carry all four fields; only **1/23 is committed in git** (`W04-H8C-box-600s`, 599 driven frames at 999 ‰). `a3-feature-provenance.csv`: 9 features with register, validity condition and computability | the ladder runs are in Member A's local tree only; H7 rows have a thermal **field** but no thermal **response** (electrical-only image); the H6 trace has no thermal channel; the energy feature has no validity token |
| **A-W15-03** | PZEM reference check against a trusted meter; if none, report plausibility/consistency and not certified calibration | **NEED_USER_ACTION** (consistency half REAL_DATA_ANALYZED) | `pzem-quality-report.md` §8: per-source V×I agreement, per-source energy counter vs trapezoidal integral (committed: Δ14 Wh vs 14.219 Wh), LSB table (0.01 V / 0.01 A / 0.1 W / 1 Wh) | one trusted reference meter (or a calibrated shunt channel) read at several dwell-stable duty points beside the PZEM in the same session; until then no calibration statement is possible |
| **A-W15-04** | PWM go/no-go for optional energy-aware duty control: test limited safe duty points, check IBT-2 response, PZEM power behaviour, thermal behaviour | **BLOCKED_HARDWARE**, delivered as **methodology** | `pwm-go-no-go.md` + `pwm-criteria.csv` (6 parameters, all `UNRESOLVED`), `pwm-preconditions.csv` (9, of which 7 FAIL/OPEN), `pwm-limits-unresolved.csv` (the delivered six, all `UNRESOLVED`) | Member D's limit values; a build with the output stage compiled in; a conductor/fuse decision (W08 returns NO_FREEZE); an interlock or an explicitly accepted risk; PSU continuous-rating confirmation; fan observability; a repeated randomized dwell campaign |
| Deliverable | `pzem-quality-report.md` | REAL_DATA_ANALYZED | generated; `--check` reproduces it byte-for-byte | — |
| Deliverable | `A3-run-index.csv` | REAL_DATA_ANALYZED | generated | — |
| Deliverable | `pwm-go-no-go.md` | IMPLEMENTED / HOST_VERIFIED | generated, decision `NOT_DECIDED` | — |

## 2. Pass-criteria walk

| Criterion | Result | Basis |
|---|---|---|
| electrical features are trustworthy enough for A3 | **QUALIFIED YES** | raw V/I/P are internally consistent (V×I within register quantisation, monotonic energy counter) **and** the failure modes are now named: unqualified CSV values, `IO_ERROR` stamps, a 1 Wh energy quantum, and one poll of latency at every ON/OFF edge |
| energy feature usable | **NO for short dwells** | 1 Wh with no validity token: ~42 s at the observed 85 W; it cannot resolve a 60 s dwell |
| ablation runs available | **1 committed / 19 declared** | B can ablate the committed 600 s run today; the duty ladder needs the local captures committed (OQ-W08-4 / OQ-W15-1) |
| calibration traced to a reference | **NO** | no trusted meter; consistency is not calibration |
| PWM work scientifically safe | **NOT_ESTABLISHED** | every decision parameter is `UNRESOLVED`, so a campaign would be run against invented thresholds — the exact failure `docs/05A` warns about |

## 3. What could not be computed, and why

* **Power factor / frequency features**: the firmware reads input registers
  0x0000-0x0005 only, so 0x0006/0x0007 are absent from every capture; on a DC
  branch the quantities are not meaningful in the first place.
* **Producer liveness counters** (`power_beats`, `power_max_gap_ms`,
  `electrical_quality`): a delivered-schema concept that the bench image's
  `#CG H8S schema=3` line never emits — visible only in the W05 host fixture.
* **A duty-resolved electrical model from git alone**: the ladder is local-bench.
* **Stale-versus-fresh separation inside the committed CSV**: its status and age
  columns are empty or absent.
* **Any statement about terminals, the IBT-2 case or the cable**: no frame in any
  source measures them.
* **A calibrated error band for any published watt or amp**: no reference
  instrument exists in the evidence chain.

## 4. Operator queue (W15 half; merged with W08 where one session serves both)

| Queue | Requirement | Session | Prerequisites | Unlocks | Extra sessions |
|---|---|---|---|---|---|
| OQ-W15-1 | A-W15-01 | none — commit/hash-pin the local H7/H8 captures | none | reproducible quality numbers | 0 |
| OQ-W15-2 | A-W15-03 | paired PZEM + reference-meter readings at dwell-stable duty points | same energized safety set as a characterization dwell | a calibration statement instead of plausibility | 0 (shares the campaign) |
| OQ-W15-3 | A-W15-04 | the PWM characterization campaign, ≥ 3 randomized dwells per point with rest intervals and touch-free component temperatures | PWM-P1…P9 satisfied first | the GO/NO-GO decision, three of the six unresolved limits, the RQ6 option | merged into the same bench day as OQ-W08-2 |
| OQ-W15-4 | A-W15-02 | none — agree the run list with Member B | none | B's ablation design without another energized run | 0 |

## 5. Items this slice does not own

* The SAFE_LOCAL policy, the numeric limits and the staleness budget: Member D.
* Transport, clock synchronisation and the backend: Member C.
* The A3 model itself and the ablation statistics: Member B.
* `firmware/main/**` (no firmware changed, so no ESP-IDF build was run) and
  `.gitattributes` (see `README.md` §5).

## 6. Verification record

| Check | Result |
|---|---|
| `py firmware/tools/run_all_checks_w15.py` | all layers PASS (see the command output in the slice report) |
| `py evidence/A/W15/build_w15_artifacts.py --check` | 11 artifacts reproduce byte-for-byte |
| `py evidence/A/W15/validate_w15.py` | PASS: pins verified, quality spine re-derived from the committed captures, PWM decision still `NOT_DECIDED`, no physical claim present |
| ESP-IDF build | not run: this slice changes no firmware |

## 7. Status vocabulary used here

IMPLEMENTED · HOST_VERIFIED · REAL_DATA_ANALYZED · NEED_USER_ACTION ·
TEAM_DEPENDENCY · BLOCKED_HARDWARE. `PHYSICALLY_VERIFIED` is never assigned:
`validate_w15.py` fails if any artifact in this dossier ever carries it, and the
PWM generator refuses to emit a `GO` while blockers exist.
