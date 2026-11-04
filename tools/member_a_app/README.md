# ColdGuard Member A hardware acceptance application

A Windows desktop application that connects to the ESP32-S3 console, shows live
telemetry and executes, records and verifies the 114 canonical Member A
requirements (`A-W01-01` .. `A-W24-04`).

## Launch

```text
py -3 tools\member_a_app\app.py
```

Registry-only check (no GUI, no serial):

```text
py -3 tools\member_a_app\app.py --check
```

Real-hardware readiness commands:

```text
py -3 tools\member_a_app\app.py --compat
py -3 tools\member_a_app\app.py --compat --port COM4
py -3 tools\member_a_app\app.py --capture-h8 --port COM4 --seconds 30
py -3 tools\member_a_app\app.py --import-evidence --session <session-dir>
```

Requires Python 3.11+ with `pyserial` and Tk (the `py` launcher in this
workspace has both). No other third-party package is used.

## Hardware compatibility

| Image | Read-only telemetry | Canonical W06 tests | Supervised TEC |
|---|---|---|---|
| H8 bench (`#CG H8S`) | Yes | INCOMPLETE | Stage F probe only (30 s, 20 %) |
| Canonical W06 (`#CG TELEM`) | Yes | Supported; output stage DISABLED | Refused unless a reviewed stage-enabled image is flashed |

The H8 bench profile is on the **Bench readiness** tab. It supports a
read-only 60 s capture (no writes) and a supervised Stage F probe that uses
the H8 grammar: `SUPERVISE`, `STAGE F`, `FAN`, `DOOR`, `ARM`, `START`,
`ACK`, `STOP`. The H8 firmware's own gates, host ACK watchdog, limits and
fault latch remain authoritative. The app never uses the H8 A-E endurance
stages for acceptance and never reports an H8 bench result as canonical W06
PASS. If Stage F is not approved in the installed image, START is refused
and the result is INCOMPLETE with the refusal token.

Canonical W06 tests are INCOMPLETE on an H8 image with an explicit reason;
they are not failed or fabricated. Documentary and operator-measured tests
(BOM, photos, documents, meter readings) remain available on either image.

## Firmware readiness result

**Installed H8 `build-t2-hot-side` image.** The build defines
`H8_ENDURANCE_STAGES_APPROVED=1`, `H8_LIMITS_OPERATOR_APPROVED=1`,
`H8_OFF_CURRENT_GATE_APPROVED=1` and `H8_SUPERVISED_BENCH=1`, but it does
**not** define `H8_STAGE_F_GUARD_APPROVED=1`. The Stage F thresholds are
still PROVISIONAL/PENDING in
`evidence/A/W04/h8/phase4e/H8_STAGE_F_FINAL_REVIEW.md`. The app therefore
offers the Stage F flow, but the firmware is expected to refuse START with
`START_STAGE_F_GUARD_UNAPPROVED`; that is recorded as INCOMPLETE, never as
PASS. The A-E endurance stages are approved in that image but are 100 %
endurance stages and are deliberately not used by the acceptance app.

**Canonical W06 shipped image.** `CG_TEC_OUTPUT_STAGE_ENABLED=0`,
`CG_TEC_HARDWARE_GATES_VERIFIED=0` and `CG_ACTUATOR_ENABLE_ALLOWED=0`; the
as-built adapter refuses every energization request, and the local
`CMDTEST` source is refused before the idempotency/expiry logic. Accepted
canonical commands need Member C's network transport; enabling the W06
output stage needs a new reviewed hardware adapter, not a build-only tweak.
The app reports those requirements INCOMPLETE with the exact reason.

No firmware was changed, no image was flashed and no TEC branch was
energized in this readiness pass. Stage F approval, building a
Stage-F-approved image, flashing and energization remain separate operator
authorizations.


## Existing W01-W04 evidence

**Tools -> Import existing W01-W04 evidence** (or `--import-evidence`) reads
only the authoritative corpora:

- `A-W01-hardware-audit/evidence/A/W01`
- `A-W02-sensor-foundation/evidence/A/W02`
- `A-W03-power-pzem-logic/evidence/A/W03`
- `A-W04-tec-commissioning/evidence/A/W04`
- `A-W04-delivery/evidence/A/W04`

The truncated root `evidence/` copy is never used. Files are copied into the
session `imports/` folder with SHA-256 provenance and attached when their
requirement runs. Import never marks a requirement PASS; the operator still
confirms the checklist and any live measurement.


## First hardware session

1. Connect the ESP32 USB console and note the COM port.
2. Launch the app, choose the operator name, and click **Connect**.
3. Confirm the identity bar shows `device_id`, `boot_id`, `firmware_version`,
   `hardware_config_id CG-HW-001` and the frozen ROM map.
4. Start with W01-W03 documentary and read-only tests.
5. Powered tests require an explicit batch opt-in, supervised prechecks, the
   boot `ARM` token and `START`; the app never energizes the TEC by itself.

Sessions are stored under `evidence/A/app-sessions/session-<UTC>/`. The
**Session** menu reopens an existing folder and resumes it. **Export 114-ID
report** writes Markdown, CSV and JSON plus the session digest and attachment
hashes.

## Safety model

- The app opens the port read-only; DTR/RTS are de-asserted immediately.
- `ARM`, `START`, `STOP`, `ESTOP` are the only manual actuation controls.
- `START` is disabled when the firmware reports `output_stage=DISABLED`.
- Closing the USB-Serial/JTAG port may reset the board; the GUI warns.
- No reset button is assumed. Warm reset pulses USB-JTAG reset lines; cold boot
  is a guided USB cable removal. The 12 V PSU and TEC branch are never switched
  by the app.
- A simulated device (`FakeDeviceLink`) can exercise logic but a hardware-measurement
  test can never record PASS from simulated telemetry. Documentary and
  operator-attested results keep their explicit source in the report.

## Coverage

All 114 canonical IDs are registered with a title, canonical criterion,
hardware/firmware prerequisites, actions, checks and evidence. `--check`
fails if an ID is missing, duplicated, has no handler, or has no checks.

Tests that need a stage-enabled firmware, a network command transport,
Controller B/D decisions, or a duty-setting console path report INCOMPLETE with
the exact reason rather than a fabricated PASS. A-W06-06 is INCOMPLETE until an
accepted command state exists; the local console source is refused before the
idempotency store.

## Tests

```text
py -3 -m unittest discover -s tools\member_a_app\tests -v
```
