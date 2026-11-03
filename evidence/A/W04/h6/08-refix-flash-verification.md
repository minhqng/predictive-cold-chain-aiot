# H6 corrected PZEM image — flash and boot verification (2026-10-29)

Status: **PASS — corrected image flashed, selftest 172/172, SAFE_OFF and
WAIT_FOR_MANUAL_ARM confirmed, no output and no reboot in a 60 s idle window.
Stopped at the power-restoration gate.** No `ARM`, no `START`, TEC branch
fuse still removed, PSU still off.

## 1. Operator isolation (prerequisite)

Operator confirmed before this session: PSU 12 V OFF and disconnected from AC,
TEC 15 A fuse (slot 3) removed while unpowered, all other wiring unchanged,
ESP32-S3 still on USB.

## 2. Target identity

`esptool --chip esp32s3 -p COM4 -b 460800 chip-id`:

```
Chip type:          ESP32-S3 (QFN56) (revision v0.2)
USB mode:           USB-Serial/JTAG
MAC:                e0:72:a1:bc:cf:4c        <- matches the required target
```

## 3. Flash (`12-flash-h6-fix.log`)

```
esptool --chip esp32s3 -p COM4 -b 460800 --before default-reset --after hard-reset \
  write-flash --flash-mode dio --flash-freq 80m --flash-size 2MB \
  0x0     _h6-build/bootloader/bootloader.bin \
  0x8000  _h6-build/partition_table/partition-table.bin \
  0x10000 _h6-build/coldguard_h6_bench.bin
```

| Offset | Image | Bytes | esptool |
|---|---:|---:|---|
| 0x00000 | bootloader | 19 008 | Hash of data verified |
| 0x08000 | partition table | 3 072 | Hash of data verified |
| 0x10000 | app | 248 592 | Hash of data verified |

No chip erase. Sector erases limited to 0x0–0x5FFF, 0x8000–0x8FFF and
0x10000–0x4CFFF (app end 0x4CB10); NVS at 0x9000 untouched.

## 4. Independent read-back (`13-h6-readback-fix.bin`, 0x0–0x4D000)

| Region | SHA-256 | Differing bytes vs build file |
|---|---|---:|
| bootloader 0x0, 19 008 | `764792967f1a0910d20290c9c2a51611a7a6d3cb0441d2c175b4200d0f3ff10d` | 0 |
| partition table 0x8000, 3 072 | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` | 0 |
| app 0x10000, 248 592 | `963f3cd623b8c8fade910adda723c0f178e7bc303528b63ed6520fd12110858d` | 0 |

The device runs exactly the reviewed build. Bootloader and partition table are
the same images flashed earlier; only the app changed.

## 5. Boot log (`24-boot-after-refix.raw.log`, real capture via idf_monitor)

```
ESP-ROM:esp32s3-20210327
rst:0x15 (USB_UART_CHIP_RESET),boot:0x8 (SPI_FAST_FLASH_BOOT)
W (92) spi_flash: Detected size(4096k) larger than the size in the binary image header(2048k)...
H6 SELFTEST result=PASS checks=172 failures=0

H6 BOOT firmware=coldguard_h6_bench build=Oct 29 2026 22:25:19 pins_rpwm=5 pins_ren=6 pins_len=10 pwm_freq_hz=1000 freq_reconstructed=1 duty_permille=100 max_on_ms=60000 pzem_uart=1
H6 SAFE_OFF duty_permille=0 ren=0 len=0 rpwm_level=0 tec_output=OFF
W (97) ledc: GPIO 5 is not usable, maybe conflict with others
H6 PZEM init=OK uart=1 tx=36 rx=37 baud=9600 slave=1 framing=8N1 read_only=1
H6 READY state=WAIT_FOR_MANUAL_ARM tec_output=OFF waiting_for=ARM
h6> H6 CONSOLE ready commands=ARM,START,STOP,STATUS,HELP
```

| Requirement | Observed | Verdict |
|---|---|---|
| SELFTEST PASS | `checks=172 failures=0` (138 state-machine + 34 PZEM framing/CRC) | PASS |
| SAFE_OFF | `duty_permille=0 ren=0 len=0 rpwm_level=0 tec_output=OFF` | PASS |
| WAIT_FOR_MANUAL_ARM | `state=WAIT_FOR_MANUAL_ARM ... waiting_for=ARM` | PASS |
| duty 0 | `duty_permille=0` at boot | PASS |
| No spontaneous activation | both EN pins 0, no `H6 ON`, no run-task notification | PASS |
| Read-only PZEM init | `read_only=1`, FC04 only | PASS |

The `spi_flash` size warning and the LEDC GPIO 5 reservation warning are the
same two known messages as the previous boot (see `04-post-flash-verification.md`
§4); `pwm_init()` logged no fault.

## 6. PSU-off PZEM behaviour (expected, not a fault)

`STATUS` with the PSU off (`25-status-after-refix.log`):

```
H6 STATUS state=WAIT_FOR_MANUAL_ARM reason=NONE run_consumed=0 elapsed_ms=0 duty_permille=0 ren=0 len=0 rpwm_level=0 pzem_ready=1
H6 PZEM_TRACE attempt=1 tx=0104000000067008 rx_len=0 rx=- ... class=NO_RESPONSE
H6 PZEM_TRACE attempt=2 tx=0104000000067008 rx_len=0 rx=- ... class=NO_RESPONSE
H6 STATUS pzem=TIMEOUT
```

With the 12 V branch dead the TTL485 module is unpowered, so there is not even
an echo (`rx_len=0`). This says nothing about the fix; it confirms that the
trace path runs and that a missing reply is classified `NO_RESPONSE`
(`TIMEOUT`), not `BAD_LENGTH`.

## 7. Idle stability

60 s capture with no commands (`26-idle-after-refix.log`): no device line at
all — no reboot marker, no watchdog, no panic, no actuator line. `STATUS`
afterwards (`27-status-after-idle.log`) still `WAIT_FOR_MANUAL_ARM`,
`run_consumed=0`, all outputs 0.

## 8. W04 restore material (unchanged)

| File | SHA-256 |
|---|---|
| `w04-flash-backup.bin` (4 MB, authoritative) | `9ac21e7863ae2f4072655c8bf9788dae337b001a908efcd22b2eb677140595cf` |
| `w04-flash-backup-reread.bin` (4 MB, second read) | `41dd8e27540a744b34f2bb934ec1811d6ff32874d089aea32ddec06eac4e4033` |
| `w04-region-app.bin` (244 352 B) | `15e640fff7dec8ab733d8f5d1cc1cba48748d1a85f3f2302289a1c2996acbfda` |

Same hashes as recorded before this flash; nothing was rewritten.

## 9. Next gate

Device waits indefinitely in `WAIT_FOR_MANUAL_ARM` with outputs off. Required
next physical action: operator restores the 15 A fuse while unpowered, then
restores PSU power and confirms the V1 fan runs. Then H6 must produce at least
three consecutive CRC-valid samples with plausible decoded values before a
separate ARM/START authorization is requested.
