# W04 physical verification plan — cold boots, pin levels, branch isolation

Status: **NEED_USER_ACTION.** Nothing here has been executed. No firmware was
flashed, no pin was measured, no branch was energized while writing this. The
missing evidence is a gap in the record, **not** a hardware limitation, and it
is closable in one attended session of roughly twenty minutes.

## 1. Which firmware is actually on the board right now

This decides what a cold-boot test would prove, so it was reconstructed from the
flash logs rather than assumed:

| Order | Event | Image | Evidence |
|---|---|---|---|
| 1 | 2026-10-29, production W04 build flashed for the G1 session | `cg-w04-0.1.0` app `39dd8332…` / `7cb26583…` | `g1/32-flash.log`, `g1/SUMMARY.md:14,101` |
| 2 | 2026-10-29, H6 bench image | `coldguard_h6_bench` app `963f3cd6…` | `h6/10-flash-h6.log`, `h6/12-flash-h6-fix.log`, `h6/h6-image-hashes.txt` |
| 3 | 2026-10-30, H7 bench image | `coldguard_h7_bench` `cf1b7e91…` | `h7/30-flash-and-boot.md` |
| 4 | 2026-10-31, H8 bench image, three attempts | `ef7974d8…` → `1df365a4…` → `344185a4…` | `h8/phase4e/h8a-*/flash.log` |
| 5 | 2026-10-31 → 2026-11-01, **final installed image** | H8 T2 HOT_SIDE `01cedce3b794638f25ae4c7f1e2dfdcb4b00555fdc81a0bcf4d35ed4187f6c9f`, 258,544 bytes | `h8/phase4e/H8_T2_HOT_SIDE_CORRECTION.md:9-11`, used by H8-B…E and the 2026-11-01 box-cooling session |

No flash event exists after 2026-11-01. **The board therefore currently runs the
H8 bench image, not the delivered W04 production build (`0acd230c…`, which has
never been flashed) and not the 2026-10-29 production build.**

Consequence: five cold boots taken today would evidence the H8 bench program.
They would not satisfy A-W04-04 for the delivered firmware. That is a flash
decision, and flashing needs your explicit authorization.

## 2. Can the earlier power cycles be authenticated instead?

Partly, and only indirectly. The corpus contains real evidence that the bench
was powered down and restored — `h7/37-power-restoration-gate.md:4` records the
15 A fuse being reinserted *while the PSU was disconnected*; `g0-electrical-verification.md`
records measurements taken with the branch dead; the PZEM polls return
`rx_len=0 class=NO_RESPONSE` whenever the 12 V supply is off — but none of those
captures a device boot banner, because the console was not attached during the
power transition or the port dropped with it.

The ROM bootloader prints `rst:0x1 (POWERON)` on a genuine power-on and
`rst:0x15 (USB_UART_CHIP_RESET)` when the host toggles DTR/RTS. Across 132
banners in 101 captures, every recorded start is `0x15` or `0xc`. So the honest
statement is: **power cycles almost certainly happened, but no capture proves
one, and no `POWERON` banner exists to reuse.** Inventing one, or relabelling a
USB reset as a cold boot, would be fabrication.

## 3. Why the native USB port cannot capture a cold boot

Both boards sessions used the ESP32-S3 native USB-Serial-JTAG on COM4. On this
topology the host's VBUS is what powers the interface, so removing board power
also removes the COM port: the capture tool loses the handle exactly at the
moment the banner is printed, and the ROM banner is missed. Two workarounds,
either of which fixes the problem:

- **Preferred — a second, independently powered console.** Attach a USB-UART
  adapter to the module's UART0 TX/RX (GPIO43/44) and GND, powered from the
  host, and capture on that port. It stays alive while the DUT is unpowered and
  sees the full ROM banner plus `#CG BOOT`. This also finally closes `docs/06`
  item U12 (console path via the CH343G), which the G1 session had to leave
  unverified because CH343G never enumerated (`g1/SUMMARY.md` §G).
- **Alternative — switch only the board's 5 V supply** while USB data stays
  connected, so the MCU brown-outs to a true power-on while VBUS keeps the JTAG
  console enumerated. Requires knowing whether this board's ESP32 rail is fed
  from VBUS, from the XL4015 5 V, or both — which the repository does **not**
  record. If you choose this route, tell me how the module is powered and I will
  re-check it against `evidence/A/W01` before writing the procedure.

## 4. Minimum safe procedure — five cold boots (not yet authorized)

Prerequisites, all unpowered or non-energizing:

1. **Isolate the TEC branch physically**: pull slot 3 and switch the 12 V PSU
   off at the mains. The delivered firmware also refuses every enable at compile
   time, but the branch must be dead as a physical fact, not as a code promise.
2. **Back up the installed image before touching it** (this is what makes the
   session reversible): `esptool read-flash` of the full 4 MB to a file, plus its
   SHA-256, recorded in the dossier. Restore is `write-flash` of that same file,
   followed by a boot-banner identity check against the recorded hash.
3. Attach the second console from §3 and start a timestamped capture.
4. For each of five cycles: mains/USB power off ≥ 30 s, power on, capture until
   the first ten telemetry lines, then note the wall-clock time.
5. Each cycle must show `rst:0x1 (POWERON)`, `#CG BOOT boot_count` incrementing,
   and the first record with `tec_state=OFF output_stage=DISABLED pwm_duty=0
   fan_command=OFF fault_reason=BOOT_SAFE_OFF`.
6. Append the raw logs to `evidence/A/W04/` and re-run
   `cg_build_boot_default_off_csv.py`; the table then contains five genuine cold
   boots without any hand-edited row.

To test the **delivered** firmware rather than the H8 image, one extra step is
required first: flash `0acd230c…` (bootloader + partition table + app), which is
a physical action I will not start without your explicit go-ahead, and the same
backup from step 2 makes it undoable.

## 5. Minimum safe procedure — DMM pin levels (you have a meter)

Steady-state only, branch isolated, board powered from USB:

| Measurement | Expected | Probe points |
|---|---|---|
| GPIO5 → logic GND | 0.0 V | module pin header, not the IBT-2 side |
| GPIO6 (R_EN) → logic GND | 0.0 V | as above |
| GPIO10 (L_EN) → logic GND | 0.0 V | as above |
| IBT-2 B+ → PSU− | 0 V with slot 3 pulled | confirms the branch is dead |

Record each as a dated line in `evidence/A/W04/` with the meter model and its
DC-voltage range. **What a DMM cannot show**: it averages tens of milliseconds,
so it proves the steady state is low and says nothing about a microsecond boot
glitch. Any claim that "no transient ever appears on the enables" needs a scope
or logic analyzer, and this dossier will not make that claim from DMM readings.

## 6. What each completed step changes in the acceptance record

| Step closes | Effect |
|---|---|
| §4 five cold boots | A-W04-04 cold-boot half moves from NEED_USER_ACTION to VERIFIED |
| §5 DMM readings | adds the first pin-level default-OFF proof in the project's history |
| §3 second console | closes `docs/06` item U12 as a side effect |
| Flashing the delivered build then §4 | makes A-W04-04 evidence about the bytes this PR ships, instead of the 2026-10-29 build |
| §5 plus a scope, if you ever get one | the only way to claim anything about boot transients |

## 7. Standing constraints for this session

No TEC energization, no PWM change, no wiring modification, and no flash without
your explicit authorization for each. The seven authentic production resets
already in `boot-default-off.csv` are not repeated, and no H6/H7/H8 test is
re-run for this purpose.
