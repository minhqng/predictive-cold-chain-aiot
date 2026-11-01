# H6 pre-flash: target identity, flash detection and full-chip backup

Session date: 2026-10-29
Result: **identity verified, 4 MB flash detected, full-chip backup taken and
region-verified. No write performed yet.**

## 1. Serial port and USB identity

| Item | Value |
|---|---|
| Port | `COM4` |
| USB VID:PID | `303A:1001` (ESP32-S3 USB-Serial/JTAG) |
| PnP serial number | `E0:72:A1:BC:CF:4C` |
| Driver instance | `USB\VID_303A&PID_1001&MI_00\7&23BBB5F2&0&0000` |

## 2. Target identity (esptool chip-id)

```
Chip type:          ESP32-S3 (QFN56) (revision v0.2)
Features:           Wi-Fi, BT 5 (LE), Dual Core + LP Core, 240MHz
Crystal frequency:  40MHz
USB mode:           USB-Serial/JTAG
MAC:                e0:72:a1:bc:cf:4c
```

MAC matches the required `e0:72:a1:bc:cf:4c`. The chip has no chip-ID
register; esptool reads the MAC instead (warning printed).

## 3. Physical flash detection (esptool flash-id)

```
Manufacturer: 5e
Device: 4016
Detected flash size: 4MB
Flash type set in eFuse: quad (4 data lines)
Flash voltage set by a strapping pin: 3.3V
```

The physical part is **4 MB**, not the 2 MB used by the firmware's flash-size
setting. The backup therefore covers the entire 4 MB chip.

## 4. On-device partition layout (read from 0x8000, 0x1000 bytes)

| # | Type | Subtype | Offset | Size | Label |
|---|---|---|---|---|---|
| 0 | data | nvs (0x02) | 0x009000 | 0x006000 (24 KiB) | `nvs` |
| 1 | data | phy (0x01) | 0x00F000 | 0x001000 (4 KiB) | `phy_init` |
| 2 | app | factory (0x00) | 0x010000 | 0x100000 (1 MiB) | `factory` |
| 3 | — | MD5 entry | — | — | `f4ad4f4538564b5d7435b62c75b69524` |

Partition table SHA-256 (first 0xC00 bytes, exact table length):
`7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820`
— identical to the recorded W04 partition table. Raw read kept as
`02-partition-table-read.bin`, parsed as `02-partition-table.txt`.

## 5. Full-chip backup

| File | Size | SHA-256 |
|---|---|---|
| `w04-flash-backup.bin` | 4 194 304 | `9ac21e7863ae2f4072655c8bf9788dae337b001a908efcd22b2eb677140595cf` |
| `w04-flash-backup-reread.bin` (independent second read) | 4 194 304 | `41dd8e27540a744b34f2bb934ec1811d6ff32874d089aea32ddec06eac4e4033` |
| `w04-region-0x00000-0x10000.bin` (restore unit: bootloader + table + NVS + phy) | 65 536 | `f06b47007558c1fe0ef905c138a2d3c3048c903dec12816f8c7016d7d5431b62` |
| `w04-region-bootloader.bin` (0x0, 32 KiB) | 32 768 | verifies OK |
| `w04-region-parttable.bin` (0x8000, 4 KiB) | 4 096 | verifies OK |
| `w04-region-app.bin` (0x10000, 244 352) | 244 352 | see §6 |

Region hashes from the first backup:

| Region | SHA-256 | Against recorded W04 provenance |
|---|---|---|
| bootloader 0x0 len 21120 | `b1aeaf744710bc1aa533c7ac428f814cd8ba8469fd304585cd344e1fa52aef94` | **exact match** |
| partition table 0x8000 len 0xC00 | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` | **exact match** |
| app 0x10000 len 244352 | `15e640fff7dec8ab733d8f5d1cc1cba48748d1a85f3f2302289a1c2996acbfda` | differs from the recorded file hash, see §6 |

## 6. App-region hash note

The app region on the device is **byte-for-byte identical** to the first
244 352 bytes of the preserved W04 rebuild
`_w04-g1-evidence/fw-build/firmware/build/coldguard_firmware.bin`
(verified with `cmp`: 0 differing bytes). That local file is 244 448 bytes,
96 bytes longer than the flashed image, so its whole-file hash
`39dd8332…` differs. The originally flashed 244 352-byte file named in the
build provenance (`7cb2658374…`) is not present bit-exactly on this host, so
its hash cannot be reproduced from local files. This is why the pre-flash
read-back, not a rebuild, is the authoritative restore source.

## 7. Integrity verification

1. **Independent second full read** (`w04-flash-backup-reread.bin`): differs
   from the first read in exactly **56 bytes**, all inside the NVS partition
   (0x903A and 0x9DC0–0x9DFB, ASCII `boot_count`). The running W04 app
   increments its NVS boot counter on every reset, so the NVS region is live;
   every other byte of the 4 MB image is identical across the two reads.
2. **esptool region verification** (`verify-flash`, flash params
   `dio`/`80m`/`2MB`, i.e. how the board was originally written):

   ```
   bootloader 0x0     0x8000  bytes -> Verification successful (digest matched)
   parttable  0x8000  0x1000  bytes -> Verification successful (digest matched)
   app        0x10000 0x3ba80 bytes -> Verification successful (digest matched)
   ```

3. A first attempt to verify the whole 4 MB file with `--flash-size 4MB`
   reported `digest mismatch`. Cause: esptool patched the bootloader image
   header in memory for a 4 MB flash, while the stored image was written with
   2 MB parameters. It did **not** modify the backup file: its SHA-256
   remained `9ac21e78…` before and after the attempt. Region verification
   with the original 2 MB parameters passed, as shown above.

Conclusion: the backup is a faithful copy of the static flash content, and
the only difference between reads is the live NVS counter area.

## 8. Restore unit and procedure

Restore writes only the used regions (all inside the 2 MB configured flash):

```
write-flash --flash-mode dio --flash-freq 80m --flash-size 2MB \
  0x0     w04-region-0x00000-0x10000.bin     (64 KiB: bootloader, table, NVS, phy)
  0x10000 w04-region-app.bin                 (244 352 bytes)
```

Writing with the original 2 MB parameters reproduces the backed-up bootloader
header unchanged (verified above), so this is a bit-exact restore of all
meaningful regions. NVS will be restored to its state at backup time
(boot counter rolls back), which is harmless. The full 4 MB dump remains
available if a whole-chip restore is ever required.

## 9. Post-flash expectation regarding PZEM

The 12 V PSU is OFF, so PZEM will report no data
(`power_status=NO_DATA`, `PZEM status=TIMEOUT`). This is **expected** and is
not evidence of a PZEM/UART fault; the same condition is visible in the
pre-flash W04 boot log (`03-w04-boot-before-flash.log`).

## 10. Commands executed (non-destructive)

```
esptool --chip esp32s3 -p COM4 -b 460800 chip-id
esptool --chip esp32s3 -p COM4 -b 460800 flash-id
esptool --chip esp32s3 -p COM4 -b 460800 read-flash 0x8000 0x1000 ...
esptool --chip esp32s3 -p COM4 -b 460800 read-flash 0x0 0x400000 ...
esptool --chip esp32s3 -p COM4 -b 460800 verify-flash --flash-size 2MB ...
```

No write, erase or flash was performed.
