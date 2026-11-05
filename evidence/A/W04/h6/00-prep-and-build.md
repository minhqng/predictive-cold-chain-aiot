# H6 — isolated bench firmware: preparation and build record

Session date: 2026-10-29
Status: **BUILD COMPLETE AND VERIFIED — FLASH NOT PERFORMED**
Reason: no USB device is present on the host (no COM port, no Espressif USB
device tree entry). Nothing has been written to the board in this session.
No git operation (commit, push, merge, reset, rebase) was performed.

Companion records in this directory:

| File | Content |
|---|---|
| `00-prep-and-build.md` | this document |
| `01-static-checks.txt` | reproducible static safety checks on the built image |
| `10-idf-build.log` | full ESP-IDF build log |
| `h6-image-hashes.txt` | SHA-256 of bootloader / partition table / app / elf |
| `h6-source-hashes.txt` | SHA-256 of every H6 source and tool file |

---

## 1. Scope conformance

The operator's revised scope (turn 5) and how the firmware satisfies it:

| Requirement | Implementation |
|---|---|
| Polarity by touch only, no thermal characterization | no temperature sensing anywhere; no DS18B20 driver linked |
| Remove DS18B20 as prerequisite | not referenced in code, CMake or checks |
| Use the previously verified 10 % PWM setting | 819/8192 = 9.9988 % duty (plan §3.4) |
| Up to 60 s ON, operator STOP any time | `H6_MAX_ON_US` = 60 000 000; `STOP` command trips synchronously |
| V1 fan runs continuously | fan is on its own fused branch, not firmware-controlled; firmware never touches it |
| Monitor PZEM V/I during operation | 1 Hz PZEM poll inside RUN, logged with state and elapsed ms |
| Manual authorization before TEC activation | `ARM` then `START`; every boot starts in `WAIT_FOR_MANUAL_ARM` |
| Automatic OFF at timeout, no restart | esp_timer one-shot + run-task deadline check; `run_consumed` latched forever |
| Touch small block after OFF | not a firmware action; execution script step (plan §9.10–11) |
| Never touch terminals / fan / hot heatsink | not a firmware action; operator instructions (plan §9) |
| Abort on abnormal current / fan / smoke / smell / wiring | current and bus-voltage window + 2 consecutive PZEM failures + immediate `STOP` |
| Do not modify W04 gates or invent limits | production files untouched; H6 limits are stated in plan §7 and explained below |
| Preserve previous evidence, no repeated G0/G1 | no hardware re-verification in this session |
| Isolated temporary firmware, TEC branch disconnected at flash | separate ESP-IDF project, flash blocked until operator connects the board with fuse out |
| No commit / push | none performed |

---

## 2. Project layout

Separate ESP-IDF project, independent of the production firmware:

```
firmware/h6-bench/
  CMakeLists.txt              project(coldguard_h6_bench)
  sdkconfig.defaults          console/size/watchdog defaults
  sdkconfig                   generated, effective config
  main/
    CMakeLists.txt
    h6_config.h               pins, PWM, timing, PZEM, plausibility window
    h6_state.h / h6_state.c   pure-C state machine (no ESP-IDF dependency)
    h6_selftest.h / .c        boot-time state-machine matrix
    h6_pzem.h / .c            read-only PZEM-017 Modbus client
    h6_main.c                 boot, GPIO/LEDC, PZEM, console, guard, run task
  tools/
    h6_serial.py              timestamped serial capture + command injection
```

The production tree (`firmware/main/`, `firmware/h6-bench` is a sibling) is
not modified and not linked. Static check 6 in `01-static-checks.txt` confirms
the only references to production modules are two explanatory comments.

---

## 3. Build provenance

| Item | Value |
|---|---|
| ESP-IDF | v6.1, `C:\Espressif\v6.1\esp-idf` |
| Target | `esp32s3` |
| Toolchain | `riscv32-esp-elf`/`xtensa-esp-elf` bundled with EIM install; esptool v5.6.0 |
| CMake / Ninja | 4.0.3 / bundled |
| Python | `C:\Espressif\tools\python\v6.1\venv` |
| Build directory | `C:/Users/dlbac/Downloads/coldguard-repo/_h6-build` (out of tree) |
| Command | `idf.py -B C:/Users/dlbac/Downloads/coldguard-repo/_h6-build build` |
| Result | success, 1082/1082 targets, exit 0 |
| Log | `10-idf-build.log` |

Host invocation note (reproducibility): ESP-IDF's `export.sh` refuses to run
under MSYS/MinGW on this host, so the build was executed from PowerShell with
`Env:MSYSTEM` removed and `$env:PYTHONUTF8='1'`, after dot-sourcing
`C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1`.

---

## 4. Image identity

| Artifact | Bytes | SHA-256 |
|---|---|---|
| `bootloader/bootloader.bin` | 19 008 (0x4A40) | `764792967f1a0910d20290c9c2a51611a7a6d3cb0441d2c175b4200d0f3ff10d` |
| `partition_table/partition-table.bin` | 3 072 | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` |
| `coldguard_h6_bench.bin` (app) | 244 544 (0x3BB40) | `573f9181a93029f4034058caf9118fa903f755c63518fcd103a35019fbc721e9` |
| `coldguard_h6_bench.elf` | 4 322 192 | `44d9b36d850a8fc1a8892f68964c1635919c147d06d186478636adf675425006` |

App partition usage: 0x3BB40 of 0x100000, 77 % free.
Bootloader usage: 0x4A40, 42 % free.

Source hashes are in `h6-source-hashes.txt`; any rebuild must be compared
against both files before flashing.

---

## 5. Effective configuration (`sdkconfig`)

Safety-relevant values actually compiled in:

```
CONFIG_ESPTOOLPY_FLASHSIZE="2MB"
CONFIG_PARTITION_TABLE_SINGLE_APP=y
CONFIG_PARTITION_TABLE_OFFSET=0x8000
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y
CONFIG_ESP_CONSOLE_SECONDARY_NONE=y
CONFIG_ESP_SYSTEM_PANIC_PRINT_REBOOT=y
CONFIG_ESP_TASK_WDT_TIMEOUT_S=10
```

Consequences:

- Console is the native USB-Serial/JTAG, primary only. The UART console is
  disabled, so GPIO 43/44 style UART0 pins are not used by the logger.
- Single-app partition table at 0x8000, app at 0x10000, 2 MB flash setting
  (the physical part is 4 MB, but the whole layout stays inside 2 MB).
- A panic reboots the chip. A reboot lands in `WAIT_FOR_MANUAL_ARM` with
  outputs off; `run_consumed` resets on reboot, so a reboot is itself an
  operator-visible reset of the one-run latch, not a way to keep drive on.

---

## 6. Static verification

Full output in `01-static-checks.txt`. Summary:

1. `h6_sm_start` is called exactly once in production code, in `cmd_start`
   (`h6_main.c:409`). All other call sites are `h6_selftest.c` local
   instances.
2. The only TEC enable helper, `outputs_on_10_percent`, is called exactly
   once (`h6_main.c:236`), inside the run task and inside the state lock.
3. `outputs_early_safe()` is the first statement of `app_main`
   (`h6_main.c:537`), before mutex, console or any peripheral.
4. No direct `gpio_set_level(..., 1)` on R_EN/L_EN outside the helper.
5. PZEM framing uses only read function code 0x04 (`h6_pzem.c:49`). There is
   no write-request builder; the `0x06` byte at `h6_pzem.c:53` is the
   register-count high byte of the read request.
6. Linked image contains the expected state names and the boot selftest
   result strings.

---

## 7. Runtime behavior (what the operator will see)

### 7.1 Boot

1. Control pins are driven to the OFF state before anything else.
2. Mutex, state machine, safe-off transition.
3. On-device selftest runs; `H6 SELFTEST result=PASS` or `FAIL`.
4. Boot banner and `H6 SAFE_OFF ... tec_output=OFF`.
5. LEDC and PZEM init, guard timer and run task created.
6. State becomes `WAIT_FOR_MANUAL_ARM`; USB-Serial/JTAG REPL starts.

A selftest FAIL, PWM init failure, guard-timer failure or run-task failure
leaves arming blocked for the whole boot (`arm_blocked=1`).

### 7.2 Commands

| Command | Accepted when | Effect |
|---|---|---|
| `ARM` | `WAIT_FOR_MANUAL_ARM` | state `ARMED`; no output change |
| `START` | `ARMED`, PWM ready, live PZEM valid, OFF current ≤ 0.2 A | one-shot guard timer, state `RUNNING_10_PERCENT`, run task enables 10 % |
| `STOP` | any state | if running: drive off synchronously, reason `OPERATOR_STOP` |
| `STATUS` | any state | prints state, reason, elapsed, pins, duty, PZEM live or last sample |
| `HELP` | any state | command list |

Malformed commands are rejected and logged. `START` is refused outside
`ARMED` and after the first accepted `START`.

### 7.3 RUN loop

- Enable sequence: duty 0 → short settle → R_EN high → L_EN high → 2 ms →
  duty 819 (any LEDC/GPIO error aborts to all-off).
- 20 ms loop: state check, deadline check.
- 1 Hz PZEM poll; each line logs elapsed ms and the full sample.
- Two consecutive invalid polls → `TELEMETRY_INVALID` trip.
- Valid sample outside −0.01…5.0 A or 6…16 V → `FAULT` trip.
- At 60 s (guard timer and run-task deadline independently) → drive off,
  reason `TIMEOUT`.
- Teardown: guard timer stopped, `H6 END ... start_rejected_until_reboot=1`.

### 7.4 Why these limits

- 5 A / 6–16 V are plausibility bounds for the recorded 12 V, ≈1 A
  operating point at 10 % duty, not new protection ratings.
- 0.2 A START precheck detects a branch already carrying current or a stuck
  driver contactor before PWM is applied.
- Both R_EN and L_EN are driven high during RUN, per plan §3.3, because the
  BTS7960 half-bridge pair needs both halves enabled to conduct. This is a
  deliberate, documented deviation from the production `(true,false)`
  request contract; production code is untouched.

---

## 8. Self-review findings fixed before the build

1. **STOP/enable race.** If `STOP` or the guard fired between the ARMED →
   RUNNING transition and the actual enable, `STOP` could return while the
   TEC was still driven. Fixed by holding `s_lock` across the whole enable
   sequence and re-checking the state under the lock (`h6_main.c:233–238`).
2. **Enable during a blocked poll.** The PZEM poll can block for up to
   ~0.5 s; a stop arriving during the poll is now detected immediately after
   the poll returns (`h6_main.c:289–298`) instead of waiting for the next
   loop iteration.
3. **Boot order.** The guard timer and run task are created before the state
   machine is allowed to become ready, and a selftest failure blocks arming;
   there is no window where `ARM` succeeds but the safety timers do not
   exist.

---

## 9. On-device selftest instead of a host test

Plan §5.2 originally called for a native host test. This host has no usable
native C toolchain: esp-clang targets ESP architectures only; there is no
gcc, no MSVC build tools, no WSL distribution and no zig. Rather than skip
the matrix, the same assertions were moved into `h6_selftest.c` and run at
boot on the shipped binary:

- happy path `SAFE_OFF → ARMED → RUNNING`;
- full transition matrix over all 7 states × 6 operations;
- second `START` rejected (one run per boot);
- first stop reason wins; stop from non-running states is a no-op;
- deadline boundary at start + 59 999 999 / 60 000 000 / 60 000 001 µs;
- elapsed-time semantics and state/reason name functions.

This tests the actual linked machine code. A FAIL is printed and blocks
arming; it does not silently continue.

---

## 10. Flash procedure (prepared, not executed)

Prerequisite, controlled by the operator: the 12 V PSU is OFF/disconnected,
the 15 A TEC fuse (slot 3) is removed, the TEC branch is disconnected for the
flash, and the board's USB-Serial/JTAG port is connected.

```powershell
# identity gate
python -m esptool --chip esp32s3 -p COMx chip-id
# require: MAC e0:72:a1:bc:cf:4c, ESP32-S3 rev v0.2, USB-Serial/JTAG

# authoritative restore source: whole 2 MB user flash, before writing
python -m esptool --chip esp32s3 -p COMx -b 460800 read-flash 0x0 0x200000 `
  evidence\A\W04\h6\w04-flash-backup.bin

# flash H6, explicit addresses, no full-chip erase
python -m esptool --chip esp32s3 -p COMx -b 460800 `
  --before default-reset --after hard-reset write-flash `
  --flash-mode dio --flash-freq 80m --flash-size 2MB `
  0x0 _h6-build\bootloader\bootloader.bin `
  0x8000 _h6-build\partition_table\partition-table.bin `
  0x10000 _h6-build\coldguard_h6_bench.bin
```

Post-flash acceptance, captured with
`python tools\h6_serial.py --port COMx --out <log> --control <file>
--seconds 30 --exit-on-end`:

- `H6 SELFTEST result=PASS`;
- `H6 SAFE_OFF ... tec_output=OFF`;
- `state=WAIT_FOR_MANUAL_ARM`;
- `pwm_duty=0`, `ren=0`, `len=0`, `rpwm_level=0`;
- PZEM init line and a plausible OFF-state sample (≈12 V, ≈0 A with PSU on;
  if the PSU is still off, a timeout status is expected and harmless).

Then the operator gate in plan §8 — no TEC power before it.

---

## 11. Restoration-source correction

Plan §11 previously named `_w04-g1-evidence/fw-build` as the restore image.
Verified during this session:

- its bootloader hash `b1aeaf74…` matches the recorded W04 provenance;
- its partition table hash matches;
- its app binary now hashes
  `39dd8332442fc45d394e70a41b7c7fac3bd16e2383a92f8f44cf085c4b15e299`,
  **not** the recorded flashed app hash `7cb2658374…`.

So that local rebuild is not provably bit-identical to what was flashed.
The authoritative restore source is therefore the read-back of the current
flash before H6 is written. After the read-back, the app region
(`skip 0x10000`, `count 244352`) is hashed and compared with `7cb2658374…`;
the result is recorded either way. Plan §5 and §11 were amended accordingly.

---

## 12. Current blocker and operator action

The only missing input is physical: **the ESP32-S3 USB-Serial/JTAG port is not
connected.** Evidence gathered this session:

- `[System.IO.Ports.SerialPort]::GetPortNames()` — empty;
- no present PnP device with `VID_303A` / `VID_1A86` / `VID_10C4`;
- no prior COM4 any more.

Required operator action, in this order:

1. PSU OFF and 12 V output disconnected.
2. 15 A TEC fuse removed (slot 3).
3. TEC branch disconnected for the flash.
4. Connect the board's USB-Serial/JTAG port.

After that, the identity gate, read-back backup, flash and SAFE_OFF capture
can proceed without further questions. The run then pauses at the plan §8
power gate; no TEC power is applied before an explicit operator PASS.

---

## 13. Explicit non-actions

- No flash, erase or write to the board (no port available).
- No TEC power, no fuse insertion, no PSU activation.
- No change to production firmware, W04 gates or hardware.
- No invented safety limits; the plausibility window is stated in plan §7.
- No git commit, push, merge, reset, rebase or stash.
- No deletion of prior evidence; new records are additive under
  `evidence/A/W04/h6/`.
