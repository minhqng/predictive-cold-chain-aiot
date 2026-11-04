# Ambient channel (BME280) — Member A → B / C / D

Added 2026-11-04. This is the field-level contract for the two ambient channels the
BME280 producer now feeds. It does not restate canonical rules from `docs/01` or
`docs/05A`; it records what Member A emits, at what verification level, and what each
consumer must do with it.

Companion files: [`member-a-bcd-compatibility-matrix.csv`](member-a-bcd-compatibility-matrix.csv)
(rows `t_ambient_c`, `relative_humidity_pct`),
[`member-a-bcd-contract-verdict.md`](member-a-bcd-contract-verdict.md) (the serial-vs-JSON
category error, which still applies unchanged to these fields).

## 1. Verification level — four separate statements

These are deliberately not collapsed into one "done".

| Level | State | Evidence |
|---|---|---|
| SOFTWARE_IMPLEMENTED | **yes** | `firmware/main/cg_bme280.c`/`.h` (decision logic, injected port), `firmware/main/cg_bme280_idf.c` (ESP-IDF v6.1 I2C transport), registered in `firmware/main/CMakeLists.txt` with `esp_driver_i2c` |
| HOST_VERIFIED | **yes** | `firmware/tools/tests/cg_bme280_harness.c` (decision logic against a scripted bus) and `cg_bme280_integration_harness.c` (real publication path + real formatter), both compiled and executed under MSVC `/W4 /WX`; `firmware/tools/tests/test_cg_bme280_harness.py`, `test_cg_bme280_integration.py` |
| ESP_IDF_BUILD_VERIFIED | **yes** | `idf.py set-target esp32s3 && idf.py build` on `feat/a-bme280-environment-producer`, 0 errors and 0 warnings, `coldguard_firmware.bin` 268 864 bytes, SHA-256 `a4bd283f2fea9bc497e87dfe76fae2893ef85267d071005094929685aa1cbba0` |
| HARDWARE_VERIFIED | **no** | Never flashed, never read from a board. See §5 for the specific measurements still outstanding. |

Nothing in this document should be read as A-W02-06 being physically accepted.
`evidence/A/W02/acceptance.md` §4.1 remains the record of what the 2026-10-18 bench
session did and did not prove.

## 2. Field contract

| Field | Producer | Consumer | Unit | Validity semantics | Compatibility result | Owner |
|---|---|---|---|---|---|---|
| `t_ambient_c` | `bme_task` → `cg_bme280_sample` → `cg_snapshot_publish_env` → `cg_telemetry.c` | C (persist), B (feature, non-control) | degrees Celsius, 2 dp as emitted | paired with `t_ambient_status`; a value is present **only** when the status is `OK` | field already on the wire; C maps it to `environment.t_air` and stores `t_air_c` — **no Member C schema change required** | Member A emits, Member C maps |
| `t_ambient_status` | same | C, D | token | closed set: `OK`, `STALE`, `INVALID`, `NO_DATA`, `SENSOR_NOT_PRESENT` | no backend counterpart today; C's rule is `None` + quality, so the status must be folded into `quality.environment` | Member C decides the mapping |
| `relative_humidity_pct` | same | C, B | percent RH, 3 dp as emitted | paired with `relative_humidity_status`, same token set | maps to `environment.rh`, stored as `rh_pct` | Member A emits, Member C maps |
| `relative_humidity_status` | same | C, D | token | same closed set | no backend counterpart | Member C |
| `health_bme` | `cg_health_registry_beat(CG_PRODUCER_BME, …)` | D | token | liveness of the **task**, not of the silicon | unchanged | Member D |

The name mapping is `t_ambient_c → environment.t_air` and
`relative_humidity_pct → environment.rh`. Those backend names are not Member A's
choice: `backend/src/coldguard_backend/validation.py:61-62` requires the pair
`("environment", "t_air")` / `("environment", "rh")`,
`contracts.py:97-101` types both as `float | None`, and
`normalized_store.py:91-92,171-172` already declares and writes the columns
`t_air_c` and `rh_pct`. Member A reused the pre-existing serial fields instead of
inventing new ones, which is why this is a mapping task and not a schema change.

## 3. Validity rules a consumer must implement

1. **`nan` is not a number.** When a status is not `OK`, the paired value is the
   literal `nan` (`CG_INVALID_VALUE_TOKEN`). It must map to `None`, never to `0.0`
   and never to a carried-forward previous reading. A failed cycle deliberately
   publishes nothing, so the old value cannot silently look current.
2. **Absence and staleness are different facts.** `SENSOR_NOT_PRESENT` means the
   producer completed a cycle and no module acknowledged the bus — a declared
   configuration fact. `STALE` means a module was heard and has not been heard for
   longer than `CG_TELEM_STALE_ENV_MS` (4 × the 1000 ms producer period = 4000 ms).
   `NO_DATA` means the producer has not completed a cycle since boot at all.
   `INVALID` means the module answered but the reading was refused (identity not a
   BME280, calibration image not ready, saturated or out-of-range raw code).
3. **A relative humidity above 100 %RH is not corruption.** The Bosch fixed-point
   humidity path clamps at 102 400 (102.400 %RH) per the datasheet, and Member A
   refuses only outside that bound. Do not add a `0..100` CHECK on ingest; it would
   reject a value the reference algorithm can legitimately produce. Decide the
   physical-plausibility bound as a team if one is wanted.
4. **Ambient is not chamber air.** `t_ambient_c` is the module's own environment.
   The chamber-air quantity is `t_inside_c` only. Any rate, band or comfort check
   that must be about chamber air (`docs/01`, A-W17) must not read `t_ambient_c`,
   and must not read `t_hot_side_c` either.
5. **Ambient is not a control input.** No Member A control path consumes it; the
   TEC controller uses thermal and electrical observations only.

## 4. Health semantics, and the one thing that stays open

`CG_PRODUCER_BME` now receives a beat on every completed producer cycle, including a
cycle that concluded "no module is present". Consequence for Member D: a
`health_bme=LATE/NEVER` now means the **task** is not running, which is a real fault;
it no longer means "this board has no humidity sensor fitted". Before this change the
two were indistinguishable, and the aggregate `health` could therefore never read OK.

What did **not** change: while the ambient module is absent or unasked,
`environment_quality` stays `DEGRADED`. Splitting "definitively absent" from "not
asked yet" would give those two cases different names in a vocabulary that Members B
and C parse (`VALID/DEGRADED/INVALID/UNKNOWN`, see
`backend/src/coldguard_backend/contracts.py:144`). That is a cross-team contract
change, so Member A left the behaviour alone and is raising it instead:

> **TEAM DECISION OPEN (owner: Member C, affects B):** should `environment_quality`
> distinguish a known-absent module from a producer that has not completed its first
> cycle, or keep both as `DEGRADED`? Member A can implement either without a serial
> schema change; the device already carries `t_ambient_status=NO_DATA` separately from
> `SENSOR_NOT_PRESENT`, so the distinction is available in the field even while the
> collapsed quality name stays `DEGRADED`.

## 5. Physical measurements still required (Member A cannot close these)

1. **I²C address on the as-built wiring.** The transport probes `0x76` then `0x77`
   rather than asserting one. `evidence/A/W02/bme280/` records a real module answering
   `0x76` with chip id `0x60`, but that bench ran with **SCL on GPIO33**; the header was
   later re-soldered to **SCL GPIO34** (`evidence/A/as-built-pinmap-2026-10-27.md`). The
   evidenced address therefore does not yet prove anything about the current wiring.
   Needed: the flash log's `event=BME280_BUS … addr=0x…` line from the present board.
2. **Humidity trim unpacking against silicon.** The datasheet packs `dig_H4`/`dig_H5`
   as 12-bit signed nibbles across `0xE3`–`0xE5`. Member A implemented the datasheet
   form and proved it deterministically on the host, but no fitted module has confirmed
   the nibble pairing. Needed: one firmware reading compared with a known-good instrument.
3. **T/RH plausibility from the firmware path** — the 2026-10-18 numbers came from an
   Arduino/Adafruit sketch, not from this driver.
4. **Mounting position and self-heating** — whether the probe is heated by the
   ESP32/V1 in its final location. This is the half of A-W02-06 that has never been
   measured at all.

## 6. `hardware_config_id` is still not resolved — do not treat these as equal

Two identifiers are in use for what may be one thing, and **no provenance in the
repository links them**:

- `CG-HW-001` — emitted by the device on every telemetry frame and present as a column
  in real capture rows (`evidence/A/W04/boot-default-off.csv`).
- `HW-CONF-2026-10-27-ASBUILT-V2` — the as-built configuration record name
  (`evidence/A/as-built-pinmap-2026-10-27.md`).

Member A is not claiming these are equivalent. Until someone records the mapping — or
declares one authoritative and deprecates the other — any consumer that joins on
`hardware_config_id` across device frames and configuration records will silently
produce zero matches. The compatibility matrix keeps this row at
`ACCEPT (only after schema rewrite + name mapping)` for that reason, and the acceptance
census tool refuses a record whose `hardware_config_id` does not equal the frozen map.
**Owner: Member C for the stored identity, with the operator to confirm which label
describes the physical board.**
