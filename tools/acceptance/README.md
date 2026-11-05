# Member A release-candidate acceptance entrypoint

`run-member-a-acceptance.ps1` is the single Windows entrypoint for the Member A
RC acceptance campaign: PHASE_A_OFFLINE .. PHASE_F_TEC_ACTUATION, with every
hardware-touching phase behind an explicit operator switch.

Companion: `read_only_capture.py` (port capture; see "Read-only guarantee").

## Gate model

| Phase | Risk class | Executed by default | Switches required to reach it |
|---|---|---|---|
| PHASE_A_OFFLINE | OFFLINE | yes | none |
| PHASE_B_IDENTITY | READ_ONLY_PORT | no, recorded NOT_RUN / BLOCKED | `-AllowSerialProbe` (+ `-Port` to capture) |
| PHASE_C_BUILD | OFFLINE | no, and DRY-RUN even when requested | `-RunBuild` to actually invoke idf.py |
| PHASE_D_FLASH | FLASH_WRITE | no, BLOCKED | `-AllowFlash` **and** `-ConfirmFlashPhrase "<literal>"` **and** `-ExecuteFlash` |
| PHASE_E_SAFETY_OFF | POWERED_ISOLATED | no, BLOCKED | `-AllowEnergize -AllowSerialProbe` **and** all five `-Ack*` switches |
| PHASE_F_TEC_ACTUATION | POWERED_ACTUATION | no, BLOCKED | `-AllowTecActuation -OperatorSupervised -AckSlot3Status "<what you see>"` (+ typed `-ConfirmTecPhrase`) |

Verdicts are `PASS`, `FAIL`, `NOT_RUN` (with reason), `BLOCKED_NEEDS_OPERATOR`.
The top-level `member-a-acceptance.json` / `.md` carry a per-phase verdict table.

Exit codes: `0` every requested phase PASSED · `1` at least one phase FAILED ·
`2` no failure but one or more phases NOT_RUN / BLOCKED (this is the normal
result of a safe default run) · `3` the script could not start.
`1` and `2` are deliberately different: BLOCKED is not FAIL.

**PowerShell argument note:** `powershell -File` cannot bind a comma-separated
array, so `-Phases B,C` fails `ValidateSet`. Pass one phase per flag
(`-Phases B -Phases C`) or use `-AllPhases`.

## (a) Offline only — no port, no build, no flash, no energisation

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\acceptance\run-member-a-acceptance.ps1
```

Runs the host-side validators only. Phases B–F are still recorded in the verdict
table, each with the exact gates that would unblock it. Expected exit `2`.

## (b) Identity only — read-only, zero bytes written to the port

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\acceptance\run-member-a-acceptance.ps1 `
  -Phases B -AllowSerialProbe -Port COM4 -Baud 115200 -Seconds 30
```

Without `-Port` the phase degrades to `NOT_RUN` and only PnP enumeration runs —
no port object is ever created. `-Port` alone is not enough: `-AllowSerialProbe`
is what permits read-only port work at all.

## (c) Build dry-run — prints the exact command, invokes nothing

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\acceptance\run-member-a-acceptance.ps1 `
  -Phases C -BuildDir C:\Users\dlbac\Downloads\coldguard-repo\_rcbuild
```

PHASE_C is DRY-RUN unless `-RunBuild` is passed, so it never races a build the
coordinator may already own. It prints the full idf.py recipe and the
`-BuildDir` length budget, then hashes any pre-existing artifacts (read-only).

```
ESP-IDF and mbedtls fail once an object path exceeds ~250 characters, so the
source tree must be staged to a short path before it is built. This script only
accepts a `-BuildDir` that already exists; it never creates or modifies one.
```

To hash a completed build without invoking the toolchain: `-Phases C -ArtifactsOnly -BuildDir <staged path>`.
To actually build, after confirming nothing else owns that directory: `-Phases C -RunBuild`.

## PHASE_D / E / F are structurally unreachable

Flashing needs three independent things (switch + typed literal + `-ExecuteFlash`);
even then step 1 is the backup **read** and a failure there aborts before any write.

PHASE_E prints six physical preconditions and needs a separate acknowledgement
switch for each. Fuse slot 3 = the 15 A IBT-2 B+ branch fuse must be **physically
REMOVED** and the 12 V PSU **OFF**; the script never reinserts a fuse, never
toggles a supply, and never sends `ARM`, `STAGE` or `START`.

PHASE_F additionally requires `-OperatorSupervised` and can **never** report
PASS: the entrypoint has no actuation capability, it only writes the operator
action sheet. A slot-3 status matching `unknown|tbd|n/a|not checked|placeholder`,
or one acknowledged as removed, blocks the phase outright.

COM loss is terminal everywhere: capture exit `3` → FAIL → the run aborts with
no retry, and later phases are recorded NOT_RUN.

## Read-only guarantee

`read_only_capture.py` opens the port, immediately de-asserts DTR and RTS, and
then only ever calls `port.read(256)`. There is no write call against the port
object anywhere in the file; `bytes_written` is a real accumulator that nothing
increments, and `writes_to_port` is reported as `NONE`. The runner asserts
`bytes_written == 0` **and** `writes_to_port == NONE` from the emitted summary
before it will call the capture a PASS — the guarantee is checked from observed
output, not from a comment.

## FLASH BACKUP AND RECOVERY

Everything below is taken from the existing records in this worktree; it is not
invented and nothing here was executed by the acceptance runner.

**What is installed right now.** An **H8 bench image**, not a production build:

| Item | Value | Source |
|---|---|---|
| Application | H8 T2 HOT_SIDE bench image | `evidence/A/W04/w04-physical-verification-plan.md:19` |
| SHA-256 | `01cedce3b794638f25ae4c7f1e2dfdcb4b00555fdc81a0bcf4d35ed4187f6c9f` | `evidence/A/W04/ARTIFACT-MANIFEST.md:101` |
| Size | 258,544 bytes | same |
| Local bin | `firmware/h8-bench/build-t2-hot-side/coldguard_h8_bench.bin` | same |
| Last flash event | 2026-11-01; none after | `w04-physical-verification-plan.md:21` |

**Target identity.** ESP32-S3 (QFN56) rev v0.2, MAC `e0:72:a1:bc:cf:4c`, native
USB-Serial/JTAG on **COM4**, USB **VID:PID 303A:1001**, driver instance
`USB\VID_303A&PID_1001&MI_00\7&23BBB5F2&0&0000` —
`evidence/A/W04/h6/02-identity-backup.md:9-24`.

**Flash size caveat.** The physical part is **4 MB** while the firmware header
says 2 MB; esptool logs `Detected size(4096k) larger than the size in the binary
image header(2048k)` and always writes with `--flash-size 2MB`
(`02-identity-backup.md:31-40`, `08-refix-flash-verification.md:26-38`). Verifying
a 2 MB-written image against `--flash-size 4MB` reports a false
`digest mismatch` (`02-identity-backup.md:103-108`).

**Partition layout read from the device** (`02-identity-backup.md:42-52`):

| Type | Label | Offset | Size |
|---|---|---|---|
| data | nvs | `0x9000` | 24 KiB |
| data | phy_init | `0xF000` | 4 KiB |
| app | factory | `0x10000` | 1 MiB |
| bootloader | — | `0x0` | — |
| partition table | — | `0x8000` | 3072 B |

**Recovery material already on hand** (`02-identity-backup.md:56-66`, §8 reused in `08-refix-flash-verification.md:106-114`):

| File | Size | SHA-256 |
|---|---|---|
| `w04-flash-backup.bin` (full-chip, authoritative) | 4,194,304 | `9ac21e7863ae2f4072655c8bf9788dae337b001a908efcd22b2eb677140595cf` |
| `w04-flash-backup-reread.bin` (independent second read) | 4,194,304 | `41dd8e27540a744b34f2bb934ec1811d6ff32874d089aea32ddec06eac4e4033` |
| `w04-region-0x00000-0x10000.bin` (restore unit: bootloader+table+NVS+phy) | 65,536 | `f06b47007558c1fe0ef905c138a2d3c3048c903dec12816f8c7016d7d5431b62` |
| `w04-region-app.bin` (app @ 0x10000) | 244,352 | `15e640fff7dec8ab733d8f5d1cc1cba48748d1a85f3f2302289a1c2996acbfda` |

The two full-chip reads differ in **56 bytes only**, all inside NVS — the running
app increments an NVS `boot_count` on every reset, so that region is live and
byte-stability elsewhere is what proves the backup faithful (`02-identity-backup.md:87-111`).

**Backup before any write.** Record what is installed *first*; a flash is only
recoverable if the pre-flash read succeeded:

```
esptool --chip esp32s3 -p COM4 -b 460800 --before default-reset --after no-reset `
  read-flash 0x0 0x400000 h8-before-flash.bin
```

`W05/acceptance.md:56-58` states the same rule in words: *"Preserve recovery
before any write ... Nothing is flashed until the backup is confirmed readable."*

**Bit-exact restore of the known-good region** (`02-identity-backup.md:113-127`):

```
esptool --chip esp32s3 -p COM4 -b 460800 write-flash `
  --flash-mode dio --flash-freq 80m --flash-size 2MB `
  0x0     w04-region-0x00000-0x10000.bin `
  0x10000 w04-region-app.bin
```

NVS rolls back to its backup-time boot counter, which is harmless; the full 4 MB
dump remains available for a whole-chip restore.

**Native-USB caveat.** The USB-Serial/JTAG port drops when board power is
removed, so a cold-boot banner cannot be captured through it; attach UART0 on
GPIO43/44 when the run must record its own start (`W05/acceptance.md:60-63`).

## What this runner can and cannot claim

- **No production image has ever been flashed on this board.** The delivered W04
  production build (`0acd230c…`) "has never been flashed"
  (`evidence/A/W04/w04-physical-verification-plan.md:21-23`), and the W05 build
  "has never run on this board" (`evidence/A/W05/acceptance.md:56-57`). Five cold
  boots taken today would evidence the H8 **bench** program, not the delivered
  firmware.
- **No physical PASS may be claimed from an offline run.** PHASE_A PASS proves
  host-side validators and unit checks only. It is not evidence of duty zero, of
  fuse state, of TEC behaviour, of current, or of thermal response.
- The W04/H8 hashes quoted above were read from repo records; this runner has not
  re-flashed, re-read or re-verified them.

## Known issue: the 90 MB phase-A document (fixed)

`output/20261103T095939Z/phase-A-offline.json` is **90,635,714 bytes** for a
1,089-byte driver stdout log. Root cause, recorded here so it is not
re-introduced: `Get-Content` returns strings decorated with the provider
NoteProperties `PSPath/PSParentPath/PSChildName/PSDrive/PSProvider`, and
`ConvertTo-Json` walks `PSDrive → Provider → ImplementingType` (a live
`System.Type`) into `Assembly.DefinedTypes` / `ExportedTypes` — the whole
System.Management.Automation type table — **once per line**. The fix is
`Get-PlainLines` (`[System.IO.File]::ReadAllLines`, undecorated strings) plus
`ConvertTo-JsonBounded`, which hard-trims to a minimal `BLOCKED_SOFTWARE`
document if a size budget is ever exceeded again. After the fix the same
content serialises to **10,588 characters**. The oversized historical file is
left in place untouched as the evidence of the defect.
