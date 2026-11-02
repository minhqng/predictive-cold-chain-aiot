# A-W14 acceptance

Slice: W14 role-aware spatial statistics and sensor-position QA · Branch
`feat/a-w14-spatial-statistics` · Stacked on `feat/a-w07-plant-repeatability`
(HEAD `2e688be`) · Owner: Member A · Status: **TOOLS + DOSSIER DELIVERED · ONE SESSION
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
| **A-W14-02** | Logical ablation support; do **not** unplug T2/T3 for core A1 | **IMPLEMENTED + HOST_VERIFIED + REAL_DATA_ANALYZED** — datasets from the same physical rows, no probe touched | `ablation-support.json/.csv/.md`: 10 feature sets × 3 phases over the identical 957-row capture, each row labelled `feature_terms`, `feature_roles`, `is_chamber_air`, `includes_hot_side`; the control is proven by `conditioning_fingerprint` (`d1671cc668ca0fa1`) over `device_ms/state/pwm_applied_permille/door_open/boot_id`, identical for every variant of a capture. Worst chamber-air deviation from the 3-probe mean **-8.7083 °C**: **0.5833 °C** (drop T3); with the hot side averaged in instead: **6.1456 °C** |
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
3. **The claim guard had a hole in its own marker list.** `CLAIM_MARKERS` originally
   included `"no "`, which is a substring of the very phrase it was meant to catch, so a
   bare "no movement verified" passed. Removed; the planted-claim tests now fail as
   designed, and the guard distinguishes assertion from quotation (backticks, `false`,
   "never", "not") instead of banning words.
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
7. **The honesty checks were proven able to fail.**
   `firmware/tools/tests/test_cg_w14_dossier.py` builds a miniature repository (tools +
   the real capture + this dossier), asserts the untouched copy exits 0, then plants one
   false claim at a time, re-pins `SHA256SUMS.txt` so a hash mismatch cannot be what
   tripped, and requires exit 1: *"no movement verified"* written into the QA report;
   `tolerance_value: 0.4` and `agreed_with_member_b: true` in the pairing input; the
   hot-side-contaminated mean re-labelled chamber air; `n=1` promoted to
   `DISTRIBUTION_COMPUTED`; a disturbance response asserted against 0 OPEN rows; an
   absolute developer path in drive-letter form inside a pinned artifact - seven false
   claims, each producing exit 1 - as does an eighth tamper case, an edit made after
   pinning, caught by the hash check. The same file carries two generator-guard cases
   proving `build_w14_artifacts.py` refuses to write an asserted false claim at all.

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

1. `.gitattributes` needs `evidence/A/W14/** -text` (not touched in this branch, per
   the file restrictions; the CSV/JSON are written LF-only and
   `validate_w14.py` fails on any CR byte in the meantime).
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

## 6. Not owned by this slice

| Item | Owner / status |
|---|---|
| Choosing the feature sets and running the A1 model ablation (B-W14) | Member B, on `ablation-support.csv` |
| Final A/B matching tolerance values | Members A and B jointly (A-W14-04) |
| Any physical session, door-open pilot or photograph | operator, supervised session |
| ROM-to-role remap, `firmware/main` changes, `docs/` edits | project-level; not touched |
| Digital-twin ingestion of these artifacts | Member C |
