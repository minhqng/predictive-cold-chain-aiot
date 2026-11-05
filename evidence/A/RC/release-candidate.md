# Member A production release candidate — 2026-11-03

Base: `feat/a-w06-command-ack` (`4d31fe5`), the top of the stack
`main` → PR #13 (`feat/a-w04-tec-commissioning`) → PR #16 (`feat/a-w05-telemetry`)
→ PR #17 (`feat/a-w06-command-ack`).

## 1. What this candidate is

The first ESP32-S3 image of Member A's **production** firmware tree
(`firmware/main/`, 23 translation units) that has been compiled. Before this
date that tree had no build log and no `sdkconfig.defaults`; every compile and
every on-box result belonged to the separate H6/H7/H8 bench applications.

The device still runs the H8 bench image
`01cedce3b794638f25ae4c7f1e2dfdcb4b00555fdc81a0bcf4d35ed4187f6c9f`. **Nothing in
this file is a hardware result.** No image in this candidate has been flashed,
booted, or energized.

## 2. Artifact

| File | Bytes | SHA-256 |
|---|---:|---|
| `coldguard_firmware.bin` (app, offset `0x10000`) | 247 584 | `f3a20eace41019f31f93256baa5bed306cf0d72295d2d3014786d95729802a8a` |
| `coldguard_firmware.elf` | 4 668 796 | `12a799673880ef5ce9e78875f5c30860ad830fc6568cf37850aa928939076e76` |
| `bootloader.bin` (offset `0x0`) | 19 008 | `d457eb9a225f2882f2b40c19adf58acd567e9143d036ea10e6633d680f8a1901` |
| `partition-table.bin` (offset `0x8000`) | 3 072 | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` |

App partition headroom: smallest app partition `0x100000`, image `0x3c720`, 76 %
free. Flash arguments `--flash-mode dio --flash-freq 80m --flash-size 2MB`.

`.bin` files are deliberately **not** committed into any evidence dossier; the
dossier guard that forbids stray flash images stays active. Reproduce the bytes
from the pinned sources in `00-source-hashes.txt` (49 files) plus
`firmware/sdkconfig.defaults`.

## 3. Reproduce it

```
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  ". 'C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1';" ^
  "Set-Location '<short path containing firmware/CMakeLists.txt, main/, sdkconfig.defaults>';" ^
  "idf.py set-target esp32s3; idf.py build"
```

Stage the sources at a **short** path. ESP-IDF/mbedtls object paths past roughly
250 characters fail to build, which is why the build above ran from
`C:\Users\dlbac\Downloads\coldguard-repo\_rcbuild4` rather than from the
worktree. Toolchain actually used: ESP-IDF v6.1,
`xtensa-esp-elf esp-15.2.0_20251204`, python venv
`C:/Espressif/tools/python/v6.1/venv`.

`idf.py set-target` honours `firmware/sdkconfig.defaults`. It selects the native
USB-Serial/JTAG port as the **primary** console: at the IDF default the primary
console is UART0 and COM4 is only secondary, which would let the operator read
the device but not drive its command console. Flash size stays 2 MB because that
is the layout already proven on this board by the bench builds, even though the
package holds 4 MB.

## 4. Software defects closed by this candidate

1. **Hot-side probe reported as chamber air** (release-blocking). `cg_telemetry.c`
   sourced `t_inside_c` from role T2, and the operator-frozen as-built map makes
   T2 = `28AEBF2200000006` the TEC **hot side**: all 957 rows of
   `evidence/A/W04/tec-cooling-response-600s.csv` carry `t2_role=HOT_SIDE`, and
   that probe rose 29.875 → 39.938 °C while chamber air fell by about 9 °C. Now
   `t_inside_src=T1` (CHAMBER_CENTER) with the hot side emitted separately as
   `t_hot_side_c` / `t_hot_side_src=T2`. The schema number stayed at 3 and no
   required token was added, so every previously committed capture still parses.
2. **Per-boot door polarity attestation** (D25). Door validity previously derived
   only from the compile-time `CG_DOOR_POLARITY_CONFIRMED`. A `polarity_attested`
   field cleared by `cg_door_init()` now gates the semantic state, so every reset
   returns the door to `UNVERIFIED` and the shipped build is unchanged while the
   constant stays 0. The attestation setter has no caller — the polarity has
   never been commissioned.
3. **Evidence that rewrote itself.** `run_all_checks_w05.py` invoked
   `build_timing_pilot.py` in write mode, so each run overwrote the very dossier
   the preceding step had hash-verified. It now runs `--check`. The W05 fixture
   and the W06 contract artifacts were regenerated deliberately and re-pinned,
   with dated corrections appended rather than history rewritten.
4. **Schema-2 frame labelled schema-3.** `demo-command-capture.log` embedded the
   stale W05 line while its test called it "the schema-3 telemetry line the
   harness emitted"; regenerating the artifacts from the real emitter closes the
   mismatch.

Verified as **not** defects, with source evidence, and therefore left alone:
the enable/actuation label already reads `FIRMWARE_OUTPUT_STATE` rather than
claiming a physical readback (D02); `CG_RS485_DIR_MODE` is already auto-direction
for the as-built TTL485-V2.0, so no DE/RE pin is driven; the MAX3485-era macro
names are pinned by host guards outside this tree and carry a naming-debt comment
instead of a rename.

## 5. Host verification actually run on this candidate

| Gate | Result |
|---|---|
| `run_all_checks.py` (W02) | 3/3 passed |
| `run_all_checks_w03.py` | 5/5 passed |
| `run_all_checks_w04.py` | 7/7 passed |
| `run_all_checks_w05.py` | 10/10 passed |
| `run_all_checks_w06.py` | 12/12 passed |
| `idf.py build` (ESP-IDF v6.1) | IDF_BUILD_OK, zero errors |
| `tools/tests` unittest discovery | recorded separately below |

The `--check` steps now fail closed if the emitter drifts, which is the intended
behaviour. None of these gates compiles for the target *and* runs on silicon:
they are host-side static, harness and dossier checks.

## 6. What remains physically open

See `remaining-hardware-gates.md` in this directory: ten gates, from the first
production flash through the hot-side limit, the fuse strategy, the ground-loop
mitigation, a true POWERON observation and the repetition campaigns. Software
work cannot close any of them and this candidate does not claim to.

## 7. Acceptance entrypoint and flash safety

`tools/acceptance/run-member-a-acceptance.ps1` is the single Windows entrypoint;
`tools/acceptance/README.md` carries the phase table, the exact commands, and the
backup-and-recovery path for the currently installed image. Its default mode
performs no flash and no hardware action; PHASE D/E/F are unreachable without
their explicit switches plus a typed operator acknowledgement, and the campaign
vocabulary (`EXECUTABLE` / `BLOCKED_NEEDS_OPERATOR` / `BLOCKED_DEPENDENCY`) is
reused from `A-IHA-01-campaign`.

Flash and energization remain gated: two-step authorization, no automatic retry,
PSU 12 V off, fuse slot 3 out until a separately authorized supervised stage.
