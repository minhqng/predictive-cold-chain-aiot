# Boot / reset default-OFF evidence — A-W04-04

`boot-default-off.csv` is generated from every ROM-bootloader banner found in the
existing captures — 101 `.log` files across the W02 session, the production G1
session, the H6, H7 and H8 bench trees and the 2026-10-29 scratch copies — by
`firmware/tools/cg_build_boot_default_off_csv.py`. It parses **132 banners** and
merges identical captures held in more than one working copy, giving **116
unique start events**, each with its reset cause, image, first device record
after the banner, evidence level and the list of duplicate copies. Nothing is aggregated or inferred: a field
an image does not emit stays empty.

## 1. What the corpus actually contains

| Start kind | Count | Images |
|---|---|---|
| **Genuine cold boot (`rst:0x1 POWERON`)** | **0** | none — no capture anywhere in any session shows a power-on banner |
| USB-JTAG chip reset (`rst:0x15 USB_UART_CHIP_RESET`) | 63 | `cg-w04-0.1.0` ×7, `h6-bench` ×3, `h7-bench` ×15, `h8-bench` ×32, `cg-w02` ×6 |
| Software reset / panic restart (`rst:0xc RTC_SW_CPU_RESET`) | 53 | `h8-bench` ×53 |
| Watchdog (`rst:0xd`) or brownout (`rst:0x9`) banner | 0 | none present |

Events with a device-reported OFF record after the banner: 31 (7 production,
3 H6, 15 H7, 6 H8). Events where PZEM branch current was actually live during
the start: **0** — in every boot capture the 12 V branch was off, so current
reads `nan`/`NO_DATA`/`INVALID`, which is a transport fact, not a zero-current
measurement. Pin-level (DMM or oscilloscope) default-OFF measurements: **0** —
no such record exists in any file, and the board has no usable RST button, which
is why the resets that do exist are USB-JTAG ones.

## 2. What that closes for A-W04-04

The canonical ask is "5 cold boots / 5 resets" with no unintended active-branch
current, and the delivered firmware's default-OFF claim rests on three things
that are already proven:

- on all 7 unique production `cg-w04-0.1.0` starts the first telemetry frame reports
  `tec_state=OFF`, `output_stage=DISABLED`, `pwm_duty=0`, `fan_command=OFF`,
  `fault_reason=BOOT_SAFE_OFF`;
- the ARM token is regenerated per boot, so a pre-boot authorization can never
  survive a restart (proven in the 34-scenario host harness and the negative
  tests);
- the output stage is compiled out and the adapter refuses every enable, so no
  boot sequence has a path to energize the branch.

Against the canonical wording, the **reset half is satisfied** (7 unique
authentic resets on the delivered source, ≥ 5 required). Two parts are not met
by existing data and cannot be met by re-reading it:

1. **5 genuine POWER_ON cold boots.** Zero exist. Every captured start is a
   USB-JTAG or software reset. A power-on banner only appears if the board loses
   power entirely (USB removed or mains off), which no session did.
2. **Pin-level evidence that RPWM/R_EN/L_EN are low at boot.** The device's own
   `rpwm_level` readback is explicitly not proof — `h6/04-post-flash-verification.md:92`
   says it reads the pin's input side. A DMM or scope on GPIO5/GPIO6/GPIO10 is
   the only way to close it.

There is also a provenance limit worth stating, reconstructed from the flash
logs rather than assumed: the binary that produced those 7 events is the
2026-10-29 production build. The board was later flashed with the H6, H7 and then
H8 images, and the last recorded flash (2026-10-31, H8 T2 HOT_SIDE `01cedce3…`)
is what is on the hardware today. The delivered image (`0acd230c…`) is
compile-only and has never run on hardware. The source difference is comment and
tooling text only, but that is an argument, not a measurement.

## 3. Minimum additional evidence that would close A-W04-04

The executable version of this list, with branch isolation, the full-flash backup
and restore step, the second-console workaround for the native USB port dropping
during power removal, and the standing authorization gates, is in
`w04-physical-verification-plan.md`.

| Need | Action | Risk |
|---|---|---|
| 5 × `rst:0x1 (POWERON)` banners on the installed production build | unplug USB (or switch the PSU off) for ≥ 30 s, reconnect, with the serial capture running — five times | none to the TEC branch: the firmware cannot drive outputs, and the branch fuse can additionally be pulled so the branch is physically dead |
| pin-level LOW at boot | DMM continuity/voltage on GPIO5, GPIO6, GPIO10 against GND during a cold boot; a scope is better but not required | unpowered measurement |
| boots on the delivered binary | flash `0acd230c…` and repeat | a flashing operation, needs explicit operator authorization |

None of the three is a repeat of a completed test: the cold-boot set and the
pin-level check have never been performed in any session, and the delivered
binary has never run on hardware.
