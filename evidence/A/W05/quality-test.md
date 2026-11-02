# A-W05-05 — Data-quality and liveness test record

Executed: 2026-11-02 · Method: **host execution of the delivered C sources**
Harness: `firmware/tools/tests/cg_w05_harness.c` (33 scenarios, compiled against
`cg_quality.c`, `cg_health.c`, `cg_snapshot.c`, `cg_telemetry.c`,
`cg_tec_control.c`, `cg_tec_limits.c` unchanged) · Checker:
`cg_check_firmware_w05.py` (125 static checks) · Negative tests:
`tests/test_cg_check_firmware_w05.py` (32 cases: 31 in-memory source mutations
plus 1 positive control that must not fire)

> **This is not fault injection.** Every state below was constructed by calling
> the delivered functions with synthetic observation values. No DS18B20 was
> disconnected, no 1-Wire bus was pulled, no RS-485 line was interrupted and no
> PZEM frame was corrupted on the bench. Physical fault validation remains
> **UNVERIFIED**, consistent with the H8 record. Host proof establishes the
> *rules*; only an authorized bench session can establish the *behaviour*.

## 1. Canonical vocabulary being enforced

`docs/01` §19 (lines 2263–2308) freezes four states. The rule set implemented
in `cg_quality.c`:

| Observation state | Emitted name | Why |
|---|---|---|
| never published | `UNKNOWN` | Nothing was observed. Calling it `INVALID` would assert a determined failure the firmware has no evidence for; `docs/01` 2302-2306 prefers UNKNOWN to invented certainty. |
| published, valid, inside the freshness bound | `VALID` | All mandatory sources satisfy quality and freshness (§19.1). |
| fresh but the read itself failed | `INVALID` | A corrupted or failed read must not drive the intended action (§19.3). |
| published, older than the bound | `INVALID` | A determined freshness failure, not an unknown (§18.4: historical validity ≠ control freshness). |
| one of three chamber probes failed | `DEGRADED` | §6.8 (924-942) counts *failed* probes: exactly one keeps a defined degraded path. |
| two or more chamber probes failed | `INVALID` | Multiple key thermal sensors failed (§19.3). |
| MC-38 fresh but polarity uncommissioned | `UNKNOWN` | `docs/01` §8.2 forbids assuming a raw→OPEN/CLOSED mapping; the level is carried in `door_raw`, the semantics stay undetermined. |
| BME280 absent (not implemented) | `DEGRADED` | Humidity is not a mandatory chamber-air source, so its absence is a defined degraded path — and it keeps `quality` from reading `VALID`. |

Overall collapse order: `INVALID > UNKNOWN > DEGRADED > VALID`.

## 2. Scenario matrix (all 33 pass)

Scenarios 29–33 drive the frame through the **real** publication path
(`cg_snapshot_publish_thermal/power/door` → `cg_snapshot_read` → formatter)
rather than writing snapshot fields by hand. That distinction is not decoration:
the hand-written fixtures hid a defect in which the probe counts were never
copied into the snapshot, so every real frame would have reported
`probes_valid=0` and collapsed chamber air to `UNKNOWN`.

| # | Scenario | Pins |
|---|---|---|
| 1 | `all_fresh_is_valid` | every source valid ⇒ overall VALID |
| 2 | `never_observed_is_unknown_not_invalid` | boot-time absence is UNKNOWN |
| 3 | `stale_is_invalid` | stale ⇒ INVALID; a caller that labels an old observation fresh is overridden by its age |
| 4 | `one_bad_probe_is_degraded` | 2/3 valid ⇒ DEGRADED, 1/3 ⇒ INVALID, 0/3 ⇒ INVALID |
| 5 | `failed_read_is_invalid` | fresh-but-failed electrical ⇒ INVALID |
| 6 | `uncommissioned_door_is_unknown` | raw level known, semantics not ⇒ UNKNOWN |
| 7 | `absent_bme_is_degraded` | humidity gap does not fake VALID |
| 8 | `collapse_order` | INVALID > UNKNOWN > DEGRADED > VALID |
| 9 | `health_states` | OK / LATE (>2×) / MISSED (>4×) boundaries at 1500, 2001, 4001 ms |
| 10 | `health_never_outranks_ok` | one healthy producer cannot certify the registry |
| 11 | `health_gap_and_backwards_clock` | worst gap tracked; uptime going backwards ⇒ MISSED, gap 0 |
| 12 | `health_registry` | shared registry init/beat/eval/copy; out-of-range producer id ignored |
| 13 | `identity_fields_are_present` | `schema=2`, `device_id`, `seq`, `boot_id`, `calibration_id`, ROMs, `role_status`, `rom_source`; no wall clock invented |
| 14 | `coherence_fields_are_present` | ages and producer sequences on the frame |
| 15 | `door_age_is_reported` | door age computed and door quality UNKNOWN |
| 16 | `stale_power_ages_saturate` | stale electrical ⇒ `cooling_evidence=UNOBSERVED_STALE` |
| 17 | `backwards_clock_saturates` | age saturates at 2^64−1 instead of wrapping to a plausible small number |
| 18 | `quality_vocabulary_in_line` | the five quality names are on the wire |
| 19 | `applied_state_is_not_the_request` | `pwm_duty=250` with outputs not energized ⇒ `cooling_applied=OFF`; applied-vs-measured contradictions named |
| 20 | `no_electrical_observation_is_unobserved` | never-polled PZEM ⇒ `UNOBSERVED_NO_DATA`, electrical quality UNKNOWN |
| 21 | `missing_thermal_is_unknown_not_invalid` | no thermal sample ⇒ NO_DATA status and UNKNOWN quality |
| 22 | `energy_is_published` | PZEM energy register reaches the frame with its status |
| 23 | `health_absent_is_unknown` | no liveness report ⇒ `health=UNKNOWN`, not OK |
| 24 | `liveness_and_counters_are_published` | worst producer named with beats and max gap |
| 25 | `unread_rom_is_named` | absent identity prints `UNREAD`, never an empty field |
| 26 | `worst_case_fits_the_budget` | constructed maximum-width frame fits `CG_TELEMETRY_LINE_MAX` |
| 27 | `overflow_refuses_whole_line` | a frame that does not fit produces an empty buffer, never a truncated line |
| 28 | `zero_cap_and_missing_strings` | missing identity pointers refuse the frame instead of emitting `null` |
| 29 | `publication_copies_probe_counts` | the driver's 3/3 counts survive the real publish/read copy; `rom_source=FROZEN_CONFIG_MAP` present |
| 30 | `degraded_is_reachable_through_publication` | a driver `DEGRADED` snapshot becomes `thermal_quality=DEGRADED` on the wire (docs/01 924-942), and `INVALID` for two failed roles |
| 31 | `failed_power_poll_through_publication` | a failed Modbus decode through the real path is never presented as a measured zero |
| 32 | `door_staleness_through_publication` | a 100 s old door level ⇒ `door_age_ms=100000`, `door_quality=INVALID` |
| 33 | `max_register_energy_renders_in_full` | the widest PZEM energy register (16 rendered characters) appears intact, not cut mid-digit |

## 3. Measured line budget

| Quantity | Bytes |
|---|---|
| Typical schema-2 frame (`schema-fixture.json`) | 1873 |
| Constructed worst-case frame (10-digit seqs, 20-digit ages, longest tokens, full 32-char run id) | 2098 |
| Shipped `CG_TELEMETRY_LINE_MAX` | 2560 |
| Headroom at worst case | 462 bytes (18.0 %) |

The W04 budget argument was "the longest line we happened to capture is 1012
bytes" — and the committed W04 capture really does measure 1007–1012 bytes per
frame. That is no longer sufficient: W05 nearly doubles the frame, so the
budget is now justified by a **constructed** worst case, and
`test_measured_worst_case_fits_the_shipped_budget` fails if the measured worst
case reaches **90 %** of the budget. At 1 Hz, 8N1 (10 bits per byte) and 115200
baud a 1873-byte frame occupies about 16.3 % of the serial link, and the
constructed worst case about 18.2 %. No schema-2 frame has ever been sent on real
hardware, so those two percentages are arithmetic on the buffer budget, not a
measured throughput.

## 4. What the checker proves statically (selected, 125 checks)

* `(device_id, boot_id, seq)` all present; `s_telem_seq` is a boot-scoped static
  incremented in exactly one place, and the command handler cannot reset it.
* `calibration_id` is the literal `UNRECORDED`; replacing it with a `CG-CAL-…`
  value fails the check until a calibration bundle record exists.
* Door observation time, energy register, probe counts and both producer
  sequences are **assigned** in `cg_snapshot.c` — the fields W04 logged but never
  published. The assertion is on the assignment statement, not on the field name
  appearing anywhere.
* Thermal quality counts **failed** probes, and the thermal source state is
  derived from the quality word rather than from the strict control gate, so the
  canonical DEGRADED state is reachable.
* The collapse order is read from inside `cg_quality_collapse`, not from the
  order the defines happen to appear.
* The registry is initialised inside `app_main` before `cg_power_start()` and
  before the door/sensor tasks are created, and both registry read and write
  occur inside their critical-section wrappers.
* `cooling_evidence` never reads `duty_permille`, and `outputs_energized` is
  cleared only when the disengage operations reported success.
* The hot-side field is bound to a missing value **and** `NOT_ASSIGNED` in the
  same argument list; the ROM values are emitted through the frame, and the line
  states `rom_source=FROZEN_CONFIG_MAP` so a configured identity is never read
  as a per-frame detection.
* Every `W05_REQUIRED_FIELDS` token appears as an emitted `key=` in the
  formatter, so the device can never emit a schema-2 line the host parser would
  reject.
* Every operating limit stays `UNRESOLVED`, `CG_TEC_OUTPUT_STAGE_ENABLED 0`,
  `CG_TEC_REQUEST_DUTY_PERMILLE 0`, and no W05 source opens a network entry
  point.

## 5. Negative coverage

31 in-memory source mutations, each required to fail the W05 checker with the
message naming the regression — including inventing a calibration id, resetting
`seq` from a command, dropping the door timestamp, dropping the probe-count copy,
defaulting an unobserved source to a definite verdict, counting good probes
instead of failed ones, making DEGRADED unreachable again, routing a chamber
reading into the hot-side field, deleting the ROM emit, clearing
`outputs_energized` after a failed disengage, truncating an oversized number,
smoothing a stale electrical reading into "idle", removing the critical section,
and reordering the collapse. One further case is a **must-not-fire** control (a
commented-out network call), so the suite also proves the checker is not simply
always failing.

## 6. Explicitly not established here

* No behaviour under a real sensor disconnection, CRC-corrupt PZEM frame, bus
  contention, brown-out or thermal runaway. Those need an authorized energized
  session with operator supervision.
* No calibration. `calibration_id=UNRECORDED` is a statement of absence.
* No verified probe positions. The ROMs in the frame are the **frozen
  configuration map** (`rom_source=FROZEN_CONFIG_MAP`), not a per-frame 1-Wire
  detection; per-boot presence/mismatch evidence is the `#CG ROM ... present=`
  line family, and `role_status` still states the physical label is pending.
* `cooling_applied` is the output layer's own record of what it last drove, and
  it is now cleared only when a disengage succeeded. There is **no electrical or
  GPIO readback** behind it, so its honest ceiling is "what this layer last
  commanded successfully", not "what the branch is doing". With the shipped
  stage-unavailable adapter it is `OFF` on every frame in this build.
* `fmt_float`'s refuse path (a value that cannot fit its field becomes the
  missing token) is defensive and is **not exercised end-to-end**, because the
  widest value any current driver can produce with `valid=true` fits the 24-byte
  buffers. Scenario 33 pins the reachable case: the full PZEM energy register
  renders intact.
* A future-dated observation (clock disagreement between producers) yields the
  saturated age sentinel `18446744073709551615`, and the host schema exposes it
  as `AGE_SATURATION_SENTINEL` with `clock_skew_frames` counted by the timing
  analyzer. The verdict is deliberately conservative — `INVALID`, i.e. "must not
  drive the action" — rather than `UNKNOWN`. Not reachable in the shipped build,
  where all producer tasks inherit core 1 from `app_main` and the commissioning
  task holds the highest priority in the group, so no producer can publish after
  the frame clock was read; it is named here instead of claimed impossible.
* `health` collapses to `NEVER` on a perfectly healthy device while BME280 is
  unimplemented, because that producer has no task to beat. Consumers must read
  the per-producer names; `health_thermal=MISSED` still surfaces as MISSED.
* The host build's registry lock is a no-op (`cg_health.c`, gated on
  `ESP_PLATFORM`), so no host scenario can fail if the critical section were
  deleted. `cg_check_firmware_w05.py` pins the lock textually; the property
  itself is only demonstrable on target.
