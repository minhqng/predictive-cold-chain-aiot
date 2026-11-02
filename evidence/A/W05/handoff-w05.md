# W05 → Members B, C, D — data handoff

Slice: **A-W05 telemetry foundation** · Delivered: 2026-11-02 · Branch `feat/a-w05-telemetry`
Consumable now: the schema-2 field contract, the quality/liveness semantics, and
one timing finding. **No physical dataset ships with W05** — there is no
30-minute capture, because the W05 image has never run.

## 1. What is machine-readable today

| Artifact | For | Use it for |
|---|---|---|
| `firmware/tools/cg_telemetry_schema.py` | C, B | The authoritative field list, closed vocabularies, coercion and rejection rules. Import it or mirror it; do not re-derive the field set from this document. |
| `evidence/A/W05/schema-fixture.json` | C, B | One real firmware-rendered line, its raw field map and its typed map. Ready as a parser ingest test. |
| `firmware/tools/cg_build_telemetry.py` | B, C | Capture → JSONL / flat CSV / ML CSV, with W05 identity, quality, coherence and liveness columns already wired into both views. |
| `firmware/tools/cg_timing_analysis.py` | B, D | Cadence, seq continuity, producer stall and quality tallies from any capture. |
| `evidence/A/W05/quality-test.md` | D | The exact conditions under which each source becomes VALID / DEGRADED / INVALID / UNKNOWN. |

## 2. Member C — device contract

Dedup identity is the tuple **`(device_id, boot_id, seq)`** (docs/02 633-646,
845). W05 puts all three on the wire.

```text
device_id       coldguard-001          (CG_DEVICE_ID, config)
boot_id         8 hex, new per boot    (esp_random, unchanged since W02)
seq             1..N per boot          (monotonic; a refused frame consumes its seq)
calibration_id  UNRECORDED             (no bundle measured — map to null)
hardware_config_id  CG-HW-001          unchanged
firmware_version    cg-w05-0.1.0       changed by this slice
schema              2                  serial line only; docs/02 envelope stays schema_version 1
```

Ingest rules that must not be relaxed:

* **`seq` gaps are expected and mean a frame was refused.** The formatter
  refuses any line that would not fit `CG_TELEMETRY_LINE_MAX` and never emits a
  truncated observation, and it consumes the sequence number either way. A hole
  is therefore "this observation does not exist", not "this row is corrupt".
  Inserting a placeholder row would be worse than the gap.
* **A repeated `(device_id, boot_id, seq)` is a defect, not a retry.** The
  firmware cannot replay a seq; if one appears, it came from two different
  captures of the same boot and the UNIQUE constraint is doing its job.
* **`calibration_id=UNRECORDED` → `null`.** `contracts.py:166` declares it
  nullable and `evidence/A/W02/sensor-rom-map.yaml` records `calibration_id:
  null`. Anything else in that column would assert a calibration that was never
  performed.
* **`nan` → NULL, never 0.0**, and a numeric field is only usable when its
  companion `*_status` is `OK`. `cg_build_telemetry.py` implements exactly this
  mask in the ML view and leaves the raw view untouched.
* **Store `schema` per row.** W04-era captures and W05 captures parse through the
  same parser; a mixed dataset has to say which line produced which columns. The
  W05 columns are empty strings for schema-1 rows, never fabricated defaults.
* **`timestamp_utc=UNAVAILABLE` is not a missing value.** The device has no wall
  clock and no network time. `captured_at` belongs to the host acquisition layer
  (docs/01 §18.1 keeps captured/received/persisted times distinct); the device
  time axis is `uptime_ms` / `elapsed_ms` / `run_elapsed_ms`.
* **A `quality` of `UNKNOWN` must not default to normal** (docs/01 2302-2306).
  The `health=UNKNOWN` fallback in particular means the firmware had no liveness
  report for that frame, not that producers were healthy.

Field groups on the line, in the docs/02 envelope's own grouping:

```text
identity     device_id boot_id boot_count seq run_id test_phase
             firmware_version hardware_config_id calibration_id
thermal      t_inside_c(+status,src) raw_t1/t2/t3/spare_c(+status)
             t_cold_side_c t_hot_side_c t_ambient_c   (all NOT_ASSIGNED)
             probes_valid probes_expected
environment  relative_humidity_pct(+status)          (SENSOR_NOT_PRESENT)
door         door_open door_status door_raw door_age_ms door_transitions door_cycles
electrical   voltage_v current_a power_w energy_wh (+*_status)
actuation    pwm_duty fan_command fan_status output_stage tec_state fault_code fault_reason
             cooling_applied cooling_applied_source cooling_evidence
quality      thermal_quality environment_quality door_quality electrical_quality quality
freshness    uptime_ms thermal_age_ms power_age_ms door_age_ms thermal_seq power_seq
liveness     health health_thermal health_bme health_door health_power health_telemetry
             health_control thermal_beats power_beats door_beats
             thermal_max_gap_ms power_max_gap_ms door_max_gap_ms
provenance   t1_rom t2_rom t3_rom spare_rom role_status
```

## 3. Member B — what you can and cannot build from this

**Can:**

* Fix the ingest contract against a real firmware line:
  `schema-fixture.json` → `fields` is the complete raw map, `typed_fields` the
  coerced one. It is produced by the delivered formatter, not written by hand.
* Decide validity policy against the vocabulary in `quality-test.md` §1,
  including the two cases that matter for labelling: one bad probe is DEGRADED
  while two or more is INVALID, and an uncommissioned door is UNKNOWN rather
  than a class.
* Size the time axis honestly. The pilot in `timing-pilot.md` measures
  `uptime_ms` deltas of 980 ms (48×), 1080 ms (12×) and one 1078 ms boot-transition
  interval — quantized by the 100 ms commissioning tick, with a mean of
  1001.279 ms. Any derivative over consecutive frames is a ~±40 ms grid, not a
  1 ms one, and the first interval after boot is not representative.

**Cannot:**

* Train or evaluate anything on W05 data. There is no chamber dataset in this
  slice: no S1 baselines (W09), no S2 disturbances (W10), no S4 (W11). The only
  real stream cited here is a 60-second W04 boot/idle window where **every**
  electrical frame decoded INVALID.
* Treat `t_inside_c` as a three-probe chamber mean. `docs/01` §20.1 requires all
  three of T1/T2/T3 valid; `probes_valid`/`probes_expected` are now on the frame
  so that condition is checkable, and `T2`'s physical position is still
  unverified.
* Use `cooling_applied` as a label for "cooling happened" in this build. The
  output stage is compiled out, so it is `OFF` on every frame; `cooling_evidence`
  is the only field that says anything about the branch, and it is `MEASURED_*`
  only when the PZEM observation is fresh and valid.
* Infer BME280 humidity. `relative_humidity_status=SENSOR_NOT_PRESENT` and
  `environment_quality=DEGRADED` are the shipped state (A-W02-06 pending).
* Use W05 schema fields on W04 rows. They are absent, and `cg_build_telemetry.py`
  emits empty cells rather than zeros.

## 4. Member D — observability inputs

* **Task-boundary failure is now observable by name.** A producer that stops
  beating surfaces as `health_thermal=MISSED` (past 4× its nominal period; LATE
  past 2×) together with `thermal_beats` and `thermal_max_gap_ms`, while the
  values it owned go stale and their quality becomes INVALID. Nothing is carried
  forward silently.
* **The 2×/4× multipliers are firmware-internal observability choices, not
  canonical thresholds.** `docs/01` §18.4 leaves the control freshness threshold
  to policy configuration; `CG_TEC_STALE_THERMAL_MS`/`_POWER_MS` remain the
  control-side bounds. If D owns those policy numbers, they should be set in one
  place by D's policy rather than inferred from these constants.
* **Stale ≠ idle, and that is now explicit on the wire.**
  `cooling_evidence=UNOBSERVED_STALE`/`UNOBSERVED_NO_DATA` distinguishes "we
  cannot tell" from `MEASURED_IDLE_AND_ZERO` ("we can tell, and current is zero").
  `MEASURED_CONTRADICTS_APPLIED` names the disagreement case, which the W04 line
  could not express at all.
* **SAFE_LOCAL physical support is unchanged by W05.** The output stage is still
  compiled out, the branch cannot be energized by this build, and no local
  fallback policy was implemented here — that is D's code.
* **Reset staleness:** a boot restarts `seq` at 1 under a new `boot_id`; a reset
  that keeps `boot_id` is indistinguishable from continued running in this slice,
  and W06 handles command-across-reset semantics.

## 5. Known open items this handoff does not settle

1. **T2 semantics.** The operator states the physical T2 probe is on the hot
   side; `docs/01` freezes T1/T2/T3 as chamber-air roles and
   `sensor-rom-map.yaml` keeps `physical_position_verified: false`. W05 emits
   `t_hot_side_c=nan t_hot_side_status=NOT_ASSIGNED` and does not move a hot-side
   value into a chamber field. The decision is a project-level contract change
   (docs/01 must be amended first), not a Member A firmware edit.
2. **The conductor and fuse deviation register** (`CR-A-W04-01`,
   `CR-A-W04-02`) stays open. Their GitHub issues were closed administratively at
   the operator's instruction on 2026-11-02 because no reviewer was available;
   that closure certifies nothing about compliance.
3. **No W05 capture exists.** B and C should not build ingestion against a
   hypothesis: the 30-minute run is a NEED_USER_ACTION item in `acceptance.md`.
4. **`docs/02` serialization is C's.** This slice delivers the device-side raw
   line and its meaning; mapping it into the JSON envelope, MQTT topics and the
   schema-version negotiation belongs to Member C.
