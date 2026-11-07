# ColdGuard · Analysis Contract v1 (W04, Member B)

> Deliverables of **B-W04-01** (real analytical schema and checker),
> **B-W04-02** (EWT semantics), **B-W04-03** (AIW interface) and
> **B-W04-05** (physical-validity intake), Doc `05B` §32.
> The frozen outcome hierarchy itself lives in `metric-hierarchy.md`
> (**B-W04-04**). This contract freezes conceptual definitions and supported
> interfaces; it does not freeze a numeric threshold, horizon, persistence
> constant, response delay, calibration model or measured result.

| Field | Value |
|---|---|
| Owner | Member B |
| Parent docs | `00` §§0.3, 5.1, 5.3–5.4 · `01` §§1, 2.4–2.7, 6.4–6.6, 9, 18–24, 33, 35, 39, 42–46 · `02` §§4–5, 13.3, 14.2–14.3, 28–32, 35, 39, 51, 59–63 · `03` §§31, 38–49, 55–57, 68–74, 84–88, 92–93, 95–97, 119–122, 125, 133, 155, 158–164, 171, 174–180, 182, 190, 204 · `04` §§3.3, 11.1, 40 · `05B` §§6–7, 12–14, 26–27, 31–32, 41–44 |
| Tasks | B-W04-01, B-W04-02, B-W04-03, B-W04-05 |
| Implementation | `ml/src/coldguard_ml/intake.py`, `ml/src/coldguard_ml/evaluation_contract.py`, `ml/scripts/schema-check.py` |
| Status | v1 freeze of W04 conceptual definitions and interfaces; all numeric physical values remain provisional until their named gates |

Tier legend: **CANONICAL** (Docs `00`–`03` fix it) · **DERIVED** (follows from
CANONICAL + a stated assumption) · **IMPLEMENTATION_CHOICE** (B's executable
choice with no statistical/physical meaning change) · **TEAM_DEPENDENCY**
(A/C/D-owned input, never invented by B) · **PROVISIONAL_UNTIL_FREEZE** (unset
value + named gate) · **SCHEDULED_DEBT** (deferred mechanics with owner/week).

---

## 0. Scope and the W04 freeze boundary

W04 establishes a reliable boundary between six different claims:

1. a **real source representation** (what A or C actually emitted);
2. a **normalized analytical representation** (B's stable identity, time,
   quality, role and measurement fields);
3. **trusted measurement and provenance metadata**;
4. **scientific run eligibility** (whether the capture may enter a research
   population);
5. **frozen evaluation methodology** (EWT, AIW, metric hierarchy);
6. **provisional physical parameters awaiting evidence** (thresholds, bands,
   horizons, delays, tolerances).

The executable boundary is:

```text
source representation  →  normalized analytical representation  →  admission ladder
     (versioned)                    (lossless where available)        (fail-closed)
```

A successful parse is **never** an admission. The W04 checker must be able to
say: "this source is structurally valid and useful for diagnostic QA, and it
is still not eligible for a predictive dataset, for these reasons."

W04 does **not** implement W05 cadence/channel QA, W06 time-alignment or
response computation, W07 repeatability, W08 the full Gate B validator, W09
baselines, W10 features, W12 EWT campaign analysis, XGBoost training, a locked
holdout, physical A/B experiments, a serial-to-MQTT gateway, a database, a
registry service, or a new persistence system.

---

## 1. W04 traceability ledger

`Requirement → canonical clause → reused source → new work → acceptance evidence`

| Requirement | Canonical clause | Reused source | New W04 work | Acceptance evidence |
|---|---|---|---|---|
| **B-W04-01** real schema/checker | `05B` §32; `01` §§1, 6, 9, 18–20, 33; `02` §§4–5, 14.2–14.3, 60–61 | W01 data dictionary; W02 `Observation` validation; A W09 export + companion; C fixture/contract; A probe-role map | `intake.py` source adapters, normalized model, admission ladder; `schema-check.py` CLI | `test_intake_schema.py` schema/role/provenance/time/electrical cases; real-export CLI run |
| **B-W04-02** EWT semantics | `03` §§39, 45, 55, 175–176; `05B` §32; `01` §18 | W03 `metric-spec.md` §4; W03 plan §2 (P4) | EWT state machine and counterfactual guard in this contract; `compute_ewt` guard | `test_evaluation_contract.py` early/late/no-warning/censored/intervened cases |
| **B-W04-03** AIW interface | `03` §§56–57, 171, 173–174, 177; `02` §§5.1, 5.4; `05B` §32 | W03 `metric-spec.md` §5 | Timing provenance table; no-double-count rule; `compute_aiw` guard | `test_evaluation_contract.py` complete/missing/overlap cases |
| **B-W04-04** metric hierarchy | `03` §§52–53, 68–74, 84–88, 92, 99, 133; `05B` §32 | W03 plan §4.8, F1–F12; W03 `metric-spec.md` §§1–8 | `metric-hierarchy.md`; `MetricHierarchy` guard; amendment rule | `test_evaluation_contract.py` AP/PR-AUC, secondary promotion, sign, locked-holdout cases |
| **B-W04-05** invalid-run intake | `01` §§33, 45; `03` §§7, 31, 95–96; `04` §10.2; `05B` §32 | A W09 run index + export invalidation summary; A W12 dataset validity; W02 split/manifest rules | Admission states, A-ledger binding, exclusion codes, no-mutation rule | `test_intake_schema.py` A-ledger-invalid, missing-evidence, synthetic, duplicate-view, zero-run cases |

The executable evidence is the pytest suite plus the real A-export CLI run
recorded in the PR description. The W04 checker is not a substitute for the
W05 full telemetry QA or the W08 run validator.

---

## 2. Source representations and normalized schema (B-W04-01)

### 2.1 The three concepts are separate

**A. Source representation.** The original producer encoding. Each
representation has its own version namespace.

**B. Normalized analytical representation.** B's stable field model
(`Capture`, `RunIdentity`, `TimeSemantics`, `SensorRole`, `NormalizedRow`). It
preserves unknown and unavailable fields as unknown/unavailable; it does not
fill them.

**C. Scientific eligibility.** The admission ladder in §3. It is computed
after normalization and is never implied by source recognition.

### 2.2 Supported source representations

| Representation | Discovery key | Version namespace | Adapter scope |
|---|---|---|---|
| A evidence-grade run export | JSON top-level `export_version: w09-run-export-v2` + companion row-validity CSV | `w09-run-export/v2` | Full W04 analytical intake: identity, A validity summary/index, sensor roles, time domains, per-row quality, invalidation reasons, electrical/actuation fields, provenance hashes |
| C telemetry snapshot | JSON with `schema_version: 1` and the thermal/environment/door/electrical/actuation/quality sections | `coldguard.telemetry/v1` | One normalized snapshot through the existing W02 `Observation` validator; no run validity, scenario, controller, ROM or physical position is invented |

The A adapter reads the export JSON **and** its declared companion CSV. The
companion path is resolved beside the export, at the dossier root, or at the
repository root; parent-directory escapes are refused. The delivered CSV
header must equal `frames.columns_per_row` exactly. A declaration and a file
that disagree are a refusal, not a column-guessing opportunity.

### 2.3 Recognized but unsupported representations

| Representation | Discovery key | W04 behavior |
|---|---|---|
| Firmware H8S serial frames | first content line `#CG H8S schema=3` | `SERIAL_SCHEMA_NOT_BACKEND_WIRE` refusal. The serial schema is a **producer** representation, not the backend JSON `schema_version=1`. W04 does not implement a serial-to-analytical or serial-to-MQTT gateway. |
| Firmware TELEM serial lines | first content line `#CG TELEM` | Same precise refusal: a serial line is not a C MQTT JSON document. |
| A companion CSV alone | CSV header with A row-validity columns | `COMPANION_METADATA_MISSING`: rows without run metadata, time semantics, sensor roles and A validity are not analyzable by themselves. |
| Unknown JSON/CSV/log | no supported key | `UNRECOGNIZED_SOURCE_FORMAT`: no mapping is attempted. |

### 2.4 Version namespaces are not conflated

```text
firmware serial H8S            coldguard.h8s-serial/v3
firmware serial TELEM          coldguard.telem-serial/v1-3
A offline run export           w09-run-export/v2
C MQTT/backend JSON snapshot   coldguard.telemetry/v1
```

`w09-run-export-v2` is not `schema_version=2`; `schema=3` is not
`schema_version=3`; the A export's `schema_version: null` means the derived
encoding did not carry a per-row wire schema, not that a wire version is zero.

### 2.5 A source → analytical mapping

| Analytical concept | A source field(s) | Rule |
|---|---|---|
| Source artifact identity | export file + SHA-256; `provenance.sources[].sha256` | Export hash computed; every pinned source hash must be present. When the pinned file is in the repository, its bytes are re-hashed and a mismatch is a refusal; a repository-relative pin whose file is absent is a physical-qualification blocker (`PINNED_SOURCE_MISSING`), not an empty proof. A pin that cannot be verified against a checkout is `PINNED_SOURCE_UNVERIFIABLE` and also blocks physical qualification. |
| Physical vs synthetic | `is_physical_measurement`; source `is_physical_measurement` | Physical only when explicitly true. A non-physical export is provenance `NON_PHYSICAL`, never physical. |
| Run identity | `run_id`, `run_id_status`, `run_ids` | A single source-carried run_id is preserved. An unresolved multi-segment boot keeps `run_id = None` and every segment in `run_ids`; no joined id is fabricated. |
| Boot/device identity | `boot_id`, `boot_id_status`, `device_id` | `boot_id` preserved. `NOT_CARRIED_BY_THIS_ENCODING` becomes `device_id = None` with that status, not a fake device constant. |
| Firmware | `firmware_version` | Preserved or marked not carried. |
| Hardware configuration | `hardware_config_id` | Preserved as a **declared label**, status `DECLARED_NOT_VERIFIED` unless separate evidence verifies it. W12's evidence-derived identity and W24's as-built identity are not silently equated with the label. |
| Calibration | `calibration_id` (absent in the current export) | `None` + `NOT_AVAILABLE`. Never synthesized. |
| Source schema identity | `export_version`; `schema_version` | `export_version` is the source schema identity; per-row `schema_version` stays `None` when the encoding does not carry it. |
| Event time | `timestamp_utc`, `timestamp_utc_status`, `timestamp_semantics` | Device UTC is preserved only when present and consistent. `UNAVAILABLE` + `DEVICE_HAS_NO_WALL_CLOCK` is a source fact. |
| Relative time | `device_ms` | Boot-scoped uptime. Monotonic within a boot; never a global clock. |
| Host capture time | `host_capture_time_utc` | Separate host domain, preserved beside device time, never written into event time. |
| Sensor slot/ROM/position/role | `sensors[]` and row `t*_rom`, `t*_physical_position`, `t*_role` | Run-level sensor block is the role authority; row-level values must agree. ROM source and readback-verification status are preserved. |
| Chamber-air membership | `in_chamber_air_mean` | Explicit per sensor; a hot-side slot cannot be true. Unknown/conflicting membership stays unknown. |
| Door | `door_open`, `door_polarity` | Raw level becomes `OPEN`/`CLOSED` only under `door_polarity = CONFIRMED`; otherwise `UNKNOWN`. `UNKNOWN` is not `CLOSED`. The A domain quality remains authoritative. |
| Electrical | `voltage_v`, `current_a`, `power_w`, `energy_wh` | Values preserved even when unqualified; missing stays `None`; unqualified stays unqualified. |
| Actuation | `pwm_req_permille`, `pwm_applied_permille`, `pwm_readback_permille`, `state` | Requested, applied and readback are distinct. A derived `ON`/`OFF` is set only when the device state and applied duty are unambiguous; permille is preserved. |
| Quality | `quality` (overall), `producer_quality`, `thermal_quality`, `environment_quality`, `electrical_quality`, `door_quality`, `sequence_quality`, `provenance_quality` | Every domain preserved verbatim, including `UNKNOWN`. A quality value outside the supported vocabulary is a refusal. |
| Invalidation | `invalidation_reasons` per row; `invalidation.summary` | Reasons preserved verbatim. A's ledger is authoritative; B does not re-validate by plausible readings. |
| Unavailable fields | `row_contract.not_available_per_row` | Reported as declared unavailable fields; not silently dropped. |

### 2.6 C source → analytical mapping

A C payload is converted into the W02 `Observation` and validated by the
existing `validate_observation` path: exact `schema_version=1`, timezone-aware
`captured_at`, enum domains, instrument ranges, non-negative electrical
domains, duty range and VALID-section completeness. Then it is mapped into the
same normalized row model.

The C wire snapshot does **not** carry: ROM identity, physical position/role,
scenario certification, controller context, A run validity, clock-sync state,
or a synthetic/physical provenance flag. Those become explicit
unknown/unavailable states. A payload that self-labels as a synthetic fixture
(`note` containing "SYNTHETIC" and "not a physical measurement") is provenance
`SYNTHETIC`; an unlabeled payload is provenance `UNVERIFIED`, never physical by
default.

### 2.7 Time contract

The firmware may report:

```text
timestamp_utc = UNAVAILABLE
timestamp_utc_source = DEVICE_HAS_NO_WALL_CLOCK
```

These are **source facts**, not parse failures to repair with the host clock.

The normalized time model distinguishes:

| Capability | `EVENT_UTC` | `BOOT_SCOPED_UPTIME` |
|---|---|---|
| Event ordering within one boot | yes | yes |
| Causality for within-boot feature/label windows | yes, subject to clock trust | only under a later named within-boot analysis definition |
| Cross-boot ordering | only with synchronization evidence | **no** |
| Absolute command/response latency (AIW) | only with synchronization evidence | **no** |
| Host capture time as device time | **never** | **never** |
| Diagnostic QA | yes | yes |

Rules:

- host capture time is preserved as a separately labeled domain, never in
  `event_time_utc`;
- receive time, where present, is arrival evidence only;
- `device_ms` resets on every boot; rows are never joined across boots on
  uptime alone;
- where event-time semantics cannot be established, W04 provides a
  diagnostic-only representation and refuses predictive admission; it does not
  manufacture UTC.

### 2.8 Measurement and role contract

The current physical rig is **not** assumed to have canonical chamber-air
T1/T2/T3 roles. The authoritative as-built record places:

```text
t1  CHAMBER_CENTER       chamber air
t2  TEC_HOT_SIDE         hot-side surface, NOT chamber air
t3  CHAMBER_BOTTOM       chamber air
t4  CHAMBER_NEAR_DOOR    chamber air
```

Consequences fixed by W04:

- the literal `Tmean_air = mean(T1, T2, T3)` is **not** a chamber-air mean on
  this rig; it mixes a heatsink temperature into the plant variable;
- the literal `G_T = Tmax − Tmin` over T1/T2/T3 is a probe-disagreement
  statistic, not a chamber-air spatial gradient;
- a chamber-air aggregate uses only explicitly role-qualified slots
  (`t1`, `t3`, `t4` on this rig), via `chamber_air_mean` / the normalized
  `chamber_air_slots`; including `t2` raises a role error;
- a hot-side temperature is still a real observation — it is simply not a
  chamber-air observation;
- an unknown ROM, position or chamber-air membership stays unknown and makes
  role-dependent analyses inadmissible; it is never silently reassigned from a
  slot name or payload position;
- a position token outside the frozen vocabulary is refused rather than
  silently dropped to "unknown"; a typo must not shrink a chamber-air
  aggregate;
- a row-level raw probe role that says `HOT_SIDE` for a slot the sensor block
  marks chamber-air is a role contradiction, not a silent re-assignment;
- the canonical/as-built naming discrepancy remains an open A/team issue. W04
  records it; it does not claim it is resolved and does not edit Doc `01` or
  firmware.

### 2.9 Electrical contract

Single cooling branch only:

```text
cooling_voltage_v
cooling_current_a
cooling_power_w
cooling_energy_counter_wh
```

These refer to the cooling branch, not facility-wide consumption. There is no
INA226, second TEC, second actuator or invented total-system energy.

Rules:

- a missing or unqualified PZEM field stays missing/unqualified; it never
  becomes a zero-valued trustworthy measurement;
- a measured physical `0.0` is distinct from a missing value (`None`); the
  normalized row records which fields were actually measured;
- energy is integrated from sampled power under Doc `01` §35.2 / Doc `03`
  §72; the 1 Wh counter is a cross-check only, with reset/discontinuity
  handling; PWM quantitative energy remains provisional until characterization
  (Doc `01` §9.10);
- unqualified electrical values may appear in diagnostic QA but cannot support
  energy or health claims.

### 2.10 Executable checker

```bash
python ml/scripts/schema-check.py identify <source>
python ml/scripts/schema-check.py check <source> [--a-run-index PATH]
    [--source-format auto|a-w09-run-export-v2|c-telemetry-json-v1]
    [--format json|text] [--out PATH] [--require-eligible]
```

The CLI and the importable API share one path:
`load_capture` → `evaluate_admission`. There is no second validation branch.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Checker ran; source structurally valid. Zero eligible runs is a successful honest result, not a failure. |
| `1` | `--require-eligible` was set and no predictive admission exists, or an internal/IO error occurred. |
| `2` | Source representation unrecognized/unsupported or structurally invalid; precise refusal printed. |

The JSON report is deterministic (sorted keys, no timestamps, no local
absolute paths) and contains:

- source identity, format and schema namespace;
- structure: row/column counts, recognized fields, unknown fields, declared
  unavailable fields;
- provenance: physical/synthetic/unverified, pinned hashes and existence;
- time domain and trust capabilities;
- role summary: chamber-air, hot-side, unknown slots and per-sensor provenance;
- quality counts by domain;
- admission status, highest stage, blockers, per-scenario eligible rows,
  eligible S1/S2 run counts and predictive-dataset readiness;
- warnings.

No database, registry table, new persistence layer or new artifact family is
introduced.

### 2.11 Current real-export checker result

On the committed A export
`evidence/A/W09/exports/CG-S1-H8C-600S.json` with
`evidence/A/W09/s1-run-index.json`:

- 957 rows, 65 delivered columns, structural status `VALID`;
- provenance `PHYSICAL`; pinned source
  `evidence/A/W04/tec-cooling-response-600s.csv` hash verified;
- `run_id = None`, status
  `UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID`; source segments
  `run-00000000`, `run-00000001`; one boot `56044b74`;
- device identity `NOT_CARRIED_BY_THIS_ENCODING`;
- hardware configuration `CG-HW-001` is a **declared, unverified** label;
- calibration identity absent;
- time domain `BOOT_SCOPED_UPTIME`; device UTC `UNAVAILABLE`; clock
  synchronization not evidenced; host capture time absent in this derived
  table;
- roles: `t1` chamber center, `t2` TEC hot side (excluded from chamber air),
  `t3` chamber bottom, `t4` near door;
- thermal domain 957 `VALID`; producer 940 `DEGRADED` / 17 `INVALID`;
  environment, door and electrical 957 `UNKNOWN`; overall 940 `UNKNOWN` /
  17 `INVALID`;
- A run index: `valid_s1_run_ids_for_member_b = []`; the run is blocked with
  an unresolved run identity and a majority of unusable frames;
- admission: `EXCLUDED_OR_BLOCKED`, highest stage
  `USABLE_FOR_DIAGNOSTIC_QA`;
- eligible S1 runs = **0**; eligible S2 disturbances = **0**; predictive
  dataset readiness = **NOT_READY**.

This is the expected, acceptable W04 result. The checker also produces useful
structure/QA diagnostics for the measured capture. It does not claim a
training dataset exists.

---

## 3. Physical-validity intake and exclusion (B-W04-05)

### 3.1 Admission states

The internal model retains the required distinctions as a cumulative ladder
plus a terminal blocked state:

```text
SOURCE_RECOGNIZED
    → STRUCTURALLY_VALID
        → USABLE_FOR_DIAGNOSTIC_QA
            → PHYSICALLY_QUALIFIED
                → ELIGIBLE_FOR_PREDICTIVE_DATASET

any failed gate → EXCLUDED_OR_BLOCKED
   (highest_stage_reached is still reported)
```

| State | Meaning |
|---|---|
| `SOURCE_RECOGNIZED` | A supported producer representation was identified; no structural promise yet. |
| `STRUCTURALLY_VALID` | The declared structure, identities, time semantics and row contract are internally consistent. |
| `USABLE_FOR_DIAGNOSTIC_QA` | The capture can support diagnostic structure/quality inspection, including unqualified or synthetic captures with explicit warnings. It is **not** research evidence. |
| `PHYSICALLY_QUALIFIED` | Physical provenance, A's authoritative validity verdict, run/boot/device identity, hardware configuration verification, calibration identity, scenario identity and role provenance all pass. |
| `ELIGIBLE_FOR_PREDICTIVE_DATASET` | Physically qualified plus a non-empty eligible scenario population and a trusted event-time domain for predictive labels/EWT. |
| `EXCLUDED_OR_BLOCKED` | At least one gate failed; every reason is reported. This is the honest state, not a software failure. |

### 3.2 Gate order

1. **Recognition** — format/version support, exact namespace.
2. **Structure** — required fields, companion header/row count, identity
   contradictions, sequence monotonicity, sensor role consistency, vocabulary
   domains, pinned source hashes.
3. **Diagnostic QA** — non-empty rows, explicit time domain, no naive
   timestamps, provenance declared (physical / synthetic / unverified).
4. **Physical qualification** — physical provenance; A validity verdict;
   canonical run identity; boot/device identity; verified hardware
   configuration; calibration identity; scenario identity; known roles;
   hot-side exclusion.
5. **Predictive eligibility** — S1/S2 scenario population with eligible rows;
   trusted event-time domain; no synthetic or unverified provenance; all
   physical gates retained.

### 3.3 Authoritative A evidence

A's actual run index (`evidence/A/W09/s1-run-index.json`) and export
invalidation summary are the authority for run validity. Binding rules:

- a **runs** entry is matched by `run_id` when both sides carry one,
  otherwise by `boot_id` + `device_run_label`; contradictory run-entry
  identities are refused rather than silently selected. No match is
  `A_RUN_INDEX_ENTRY_MISSING`, never a pass;
- a **blocked** entry matches on any strong identity (`run_id` or
  `boot_id`); when no strong identity is comparable, an exact run label is
  used. A strong match wins even if another identity disagrees, and the
  disagreement is reported as `LEDGER_IDENTITY_CONTRADICTION`. A blocked
  entry that shares no identity does not invalidate an unrelated run;
- a run is valid only when the index explicitly grants validity or lists it
  in `valid_s1_run_ids_for_member_b`; a blocked-ledger match is `INVALID`,
  and the blocked ledger wins even if the same id also appears in a valid
  list or carries `is_valid: true` (`CONTRADICTORY_LEDGER`);
- validity is **scenario-scoped**. The S1 list grants S1 only; a future
  index may carry `is_valid` + `valid_for_scenarios`. An S2 run is never
  admitted from an S1 grant; missing scenario scope is
  `SCENARIO_VALIDITY_NOT_GRANTED`;
- a run/boot status other than `SOURCE_CARRIED_SINGLE` is not a lawful dataset
  join identity, even if a string is present: `RUN_ID_UNRESOLVED` /
  `BOOT_ID_UNRESOLVED`;
- a validity grant is not bound to a capture whose own run identity is
  unresolved; the evidence object stays `UNKNOWN` even if an index entry
  looks valid;
- the valid-id list and every ledger entry must have a well-formed identity;
  malformed list/entry types are `A_RUN_INDEX_INVALID`, not coerced;
- the export summary alone is **not** a verdict: without an index it yields
  `PHYSICAL_VALIDITY_EVIDENCE_MISSING`;
- an explicit A-ledger `INVALID` run is excluded even when temperatures look
  plausible; B never overrides A's physical verdict;
- hardware-configuration verification, calibration verification and clock
  synchronization are accepted only when explicit evidence is present. The
  current A ledger does not verify the configuration (W12 reports
  `config_verification = UNVERIFIED`, `authorized_provenance_valid = False`,
  `dataset_pooling_eligibility = UNQUALIFIED`) and no calibration id exists;
  therefore those gates are blocked for the current real capture;
- `UNKNOWN` is never promoted to `VALID`; absence of a record is not an
  empty proof.

### 3.4 Exclusion and invalidation reasons

The admission result preserves, at minimum:

- valid / invalid / aborted status and explicit invalidation reasons;
- unknown hardware configuration or unverified declared configuration;
- unknown/unqualified calibration;
- run/boot/sequence contradiction or unresolved run identity;
- unsuitable scenario or experiment phase;
- untrusted critical channel (door/environment/electrical/producer);
- missing relevant event coverage (S2 door disturbance);
- sensor-position/ROM/role mismatch or unknown;
- unsynchronized timing for time-dependent analysis;
- physical versus synthetic provenance;
- incomplete required A-side evidence.

S2 specifically requires an observed, timing-qualified door disturbance.
A's current `w09-run-index-v1` hand-off is S1-scoped: its
`valid_s1_run_ids_for_member_b` list cannot certify an S2 disturbance. S2
admission therefore remains a TEAM_DEPENDENCY until A supplies an S2-scoped
validity list; B never reuses the S1 list for S2.

Reason codes are machine-readable and stable; the report lists each with the
gate at which it blocked admission.

### 3.5 Current real-data behavior

Unless newer evidence proves otherwise, the expected scientific admission
result is:

```text
eligible S1 runs = 0
eligible S2 disturbances = 0
predictive dataset readiness = NOT_READY
```

This is an acceptable W04 checker result. A synthetic fixture is never
presented as a certified physical run. The checker never mutates A's evidence,
never regenerates an exclusion ledger to erase a physical limitation and never
converts an invalid capture into a valid research run.

### 3.6 W02 integration

When eligibility later feeds dataset/split operations:

- the original run identity is retained; exclusions carry their reasons
  forward;
- W02 pair-lineage checks, dataset/run schema checks, and P1/P2/P3
  disjointness remain authoritative;
- multiple run groups are never claimed from row counts or same-boot labels
  alone;
- W04 does **not** create or open a locked test manifest;
- W04's admission result is an input to W05/W08, not a replacement for them.

### 3.7 Synthetic and fixture rule

A fixture may prove tooling, schema handling or admission logic. It may not
become physical evidence through conversion. The C fixture self-identifies as
synthetic and stays `SYNTHETIC`; a C payload without a provenance label stays
`UNVERIFIED`; neither is physically qualified.

---

## 4. EWT semantics (B-W04-02)

### 4.1 Conceptual invariant

```text
t_predictive:
    first valid persistent predictive warning

t_reactive:
    first qualifying reactive criterion

EWT = t_reactive - t_predictive
```

Both times must be established on the **same eligible,
non-predictively-intervened trajectory**. Positive EWT means the persistent
warning came earlier than the reactive criterion. A negative EWT is a late
warning and is reported, not discarded. No warning is missed-warning
accounting, **not** `EWT = 0`.

### 4.2 Required declarations for every EWT result

| Element | W04 requirement |
|---|---|
| Event/run identity | `run_id`, event identity, trajectory identity and source provenance recorded; no anonymous EWT. |
| Event-time domain | Absolute UTC with synchronization evidence, or a declared trusted relative domain. Untrusted/mixed domains are refused. |
| Warning persistence | First warning that satisfies the frozen persistence semantics; a flicker is not a valid warning. |
| Reactive criterion | Depends on D's reactive threshold semantics; B does not invent the threshold. |
| Censoring | An unobserved reactive crossing is censored, counted as censored support and excluded from EWT; no crossing time is invented. |
| First warning | Multiple warnings collapse to the first valid persistent one for the primary EWT. |
| Repeated warnings | Counted as warning episodes/burden; they are not extra EWT events. |
| Missed event | Reported in missed-event accounting with its denominator; never converted to zero EWT. |
| Negative EWT | Allowed and reported as a late warning, with the same provenance as a positive value. |
| Missing synchronization | `UNTRUSTED_TIMESTAMPS`; no EWT. |
| Untrusted timestamps | Refused; arrived/received time is not a substitute. |
| Result provenance | Warning definition, persistence parameters, event series identity, code version and input artifact ids recorded. |

### 4.3 Result states

| State | `ewt_s` | Meaning |
|---|---|---|
| `ESTIMABLE` | numeric (may be negative) | Both the first valid persistent warning and the reactive crossing are observed on one eligible trajectory in one trusted domain. |
| `MISSING_WARNING` | `None` | No valid persistent warning; missed-event accounting. |
| `MISSING_REACTIVE_CROSSING` | `None` | Reactive crossing not observed; censored, never imputed. |
| `INADMISSIBLE_INTERVENED_TRAJECTORY` | `None` | Controller B (or any predictive intervention) changed the trajectory; the counterfactual crossing is unknown. |
| `UNTRUSTED_TIMESTAMPS` | `None` | Event-time domain missing, untrusted or unsynchronized. |
| `MISSING_PROVENANCE` | `None` | Run/event identity or the warning/persistence definitions are absent; the result cannot be audited. |

The executable `EWTProvenance` object requires a non-empty `run_id`,
`event_id`, `warning_definition` and `persistence_definition`; `compute_ewt`
returns `MISSING_PROVENANCE` rather than an anonymous number.

The executable guard is `coldguard_ml.evaluation_contract.compute_ewt`. It is
an interface/state check, not a W06 event-alignment engine.

### 4.4 Counterfactual guard

A Controller B-intervened physical trajectory is **not admissible for naive
offline EWT**. Predictive intervention can change whether and when the
critical boundary occurs. If B prevents the crossing, the unobserved
counterfactual time is unknown: do not compute fake EWT from a crossing that
never happened. Closed-loop physical questions belong to the paired A/B
population (P5), not to offline EWT (P4).

### 4.5 Worked illustrative timelines

All values are illustrative, not data.

| Case | `t_predictive` | `t_reactive` | Result |
|---|---:|---:|---|
| Early persistent warning | 100 s | 160 s | `ESTIMABLE`, **EWT = +60 s** |
| Late persistent warning | 200 s | 160 s | `ESTIMABLE`, **EWT = −40 s** (late, counted against usefulness) |
| No warning | — | 160 s | `MISSING_WARNING`; missed event, never EWT = 0 |
| Non-persistent flicker | 100 s (not persistent) | 160 s | `MISSING_WARNING`; not a valid first warning |
| Censored observation | 100 s | not observed | `MISSING_REACTIVE_CROSSING`; counted as censored, no invented time |
| Controller B intervened | 100 s | no counterfactual | `INADMISSIBLE_INTERVENED_TRAJECTORY` |
| Unsynchronized clocks | 100 s | 160 s | `UNTRUSTED_TIMESTAMPS` |

### 4.6 Freeze boundary

W04 freezes conceptual event identity, warning-persistence shape, missing-state
policy, sign convention and reporting semantics. It does **not** freeze:

- a numeric warning threshold or persistence constant (W15/D policy);
- a numeric reactive threshold (D);
- a primary horizon (W13);
- a measured EWT distribution (W12 and later evidence);
- the full W09 baseline event evaluator or W12 campaign analysis.

---

## 5. AIW analysis interface (B-W04-03)

### 5.1 Conceptual expression

```text
AIW = t_critical - t_warning - T_system - T_physical
```

`T_system` is the measured sensing + inference + policy + command overhead;
`T_physical` is the measured command-to-plant response delay. The W04
deliverable is the **interface specification**. Actual time alignment and
response-window computation belong to W06 and later evidence stages.

### 5.2 Required timing provenance

| Required field | Owner | Source / artifact | Trust requirement |
|---|---|---|---|
| Sample acquisition time | A | Edge sample timestamp, or boot-scoped uptime for ordering only | Event-time domain and clock status recorded; uptime alone cannot support a cross-domain absolute latency |
| Event timestamp / relative-time domain | A/C | Telemetry event time or explicit uptime | Domain declared; no host substitution |
| Backend/transport delay | C | Receive time − event time (requires sync) | Clock synchronization evidence |
| Feature/inference latency | B | Monotonic inference span | Measured, not nominal |
| Policy decision latency | D | Policy/decision timestamp | Measured, policy-versioned |
| Command publication/transport | C | Publish timestamp and transport record | Publication is not execution |
| Device receipt/ACK | A/C | Device receive/ACK record | ACK is not electrical actuation |
| Electrical response | A | PZEM response relative to applied command | Measured, qualified channel |
| Thermal response | A | DS18B20 response relative to electrical response | Measured, role-qualified channel |
| Critical boundary crossing | B/A | Authoritative critical-event series | Trusted event-time domain |
| Event/run/command identity | B/A/C/D | `run_id`, event id, `command_id`, prediction id | Complete chain, no anonymous interval |
| Timing uncertainty and method | All | Per-component method, clock domain, uncertainty | Recorded; no single undifferentiated "latency" |

### 5.3 No double counting

Timing components are intervals. Components within a chain must not overlap;
`compute_aiw` refuses overlapping components instead of summing them twice.
Sequential stages are added once. Every measured component carries a measured
`uncertainty_s` (0.0 is valid for an exact counter span) and a clock domain.
Mixed clock domains are `NOT_ESTIMABLE` until W06 supplies alignment evidence;
they are never subtracted as if they shared a clock. A component with an
unknown or untrusted measurement is not replaced by a nominal value, a
hardcoded guess or a single-sample "distribution".

### 5.4 No stage equivalence

The interface must not equate:

- publish acknowledgement with device command execution;
- device ACK with electrical actuation;
- electrical response with thermal recovery.

These are distinct evidence stages. A verified physical intervention requires
both an electrical response and a thermal response; an ACK alone is not
physical verification.

### 5.5 Missing-data rule

If a system latency or physical response latency is unavailable or
unqualified:

```text
AIW = NOT_ESTIMABLE
reason = measured input missing/untrusted
```

The result carries the missing component names. No substitute nominal latency
and no hardcoded guess are used. A measured single response sample is **not** a
response-delay distribution: the current A hand-off reports one
command→electrical sample (1.094 s) and labels it as a single sample, so it
cannot by itself support a distributional AIW claim.

### 5.6 What would enable a future estimate

- A: repeated measured step responses with a stated distribution and
  uncertainty, on a qualified electrical/thermal channel;
- C/D: timestamped and synchronized policy, publication, receipt, ACK and
  command records;
- A/C: event-time synchronization evidence across the domains used;
- B/W06: the alignment and response-window computation under this interface;
- a complete event/run/command identity chain.

Until then, AIW stays `NOT_ESTIMABLE` with the missing-input reason.

### 5.7 Freeze boundary

W04 freezes the interface, required provenance, missing-data rule and
non-equivalence rules. It does not produce a numeric AIW, a latency
distribution, a response window or a W06 alignment implementation.

---

## 6. Cross-document consistency

This contract is consistent with the existing B contracts:

| Companion | Relationship |
|---|---|
| `data-dictionary-v0.md` | Field semantics, identity, quality, missing-data and forbidden-field rules are reused; W04 does not re-define them. |
| `claim-data-matrix.md` | RQ2/RQ4 outcome families are unchanged. W04 resolves the exposure-unit and primary-outcome choices that the matrix left PROVISIONAL at the statistics/metric freeze: °C·s, thermal exposure primary, recovery time secondary. |
| `leakage-risk-register.md` | LRK-09 (intervention), LRK-12 (row multiplicity), LRK-13 (time semantics), LRK-14 (missing ≠ zero) and LRK-15 (configuration identity) are enforced at intake. |
| `artifact-convention.md` | W04 adds no namespace, registry service or artifact class; run identity and dataset/split identities remain W01/W02. |
| `statistical-analysis-plan-v0.md` | P1–P6, the paired unit, the `I_i = Y_A − Y_B` convention and the F1–F12 freeze schedule are unchanged. |
| `metric-spec.md` | W04 freezes definitions/interfaces and the hierarchy; the numeric gates F1–F12 remain in force. |
| `metric-hierarchy.md` | The primary predictive metric, primary physical outcome, secondary/diagnostic outcomes and amendment rule are frozen there. |

Explicit consistency checks:

- run validity has one authority: A's ledger + export summary; B never
  re-validates by plausible numbers;
- P1/P2/P3 remain disjoint and run-grouped; W04 does not open a split;
- device time and host time are never conflated;
- a hot-side probe is never chamber air;
- energy is cooling-branch only; integrated power is primary, counter is
  cross-check;
- EWT is offline/non-intervened only; AIW requires measured components;
- no horizon, threshold, persistence constant or calibration is frozen here.

### 6.1 A/C/D dependencies

| Dependency | Owner | Status |
|---|---|---|
| Valid run IDs + invalid reasons | A | A W09 index exists; current valid S1 list is empty |
| Hardware-configuration verification and signoff | A/team | W12: `UNVERIFIED`; W24 as-built identity differs from the `CG-HW-001` label |
| Calibration identity | A | Does not exist on the current rig |
| Door disturbance event + timing | A | No committed door-open event; W10 protocol is NEED_USER_ACTION |
| Qualified PZEM channel | A | W12/W09: `UNQUALIFIED`; status fields absent |
| Clock synchronization evidence | A/C | Not present in the current export/schema |
| Event/command timeline | C | `events`/experiments realization is C W07 |
| Policy timing / reactive semantics | D | TEAM_DEPENDENCY; numeric values provisional |
| W06 alignment / response windows | B | SCHEDULED_DEBT, W06 |

### 6.2 W05/W08 handoff

- **W05** uses the normalized rows and admission report for cadence/channel QA,
  missingness, flatline, duplicates and physical-state plots.
- **W08** uses the admission result as an input to the full Gate B validator;
  W04 is not a substitute.
- A dataset builder must carry the original run identity and exclusion reasons
  forward; it must not count repeated export views as independent runs.

---

## 7. Out of scope and change control

Out of scope: W05–W16 implementation, physical experiments, hardware
energization, canonical-document edits, A/C/D file edits, MLflow/database/
registry infrastructure, serial-to-MQTT gateway, locked holdout, model
training and numeric physical thresholds.

Change control: this contract changes via a Member-B PR. No later change may
relax a CANONICAL rule, silently convert an unsupported source, upgrade an
unknown to valid, or turn a provisional value into a measured fact without its
named gate. Any amendment to the metric hierarchy must be a recorded,
disclosed amendment (see `metric-hierarchy.md`).

---

*Contract ends. It freezes how real sources, eligibility and evaluation
interfaces are judged; it computes no ColdGuard result.*
