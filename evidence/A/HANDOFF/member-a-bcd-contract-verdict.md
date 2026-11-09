# Member A → B/C/D interface contract: compatibility verdict

Worker R. Machine-readable companion: [`member-a-bcd-contract.json`](member-a-bcd-contract.json),
row-level matrix: [`member-a-bcd-compatibility-matrix.csv`](member-a-bcd-compatibility-matrix.csv),
generator (re-runnable): [`contract_probe.py`](contract_probe.py).

Every claim is marked **OBSERVED** (read or executed in this session against the
committed tree) or **HISTORICAL** (carried from an existing document). Nothing here
is a hardware, bench, broker or database result. No class was promoted.

## Verdict in one line

**This is not a version-negotiation gap and it is not a true breaking schema-3-vs-1
conflict — it is a category error.** Member A emits a *serial `key=value` line*, Member C
contracts a *JSON MQTT envelope*. There is no device-side MQTT publisher at all, so a
**translation layer is required**, and three specific backend literals must change on
Member C's side regardless of it.

## A. The three schema numbers (OBSERVED)

| # | Symbol | Value | file:line |
|---|---|---|---|
| 1 | `CG_TELEMETRY_SCHEMA_VERSION` | `3` | `firmware/main/coldguard_config.h:472` (this worktree, HEAD `c2c0e35`) — same value at `:482` in `A-W06-command-ack` (extra W06 commentary shifts the line) |
| 2 | `SCHEMA_VERSION` | `3` | `firmware/tools/cg_telemetry_schema.py:43` (`SUPPORTED_SCHEMAS = (1, 2, 3)` at `:44`) |
| 3 | `WIRE_SCHEMA_VERSION` | `1` | `backend/src/coldguard_backend/contracts.py:38` (`Telemetry.schema_version: Literal[1]` at `:157`) |

The two device numbers are **consistent**; the third counts a different stream.
`coldguard_config.h:468-476` and `cg_command.h:241-243` state in-repo that the serial
schema does not amend the JSON envelope contract. The real gate is
`backend/src/coldguard_backend/validation.py:47` (`SUPPORTED_SCHEMA_VERSIONS = frozenset({1})`)
enforced at `validation.py:210`.

Also OBSERVED: `control/src/coldguard_control/commands.py:51` `SUPPORTED_SCHEMA_VERSION = 1`
for the *command* envelope, which agrees with `cg_command.h` (`schema=1`).

## B. Frame grammars

Full byte-level grammar is in the JSON under `grammars`. The 96-token order of one
schema-3 telemetry frame, as emitted by `cg_telemetry.c:231-385` and validated by
`cg_telemetry_schema.parse_line`:

`schema timestamp_utc timestamp_utc_source uptime_ms elapsed_ms run_elapsed_ms run_id
device_id boot_id boot_count seq firmware_version hardware_config_id calibration_id
test_phase t1_rom t2_rom t3_rom spare_rom role_status rom_source t_inside_c
t_inside_status t_inside_src t_cold_side_c t_cold_side_status t_hot_side_c
t_hot_side_status t_ambient_c t_ambient_status relative_humidity_pct
relative_humidity_status door_open door_status door_raw voltage_v voltage_status
current_a current_status power_w power_status energy_wh energy_status pwm_duty
fan_command fan_status output_stage tec_state fault_code fault_reason sensor_validity
power_validity raw_t1_c raw_t1_status raw_t2_c raw_t2_status raw_t3_c raw_t3_status
raw_spare_c raw_spare_status thermal_age_ms power_age_ms door_age_ms thermal_seq
power_seq door_transitions door_cycles probes_valid probes_expected thermal_quality
environment_quality door_quality electrical_quality quality cooling_applied
cooling_applied_source cooling_evidence health health_thermal health_bme health_door
health_power health_telemetry health_control thermal_beats power_beats door_beats
thermal_max_gap_ms power_max_gap_ms door_max_gap_ms command_id desired_cooling
desired_duty_permille last_ack_status last_ack_reason`

Sentinels (OBSERVED): `timestamp_utc=UNAVAILABLE` + `timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK`
are the only accepted values (`cg_telemetry_schema.py:470-478`); a missing number is the
literal `nan` (`coldguard_config.h:577`), never `0`; `desired_duty_permille=nan` beside
`desired_cooling=NONE` is the honest no-request state (`cg_telemetry_schema.py:154-157`);
age fields saturate at `2^64-1` on clock rewind (`cg_telemetry.c:67-73`);
`*_status ∈ OK|INVALID|STALE|NO_DATA|NOT_ASSIGNED|SENSOR_NOT_PRESENT|UNVERIFIED`
(`cg_telemetry.h:93-99`). A frame is **refused, never truncated** (`cg_telemetry.c:33-39`,
`cg_log.c:70-92`, budget `CG_TELEMETRY_LINE_MAX=3072` at `coldguard_config.h:474`).

The probe frame the matrix is built on is **DERIVED, not captured** — see `G` below.

## C. Compatibility matrix

`member-a-bcd-compatibility-matrix.csv` has 96 rows: 23 mapped onto a backend field and
73 IGNORED (extra device-only fields allowed by `Telemetry._WireBase extra=allow`), with
2 REJECT at source and 1 REJECT - unsatisfiable on the device. Verbatim classifier output is in JSON
`ingest_cases`.

| Device token | Backend field | Verdict | Why |
|---|---|---|---|
| `schema=3` | `schema_version` | **REJECT** | `UNSUPPORTED_SCHEMA: unsupported schema_version 3; supported: [1]` — `validation.py:47,210` |
| `timestamp_utc=UNAVAILABLE` | `captured_at` | **REJECT, unsatisfiable** | `contracts.py:161` requires a datetime; `validation.py:230` rejects naive; device has no wall clock (`cg_telemetry.c:232`) |
| `quality` (value `UNKNOWN`) | `quality.overall` | **REJECT** | `contracts.py:40` `Quality = Literal["VALID","DEGRADED","INVALID"]`; device vocabulary is four states (`cg_telemetry_schema.py:216`); Member D **does** model `UNKNOWN` (`control/.../types.py:25-35`) |
| `pwm_duty=0` (permille int) | `actuation.duty` | **UNIT CLASH** | `contracts.py:132-137` bounds `[0.0, 1.0]`; raw `250` fails, `0.25` only after scaling |
| `door_open`/`door_status` | `door.state` | **TRANSLATION REQUIRED** | `contracts.py:44,107` wants `OPEN|CLOSED|UNKNOWN`; the TELEM line never emits those tokens (`cg_telemetry.c:275-281`) |
| `raw_t1_c`/`raw_t2_c`/`raw_t3_c` | `thermal.t1/t2/t3` | **name + type** | `_coerce` leaves them as text (`cg_telemetry_schema.py:309-345`); backend demands JSON number or null (`validation.py:57-68`) |
| `t_ambient_c`,`relative_humidity_pct` | `environment.t_air`,`environment.rh` | name map only | values already numeric |
| `voltage_v`,`current_a`,`power_w`,`energy_wh` | `electrical.*` | **ACCEPT** | names identical — the only clean group |
| `cooling_applied` | `actuation.cooling` | name map only | same `ON/OFF` vocabulary |
| `thermal_quality`,`environment_quality`,`electrical_quality` | `quality.*` | name map, `UNKNOWN` risk | as row 3 |
| `device_id`,`boot_id`,`seq`,`uptime_ms`,`run_id`,`hardware_config_id`,`firmware_version`,`calibration_id` | same names | **ACCEPT** | direct pass-through |
| 70 remaining tokens (`test_phase`, `fault_code`, `fault_reason`, `health*`, `*_age_ms`, `*_beats`, `rom`, `tec_state`, `command_id`, `desired_cooling`, `last_ack_status`, `last_ack_reason`, …) | `<none>` | **IGNORED** | `contracts.py:84` `extra="allow"` accepts and drops them; none is a column in `normalized_store.telemetry` |

**Command path mismatches (OBSERVED, named verbatim):**

| Member C / D | Member A device side |
|---|---|
| `created_at: datetime` `contracts.py:241` | `created_at_ms` int — `cg_command.c:704` |
| `expires_at: datetime` `contracts.py:242` | `expires_at_ms` int — `cg_command.c:718` |
| `action.cooling` nested `contracts.py:224` | `action_cooling` flat token — `cg_command.c:746` |
| `action.duty` float `[0.0,1.0]` `contracts.py:227-232` | `action_duty_permille` uint32 — `cg_command.c:759` |
| accepts unknown keys (`extra="allow"`) | **refuses** them: `UNKNOWN_FIELD` `cg_command.c:780` |
| optional `controller_id` `contracts.py:243` | `controller_id` optional (`cg_command.c:581`), but 9 of 10 fields mandatory (`cg_command.c:576-586`) |
| — | 26 device reason tokens absent from `control/.../types.py` `ReasonCode` (JSON `ack_reason_vocabulary`) |

**Probe commands against Member D's real validator** (JSON `control_validator_probe`):
a request carrying the device's own `schema_version=3` returns
`status=REJECTED reason_code=INVALID_JSON detail="schema: unsupported schema_version 3; supported: 1"`,
while the same request at `schema_version=1` returns `ACCEPTED`.

**ACK-status sets agree** (`ACCEPTED/REJECTED/DUPLICATE_CANONICAL/EXPIRED/SAFETY_BLOCKED/INVALID_STATE/OUT_OF_RANGE`,
`cg_command.h:106-114` = `control/.../types.py:115-128` = `cg_telemetry_schema.py:252-260`);
the device adds `NONE` on the telemetry line only, explicitly not an ACK status
(`cg_telemetry_schema.py:261-263`).

## D. MQTT topics (verbatim, OBSERVED)

Device side: **zero MQTT topic strings exist.** `firmware/main/app_main.c:20` —
`* Not implemented on purpose: MQTT/telemetry publishing, cloud commands and`. A
repo-wide grep of `firmware/` finds MQTT only in the static-check denylist
(`firmware/tools/cg_check_firmware_w04.py:63`). The device wire surface is serial only.

Backend subscriptions, `backend/src/coldguard_backend/mqtt_consumer.py:60-65`:
`coldguard/+/telemetry`, `coldguard/+/event`, `coldguard/+/state`, `coldguard/+/health`.
Canonical telemetry topic regex, `validation.py:52`: `^coldguard/([^/+#]+)/telemetry$`.

| Source | Line | String |
|---|---|---|
| docs/00 | `docs/00-project-scope-architecture.md:1593` | `coldguard/{deviceId}/ack` |
| docs/02 | `docs/02-aiot-closed-loop-engineering.md:787` | `coldguard/{device_id}/command_ack` |
| docs/05C | `docs/05C-member-c-iot-backend-digital-twin.md:425` | `coldguard/{device_id}/command_ack` |
| broker ACL | `infra/mosquitto/acl.conf:29` | `topic write coldguard/coldguard-001/command_ack` |
| broker ACL | `infra/mosquitto/acl.conf:37` | `topic read coldguard/+/command_ack` |
| backend consumer | `mqtt_consumer.py:60-65` | **no `command_ack` subscription** |
| backend simulator | `simulator.py:57` admits family `command_ack` | `simulator.py:63-73` has no policy — probe raised `ValueError: no publisher policy for family 'command_ack'` |
| control | `control/src/coldguard_control/*` | **no topic strings at all** (pure validator, `commands.py:14-17`) |

**Mismatches:** docs/00 `:1593` `/ack` vs docs/02+05C+ACL `/command_ack`; docs/00 uses
`{deviceId}` where every other source uses `{device_id}`. The ACL authorises the ACK path
in both directions while the consumer never subscribes to it — device ACKs are
unobservable in the backend today.

**PUBACK vs execution.** No conflation found. `mqtt_consumer.py:12-31` states the PUBACK
is not the authority for "durably processed"; `simulator.py:22` states counts report
"PUBACK completion only"; `cg_command.h:48-54` states an ACK is protocol evidence and
that in this build the applied state an ACK can ever report is `OFF`;
`commands.py:15-17,119-131` states `ACCEPTED` is not physical proof. **Recorded as an
open risk rather than a defect:** the loop cannot be closed today because there is no
transport, so no ACK of any kind is deliverable (A-W06-05/06 remain physically open).

## E. Test suites actually run in this worktree (OBSERVED)

Interpreter `C:\Users\dlbac\Downloads\coldguard-repo\_audit-venv\Scripts\python.exe`
(CPython 3.14, pytest 9.2.0, pydantic 2.14.1), `PYTHONUTF8=1`, offline, no broker, no DB.

| Suite | Command | Verbatim result |
|---|---|---|
| Member C backend | `PYTHONPATH=src pytest -q` in `backend/` | `75 passed, 41 skipped, 1 warning in 0.45s` |
| Member D control | `PYTHONPATH=src pytest -q` in `control/` | `330 passed in 0.20s` |
| Member A firmware host tools | `python -m unittest discover -s tests -t tests` in `firmware/tools/` | `Ran 370 tests in 11.606s` / `OK` |

All 41 backend skips carry the same reason, verbatim:
`requires COLDGUARD_TEST_DATABASE_URL …` / `requires COLDGUARD_TEST_MQTT_HOST pointing at the
W02 test broker` (offline host, as required).

**No test failed, and that is the finding, not a pass.** Nothing in either suite crosses
the A→C boundary: no backend or control test mentions `#CG TELEM` or
`cg_telemetry_schema`, and no firmware test imports `coldguard_backend` or
`coldguard_control`. The nearest backend test is
`backend/tests/test_validation.py:97 test_unsupported_schema_rejected_never_parsed_as_compatible`,
which only probes `schema_version = 2`. Three green suites therefore **do not** prove
compatibility; the incompatibility is proven only by the probe in
`member-a-bcd-contract.json` (`ingest_cases`).

## F. Which side must change

1. **A translation layer is required and it belongs to Member C's gateway.** No device
   change can produce a JSON MQTT envelope: there is no network stack
   (`app_main.c:20-21`, `cg_command.h:6-9`), and adding one is not Member A's W06 scope.
2. **Member C must change three things regardless of the gateway** (each is a closed
   literal that rejects a value a real device frame carries):
   - `contracts.py:40` `Quality` must admit `UNKNOWN`. Member D already does
     (`control/.../types.py:35`) and Member A's docs/01 vocabulary is four states
     (`cg_telemetry_schema.py:216`). Today `quality=UNKNOWN` is unrepresentable.
   - `contracts.py:161` / `validation.py:230`: `captured_at` must be explicitly documented
     and typed as **gateway-assigned ingest time**, with a provenance flag, because the
     device can only ever say `UNAVAILABLE`. Member A must **not** be asked to invent a clock.
   - `mqtt_consumer.py:60-65`: add `("coldguard/+/command_ack", 1)`, and give
     `simulator.py:63-73` the missing `command_ack` QoS/retain policy.
3. **Unit and identity conventions must be frozen, not patched per-field**: `duty`
   float `[0.0,1.0]` vs `pwm_duty`/`*_duty_permille` integer permille; `created_at`/
   `expires_at` ISO datetime vs `*_at_ms`; nested `action.*` vs flat `action_*`; and the
   fact that the device refuses unknown command fields (`cg_command.c:780`) while the
   backend accepts them — that asymmetry is deliberate and must not be relaxed.
4. **Member A owns two fixes** (defect `R-07`, `R-08` in the JSON register) and they do
   not require touching B/C/D code.

## G. Blockers, stated exactly

- **B-1 (RESOLVED in this remediation).** The committed W06 demo capture now carries a
  real `schema=3` telemetry frame with the full W06 command/ACK tail
  (`cg_telemetry.c:382-384`), parsed directly by `cg_telemetry_schema.parse_line`
  (provenance: `PARSED, not derived` in `member-a-bcd-contract.json`).
- **B-2.** No live broker, no PostgreSQL, no device. All 41 backend skips and every
  physical A-W06 item stay open; nothing in this report is a round-trip proof.
- **B-3.** The command path cannot be closed at all today: `CG_CMD_SOURCE_NETWORK` is
  documented as "reserved: no transport exists in this build" (`cg_command.h:95`), so
  even a correct gateway payload could not be stamped admissible without Member C's
  delivery slice.
- **B-4.** `docs/00:1593` is stale against `docs/02:787`; the canonical docs owner must
  resolve it, not Member A.
