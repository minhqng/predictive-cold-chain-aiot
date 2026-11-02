# A-W14 acceptance

Slice: W14 role-aware spatial statistics and sensor-position QA · Branch
`feat/a-w14-spatial-statistics` · Stacked on `feat/a-w07-plant-repeatability` at its
current head `ff387a1`, which is also this branch's merge-base with it and the base PR
#21 opens against (the W07 delivery head `2e688be` is an ancestor of `ff387a1`, not its
tip) · Owner: Member A · Status: **TOOLS + DOSSIER DELIVERED · ONE SESSION
ANALYZED · DISTURBANCE NOT COMPUTABLE · TOLERANCES TEAM_DEPENDENCY · NON-MOVEMENT NOT
VERIFIABLE FROM ARCHIVED DATA**

docs/05A §23 asks for four things. None of them asks for a new bench session, and none
of them can be closed by the one session this repository holds. Everything deliverable
without hardware is delivered at the strength the data supports; the rest is named as
owed, not simulated.

Status vocabulary used below: IMPLEMENTED · HOST_VERIFIED · REAL_DATA_ANALYZED · PHYSICALLY_VERIFIED (never used in this dossier: nothing host-side earns it) · NEED_USER_ACTION · TEAM_DEPENDENCY · BLOCKED_HARDWARE.

## 1. Requirement matrix (docs/05A §23)

| ID | Canonical ask | Status | Evidence |
|---|---|---|---|
| **A-W14-01** | Sensor-position QA: "verify no movement since freeze" | **HOST_VERIFIED + REAL_DATA_ANALYZED for what data can show · NON-MOVEMENT = NEED_USER_ACTION (physical evidence) and NEEDS-A-NEW-CAPTURE** | `sensor-position-qa.md` / `.json`: capture role labels vs the frozen record = `MATCH` on all four slots; behaviour signature shows exactly one rising channel while driven and it is `t2_c` (`TEC_HOT_SIDE`) while T1/T3/T4 all fall; air triad max spread 1.126 °C against a surface separation of 18.938 °C. Verdict `movement_since_freeze: NOT_VERIFIABLE_FROM_ARCHIVED_DATA` — the H8S schema-3 frames carry no ROM ids and no frame records mounting, so archived data cannot close the canonical sentence, and this dossier says so instead of pretending |
| **A-W14-02** | Logical ablation support; do **not** unplug T2/T3 for core A1 | **IMPLEMENTED + HOST_VERIFIED + REAL_DATA_ANALYZED** — datasets from the same physical rows, no probe touched | `ablation-support.json/.csv/.md`: 10 feature sets × 3 phases over the identical 957-row capture, each row labelled `feature_terms`, `feature_roles`, `is_chamber_air`, `includes_hot_side`; the control is *checked*, not claimed: `conditioning_fingerprint` (`d1671cc668ca0fa1`) hashes `device_ms/state/pwm_applied_permille/door_open/boot_id` over the rows each variant actually walked, `physical_condition_control.one_fingerprint_per_capture` is computed from those hashes rather than written as a literal, and `validate_w14.py` re-derives the fingerprint and every `ablation-support.csv` row's `device_ms` → `feature_c`/`pwm`/`door`/`boot_id` attribution from the committed capture (a stamped value the capture does not produce fails the dossier). Worst chamber-air deviation from the 3-probe mean **-8.7083 °C**: **0.5833 °C** (drop T3); with the hot side averaged in instead: **6.1456 °C** |
| **A-W14-03** | Spatial statistics: gradient distributions, max pairwise differences, disturbance-specific spatial response | **REAL_DATA_ANALYZED (single-session, labelled) · gradient DISTRIBUTION = NOT COMPUTABLE · disturbance response = NOT COMPUTABLE** | `spatial-statistics.json` / `spatial-report.md`: per-pair mean / within-session sd / min / max / max|ΔT| for the 3 air pairs and the 3 air-vs-surface pairs in each phase; driven-block air max |ΔT| **1.126 °C** vs surface **18.938 °C**; recovery 0.813 °C; baseline 0.438 °C. `NOT_COMPUTABLE_AS_DISTRIBUTION` because independent sessions = 1 (needs 3), and the door block is `NOT_COMPUTABLE` because re-reading the capture gives `{'0': 940, 'UNKNOWN': 17}` — zero OPEN rows |
| **A-W14-04** | With B freeze final A/B initial physical matching tolerances | **TEAM_DEPENDENCY** — Member A's input side delivered, **no tolerance value proposed** | `pairing-input.json` / `member-b-handoff.md`: `tolerance_proposed: false`, `tolerance_value: null`, `agreed_with_member_b: false`, status `TEAM_DEPENDENCY`; the join keys, the partial-mean rule, the form a tolerance takes once ≥3 sessions exist, and the four asks for B are all in the file. `cg_w14_pairing.assert_no_invented_tolerance` raises if a number appears under a tolerance-named key or if the payload claims agreement |
| Pass criterion | Spatial features support A1 one-vs-three-sensor ablation without a physical reconfiguration | **MET at the level the data allows, HOST_VERIFIED** — ablation datasets exist and no reconfiguration happened; a *repeat* spatial claim still needs the sessions below | no probe was unplugged, moved or re-identified; the ablation is logical and the physical conditions are held by construction |

## 2. What the one real session measures

All figures are recomputed from `evidence/A/W04/tec-cooling-response-600s.csv` by the
tools and re-checked from the raw rows by `validate_w14.py`.

| quantity | driven block (600 samples) | source |
|---|---|---|
| air-to-air max |ΔT| | **1.126 °C** (T1 centre vs T3 bottom) | `spatial-statistics.json` |
| air-vs-hot-side-surface max |ΔT| | **18.938 °C** | `spatial-statistics.json` |
| reference `tmean_airroles_v0` delta | **-8.7083 °C** | matches W07's published value exactly |
| worst air feature-set deviation | **0.5833 °C** (dropping T3 bottom) | `pairing-input.json` |
| hot side averaged into an air mean | **+6.1456 °C** off the reference (-2.5627 °C) | `ablation-support.md` |
| role labels vs frozen record | `MATCH` (t2 `HOT_SIDE`; t1/t3/t4 `UNASSIGNED`) | `sensor-position-qa.json` |
| channels rising while driven | `['t2_c']` only | `sensor-position-qa.json` |
| door-open rows | **0** of 957 (940 `0`, 17 `UNKNOWN`) | re-derived, not quoted |

## 3. Defects found and closed while building W14

1. **A hot-side mean could have been labelled chamber air.** Rather than trust the
   label, `require_air()` re-derives `includes_hot_side` from W07's role map at compute
   time and raises, and a planted defect test (air variant given `t2_c`) must fail.
   `validate_w14.py` then re-checks the flag against the term list on **every** CSV row.
2. **A nearest-timestamp join in the ablation CSV.** It was O(n²) and could attach a
   feature value to a neighbouring row's conditions; replaced by walking the phase rows
   directly, with tests that the CSV row count equals the published `samples` and that
   each `feature_c` recomputes from the row it names.
3. **The claim guard had two holes in its own marker list.** First `CLAIM_MARKERS`
   included `"no "`, a substring of the very phrase it was meant to catch, so a bare
   `no movement verified` passed; removed. Then the review found the second and worse
   one: the list also counted a double quote as evidence of quotation, and every JSON
   value line is made of double quotes, so the entire content of every `.json` artifact
   was exempt from the guard - planting `"summary": "... no movement verified since the
   freeze"` in `sensor-position-qa.json` and re-pinning shipped at exit 0. The double
   quote is gone from the marker list, `validate_w14.py` now runs the structural
   `guard_no_forbidden_claim` on the parsed JSON of every artifact (it has no exemption
   list at all), and the planted-claim tests cover both prose and JSON shapes.
4. **The generator refused to write its own first draft.** A handoff line asserted
   something the captures cannot support and `build_w14_artifacts.py` exited non-zero.
   That behaviour is now covered by durable tests rather than being mentioned as luck.
5. **A validator that could not fail.** The first `check_pairing_artifact` built its
   expected strings from the payload it was checking (`payload['verdict'] and 1`), so it
   could only ever restate the file. It now re-reads the CSV: the session count, row
   count and unqualified-current count are derived from the capture and required to
   appear in the artifact.
6. **W07 gaps worked around, not edited.** W07 exposes no mean over an arbitrary term
   tuple, no public point builder, and no public whole-phase least-squares function
   (`_phase_points`/`_least_squares` are private), so `cg_w14_spatial` implements the
   three and pins each against W07's behaviour by differential test. See §5.
6b. **A fabricated proof field.** `one_fingerprint_per_capture` was the literal `true`
   and `conditioning_fingerprint` was computed once per capture and stamped on every
   variant row, so the field that acceptance §1 called the proof of "the same physical
   run" could not disagree with anything: replacing all 9 601 published fingerprints with
   `ffffffffffffffff`, setting one series row's `feature_c` to 99.9999, and appending a
   row attributed to a `boot_id` the capture never recorded each re-pinned and passed at
   exit 0. Now the flag is computed from the rows (with a per-variant fingerprint of the
   rows each statistic walked, which is the part that can actually disagree), the
   validator re-derives every fingerprint and re-attributes every CSV row from the
   committed capture, and all three tamper cases plus two more exit 1 by test. The
   published data was, and stays, clean: the fingerprints re-derive and every `feature_c`
   equals the mean of the terms its own row names.
6c. **A provenance rule that stopped at the file extension.** The absolute-path scan
   covered `.md/.json/.csv/.jsonl` only, so a drive-letter capture path planted inside
   the pinned `build_w14_artifacts.py` was hashed, never read, and passed. `.py` is in
   the scan set now, and the validator's own pattern is written so that its text cannot
   match itself.
6d. **A pin set that absorbed whatever was in the folder.** `--pins` walked the directory
   and pinned every file it found, and the validator's expected list was the same walk
   minus caches: a dropped `.pyc` was invisible and a dropped `dropped-artifact.json`
   became a certified deliverable. Both sides now read one explicit allowlist, `--pins`
   refuses unknown files, missing deliverables and caches, and the validator fails on a
   cache file in the dossier.
6e. **A validator that could only ever describe this week's single session.** The capture
   set, the `9 570` series-row count, the 957-row count and the five headline figures the
   prose quotes were frozen in the validator itself, so the multi-session branch was
   unreachable by construction and the file would have blamed the data when sessions 2
   and 3 arrive. The capture set now comes from `build_w14_artifacts.CAPTURES`, and every
   count and figure a document quotes is re-derived from the artifacts; §7 records which
   statements are a PHASE SNAPSHOT - MUST EVOLVE.
6f. **Unqualified gradients counted nowhere.** `pairwise_series` had no unqualified
   tally, so a gradient over readings whose `t*_status` was never recorded looked the same
   as one over OK-qualified readings. It publishes `unqualified_rows` and
   `usable_pairs_all_terms_ok` now, and `pair_agreement` states whether the block's
   samples are all status-qualified. On this capture the counts are 0 of 957 - all four
   `t*_status` columns read `OK` in every row - so no published figure moved; the
   mechanism is what changed, proven by a blank-status fixture.
6g. **The identification session refused by name only.** `capture_class` looked at the
   path and two field markers, so a renamed derivative of the 2026-11-02 touch logs would
   have been admitted. It now refuses on provenance first: the six `boot_id` values the
   frozen record documents for those windows, read out of the rows. Residual risk is
   recorded in §8.
7. **The honesty checks were proven able to fail.**
   `firmware/tools/tests/test_cg_w14_dossier.py` builds a miniature repository (tools +
   the real capture + this dossier), asserts the untouched copy exits 0, then plants one
   false claim at a time, re-pins `SHA256SUMS.txt` so a hash mismatch cannot be what
   tripped, and requires exit 1: the phrase `no movement verified` written in prose and
   the same claim written into a JSON value; `tolerance_value: 0.4` and
   `agreed_with_member_b: true` in the pairing input; the hot-side-contaminated mean
   re-labelled chamber air; `n=1` promoted to `DISTRIBUTION_COMPUTED`; a disturbance
   response asserted against 0 OPEN rows; an absolute developer path in drive-letter form
   inside a generated artifact **and** inside the pinned `build_w14_artifacts.py`; a
   fabricated `conditioning_fingerprint` across every published row; a series row whose
   `feature_c` is not the mean of the terms it names; a series row attributed to a
   `boot_id` the capture never recorded; a per-variant used-row fingerprint the rows do
   not produce; a file dropped into the dossier (refused by `--pins`, failed by the
   validator) and a dropped `__pycache__` - sixteen planted defects in that file, each
   producing exit 1, including the after-pinning tamper case (an edit made after the
   hashes were written, caught by the pin check). The same file carries two generator-guard cases
   proving `build_w14_artifacts.py` refuses to write an asserted false claim at all, and
   `test_cg_w14_provenance.py` carries 22 more on the mechanisms themselves.

## 4. Physical evidence still owed (consolidated)

1. **≥2 more thermal sessions** of the same protocol (3 total) — the only thing that
   turns the labelled `SINGLE_SESSION_OBSERVATION` numbers into the gradient
   distributions A-W14-03 asks for.
2. **A supervised door-open pilot** — the event itself, recorded with
   `door_polarity: CONFIRMED` on the open rows. No archived capture can substitute: the
   disturbance was never applied, so A-W14-03's third bullet stays `NOT COMPUTABLE`.
3. **One new capture under the QA protocol** (`sensor-position-qa.md`) plus a ROM
   readback or equivalent per-channel identity record, so slot identity stops being an
   assumption.
4. **The `geometry-v1.md` §5 physical items** — configuration photo with a scale,
   mounting method/height/clearance per probe, cable path, wire-label confirmation.
   These are what A-W14-01's "no movement" actually rests on, and they are
   NEED_USER_ACTION, not tooling.
5. **Member B's pairing axes and minimum session count** — A-W14-04's `TEAM_DEPENDENCY`.

Nothing above was performed here: no flash, no energized stage, no probe moved, and no
new identification test requested or run.

## 5. Coordinator actions

1. `.gitattributes`: the line `evidence/A/W14/** -text` is **already on this branch** -
   commit `9fc0780 chore(w14): keep the W14 dossier pins byte-exact on checkout` adds
   exactly those six lines, and this file's earlier claim that the file was "not touched
   in this branch" was stale. Nothing further is needed from the coordinator for W14;
   the CSV/JSON are written LF-only and `validate_w14.py` still fails on any CR byte.
2. W07 API gaps to close in a W07-owned follow-up, so W14 stops carrying local
   equivalents: public `mean_of_terms(row, terms)`, a public phase-point builder that
   takes a term tuple, and a public whole-phase `least_squares(points)`. W14's
   differential tests already pin the semantics.
3. The `docs/01` §20.1 literal `tmean_chamber3_v0` still averages the hot-side surface
   into an "air" mean. W14 publishes it labelled and excluded from ablation, but the
   naming question is a project decision that has been open since W07.
4. If the review of W07 changes `AS_BUILT_ROLES`, `REPRESENTATIONS`, `tmean`,
   `includes_hot_side` or `capture_id`, W14 inherits the change — `run_all_checks_w14.py`
   re-runs the W07 dossier validators so that breakage surfaces here rather than in
   silence.
5. **Cross-week finding (W02 and W03, not W14): their dossier validators are
   archive-sensitive.** On a `git archive HEAD` extraction of this branch,
   `run_all_checks_w06.py` reports 10/12 because `validate_w02.py` and `validate_w03.py`
   fail there - each resolves its recorded `firmware_commit` by asking git whether that
   commit contains the week's firmware sources, and an export has no history to ask.
   Both pass in a real checkout. W14 does not own those files and changed none of them;
   its runner now runs that chain only where git history exists and prints
   `[NOT RUN] ... WAITING_TEAM_DEPENDENCY` otherwise, so another week's export
   sensitivity no longer reads as a W14 gate failure - and a skipped layer is never
   counted as a pass either. The fix belongs to W02/W03: those validators need a
   history-free path (verify the recorded commit from pinned content, or report NOT RUN).

## 6. Not owned by this slice

| Item | Owner / status |
|---|---|
| Choosing the feature sets and running the A1 model ablation (B-W14) | Member B, on `ablation-support.csv` |
| Final A/B matching tolerance values | Members A and B jointly (A-W14-04) |
| Any physical session, door-open pilot or photograph | operator, supervised session |
| ROM-to-role remap, `firmware/main` changes, `docs/` edits | project-level; not touched |
| Digital-twin ingestion of these artifacts | Member C |


## 7. PHASE SNAPSHOT - MUST EVOLVE

These statements are true of the corpus W14 holds today and are *required to stop being
true* as the physical study develops. `validate_w14.py` keeps them apart from the durable
vocabulary on purpose: it demands them while one session is on disk and forbids them the
moment a second `boot_id` appears, so a future session cannot be forced through a sentence
written for this one.

| snapshot | why it has to evolve | what replaces it |
|---|---|---|
| "one session", `independent_sessions: 1`, `SINGLE_SESSION_OBSERVATION`, `NOT_COMPUTABLE_AS_DISTRIBUTION` | true only while the repository holds one thermal boot | the multi-session branch already in `cg_w14_spatial`, and a repeat distribution once 3 sessions exist |
| the capture set: `evidence/A/W04/tec-cooling-response-600s.csv`, and nothing else | the builder's `CAPTURES` list is data, not a constant | append the next session; artifacts, pins and every validator loop follow it |
| 957 rows in the session, 10 feature sets x 3 phases, 9 570 long-format rows | a second session changes all three counts | re-derived by `check_generated_counts`, which fails a document that keeps quoting the old numbers |
| the quoted figures `1.126`, `18.938`, `-8.7083`, `0.5833`, `6.1456`, `-2.5627` and the fingerprint `d1671cc668ca0fa1` | they belong to this capture set, not to spatial statistics in general | `check_handwritten_claims` reads each value from the artifact that produced it, so the docs are checked against the new number instead of pinned to today's |
| `disturbance_specific_response: NOT_COMPUTABLE` | true because `door_open` is never OPEN in any of the 957 rows | a supervised door-open pilot makes the computed branch live |
| `TEAM_DEPENDENCY` with the tolerance slot left empty | A-W14-04 is a joint decision with Member B | B's pairing axes and minimum session count, once given |

Durable, never a snapshot: the `SINGLE_SESSION_OBSERVATION` / `NOT_COMPUTABLE` /
`NOT_VERIFIABLE` vocabulary itself, `includes_hot_side` and the rule that T2 never enters
an air statistic, the frozen role map's authority, the conditioning-fingerprint fields,
the refusal of the identification session, and the rule that no host-side artifact may
carry the label `PHYSICALLY_VERIFIED`, which nothing analysed on a host earns.

## 8. Residual risk this slice did not close

* **The identification refusal is provenance-based, not forensic.** `capture_class` now
  refuses the six `boot_id` values the frozen record documents for the 2026-11-02
  windows, so a renamed or re-copied derivative of those logs is refused even under a
  thermal-looking filename. A derivative that *re-stamped* its `boot_id`s and carried no
  marker string would still be admitted, because nothing in a `#CG H8S` schema-3 frame
  identifies a physical probe - the frames hold no ROM id. The durable guard against that
  is the identification record's own evidence (the per-window rise pattern), which W14
  does not re-derive and no W14 statistic needs, because the only capture W14 reads is the
  2026-11-01 H8 session. A per-channel identity record stays in section 4 as physical
  evidence owed.
* **Unqualified readings still enter the means, and now say so.** `mean_of_terms` follows
  W07's `tmean` exactly - a pinned differential test, not a coincidence: a value whose
  status column is empty is unqualified, counted, and still used. Making it excluded
  instead is a W07 semantics change rather than a W14 one, and on this capture it would
  move nothing, because all four `t*_status` columns read `OK` in every one of the 957
  rows. What changed is visibility: `pairwise_series` and `pair_agreement` publish
  `unqualified_rows` and `usable_pairs_all_terms_ok`, so a gradient built on rows nobody
  vouched for stops looking identical to a checked one.
* **The QA separation screen is a flag, not a tolerance.** The factor-of-two band around
  one session's own maximum air spread is stated as a screen for inspection in
  `sensor-position-qa.json`; the number a pairing tolerance needs is A-W14-04's, with B.
