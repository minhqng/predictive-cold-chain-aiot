# H6 — TEC Hot/Cold Polarity Bench Test (plan v2)

Status: H6 ONE-SHOT RUN COMPLETE — awaiting operator touch observation.
Authorization was given and the single run executed: 60.000 s at duty 100
permille (819/8192), 60 valid 1 Hz samples (11.71 V, 0.96 A, 11.2 W), automatic
OFF via the guard timer, all outputs 0. No STOP, no fault, no retry. Polarity
result is pending the qualitative touch of the small aluminum block; W04
restore is held until that result is recorded. See `h6/41-h6-run-analysis.md`.
The earlier §8 gate passed (fuse in, PSU on); the first attempt was blocked by
PZEM `BAD_LENGTH`, the reader was corrected and reflashed (MAC
`e0:72:a1:bc:cf:4c`, read-back verified, SELFTEST 172/172), and five
consecutive live samples then passed (`h6/08-refix-flash-verification.md`,
`h6/09-pzem-gate-pass.md`).
See `evidence/A/W04/h6/05-pzem-root-cause.md` and `06-pzem-fix-and-build.md`.
Supersedes: H6 plan v1 (attachment `ColdGuard — H6: TEC Hot/Cold Polarity Bench Test`).
Session date: 2026-10-29. Worktree: `A-W04-tec-commissioning`, branch
`feat/a-w04-tec-commissioning-foundation`.

This document is the single source of truth for the H6 test. It records the
scope change, every hardware/firmware decision with its evidence basis, the
operator gate, the execution script and the result classes. Nothing here
authorizes TEC power: the branch stays fused-out (15 A fuse removed) until the
operator explicitly passes the gate in section 8.

---

## 0. Scope change from v1

| Item | v1 | v2 (this plan) |
|---|---|---|
| Objective | polarity by touch | unchanged |
| DS18B20 | required background logging | **removed as a prerequisite and as a data source** |
| TEC ON time | 60 s max | 60 s hard max, operator STOP any time (unchanged in substance) |
| PWM | "previously verified 10%" | 10% duty only; frequency reconstructed and disclosed (§3.2) |
| Fan | continuously ON | unchanged (independent fused branch, not firmware-controlled) |
| PZEM | V/I/P | unchanged, 1 Hz, abort on invalid telemetry |
| ARM | manual authorization | explicit `ARM` then `START`, one run per boot |
| Auto-OFF | at timeout | unchanged, plus an independent guard task |
| Touch check | after OFF | unchanged, PSU switched off first |
| W04 gates | unchanged | unchanged |
| Historic evidence | not repeated | not repeated |

Historical G0/G1/G2-A evidence is preserved and is not re-measured for H6.

---

## 1. Test objective (single)

Decide whether the TEC is installed with the correct hot/cold orientation:

- small external aluminum block = expected **COLD** side;
- large V1 aluminum heatsink + fan = expected **HOT** side.

The only measurement that classifies the result is a qualitative touch of the
small block after the TEC is off. This test does not characterize thermal
performance, maximum power, duty cycle capability or continuous-duty safety.

---

## 2. Verified hardware configuration (from G0/G1/G2-A evidence)

- MCU: ESP32-S3R2, MAC `e0:72:a1:bc:cf:4c`, 4 MB flash (configured 2 MB),
  USB-Serial/JTAG console. Serial port rediscovered before flashing; MAC must
  match before any write.
- TEC: TEC1-12715 SR in the V1 assembly, red/black leads on IBT-2 M+/M−.
- Driver: IBT-2 / HW-039 (2× BTS7960B + 74HC244). Logic VCC on ESP32 3V3.
  RPWM = GPIO5, R_EN = GPIO6, L_EN = GPIO10, LPWM tied to IBT-2 GND,
  R_IS/L_IS unused.
- Power: 12 V / 33.3 A PSU, four fused branches:
  1 = 5 A XL4015, 2 = 1 A PZEM, 3 = **15 A IBT-2 B+ (removed)**, 4 = 1 A V1 fan.
- TEC return through the 50 A / 75 mV PZEM shunt.
- PZEM-017 on UART1 (GPIO36 TX / GPIO37 RX through a 10k/10k/10k divider),
  9600 8N1, slave 1, 50 A profile verified.
- V1 fan runs from its own fused branch and is not firmware-controlled
  (PHY-TH-001). It must be observed ON by the operator.

Not re-measured: continuity, GPIO voltage, shunt isolation, relay/fuse
continuity, PZEM profile. They are unchanged since G0/G1.

---

## 3. PWM basis and disclosure

### 3.1 What is verified

- 10% duty is the only recorded attribute of the earlier successful TEC run
  (PZEM ≈ 0.98 A at 10%).
- The pin mapping, IBT-2 ON/OFF operation, and the independence of the fan
  were verified in G0/G1.
- Production W04 firmware contains **no** PWM implementation by design
  (`cg_tec_hw.c` refuses every non-zero duty); the earlier 10% bench run was
  not the production image. No local sketch or log records its PWM frequency.

### 3.2 Frequency: reconstructed, not verified

`H6_PWM_FREQ_HZ = 1000` — reconstructed from the ESP32 Arduino `analogWrite`
default. It is **not** recovered from recorded evidence and is labeled as a
reconstruction in the firmware (`H6_PWM_FREQ_RECONSTRUCTED 1`) and in this
plan. The operator is told this in the gate.

Why this is acceptable for H6: the polarity of a TEC is set by the net DC
direction of the average current, not by the chopping frequency. 1 kHz is
within the BTS7960's documented switching capability (docs/01 §12.2 cites
~25 kHz capability; the project's old plan baseline was 1–3 kHz) and is low
enough that no new driver strategy is introduced. The test does not use the
frequency as a performance result.

### 3.3 Enable sequencing: both halves enabled during RUN

The H6 runner drives `R_EN = 1` **and** `L_EN = 1` while `LPWM` is held low by
hardware (module wiring), then applies 10% duty on `RPWM`.

Evidence basis: a BTS7960 half-bridge conducts only when its own EN is high.
With `L_EN = 0`, the left half is high-impedance, the H-bridge has no return
path, and the PZEM would read ≈ 0 A. The recorded ≈ 0.98 A at 10% on 12 V
across a TEC1-12715 (~1.2 Ω) is only physically consistent with both halves
enabled. That makes "both EN high" the verified configuration in substance,
even though the production controller's abstract contract only ever requests
`(R_EN=true, L_EN=false)` (a path that is compiled out and never exercised).

Consequences recorded honestly:

- The H6 runner does **not** reuse the production controller's enable
  contract; it uses the physically verified IBT-2 forward configuration.
- It never drives LPWM, never reverses direction, never ramps.
- Production `cg_tec_hw.c` is not modified.

### 3.4 Duty

- LEDC timer: 1 kHz, 13-bit resolution (`8192` steps).
- Duty count `819` → 819/8192 = 9.9988% (0.0012 pp below the 10% nominal).
- Duty is set to 0 before enable and first thing on every exit path.

---

## 4. Firmware: isolated H6 bench target

Location: `firmware/h6-bench/` — a separate ESP-IDF project. It is not part
of the production `firmware/CMakeLists.txt` build. No production file is
modified.

### 4.1 State machine

```
BOOT -> SAFE_OFF -> WAIT_FOR_MANUAL_ARM -> ARMED -> RUNNING_10_PERCENT
                                                      |
                                                      v
                                              SAFE_OFF_FINAL -> COMPLETE
```

Rules enforced in code:

- `BOOT -> SAFE_OFF` runs before the UART/PZEM/console are initialized:
  GPIO5/6/10 are configured as outputs and driven low with internal pull-down
  enabled at the top of `app_main`.
- `SAFE_OFF -> WAIT_FOR_MANUAL_ARM` only after the safe state is latched.
- TEC is never enabled by boot, USB attach, reset, watchdog restart, or any
  automatic path. Only `START` while `ARMED` can enable it.
- `ARM` is accepted only in `WAIT_FOR_MANUAL_ARM`; `START` only in `ARMED`;
  `STOP` only in `RUNNING_10_PERCENT`. Every other command/transition is
  rejected with a printed reason and leaves the state unchanged.
- One run per boot: after `SAFE_OFF_FINAL`/`COMPLETE`, `START` is rejected
  until a power cycle. No automatic retry.
- The transition function is a pure C module (`h6_state.c`) so the host test
  can exhaust the transition matrix.

### 4.2 Independent bounded execution

- `run_task` owns the 60 s window: deadline = `esp_timer_get_time()` at START
  + 60 000 000 µs, monotonic, never extended by any input.
- `guard_task` (higher priority than `run_task`, no UART access) waits on the
  RUNNING notification, sleeps until the same absolute deadline, and calls the
  forced-off path unconditionally. Even if `run_task` is blocked or stuck, the
  guard removes drive at the deadline.
- `STOP` only sets a stop flag; it can shorten the window, never lengthen it.
- This is software protection only. A hard reset or CPU lock-up can leave the
  LEDC/GPIO state as-is until the operator cuts power; the PSU switch is the
  real shutdown authority. No hardware-level shutdown is claimed.

### 4.3 Output sequence

Enable:

1. duty = 0 (LEDC attached, output low);
2. `R_EN = 1`, `L_EN = 1`;
3. duty = 819 (10%).

Disable (timeout, STOP, telemetry fault, any fault, final):

1. duty = 0;
2. `R_EN = 0`;
3. `L_EN = 0`;
4. log the final state and reason.

### 4.4 PZEM telemetry

- Same transport as the validated production driver: UART1 9600 8N1, slave 1,
  FC04, registers 0x0000..0x0005, 8-byte request, 17-byte response,
  CRC16/MODBUS, 250 ms timeout, 2 attempts, 1 s poll, 32-byte RX cap.
- Read-only. No write function code exists in the image.
- One PZEM poll before START must succeed; otherwise START is refused.
- During RUN, two consecutive failed polls abort the run (telemetry invalid).
- Log line per second (console, 115200):
  `H6 ts_ms state duty_permille elapsed_ms vbus_mv current_ma power_mw pzem_valid stop_reason`.

### 4.5 Commands

`ARM`, `START`, `STOP`, `STATUS`, `HELP` (uppercase). Anything else is
rejected and does not change state. Every accepted/rejected command is echoed
with the resulting state.

### 4.6 Explicitly not included

- No DS18B20, no one-wire bus, no fan control, no reverse PWM, no PWM ramp,
  no duty change, no persistent configuration, no NVS writes, no OTA.
- No changes to `coldguard_config.h`, `cg_actuator.c`, `cg_tec_control.c`,
  `cg_tec_hw.c` or any production source.
- No modification of the six unresolved commissioning limits.

---

## 5. Build and preliminary checks (computer-side, no TEC power)

1. Preserve the existing dirty worktree; no reset/clean/stash.
2. Write the isolated project; run the state-machine matrix (transition table,
   timeout boundary at 59 999 999 / 60 000 000 µs, one-run latch, rejection
   cases). This host has no native C toolchain (checked: no gcc/clang/MSVC,
   no WSL), so the matrix runs **on the shipped binary at boot**
   (`h6_selftest.c`, PASS/FAIL printed), which tests the actual machine code;
   a FAIL blocks `ARM` for the whole boot.
3. Static checks on the image source: no write FC (0x06/0x10), no `arm` path
   that can run without a command, GPIO init before any peripheral.
4. `idf.py set-target esp32s3 && idf.py build` with ESP-IDF v6.1.
5. Record SHA-256 of bootloader/partition/app and the sdkconfig safety lines.
6. Confirm the image cannot auto-start: boot log must show `SAFE_OFF` then
   `WAIT_FOR_MANUAL_ARM` with duty 0 and no enable write.
7. Rediscover the port, read chip identity, require MAC `e0:72:a1:bc:cf:4c`.
8. With the TEC branch fuse-out, read back the **whole physical flash** (4 MB
   on this part; a 2 MB read-back is not a full backup) to
   `evidence/A/W04/h6/w04-flash-backup.bin` before writing anything. This
   dump is the authoritative restore source (the local rebuild under
   `_w04-g1-evidence/fw-build` no longer matches the recorded app hash; see
   §11.3). Hash the dump and hash its app region
   (`skip 0x10000`, `count 244352`); record both.
9. Flash with explicit addresses (0x0 / 0x8000 / 0x10000), no full-chip
   erase.
10. Capture the post-flash boot log and confirm `SAFE_OFF`,
    `WAIT_FOR_MANUAL_ARM`, `pwm_duty=0`.

Stop after step 10 and request the operator gate.

### 5a. Rebuild after the PZEM precheck block (2026-10-29)

The gate in §8 was passed (fuse in, PSU on) but the live PZEM sample was
`BAD_LENGTH`, so `START` was refused and no run occurred. Root cause, from the
preserved W03 bench firmware and logs: this TTL485 module echoes the 8-byte
request onto RX and the module's reply completes ~72–92 ms later, while the H6
reader ended each attempt after 10 ms of line idle — i.e. right after the
echo. The successful 600/600 bench run read with an 800 ms window and
explicitly ignored the 8-byte echo.

The H6 reader was corrected (accumulate until a CRC-valid reply or the 250 ms
window; scan the whole buffer; never stop on idle) and now logs raw TX/RX hex,
chunk timing, parsed header, CRC status and a class per attempt. Request
bytes, transport parameters, PWM, ON bound, ARM/START gating and every W04 gate
are unchanged. Evidence: `h6/05-pzem-root-cause.md`,
`h6/06-pzem-fix-and-build.md`, `h6/07-static-checks.txt`.

Rebuild requires the same isolation as §8: PSU off and disconnected, 15 A fuse
out. The existing 4 MB pre-flash backup is authoritative and is not rewritten.

Corrected image flashed 2026-10-29 22:31 with that isolation in place: app
`963f3cd623b8c8fade910adda723c0f178e7bc303528b63ed6520fd12110858d` at 0x10000,
read back byte-identical, `SELFTEST result=PASS checks=172 failures=0`,
`SAFE_OFF`, `WAIT_FOR_MANUAL_ARM`, duty 0, no output or reboot in 60 s. With the
PSU off the PZEM correctly reports `class=NO_RESPONSE` / `pzem=TIMEOUT` (the
TTL485 module is unpowered, so there is not even an echo). Details:
`h6/08-refix-flash-verification.md`.

---

## 6. Telemetry captured during the physical test

Per second while RUNNING, and at every state change:

- timestamp (device ms since boot) and host-side UTC time;
- test state;
- commanded duty (permille);
- elapsed ON time (ms);
- PZEM voltage (V), current (A), power (W) when the module provides it;
- PZEM validity and status token (`OK`, `TIMEOUT`, `CRC_ERR`, …);
- stop reason (`TIMEOUT`, `OPERATOR_STOP`, `TELEMETRY_INVALID`, `FAULT`);
- final actuator confirmation (`STATE=SAFE_OFF_FINAL duty=0 ren=0 len=0`).

The earlier ≈ 0.98 A is an averaged bench observation, not a peak-current
limit.

---

## 7. Abort conditions (any one ends the run immediately)

- operator `STOP` command, or operator requests abort verbally before START;
- any PZEM poll failure twice in a row, or no valid sample at START;
- PZEM current or voltage implausible (negative, or current > 5 A at 10%);
- any state-machine inconsistency or unexpected command;
- observed smoke, smell, unusual noise, fan stopped, visibly compromised
  wiring, or anything the operator judges abnormal;
- 60 s elapsed (hard timeout).

On abort: outputs off, reason logged, state `SAFE_OFF_FINAL`, no retry.

---

## 8. Mandatory human power gate (pause point)

The test does not proceed until the operator confirms **all** of:

1. PSU is OFF and its 12 V output is disconnected before the fuse is inserted.
2. The 15 A fuse is in the intended TEC branch (slot 3), inserted only while
   unpowered.
3. Power wiring, shunt terminals and clamps are secure.
4. TEC and V1 heatsink remain mechanically clamped; nothing has been
   disassembled since G0/G1.
5. After PSU ON, the V1 fan is visibly running.
6. The small aluminum block is reachable for a brief touch without touching
   terminals, fan blades, or the hot-side heatsink.
7. The PSU can be switched off immediately (switch reachable).
8. No smell, heat, noise, smoke or exposed conductor is present.
9. The operator has read the frequency disclosure (§3.2) and the enable
   disclosure (§3.3) and accepts the test as a qualitative polarity check.

No new continuity/GPIO measurements are required. The operator must not open
the PSU enclosure or rewire anything while powered.

Gate outcome is recorded as PASS/BLOCKED. Any doubt = BLOCKED.

---

## 9. Execution script (after gate PASS)

1. Confirm serial console is attached and state is `WAIT_FOR_MANUAL_ARM`.
2. Confirm PZEM returns valid samples (voltage ≈ 12 V, current ≈ 0 A with TEC
   off and PSU on). Record OFF-state values.
3. Operator confirms the V1 fan is running.
4. Send `ARM`; expect `ARMED`.
5. Send `START`; runner enables and applies 10% within one second. Record the
   host time of START.
6. Log V/I/P and elapsed each second. Watch for the abort conditions.
7. `STOP` at operator request, or automatic OFF at 60 s.
8. Confirm `SAFE_OFF_FINAL`, duty 0, R_EN 0, L_EN 0. Confirm state is
   `COMPLETE`.
9. Operator confirms TEC is off (fan may keep running).
10. **Operator switches the PSU OFF** before touching anything.
11. Operator briefly touches the accessible small block and reports
    COLDER / WARMER / NO NOTICEABLE CHANGE.

Touch rules: only the accessible small block surface; never bare live
terminals, never fan blades, never the hot-side heatsink, never a surface that
feels dangerously hot. If it feels unexpectedly hot, withdraw immediately.

---

## 10. Result classification

- **H6_POLARITY_CORRECT** — block perceptibly colder, no abnormal electrical
  behavior, automatic OFF within 60 s.
- **H6_POLARITY_REVERSED_SUSPECTED** — block perceptibly warmer; no rewiring
  until investigated.
- **H6_INCONCLUSIVE** — no noticeable change or insufficient evidence.
- **H6_FAIL** — control malfunction, uncontrolled ON, unexpected power
  behavior, or failure to switch OFF.
- **H6_BLOCKED** — gate failed, firmware not verified, or test not executable.

Current detected alone is never a PASS. This result says nothing about
high-power or continuous operation.

---

## 11. Restoration

1. Confirm TEC off; state `COMPLETE`.
2. PSU OFF and disconnected; remove the 15 A TEC fuse from slot 3.
3. Restore W04 from the pre-flash dump `w04-flash-backup.bin` (write it back
   to 0x0 at 2 MB, then verify the app region hash against
   `7cb26583743a4a9d246eb6f87f45940623bb52d4ceab672157dd49a9d5e9c6df`).
   Fallback only if the dump is unusable: rebuild `_w04-g1-evidence/fw-build`
   and record its actual hash — that local copy currently hashes
   `39dd8332…`, not the recorded app hash, so it must not be presented as a
   bit-identical restore. All production gates must remain `0`.
4. Confirm W04 boots to `SAFE_OFF` with `output_stage=DISABLED`.
5. Keep the H6 image, its source tree and all logs in `evidence/A/W04/h6/`.
6. If W04 restoration fails, state which image is installed and require the
   15 A fuse to stay out.
7. No commit, push or merge at any point.

---

## 12. Final report contents

A. Firmware basis and the 10% PWM reconstruction.
B. H6 image changes and independent review findings.
C. Build/flash results and hashes.
D. Operator gate confirmations.
E. Actual TEC ON time.
F. PZEM V/I/P series and validity.
G. Automatic OFF evidence.
H. Touch observation.
I. Verdict.
J. W04 restoration status.
K. Exactly one recommended next step.
