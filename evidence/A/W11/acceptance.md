# A-W11 acceptance

Slice: W11 S4 refusal dataset tooling and S3 feasibility · Branch
`feat/a-w09-dataset-tooling` · Base `4d31fe5` · Docs `docs/05A` §20
S4 sessions run on a device: **NO** · Publishable S4 runs: **0** ·
Command observations in any committed capture: **0** · S3 verdict: **NO-GO**

W11 is **not** a fault-injection week and it does not pretend to have collected a
refusal dataset. It is delivered as **workflow-complete, physically uncollected**:
the four-lane S4 analysis, the refusal/physical-evidence validator, the S3
feasibility methodology and the run-expansion list exist, are host-verified, and
were run over the real committed captures. There is no physical refusal dataset, so
the deliverable is the analysis workflow plus exactly what the operator must record,
and the status of the dataset itself is REAL DATA NOT AVAILABLE. Nothing in this
dossier was simulated into a result: no publishable S4 run is claimed.

Status vocabulary (used everywhere in this dossier): IMPLEMENTED ·
HOST_VERIFIED · REAL_DATA_ANALYZED · PHYSICALLY_VERIFIED · NEED_USER_ACTION ·
TEAM_DEPENDENCY · BLOCKED_HARDWARE. No host test in this week may be read as
physical verification, and none is labelled as such.

## 1. Requirement matrix (docs/05A §20)

| ID | Canonical ask | Status | Evidence |
|---|---|---|---|
| **A-W11-01** | S4 method: create the fault **in software** (a test mode that intentionally refuses/blocks actuation) while keeping protocol visibility; never short a branch, bypass a fuse or damage the TEC | **IMPLEMENTED / HOST_VERIFIED** (method + validator) · **NEED_USER_ACTION** (no device has ever been put in that mode) | `S4-protocol.md` §1/§5 from `cg_w11_s4.S4_PROTOCOL`: the safe method, the three forbidden unsafe methods, and the hazard the protocol exists to catch - a harness reporting `SAFETY_BLOCKED` while the output is live. §9 is the operator recipe: 4 repetitions, attended, qualified electrical lane first. Nothing was injected: no branch shorted, no fuse bypassed, no TEC damaged, no fan obstructed |
| **A-W11-02** | S4 evidence: command/intention, applied state, PZEM no-active-response, thermal non-response - proving `command != electrical effect` | **REAL_DATA_ANALYZED** (device lanes over the 957-frame capture) · **REAL DATA NOT AVAILABLE → NEED_USER_ACTION** (the command lane) · **BLOCKED_HARDWARE / TEAM_DEPENDENCY** (electrical qualification) | The three device lanes are separate in real frames: `(1000, 999, 999)` in **600** frames and `(0, 0, 0)` in **357** of `evidence/A/W04/tec-cooling-response-600s.csv`; applied differs from requested in 600, read-back differs from applied in 0. S4-shaped disagreements exist: seq **227** (`COOLING`, duty 999, 0.0 A) and seq **827/828** (`COOLDOWN`, duty 0, 7.15 A then 0.56 A). All three are `electrically_qualified: false` because `current_status` is empty in all 957 rows and no `power_status` column exists. The **intent** lane has no device instance: `commands_observed: 0` in the CSV and 0 `#CG CMDACK` lines in `evidence/A/W04/g1/40-g1-boot-60s.log` (62 telemetry frames). So intent cannot be separated from application anywhere in this repository, and `command != electrical effect` is proven as a lane split, never as a physical instance |
| **A-W11-03** | Collect additional S1/S2 runs as B's run plan requires | **REAL DATA NOT AVAILABLE → NEED_USER_ACTION** · **TEAM_DEPENDENCY** (the plan itself) | `additional-valid-run-list.json` reuses the W09 run registry (same 6 capture ids, same 6 sha256 values - asserted) and measures usability per scenario: the one parseable physical capture gives **940/957** frames usable for S1 and for S2, **0** for S3 and S4; the other 5 sources are stated as unparseable by the delivered parser, never as zero. Additional valid runs: **0**, because 957 frames inside one `boot_id` (`56044b74`) are segments of the run W09 already registers, not new sessions. Nothing was invented to fill B's quota |
| **A-W11-04** | Conditional S3 feasibility: can a safe, repeatable thermal-effectiveness degradation be made with the frozen hardware? If not, NO-GO is acceptable; do not invent unsafe fan obstruction | **IMPLEMENTED / HOST_VERIFIED (methodology only, no run, no verdict of GO)** | `S3-go-no-go.md` + `s4-s3/s3-feasibility.json`: verdict **NO-GO**, 0 of 5 required measurements available, and all 6 candidate methods accounted for (3 NO-GO, 2 RECLASSIFIED into S2/S4, 1 REJECTED_BY_INSTRUCTION - the fan obstruction). §"What an S3 session must record" is the methodology: R1 instrumentation attestation, R2 qualified electrical state, R3 degradation setting and magnitude, R4 matched healthy baseline, R5 repetition count, R6 confounders, R7 not-done declaration. §"Why no committed capture can supply it" walks all 6 registry captures and names the measurement each falls short of, with a reason; sources the delivered parser cannot read are labelled **NOT CHECKED**, which is not reported as a failed check. No S3 run is claimed, listed or scheduled |
| Deliverables `S4-protocol.md`, `S4-runs/`, `S3-go-no-go.md`, `additional-valid-run-list` | **HOST_VERIFIED** | all generated by `build_w11_artifacts.py`; `--check` reproduces every artifact byte-for-byte; `S4-runs/index.json` publishes `publishable_run_count: 0` with the reason per audited source |

## 2. Pass-criteria walk

| Criterion | Result |
|---|---|
| intent may never populate the applied, electrical or thermal lane | **met** - `INFERRED_FROM_INTENT` is a forbidden source; `_lane()` raises `PromotionError`, `assert_no_promotion` re-checks a whole trace, and `S4-runs/host-fixture-refusal-trace.json` records the exact raised error as its purpose |
| a refusal is protocol evidence, not physical non-action (docs/02 §32.2) | **met** - a refusal reaching `ELECTRICAL_VERIFIED`/`THERMAL_VERIFIED` is rejected; an accepted command is not treated as a refusal; `thermal_non_response_proven: false` for the real log |
| a refusal may never show an applied action | **met** - `REFUSED_WITH_APPLIED_ON` is rejected unless the trace supplies explicit `applied_state_before_command`, in which case it is labelled `REFUSED_PREEXISTING_APPLICATION` and not credited to the command |
| `DUPLICATE_CANONICAL` may never show a second application (docs/02 §30.1) | **met** - `reapplied=1` on a canonical duplicate raises |
| the ACK set is handled as the firmware emits it | **met** - ACCEPTED / REJECTED / DUPLICATE_CANONICAL / EXPIRED / SAFETY_BLOCKED / INVALID_STATE / OUT_OF_RANGE are classified, and an unrecognised status is `+UNKNOWN`, never folded into a refusal or an acceptance |
| fail closed when the evidence is absent | **met** - an empty `current_status` is not OK; a missing lane is `NO_EVIDENCE_IN_THIS_SOURCE`; zero observations yield `NO_COMMAND_OBSERVATIONS` with all five legs `legs_never_observed`, and `score_run([])` proves nothing by default |
| command freshness is not reinterpreted in tooling | **met** - the W06 posture is inherited unchanged: expiry needs `created_at`/`expires_at` semantics, a TTL measured at device receipt does not establish a command's original age, and an unverifiable absolute expiry fails closed. No W11 module widens admission or relaxes that; `cg_command.c`'s fail-closed order is left as delivered |
| every excluded row is counted under a named reason | **met** - both comparisons publish `row_account` (scanned = compared + excluded, each exclusion one of the named reasons, plus `reasons_never_fired` so checked-and-found-none stays distinct from did-not-check). Over the real capture: 957 scanned, 957 compared, **0** excluded |
| where the capture cannot separate intent from application, it says so | **met** - `request_applied_divergence` publishes `intent_vs_application: "NOT SEPARABLE IN THIS SOURCE..."` beside the counts, because all three numbers are device-reported duty fields |
| one `boot_id`'s segments are never independent runs | **met** - the registry's single physical capture is listed as one candidate with `additional_s1_or_s2_runs_available: 0`; `S4-runs/index.json` has zero runs |
| chamber air never includes the TEC hot side; the geometry discrepancy is documented, never silently remapped | **met** - the slot basis is **read from W09** (`as-built-2026-11-02-frozen`, `cg_w09_export.FROZEN_SENSOR_GEOMETRY`), `t2` stays excluded, the capture's own role fields (`t2_role=HOT_SIDE`, `t1/t3/t4_role=UNASSIGNED`) are published next to it, and the `docs/01` 823-825 naming conflict is restated with the coordinator as owner |
| no host fixture is presented as a run | **met** - `is_physical_measurement: false` on the fixture, `analyze_capture(..., is_physical_measurement=...)` recorded per source, and the validator fails if the fixture ever hides it |
| S3 stays methodology, not a verdict of GO or invented data | **met** - verdict NO-GO, `available_now: false` on all 5 measurements, no method accepted, and `not_done` states that no fan obstruction, no hardware change and no S3 run is claimed |
| the run registry is reused, not duplicated | **met** - the run list and the S3 per-capture table both iterate `evidence/A/W09/run-registry.json`; tests assert capture ids and sha256 lists match it exactly |
| no absolute developer path in any artifact | **met** - every published path is repository-relative; the validator scans every pinned file for one |

## 3. What W09's registry did not carry, and how it was worked around

`evidence/A/W09/run-registry.json` has no geometry field: it registers captures,
boot ids, kinds and eligibility, but not the frozen probe positions. W11 needs them
for its thermal lane, so instead of re-deriving a second geometry (which could
drift from W09's), `s4-s3/lane-evidence.json` reads
`cg_w09_export.FROZEN_SENSOR_GEOMETRY` / `FROZEN_GEOMETRY_VERSION` - the same record
W09 published in `evidence/A/W09/exports/CG-S1-H8C-600S.json` - and publishes the
gap itself in `chamber_air_slot_basis.registry_gap`. `validate_w11.py`
(`geometry_failures`) fails the dossier if that attribution disappears, so the
workaround cannot silently become a second source of truth. **Requested of the
coordinator:** add a `sensor_geometry` block to the W09 registry so consumers read
it from the registry rather than from a module constant.

## 4. Proof that the validator can fail

Each mutation was made in a scratch copy of the tree held **outside the repository**
(a working directory named `_w11fix/`, not a git checkout, not shipped), then
`build_w11_artifacts.py` was re-run and **`SHA256SUMS.txt` was rebuilt with `--sums`**.
So in every case below the bytes on disk hash to the published pins and a
hash-only check would have passed: what stopped each one is the validator
re-deriving the claim from the pinned sources, plus the durable host tests. Paths in
the transcripts are repository-relative because this very file is scanned for
absolute developer paths.

**A - a missing probe declared available and the forbidden fan obstruction accepted**
(`cg_w11_s3_feasibility.py`: `M2-cold-side-temperature.available_now` -> `True`,
`C1-fan-obstruction.verdict` -> `GO`):

```text
$ py evidence/A/W11/build_w11_artifacts.py --check
W11 ARTIFACT CHECK: 9 artifacts reproduce exactly
$ py evidence/A/W11/build_w11_artifacts.py --sums
wrote SHA256SUMS.txt (13 files)
$ py evidence/A/W11/validate_w11.py
W11 DOSSIER: FAIL
  - an S3 measurement is claimed available on the frozen hardware
  - S3 candidate 'partially block the hot-side fan' was accepted
exit=1
$ py -m unittest discover -s firmware/tools/tests -t firmware/tools/tests -p "test_cg_w11*"
FAIL: test_no_required_measurement_is_available (S3Feasibility)
FAIL: test_the_fan_obstruction_is_rejected_by_instruction (S3Feasibility)
Ran 89 tests ... FAILED (failures=2)
```

**B - an unqualified electrical lane promoted to certified** (empty `current_status`
treated as OK in `cg_w11_s4.electrical_lane_from_frame` and in the disagreement scan):

```text
$ py evidence/A/W11/build_w11_artifacts.py --check
W11 ARTIFACT CHECK: 9 artifacts reproduce exactly
$ py evidence/A/W11/build_w11_artifacts.py --sums
wrote SHA256SUMS.txt (13 files)
$ py evidence/A/W11/validate_w11.py
W11 DOSSIER: FAIL
  - frame 227 was certified electrically although its current_status is empty
  - frame 827 was certified electrically although its current_status is empty
  - frame 828 was certified electrically although its current_status is empty
exit=1
```

**C - an S4 run invented in the published run list**
(`S4-runs/index.json`: `publishable_run_count`/`runs_available` -> 1, one run added,
pins rebuilt):

```text
$ py evidence/A/W11/validate_w11.py
W11 DOSSIER: FAIL
  - S4-runs/index.json does not reproduce from the delivered tooling
  - an S4 run is published that the evidence does not support
  - the S4 run list invented a run
exit=1
```

**D - the TEC hot side re-entering the chamber-air statistic** (the slot basis
published `t1/t2/t3/t4` instead of `t1/t3/t4`):

```text
$ py evidence/A/W11/validate_w11.py
W11 DOSSIER: FAIL
  - the TEC hot side re-entered the chamber-air slots
exit=1
FAIL: test_the_shipped_lane_evidence_passes_both_checks (GeometryAndRowAccountAreChecked)
```

**E - the `docs/01` 823-825 discrepancy note deleted from the generator** (six lines
removed from `chamber_air_slot_basis`, artifacts regenerated, pins rebuilt):

```text
$ py evidence/A/W11/validate_w11.py
W11 DOSSIER: FAIL
  - the docs/01 823-825 probe-naming discrepancy is no longer documented - silently
    remapping a slot would measure a different box than the project expects
exit=1
```

**F - the refusal fixture relabelled as device evidence**
(`is_physical_measurement: false` -> `true`, regenerated and re-pinned):

```text
$ py evidence/A/W11/build_w11_artifacts.py --check
W11 ARTIFACT CHECK: 9 artifacts reproduce exactly
$ py evidence/A/W11/validate_w11.py
W11 DOSSIER: FAIL
  - the refusal fixture is presented as device evidence
exit=1
```

**G - the promotion rule switched off** (`FORBIDDEN_SOURCES = ()`, so intent may fill a
device lane). The dossier build refuses to produce the artifact at all, and the tests
fail:

```text
$ py evidence/A/W11/build_w11_artifacts.py
  File "evidence/A/W11/build_w11_artifacts.py", line 254, in _promotion_demo
    raise RuntimeError("assert_no_promotion accepted an intent-derived electrical lane")
RuntimeError: assert_no_promotion accepted an intent-derived electrical lane
$ py -m unittest discover -s firmware/tools/tests -t firmware/tools/tests -p "test_cg_w11*"
FAIL: test_an_intent_derived_applied_lane_is_refused (LanesAreNeverDerivedFromIntent)
FAIL: test_an_intent_derived_electrical_lane_is_refused (LanesAreNeverDerivedFromIntent)
Ran 89 tests ... FAILED (failures=2)
```

**H - a deliverable shipped without a pin** (`S4-runs/invented-s4-run.json`, claiming
`thermal_non_response_proven: true`, added to the dossier; `--sums` re-pins only the
declared set):

```text
$ py evidence/A/W11/build_w11_artifacts.py --sums
wrote SHA256SUMS.txt (13 files)
$ py evidence/A/W11/validate_w11.py
W11 DOSSIER: FAIL
  - S4-runs/invented-s4-run.json is present in the dossier but not hash-pinned
exit=1
$ py -m unittest discover -s firmware/tools/tests -t firmware/tools/tests -p "test_cg_w11*"
FAIL: test_the_shipped_manifest_pins_exactly_the_shipped_dossier (DossierPinSetIsExact)
```

**I - a build cache pinned** (a `__pycache__/*.pyc` line appended to the manifest, as
would happen if it were generated by globbing a dirty tree):

```text
$ py evidence/A/W11/validate_w11.py
W11 DOSSIER: FAIL
  - __pycache__/build_w11_artifacts.cpython-314.pyc does not hash to the pinned value
  - __pycache__/build_w11_artifacts.cpython-314.pyc is a build cache, not evidence - it may never be pinned
exit=1
```

**J - the one limit, stated honestly.** Deleting the exclusion counter
(`exclusions[reason] = exclusions.get(reason, 0) + 1`) from
`find_command_electrical_disagreements` did **not** fail the validator once the
artifacts were regenerated and the pins rebuilt: the committed capture needs zero
exclusions (957 scanned, 957 compared), so the dossier-level reconciliation cannot bite
on this source. What stops it is the tool refusing to publish and the durable tests:

```text
$ py evidence/A/W11/build_w11_artifacts.py && py evidence/A/W11/build_w11_artifacts.py --sums
wrote SHA256SUMS.txt (13 files)
$ py evidence/A/W11/validate_w11.py
W11 DOSSIER: OK (13 pinned files, 957 frames re-read, 0 command observations,
0 publishable S4 runs, S3 NO-GO intact)                                   # not caught here
$ py -m unittest discover -s firmware/tools/tests -t firmware/tools/tests -p "test_cg_w11*"
ERROR: test_a_frame_with_no_applied_field_is_named_not_dropped (ExcludedRowsAreCountedAndNamed)
ERROR: test_an_unreadable_current_is_excluded_under_its_own_name (ExcludedRowsAreCountedAndNamed)
ERROR: test_every_frame_is_compared_or_exactly_one_exclusion (ExcludedRowsAreCountedAndNamed)
ValueError: the applied/current comparison lost or mislabelled rows: {'frames_scanned': 5,
 'rows_compared': 1, 'rows_excluded': {}, 'rows_excluded_total': 0, 'reconciles': False, ...}
Ran 89 tests ... FAILED (errors=3)
```

The named-exclusion rule is therefore proved on fixture rows that actually need
excluding; the first real capture with excluded rows will make the dossier check bite
as well. After every mutation the scratch tree was refreshed from the committed files
and `validate_w11.py` returned to `W11 DOSSIER: OK`.


## 5. Open items

| Item | Status | Owner | Needed to close |
|---|---|---|---|
| Execute the S4 refusal mode on a device | **NEED_USER_ACTION** | Member A + operator + supervisor | a supervised, energized rig; `S4-protocol.md` §9, one repetition at minimum, captured to a tracked file |
| A transport and an issuer that a device can receive from | **TEAM_DEPENDENCY** | Member C (canonical source), firmware owner | today admission requires the canonical network source and the firmware has no transport, so no command can reach a device at all |
| Qualified electrical lane (`current_status` / `voltage_status` / `power_status` emitted and OK) | **BLOCKED_HARDWARE / TEAM_DEPENDENCY** | firmware + bench (H8 capture encoding) | until then every S4 electrical claim stays a candidate; `power_w`/`energy_wh` currently have no status column at all |
| S3 thermal-effectiveness degradation | **BLOCKED_HARDWARE** (NO-GO) | operator + hardware owner | install cold-plate and hot-base probes, resolve `hot_base_max_c` and `cold_plate_min_c` in `firmware/h8-bench/main/h8_limits.c:27`, then re-run this assessment; the methodology in `S3-go-no-go.md` is ready for it |
| Additional valid S1/S2 runs | **NEED_USER_ACTION** · **TEAM_DEPENDENCY** (B's run plan) | Member A + operator, quantities from Member B | sessions executed against `evidence/A/W09/run-protocol-v1.md`, committed and hash-pinnable |
| Door attestation and `door_cycles`/`door_raw` in the export | **NEED_USER_ACTION** (carried from W10) | operator + firmware owner | S2 pairs and the door→response metric stay NOT COMPUTABLE without it |
| Probe naming discrepancy (`docs/01` 823-825 vs the frozen as-built record) | **TEAM_DEPENDENCY** | coordinator | a canonical decision; W11 documents it and remaps nothing |
| `sensor_geometry` missing from the W09 registry | **TEAM_DEPENDENCY** | W09 owner / coordinator | add the block so consumers stop reading a module constant (§3) |
