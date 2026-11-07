# ColdGuard W06 — Event Alignment and Timing Audit

Provenance-aware event alignment, clock/sequence diagnostics, bounded response detection and deterministic duplicate handling. No model training, no W07 plant EDA, no W08 Gate B, no W12 evaluation.

## 0. Scientific separation

| Status | Value | Meaning |
|---|---|---|
| W06 SOFTWARE VERIFICATION | PASS | CLI completed and artifacts are deterministic; pytest is the stronger evidence |
| REAL COMMAND-LIFECYCLE EVIDENCE | ABSENT | no physical command/ACK round trip exists in the committed evidence |
| PHYSICAL DATA ELIGIBILITY | NOT_READY | authoritative W04 admission over the analyzed captures |
| REAL AIW | NOT_ESTIMABLE | W06 supplies candidate inputs only; compute_aiw remains the gate |

A software-green W06 with absent real command evidence is an acceptable engineering result. It is not a physical verification claim.

## 1. Provenance

| Field | Value |
|---|---|
| Report schema | coldguard-w06-timing-report-v1 |
| Package version | 0.1.0 |
| W06 layer version | coldguard-w06-timing-v1 |
| Analysis code SHA-256 | `90bc2e448c15b551f2a9409cd7f2aaa4eebef97e186947e302b8c7603a76afb0` |
| Repository revision | 84dd39fbd8e500ab14ff1d4a38a746e7fad674ed |
| A run index | evidence/A/W09/s1-run-index.json |
| Generation command | `event-alignment-W06.py --source ../evidence/A/W09/exports/CG-S1-H8C-600S.json --source ../backend/fixtures/telemetry_v0.json --a-run-index ../evidence/A/W09/s1-run-index.json --a-command-log ../evidence/A/W06/demo-command-capture.log --a-command-provenance HOST_GENERATED_SYNTHETIC --event-fixture tests/fixtures/W06/qualified-response.json --out reports/W06 --baseline-window-s 10.0 --electrical-max-window-s 60.0 --thermal-max-window-s 300.0 --max-gap-s 5.0 --sustained-observations 3 --electrical-min-change-a 0.05 --thermal-min-change-c 0.25 --max-uncertainty-s 10.0 --repository-revision 84dd39fbd8e500ab14ff1d4a38a746e7fad674ed` |

## 2. Source inventory

| Kind | Path | SHA-256 | Namespace | Provenance | Time domain | Clock sync | Admission | Rows/events |
|---|---|---|---|---|---|---|---|---|
| CAPTURE | evidence/A/W09/exports/CG-S1-H8C-600S.json | f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb | w09-run-export/v2 | PHYSICAL | BOOT_SCOPED_UPTIME | NOT_EVIDENCED | EXCLUDED_OR_BLOCKED | 957 |
| CAPTURE | backend/fixtures/telemetry_v0.json | 48358561236d062ee63bc3fc8596f341498837063c24aa9b84b5873525a23dab | coldguard.telemetry/v1 | SYNTHETIC | EVENT_UTC | UNVERIFIED_SYNC | EXCLUDED_OR_BLOCKED | 1 |
| A_COMMAND_LOG | evidence/A/W06/demo-command-capture.log | 9a6a47a0119c9303cb8c24094b878c78e1999b538fd5267a17f0ead281b3ec06 | coldguard.command-ack-serial/v1 | HOST_GENERATED_SYNTHETIC | DEVICE_BOOT_UPTIME | PER_ACK_FIELD | EXCLUDED_OR_BLOCKED | 5 |
| W06_EVENT_FIXTURE | ml/tests/fixtures/W06/qualified-response.json | 183f9ae803dee1a4aff83b72017e0b4bb06edf9c16e58eb3a242013f4291ce1f | coldguard.w06-event-fixture/v1 | SYNTHETIC_FIXTURE | DECLARED_PER_EVENT | SYNTHETIC_EXACT | EXCLUDED_OR_BLOCKED | 24 |

## 3. Source-contract ledger

| Source field | Namespace/version | Time domain | Identity | Quality | Authority | W06 use |
|---|---|---|---|---|---|---|
| A W09 seq/boot_id/device_id | w09-run-export/v2 | boot-scoped identity; no absolute time | device_id may be NOT_CARRIED; boot_id+seq is the session identity | sequence_quality | A export; W04 intake preserves unresolved values | telemetry event identity and duplicate key |
| A W09 device_ms | w09-run-export/v2 | DEVICE_BOOT_UPTIME | boot_id | sequence/provenance quality | A export | within-boot ordering and elapsed intervals only |
| A W09 host_capture_time_utc | w09-run-export/v2 | HOST_CAPTURE_UTC | row/session | NOT_AVAILABLE in the committed capture | A export | never promoted to device event UTC |
| A W09 door_open/door_polarity | w09-run-export/v2 | DEVICE_BOOT_UPTIME | boot_id+seq | door_quality | A export | named OPEN/CLOSED transitions only; UNKNOWN is not a transition |
| A W09 pwm_applied_permille/state | w09-run-export/v2 | DEVICE_BOOT_UPTIME | boot_id+seq | overall_quality | A export | device-reported applied-state observation; not command proof |
| A W09 voltage/current/power/energy | w09-run-export/v2 | DEVICE_BOOT_UPTIME | boot_id+seq | electrical_quality | A export | electrical response candidate; UNKNOWN quality never certifies |
| A W09 t1/t2/t3/t4 | w09-run-export/v2 | DEVICE_BOOT_UPTIME | boot_id+seq | per-probe status and sensor roles | A export plus frozen ROM role map | chamber-air mean from role-qualified slots only; T2 hot side excluded |
| A W06 #CG CMDACK command envelope | coldguard.command-ack-serial/v1 (schema=1) | DEVICE_BOOT_UPTIME; no UTC epoch | command_id + device_id + boot_id + ack_seq | protocol evidence; not measurement quality | A host-generated fixture; synthetic until a real transport exists | ACK event and duplicate-canonical semantics; never applied proof |
| A W06 #CG TELEM schema=3 | coldguard.telem-serial/v3 | DEVICE_BOOT_UPTIME; DEVICE_HAS_NO_WALL_CLOCK | boot_id+seq | per-field status tokens | A firmware serial namespace, not C MQTT JSON | not parsed by W06; the C JSON parser is never substituted |
| C telemetry JSON captured_at/uptime_ms/seq | coldguard.telemetry/v1 (schema_version=1) | DEVICE_EVENT_UTC for captured_at; boot-scoped uptime_ms | device_id+boot_id+seq | quality sections | C wire contract; current fixture is synthetic/unverified | telemetry event time and identity; no command/ACK linkage |
| C telemetry_raw backend_received_at/created_at | backend storage (C W02) | BACKEND_RECEIVE_UTC / BACKEND_PERSISTED_UTC | raw delivery row | ingest_status | C backend | receive/persisted provenance only; never source acquisition time |
| A W10 door-events timing_uncertainty | A W10 s2-horizon evidence | DEVICE_BOOT_UPTIME | boot_id+seq | door mapping not attested | A W10 evidence; reference only for W06 uncertainty | documented 1 s edge uncertainty; no door-open claim |

Command-log inputs: 1 embedded `#CG TELEM` line(s) were ignored; serial telemetry is never fed through the C JSON parser.

## 4. Event counts (canonical, after duplicate collapse)

| Count | Value |
|---|---|
| Telemetry events | 979 |
| Door transitions | 0 |
| Command events | 1 |
| ACK events | 6 |
| Applied-state observations | 3 |
| Electrical response events | 0 |
| Thermal response events | 0 |
| Electrical responses (numeric) | 2 |
| Thermal responses (numeric) | 4 |
| Verified electrical responses | 0 |
| Verified thermal responses | 0 |
| Duplicate deliveries | 0 |
| Contradictory identities | 0 |
| Contradictory events | 0 |
| Missing-identity events | 0 |
| Unalignable events | 0 |
| Real measured response delays | 0 |
| Synthetic example delays | 6 |
| Not-estimable responses | 21 |
| Censored responses | 0 |
| Contradictory responses | 0 |

Per-source counts:

| Source | Telemetry | Door | Command | ACK | Applied | Electrical | Thermal |
|---|---|---|---|---|---|---|---|
| evidence/A/W09/exports/CG-S1-H8C-600S.json | 957 | 0 | 0 | 0 | 2 | 0 | 0 |
| backend/fixtures/telemetry_v0.json | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| evidence/A/W06/demo-command-capture.log | 0 | 0 | 0 | 5 | 0 | 0 | 0 |
| ml/tests/fixtures/W06/qualified-response.json | 21 | 0 | 1 | 1 | 1 | 0 | 0 |

## 5. Ordering and clock/sequence diagnostics

| Clock domain | Device | Boot | Events | First time (s) | Last time (s) | Median interval (s) | P95 interval (s) | Monotonic | Seq gaps | Seq dups | Reversals | Uptime resets | Receive conflicts | Max uncertainty (s) | Reason codes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEVICE_BOOT_UPTIME | cg-sim-qualified | sim-boot-qualified | 24 | 0.500 | 2.500 | 0.100000 | 0.100000 | True | 0 | 0 | 0 | 0 | 0 | 0.050000 | MISSING_CAPTURE_TIME, MISSING_RECEIVE_TIME |
| DEVICE_BOOT_UPTIME | coldguard-001 | abcd0123 | 5 | 123.456 | 123.456 | NOT_ESTIMABLE | NOT_ESTIMABLE | True | 0 | 0 | 0 | 0 | 0 | NOT_ESTIMABLE | MISSING_CAPTURE_TIME, MISSING_RECEIVE_TIME |
| DEVICE_BOOT_UPTIME | NOT_CARRIED | 56044b74 | 959 | 0.904 | 956.894 | 1.000000 | 1.000000 | True | 0 | 0 | 0 | 0 | 0 | 6.000000 | MISSING_CAPTURE_TIME, MISSING_RECEIVE_TIME, UNCERTAIN_CROSS_STREAM_ASSOCIATION |
| DEVICE_EVENT_UTC | coldguard-001 | boot-w01-fixture-001 | 1 | 1791961200.000 | 1791961200.000 | NOT_ESTIMABLE | NOT_ESTIMABLE | True | 0 | 0 | 0 | 0 | 0 | NOT_ESTIMABLE | MISSING_RECEIVE_TIME |

| Ordered session | Status | Reason codes |
|---|---|---|
| DEVICE_EVENT_UTC / coldguard-001 / boot-w01-fixture-001 | ORDERED_IN_DOMAIN | CLOCK_SYNC_UNVERIFIED_FOR_ABSOLUTE_LATENCY |
| DEVICE_BOOT_UPTIME / coldguard-001 / abcd0123 | ORDERED_IN_DOMAIN | NONE |
| DEVICE_BOOT_UPTIME / NO_DEVICE_ID / 56044b74 | ORDERED_IN_DOMAIN | NONE |
| DEVICE_BOOT_UPTIME / cg-sim-qualified / sim-boot-qualified | ORDERED_IN_DOMAIN | NONE |

Uptime is boot-scoped. No host capture time is promoted to device event time, no backend receive time is a source acquisition time, and no cross-boot uptime subtraction is performed.

## 6. Duplicate and idempotency handling

| Field | Value |
|---|---|
| Canonical events | 989 |
| Contradictory events | 0 |
| Missing-identity events | 0 |
| Identical duplicate deliveries | 0 |
| DUPLICATE_CANONICAL replies | 1 |
| Commands with multiple ACKs and no DUPLICATE_CANONICAL | 0 |
| Reboot identity resets | 0 |
| New command IDs with the same requested action | 4 |
| Reason codes | DUPLICATE_CANONICAL_REPLY, NEW_COMMAND_SAME_ACTION |

Identical repeated delivery collapses to one logical event while retaining `delivery_count`. Contradictory payloads sharing one identity are retained and reported, never resolved by choosing a favorable payload. A DUPLICATE_CANONICAL reply is not another independent application, and a cross-boot uptime match is never duplicate proof.

## 7. Command and response results

| Source | Relationship | Command | State | Latency (s) | Uncertainty (s) | Evidence class | Samples | Baseline | Policy | Reason codes |
|---|---|---|---|---|---|---|---|---|---|---|
| backend/fixtures/telemetry_v0.json | ACK_TO_APPLIED_STATE | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| backend/fixtures/telemetry_v0.json | APPLIED_TO_ELECTRICAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| backend/fixtures/telemetry_v0.json | APPLIED_TO_THERMAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| backend/fixtures/telemetry_v0.json | COMMAND_TO_ACK | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| backend/fixtures/telemetry_v0.json | COMMAND_TO_ELECTRICAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| backend/fixtures/telemetry_v0.json | COMMAND_TO_THERMAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| evidence/A/W06/demo-command-capture.log | ACK_TO_APPLIED_STATE | 00000000-0000-4000-8000-00000000000a | NOT_APPLICABLE_ACK_NOT_ACCEPTED | NOT_ESTIMABLE | NOT_ESTIMABLE | SYNTHETIC_UNIT_TEST | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | ACK_STATUS_SAFETY_BLOCKED |
| evidence/A/W06/demo-command-capture.log | ACK_TO_APPLIED_STATE | 00000000-0000-4000-8000-00000000000b | NOT_OBSERVED | NOT_ESTIMABLE | NOT_ESTIMABLE | SYNTHETIC_UNIT_TEST | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_APPLIED_STATE_EVIDENCE_AFTER_ACCEPTED_ACK |
| evidence/A/W06/demo-command-capture.log | ACK_TO_APPLIED_STATE | 00000000-0000-4000-8000-00000000000c | NOT_APPLICABLE_ACK_NOT_ACCEPTED | NOT_ESTIMABLE | NOT_ESTIMABLE | SYNTHETIC_UNIT_TEST | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | ACK_STATUS_EXPIRED |
| evidence/A/W06/demo-command-capture.log | ACK_TO_APPLIED_STATE | 00000000-0000-4000-8000-00000000000d | NOT_APPLICABLE_ACK_NOT_ACCEPTED | NOT_ESTIMABLE | NOT_ESTIMABLE | SYNTHETIC_UNIT_TEST | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | ACK_STATUS_REJECTED |
| evidence/A/W06/demo-command-capture.log | ACK_TO_APPLIED_STATE | 00000000-0000-4000-8000-00000000000e | DUPLICATE_CANONICAL_NOT_AN_APPLICATION | NOT_ESTIMABLE | NOT_ESTIMABLE | SYNTHETIC_UNIT_TEST | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | DUPLICATE_CANONICAL_DOES_NOT_COUNT_AS_ANOTHER_APPLICATION |
| evidence/A/W06/demo-command-capture.log | APPLIED_TO_ELECTRICAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| evidence/A/W06/demo-command-capture.log | APPLIED_TO_THERMAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| evidence/A/W06/demo-command-capture.log | COMMAND_TO_ACK | 00000000-0000-4000-8000-00000000000a | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 1 | NOT_ESTIMABLE | electrical-current-step-v1 | ACK_RELATIVE_LATENCY_IS_NOT_COMMAND_PUBLICATION_LATENCY, NO_COMMAND_PUBLICATION_EVENT |
| evidence/A/W06/demo-command-capture.log | COMMAND_TO_ACK | 00000000-0000-4000-8000-00000000000b | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 1 | NOT_ESTIMABLE | electrical-current-step-v1 | ACK_RELATIVE_LATENCY_IS_NOT_COMMAND_PUBLICATION_LATENCY, NO_COMMAND_PUBLICATION_EVENT |
| evidence/A/W06/demo-command-capture.log | COMMAND_TO_ACK | 00000000-0000-4000-8000-00000000000c | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 1 | NOT_ESTIMABLE | electrical-current-step-v1 | ACK_RELATIVE_LATENCY_IS_NOT_COMMAND_PUBLICATION_LATENCY, NO_COMMAND_PUBLICATION_EVENT |
| evidence/A/W06/demo-command-capture.log | COMMAND_TO_ACK | 00000000-0000-4000-8000-00000000000d | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 1 | NOT_ESTIMABLE | electrical-current-step-v1 | ACK_RELATIVE_LATENCY_IS_NOT_COMMAND_PUBLICATION_LATENCY, NO_COMMAND_PUBLICATION_EVENT |
| evidence/A/W06/demo-command-capture.log | COMMAND_TO_ACK | 00000000-0000-4000-8000-00000000000e | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 1 | NOT_ESTIMABLE | electrical-current-step-v1 | ACK_RELATIVE_LATENCY_IS_NOT_COMMAND_PUBLICATION_LATENCY, NO_COMMAND_PUBLICATION_EVENT |
| evidence/A/W06/demo-command-capture.log | COMMAND_TO_ELECTRICAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| evidence/A/W06/demo-command-capture.log | COMMAND_TO_THERMAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| evidence/A/W09/exports/CG-S1-H8C-600S.json | ACK_TO_APPLIED_STATE | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| evidence/A/W09/exports/CG-S1-H8C-600S.json | APPLIED_TO_ELECTRICAL | NOT_APPLICABLE | NOT_ESTIMABLE_QUALITY | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | BASELINE_QUALITY_NOT_VALID |
| evidence/A/W09/exports/CG-S1-H8C-600S.json | APPLIED_TO_ELECTRICAL | NOT_APPLICABLE | NOT_ESTIMABLE_QUALITY | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | BASELINE_QUALITY_NOT_VALID |
| evidence/A/W09/exports/CG-S1-H8C-600S.json | APPLIED_TO_THERMAL | NOT_APPLICABLE | OBSERVED_DIAGNOSTIC_ONLY | 28.000000 | 1.000000 | PHYSICAL_MEASURED | 3 | 30.020667 | chamber-air-temperature-step-v1 | ANCHOR_QUALITY_NOT_VALID_DIAGNOSTIC_ONLY |
| evidence/A/W09/exports/CG-S1-H8C-600S.json | APPLIED_TO_THERMAL | NOT_APPLICABLE | OBSERVED_DIAGNOSTIC_ONLY | 25.000000 | 6.000000 | PHYSICAL_MEASURED | 3 | 21.312667 | chamber-air-temperature-step-v1 | ANCHOR_QUALITY_NOT_VALID_DIAGNOSTIC_ONLY |
| evidence/A/W09/exports/CG-S1-H8C-600S.json | COMMAND_TO_ACK | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| evidence/A/W09/exports/CG-S1-H8C-600S.json | COMMAND_TO_ELECTRICAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| evidence/A/W09/exports/CG-S1-H8C-600S.json | COMMAND_TO_THERMAL | NOT_APPLICABLE | NOT_ESTIMABLE_MISSING_ANCHOR | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | 0 | NOT_ESTIMABLE | electrical-current-step-v1 | NO_ANCHOR_EVENT |
| ml/tests/fixtures/W06/qualified-response.json | ACK_TO_APPLIED_STATE | CMD-QUALIFIED | OBSERVED_DIAGNOSTIC_ONLY | 0.300000 | 0.050000 | SYNTHETIC_UNIT_TEST | 2 | NOT_ESTIMABLE | electrical-current-step-v1 | NONE |
| ml/tests/fixtures/W06/qualified-response.json | APPLIED_TO_ELECTRICAL | CMD-QUALIFIED | OBSERVED_DIAGNOSTIC_ONLY | 0.200000 | 0.050000 | SYNTHETIC_UNIT_TEST | 3 | 0.000000 | electrical-current-step-v1 | SYNTHETIC_UNIT_TEST_EVIDENCE |
| ml/tests/fixtures/W06/qualified-response.json | APPLIED_TO_THERMAL | CMD-QUALIFIED | OBSERVED_DIAGNOSTIC_ONLY | 0.300000 | 0.050000 | SYNTHETIC_UNIT_TEST | 3 | 25.000000 | chamber-air-temperature-step-v1 | SYNTHETIC_UNIT_TEST_EVIDENCE |
| ml/tests/fixtures/W06/qualified-response.json | COMMAND_TO_ACK | CMD-QUALIFIED | OBSERVED_DIAGNOSTIC_ONLY | 0.200000 | 0.050000 | SYNTHETIC_UNIT_TEST | 2 | NOT_ESTIMABLE | electrical-current-step-v1 | SYNTHETIC_UNIT_TEST_EVIDENCE |
| ml/tests/fixtures/W06/qualified-response.json | COMMAND_TO_ELECTRICAL | CMD-QUALIFIED | OBSERVED_DIAGNOSTIC_ONLY | 0.700000 | 0.050000 | SYNTHETIC_UNIT_TEST | 3 | 0.000000 | electrical-current-step-v1 | SYNTHETIC_UNIT_TEST_EVIDENCE |
| ml/tests/fixtures/W06/qualified-response.json | COMMAND_TO_THERMAL | CMD-QUALIFIED | OBSERVED_DIAGNOSTIC_ONLY | 0.800000 | 0.050000 | SYNTHETIC_UNIT_TEST | 3 | 25.000000 | chamber-air-temperature-step-v1 | SYNTHETIC_UNIT_TEST_EVIDENCE |

A numeric latency is emitted only for synthetic unit-test controls or for physical evidence whose anchor, channel quality and clock evidence are qualified. `VERIFIED_MEASURED_RESPONSE` is the only state that may be read as a measured physical response. `NOT_ESTIMABLE_*` and `CENSORED` are not zero-second responses.

## 8. Scientific limits

- The A W06 command fixtures are host-generated/synthetic: no transport, no backend issuer and no energized round trip exist.
- An ACCEPTED ACK is protocol evidence, not applied cooling and not electrical or thermal response.
- Device uptime is boot-scoped; no absolute UTC epoch is carried by the A serial command line.
- Numeric PZEM power under UNKNOWN quality is never a certified electrical response; the TEC hot side is never chamber-air response.
- The real A W09 capture has no command/ACK lines; its applied-state observations are device-reported and not command-linked.
- W06 does not compute AIW. `compute_aiw` in the W04 contract remains the gate for a complete, non-overlapping multi-component chain.
- Response thresholds are configurable analysis floors recorded in the manifest, not frozen hardware contract thresholds.

## 9. Reproduction

```bash
cd ml
uv run --locked --python 3.12 --extra test python scripts/event-alignment-W06.py --source ../evidence/A/W09/exports/CG-S1-H8C-600S.json --source ../backend/fixtures/telemetry_v0.json --a-run-index ../evidence/A/W09/s1-run-index.json --a-command-log ../evidence/A/W06/demo-command-capture.log --a-command-provenance HOST_GENERATED_SYNTHETIC --event-fixture tests/fixtures/W06/qualified-response.json --out reports/W06 --baseline-window-s 10.0 --electrical-max-window-s 60.0 --thermal-max-window-s 300.0 --max-gap-s 5.0 --sustained-observations 3 --electrical-min-change-a 0.05 --thermal-min-change-c 0.25 --max-uncertainty-s 10.0 --repository-revision 84dd39fbd8e500ab14ff1d4a38a746e7fad674ed
```

Repeated execution on the same inputs and configuration produces identical artifacts. The report contains no runtime timestamp and no local absolute path.
