# H6 post-flash verification

Session date: 2026-10-29
Status: **H6 IMAGE FLASHED AND VERIFIED — AWAITING POWER GATE**
No `ARM`, no `START`, no TEC power, 15 A fuse still removed, PSU still off.

## 1. Flash

Command (no chip erase, explicit offsets, TEC branch fuse-out):

```
esptool --chip esp32s3 -p COM4 -b 460800 --before default-reset --after hard-reset \
  write-flash --flash-mode dio --flash-freq 80m --flash-size 2MB \
  0x0     _h6-build/bootloader/bootloader.bin \
  0x8000  _h6-build/partition_table/partition-table.bin \
  0x10000 _h6-build/coldguard_h6_bench.bin
```

Result (`10-flash-h6.log`):

| Offset | Image | Bytes | esptool check |
|---|---|---|---|
| 0x0 | bootloader | 19 008 | Hash of data verified |
| 0x8000 | partition table | 3 072 | Hash of data verified |
| 0x10000 | app | 244 544 | Hash of data verified |

Sector erases were limited to the image ranges (0x0–0x5FFF, 0x8000–0x8FFF,
0x10000–0x4BFFF). The NVS partition at 0x9000 was not touched.

## 2. Independent read-back

Read 0x0–0x4C000 after flashing (`11-h6-readback.bin`) and compared with the
build artifacts byte for byte:

| Region | SHA-256 | Bytes vs build file |
|---|---|---|
| bootloader 0x0, 19 008 | `764792967f1a0910d20290c9c2a51611a7a6d3cb0441d2c175b4200d0f3ff10d` | 0 differing |
| partition table 0x8000, 3 072 | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` | 0 differing |
| app 0x10000, 244 544 | `573f9181a93029f4034058caf9118fa903f755c63518fcd103a35019fbc721e9` | 0 differing |

The flashed device content is exactly the verified H6 build.

## 3. Boot log (real capture, `20-boot-after-flash.log`)

Captured with `idf_monitor` from chip reset, not a simulated or reconstructed
log. Relevant lines:

```
ESP-ROM:esp32s3-20210327
rst:0x15 (USB_UART_CHIP_RESET),boot:0x8 (SPI_FAST_FLASH_BOOT)
W (91) spi_flash: Detected size(4096k) larger than the size in the binary image header(2048k). Using the size in the binary image header.
H6 SELFTEST result=PASS checks=138 failures=0

H6 BOOT firmware=coldguard_h6_bench build=Oct 29 2026 21:56:41 pins_rpwm=5 pins_ren=6 pins_len=10 pwm_freq_hz=1000 freq_reconstructed=1 duty_permille=100 max_on_ms=60000 pzem_uart=1
H6 SAFE_OFF duty_permille=0 ren=0 len=0 rpwm_level=0 tec_output=OFF
W (96) ledc: GPIO 5 is not usable, maybe conflict with others
H6 PZEM init=OK uart=1 tx=36 rx=37 baud=9600 slave=1
H6 READY state=WAIT_FOR_MANUAL_ARM tec_output=OFF waiting_for=ARM
```

Verification against the required list:

| Requirement | Observed | Verdict |
|---|---|---|
| SELFTEST PASS | `checks=138 failures=0` | PASS |
| SAFE_OFF | `duty_permille=0 ren=0 len=0 rpwm_level=0 tec_output=OFF` | PASS |
| WAIT_FOR_MANUAL_ARM | `state=WAIT_FOR_MANUAL_ARM ... waiting_for=ARM` | PASS |
| PWM duty = 0 | `duty_permille=0`, LEDC timer started with duty 0 | PASS |
| No spontaneous TEC activation | both EN pins 0, no `H6 ON` line, no run task notification | PASS |

The `spi_flash` warning is expected: the physical part is 4 MB but the image
header declares the configured 2 MB, and all partitions live inside 2 MB.

## 4. LEDC GPIO 5 warning — analysis

`W (96) ledc: GPIO 5 is not usable, maybe conflict with others` is emitted by
`_ledc_set_pin` (`esp_driver_ledc/src/ledc.c:820`) when the output path was
already reserved. `outputs_early_safe()` calls `gpio_config()` on GPIO 5/6/10
before any peripheral, and `gpio_config()` reserves output pins
(`esp_driver_gpio/src/gpio.c:390`). LEDC then calls `gpio_matrix_output()` and
returns `ESP_OK`, so the channel is configured and the RPWM signal is routed
to the pad. `pwm_init()` checks every LEDC return code and would have logged
`H6 FAULT pwm_init_failed arm_blocked=1` on a real failure; that line is
absent, so PWM init succeeded with the reservation warning only.

Residual uncertainty, stated explicitly: the warning is cosmetic by code
inspection, but the physical PWM waveform has not been observed. The
authoritative functional check is PZEM branch current during the gated run
(expected order 1 A at 10 % on 12 V); if current stays at zero with valid bus
voltage, the run must be stopped and classified H6_FAIL.

Note: `STATUS` reports `rpwm_level` from `gpio_get_level()`, which reads the
pin's input side and cannot prove the PWM output. It is used only as an
off-state confirmation (0 when the channel is at 0 %).

## 5. Live state and idle stability

`STATUS` immediately after flash (`21-status-after-flash.log`):

```
H6 STATUS state=WAIT_FOR_MANUAL_ARM reason=NONE run_consumed=0 elapsed_ms=0 duty_permille=0 ren=0 len=0 rpwm_level=0 pzem_ready=1
H6 STATUS pzem=TIMEOUT
```

After a 70 s no-reset monitor window (`22-idle-wait.log`): no `ESP-ROM`
reboot marker, no task-watchdog or panic output, no spontaneous lines.
`STATUS` after the idle period (`23-status-after-idle.log`) still reports
`WAIT_FOR_MANUAL_ARM`, `run_consumed=0`, all outputs 0.

Why it can wait indefinitely at the gate:

- state `WAIT_FOR_MANUAL_ARM` has no timer and no task action;
- the 60 s guard timer is created but not started until `START`;
- the run task blocks on a task notification, which only `cmd_start()` gives;
- `ARM` alone changes no pin and starts no timer;
- one run per boot is latched by `run_consumed` on the first accepted `START`;
- watchdog is 10 s, idle tasks are serviced by the blocked console/run tasks;
- a reboot would land back in `WAIT_FOR_MANUAL_ARM` with outputs off.

## 6. PZEM in the current state

`pzem=TIMEOUT` is expected because the 12 V PSU is off and its output is
disconnected; the PZEM-017 is powered from the measured branch. The UART
driver initialised (`PZEM init=OK`) and `pzem_ready=1`. This is **not** a PZEM
fault and must not be reported as one. The same condition appears in the
pre-flash W04 boot log (`03-w04-boot-before-flash.log`).

## 7. Gate state

- 15 A TEC fuse: **removed** (slot 3).
- PSU 12 V: **off and disconnected**.
- `ARM` sent: **no**.
- `START` sent: **no**.
- TEC power ever applied in this session: **no**.
- W04 gates: unchanged (production code not modified).
- Git: no commit, push, merge, reset or rebase.

The next action is the plan §8 operator power gate. Nothing further will be
sent to the device before an explicit operator PASS.

## 8. Evidence index (this phase)

| File | Content |
|---|---|
| `02-identity-backup.md` | port/MAC/flash identity, partition layout, backup hashes |
| `02-partition-table-read.bin` | raw pre-flash partition table |
| `02-partition-table.txt` | parsed partition table |
| `03-w04-boot-before-flash.log` | genuine W04 boot log before the write |
| `w04-flash-backup.bin` | full 4 MB pre-flash backup |
| `w04-flash-backup-reread.bin` | independent second read (NVS-only delta) |
| `w04-region-*.bin` | restore units and static regions |
| `10-flash-h6.log` | flash transcript |
| `11-h6-readback.bin` | post-flash read-back |
| `20-boot-after-flash.log` | genuine H6 boot log |
| `21-status-after-flash.log` | first STATUS |
| `22-idle-wait.log` | 70 s no-reset idle observation |
| `23-status-after-idle.log` | STATUS after idle |
