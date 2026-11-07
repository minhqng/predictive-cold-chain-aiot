# ColdGuard · Timing Alignment Contract v1 (W06, Member B)

> Deliverables of **B-W06-01** (event alignment), **B-W06-02**
> (clock/sequence diagnostics), **B-W06-03** (response-window helper) and
> **B-W06-04** (duplicate event handling), Doc `05B` §34.
> This contract freezes conceptual interfaces and stable reason codes; it does
> **not** freeze a numeric hardware response threshold, a measured delay, a
> command transport, or an AIW value.

| Field | Value |
|---|---|
| Owner | Member B |
| Parent docs | `05B` §34 · `04` WEEK 06 · `01` §18 · `02` §§28–33 · `03` §§55–57 |
| Implementation | `ml/src/coldguard_ml/timing_alignment.py`, `ml/scripts/event-alignment-W06.py` |
| Tests | `ml/tests/test_timing_alignment.py`, `ml/tests/fixtures/W06/` |
| Status | v1 freeze of W06 event/timing interfaces; all physical results remain diagnostic until their named evidence gates |

Tier legend: **CANONICAL** (Docs 00–03 fix it) · **DERIVED** (follows from
CANONICAL + a stated assumption) · **IMPLEMENTATION_CHOICE** (B's executable
choice with no physical meaning change) · **TEAM_DEPENDENCY** (A/C/D-owned
input, never invented by B) · **PROVISIONAL_UNTIL_FREEZE** (unset value +
named gate).

---

## 0. Scope and W04 boundary

W06 turns the W04 normalized capture into a provenance-aware event timeline,
diagnostics and bounded response helpers. It also adds one distinct command
event adapter for A's `#CG CMDACK schema=1` serial representation.

W06 does **not**:

- re-adjudicate A's validity or W04's admission ladder;
- parse serial telemetry through the C JSON parser;
- invent a command publication time, backend receive time, ACK, applied state
  or device clock synchronization;
- report a numeric measured delay when the anchor, channel quality or clock
  domain is unqualified;
- compute AIW, train models, or implement W07–W12 work.

`compute_aiw()` in the W04 evaluation contract remains the gate for a valid
multi-component decomposition, including cross-chain overlap rejection.

---

## 1. Typed event representation (B-W06-01)

Eight event types:

```text
DOOR_TRANSITION
TELEMETRY_SAMPLE
POLICY_DECISION
COMMAND_CREATED_OR_PUBLISHED
DEVICE_ACK
APPLIED_STATE
ELECTRICAL_RESPONSE
THERMAL_RESPONSE
```

Every retained event carries, where the source provides it:

| Field group | Fields |
|---|---|
| Source provenance | source path, SHA-256, namespace/version, record/line index, raw vs normalized origin |
| Evidence category | PHYSICAL_MEASURED, HOST_GENERATED_SYNTHETIC, SYNTHETIC_FIXTURE, UNVERIFIED |
| Identity | device_id, boot_id, run_id, identity status, event id |
| Command identity | command_id, ack_seq |
| Sequence | seq, device uptime, source line index |
| Time | device uptime domain, event UTC when carried, backend receive/persisted time when actually carried, clock domain, sync evidence |
| Quality | measurement quality, per-channel quality, uncertainty/resolution |
| Use | eligibility/diagnostic-only label, stable reason codes |

No missing field is filled from another record by matching only a similar
timestamp. A source with no command lines produces an honest empty command
timeline.

### 1.1 Two ordering operations, never conflated

| Operation | Allowed claim |
|---|---|
| `order_timeline()` inside one trusted clock/boot domain | Local order and elapsed intervals within that domain |
| `partial_order()` over protocol identities | A lifecycle-stage relation only; `latency_claim=False` |

A protocol relation is not a measured latency. Ordering refuses mixed clock
domains, mixed devices/boots, missing timestamps and time reversal; it retains
the events and returns a stable status/reason.

A caller-supplied `device_id`/`boot_id` is a constraint validated against the
events, never authority to rewrite their identities. A missing identifier on
one side is not evidence that two events share a device or boot; an incomplete
identity does not support a verified cross-stream association.

### 1.2 Forbidden subtractions

Never subtract:

- two different boot uptimes;
- host receive time from device uptime without a verified transform;
- an unsynchronized device epoch from backend UTC;
- timestamps whose uncertainty exceeds the claimed precision.

No absolute command latency is fabricated from an ACK uptime alone.

---

## 2. Source-contract ledger

`source field → namespace/version → time domain → identity → quality → authority → W06 use`

| Source field | Namespace/version | Time domain | Identity | Quality | Authority | W06 use |
|---|---|---|---|---|---|---|
| A W09 `seq`/`boot_id`/`device_id` | `w09-run-export/v2` | boot-scoped identity | device may be `NOT_CARRIED`; boot+seq is the session identity | `sequence_quality` | A export | telemetry identity and duplicate key |
| A W09 `device_ms` | `w09-run-export/v2` | `DEVICE_BOOT_UPTIME` | boot_id | sequence/provenance quality | A export | within-boot order and elapsed intervals only |
| A W09 `host_capture_time_utc` | `w09-run-export/v2` | `HOST_CAPTURE_UTC` | row/session | `NOT_AVAILABLE` in the committed capture | A export | never promoted to device event UTC |
| A W09 `door_open`/`door_polarity` | `w09-run-export/v2` | `DEVICE_BOOT_UPTIME` | boot+seq | `door_quality` | A export | named OPEN/CLOSED transitions only; UNKNOWN is not a transition |
| A W09 `pwm_applied_permille`/`state` | `w09-run-export/v2` | `DEVICE_BOOT_UPTIME` | boot+seq | `overall_quality` | A export | device-reported applied state; not command proof |
| A W09 `voltage_v`/`current_a`/`power_w`/`energy_wh` | `w09-run-export/v2` | `DEVICE_BOOT_UPTIME` | boot+seq | `electrical_quality` | A export | electrical response candidate; UNKNOWN quality never certifies |
| A W09 `t1`/`t2`/`t3`/`t4` | `w09-run-export/v2` | `DEVICE_BOOT_UPTIME` | boot+seq | per-probe status + frozen ROM roles | A export + role map | chamber-air mean from role-qualified slots only; T2 hot side excluded |
| A W06 `#CG CMDACK` | `coldguard.command-ack-serial/v1` (`schema=1`) | `DEVICE_BOOT_UPTIME`; no UTC epoch | command_id + device + boot + ack_seq | protocol evidence, not measurement | A host-generated fixture | ACK events and duplicate-canonical semantics; never applied proof |
| A W06 `#CG TELEM` | `coldguard.telem-serial/v3` | `DEVICE_BOOT_UPTIME`; `DEVICE_HAS_NO_WALL_CLOCK` | boot+seq | per-field status tokens | A firmware serial namespace, **not** C MQTT JSON | W06 does not parse it; the C JSON parser is never substituted |
| C telemetry JSON `captured_at`/`uptime_ms`/`seq` | `coldguard.telemetry/v1` | `DEVICE_EVENT_UTC` for `captured_at`; boot uptime | device+boot+seq | quality sections | C wire contract; current fixture synthetic/unverified | telemetry event time and identity; no command/ACK linkage |
| C `telemetry_raw` `backend_received_at`/`created_at` | backend storage (C W02) | `BACKEND_RECEIVE_UTC` / `BACKEND_PERSISTED_UTC` | raw delivery row | `ingest_status` | C backend | receive/persisted provenance only; never acquisition time |
| A W10 door-event `timing_uncertainty` | A W10 s2-horizon evidence | `DEVICE_BOOT_UPTIME` | boot+seq | door mapping not attested | A W10 evidence (reference only) | documented 1 s edge uncertainty; no door-open claim |

`#CG CMDACK schema=1` is the command-envelope namespace. It does not make the
serial telemetry line C's `schema_version=1` JSON namespace.

---

## 3. Clock, sequence and provenance diagnostics (B-W06-02)

Per clock-domain/boot group the audit reports:

- first/last event time and count;
- monotonicity, timestamp reversals, sequence gaps/reversals/duplicates and
  uptime resets;
- capture/receive ordering conflicts and missing capture/receive fields;
- impossible negative elapsed intervals;
- uncertain cross-stream associations (e.g. an ACK or applied state with no
  command identity);
- maximum carried uncertainty;
- stable reason codes.

A backend receive timestamp is not a source acquisition timestamp. A missing
field is counted, not fabricated.

The real A W09 check remains: 957 telemetry samples, one boot-scoped device
timeline, median/P95 Δt = 1.000 s, no demonstrated command/ACK, A validity
INVALID, W04 admission blocked. Zero observed commands is not a parser failure
and is not permission to invent one.

---

## 4. Bounded response helpers (B-W06-03)

Relationships:

```text
command → device ACK
command/ACK → applied-state observation
applied/command → electrical response
applied/command → thermal response
```

### 4.1 Detection policy (configurable, recorded)

| Field | Meaning |
|---|---|
| baseline window | pre-anchor observations used to form a baseline median |
| channel + physical role | measurement channel and its qualified physical role |
| expected direction | UP or DOWN, derived from the requested/applied state where relevant |
| minimum change | analysis floor above instrument resolution/noise, not a contract threshold |
| sustained observations | consecutive qualified samples required |
| maximum analysis window | end of the search window |
| gap/quality exclusion | CENSOR or SKIP; non-VALID samples are excluded, never zero-filled |
| timing uncertainty | carried anchor/sample uncertainty and a named bound |
| censoring | an incomplete window is CENSORED, not a zero-second response |

Defaults (`0.05 A`, `0.25 °C`, 1 s timing uncertainty) are named analysis
floors inherited from A's trace-tool review, recorded in the manifest, and
configurable from the CLI. They are not frozen hardware thresholds.

### 4.2 Output states

```text
OBSERVED_DIAGNOSTIC_ONLY
VERIFIED_MEASURED_RESPONSE
NOT_OBSERVED
NOT_ESTIMABLE_MISSING_ANCHOR
NOT_ESTIMABLE_CLOCK
NOT_ESTIMABLE_QUALITY
NOT_ESTIMABLE_BASELINE
NOT_ESTIMABLE_UNCERTAINTY
CENSORED
CONTRADICTORY_EVIDENCE
NOT_APPLICABLE_ACK_NOT_ACCEPTED
DUPLICATE_CANONICAL_NOT_AN_APPLICATION
```

Rules:

- A missing response is not zero seconds.
- An ACK is protocol evidence, not applied cooling and not a physical response.
- Numeric PZEM power under UNKNOWN quality is never a certified electrical
  response.
- The TEC hot side is never chamber air.
- A stable temperature or a generic gradient is not a response.
- A numeric delay is reported only for synthetic unit-test evidence or for
  physical evidence whose anchor, channel quality and clock evidence are
  qualified. Synthetic numbers are never measured hardware performance.
- `VERIFIED_MEASURED_RESPONSE` is the only state that may be read as a measured
  physical response.
- An incomplete event identity (missing device or boot on either side) never
  yields `VERIFIED_MEASURED_RESPONSE`. Same-source, same-boot evidence may
  support an `OBSERVED_DIAGNOSTIC_ONLY` result, including a diagnostic numeric
  delay; a cross-source association without a complete identity is not
  estimable.

---

## 5. Duplicate and idempotency handling (B-W06-04)

Keys are scoped to the actual source contract, never one universal key:

| Event | Key |
|---|---|
| Telemetry / door / applied | device + boot + seq + event subtype (source SHA when device is not carried) |
| ACK | command_id + device + boot + ack_seq |
| Command publication | command_id + device/boot provenance |

Rules:

- identical repeated delivery collapses to one logical event while retaining
  `delivery_count`;
- contradictory payloads sharing one identity are retained and reported, never
  resolved by choosing the latest, earliest, largest or most favorable payload;
- multiple protocol ACKs for one command are visible; a
  `DUPLICATE_CANONICAL` reply does not count as another independent
  application;
- a new `command_id` with the same requested action is a new logical command;
- a reboot resets volatile device idempotency memory; a cross-boot uptime match
  is never duplicate proof;
- missing identity means deduplication cannot be asserted.

---

## 6. Artifacts

| Artifact | Content |
|---|---|
| `ml/reports/W06/event-timeline-W06.csv` | typed events with provenance, identity, clock, quality, eligibility and delivery multiplicity |
| `ml/reports/W06/response-summary-W06.csv` | command/ACK/applied/electrical/thermal relationships and explicit states |
| `ml/reports/W06/timing-audit-W06.md` | scientific separation, source inventory, ledger, counts, diagnostics, duplicates, responses, limits |
| `ml/reports/W06/timing-manifest-W06.json` | machine-readable manifest with code hash, revision, configs, ledger, events, diagnostics, dedup, responses and counts |

The manifest records the analysis code SHA-256 and repository revision used for
generation. A report generated from a previous code revision does not claim a
later one.

---

## 7. Scientific separation

Report independently:

```text
W06 SOFTWARE VERIFICATION: PASS / FAIL / NOT_RUN
REAL COMMAND-LIFECYCLE EVIDENCE: PRESENT_QUALIFIED / PARTIAL / ABSENT / NOT_VERIFIED
PHYSICAL DATA ELIGIBILITY: READY / NOT_READY / NOT_VERIFIED
REAL AIW: ESTIMABLE / NOT_ESTIMABLE
```

A software-green W06 with absent real command evidence is an acceptable
engineering result. It is not a physical verification claim.

The current evidence does not contain a physical command round trip:
A W06 fixtures are host-generated, the W09 capture has no command/ACK lines.
`REAL AIW` remains `NOT_ESTIMABLE`; W06 supplies candidate timing inputs only.
