# A-W10 — S2 door-disturbance pilot, alignment and horizon support (Member A)

Week: **W10** · Branch: `feat/a-w09-dataset-tooling` · Docs `docs/05A` §19
Status: **TOOLING DELIVERED AND HOST-VERIFIED · DOOR→RESPONSE METRIC
NOT COMPUTABLE · S2 PILOT SESSIONS NOT RUN — REAL DATA NOT AVAILABLE**

The primary reproducible thermal disturbance of S2 has never been captured on
this rig. What W10 delivers is the door-event parser, the MC-38 transition
alignment rule, the duration/rise/recovery analysis, the physical pairing
tolerance estimator and the horizon-support analysis — run over the real
committed capture, which they correctly report as containing **no door-open
event**. No rise, duration or recovery is invented to fill that gap.

## 1. Files

| File | What it is |
|---|---|
| `README.md` | this file |
| `acceptance.md` | requirement-by-requirement status with the gaps named |
| `S2-protocol-v1.md` | A-W10-01/-02 deliverable: protocol candidates, MC-38 timing quantisation, per-boot attestation rule, safety prerequisites, capture recipe |
| `S2-pilot.csv` | A-W10-03 deliverable: the door-state segments the detector finds in the real capture, with the reason each is not an S2 pilot disturbance |
| `door-event-validation.csv` | 957 rows + header: per-frame door evidence and quality domain, so the "no open event" claim is checkable row by row |
| `pairing-physics-summary.md` | A-W10-04 deliverable: measured noise floor, minimum detectable disturbance per horizon, tolerance estimator's refusal |
| `s2-horizon/door-events.json` | full `detect_events` report over the real capture |
| `s2-horizon/pairing-physics.json` | noise profile + detection floor + tolerance, source-pinned |
| `s2-horizon/horizon-support.json` | A-W10-05: what the horizon support can state today |
| `s2-horizon/door-response-metric.json` | the door→response metric with `NOT_COMPUTABLE` and its cause |
| `s2-horizon/pilot-status.json` | `cg_w10_door.pilot_status` over the real report |
| `build_w10_artifacts.py` | regenerates the 9 derived artifacts; `--check`, `--sums` |
| `SHA256SUMS.txt`, `validate_w10.py` | byte pins and the re-checker |

## 2. Reproduce

```bash
py firmware/tools/run_all_checks_w10.py
py -m unittest discover -s firmware/tools/tests -t firmware/tools/tests -p "test_cg_w10*"
py evidence/A/W10/build_w10_artifacts.py --check
py evidence/A/W10/validate_w10.py
```

`run_all_checks_w10.py` prints the test files every selection resolves to and fails
if a selection resolves to nothing, so this verdict rests only on files tracked on
this branch (see `test_cg_w09_runners.py`); a pass seen in a working tree holding
another worker's untracked files is not a pass.

## 3. Real numbers, from the committed capture

Source `evidence/A/W04/tec-cooling-response-600s.csv`, boot `56044b74`, 957 rows.

* Door segments found: `UNKNOWN` 17 frames (15.99 s), `CLOSED_AS_REPORTED` 940 frames
  (939.0 s) — the second is the device's reported level, **not** a named physical
  state, because no attestation licenses it. **`OPEN` segments: 0. S2 pilot events:
  0.**
* 940 frames report `door_polarity=CONFIRMED`; 17 report `UNCONFIRMED` with
  `door_open=UNKNOWN`. `UNKNOWN` is kept as its own state and never renamed CLOSED.
* **`frames_usable_for_s2: 0`** — the W09 validity layer reports `DOOR_STATUS_ABSENT` on all
  957 rows (the derived table carries no `door_status` column), and the door domain is a
  required domain for S2, so no row of this capture is scenario-usable even before the
  missing open event. The door *rise* columns of `S2-pilot.csv` are therefore empty: the
  segment that would have carried them is not usable. That is a property of this encoding;
  a capture that keeps its door qualifier is judged by the same rule and can be usable.
* No operator attestation exists for boot `56044b74`, so every segment is
  `REPORTED_BY_FRAME_ONLY_NOT_PHYSICALLY_NAMED` and the detector refuses to call
  any of them a physical door state.
* The derived CSV carries **no `door_raw`, no `door_status` and no `door_cycles`**
  column values, so `frames_with_raw_and_confirmed_polarity = 0` and the MC-38
  cycle cross-check is `aligned: null` — not computable from this encoding.
* Measured noise (2 quiescent runs found, 209 frames pooled per probe):
  T1 σ 0.019032 °C, T3 σ 0.020866 °C, T4 σ 0.018964 °C, T2 σ 0.02457 °C
  (**excluded from chamber air: TEC hot side**). ADC quantisation floor
  0.018042 °C at 0.0625 °C resolution — the noise exceeds quantisation alone.
* Minimum detectable disturbance: **single frame 0.05383 °C** (conservative, no
  averaging assumption); chamber-air mean floor by horizon 30 s 0.00534,
  60 s 0.00378, 120 s 0.00267, 300 s 0.00169, 600 s 0.00119 °C.
* Pair-matching tolerance: **`null`, NEED_USER_ACTION** — 1 physical run; a
  tolerance is a between-run spread.

## 4. Limits of this dossier

* **No real door-open event exists**, so the door→response metric is
  `NOT COMPUTABLE`. `S2-pilot.csv` publishes the segments that do exist and the
  reason each is not S2 evidence; it contains no fabricated disturbance.
* **The MC-38 mapping is a switch whose two settings assign opposite states to
  every raw level**, so frames alone can never name their own door state: the ask
  is canonical in `docs/01` §8.1/§8.2 (door semantics are "subject to actual
  polarity mapping"; neither `HIGH = OPEN` nor `LOW = OPEN` may be assumed without
  physical verification), and the mapping table `cg_w10_door.MAPPING_BY_POLARITY`
  is complementary by construction. The code-level demonstration would need
  `firmware/h8-bench/main/h8_door.c`, which is tracked on no ref here, so that
  proof is labelled `UNCITABLE_UNTRACKED_SOURCE` in
  `evidence/A/W09/run-registry.json` instead of being quoted as if it were
  citable; the claim stands, its proof does not. The confirmation is a per-boot
  console command, and the alignment record states that `NEAR_HIGH` once made the
  firmware echo a stuck-high input as CLOSED.
* **The untracked H8 frames are not citable** and are not used here: the
  465-frame `door_open=1` block sits on boot `eec9f67f` with a polarity command
  sent on a different boot, so it classifies as `UNATTESTED_DOOR_TRANSITION`.
* **No ML horizon is selected here** (docs/05A §19 A-W10-05 says so explicitly);
  B receives the floor curve and the distributions it can freeze, not a choice.
* **The critical threshold is Member D's safety contract**, not a Member A
  number, so `door→critical` needs D's frozen threshold before it is computable.
* Host tests prove the rules (57 W10 tests); they do not measure the plant.
