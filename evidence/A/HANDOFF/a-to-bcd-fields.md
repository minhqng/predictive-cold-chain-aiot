# A → B / A → C / A → D handoff fields (docs/05A §6.1-§6.3)

## CURRENT FIELD AVAILABILITY (2026-11-09 — read this first)

Everything below the "Historical snapshot" marker was written against the single 957-row
H8-C capture and is retained for traceability. Current availability is against the
**accepted real dataset** `evidence/A/SOURCES/20261107/datasets/` (18 runs/segments,
9,293 rows, per-run CSVs with per-field status, manifest + SHA256SUMS) and the
**supplementary 2026-11-09 S1 trial** `evidence/A/SOURCES/20261109/s1/s1-20261109T081304Z/`.

### §6.1 A → B — current

| Field | Current state | Source |
|---|---|---|
| valid/invalid run status | **AVAILABLE AND QUALIFIED** for the 18 accepted runs (dataset classification DATASET_ACCEPTED_S1 x4, DATASET_ACCEPTED_S2 x5 windows, flagged recovery/holdover segments); the new 2026-11-09 trial carries its own acceptance-verification.json | `datasets/run_index.csv`, `quality_report.md`, trial host-summary |
| independent run identity | **AVAILABLE**: `run_id` + host window per run; `boot_id` is the independence key (one run = one `boot_id`); the H8-C two-run-ids-in-one-boot case stays excluded and is not hidden | `run_index.csv` (boot ids listed) |
| `hardware_config_id` | **AVAILABLE**: `CG-HW-001` emitted by the canonical firmware inside every schema-3 frame (not inferred from a session string) | schema-3 frames, pin map v2 |
| `calibration_id` | **NOT AVAILABLE — honestly `UNRECORDED`**; no calibration measurement was ever taken on this rig. Do not invent one | frames carry `calibration_id=UNRECORDED` |
| sensor ROM + placement | **AVAILABLE, source-recorded**: per-run `{slot}_rom` + `{slot}_physical_position`; placement OPERATOR_FROZEN (T1 centre, T2 hot side, T3 bottom, T4 near door), role fields stay `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` (W23-03 labels deferred) | dataset CSVs; `evidence/A/W07/geometry-v1.md` |
| chamber-air roles | **AVAILABLE, rule-stated**: Tmean air = mean of T1/T3/T4 (all-OK rule); **T2 is hot-side and is never averaged in**; gate on the probe-role field, not the slot name | `firmware/tools/cg_probe_roles.py`; dataset derivation |
| applied cooling state | **AVAILABLE AND QUALIFIED in the accepted runs**: duty/current/power statuses recorded per frame in schema-3 (the old "empty validity columns" situation applies only to the H8-C CSV) | dataset CSVs |
| PZEM V/I/P/E | **AVAILABLE WITH STATUS TOKENS** (v/i/p/e + `power_validity`); electrical_valid_rate of the 2026-11-09 trial 0.99667 (2 PZEM timeouts at capture start) | trial verification; dataset CSVs |
| electrical validity/quality flags | **AVAILABLE** in schema-3 frames; remain **unqualified against an external reference** (A-W15-03: self-consistency is not accuracy) | frames + W15 dossier |
| door disturbance timestamps | **AVAILABLE** for the 4 accepted S2 windows (MC-38 transitions are the timing authority) | `datasets/raw/s2-door-20261107/` |
| physical response delays | **AVAILABLE** from campaign captures (command→electrical median from real transitions) | `measurement_summary.csv` |
| pairing context | **PARTIAL**: pairing physics evidence delivered; final tolerance freeze belongs to B (A-W14-04/A-W16-03 remain B-dependent) | `pairing-physics.json` analogs, coverage-matrix |
| provenance + checksums | **AVAILABLE**: manifest + SHA256SUMS for every dataset input/output; every 2026-11-09 trial file hash-pinned | both packages |

### New 2026-11-09 S1 trial — exact admissibility levels

1. **Capture execution acceptance: PASS.** Read-only 600 s capture, 600/600 schema-3 frames
   at 1 Hz, zero bytes written, zero commands, single boot `c0e43470` recorded from the boot
   banner inside the file, fault bits 0, `coverage 0.99833`, `thermal_valid_rate 0.99833`,
   `electrical_valid_rate 0.99667`. Verified twice (capture-time verifier + independent
   recompute from the committed bytes with the store parser). Store verdict: **A-W11-03 PASS**.
2. **Physical run validity (W09 protocol): VALID as an additional passive S1 baseline run.**
   Gates satisfied: HWCONFIG (CG-HW-001, pin map 2, canonical `cg-w06-0.1.0`), BOOT-IDENTITY
   (one boot per run, banner in-file), SENSOR-IDENTITY (ROMs in `#CG ROM` lines, matches
   frozen map), INITIAL-STATE (first valid frame recorded), output stage DISABLED +
   BOOT_SAFE_OFF (no actuation anywhere). GATE-DOOR-STATE is the honest weak point: raw
   level 0 in 600/600 frames and operator-confirmed closed, but `door_status=UNVERIFIED`
   because no attestation command was sent (read-only trial — the historical runner sent a
   `DOOR ATTEST` command; this one deliberately did not). Treat door evidence as
   raw-level + operator attestation, not device-attested.
3. **S1 dataset admission: NOT ADMITTED to the published 18-run package.** The accepted
   dataset is a frozen, hash-pinned package whose committed `manifest.json` is never
   modified; re-admission as run 19 would require the re-export/regeneration cycle, which
   was deliberately not done in this handover. The trial is published as a supplementary
   self-contained run (trial.json + raw + verification + SHA256SUMS) at
   `evidence/A/SOURCES/20261109/s1/s1-20261109T081304Z/`.
4. **Member B training-pipeline eligibility: ELIGIBLE AS SUPPLEMENTARY S1 BASELINE
   MATERIAL, with these restrictions**: (a) passive only — no cooling response, no duty
   ladder, no S2 disturbance; (b) `door_status=UNVERIFIED` at the frame level (see 2);
   (c) 2 of 600 frames had PZEM TIMEOUT (electrical NULL at capture start);
   (d) `calibration_id=UNRECORDED`; (e) environment quality degraded (no BME280 humidity
   on CG-HW-001; frame `quality` aggregate UNKNOWN 599 / INVALID 1 — thermal quality is
   VALID 599 frames and that is the channel B should use); (f) tmean_air min/mean/max
   26.1667 / 26.3829 / 26.625 C, gradient mean/max 0.4018 / 0.5 C, in family with the four
   accepted S1 trials (≈29.46–29.86 C from the warmer 2026-11-07 ambient) — absolute
   levels differ with ambient temperature, so pooling across days must be ambient-aware;
   (g) one capture must not be rebinned into multiple "runs". It does NOT by itself
   constitute a qualified cooling-performance or thermal-response measurement.

### §6.2 A → C — current deltas vs the historical table

- Schema-3 frames are the canonical real-device grammar; the read-only collector
  (`tools/acceptance/read_only_capture.py`) now classifies a line as telemetry only when it
  declares the `#CG TELEM` grammar **and** the canonical parser validates it
  (`firmware/tools/cg_telemetry_schema.py`); malformed `#CG TELEM` lines are not counted.
  Legacy H8 pwm-token frames remain accepted as legacy evidence (grammar tests included in
  the 1165-test host suite).
- Host timestamps are ISO-8601 with fractional seconds and `±HH:MM` offsets and are
  handled by the acceptance parser (round-trip + reject-bogus tests committed); device
  wall-clock timestamps do not exist and are never fabricated — frames carry
  `timestamp_utc=UNAVAILABLE, timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK` and hosts
  stamp receipt time.
- Device/boot/sequence semantics unchanged and verified live in the 2026-11-09 log:
  `boot_id` changes at capture open (open resets the board), `seq` is per-boot-frame
  (`seq=1..600`, no gaps/duplicates in this trial), boot banner lines are captured in-file.
- Capture read-only guarantee: DTR and RTS are de-asserted immediately at open and the tool
  contains no write path; `bytes_written=0`/`writes_to_port=NONE` are asserted from tool
  output by the acceptance runner, not by assertion in a comment.
- Command/ACK: the canonical console grammar and typed ACK exist host-verified, but no
  transport-backed ACK integration is claimed — A-W06-01/02/03/06 sit INCOMPLETE on
  Member C's merged contracts, and no applied-state or ACK claim in the new trial exists
  (zero commands). Statuses were physically verified where marked (this trial), host-tested
  elsewhere; nothing transport-related is claimed as physically executed.

### §6.3 A → D — current deltas vs the historical table

- The OFF envelope, zero-duty floor, healthy-ON observations and the **7.15 A zero-duty
  anomaly stay exactly as historically documented** — the anomaly is NOT resolved by the
  new trial: the trial ran with the slot-3 TEC-branch fuse OUT (branch electrically open)
  while the PZEM kept its own logic feed (slot-2, per the as-built runbook), so
  `v=11.95 / i=0.000 A` in every frame evidences an open branch, not a classification of
  the H8-C zero-duty current question.
- A-W08-02 fuse decision recorded PASS (2026-11-05): **15 A** against both measured bases
  (bench peak 5.03 A needs ≥6.29 A; full-duty record 9.35 A steady needs ≥11.69 A) —
  with the explicit limitation that **no certified ampacity, insulation class, routing/
  bundling record or conductor marking exists** (operator statement of record: no further
  ratings obtainable). D's gate A decision (six TEC operating limits incl. hot-side max,
  default-provisional 55 C) is the *unresolved* input that blocks A-W08-03/W16-01.
- W15-04 PWM Go/No-Go: **NO-GO** recorded (no characterized canonical duty ladder; duty
  request gated to 0 in the delivered config). Never read this as a PWM rating.
- Everything else in the historical §6.3 table remains accurate as written.

### §5 definition-of-done cross-check (current)

Producible today that the historical list said was missing: dataset + validity records
(18 runs), real door disturbances + pairing evidence, per-run response delays, spatial
statistics, and the additional S1 expansion run. Still not producible without the gated
physical session: a supervised loaded COOLING_STEP under frozen D limits (A-W08-03 →
A-W09-04, A-W16-01..03), certified ampacity/reference-meter accuracy, physical labels
(A-W23-03), and Member C transport-backed command/ACK integration.

## HISTORICAL SNAPSHOT (pre-dataset era — retained for traceability)

Field-by-field, against what the repository could produce at the time (single H8-C 957-row
capture). Every statement below was true then; where current evidence differs, the current
sections above win.

Field-by-field, against what the repository can actually produce today. Every "available"
below was checked against the committed capture columns or a delivered branch, not asserted.

The single real thermal session is `evidence/A/W04/tec-cooling-response-600s.csv`: 957 rows,
one `boot_id` `56044b74`, columns verified this pass — `t1..t4_status` = `OK` in 957/957;
`current_status` and `voltage_status` **empty** in 957/957; no `power_status` column at all;
`door_open` = `0` in 940 and `UNKNOWN` in 17 with `door_polarity` `CONFIRMED` 940 /
`UNCONFIRMED` 17; `limits_policy` = `APPROVED` 957; `physical_output` empty 957;
`pwm_applied_permille` 999 in 600 rows and 0 in 357.

## §6.1 A → B (training data)

| Required field | State | Source / why |
|---|---|---|
| valid / invalid run status | **Tool ready, zero valid runs** | W09 validity engine on `feat/a-w09-dataset-tooling`; today it rejects the only session rather than passing it |
| `run_id` | **Present but not an independence key** | the capture holds two values (`run-00000000` 226 rows, `run-00000001` 731 rows) **inside one `boot_id`**, so run_id cannot certify a separate run; W09 blocks both instead of handing them over |
| `hardware_config_id` | **NOT AVAILABLE as a justified identity** | no dedicated column exists. The only discriminators are the `session` string (embeds image `01cedce3...`) and `limits_policy`. Deriving a stable id from those is exactly what W12's `configuration_of` got wrong (two different images collapsed to one key) and it is under repair |
| `calibration_id` | **DOES NOT EXIST** | no calibration measurement has ever been taken on this rig; inventing an id would fabricate provenance |
| sensor identity / placement | **PARTIAL** | placement is frozen by operator response (`evidence/A/W07/geometry-v1.md` §1). The in-frame `t1..t4_role` fields are `UNASSIGNED` except `t2_role=HOT_SIDE`, and the ROM ids come from `coldguard_config.h:229-235` *by source*, never read back from the devices |
| door disturbance timestamps | **NO SUCH EVENT EXISTS** | `door_open` is `0`/`UNKNOWN` across all 957 rows and across every other committed capture. Session S-3 is the only way to produce these |
| applied cooling | **AVAILABLE** | `pwm_applied_permille` (+ `_req`, + `_readback`) |
| PZEM V/I/P | **AVAILABLE, UNQUALIFIED** | `voltage_v` / `current_a` / `power_w` / `energy_wh` are present, but their validity fields are empty or absent, so they are values without a recorded check. B must treat them as unqualified features |
| quality flags | **PARTIAL** | probe quality is real (`t*_status` all `OK`, plus `t*_age_ms`); electrical quality is unrecorded at the source |
| physical response delay | **SINGLE SAMPLE** | W13 reports 1.094 s command→electrical from the H6 trace with n=1; publishing median/P95/max over one sample is not a distribution, and the code path that could have shifted it is being fixed |
| pairing context | **NOT AVAILABLE** | W10 `pairing-physics.json` tolerance is `null` by design; matching variation cannot be estimated without repeated real disturbances |

**What B can consume right now:** the schema, the validity/invalidation rules, the export
format and the chamber-air representation set — i.e. the pipeline — plus one unqualified
cooling session for plumbing tests. **What B cannot consume:** any claim of dataset
sufficiency. There are 0 valid S1 runs and 0 valid S2 disturbances.

### Probe-role field added for B (this change)

`ml/data-dictionary-v0.md:101` defines `t2_c` only as "Probe role T2" — a slot name, with
no physical semantics. On the as-built rig that is unsafe for training data: the same field
name carries chamber air in the W04-era synthetic generator (`ml/src/coldguard_ml/synthetic.py:334-337`
builds `t2` around a shared `t_mean`, i.e. as an air probe) and a heatsink in every real
capture (`t2_role=HOT_SIDE` on all 957 rows). Aggregating over `t1_c,t2_c,t3_c` therefore
mixes two different physical quantities under one schema.

New host-side field, additive and unpinned: `firmware/tools/cg_probe_roles.py`
(`schema: coldguard.probe-roles/v0`) emits, per slot, `rom`, `physical_position`,
`in_chamber_air_aggregate`, `exclusion_reason`, `position_provenance` and
`independently_verified_no_movement`. Gate a chamber-air feature on
`in_chamber_air_aggregate`, not on the slot name.

```text
py firmware/tools/cg_probe_roles.py <capture.csv> [--json out.json]
```

Two deliberate limits. It does not rewrite any committed export: `cg_build_sensor_csv.py`
still emits `t1_c,t2_c,t3_c` with no role column, and its `max disagreement` is
docs/01 §20.3 `G_T = Tmax - Tmin` over T1,T2,T3 — so on this rig that figure includes the
hot-side probe and is a probe-disagreement statistic, not a chamber-air spatial gradient;
its own footer already says "consistency check only". Historical evidence is not relabelled.
And `independently_verified_no_movement` is `false` for every slot: position is
OPERATOR_FROZEN_AS_BUILT, not re-measured (level 4 of the IHA-01 record is NOT_AVAILABLE).
The row-level ROM binding for the S1 dataset (`{slot}_rom`, `{slot}_physical_position` per
row) already exists in `cg_w09_export.py:707-708` on `fix/a-w09-w10-review`; B should read
both from one reconciled source rather than let two role maps drift.

## §6.2 A → C (device/backend contract)

| Required field | State | Source |
|---|---|---|
| real telemetry fixture | **AVAILABLE** | committed W05/W06 logs and schema-3 frames on PR #16 / PR #17 |
| field semantics | **AVAILABLE** | docs/02 §28-§32 plus the W05/W06 acceptance dossiers |
| device boot / seq behaviour | **AVAILABLE** | `boot_id` and `seq` are in the capture; opening the serial port resets the board and changes `boot_id`, which is recorded and matters for any session-scoped assumption |
| firmware version | **PARTIAL** | the image identity present in the data is the `session` string's `01cedce3...`; the built image itself is local-only (258 544 B, hash recorded in `geometry-v1.md` §2) and was never read back from flash |
| quality status | **AVAILABLE, with the electrical gap stated** | §19 vocabulary implemented; electrical validity absent at source, and tooling must not infer it |
| command applied state | **AVAILABLE** | `pwm_req_permille` vs `pwm_applied_permille` vs `pwm_readback_permille` give intent and application separately |
| ACK device-side info | **AVAILABLE** | W06 emits `#CG CMDACK` with `device_id` taken from authoritative device context (not the command field), plus `boot_id`; freshness fails closed because a receipt-time TTL cannot establish a command's original age |

## §6.3 A → D (control safety inputs)

| Required field | State | Source |
|---|---|---|
| OFF electrical envelope | **AVAILABLE with one unresolved exception** | 357 zero-applied-duty frames: current values are 0.0, 0.02 (idle floor), 0.56 and **7.15 A**. The 7.15 A frame at `device_ms=826894` is docs/01 §22.4's candidate `CONTROL_ELECTRICAL_ANOMALY` (high severity) and is **not** resolved |
| healthy ON current / power range | **ONE SESSION, UNQUALIFIED** | mean 7.2247 A, peak 9.99 A, mean 85.1593 W over 600 driven frames. A range from one session is an observation, not a rating |
| allowed duty / state | **TEAM_DEPENDENCY** | firmware is fail-closed: output stage compiled out, six limits `UNRESOLVED`. Thresholds belong to Member D |
| thermal response window | **ONE SESSION** | chamber-air mean -8.7083 C over 9.98 min; 1 C at 0.85 min; W13 tau proxies 174 s cooling / 86 s recovery, labelled as biased-low proxies |
| default-off behaviour | **AVAILABLE** | W04 evidence: stage disabled at compile time, actuator enable disallowed, REN/LEN readback recorded |
| sensor degraded behaviour | **AVAILABLE at the vocabulary level** | `t*_status`, `t*_age_ms`, `snapshot`/`missing`/`invalid`/`stale` bitfields; the rule "unknown must not silently become normal" is enforced in W05/W06/W09 tooling |
| physical failure evidence | **AVAILABLE, sparse** | the 7.15 A zero-duty frame; `fan_status=NOT_COMMANDABLE` in all 62 committed G1 rows (no tachometer feedback on CG-HW-001); one `ECHO_ONLY` poll retried once, documented as transport latency in `evidence/A/W04/h6/41-h6-run-analysis.md`, not as zero current |

## §5 definition-of-done cross-check

Of the 16 handover items in docs/05A §5, Member A can produce today: hardware configuration
record (partial — the conductor line is missing), final pin map, sensor ROM map (by source),
placement map (frozen by response), healthy electrical envelope (one session), S1/S2 physical
protocols, H0-H8 evidence, physical limitations, and the run/recovery runbook in this
directory. **Not producible without sessions:** calibration/consistency evidence, repeatability
data, PZEM configuration proof against a reference, TEC safe operating point beyond the
observed point, and thermal response windows from more than one run.
