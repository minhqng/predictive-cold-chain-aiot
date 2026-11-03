# A-W09 acceptance

Slice: W09 evidence-grade data collection · Branch `feat/a-w09-dataset-tooling` ·
Base `4d31fe5` · Docs `docs/05A` §18
Physical S1 session run: **NO** · Valid S1 runs certified: **0** ·
Electrical values qualified: **NO**

W09 is **not** a complete data-collection week. It is delivered as
**workflow-complete, physically uncollected**: the acquisition, QC, invalidation,
export and checklist machinery exists, is host-verified, and was run over the one
real thermal capture in the repository; the S1/S2/S4 sessions themselves have not
happened and are named as open instead of being simulated.

Status vocabulary (used everywhere in this dossier): IMPLEMENTED ·
HOST_VERIFIED · REAL_DATA_ANALYZED · PHYSICALLY_VERIFIED · NEED_USER_ACTION ·
TEAM_DEPENDENCY · BLOCKED_HARDWARE.

## 1. Requirement matrix (docs/05A §18)

| ID | Canonical ask | Status | Evidence |
|---|---|---|---|
| **A-W09-01** | Run checklist: before-run hardware config, sensor identity, PZEM range, initial state, door, storage online; after-run end reason, manual intervention, anomaly, validity candidate | **HOST_VERIFIED** (checklist exists and is machine-readable) · **NEED_USER_ACTION** (nobody has executed it on a run) | `run-protocol-v1.md`/`.json`: 20 gates, 9 BEFORE_RUN / 2 DURING_RUN / 9 AFTER_RUN, 18 blocking, every gate anchored to a canonical doc line. 6 gates are HOST_ONLY because firmware has no storage and no transport — the tool refuses to label them observable. 62 tests in `test_cg_w09_export.py` cover the protocol shape, including "every named item of A-W09-01 has a gate" |
| **A-W09-02** | Collect ~4 valid S1 baseline runs per Doc 03 planning | **REAL DATA NOT AVAILABLE → NEED_USER_ACTION** | The machinery ran: the one real candidate (`evidence/A/W04/tec-cooling-response-600s.csv`, 957 rows, **940 thermally usable, 0 usable for the S1 scenario**) is parsed, qualified, exported and indexed. No row of this table can carry the S1 scenario, because the derived CSV dropped the door, BME humidity/temperature and PZEM-power qualifiers the scenario needs — see §2. `run-registry.json` publishes `s1_candidates_available: 1`, `s1_runs_certified_valid: 0` with the reasons. **Zero** S1 runs were collected; nothing here stands in for them. The operator needs to execute `run-protocol-v1.md` on an energized, configured rig and keep the source qualifiers |
| **A-W09-03** | Physical invalidation logging (sensor moved, manual touch, fan anomaly, missing key telemetry, unexpected power event); never delete an invalid attempt | **HOST_VERIFIED** · **REAL_DATA_ANALYZED** | `cg_w09_validity.py`: 31 reason codes declared across 7 domains, `EXCLUDED_SESSION_CLASSES = ("PROBE_IDENTIFICATION", "TOUCH_IDENTIFICATION")`, no delete/remap path anywhere (a row is labelled and kept). Over the real capture: 17 rows are `SNAPSHOT_INVALID`/`DOOR_STATE_UNKNOWN`/`DOOR_POLARITY_UNCONFIRMED`, 957 rows carry `DOOR_STATUS_ABSENT`/`AIR_C_STATUS_ABSENT`/`RH_PCT_STATUS_ABSENT`/`POWER_W_STATUS_ABSENT`, and all 957 are retained in the export and in `exports/CG-S1-H8C-600S.row-validity.csv`. Tests in `test_cg_w09_validity.py` cover the touch-session refusal, the absent-qualifier blocking, the never-observed cooling state and the closed quality vocabulary |
| **A-W09-04** | Healthy response reference: electrical active range, OFF range, thermal baseline, gradient | **REAL_DATA_ANALYZED** (thermal) · **BLOCKED_HARDWARE/TEAM_DEPENDENCY** (electrical qualification) | `healthy-ranges.json`: active 600 frames / OFF 335 frames / cooldown 5, thermal baseline per physical position, gradients, cadence (956 intervals, mean 999.99 ms), per-probe noise. Every electrical lane carries `usable_for_a_health_claim: false` because the source has no producer status for it |
| Handoff B — valid S1 IDs | **IMPLEMENTED / HOST_VERIFIED**, result: **empty list** | `s1-run-index.json` → `valid_s1_run_ids_for_member_b: []`, `blocked_run_ids` states that the source `run_id` is ambiguous inside one `boot_id`. B gets measured usability per capture, not a guess |
| Handoff C — run-manifest edge fields | **HOST_VERIFIED** | `handoff-fields.md`, derived from the export schema, with ROM source and physical position per slot |
| Handoff D — healthy ranges | **HOST_VERIFIED** | `healthy-ranges.json` |

## 2. Pass-criteria walk

| Criterion | Result |
|---|---|
| every exported row carries run_id, boot_id, hardware_config_id, firmware_version, sensor ROM, physical position, timestamp/uptime semantics, measurement-quality state, experiment phase, invalidation reason, source provenance | **met, and now measured** — the companion CSV delivers **65 columns on 957/957 rows**, including `quality_by_domain` as one `{domain}_quality` column per domain, `invalidation_reasons`, `dedup_key`, `device_id`, `hardware_config_id`, `firmware_version`, `source_path`/`source_kind`/`source_line_index` and `t{1..4}_rom`/`t{1..4}_physical_position`. `exports/CG-S1-H8C-600S.json` → `frames.row_contract` states the same set, and the fields no encoding can carry per row are stated per field in `frames.row_contract.not_available_per_row` as `NOT AVAILABLE (<reason>)` (`timestamp_utc`, `host_capture_time_utc`, `device_id`, `calibration_id`, `schema_version`) instead of being dropped. `_assert_complete()` checks the rows against that contract and `validate_w09.py` compares the published header against the declaration, so a claim of columns the file does not carry cannot return — it used to: this row claimed 26 columns with three named fields that did not exist in a 24-column file |
| fail closed on a missing field | **met** — absent ≠ satisfied: a status column the encoding does not carry emits `{FIELD}_STATUS_ABSENT` at `UNKNOWN` (docs/01 §19.4), which is a blocking severity (`BLOCKING_SEVERITIES = {INVALID, UNKNOWN}`), so door/environment/electrical absence removes the row from every scenario that needs that domain. `MASKS_ABSENT` stays DEGRADED because docs/01 §19.2 documents that degraded path; a qualifier nobody wrote is not a documented degradation. The cooling state has its own code: `COOLING_STATE_UNOBSERVED` (§17.8 separates ON/OFF from never observed), and an unrecorded quality token ranks as `UNKNOWN` instead of falling through to `VALID` |
| one boot_id's segments are never independent runs | **met** — the two source `run_id` segments stay inside one export; no joined identifier is invented; the run is blocked from B's list and the reason is published |
| a host fixture never becomes physical data | **met** — `is_physical_measurement=False` raises in `build_run_export` with no override flag; 3 registry captures are classified `HOST_FIXTURE_NOT_A_RUN`; `validate_w09.py` re-checks it |
| byte-reproducible artifacts, repository-relative paths only | **met** — `--check` reproduces 9/9; the validator scans every pinned file for absolute developer paths |
| validator pins hashes and re-checks verdict honesty | **met** — `validate_w09.py` re-derives 957 rows from the CSV, re-runs the validity layer, compares all published counts, and fails if any honest verdict was softened |
| durable claims are separated from phase snapshots | **met** — §4 of the README labels every claim **MUST-KEEP** (rules: an absent qualifier is `UNKNOWN` and never a pass, a slope names its fit method, one boot's `run_id` segments are never joined, `PROBE_IDENTIFICATION` stays excluded, host tests are not physical verification, T2 is `TEC_HOT_SIDE` and never in chamber air) or **PHASE SNAPSHOT** (the figures of the single real thermal session filed today). `validate_w09.py` demands the durable tokens in every revision and the snapshot figures only while `run-registry.json` lists one real thermal capture, and **refuses** the single-session wording once a second is filed — so the honesty check cannot become a lock that fails the day the study succeeds. Exercised in both directions by `test_cg_w09_dossier_claims.py` |
| tests fail when a rule breaks | **met** — 163 W09 host tests (`validate_w09.py` re-counts them and refuses a README that quotes a stale figure); the failover demonstration is in §4 |

## 3. What W09 does **not** claim

* No `PHYSICALLY_VERIFIED` status anywhere: the S1 session never happened, and no
  host test is described as physical verification.
* No energy, power or current value is cited as health evidence.
* No chamber-air mean includes T2; `docs/01` §20.1 literally averages T1/T2/T3,
  which on this rig mixes a heatsink temperature into a chamber-air state. The
  literal value is reported **and** labelled contaminated; the naming discrepancy
  against `docs/01` lines 823-825 stays open as a project issue.
* No clock synchronisation is assumed: absolute command expiry is not weakened,
  and `device_ms` is exported as uptime, never as wall time.

## 4. Proof that the validator can fail

The dossier is only worth its verdict if a softened claim is caught. Two
mutations were made to derived artifacts on disk and the checker was re-run
exactly as recorded below; the artifacts were then restored by regenerating them.

```text
$ py - <<'PY'   # fake the certification of S1 runs that were never collected
  p = pathlib.Path('evidence/A/W09/run-registry.json')
  p.write_text(p.read_text(encoding='utf-8').replace(
      '"s1_runs_certified_valid": 0', '"s1_runs_certified_valid": 4'),
      encoding='utf-8', newline='\n')
PY
$ py evidence/A/W09/validate_w09.py
W09 DOSSIER: FAIL
  - run-registry.json does not hash to the pinned value
  - run-registry.json does not reproduce from the delivered tooling
  - the registry certifies S1 runs that were never collected
exit=1

$ py - <<'PY'   # offer the unqualified electrical lane as health evidence
  p = pathlib.Path('evidence/A/W09/healthy-ranges.json')
  p.write_text(p.read_text(encoding='utf-8').replace(
      '"usable_for_a_health_claim": false', '"usable_for_a_health_claim": true'),
      encoding='utf-8', newline='\n')
PY
$ py evidence/A/W09/validate_w09.py
W09 DOSSIER: FAIL
  - healthy-ranges.json does not hash to the pinned value
  - run-registry.json does not hash to the pinned value
  - run-registry.json does not reproduce from the delivered tooling
  - healthy-ranges.json does not reproduce from the delivered tooling
  - healthy-ranges.json now offers unqualified electrical values as health evidence
  - the registry certifies S1 runs that were never collected
exit=1

$ py - <<'PY'   # file a second real thermal session, keep the single-session prose
  p = pathlib.Path('evidence/A/W09/run-registry.json')
  reg = json.loads(p.read_text(encoding='utf-8'))
  clone = json.loads(json.dumps(next(c for c in reg['captures']
                                     if c['scenario_screen'])))
  clone['capture_id'] = 'W0X-SECOND-SESSION'
  reg['captures'].append(clone)
  p.write_text(json.dumps(reg, indent=2, sort_keys=True) + '
',
               encoding='utf-8', newline='
')
PY
$ py evidence/A/W09/validate_w09.py
W09 DOSSIER: FAIL
  - run-registry.json does not hash to the pinned value
  - run-registry.json does not reproduce from the delivered tooling
  - README.md still says 'only real thermal capture' with 2 real thermal sessions registered: a PHASE SNAPSHOT claim kept past its phase is an overstatement, not evidence
exit=1

$ py evidence/A/W09/build_w09_artifacts.py && py evidence/A/W09/build_w09_artifacts.py --sums
$ py evidence/A/W09/validate_w09.py
W09 DOSSIER: OK (13 pinned files, 957 rows re-derived from the committed capture,
honest verdicts intact)
exit=0
```

The same run catches a fabricated `run_id` join, a non-physical run entering the
index, a certification of S1 runs that were never collected, a missing
`PROBE_IDENTIFICATION` exclusion, an absolute developer path in any artifact, a
README that calls the week complete, a pinned file that left the folder unpinned
or a `__pycache__` entry that got pinned, a file carrying CR bytes (which would
re-hash on checkout, since `.gitattributes` normalises text to LF), a README that
quotes a stale derived figure, and - the third block above - a **PHASE SNAPSHOT**
claim kept after the phase ended. The reverse direction is covered by
`test_cg_w09_dossier_claims.py`, which re-runs the same check against a registry
that lists a second real thermal session and asserts that the H8-only numbers are
*no longer demanded*: an honesty check that fails the day the study succeeds is a
lock, not a check.

## 5. Open items

| Item | Owner | Needed to close |
|---|---|---|
| S1 baseline runs (target ~4) | Member A + operator | an authorized, energized, configured session executed against `run-protocol-v1.md`, captured to a tracked file |
| Electrical qualification | Firmware/B (transport + producer status) | `current_status`/`voltage_status`/`power_w_status` populated at the source, or a contract that labels the lane permanently unqualified |
| `run_id` semantics inside one `boot_id` | Firmware owner (C for the contract) | a rule for whether a boot may carry several `run_id` segments; until then the case stays blocked, not guessed |
| Probe naming discrepancy (`docs/01` 823-825 vs as-built) | coordinator | a canonical decision; no silent remap is allowed here |
| H8 raw frames, W07 probe-identification records | worktrees `A-W04-tec-commissioning`, `A-W07-plant-repeatability` | committed on the integration branch before they can be cited from this dossier |
