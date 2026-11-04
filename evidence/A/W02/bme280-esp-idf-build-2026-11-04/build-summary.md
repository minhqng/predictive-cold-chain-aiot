# BME280 ESP-IDF build record - 2026-11-04

Member A compile-only evidence for A-W02-06. No flash, no energization, no
output-enable change. This record exists because `evidence/A/W02/acceptance.md`
section 9 marked the build claim PROVENANCE_BACKFILL_NEEDED: the compile had
succeeded but nothing in the repository let a reader check that.

## What was built

| Item | Value |
|---|---|
| Branch | `feat/a-bme280-environment-producer` |
| Commit built | `f35b39e80268c0a8edff5a03b16f42388e2f55e0` |
| Project | `firmware/` (`project(coldguard_firmware)`) |
| Target | `esp32s3` (`CONFIG_IDF_TARGET="esp32s3"` in `firmware/sdkconfig.defaults`) |
| ESP-IDF | v6.1.0 at `C:\Espressif\v6.1\esp-idf` |
| Toolchain | xtensa-esp-elf `esp-15.2.0_20251204`, cmake 4.0.3, ninja 1.12.1, ccache 4.12.1 |
| Python venv | `C:\Espressif\tools\python\v6.1\venv` (Python 3.11.15) |
| Commands | `idf.py set-target esp32s3` then `idf.py build` |
| Result | `SET_TARGET_EXIT=0`, `BUILD_EXIT=0` |
| Diagnostics | 0 errors, 0 warnings (count of `error:` and `warning:` in the log) |
| Artifact | `coldguard_firmware.bin`, 268912 bytes |
| Artifact SHA-256 | `6f6bfaa929549f322568af6473fc2a42efe8edd87d36712f689e347cd1c010b0` |

## How to reproduce, and the honest limit

Run from `firmware/`:

```
idf.py set-target esp32s3
idf.py build
```

`set-target` rewrites `sdkconfig`, so the image is compile-proven but not
bit-reproducible from git alone - the same limitation `evidence/A/W04/acceptance.md`
records for the W04 build. Verify the inputs first with `source-hashes.txt`:

```
cd <repo root> && sha256sum -c evidence/A/W02/bme280-esp-idf-build-2026-11-04/source-hashes.txt
```

If every source hash matches `f35b39e80268c0a8edff5a03b16f42388e2f55e0`, a rebuild exercises the same bytes this
record describes. A matching image hash is NOT expected and is not a failure.

## What this record does NOT prove

- Nothing about hardware. The image was never flashed and never read from a board.
- Nothing about the I2C strap address: the transport probes `0x76` then `0x77` at
  run time, so compiling it says nothing about which, if either, answers.
- Nothing about the humidity trim nibble packing against real silicon.
- A host C compilation is not an ESP-IDF build, and this is not a host compilation.

## Build log tail

```
[1097/1103] No install step for 'bootloader'
[1098/1103] Completed 'bootloader'
[1099/1103] Generating esp-idf/esp_system/ld/sections.ld
NOTE: C:/Espressif/v6.1/esp-idf/components/bt/host/nimble/Kconfig.in:1428: BT_NIMBLE_MESH_PROVISIONER: 'default 0' is not a valid bool value (only 'y' and 'n' are allowed). Value is treated as 'n'.
NOTE: C:/Espressif/v6.1/esp-idf/components/fatfs/Kconfig:240: FATFS_PRINT_LLI: 'default 0' is not a valid bool value (only 'y' and 'n' are allowed). Value is treated as 'n'.
NOTE: C:/Espressif/v6.1/esp-idf/components/fatfs/Kconfig:245: FATFS_PRINT_FLOAT: 'default 0' is not a valid bool value (only 'y' and 'n' are allowed). Value is treated as 'n'.
NOTE: C:/Espressif/v6.1/esp-idf/components/bootloader/Kconfig.projbuild:383: Deprecation notice: hex literal '0' without '0x' prefix detected. In the next major version, hex literals will be required to have a '0x' prefix.
NOTE: C:/Espressif/v6.1/esp-idf/components/bootloader/Kconfig.projbuild:423: Deprecation notice: hex literal '0' without '0x' prefix detected. In the next major version, hex literals will be required to have a '0x' prefix.
NOTE: C:/Espressif/v6.1/esp-idf/components/bt/common/Kconfig.in:136: Deprecation notice: hex literal '0' without '0x' prefix detected. In the next major version, hex literals will be required to have a '0x' prefix.
NOTE: C:/Espressif/v6.1/esp-idf/components/bt/host/nimble/Kconfig.in:1023: Deprecation notice: hex literal '0' without '0x' prefix detected. In the next major version, hex literals will be required to have a '0x' prefix.
NOTE: C:/Espressif/v6.1/esp-idf/components/bt/controller/esp32c3/Kconfig.in:652: Deprecation notice: hex literal '0' without '0x' prefix detected. In the next major version, hex literals will be required to have a '0x' prefix.
NOTE: C:/Espressif/v6.1/esp-idf/components/esp_hw_support\./lowpower/port/esp32p4/Kconfig.p4_rev3_mspi_workaround:6: Deprecation notice: hex literal '0' without '0x' prefix detected. In the next major version, hex literals will be required to have a '0x' prefix.
NOTE: C:/Espressif/v6.1/esp-idf/components/esp_mm/Kconfig:20: Deprecation notice: hex literal '0' without '0x' prefix detected. In the next major version, hex literals will be required to have a '0x' prefix.
NOTE: C:/Espressif/v6.1/esp-idf/components/esp_system\./port/soc/esp32s3/Kconfig.memory:21: Deprecation notice: hex literal '0' without '0x' prefix detected. In the next major version, hex literals will be required to have a '0x' prefix.
NOTE: C:/Espressif/v6.1/esp-idf/components/openthread/Kconfig:106: Deprecation notice: hex literal '0' without '0x' prefix detected. In the next major version, hex literals will be required to have a '0x' prefix.

[1100/1103] Building C object CMakeFiles/coldguard_firmware.elf.dir/project_elf_src_esp32s3.c.obj
[1101/1103] Linking CXX executable coldguard_firmware.elf
[1102/1103] Generating binary image from built executable
esptool v5.6.0

Creating ESP32-S3 image...

Merged 3 ELF sections.

Successfully created ESP32-S3 image.

Generated C:/cgb/bme/firmware/build/coldguard_firmware.bin
[1103/1103] C:\WINDOWS\system32\cmd.exe /C "cd /D C:\cgb\bme\firmware\build && C:\Espressif\tools\python\v6.1\venv\Scripts\python.exe C:/Espressif/v6.1/esp-idf/components/partition_table/check_sizes.py --offset 0x8000 partition --type app C:/cgb/bme/firmware/build/partition_table/partition-table.bin C:/cgb/bme/firmware/build/coldguard_firmware.bin"
coldguard_firmware.bin binary size 0x41a70 bytes. Smallest app partition is 0x100000 bytes. 0xbe590 bytes (74%) free.

Executing action: all (aliases: build)
Running ninja in directory C:\cgb\bme\firmware\build
Executing "ninja all"...


Project build complete. To flash, run:
 idf.py flash
or
 idf.py -p PORT flash
or
 python -m esptool --chip esp32s3 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 2MB --flash-freq 80m 0x0 build\bootloader\bootloader.bin 0x8000 build\partition_table\partition-table.bin 0x10000 build\coldguard_firmware.bin
or from the "C:\cgb\bme\firmware\build" directory
 python -m esptool --chip esp32s3 -b 460800 --before default-reset --after hard-reset write-flash "@flash_args"
BUILD_EXIT=0
```
