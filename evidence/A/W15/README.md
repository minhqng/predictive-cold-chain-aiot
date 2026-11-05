# A-W15 — Electrical observability, A3 provenance and the PWM decision method (Member A)

Week: **W15** · Branch: `feat/a-w08-electrical-envelope` · Stacked on
`feat/a-w06-command-ack` (head `4d31fe5`)
Owner: Member A · Language: host Python 3.14 (`py`)
Status: **PRODUCER AUDITED · A3 INDEXED · calibration NOT certified · A-W15-04 decision: NOT_DECIDED**
PHYSICAL MEASUREMENT TAKEN BY THIS DOSSIER: **NONE**

This dossier quantifies **what the PZEM-fed electrical producer actually
delivers**, tells Member B which runs can carry an electrical ablation, and hands
the PWM question back as a *method with unresolved parameters*. There is **no
trusted independent meter** in this repository, so A-W15-03 reports plausibility
and internal consistency and explicitly not calibration. A-W15-04 decision:
**NOT_DECIDED**, by construction: every threshold that would decide it is
`UNRESOLVED`.

## 1. What W15 delivers (docs/05A section 24)

| Requirement | Delivered | Status label |
|---|---|---|
| **A-W15-01** electrical feature integrity (missing samples, cadence, ON/OFF separation, power consistency) | `pzem-quality-report.md` + `electrical-frame-quality.csv` + `pzem-quality.json`: 23 sources / **11 242 frames**, with every missing, invalid, unpowered and latency frame classified and counted | REAL_DATA_ANALYZED |
| **A-W15-02** A3 dataset support for B's electrical ablation | `A3-run-index.csv` (**19 of 23** runs carry command + applied + V/I/P + a thermal field, **1 of them committed in git**) + `a3-feature-provenance.csv` (feature → register → validity condition → whether authentic data exists) | REAL_DATA_ANALYZED (+ TEAM_DEPENDENCY for the runs only Member A's tree holds) |
| **A-W15-03** PZEM reference check | plausibility/consistency only: V×I worst delta **0.099 W** committed (0.0997 W across all sources) against a **0.18 W** register-quantisation tolerance, 0 frames beyond; energy counter vs power integral within its 1 Wh quantum. calibration **NOT certified** | NEED_USER_ACTION |
| **A-W15-04** PWM go/no-go | `pwm-go-no-go.md` + `pwm-criteria.csv` + `pwm-preconditions.csv` + `pwm-limits-unresolved.csv`: the **methodology**; 6/6 decision parameters and 6/6 firmware limits `UNRESOLVED`, 7/9 safety preconditions FAIL/OPEN | BLOCKED_HARDWARE |

## 2. Files

| File | What it is |
|---|---|
| `README.md` | this file |
| `acceptance.md` | per-requirement matrix A-W15-01…04, the pass-criteria walk, the owed physical actions |
| `pzem-quality-report.md` | A-W15-01 deliverable: missing/invalid/unpowered responses, cadence and freshness, transport classes, ON/OFF separation, power and energy consistency, and the "could not compute" list |
| `electrical-frame-quality.csv` | one row per capture: value counts, status tokens, transport classes, gap statistics, age statistics, latency-class counts, V×I and energy verdicts, `electrical_status_recorded` |
| `a3-feature-provenance.csv` | the A3 provenance table: raw and derived features, their PZEM register, the validity condition, authentic-data availability, caveat |
| `A3-run-index.csv` | the run index for Member B's ablation, including why each unusable run is unusable |
| `pzem-quality.json` | the whole audit payload (audit + provenance + run index + reference check + PWM decision), one file for tooling |
| `w15-input-provenance.json` | which inputs are committed in git and which come from the shared declared table, with its SHA-256 |
| `pwm-go-no-go.md` | A-W15-04 deliverable: criteria, required measurements, safety preconditions, thresholds as `UNRESOLVED` parameters, and the decision `NOT_DECIDED` |
| `pwm-criteria.csv` / `pwm-preconditions.csv` / `pwm-limits-unresolved.csv` | the machine-readable forms of the same three tables |
| `w15-operator-queue.csv` | the W15 half of the consolidated operator queue |
| `build_w15_artifacts.py` | regenerates all of the above; `--check` compares; refuses to emit a GO or a physical claim |
| `validate_w15.py` | hash pins + honest verdicts + **re-derived** quality spine + no-physical-claim guard |

## 3. Reproduce

```bash
py firmware/tools/cg_w15_pzem_quality.py                 # audit (git + local bench if present)
py firmware/tools/cg_w15_pzem_quality.py --no-local      # git sources only
py firmware/tools/cg_w15_pwm_gonogo.py                   # decision object (NOT_DECIDED)
py firmware/tools/run_all_checks_w15.py                  # suite + validators + artifact check
py evidence/A/W15/build_w15_artifacts.py --check         # artifacts reproduce byte-for-byte
py evidence/A/W15/validate_w15.py                         # pins, verdicts, spine
```

## 4. The findings that matter

1. **Producer failures are stamped, and the stamp is not zero.** In the H8 raw
   sessions **16 frames** carry `current_a_status=IO_ERROR` with an empty value
   cell and an age token of `-1` (H8-A 13, H8-B 1, H8-E 2; the committed 2026-11-01
   box session has none). Reading such a frame as 0 A would fabricate a
   zero-current event.
2. **Freshness is real and bounded**: the electrical sample is stamped **636-666 ms
   old** inside a 1000 ms frame; the BME air sample is 775 ms old; frame gaps have
   median 1000 ms with **0 late gaps**. So any consumer that treats an electrical
   value as instantaneous is wrong by ~0.7 s, and any staleness budget must be
   stated in those terms (Member D's policy parameter, not this slice's).
3. **The committed CSV lost the tokens.** `voltage_status`/`current_status` are
   empty in all 957 rows; `power_status`, `energy_status` and `door_status` are not
   columns; the raw line of the same session has them. The 600 s CSV therefore
   cannot support a freshness claim at all, while its own V/I/P numbers still pass
   the V×I consistency test.
4. **`energy_wh` has no validity token on the bench wire in any frame**, and a 1 Wh
   quantum: at ~85 W it updates roughly every 42 s. It is the weakest feature in the
   set and the reason A-W15-04's `energy_resolution_floor_wh` cannot be waved through.
5. **ON/OFF separation is a latency problem, not a physics problem.** 31 latency
   frames across all sources (20 `PRE_RUN_REGISTER`, 7 `OUTPUTS_OFF_REGISTER`,
   4 `OFF_SETTLING`). Steady OFF current never exceeded **0.02 A** (one LSB).
6. **Only one committed run supports the ablation.** `A3-run-index.csv` marks
   `W04-H8C-box-600s` as the single committed run with command + applied + V/I/P +
   thermal; the H6 trace has no thermal channel, the W03 captures and G1 have no
   drive, and the 20-100 % ladder lives in the local bench tree.
7. **Power factor and frequency features are not computable at all**: the firmware
   reads six input registers (0x0000-0x0005) and never 0x0006/0x0007, so no capture
   contains them. On a DC branch through an IBT-2 they would not mean much either.

## 5. Limits of this dossier

* **No calibration statement.** No trusted independent meter and no shunt
  calibration record exist here; the W03 capture is *self-consistent*, not traced.
* **Declared local numbers.** The H7/H8 rows come from
  `evidence/A/W08/local-bench-observations.json` (SHA-256 recorded in
  `w15-input-provenance.json`); originals were read in Member A's tree and never
  copied. Flagged `reproducible_from_git: false`.
* **The PWM document decides nothing** and invents no threshold to make itself
  decidable; `docs/05A` explicitly allows NO-GO, and this slice reports
  NOT_DECIDED because the parameters do not exist yet.
* **Bench image ≠ delivered firmware.** The delivered build's electrical cells are
  empty and labelled `INVALID`/`NO_DATA` in 62/62 frames; `docs/02` producer
  liveness counters (`power_beats`, `power_max_gap_ms`, `electrical_quality`) exist
  only in the W05 host fixture, not in any capture.
* **Checkout line endings**: the coordinator must add `evidence/A/W15/** -text`
  (and `evidence/A/W08/** -text`) to `.gitattributes`, or `core.autocrlf` rewrites
  CRLF on checkout and breaks every pin in `SHA256SUMS.txt`. This slice may not
  edit `.gitattributes`.
