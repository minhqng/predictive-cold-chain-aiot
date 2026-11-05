# W04 Flash + G1 Hardware Test — Evidence Summary

Session: 2026-10-29 (UTC 10:59–11:10). All raw files are in this directory.

## A. Source / build identity
- Worktree: `C:\Users\dlbac\Downloads\coldguard-repo\A-W04-tec-commissioning`
- Branch: `feat/a-w04-tec-commissioning-foundation`, HEAD `0d350a57874d53f9b48bfd6b639eae0f50e6f450`
- Dirty state preserved: 7 modified + 25 untracked (32 entries, unchanged before/after session)
- Source hashes: `01-source-hashes.txt`; git identity: `00-git-identity.txt`
- ESP-IDF v6.1 (EIM install, `C:\Espressif\v6.1\esp-idf`), target `esp32s3`
- Build dir (scratch, byte-identical source): `_w04-g1-evidence/fw-build/firmware/build`
- App: 244,352 bytes (0x3BA80), partition 0x10000/0x100000 (77% free)
- `coldguard_firmware.bin` SHA-256 `7cb26583743a4a9d246eb6f87f45940623bb52d4ceab672157dd49a9d5e9c6df`
- sdkconfig: UART0 primary console + USB-Serial-JTAG secondary (default), 2MB flash layout,
  TWDT 5 s, INT WDT 300 ms, single-app partition table (`23-build-provenance.txt`)

## B. Safety gates
- Operator confirmed physical prep (PSU OFF/disconnected, 15 A fuse slot 3 removed, shunt/GND untouched)
  before any reset/flash.
- Compile-time: `CG_ACTUATOR_ENABLE_ALLOWED 0`, `CG_TEC_OUTPUT_STAGE_ENABLED 0`,
  `CG_TEC_HARDWARE_GATES_VERIFIED 0`, `CG_TEC_REQUEST_DUTY_PERMILLE 0`; all limits UNRESOLVED.
- Runtime: `cg_safety_force_actuator_off()` first action in `app_main`; `cg_tec_hw` refuses enables/duty.
- Only GPIO writes to 5/6/10 are `gpio_set_level(...,0)` (cg_actuator.c:30-32).
- No erase-flash, no source edits, no git mutation, no commands sent to the device console.

## C. Software verification (all re-run this session)
- Host suite: 179 tests OK — exit 0 (`10-unittest-verbose.log`)
- State-machine harness: 34/34 scenarios PASS (asserted by test, exit 0)
- Negative safety tests: 11 tests OK (`12-negative-tests.log`)
- `run_all_checks_w04.py`: 6/6 PASS — exit 0 (`11-static-checks.log`)
- `idf.py set-target esp32s3` exit 0; `idf.py build` exit 0 (`22-idf-build.log`)

## D. Flash
- Target: ESP32-S3 rev v0.2, MAC `e0:72:a1:bc:cf:4c`, 4 MB flash, USB-Serial/JTAG on COM4
- Matches prior primary-MCU record (`evidence/A/W02/espidf-run/flash-provenance.md`)
- `write-flash @flash_args` (bootloader 0x0, partition 0x8000, app 0x10000): exit 0,
  3/3 regions "Hash of data verified" (`32-flash.log`). No full-chip erase.

## E. G1 results (raw logs)
- G1-01 Boot: PASS (`40-g1-boot-60s.log`) — `#CG SAFETY actuator=OFF`, `#CG BOOT boot_count=13`,
  ROMs 4/4 present, `#CG TEC event=BOOT result=LIMITS_UNRESOLVED state=OFF`. No panic/Guru.
- G1-02 Default OFF: PASS (software-reported) — all 62 TELEM lines: `pwm_duty=0`,
  `output_stage=DISABLED`, `tec_state=OFF`, `fan_command=OFF`, `fault_code=0x00000000`.
  No enable/PWM request logged. NOT a pin-voltage measurement.
- G1-03 Telemetry: PASS (`42-builder.log`: "TELEMETRY ACQUISITION: CLEAN", 62/62 rows) —
  TELEM 62 samples / 61.078 s; SAMPLE 61 samples, 60/60 deltas 990–1000 ms; T1/T2/T3 ~29.4–30.1 °C.
  PZEM 63/64 TIMEOUT — expected; PSU 12 V is OFF, so no sensor power/PZEM data.
- G1-04 Reset: PASS (`41-g1-reset.log`) — one controlled USB-JTAG reset, `rst:0x15
  (USB_UART_CHIP_RESET), boot:0x8`, boot_count 14→15, both boots SAFE_OFF, 10/10 TELEM safe.
- G1-05 Safety guards: PASS — host-side negative/authorization tests only; no hardware START/ON/PWM.

## F. Defect found on real hardware (fixed in session 2, section H)
`cg_commission.c:245` calls `esp_task_wdt_add(NULL)` from `app_main` (main task). `app_main`
returns, the main task is deleted, but stays subscribed. `commission_task` then calls
`esp_task_wdt_reset()` (cg_commission.c:199) and is not subscribed, producing
`esp_task_wdt_reset(707): task not found` ~10 Hz (568 lines/61 s) and
`Task watchdog got triggered ... main (CPU 0)` every 5 s (12 events/61 s).
No reset/panic (TWDT panic is off). Actuator safety is unaffected. Raw: `40-g1-boot-60s.log`.

## G. Limitations
- No DMM/oscilloscope measurement of GPIO5/6/10; OFF state is firmware-reported only.
- CH343G was not enumerated; the session used the native USB-Serial-JTAG (same MCU MAC),
  so docs/06 item U12 (console via CH343G) remains unverified.
- G0 electrical continuity/shunt/fuse inspection was not performed or re-verified here.
- IBT-2 input topology/back-power behaviour not measured; mitigated by fuse removal + PSU OFF.

## H. Session 2 (2026-10-29, TWDT lifecycle fix + G1 re-run)

### Patch
- `firmware/main/cg_commission.c` (untracked W04 file):
  - `commission_task` subscribes itself (`esp_task_wdt_add(NULL)`) as its first action; on
    failure logs `commission=TASK_WDT_ADD_FAIL` and skips resets (`wdt_subscribed` local).
  - `esp_task_wdt_reset()` now runs only when subscribed and its error is logged
    (`commission=TASK_WDT_RESET_FAIL`).
  - `cg_commission_start` no longer subscribes the `main` task.
  - Task never exits (`for(;;)`), so no unsubscribe/delete path is needed.
  - TWDT stays enabled at 5 s, idle-task checks unchanged, warnings not suppressed.
- `firmware/tools/cg_check_firmware_w04.py`: enforces add/reset in `commission_task` and
  absence of `esp_task_wdt_add` in `cg_commission_start`.
- `firmware/tools/tests/test_cg_check_firmware_w04.py`: 2 new negative tests
  (subscription removed from task; subscription reintroduced in start context).

### Verification (real exits)
- Host suite: 181 tests OK, exit 0 (`50-unittest-verbose.log`)
- State machine + actuator safety: 11 tests OK, 34/34 scenarios, exit 0 (`52-negative-tests.log`)
- `run_all_checks_w04.py`: 6/6 PASS, exit 0 (`51-static-checks.log`)
- `idf.py build` esp32s3: exit 0, no warnings/errors (`53-idf-build.log`)
- Build tree `firmware/main` byte-identical to worktree (`diff -r` empty; cg_commission.c sha256
  `0c22ebc3…` both sides)

### Flash
- Operator re-confirmed the physical safety configuration before flashing.
- MAC `e0:72:a1:bc:cf:4c` re-read from COM4 (USB-Serial/JTAG VID_303A PID_1001) — same MCU.
- images: app SHA-256 `39dd8332442fc45d394e70a41b7c7fac3bd16e2383a92f8f44cf085c4b15e299`
  (244,448 B), bootloader `b1aeaf74…`, partition table `7f00b6c0…`
- write-flash 0x0/0x8000/0x10000, no erase: 3/3 "Hash of data verified" (`60-flash.log`),
  re-run with captured exit code `FLASH_EXIT=0`, 3 writes / 3 verified (`60b-flash-exitcode.log`)
- independent readback `verify-flash 0x10000`: "Verification successful (digest matched)"

### G1 re-run
- 60 s boot capture (`61-g1-boot60.log`): `rst:0x15 (USB_UART_CHIP_RESET), boot:0x8`,
  `#CG BOOT boot_count=18`, `#CG TEC event=WDT result=SUBSCRIBED task=cg_commission timeout_s=5`
  - "task not found": 0; "Task watchdog": 0; `TASK_WDT_RESET_FAIL`: 0; panic/Guru/backtrace: 0
  - TELEM 62 frames / 61.3 s (first 230 ms, last 61,307 ms) ≈ 1 Hz
  - 62/62: `tec_state=OFF`, `pwm_duty=0`, `output_stage=DISABLED`, `fan_command=OFF`
  - six TEC_LIMIT lines UNRESOLVED; `PZEM` 64 lines (expected with PSU off)
- Controlled reset (`62-g1-reset.log`): boot_count 19→20, both boots `rst:0x15`, WDT SUBSCRIBED
  on both, 12/12 TELEM safe; `cg_verify_reboots.py` → REBOOT IDENTITY: PASS (2 boots,
  roles T1/T2/T3 stable)
- No console commands sent; no START/ON/PWM; gates and limits unchanged; no git mutation.
