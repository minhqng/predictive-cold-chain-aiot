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

Requires Python 3.11+ with `pyserial` and Tk (the `py` launcher in this
workspace has both). No other third-party package is used.

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
