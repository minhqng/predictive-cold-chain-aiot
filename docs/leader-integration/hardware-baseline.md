# Hardware baseline ledger

This ledger records what was actually verified on physical ColdGuard hardware,
what was verified only in software, and what remains unverified on the final
release. It exists so the release never implies a combined physical acceptance
that the evidence does not support.

Classification vocabulary used below:

- `HARDWARE_BENCH_VERIFIED` — observed on real ESP32/PZEM/TEC hardware.
- `SOFTWARE_TESTED` — builds or runs, but no physical observation.
- `INTEGRATION_OFFLINE_VERIFIED` — unit/integration/regression/shadow tests pass.
- `SHADOW_ONLY_VERIFIED` — decisions computed offline, zero physical dispatch.
- `PHYSICAL_END_TO_END_NOT_RUN` — no combined physical trial of this release.
- `NOT_PROVEN` — claimed nowhere; needs evidence that does not exist yet.

## 1. Release firmware identity

| Item | Value |
| --- | --- |
| Release branch | `leader/release/coldguard-final` |
| Release checkpoint | `b65889fdca658100e346c4ad5725ff97269ca12a` |
| Main baseline | `557e887432d1a72b3d097f92644fe72b809c824e` |
| Firmware target | ESP32-S3 |
| Build toolchain | ESP-IDF 6.1 |
| Built app SHA-256 | `f6c45179f5bfdae44f39e935e9cee36b5ce2f325c5bd57f6ba4c1e670bd0fa2` |
| Build evidence | `C:/cgb/demo-out/final-release-20261115/firmware-build.log` |
| Build verdict | `SOFTWARE_TESTED` (build exit 0; image generated; **not flashed**) |

The build above is of the **committed** `b65889f` Member firmware tree. It does
**not** include the uncommitted Leader firmware components or the uncommitted
Member A working-tree diffs described in section 4. Those are excluded from the
release commits and preserved in the worktree pending physical validation.

## 2. What was physically tested (historical bench)

These are `HARDWARE_BENCH_VERIFIED` on **historical** images, not on the release
image. Each is separate evidence; none proves the release stack ran together.

| Capability | Evidence location | Notes |
| --- | --- | --- |
| BME280 environmental bench | `evidence/A/W02/bme280/bme280-bench-report.md` | sensor characterization |
| MC-38 door bench | `evidence/A/W02/mc38/mc38-bench-report.md` | raw 1 = OPEN, raw 0 = CLOSED |
| Fuse / commissioning note | `evidence/A/W04/fuse-commissioning-note.md` | electrical safety |
| W06 demo command capture | `evidence/A/W06/demo-command-capture.log` | command path trace |
| H8 supervised bench A–E | `evidence/A/RC/acceptance-run/member-a-acceptance.md` | IBT-2 paired-enable load-current path; T2 hot-side ROM `28AEBF2200000006` |

Historical bench image lineage (from prior commissioning records):
`01cedce3` (H8) → `39c76c6d` (2026-11-07) → `73968c19` (W06 integrated).
The as-built IBT-2 requires both enables (R_EN + L_EN) for the H8-verified
load-current path; T2 is the TEC hot-side probe. These facts are
`HARDWARE_BENCH_VERIFIED` historically and are the reason the preserved Member A
firmware semantics must not be redesigned without hardware evidence.

## 3. What was NOT tested on this release

- `PHYSICAL_END_TO_END_NOT_RUN` — the release firmware + Vietnamese Dashboard +
  Leader gateway were **not** run together on physical hardware. Hardware is
  unavailable; no flashing, COM4 access, ARM/START, PSU operation or
  commissioning was authorized or performed for this release.
- `PHYSICAL_END_TO_END_NOT_RUN` — AI-driven closed-loop physical TEC control.
  Historical TEC bench success is **not** equivalent to AI end-to-end control.
- `NOT_PROVEN` — AI improved electrical efficiency.
- `NOT_PROVEN` — XGBoost production-ready prediction (persistence beat the
  experimental model on holdout; the forecast is experimental demo only).
- `NOT_PROVEN` — cold-face temperature (no cold-side probe is fitted).
- `NOT_PROVEN` — runtime image safety limits beyond the historical bench record.

## 4. Included commissioning firmware (Leader decision 2026-11-15)

The release **includes** the verified hardware-working firmware as a distinct,
labelled artifact: `firmware/commissioning/staging-ai-final-20261113/`
(`SUPERVISED_DEMO_COMMISSIONING`, **not production**). This is the exact source
that built the live-verified actuating image, preserved byte-for-byte:

| Item | Value |
| --- | --- |
| Verified image SHA-256 | `def89390f102fe248eb177d9a8349b9e297e7413cc928d3896892f0aeebf5623` |
| Live actuation evidence | supervised TEC1000, measured **7.91 A** on 2026-11-13 |
| Source manifest | 223 file hashes, all verified matching the committed source |
| Commissioning gates | `CG_ACTUATOR_ENABLE_ALLOWED=1`, `CG_TEC_OUTPUT_STAGE_ENABLED=1`, `CG_TEC_HARDWARE_GATES_VERIFIED=1`, door polarity confirmed |
| Actuator route | H8_DUAL_ENABLE paired-enable (R_EN=GPIO6, L_EN=GPIO10, RPWM=GPIO5) |
| Cold probe | NOT FITTED (`SUPERVISED_NO_COLD_PROBE`); only the cold-presence check omitted |

This is the same firmware logic as the portable demo package
(`tec100-demo`); the staging tree is the commissioning-applied source. It is
`HARDWARE_BENCH_VERIFIED` **historically** (the 2026-11-13 live session on this
image). Including it does **not** auto-energize anything: host ARM defaults OFF
and physical actuation still requires separate operator authorization +
prechecks. The release stack end-to-end on hardware remains
`PHYSICAL_END_TO_END_NOT_RUN`. Full provenance and reproduction:
`firmware/commissioning/staging-ai-final-20261113/README.md`.

## 4b. Hardware-facing work still preserved, not released

The following **diverged** worktree changes remain **excluded** from the release
commits (they differ from the verified commissioning source above and were not
re-verified on hardware). They are `REQUIRES_PHYSICAL_VALIDATION`:

- Member A working-tree diffs: `firmware/main/cg_commission.c`,
  `cg_tec_control.c` / `cg_tec_control.h`, `cg_tec_platform.h` (a diverged
  paired-enable variant, not byte-identical to the verified staging source).
- Coupled Member A harness diffs: `firmware/tools/tests/cg_tec_harness.c`,
  `test_cg_tec_state_machine.py`, `firmware/tools/cg_check_firmware_w04.py`.
- Diverged worktree Leader components `firmware/components/cg_leader_ingress/`,
  `cg_leader_tec_hw/` and the Leader host harnesses under `firmware/tools/tests/`
  (coupled to the diverged worktree sources).

The host harness tests require a host C compiler that is unavailable in this
environment, so they are `NOT RUN` offline. The verified firmware is preserved
in the commissioning artifact (section 4), not in these diverged worktree files.

## 5. Confidence and limitations

- The release is a **software integration** release. Its backend, dashboard,
  shadow control and inference display are `INTEGRATION_OFFLINE_VERIFIED`
  (backend 857 pass / 94 skip / 0 fail with disposable PostgreSQL; Member D
  control 770 pass; Member B ML focused 57 pass).
- The release also **preserves the verified hardware-working commissioning
  firmware** (section 4, `SUPERVISED_DEMO_COMMISSIONING`, image `def89390`,
  7.91 A live on 2026-11-13) so the hardware demo can be reproduced. This is
  historical bench evidence on that image, not a release-stack physical trial.
- Physical control authority remains with Member D and the Leader orchestrator
  behind the existing boot-scoped admission. Shadow mode dispatches nothing.
- Do not infer a combined physical acceptance from the separate bench records.
  Hardware validation is still required before any physical deployment.