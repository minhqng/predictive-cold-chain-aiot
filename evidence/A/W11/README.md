# A-W11 — S4 safe actuation-response fault, S3 feasibility and run expansion (Member A)

Week: **W11** · Branch: `feat/a-w09-dataset-tooling` · Docs `docs/05A` §20
Status: **TOOLING DELIVERED AND HOST-VERIFIED · NO PUBLISHABLE S4 RUN ·
S3 = NO-GO · ADDITIONAL S1/S2 RUNS: REAL DATA NOT AVAILABLE**

## 1. Files

| File | What it is |
|---|---|
| `README.md` | this file |
| `acceptance.md` | requirement-by-requirement status with the gaps named |
| `S4-protocol.md` | A-W11-01/-02 deliverable: the four evidence lanes, the promotion rules, the forbidden unsafe methods, the real three-lane divergence found in the committed capture with its row accounting, the frozen chamber-air slot basis, and the capture recipe |
| `S3-go-no-go.md` | A-W11-04 deliverable: the feasibility **methodology** — 5 required measurements, 6 candidate methods, what a session must record (R1-R7), per-capture shortfalls over the W09 registry — verdict **NO-GO**, no run and no invented data |
| `additional-valid-run-list.json` | A-W11-03: per-capture, per-scenario measured usability and what a new run needs |
| `S4-runs/index.json` | the S4 run list: **0 publishable runs**, with the reason per audited source |
| `S4-runs/host-fixture-refusal-trace.json` | a labelled host fixture proving the refusal validator bites (not device evidence) |
| `s4-s3/s4-trace-real-capture.json` | `build_s4_trace` over the real capture: 0 commands + the device-lane audit |
| `s4-s3/refusal-analysis-real-log.json` | `cg_s4_refusal.analyze_capture` over a real device log with telemetry and no command lines |
| `s4-s3/lane-evidence.json` | lane view of a real active frame, divergence counts, disagreement candidates, the row accounting, and the frozen chamber-air slot basis |
| `s4-s3/s3-feasibility.json` | machine form of the NO-GO assessment |
| `build_w11_artifacts.py` | regenerates every derived artifact; `--check`, `--sums` |
| `SHA256SUMS.txt`, `validate_w11.py` | byte pins and the re-checker |

## 2. Reproduce

```bash
py firmware/tools/run_all_checks_w11.py
py -m unittest discover -s firmware/tools/tests -t firmware/tools/tests -p "test_cg_w11*"
py evidence/A/W11/build_w11_artifacts.py --check
py evidence/A/W11/validate_w11.py
```

## 3. Real numbers, recomputed from committed sources

`evidence/A/W04/tec-cooling-response-600s.csv` (957 frames, boot `56044b74`):

* requested/applied/read-back tuples: `(1000, 999, 999)` in **600** frames,
  `(0, 0, 0)` in **357** — applied differs from requested in 600 frames,
  read-back differs from applied in 0. Three separate device claims.
* no-active-response candidate: **seq 227** — `state=COOLING`, applied duty 999,
  `current_a=0.0`.
* residual-response candidates: **seq 827, 828** — `state=COOLDOWN`, duty 0, current
  still 7.15 A then 0.56 A.
* Every one of those currents is **unqualified** (`current_status` empty in all 957
  rows, no `power_status` column): `electrically_qualified: false`, so they are
  candidates for an S4 signature, never certified electrical evidence.
* Command observations in that capture: **0**. In
  `evidence/A/W04/g1/40-g1-boot-60s.log`: **62** telemetry frames, **0**
  `#CG CMDACK` lines → verdict `NO_COMMAND_OBSERVATIONS`,
  `thermal_non_response_proven: false`, `s4_run_publishable: false`.
* S4 thermal lane compares against the measured single-frame floor
  **0.05383 °C** over chamber-air slots t1/t3/t4 (T2 excluded).
* Row accounting, both comparisons: **957 scanned, 957 compared, 0 excluded**. The
  four exclusion reasons (field absent / value unreadable, for applied duty and for
  current) are published per comparison and fired zero times here, which is a
  checked-and-found-none claim, not an un-checked one.
* Intent is **not** separable from application in any committed source: the three
  duty numbers are all device-reported fields, and there is no command observation
  to compare them against. `s4-s3/lane-evidence.json` carries that limit next to
  the divergence counts so the divergence can never be read as an intent claim.
* Additional valid S1/S2 runs available today: **0** (the one parseable physical
  capture is already registered as a single candidate: 940/957 frames usable for
  S1 and S2, 0 for S3 and S4).

## 4. Limits of this dossier

* **No device has ever received a command in this firmware.** There is no
  transport, canonical-source admission rejects every other issuer, and expiry
  fails closed as `EPOCH_UNSYNCHRONIZED` because the clock is unsynchronised. The
  command→applied→electrical→thermal ladder therefore has no physical instance
  anywhere in this repository; `NEED_USER_ACTION` + `TEAM_DEPENDENCY` (Member C's
  issuer, Member B's qualified electrical lane).
* **A refusal verdict is protocol evidence, not physical non-action.** docs/02
  §32.2; the hazard S4 exists to catch is a harness reporting `SAFETY_BLOCKED`
  while the output is live, which is why intent may never populate the applied,
  electrical or thermal lane (`assert_no_promotion` raises, and the fixture
  artifact records the exact `PromotionError`).
* **`DUPLICATE_CANONICAL` may never show a second application** (docs/02 §30.1),
  and a refusal status may never show an applied action.
* **S3 is NO-GO on instrumentation, not on opinion**: 0 of 5 required
  measurements exist (no cold-plate probe, no hot-base probe —
  `firmware/h8-bench/main/h8_limits.c:27`), and all 6 candidate methods either
  violate a constraint (3 NO-GO), get reclassified as S2/S4 (2), or are rejected
  by instruction (1). No fan obstruction was invented and no S3 run is claimed.
* **S3 is delivered as methodology, not as a result.** `S3-go-no-go.md` states
  what a session must record (R1 instrumentation attestation, R2 qualified
  electrical state, R3 degradation setting and magnitude, R4 matched healthy
  baseline, R5 repetitions, R6 confounders, R7 not-done declaration) and then
  walks all 6 registered captures naming the measurement each falls short of;
  sources the delivered parser cannot read are labelled **NOT CHECKED**, which is
  not reported as a failed check.
* **Host fixtures are not runs.** `S4-runs/host-fixture-refusal-trace.json`
  carries `is_physical_measurement: false` and exists to prove the validator
  refuses promotion.
* **The probe geometry is inherited, not re-decided.** The thermal lane uses the
  W09-frozen as-built record (`as-built-2026-11-02-frozen`: T1 chamber centre, T2
  TEC hot side, T3 bottom, T4 near door), which contradicts `docs/01` 823-825 (T1
  door / T2 centre / T3 far-opposite). The capture's own role fields disagree with
  both (`t2_role=HOT_SIDE` in all 957 rows, `t1/t3/t4_role=UNASSIGNED`), so they are
  published next to the frozen positions and **nothing is remapped**: the canonical
  naming decision is the coordinator's (`TEAM_DEPENDENCY`, same open item W09 filed).
* **One `boot_id` is one run, not several.** The 957 frames are two segments
  (`boot_id 56044b74` only), so they are listed as segments of the W09-registered
  candidate and `additional_s1_or_s2_runs_available` stays 0.
* The W11 host tests in `firmware/tools/tests/test_cg_w11_s4.py` prove the rules;
  they are not physical verification, and their count is not part of the evidence.

## CURRENT HANDOFF (2026-11-07)

The accepted real S1/S2 dataset is published at `evidence/A/SOURCES/20261107/datasets/`
(18 runs, 9,293 measured frames, manifest + SHA256SUMS + standalone regeneration).
Earlier sections of this document are historical snapshots of the weeks when this
dataset did not yet exist; verdicts above describe those snapshots, not the current
package. Consumers: read `README.md` + `manifest.json` in that directory first.
