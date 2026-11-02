# A-W14 — Role-aware spatial statistics and sensor-position QA (Member A)

Week: **W14** · Branch: `feat/a-w14-spatial-statistics` · Stacked on
`feat/a-w07-plant-repeatability` (HEAD `2e688be`, the W07 delivery head)
Owner: Member A · Status: **TOOLS + DOSSIER DELIVERED · SPATIAL STATISTICS LIMITED TO
ONE SESSION · DISTURBANCE RESPONSE NOT COMPUTABLE · PAIRING TOLERANCES TEAM_DEPENDENCY
· NON-MOVEMENT NOT VERIFIABLE FROM ARCHIVED DATA**

W14 supports Member B's one-sensor-versus-three-sensor ablation and the spatial
feature work **without changing the physical configuration**, exactly as docs/05A §23
requires. It adds three host tools and this dossier. It does not add a measurement:
the repository still holds **one** thermal session (957 rows, one `boot_id 56044b74`)
and **no** door-open event anywhere, so what is delivered is the method, the baseline,
the datasets from the runs that exist, and the honest boundary of each.

## 1. What W14 adds

| Piece | What it is |
|---|---|
| `firmware/tools/cg_w14_spatial.py` | A-W14-02/03: named sensor **feature sets** (single probe, pairs, the W07 air mean) computed over the *same rows*, with a per-row conditioning fingerprint as the proof of "same physical run"; per-pair gradients, max pairwise differences, door-event detection, and `require_air()`, which raises instead of averaging the hot side into an air statistic |
| `firmware/tools/cg_w14_sensor_qa.py` | A-W14-01: the sensor-position QA **method and baseline** — capture role labels and per-channel behaviour checked against the frozen record, every mismatch class naming what it would mean physically, output split into `CURRENT_VERIFIABLE` / `NEEDS_A_NEW_CAPTURE` / `NEEDS_PHYSICAL_EVIDENCE` |
| `firmware/tools/cg_w14_pairing.py` | A-W14-04: Member A's **input side** for the A/B matching tolerances in a form B can consume, with a structural guard that raises if any number ever appears under a tolerance-named key |
| `spatial-statistics.json`, `spatial-report.md` | the generated A-W14-03 numbers, labelled `SINGLE_SESSION_OBSERVATION`, with the gradient distribution `NOT_COMPUTABLE_AS_DISTRIBUTION` and the disturbance block `NOT_COMPUTABLE` |
| `ablation-support.json`, `ablation-support.csv`, `ablation-support.md` | the A-W14-02 datasets: 10 feature sets × 3 phases, long-format per-sample series (95 700 rows) joinable on `device_ms`, each row carrying `feature_terms`, `feature_roles`, `is_chamber_air`, `includes_hot_side` |
| `sensor-position-qa.json`, `sensor-position-qa.md` | the A-W14-01 baseline, the role-label check, the behaviour signature, and the protocol a new capture must meet |
| `pairing-input.json`, `member-b-handoff.md` | the A-W14-04 payload: what the data supports, what it cannot, join keys, the form a tolerance takes once sessions exist, and the asks for B |
| `build_w14_artifacts.py`, `validate_w14.py`, `SHA256SUMS.txt` | regeneration with `--check`, `--pins`, byte pins, and the honesty re-checker that re-derives every published number from the raw rows |
| `firmware/tools/tests/test_cg_w14_dossier.py` | proves the validator fails: a mini-repo copy passes untouched, then each planted false claim (non-movement, invented tolerance, hot-side air mean, `n=1` as a distribution, fabricated disturbance, absolute path, unpinned edit) exits non-zero |
| `firmware/tools/run_all_checks_w14.py` | six layers, including the W07/W06/W05/W04 regressions |

## 2. The headline numbers, all from the one real session

Driven (cooling) block, 600 samples, `tmean_airroles_v0` = mean(T1,T3,T4):

- **air-to-air max |ΔT| = 1.126 °C** (T1 centre vs T3 bottom, at `device_ms=518894`);
- **air-to-hot-side-surface max |ΔT| = 18.938 °C** — a factor of **16.8** apart, which
  is *why* T2 must never sit inside an air mean;
- the reference response itself is **-8.7083 °C**, W07's published figure, reproduced
  byte-for-byte by the W14 helper (differential test, not assertion);
- dropping one air probe from that mean moves it by at most **0.5833 °C** on identical
  rows; putting the hot-side surface in instead moves it by **6.1456 °C**
  (`tmean_chamber3_v0` = -2.5627 °C) — a measured feature-set sensitivity, and
  explicitly **not** a matching tolerance.

## 3. Definitions stay W07's definitions

Roles, representations and the hot-side flag are **imported** from
`cg_thermal_repeatability` (`AS_BUILT_ROLES`, `REPRESENTATIONS`, `terms_of`,
`includes_hot_side`), never restated. The single helper W07 does not expose — a mean
over an arbitrary term tuple, needed because A-W14-02 asks for one-sensor sets — is
pinned against W07's own `tmean` by a test over every registered representation, so the
two cannot drift. Chamber-air variants are checked against the role map at compute time
(`require_air`), and the 97 W14 tests (40 spatial, 25 QA, 21 pairing, 11 dossier-guard)
include the hot-side containment proofs at three levels: the label check, the planted
air-labelled-hot-terms defect, and a per-row re-check of every published CSV line.

## 4. What each deliverable can and cannot say

| Ask | What was delivered | What it does not say |
|---|---|---|
| A-W14-01 verify no movement since freeze | method + baseline + mismatch semantics, split into `CURRENT_VERIFIABLE` / `NEEDS_A_NEW_CAPTURE` / `NEEDS_PHYSICAL_EVIDENCE`, verdict `NOT_VERIFIABLE_FROM_ARCHIVED_DATA` | it cannot and does not claim the probes did not move: `#CG H8S schema=3` frames carry no ROM ids, so a channel is a slot name, not a proven probe |
| A-W14-02 ablation support | feature sets from the same rows, control proven by fingerprint | it is one run described several ways, so it carries no run-to-run information |
| A-W14-03 spatial statistics | per-pair gradients, max pairwise differences, per-probe agreement — all labelled `SINGLE_SESSION_OBSERVATION` | no gradient **distribution**, no disturbance response: `door_open` is `0` in 940 rows and `UNKNOWN` in 17, so the event was never applied |
| A-W14-04 pairing tolerances | Member A's input, structured for B to consume | no number in the tolerance slot, and no claim that anything is agreed |

## 5. Reproduce

```bash
py firmware/tools/run_all_checks_w14.py
py firmware/tools/cg_w14_spatial.py evidence/A/W04/tec-cooling-response-600s.csv
py firmware/tools/cg_w14_sensor_qa.py
py firmware/tools/cg_w14_pairing.py evidence/A/W04/tec-cooling-response-600s.csv
py evidence/A/W14/build_w14_artifacts.py --check
py evidence/A/W14/validate_w14.py
py -m unittest discover -s firmware/tools/tests -t firmware/tools/tests
```

## 6. Limits of this dossier

* **Host analysis of old captures.** No flash, no energized stage, no bench session, no
  probe moved. Nothing here is `PHYSICALLY_VERIFIED`, and the validator refuses the
  phrase as an assertion.
* **One session is one session.** Its baseline, cooling and recovery segments are
  published as segments of one boot with `independent_session: false`, never as three
  runs, and `n=1` is never promoted to a distribution.
* **The 2026-11-02 touch session is `PROBE_IDENTIFICATION`** and is refused before a
  number is computed — including as a QA baseline, because a hand-held probe is not a
  behaviour reference. `evidence/A/W02/sensor-consistency.csv` is likewise excluded: its
  probe positions were not yet frozen, so it is not a spatial input.
* **The pairing tolerances are not invented here.** A within-session spread and a
  run-to-run band are different physical quantities; `cg_w14_pairing` raises if a value
  ever appears under a tolerance key, and the validator re-runs that guard on the
  published file.
* **The generator once refused its own draft.** An early `member-b-handoff.md` line
  asserted a thing the captures cannot support and `build_w14_artifacts.py` exited
  non-zero rather than writing it; that refusal is now a durable test, not a footnote.
