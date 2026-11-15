# Supervised demo commissioning firmware (staging-ai-final-20261113)

Classification: **`SUPERVISED_DEMO_COMMISSIONING`** — `HARDWARE_BENCH_VERIFIED`
historically (live actuation), **NOT a production mode**.

This directory preserves, byte-for-byte, the exact firmware source that built
the **live-verified actuating image** used by the ColdGuard portable demo. It is
the hardware-working firmware the owner ran on physical hardware. It is included
in the release so the release can reproduce the verified hardware demo, while
the committed Member baseline firmware (`firmware/main/`, inert by design) is
preserved separately and unchanged.

## Provenance

| Item | Value |
| --- | --- |
| Source tree | `staging/` (224 files, complete ESP-IDF project) |
| Generator | `firmware/tools/leader_commissioning_build.py` (Leader-owned) |
| Generated | 2026-11-13T14:53:31Z |
| Verified image | `verified-image/coldguard_firmware.bin` |
| Image SHA-256 | `def89390f102fe248eb177d9a8349b9e297e7413cc928d3896892f0aeebf5623` |
| Live evidence | supervised TEC1000, measured **7.91 A** on 2026-11-13 |
| Source manifest | `manifest.json` — 223 file hashes, all verified matching `staging/` |
| Config patch | `staging-config.diff` (member baseline → commissioning) |
| Build log | `build.log`, `build-log.txt` |

The same firmware logic ships in the portable demo package
(`ColdGuard-Demo-Portable/APP/tec100-demo/firmware`): `cg_tec_control.c`,
`cg_commission.c`, `cg_tec_platform.h`, `cg_leader_ingress.c`,
`cg_leader_tec_hw.c` are byte-identical to this staging source. The demo package
ships the source with baseline gates OFF and applies the commissioning toggles at
build time; this staging tree is the commissioning-applied source.

## What makes it actuate (commissioning gates)

The member baseline is inert (`CG_ACTUATOR_ENABLE_ALLOWED=0`,
`CG_TEC_OUTPUT_STAGE_ENABLED=0`, `CG_TEC_HARDWARE_GATES_VERIFIED=0`). This
commissioning source sets, in `staging/main/coldguard_config.h`:

- `CG_ACTUATOR_ENABLE_ALLOWED=1`
- `CG_TEC_OUTPUT_STAGE_ENABLED=1`
- `CG_TEC_HARDWARE_GATES_VERIFIED=1`
- `CG_DOOR_POLARITY_CONFIRMED=1`, `CG_DOOR_RAW_OPEN_LEVEL=1` (owner live
  observation 2026-11-13: raw 1 = OPEN, raw 0 = CLOSED).

These are **deliberate commissioning decisions that require recorded gate
evidence, not build tweaks**. They are justified by the historical H8 supervised
bench (A–E) and the 2026-11-13 live TEC1000 session, not by a production
certification.

As-built actuator route (H8_DUAL_ENABLE, paired-enable):
`R_EN=GPIO6`, `L_EN=GPIO10`, `RPWM=GPIO5` (1000 Hz, 13-bit), `LPWM=GND`. Both
enables are driven together; mixed enables are refused. T2 is the TEC hot-side
probe (ROM `28AEBF2200000006`).

`SUPERVISED_NO_COLD_PROBE`: the real hardware has **no cold-side probe fitted**
(`cold_probe_fitted=false`). Only the cold-presence check is omitted; the hot
input, PZEM, freshness, interlock/fan, heartbeat and the supervised envelope all
stay in force.

## Supervised envelope (NOT a certified rating)

Owner-proposed single-session TEC1000 envelope (2026-11-13): 1000 permille,
CONTINUOUS until operator STOP/fault (the 30 s timed-command cap is metadata
only), 10.0 A stop, 40.0 C T2 stop, 10.0–13.2 V. The 10.0 A ceiling is a
supervisory demo limit observed at 9.99 A peak — **not a continuous rating and
not an instantaneous-current guarantee**. No cold-performance, freeze,
G3-acceptance or COP claim is made.

## Reproduction

`staging/` is a complete, self-contained ESP-IDF project (with `sdkconfig`).
Build it with ESP-IDF 6.1 (`idf.py build`) to produce the commissioning image.
`manifest.json` records the exact source hashes; `staging-config.diff` records
the config patch from the member baseline. The preserved
`verified-image/coldguard_firmware.bin` is the historical live-verified binary
for provenance comparison.

> Note: `leader_commissioning_build.py` stages from a member tree that already
> contains the paired-enable + Leader ingress/tec-hw logic and applies the
> commissioning toggles. Run against the inert committed baseline alone it does
> not reproduce this image; this staging tree is the canonical verified source.

## Safety boundary

- This is a **supervised demo** commissioning config, not production firmware.
- Host-side authority is unchanged: ARM defaults OFF, START requires explicit
  operator authorization, boot-scoped admission, correlated ACK and a bounded
  session. Including this source does **not** auto-energize anything.
- Physical actuation requires separate operator authorization + physical
  prechecks (fuse, wiring, PZEM current monitoring, attended bench). On zero or
  abnormal current: STOP, preserve the latch, no auto retry.
- The release makes **no claim of physical end-to-end verification of the release
  stack**; the 7.91 A evidence is the historical 2026-11-13 demo session on this
  image. See `docs/leader-integration/hardware-baseline.md`.