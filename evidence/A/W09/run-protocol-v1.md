# S1/S2/S4 run protocol v1

Generated from `firmware/tools/cg_w09_run_protocol.py` (w09-run-protocol-v1); source requirement: docs/05A §18 A-W09-01 (Week 09 run checklist).

Status: **IMPLEMENTED / HOST_VERIFIED**. No gate here was closed by a physical session; the list is the instrument Member A and the operator use to close them.

`Firmware` says whether the device itself can decide the gate:

| value | meaning |
|---|---|
| `OBSERVABLE` | a shipped frame field decides it (5 gates) |
| `PARTIAL` | the device states something weaker than the gate asks (9) |
| `HOST_ONLY` | the firmware cannot see it at all (6) |

## Before Run - 9 gate(s)

| Gate | Requirement | Doc anchor | Firmware | Blocking | Frame fields |
|---|---|---|---|---|---|
| `GATE-HWCONFIG` | hardware config | docs/05A §18 A-W09-01; docs/03 §5 run manifest | OBSERVABLE | yes | `hardware_config_id`, `pin_map_version`, `firmware_version` |
| `GATE-BOOT-IDENTITY` | one boot_id per run, recorded before the run starts | docs/02 §4.2 identity | OBSERVABLE | yes | `boot_id`, `reset_cause`, `run_id` |
| `GATE-SENSOR-IDENTITY` | sensor identity | docs/05A §18 A-W09-01; docs/01 §19.3 (unknown DS18B20 identity is INVALID) | PARTIAL | yes | `t1_role`, `t2_role`, `t3_role`, `t4_role`, `probes_valid`, `probes_expected`, `missing` |
| `GATE-SENSOR-POSITION` | each probe is physically where the frozen geometry says it is | docs/05A §18 A-W09-03 (sensor moved invalidates a run) | HOST_ONLY | yes | *(none)* |
| `GATE-ELECTRICAL-RANGE` | PZEM range | docs/05A §18 A-W09-01; docs/01 §19.3 (wrong PZEM range is INVALID) | PARTIAL | yes | `voltage_v_status`, `current_a_status`, `power_w_status`, `limits_policy`, `limits_operator_approved`, `off_current_limit_a`, `energy_wh` |
| `GATE-INITIAL-STATE` | initial state | docs/05A §18 A-W09-01; docs/03 §5 initial_condition | OBSERVABLE | yes | `state`, `stage`, `snapshot`, `air_c`, `t1`, `t2`, `t3`, `t4`, `rh_pct`, `pressure_hpa` |
| `GATE-DOOR-STATE` | door closed at rest, with a machine-readable state | docs/05A §18 A-W09-01; docs/03 §5 (initial_condition.door: CLOSED); docs/05A §19 A-W10-02 | PARTIAL | yes | `door_open`, `door_raw`, `door_status`, `door_polarity`, `door_age_ms`, `door_cycles` |
| `GATE-OUTPUT-GATE` | the actuator gate and interlock posture are known before ARM | docs/05A §17 pass criteria; docs/05A §18 A-W09-01 | OBSERVABLE | yes | `interlock_state`, `supervised_bench`, `supervised_authorized`, `physical_output`, `limits_enforced` |
| `GATE-STORAGE-ONLINE` | storage online (capture is actually being written) | docs/05A §18 A-W09-01 | HOST_ONLY | yes | *(none)* |

### `GATE-HWCONFIG` - hardware config

* Host method: match the boot line `#CG LOG v=.. fw=.. hw=.. device=.. pin_map=..` against the frozen as-built record for the campaign
* On failure: stop: a frame from an unidentified configuration cannot enter a run
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: committed evidence carries hw=CG-HW-001, pin_map=2, fw=cg-w04-0.1.0

### `GATE-BOOT-IDENTITY` - one boot_id per run, recorded before the run starts

* Host method: open the capture before ARM so the boot line is inside the file
* On failure: stop: opening the port resets the board, so a boot_id first seen mid-capture means the early frames belong to another boot
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: the probe-identification session changed boot_id per touch window for exactly this reason

### `GATE-SENSOR-IDENTITY` - sensor identity

* Host method: ROM ids come from the per-boot `#CG ROM role=.. rom=.. present=..` lines, not from the frame; the frame carries slot roles only
* On failure: stop: a probe whose identity is unknown cannot drive a derived state
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: PARTIAL because the H8S frame has no ROM field. The slot->position mapping is OPERATOR-FROZEN (T1 centre, T2 TEC hot side, T3 bottom, T4 near door) and is recorded *by-source* from the firmware ROM table; it is not verified by readback

### `GATE-SENSOR-POSITION` - each probe is physically where the frozen geometry says it is

* Host method: operator visual confirmation against the frozen geometry record; the 2026-11-02 PROBE_IDENTIFICATION session is the identity record but must never be reused as thermal data
* On failure: invalidate the run; a moved probe is a physical invalidation
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: the device cannot see its own probes being moved; slot roles stay ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING in the boot line

### `GATE-ELECTRICAL-RANGE` - PZEM range

* Host method: confirm the PZEM configuration and the limit table the boot line echoes
* On failure: stop: an unqualified electrical column makes the run's energy and active-range claims unusable
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: PARTIAL: the frame reports a status per electrical field and the approved limit policy, but not the instrument's configured range. The committed CSV carries voltage_status/current_status EMPTY in all 957 rows, which is exactly the failure this gate exists to catch

### `GATE-INITIAL-STATE` - initial state

* Host method: record the first VALID frame as the run's initial condition
* On failure: stop: a run without a valid initial condition has no baseline to differ from
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: docs/03 §5 wants target_state, tmean_c, tmax_c, gradient_c and door state here

### `GATE-DOOR-STATE` - door closed at rest, with a machine-readable state

* Host method: operator confirms the lid is seated; MC-38 polarity is confirmed per boot with `DOOR NEAR_LOW|NEAR_HIGH <token>`
* On failure: do not start: door_open=UNKNOWN is not CLOSED. A polarity confirmation only makes the level nameable, it does not prove the magnet reaches the switch
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: the strongest available statement is sensor level + confirmed polarity. The 2026-11-01 MC-38 work documents a stuck-high input that `DOOR NEAR_HIGH` made the firmware echo as CLOSED (door_open=0, snapshot=VALID), which is why this gate stays PARTIAL rather than OBSERVABLE

### `GATE-OUTPUT-GATE` - the actuator gate and interlock posture are known before ARM

* Host method: read the `#CG H8 ACTUATOR` and BOOT_POLICY lines
* On failure: stop: an unknown output posture is a safety posture change
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: committed H8 frames report supervised_bench=1 with supervised_authorized=0

### `GATE-STORAGE-ONLINE` - storage online (capture is actually being written)

* Host method: the capture host confirms the file is open and growing, and that rejections are being written beside samples rather than dropped
* On failure: stop: a run with no raw file is not evidence-grade and cannot be replayed
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: the device has no non-volatile run storage; `cloud=NOT_PROVISIONED` in every frame and there is no transport in this firmware

## During Run - 2 gate(s)

| Gate | Requirement | Doc anchor | Firmware | Blocking | Frame fields |
|---|---|---|---|---|---|
| `GATE-CADENCE` | the declared cadence is met (1 Hz nominal) and gaps are counted | docs/05A §18 A-W09-03 (missing key telemetry) | PARTIAL | no | `seq`, `device_ms`, `host_ack_seq` |
| `GATE-SUPERVISION` | an operator is at the bench for the whole energized run | docs/05A §17 pass criteria (safe physical envelope); docs/04 §5.2 | PARTIAL | yes | `supervised_bench`, `supervised_authorized` |

### `GATE-CADENCE` - the declared cadence is met (1 Hz nominal) and gaps are counted

* Host method: gap statistics on the host clock, e.g. the W05 timing pilot method
* On failure: record as a validity finding; a gap invalidates the affected interval, not necessarily the run
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: device_ms is per-boot uptime; the host clock owns the cadence claim

### `GATE-SUPERVISION` - an operator is at the bench for the whole energized run

* Host method: operator attestation in the run manifest
* On failure: stop the stage
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: supervised_bench is a compile-time posture, not a live human-presence sensor

## After Run - 9 gate(s)

| Gate | Requirement | Doc anchor | Firmware | Blocking | Frame fields |
|---|---|---|---|---|---|
| `GATE-END-REASON` | end reason | docs/05A §18 A-W09-01 | OBSERVABLE | yes | `stop_reason`, `state`, `fault_bits`, `fault` |
| `GATE-MANUAL-INTERVENTION` | manual intervention logged | docs/05A §18 A-W09-01 | PARTIAL | yes | *(none)* |
| `GATE-ANOMALY` | anomaly recorded | docs/05A §18 A-W09-01 | PARTIAL | no | `fault_bits`, `fault`, `off_verify`, `host_ack_reject` |
| `GATE-VALIDITY-CANDIDATE` | validity candidate assigned | docs/05A §18 A-W09-03; docs/03 §6 run lifecycle (COMPLETED_RAW -> VALIDITY_REVIEW) | PARTIAL | yes | `snapshot` |
| `GATE-PROVENANCE-PIN` | every ingested source file is hash-pinned | docs/04 §7 evidence ownership; docs/05A §18 A-W09-02 | HOST_ONLY | yes | *(none)* |
| `GATE-SESSION-CLASS` | the run's session class is eligible for the dataset it is entering | docs/05A §18 A-W09-03 | HOST_ONLY | yes | *(none)* |
| `GATE-NON-PHYSICAL-FILTER` | a host fixture can never be published as a run | docs/05A §18 A-W09-02 | HOST_ONLY | yes | *(none)* |
| `GATE-S2-DISTURBANCE-CONTROL` | for S2, the disturbance was operator-controlled and timed | docs/05A §19 A-W10-02/03 | HOST_ONLY | yes | `door_open`, `door_cycles`, `device_ms` |
| `GATE-S4-NO-PROMOTION` | for S4, a refused command never appears as an applied action | docs/05A §20 A-W11-01/02; docs/02 §32.2 | PARTIAL | yes | `last_ack_status`, `desired_cooling`, `desired_duty_permille` |

### `GATE-END-REASON` - end reason

* Host method: confirm the last frame's stop_reason is consistent with how the stage ended
* On failure: record; an unexplained end reason makes the run a validity candidate only after review
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: the committed 600 s capture ends with stop_reason=STAGE_DEADLINE on 131 rows

### `GATE-MANUAL-INTERVENTION` - manual intervention logged

* Host method: the control file (commands actually sent) plus the operator's note; the device cannot see a hand on a probe or a magnet near a sensor
* On failure: invalidate the run physically (A-W09-03) and keep the raw attempt
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: this is the gate the 2026-11-02 touch-identification session fails by design: every frame there has a hand on a probe, which is why it is excluded from S1/S2/S4

### `GATE-ANOMALY` - anomaly recorded

* Host method: operator observation plus host-side validity analysis
* On failure: record; unexplained anomalies escalate to the campaign owner
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: fault_bits is a device-side vocabulary; a thermal excursion with no fault bit is invisible to the device

### `GATE-VALIDITY-CANDIDATE` - validity candidate assigned

* Host method: cg_w09_validity.evaluate_frames() over the raw capture; the producer's snapshot flag is a first pass, not the verdict
* On failure: no valid S1 ID is issued; the attempt stays in the registry
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: never delete an invalid attempt (A-W09-03)

### `GATE-PROVENANCE-PIN` - every ingested source file is hash-pinned

* Host method: SHA-256 of each source recorded in the export and in SHA256SUMS.txt
* On failure: the export is not published
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: a dataset whose bytes are not pinned cannot be re-derived later

### `GATE-SESSION-CLASS` - the run's session class is eligible for the dataset it is entering

* Host method: cg_w09_validity rejects frames whose run label is an excluded class
* On failure: reject the frames; PROBE_IDENTIFICATION may never enter S1/S2/S4
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: enforced by label match, not by inspecting temperatures, so it cannot be defeated by a plausible-looking touch window

### `GATE-NON-PHYSICAL-FILTER` - a host fixture can never be published as a run

* Host method: every export refuses a source whose provenance has is_physical_measurement=false
* On failure: the export raises instead of writing
* Scope: S1_NORMAL_BASELINE, S2_DOOR_DISTURBANCE, S4_ACTUATION_RESPONSE_FAULT
* Note: validated by validate_w09.py and by the W09/W10/W11 unit tests

### `GATE-S2-DISTURBANCE-CONTROL` - for S2, the disturbance was operator-controlled and timed

* Host method: MC-38 transition as machine ground truth plus the operator timer as a secondary check
* On failure: the disturbance is not an S2 pilot event; record it as an incidental door observation instead
* Scope: S2_DOOR_DISTURBANCE
* Note: an incidental OPEN window inside a commissioning stage is not a protocolised disturbance and is not counted as one

### `GATE-S4-NO-PROMOTION` - for S4, a refused command never appears as an applied action

* Host method: cg_w11_s4 refuses a trace that infers applied evidence from intent
* On failure: reject the trace
* Scope: S4_ACTUATION_RESPONSE_FAULT
* Note: applied state must be read from the device, not from what was requested

## Protocol-level honesty notes

* a gate is OBSERVABLE only when a shipped frame field decides it
* door polarity confirmation names a level; it does not prove a physical door position
* firmware has no run storage and no transport: storage and command issuance are host/operator gates by construction
* an invalid attempt is recorded, never deleted (docs/05A §18 A-W09-03)

## Gates the firmware cannot close

`GATE-SENSOR-POSITION`, `GATE-STORAGE-ONLINE`, `GATE-PROVENANCE-PIN`, `GATE-SESSION-CLASS`, `GATE-NON-PHYSICAL-FILTER`, `GATE-S2-DISTURBANCE-CONTROL`

These are operator or capture-host gates. A frame cannot vouch for them, so a run whose record shows them as closed only because the device was happy is not evidence-grade.
