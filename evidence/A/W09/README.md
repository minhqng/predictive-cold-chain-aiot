# A-W09 — Evidence-grade dataset acquisition, QC and export (Member A)

Week: **W09** · Branch: `feat/a-w09-dataset-tooling` · Base `4d31fe5`
Owner: Member A · Docs precedence: 00 > 01 > 02 > 03 > 04 > 05A
Status: **TOOLING DELIVERED AND HOST-VERIFIED · ONE REAL CAPTURE ANALYZED ·
S1/S2/S4 PHYSICAL SESSIONS NOT RUN — REAL DATA NOT AVAILABLE**

This dossier delivers the acquisition, QC, analysis and export **workflow** for
the S1 normal-baseline scenario plus the operator checklist, and runs that
workflow over the only real thermal capture that exists in the repository. It
does **not** contain an S1 baseline dataset: the required physical S1 session has
not been run, nothing here invents one, and no host fixture is presented as a
measurement.

## 1. What W09 changed

| Requirement | Delivered | Status |
|---|---|---|
| **A-W09-01** run checklist | `cg_w09_run_protocol.py`: 20 gates (9 BEFORE_RUN, 2 DURING_RUN, 9 AFTER_RUN), each with a canonical doc anchor and an honesty label for whether firmware can observe it; 6 gates are HOST_ONLY by construction, 18 are blocking. Rendered as `run-protocol-v1.md` + `run-protocol-v1.json` | IMPLEMENTED / HOST_VERIFIED |
| **A-W09-02** S1 baseline | The acquisition + QC + export path is delivered and run over the real committed capture. **No S1 run is collected**: `run-registry.json` reports 1 candidate and **0 certified runs** | REAL_DATA_ANALYZED for the candidate · **REAL DATA NOT AVAILABLE** for the target (`~4 valid S1 runs`) → NEED_USER_ACTION |
| **A-W09-03** physical invalidation | `cg_w09_validity.py`: per-domain quality (provenance/producer/thermal/environment/door/electrical/sequence), 31 reason codes declared, `EXCLUDED_SESSION_CLASSES = ("PROBE_IDENTIFICATION", "TOUCH_IDENTIFICATION")`, and no delete path — a row is labelled, never dropped | IMPLEMENTED / HOST_VERIFIED / REAL_DATA_ANALYZED |
| **A-W09-04** healthy response reference | `healthy-ranges.json`: electrical active/OFF ranges, thermal baseline per physical position, gradient, cadence, per-probe noise — every lane labelled with the qualification it actually has | REAL_DATA_ANALYZED (thermal) · **UNQUALIFIED** (electrical) |
| Run registry | `run-registry.json`: all 6 repository captures classified, 3 host fixtures refused as runs, plus the 2 external positions that cannot be cited from this branch | REAL_DATA_ANALYZED |
| Provenance + export | `cg_w09_export.py`: identity, ROM **and** physical position, timestamp/uptime semantics, per-field quality, experiment phase, per-row invalidation reasons, SHA-256 of every source | IMPLEMENTED / HOST_VERIFIED / REAL_DATA_ANALYZED |
| Handoffs (§18) | B: `s1-run-index.json` · C: `handoff-fields.md` · D: `healthy-ranges.json` | see §4 |

## 2. Files

| File | What it is |
|---|---|
| `README.md` | this file |
| `acceptance.md` | requirement-by-requirement status with the gaps named |
| `run-protocol-v1.md` / `.json` | the operator checklist (docs/05A §18 A-W09-01) in human and machine form |
| `run-registry.json` | every capture in the repo and what it may enter |
| `exports/CG-S1-H8C-600S.json` | the evidence-grade export of the real capture, with its per-row companion |
| `exports/CG-S1-H8C-600S.row-validity.csv` | 957 rows + a 65-column header: the whole per-row contract - identity, provenance, uptime/UTC semantics, per-domain quality, reasons, phase |
| `s1-run-index.json` | Member B's join surface: measured usability and the blocked-run reasons |
| `invalidation-summary.json` | reason and domain counts over the real capture, including the reasons that fired zero times |
| `healthy-ranges.json` | the A-W09-04 reference D consumes |
| `handoff-fields.md` | the run-manifest edge fields C consumes |
| `build_w09_artifacts.py` | regenerates all 9 derived artifacts; `--check` compares, `--sums` rewrites the pins |
| `SHA256SUMS.txt`, `validate_w09.py` | byte pins and the re-checker, which also re-derives the numbers, re-asserts the honest verdicts and separates the durable claims from the phase snapshots |

## 3. Reproduce

```bash
py firmware/tools/run_all_checks_w09.py              # W09 layers, end to end
py -m unittest discover -s firmware/tools/tests -t firmware/tools/tests -p "test_cg_w09*"
py evidence/A/W09/build_w09_artifacts.py             # regenerate the 9 artifacts
py evidence/A/W09/build_w09_artifacts.py --check     # byte-reproducible
py evidence/A/W09/validate_w09.py                    # hashes + re-derived numbers + honesty
```

The runner prints the exact test files each selection resolves to, and fails if a
selection resolves to nothing: a verdict published here may only rest on files
tracked on this branch. `test_cg_w09_runners.py` enforces that. Proof from tracked
state alone — a working tree that also holds another worker's untracked files is
**not** a passing environment — means a **detached checkout of this branch**, not an
archive extraction:

```bash
git -C <repo> worktree add --detach <scratch>/w09-verify fix/a-w09-w10-review
# from that directory run both runners and both validators, then remove the worktree
```

An extracted `git archive` is **not** an acceptable verification environment for
this ladder: `evidence/A/W02/validate_w02.py` and `evidence/A/W03/validate_w03.py`
resolve their own claims with `git cat-file -e` / `git show` and treat "git cannot
run" as a FAIL rather than a skip, so an archive with no object store fails weeks
this branch never touched. A detached worktree is the same commit *with* its git
history, which is what "from tracked state alone" has to mean here.

## 4. Real numbers, from the committed capture

Every claim in this section carries one of two labels, and the labels are part of
the dossier rather than decoration:

* **MUST-KEEP** — a rule or a provenance fact that stays true however the physical
  study develops. `validate_w09.py` requires it in every revision of this file.
* **PHASE SNAPSHOT** — a figure measured over the single real thermal session the
  repository holds today. It **MUST EVOLVE**: the validator asks for those numbers
  only while `run-registry.json` lists exactly one real thermal capture, and it
  refuses the single-session wording the moment a second one is filed. Pinning
  H8-only figures forever would make this honesty check fail the day the physical
  study succeeds, which is the opposite of what an honesty check is for. The same
  two-class split is what the reviewed W07 report validator applies with
  `ALWAYS_REQUIRED` against its conditional snapshot tokens.

### 4.1 MUST-KEEP (durable)

* **T2 is the TEC hot side — `TEC_HOT_SIDE` — and is never averaged into chamber
  air**; T1 = chamber centre, T3 = chamber bottom, T4 = near the door. That is the
  operator-frozen as-built geometry, not a re-measurement performed here. `docs/01`
  lines 823-825 expect T1 near-door / T2 central / T3 far-opposite; the naming
  discrepancy stays **documented, not resolved** — no silent remap and no slot-role
  swap may return through this dossier.
* **A qualifier the encoding does not carry is reported `UNKNOWN`, never assumed
  satisfied** (docs/01 §19.4). `{FIELD}_STATUS_ABSENT` is a blocking code, so a
  missing door/environment/electrical qualifier removes the row from every scenario
  that needs that domain. *Which* columns this capture lacks is a snapshot; the rule
  that absence is not a pass is not.
* **Two counts that are not the same claim stay published apart**:
  `rows_thermally_usable_for_statistics` is the row set a mixed-probe thermal
  statistic runs over, and `rows_usable_for_baseline` is what the S1 scenario can
  actually consume. Collapsing one into the other is the partial-figure-read-as-full
  failure docs/01 §20.1 names.
* **A slope names its temperature representation, its window and its fit method**
  (docs/01 §20.5). The least-squares, endpoint and median-of-successive-intervals
  figures are published under their own names; none of the three may be quoted as
  "the gradient".
* **Segments of one `boot_id` are never merged into an invented `run_id`**: B
  receives an empty `valid_s1_run_ids_for_member_b` plus `blocked_run_ids` carrying
  the reason, and the joined tokens `MULTIPLE_RUN_IDS` / `MULTIPLE_BOOT_IDS` are
  forbidden anywhere in this dossier.
* **`PROBE_IDENTIFICATION` and `TOUCH_IDENTIFICATION` frames are permanently
  excluded** from S1/S2/S4 and from every thermal-response statistic, and an
  invalid attempt is labelled and kept, never deleted (docs/05A §18 A-W09-03).
* **A host fixture is never a measurement, and host tests are not physical
  verification.** Everything asserted here is HOST_VERIFIED or REAL_DATA_ANALYZED;
  no session that did not happen may carry `PHYSICALLY_VERIFIED`.
* **Unqualified electrical values are not health evidence**: every electrical lane
  carries `usable_for_a_health_claim: false` for as long as its producer status is
  absent. The absent columns are the snapshot; the refusal is the rule.
* **Every artifact path is repository-relative** — no pinned file may carry a
  developer disk, and `validate_w09.py` scans for one.

### 4.2 PHASE SNAPSHOT — MUST EVOLVE once more than one real thermal session exists

Source: `evidence/A/W04/tec-cooling-response-600s.csv` (336,832 bytes, SHA-256
`f8716b5136f34542225b366c238be4e65ce309e78593e8bad90d578af9a7c14d`), one boot_id
`56044b74` carrying two `run_id` segments, firmware `cg-w04-0.1.0`, hardware
`CG-HW-001`. It is the only real thermal capture in the repository today, which is
why these figures headline the dossier; a second committed session turns this block
into one row per session.

* **957** data rows parsed, **0** rejected lines.
* **940** rows are clean enough for a mixed-probe **thermal statistic**
  (`rows_thermally_usable_for_statistics`); **0** rows are usable for the
  **S1 scenario** (`rows_usable_for_baseline`, usable_fraction 0.0). Those are
  different claims and are published apart on purpose: the S1 scenario also asks
  for the door and environment domains, and this derived table carries no
  `door_status`, `air_c_status`, `rh_pct_status` or `power_w_status` column, so
  those domains cannot be qualified at all. Absent is reported as `UNKNOWN`, not
  as satisfied (docs/01 §19.4).
* The first **17** frames are `snapshot=INVALID`, `door_open=UNKNOWN`,
  `door_polarity=UNCONFIRMED` and are excluded from every statistic, thermal included.
* Phases: `PRE_FIRST_SNAPSHOT` 17, `OFF_IDLE` 335, `ACTIVE_COOLING` 600, `COOLDOWN` 5.
* Reason counts fired: `ELECTRICAL_UNQUALIFIED` 2,871 (3 fields × 957),
  `ENERGY_ACCUMULATOR_UNQUALIFIED` 957, `MASKS_ABSENT` 957,
  `DOOR_STATUS_ABSENT` 957, `AIR_C_STATUS_ABSENT` 957, `RH_PCT_STATUS_ABSENT` 957,
  `POWER_W_STATUS_ABSENT` 957, `DOOR_POLARITY_UNCONFIRMED` 17,
  `DOOR_STATE_UNKNOWN` 17, `SNAPSHOT_INVALID` 17.
  31 reason codes declared as checked and the rest fired zero times — recorded so
  that "checked and found none" is distinguishable from "did not check".
* Per domain: thermal/sequence/provenance **VALID 957**; producer DEGRADED 940 /
  INVALID 17; electrical, environment **and door UNKNOWN 957, VALID 0**.
* Gradient over the 940 thermal-valid rows, window 939 s, per single-probe value
  (docs/01 §20.5: a slope names its representation, window and fit method, so the
  estimators are published apart). Least-squares fit: T1 -0.0112103, T3 -0.0101739,
  T4 -0.010514 °C/s. Endpoint figure `(last - first) / duration`, which on an
  evenly spaced series equals the mean of the successive interval slopes: T1
  -0.0034611, T3 -0.0035953, T4 -0.003394 °C/s. The two differ about 3x because
  the box cools and then recovers; quoting one of them as "the gradient" without
  naming the estimator is the ambiguity §20.5 forbids. The median of the
  successive interval slopes is 0.0 for all three, which is the 0.0625 °C
  quantisation saying most 1 Hz steps are zero, not that the air stood still.
* Cadence: 956 intervals, mean 999.99 ms, min 990, max 1000, 0 non-positive.
* 163 W09 host tests check the rules against synthetic frames; they count fixture
  rows, not plant measurements.

### 4.3 What has to change when a second real session is filed

* Every figure in §4.2 becomes **per session**; none of them may be re-published as
  an aggregate until `run-registry.json` lists more than one real thermal capture
  and the builder is pointed at all of them. The single-session wording stops being
  acceptable at that point, and `validate_w09.py` is written to catch it rather than
  to bless it.
* `rows_usable_for_baseline: 0` and `usable_fraction 0.0` are properties of this
  **encoding**, not of the plant: a capture that keeps its `door_status`,
  `air_c_status`, `rh_pct_status` and `power_w_status` qualifiers scores above zero
  under the same rules. That is the operator action A-W09-02 names, and it is why
  the checklist, not the analysis, is the blocking artifact.
* `s1_runs_certified_valid: 0` is a snapshot of the study phase too. The validator
  ties the "REAL DATA NOT AVAILABLE" wording to that measured count, so certifying
  real runs releases the wording instead of fighting it — and a non-zero count with
  that sentence still standing would be an overstatement, not a pass.

## 5. Limits of this dossier

* **The S1 session has not been run.** `~4 valid S1 runs` is a target, not a
  result. `run-registry.json` says `s1_runs_certified_valid: 0` and why.
* **The candidate's `run_id` is unresolved and therefore not handed to B.** The
  source carries two `run_id` segments (`run-00000000`, `run-00000001`) inside
  one `boot_id`. Segments of one boot are not independent runs, and a joined id
  would exist in no source, so `valid_s1_run_ids_for_member_b` is **empty** and
  the case is listed in `blocked_run_ids` with its reason.
* **Electrical values are unqualified.** The 957-row H8 capture has empty
  `current_status`/`voltage_status` on every row and no status column at all for
  `power_w`/`energy_wh`. Every electrical number is published with
  `usable_for_a_health_claim: false`.
* **There is no real door-open event**: `door_open` is `0` in 940 rows and
  `UNKNOWN` in the other 17, with `door_polarity` matching. The door→response
  metric is therefore NOT COMPUTABLE (see W10).
* **No `#CG H8S schema=3` frame carries a sensor ROM id.** ROM identity comes
  from the per-boot `#CG ROM` lines and the frozen ROM table, exported as
  `rom_source=BOOT_LOG_*` with `rom_readback_verified: false`.
* **As-built geometry is operator-frozen, not re-measured here**: T1 = chamber
  centre, T2 = TEC HOT_SIDE, T3 = chamber bottom, T4 (SPARE) = near the door.
  `docs/01` lines 823-825 expect T1 near-door / T2 central / T3 far-opposite.
  That naming discrepancy is **documented, not resolved**: no silent remap is
  performed, and T2 is never averaged into chamber air.
* **The 2026-11-02 hand-touch session is `PROBE_IDENTIFICATION`** and is
  permanently excluded from S1/S2/S4 and from every thermal-response statistic;
  the exclusion is in `cg_w09_validity.py`, exercised by tests, and asserted by
  the validator.
* **`device_ms` is per-boot** and opening the COM port changes `boot_id`; host
  UTC is not device time, so `timestamp_utc` stays `UNAVAILABLE`.
* **Host tests are not physical verification.** The 163 W09 host tests named in
  §4.2 check the rules; they do not measure the plant, and no verdict here may
  be reported as a physical confirmation.
