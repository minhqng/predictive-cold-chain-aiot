# ColdGuard · Data Dictionary v0 (W01, Member B)

> Deliverable of task **B-W01-02** (Doc `05B` §29). Consumer-side contract for the machine-analyzable
> record ColdGuard P0 produces from the **frozen current BOM** (three DS18B20 + BME280 + MC-38 +
> PZEM-017 with 50 A / 75 mV shunt, one BTS7960/IBT-2 cooling branch). This is **not** a firmware
> schema, MQTT topic spec, or DB migration; it is the field semantics ML/analytics consume.

| Field | Value |
|---|---|
| Owner | Member B |
| Reviewer focus | Dataset/split reviewer: A or C (Doc `04` §3.3); C's wire contract cited as TEAM_DEPENDENCY context |
| Parent docs | Doc `00` §§0.3, 3.1–3.3, 3.9–3.11, 5.1, 5.3–5.4 · Doc `01` §§1.3–1.7, 1.17, 2.4–2.6, 6–9, 12, 16–24, 33–35, 38–40, 45–46 · Doc `02` §§2, 4–5, 8.2, 13, 14, 25–26, 28–32, 35, 39–40, 45, 51, 59–63 · Doc `03` §§15, 31, 38, 57, 72, 85, 87–88, 95, 103, 109, 119–122, 125, 159–162, 172, 176–180 · Doc `04` §§3.3, 10.1–10.2, 10.7 · Doc `05B` §§3.2, 6–7, 9, 10, 14, 26, 29–30, 38 |
| Status | v0 (W01 contract) |

Tier legend: **CANONICAL** (Docs `00`–`03` fix it) · **DERIVED** (computed downstream under a versioned formula) · **PROVISIONAL** (unfrozen; later predeclared freeze) · **TEAM_DEPENDENCY** (another member's artifact, quoted as observed) · **SCHEDULED_DEBT** (deferred, owner named). All four files share one legend; a value not bearing the source doc is either TEAM_DEPENDENCY (cited path) or PROVISIONAL.

---

## 1. Scope, identity model, and exclusions

### 1.1 Hardware scope — exact frozen BOM (`00` §3.1, CANONICAL)

| BOM ID | Item | Analytical symbol(s) in this dictionary |
|---|---|---|
| HW-02 | DS18B20 waterproof, 1 m ×3 | `t1_c`, `t2_c`, `t3_c` |
| HW-03 | BME280 3.3 V module | `t_air_c`, `rh_pct` |
| HW-04 | MC-38 reed switch | `door_state` |
| HW-05 + HW-06 | PZEM-017 RS485/Modbus + external 50 A / 75 mV shunt | `cooling_voltage_v`, `cooling_current_a`, `cooling_power_w`, `cooling_energy_counter_wh` |
| HW-08 | BTS7960 / IBT-2 H-bridge module | `applied_cooling`, `applied_duty` |
| HW-09 + HW-10 | TEC1-12715 (exact purchased SKU) + V1 12 V assembly | plant under test (no direct electrical telemetry channel; observed only through DS18B20/PZEM) |
| HW-11 | Chamber HS2 6 L | spatial relationships fixed by geometry config |
| HW-01 | Dual ESP32-S3R2 board | `device_id`, `boot_id`, `firmware_version`, `uptime_ms` |
| HW-12–HW-18 | PSU 12 V/33 A, fuses, XL4015, TB4504, PCT218 | power-path config identity, not per-sample channels |
| HW-19–HW-24 | Power wires, jumpers, headers, 4.7 kΩ resistor, thermal paste | assembly/config evidence only (no telemetry channels) |

Sensor sampling targets are CANONICAL planning targets (≈1 Hz DS18B20/BME280, ≈1–2 Hz PZEM, door event-driven + sampled state, ≈1 Hz MQTT; `00` §3.9). Exact realized cadence per run is measured, never assumed (`03` §120).

### 1.2 Dedup / message identity (CANONICAL + TEAM_DEPENDENCY)

- Physical-sample identity: **`(device_id, boot_id, seq)`** (`02` §4.2, §13.3). Timestamps are event-time evidence, never identity (`02` §4.3).
- Duplicate QoS-1 deliveries of the same identity are **one normalized physical sample**; duplicates remain separately observable in the raw delivery log (TEAM_DEPENDENCY: `telemetry_raw` has no unique constraint; normalized `telemetry` enforces `UNIQUE(device_id, boot_id, seq)` — `backend/src/coldguard_backend/migrations/versions/0002_raw.py`, `0003_normalized.py`).
- **No backfill fabricates normalized rows from historical raw deliveries** (TEAM_DEPENDENCY, migration 0003 docstring) — formalized for B's use in `leakage-risk-register.md` LRK-12/13.

### 1.3 Exclusions — legacy / superseded fields (CANONICAL, `02` §14.3 + `00` §3.2)

Forbidden in any consumer schema: `current_1`, `current_2`, `power_1`, `power_2`, `cmd_1`, `cmd_2`, INA226 references, second-TEC references (`tec_2`), 20 L-chamber assumptions. Rows carrying them are **not comparable** evidence and are excluded (see §14). Team-observed enforcement: `LEGACY_FORBIDDEN_KEYS` in `backend/src/coldguard_backend/contracts.py` rejects these recursively at wire admission (TEAM_DEPENDENCY, C-W01-03).

---

## 2. Identity, provenance and run metadata

Run-level metadata attach: some identifiers govern at sample level, others at run/experiment level (`00` §5.1; `05B` §6 mandatory identifiers; `02` §14.2 tail, §14.8 experiments). Wire presence per sample is TEAM_DEPENDENCY (`backend/fixtures/telemetry_v0.json` + `contracts.py`: non-empty, non-negative validators); `scenario_id`/`controller_id` attach to the run/experiment record (`02` §14.8), and only `run_id` travels on the per-sample wire (observed).

| Field (normalized name) | Unit / type | Semantics | Tier | Canonical source |
|---|---|---|---|---|
| `device_id` | text | Edge controller identity; logical device instance (`coldguard-001` in fixtures). | CANONICAL | `00` §5.1 |
| `boot_id` | text | Firmware-boot session identity; groups one power-on session's monotonic ordering. | CANONICAL | `02` §4.4 |
| `seq` | integer ≥ 0 | Monotonic-within-boot acquisition sequence. | CANONICAL | `02` §4.5; `01` §18.3 |
| `time` | TIMESTAMPTZ | Event time (edge-captured sample time). See §3. | CANONICAL | `01` §18.1–18.2 |
| `uptime_ms` | integer ms ≥ 0 | Monotonic duration within boot; auxiliary relative-time/clock-uncertainty evidence. | TEAM_DEPENDENCY (name) / CANONICAL (concept `01` §18.5) | — |
| `run_id` | text (hint `CG-S…-…`) | Physical experiment run association; nullable per message (pre-experiment samples may lack a run). | CANONICAL | `00` §5.3; `05B` §6 |
| `scenario_id` | text (S1–S6 family) | Which predeclared scenario the run executes. Attached at the run/experiment record, not on the per-sample wire (observed). | CANONICAL (concept) / TEAM_DEPENDENCY (transport) | `03` §31; `02` §14.8 |
| `controller_id` | text | Which controller governed the run (reactive/Controller A vs predictive/Controller B vs manual). Attached at the run/experiment record; appears in command records as the commanding origin. | CANONICAL (concept) — observed enum TEAM_DEPENDENCY (C/D schema) | `03` §38; `02` §25–26, §14.8 —`04` §10.7 |
| `hardware_config_id` | text, pattern `CG-HW-…` | Frozen hardware configuration identity, incl. `pin_map_version` and exact TEC SKU label. | CANONICAL | `01` §39.1 |
| `firmware_version` | text | Firmware build identity of the sample. | CANONICAL | `02` §60.2 |
| `calibration_id` | text, pattern `CG-CAL-…`, nullable | Calibration/check bundle identity; samples are comparable only within it. | CANONICAL | `01` §39.2 |
| `schema_version` | integer | Wire/protocol version; currently `1` per Doc `02` examples and C contract (TEAM_DEPENDENCY observed value). Breaking semantic change ⇒ new version (`02` §60.1, §61). | CANONICAL (rule) / TEAM_DEPENDENCY (current value) | — |
| `backend_received_at` | TIMESTAMPTZ | Arrival time at backend; never substitutes for `time` (§3). | CANONICAL (concept) / TEAM_DEPENDENCY (realized column) | `02` §14.2 |

Pattern examples quoted from docs/fixtures (TEAM_DEPENDENCY context): `CG-HW-001` (hardware config), `CG-S2-A-001` (run; scenario-arm-serial convention), `CG-CAL-…`, `pin_map_version: "pin-v1"` (`01` §39.1). Full B-artifact grammar is governed in `artifact-convention.md` §§2–3.

---

## 3. Time and sequence semantics (CANONICAL, `01` §18; `02` §5)

Three distinct times exist per measurement/event and are **never interchangeable**:

| Concept | Meaning | Role in analytics |
|---|---|---|
| `captured_at` → normalized `time` | Edge-captured physical sample time | Event time used for ordering, windows, labels and every causal statement |
| `received_at` → `backend_received_at` | Backend arrival time of one delivery/replay | Arrival-vs-event delay analysis; **never** a causality anchor for prediction windows |
| persisted time | Database insert/commit time | Storage forensics only (`02` §5.1 family concepts) |

Rules (CANONICAL):

- Where the edge clock is not synchronized, relative order still exists via `boot_id + seq`; store uptime/sequence; **do not manufacture false timestamp precision** (`01` §18.3, §18.5). Wire timestamps are RFC 3339 UTC (`Z` suffix observed in fixtures and `02` §63 exemplars — TEAM_DEPENDENCY).
- Stale data: a value can remain historically valid yet be invalid for control; historical validity ≠ control freshness (`01` §18.4). Feature windows therefore inherit `captured_at` semantics, and freshness thresholds belong to policy config (D-owned), never to analytics-derived constants.
- Stale/late-arriving samples keep historical storage; current twin state must not regress blindly (out-of-order guard; `02` §13.4, `01` §40.2). Analysis datasets must expose the same guard parameterization as metadata (§11).
- Clock-synchronization state is a required metadata concept for offline correctness (`01` §18.5 observes "record synchronization state"). The observed v0 wire contract has **no** explicit `time_sync` field (TEAM_DEPENDENCY artifact, `contracts.py`); Doc `02` §62 quality payload concept includes `time_sync`. Recorded as needed-handoff #2 in §16; nothing is invented here.
- Reboot boundary: a new `boot_id` may restart `seq` from zero; analysis code must never construct cross-boot windows on a shared seq axis alone (register LRK-13). Door-event and sequence-axis windows must be boot-scoped.

---

## 4. Thermal channels — three DS18B20 probes (HW-02)

Authority: Doc `01` §6 (sensor contract) and §17.1 (unit); Doc `02` §4.1 snapshot; wire/normalized names TEAM_DEPENDENCY.

| Field | Unit | Value domain | Semantics | Tier | Authority refs |
|---|---|---|---|---|---|
| `t1_c` / wire `thermal.t1` | °C | real (nullable) + quality | Firmware slot T1 signal. Canonical intended role: near-door chamber air. As-built position differs — §4.1–§4.4. | name TEAM_DEPENDENCY / role intent CANONICAL | `01` §6.4, §6.5; normalized col `0003_normalized.py` |
| `t2_c` / wire `thermal.t2` | °C | real (nullable) | Firmware slot T2 signal. Canonical intended role: central chamber air. **On the current as-built rig this slot carries TEC hot-side, not chamber air** — §4.2. | name TEAM_DEPENDENCY / role intent CANONICAL | `01` §6.4 |
| `t3_c` / wire `thermal.t3` | °C | real (nullable) | Firmware slot T3 signal. Canonical intended role: far/opposite chamber air. As-built position is chamber bottom — §4.2. | name TEAM_DEPENDENCY / role intent CANONICAL | `01` §6.4 |

- **Role assignment permanently binds 64-bit ROM ID → physical position/role** (`01` §6.5 identity contract; §2.4). A consumer must not remix roles from payload positions; unknown ROM ⇒ degraded/invalid path, never silent remap (`01` §6.6 PHY-DS-001/002).
- Position stability is configuration evidence: probe displacement events invalidate affected comparisons (`01` §6.6 PHY-DS-003; run invalidation list `01` §33).
- Raw DS18B20 failures stay visible end-to-end; no wall/cold-plate contact for air-positions; shared conversion semantics across the three probes (`01` §6.6 PHY-DS-004/005/006).
- Air-sample positions measure air, not contact surfaces (`01` §6.6 PHY-DS-005) — relevant to RQ1 spatial semantics.
- VALID-quality thermal sections must carry all three values (C contract validator; TEAM_DEPENDENCY `contracts.py` `_missing_values_need_quality`); DEGRADED/INVALID sections may carry partial values with reduced trust (value absence: `None`).
- Canonical derived thermal-state vocabulary (Tmean/Tmin/Tmax/gradient/std/slope/recovery-slope) is fixed at concept level (`01` §20 formulas) but the **analysis roster** using them is a versioned DERIVED choice (`05B` §10.1) — §12.

### 4.1 Canonical intended measurement roles (CANONICAL)

Doc `01` §6.4 defines the intended position semantics: `T1` = near-door
region, `T2` = central region, `T3` = far/opposite region. These are
**intended** roles, not evidence of the installed geometry.

### 4.2 As-built observed mapping (TEAM_DEPENDENCY, A-owned; not verified by B)

The operator-frozen as-built identification (`evidence/A/W07/geometry-v1.md`
§1 and §4; `evidence/A/W07/probe-identification-v0.md`, accepted 2026-11-02)
and the A→B handoff (`evidence/A/HANDOFF/a-to-bcd-fields.md` §6.1) report:

| Firmware slot | ROM ID | As-built physical position |
|---|---|---|
| T1 | `287088CA00000051` | chamber center |
| T2 | `28AEBF2200000006` | **TEC hot side (hot-side metal; not air)** |
| T3 | `28CBE9CA00000072` | chamber bottom |
| T4 / SPARE | `283BE5C9000000A9` | near the chamber door |

Configuration/ROM context: the mapping was established by the probe
identification captures under the installed bench image `build-t2-hot-side`
(SHA-256 `01cedce3b794638f25ae4c7f1e2dfdcb4b00555fdc81a0bcf4d35ed4187f6c9f`,
recorded in `evidence/A/W04/ARTIFACT-MANIFEST.md`); the ROM ids come from the
firmware's frozen ROM map, not an independent on-wire ROM readback. A's host
tool `firmware/tools/cg_probe_roles.py` exposes the mapping and gates
chamber-air membership on ROM role (`in_chamber_air_aggregate`), not on the
slot literal.

Consequences that must not be hidden:

- `t2_c` currently carries the **hot-side** signal. The literal canonical
  expression `mean(T1,T2,T3)` is therefore not a chamber-air mean on this
  rig, and the literal `G_T = Tmax − Tmin` over all three slots is a
  probe-disagreement statistic, not a chamber-air spatial gradient.
- `T3` is at the chamber bottom, not the canonical far/opposite region, until
  measured geometry establishes an equivalence; do not describe it as
  far/opposite merely because Doc `01` names the slot that way.

### 4.3 Synthetic-fixture assumption (SYNTHETIC — never physical evidence)

The W02 synthetic generator (`ml/src/coldguard_ml/synthetic.py`) builds
`t1_c`/`t2_c`/`t3_c` as nearby chamber-like values around a shared mean for
pipeline-correctness testing. Those values are **synthetic fixtures**, not
measurements: they do not reproduce the as-built hot-side signal, and they
must never be presented as physical T2 or chamber-air evidence. The generator
is changed only if a correctness requirement demands it; this dictionary does
not silently relabel the real hot-side channel.

### 4.4 Physical-use limits and ownership

- **Do not silently relabel the real T2 hot-side signal as chamber air**, and
  do not average incompatible sensor roles into a "chamber" aggregate. The
  original channel identity (`thermal.t2` → `t2_c`) is preserved; no raw
  evidence is rewritten.
- Until A/team reconcile Doc `01` §6.4/§20.1 (and any firmware ROM-role map)
  with the as-built geometry, real rig data must not claim that the current
  hardware satisfies the canonical air-position requirements. T2 remains the
  only hot-side observation, and no hot-side limit is established for it
  (`firmware/main/cg_tec_limits.c` records `HOT_SIDE_LIMIT_NOT_ESTABLISHED`).
- Physical geometry/authority reconciliation and any firmware change belong
  to A/team; B records the dependency and does not edit Doc `01` or firmware.
  This is an open TEAM_DEPENDENCY, not a B-owned licence to remap channels.

---

## 5. Environment channels — BME280 (HW-03)

| Field | Unit | Value domain | Semantics | Tier | Authority refs |
|---|---|---|---|---|---|
| `t_air_c` / wire `environment.t_air` | °C | real (nullable) | Chamber-air temperature (context channel). | name TEAM_DEPENDENCY / semantics CANONICAL | `01` §7.2; `0003_normalized.py` |
| `rh_pct` / wire `environment.rh` | %RH | real 0–100 (nullable) | Relative humidity (context channel). | same | `01` §7.2, §17.2 |

- BME280 is **context sensing, not a substitute for the three spatial probes** (`00` §3.3 project implication; `01` §7.1). It never replaces a missing DS18B20 channel in evidence-grade claims.
- No invented "moisture quality score" at the physical layer, no unit mixing without schema/version (`01` §17.2, §17.1).
- Pressure is NOT a P0 consumer channel (`01` §7.4 pressure excluded from normalized snapshot) — its absence is deliberate, not `None`.
- Failure semantics: BMEUnavailable follows the degraded-path rules (`01` §7.5; `02` §40.3 snapshot family); quality section `environment` then carries DEGRADED/INVALID with `None` or suspicious-value semantics per §9.

## 6. Door channel — MC-38 (HW-04)

| Field | Unit | Value domain | Semantics | Tier | Authority refs |
|---|---|---|---|---|---|
| `door_state` / wire `door.state` | enum | `OPEN` \| `CLOSED` \| `UNKNOWN` | Commissioned-contact semantic state (polarity verified at bring-up; debounced <= raw GPIO transition stream). | CANONICAL enum | `01` §8.2, §8.3, §17.7; `02` §14.2 CHECK constraint |

- Raw GPIO level is never the domain meaning (`01` §17.7). Polarity/debounce commissioning evidence lives in the run's configuration (`03` §15 `SEN-H1-05`).
- **`UNKNOWN` must never be treated as `CLOSED`** (observed C contract docstring + `01` §8.5 PHY-DOOR invariants). `door_state` validity for label/event construction is checked with `UNKNOWN` handled as a distinct state.
- Event identity: door OPEN/CLOSED transitions get event records (concept: `events` table `02` §14.4; realization TEAM_DEPENDENCY/SCHEDULED_DEBT — C W07). Until event-based export exists, analysis consumes door via sampled `door_state` + time axis; the two must agree within the run's timing tolerance (`03` §172 door-event timing audit as the planned gate).

## 7. Electrical channels — PZEM-017 + 50 A / 75 mV shunt (HW-05 + HW-06), cooling branch only

Authority: `01` §9 contract; `00` §3.10; `01` §17.3–17.6 units; `01` §35 energy contract. All currents/powers are **cooling-branch observations, never total-system values** (`00` §3.10).

| Field | Unit | Value domain | Semantics | Tier | Authority refs |
|---|---|---|---|---|---|
| `cooling_voltage_v` / wire `electrical.voltage_v` | V | real ≥ 0 (nullable); 0.01 V device resolution (`01` §17.3) | Branch-side voltage as observed by PZEM (`01` §9.2). Nominal system voltage is 12 V-class (BOM), but expected values are commissioning-characterized, not stated here. | name TEAM_DEPENDENCY / semantics CANONICAL | `01` §9.2 |
| `cooling_current_a` / wire `electrical.current_a` | A | real ≥ 0 (nullable); 0.01 A resolution **with** 50 A profile | Shunt-measured branch current (`01` §9.2, §9.6). Meaningful **only** under correct 50 A profile + validated module state (`01` §38 authority matrix). | same | `01` §9.2, §9.6 |
| `cooling_power_w` / wire `electrical.power_w` | W | real ≥ 0 (nullable); 0.1 W resolution | Cooling-branch power (`01` §9.2). Primary energy-integration source (`01` §35.1–35.2). | same | `01` §9.2 |
| `cooling_energy_counter_wh` / wire `electrical.energy_wh` | Wh | real ≥ 0 (nullable); 1 Wh resolution; **monotonic counter per message** | PZEM energy register (`01` §9.2). Cross-check / long-run measurement ONLY — too coarse for short-run energies (`01` §35.3; `00` §3.10). Never labeled *Total System Energy*. | same | `01` §35.3 |

Semantics rules (CANONICAL unless noted):

- Run energy is integrated from sampled power: `E_Wh ≈ (1/3600) Σ P_i Δt_i` (`01` §35.2; `03` §72) — DERIVED artifact, versioned.
- Counter non-negativity is a wire contract (TEAM_DEPENDENCY validator). Cross-boot counter continuity is **not asserted** (registers may reset at power loss): counter-delta analysis must handle counter reset/rebase events explicitly (not silently) — PROVISIONAL until the operating envelope (A, `01` §39.3) documents the module's reset behavior; offline gaps crossing resets are quality-flagged so fills never fabricate energy (register LRK-14).
- OFF-current semantics (unexpected current while OFF; expected near-zero under OFF) are electrical-state diagnosis concepts (`01` §22.4) whose numeric envelope is commissioning-derived (PROVISIONAL, CG-OE). A/B interpretations requiring it wait for that envelope.
- PWM caution: `cooling_power_w` under fast PWM is not yet a validated energy metric (`00` §3.11; `01` §9.10 PHY-PZ-002; `03` §102) — quantitative PWM-energy use is PROVISIONAL pending characterization.
- Cross-check requirement: PZEM readings are cross-checked against independent evidence; a single-channel claim is not physically verified (`01` §9.11).
- Shunt-dissipation and serial-revision rules constrain the sensing path itself (`01` §9.7; §9.4 PHY-PZ-001); wrong range ⇒ INVALID-quality electrical section (`01` §19.3 invalid examples; `03` §122 "correct PZEM range" QA).

---

## 8. Actuation channels — single cooling branch (HW-08; edge-applied state)

Authority: `01` §12 (IBT-2/BTS7960), §17.8, §24; `02` §14.2; `04` §10.1 (edge applied state supplied by A). **The applied state means what the device actually drove the branch to, at the edge, at sample time.**

| Field | Unit | Value domain | Semantics | Tier | Authority refs |
|---|---|---|---|---|---|
| `applied_cooling` / wire `actuation.cooling` | enum | `ON` \| `OFF` | Edge-applied cooling-branch state at sample time. | CANONICAL enum / name TEAM_DEPENDENCY | `01` §17.8; `0003_normalized.py` CHECK |
| `applied_duty` / wire `actuation.duty` | ratio | `[0.0, 1.0]` (nullable; present when PWM used) | Edge-applied duty (validated range per C wire contract, TEAM_DEPENDENCY). PWM usage remains conditional (§7 cautions). | CANONICAL concept (`01` §24.3 duty ∈ validated range) | `01` §24.3 |

- Default-OFF is a board-level invariant; OFF is a lawful actuation state; REVERSE is an unsafe, excluded state for control (unsafe payload gets rejected by device-side validation before any analysis view matters — `01` §24.4, §12.6 PHY-ACT-001).
- Intent vs application distinction: a **command record** says what the backend asked; `applied_cooling` says what the edge actually set (`01` §1.3 vs §1.4; `02` §28 command vs §4 snapshot). Verification chain: command → applied → electrical response (`PZEM`) → thermal response (`DS18B20`) (`01` §1.5–1.7).
- For features and labels, the *applied* state (and physical response) is authoritative; the *commanded* record is auxiliary intent metadata (`01` §45: no future command/response info used to predict a prior event — see register LRK-04).

## 9. Quality channels — per-section and overall trust

Authority: `01` §19 enum family; `02` §14.2; C wire contract (`contracts.py`) for realized enums (TEAM_DEPENDENCY).

| Field | Value domain | Semantics | Tier | Authority refs |
|---|---|---|---|---|
| `thermal_quality` / wire `quality.thermal` | `VALID` \| `DEGRADED` \| `INVALID` | Thermal section trust (DS18B20 completeness/identity correctness). | enum realized TEAM_DEPENDENCY; semantics CANONICAL (`01` §19) | `01` §19.1–19.3 |
| `environment_quality` / wire `quality.environment` | `VALID` \| `DEGRADED` \| `INVALID` | BME280 section trust. | same | `01` §19 |
| `electrical_quality` / wire `quality.electrical` | `VALID` \| `DEGRADED` \| `INVALID` | PZEM section trust (incl. range-profile correctness). | same | `01` §19.3 |
| `overall_quality` / wire `quality.overall` | `VALID` \| `DEGRADED` \| `INVALID` | Firmware's synthesis per section quality. | same | `02` §14.2 |
| `device_mode` / wire `quality.device_mode` (nullable) | `BOOT` \| `SELF_TEST` \| `ONLINE_NORMAL` \| `ONLINE_DEGRADED` \| `SAFE_LOCAL` \| `FAULT_LOCKOUT` | Device lifecycle mode at sample time (`02` §2.1). | CANONICAL (enum in `02` §2.1–2.7 + C contract) | `02` §2 |

Rules:

- `UNKNOWN` exists in the Doc `01` §19 quality-enum family and the door domain, and as a diagnosis state family; the realized wire contract represents section quality with three values and relies on DEGRADED/INVALID (or door `UNKNOWN`) to express uncertainty (TEAM_DEPENDENCY, `contracts.py` docstring). Any B-side consumer must treat "quality-absent" (`None`) as NOT-VALID, never as valid-by-default.
- VALID ⇒ all section values present (C validator; TEAM_DEPENDENCY). DEGRADED/INVALID sections may still carry values with reduced trust.
- Applicability rules for analytics: INVALID sections' float values must never enter features/labels as if measured; DEGRADED semantics are feature-version-level decisions (`05B` §14) recorded per feature (`03` §125 registered features carry missing behavior).

## 10. Command record — backend consumer view (intent, not execution)

Observed contract (TEAM_DEPENDENCY): `backend/fixtures/command_v0.json`, `contracts.py` `Command`; concept authority: `02` §28 (canonical command), §29 (validation), §31 (freshness/expiry), §32 (ACK), §14.7 (commands table).

| Field | Type | Semantics | Tier |
|---|---|---|---|
| `command_id` | text (logical ID; no enforced UUID text format) | Stable logical identity; duplicate same-ID ⇒ no second actuation (`02` §30.1). | TEAM_DEPENDENCY (rule observed) / CANONICAL (`02` §28 canonical-command concept) |
| `device_id` | text | Target device. | CANONICAL |
| `created_at` / `expires_at` | RFC 3339 UTC | Command issue time and strict TTL; `expires_at > created_at` enforced (`02` §31.1; C validator). Commands are never retained (`02` §8.2; fixture note); stale commands rejected at device and must never actuate (`03` §109). | CANONICAL (semantics) / TEAM_DEPENDENCY (validation realized) |
| `controller_id` | text | Originating controller (e.g., `PREDICTIVE` in fixture). | TEAM_DEPENDENCY enum; CANONICAL concept (`03` §38) |
| `policy_version` | text | D-owned policy identity producing this command (`02` §60.7). | CANONICAL (field) / TEAM_DEPENDENCY (value discipline) |
| `prediction_id` | text (nullable) | Link from command to the prediction that justified it (`02` §14.7). | CANONICAL (field) |
| `run_id` | text (nullable) | Run association of the command act. | CANONICAL |
| `expected_twin_version` | int (nullable) | Optimistic-concurrency guard for desired-state application (`02` §45 reconciliation; observed field). | TEAM_DEPENDENCY |
| `reason_code` | text | Enumerated reason for command issuance (e.g., `PREDICTED_CRITICAL` in fixture example, `02` §63). | CANONICAL (concept) — full enum D-owned (`04` §10.7) |
| `action.cooling` / `action.duty` | enum/ratio | Requested action (same domains as §8). §Commanded state ≠ applied state. | CANONICAL domains |
| status/lifecycle (`published_at`/`ack_at`/`applied_at`/`verified_at`/`status`/`reject_code`/`verification_status`) | — | realized `commands` table fields (`02` §14.7) — storage realization SCHEDULED_DEBT (C). ACK is NOT physical verification (`02` §32.2). | TEAM_DEPENDENCY / SCHEDULED_DEBT |

Forbidden inference: an ACK (any type) must never be used as evidence that cooling physically applied or took effect (`02` §32.2). Physical effect is verified through the §7 electrical and §4 thermal responses (`02` §35 electrical/thermal verification service concept).

---

## 11. Run and experiment validity metadata

- **Run identity**: `run_id` + `scenario_id` + `controller_id` (+ `pair_id` for A/B arms) constitute the experiment key (`02` §14.8 `experiments`; `03` §95 pairing protocol). Run IDs follow the observed `CG-S<scenario>-<arm>-<serial>` pattern (`CG-S2-A-001` in fixtures/`05B` §7).
- **Run validity**: a run is evidence-grade only when its validity ledger says so. Physical invalidation triggers live in `01` §33 (CANONICAL list: unknown hw config, identity mismatch, position change, missing required thermal channels, wrong PZEM range, corrupted time/sequence alignment, protocol deviation, unrecorded manual interventions, unsafe shutdown, uncontrolled reassembly, capture gap over the primary outcome). A supplies invalid-run reasons (`04` §10.2); B records them in dataset manifests and never re-validates a physically-invalid run by downstream cleaning (`01` §45 closing rule).
- **Timing metadata per run**: start/end, disturbance timestamps, pairing/randomization record fields are experiment-manifest concepts (`02` §14.8; `03` §159–162). Realization is C-scope, SCHEDULED_DEBT (experiments table at W07 per `backend` migration 0003 docstring).
- **Synthetic fixtures**: `backend/fixtures/telemetry_v0.json` and `command_v0.json` are DEVELOPMENT slices (fixture self-label: "SYNTHETIC fixture v0 … not a physical measurement"). Fixture-tagged data must never enter a research dataset manifest or be used as physical evidence; dataset export QA must exclude ingest tagged as synthetic. This codifies `03` §122 data-QA pre-ML and `01` §1.17 evidence-grade run.
- **Provenance requirement**: every report-grade record carries the `00` §5.4 version list (hardware_config_id, firmware_version, schema_version, calibration_id, feature_version, model_version, policy_version, backend/git version) — absence ⇒ not report-grade (CANONICAL).

## 12. Derived-state vocabulary (analysis-side, pointers only)

No new formula is minted in W01; this section pins the canonical formulas B's DERIVED features must cite:

- Thermal means/min-max/gradient/std/slope/recovery-slope formulas: `01` §20.1–20.6 (CANONICAL), incl. the "derived must not hide missing raw channels" rule (`01` §2.6).
- Spatial features for RQ1 (Tmax−Tmin family): `00` §0.3 RQ1; `03` §121 disagreement monitoring; `05B` §3.2.
- Electrical-response / cooling-health diagnosis states: `01` §22 (four commanded-vs-response combinations), §23 (five cooling-health states), echoed as DIAG test family (`03` §103). No component-level root causes (`00` §0.3).
- WARNING-state derivation for EWT: threshold + persistence gates frozen later (`03` §87–88, §176 reactive-warning definition for the reactive side).
- Exposure and recovery formulas for A/B outcomes: `01` §21; `03` §§68–70, §177–180.
- Every DERIVED field must: cite its formula, record source channel list + window + causality + missing behavior and bind to a `feature_version` (`03` §125; `05B` §9). Roster finalization is SCHEDULED_DEBT (B-W10 features; prototype versions may exist earlier in the synthetic harness — `05B` §30, §38).

## 13. Missing-data handling contract (consumer rules)

- Bounded rules from `05B` §14 + `03` §85 (CANONICAL): never silently forward-fill a physical channel indefinitely; short missing intervals handled only by predeclared method; a critical-event data gap can invalidate the run (`01` §33 data-capture-gap trigger); imputation cannot create physical evidence.
- Concretely for B consumers: (a) `None` + non-VALID section quality = missing/low-trust state (never a numeric zero when PZEM is simply absent — register LRK-14); (b) drop window / explicit missing flag / bounded predeclared interpolation / feature-disable are the four legal strategies, all recorded in the feature version; (c) completeness must account for the actual acquisition cadence, with stronger completeness demanded over the primary event window than the run average (`03` §119).
- Lateness/replay: offline-buffer replayed samples keep identity (`02` §39.1); analysis must detect replay patterns (duplicate identities, out-of-order arrival) and reproduce backend-side dedup semantics in any offline table (LRK-13).

## 14. Forbidden and legacy register (flat checklist for consumers)

1. Legacy two-branch fields: `current_1/2`, `power_1/2`, `cmd_1/2` — forbidden (`02` §14.3).
2. INA226 / second-TEC / thermal-assembly substitute assumptions — forbidden (`00` §3.2).
3. 20 L chamber / scaled-chamber assumptions — forbidden (`00` §3.2, §3.8).

4. Raw GPIO levels presented as door semantics — forbidden (`01` §17.7).
5. ACK treated as physical verification — forbidden (`02` §32.2).
6. Command intent presented as applied state — forbidden (`01` §1.3 vs §1.4).
7. `total_system_energy` wording on the PZEM path — forbidden (`00` §3.10).
8. Arrival time (`backend_received_at`) used as causal event time — forbidden (`01` §18.1–18.2).
9. Cross-boot seq joins treated as continuous order — forbidden (§3; register LRK-13).
10. `UNKNOWN` door collapsed into `CLOSED` — forbidden (`01` §8).
11. Invalid-quality values entering features/labels as measurements — forbidden (§9 rules).
12. Fabricated identities/records (backfill inventing authority) — forbidden (TEAM_DEPENDENCY: migration 0003 no-backfill rule; `01` §1.17 evidence-grade run).

## 15. Open-items ledger (dictionary v0's PROVISIONAL / TEAM_DEPENDENCY / SCHEDULED_DEBT set)

| # | Item | Tier | Owner / freeze point | Anchor |
|---|---|---|---|---|
| 1 | Horizon candidates → one primary horizon | PROVISIONAL | B, before final predictive test | `03` §44 |
| 2 | `T_critical` value; representative temperature | PROVISIONAL | B, predeclared pre-split freeze | `03` §§42–43 |
| 3 | Door protocol duration/tolerance values | PROVISIONAL | A protocol freeze | `03` §§32–33 |
| 4 | CG-OE envelope (healthy/OFF current-power ranges, max duty, response window) | PROVISIONAL (A commissioning) | A | `01` §39.3 |
| 5 | TEC fuse final value | PROVISIONAL | A | `01` §16 |
| 6 | PWM switching range and quantitative electrical use | PROVISIONAL | A+B characterization | `01` §34 |
| 7 | T_config / latency component numbers | PROVISIONAL | measured, never assumed | `03` §57 |
| 8 | Full ordinal `controller_id`/`reason_code` enums | TEAM_DEPENDENCY | C/D schemas | `02` §59; `04` §10.7 |
| 9 | `events`/`experiments`/`commands`/`predictions` table realizations | TEAM_DEPENDENCY / SCHEDULED_DEBT | C (W07 for semantics; predictions later) | `02` §14.4–14.7; `backend` migrations |

## 16. Handoff note (the only W01 "ask" this dictionary propagates)

1. **To C (analytical field requirements)**: keep per-section + overall quality, full provenance block, both event and arrival timestamps, and the `raw_id` provenance linkage in any dataset export (`02` §14.2 already carries `backend_received_at`); export QA must preserve dedup semantics (`UNIQUE(device_id, boot_id, seq)`) and exclude fixture-tagged synthetic data; provide dataset/checksum/manifest facility per `02` §51. The `time_sync` concept of `02` §62 is not represented in the observed v0 wire contract — B asks C to surface clock-synchronization state before locked predictive datasets (needs `01` §18.5); no schema change is asserted here.
2. **To A (required physical metadata)**: ROM↔role registration, position-change records, calibration ids, invalid-run reasons, disturbance/pairing timestamps (specifics above in §11; canonical list in `04` §10.2).
3. **To D (prediction vs policy)**: the model emits scores/warnings only; every actuation decision parameter (operating threshold for commands, persistence, safety limits, duty) is a policy-versioned D-state decision travelling the §10 command chain (`05B` §26.4; `01` §46 chain).

---

Dictionary ends. Events/labels/final thresholds intentionally have NO values here — they are PROVISIONAL until their predeclared freezes (matrix §8). Any later patch of this dictionary must (a) restate tier tags, (b) never relax a CANONICAL rule, and (c) never restate a TEAM_DEPENDENCY artifact as B-owned.
