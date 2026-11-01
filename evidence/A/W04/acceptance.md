# W04 acceptance — Member A TEC commissioning

## 0. Metadata (`docs/05A` evidence block)

| Field | Value |
|---|---|
| Dossier date | 2026-11-01 |
| Bench sessions covered | 2026-10-29 (G0, G1, H6) |
| Operator | Member A (GitHub `giaback`), attended bench, per-session explicit authorization |
| `hardware_config_id` | `CG-HW-001` (device-emitted, `h6/03-w04-boot-before-flash.log`) |
| Firmware under review | the production tree delivered by this PR, based on `origin/main` `8b73da8` |
| Built image of that tree | `coldguard_firmware.bin` SHA-256 `0acd230c77698a83de7d124d53fe4f9df9965c68c4dd1a673da0ad20b240769e`, 244,496 bytes (`build-2026-11-01/`, rebuilt 2026-11-01 after the review wording edits) |
| H6 bench image (different program) | app SHA-256 `963f3cd623b8c8fade910adda723c0f178e7bc303528b63ed6520fd12110858d` (`h6/h6-image-hashes.txt`), source hashes `h6/h6-source-hashes.txt` |
| Test IDs | `A-W04-01`…`A-W04-07`, `ACT-H4-01..03`, `PWR-H5-01..03`, `THERM-H6-01/02`, `docs/06` gates G0–G3 |
| Overall result | **W04 PARTIAL — foundation delivered, output stage fail-closed, physical acceptance not met** |

## 1. Requirement status

| ID | Canonical ask | State | Evidence |
|---|---|---|---|
| A-W04-01 | Power path review | PARTIAL | `g0-electrical-verification.md`; the branch being de-energized is **inferred**, not measured — G0-1 is classified `INFERRED_ONLY` (`g0-electrical-verification.md:185-188`, verdict `SUY LUẬN` at `:393`) |
| A-W04-02 | Wiring class `2 × 2.5 mm²`, no PCT218/Dupont in the TEC path | **NOT VERIFIED** | the required class is recorded as `UNVERIFIED` for HW-19 (`g0-electrical-verification.md:331`, `evidence/A/W01/bom-audit.csv`) with no photo; the crimp actually used, FDD2-250 rated 1.5–2.5 mm² on 0.75 mm² wire, is out of range (`g0-electrical-verification.md:332-333`). Member A's later-week local bench notes report a 1.75 mm² conductor, but those files are excluded from this PR, so **no measured conductor class is claimed here** |
| A-W04-03 | Conservative defensible fuse choice | PARTIAL | the 15 A branch fuse being reinserted while unpowered is **operator-reported** (`h6/09-pzem-gate-pass.md:8`); the G0 dossier classifies the physical fuse-position check as `NOT_VERIFIED` and records it removed at that moment (`g0-electrical-verification.md:231-239,345-354`). No photo of label or position, and no measured selection basis. 15 A was **not** inferred from the `12715` marking |
| A-W04-04 | Default-OFF at boot/reset, 5 cold boots + 5 resets | PARTIAL | committed `g1/` captures show software-reported OFF, not a pin sweep: 62/62 telemetry rows carry `tec_state=OFF output_stage=DISABLED pwm_duty=0 fan_command=OFF` (`g1/42-telemetry.csv`), one controlled USB-JTAG reset with both boots SAFE_OFF (`g1/SUMMARY.md`, `g1/41-g1-reset.log`). No cold-boot × 5 + reset × 5 set and **no DMM/oscilloscope** measurement of GPIO5/6/10, which `g1/SUMMARY.md` §G itself declares |
| A-W04-05 | First conservative actuation, immediate stop on abnormal | DONE (electrical only) | one H6 run, PWM 10 %, guard-capped 60 s, 60/60 valid PZEM samples, peak 0.97 A / 11.3 W (modal 0.96 A / 11.2 W) at 11.71 V, automatic OFF `source=guard_timer reason=TIMEOUT elapsed_ms=60000`, outputs 0 after (`h6/40-h6-run.log:132-133`, `h6/41-h6-run-analysis.md` and its dated 2026-11-01 correction) |
| A-W04-06 | Polarity frozen with a record | **MISSING** | plan only (`h6-tec-polarity-test-plan.md`); the analysis states polarity rests on a qualitative touch observation and the verdict was held (`h6/41-h6-run-analysis.md`). No `H6_POLARITY_*` result, no photo |
| A-W04-07 | First response trace: command/applied, V/I/P, T1/T2/T3, time | PARTIAL | V/I/P/time/state present; **no thermal channels** — the H6 bench image does not read DS18B20/BME280, so no T1/T2/T3 in this trace |
| H4 (`ACT-H4-01..03`) | no unintended energization, no reverse | PARTIAL | refusal + default-OFF proven in host tests and in the idle polls; 5-boot/5-reset physical proof missing |
| H5 (`PWR-H5-01..03`) | branch fuse, conductor class, fan whenever TEC can energize | PARTIAL | fuse reinsertion operator-reported, not verified; conductor class unverified; the fan dependency is unproven — every committed telemetry row carries `fan_status=NOT_COMMANDABLE` (`g1/42-telemetry.csv`, 62/62) because CG-HW-001 has no tachometer feedback |
| H6 (`THERM-H6-01/02`) | conservative TEC response | PARTIAL | electrical response measured once; thermal response and polarity not evidenced |

## 2. Canonical W04 deliverables (`docs/05A` §W04)

| Deliverable | In this PR |
|---|---|
| `power-topology-v1.png` | MISSING — no diagram exists; G0 has a prose fuse-slot table only |
| `fuse-commissioning-note.md` | MISSING — fuse handling is scattered across `g0-electrical-verification.md` and `h6/09-pzem-gate-pass.md`, with no selection rationale |
| `boot-default-off.csv` | MISSING as a named deliverable — the dossier holds two CSVs (`g1/42-telemetry.csv`, `g1/42-ml.csv`) but neither is the 5-boot/5-reset default-OFF capture |
| `first-tec-trace.csv` | PARTIAL — the 60 s trace exists as raw serial log `h6/40-h6-run.log`, not as the named CSV |
| `first-tec-plot.png` | MISSING |
| `polarity-photo.md` | MISSING |

Three of the six physical checks above need an attended bench session; none can
be produced from the repository.

## 3. Verification executed for this delivery

| Check | Result | Where |
|---|---|---|
| Host suite `py firmware/tools/run_all_checks_w04.py` — 1 unittest run + 3 static checkers + 3 dossier validators | PASS 7/7 | `build-2026-11-01/30-host-suite-run.log`; unittest suite 185 tests today (2026-11-01: 179 from the 2026-10-29 pass + the W04 telemetry/state-machine tests + the two docs/06 disclosure mutation tests + the two network-token tests; `g1/50-unittest-verbose.log` ran 181, `g1/10-unittest-verbose.log` ran 179 on 2026-10-29) |
| W04 static contract checker | PASS | `g1/11-static-checks.log`, `g1/51-static-checks.log` |
| Negative/mutation tests for the checker | PASS | `g1/12-negative-tests.log`, `g1/52-negative-tests.log` |
| TEC state-machine harness against the real control core, 34 scenarios, fake backend | PASS (host compile + run) | `firmware/tools/tests/cg_tec_harness.c` driven by `tests/test_cg_tec_state_machine.py` |
| ESP-IDF v6.1 compile of the delivered `firmware/main` tree | PASS, `IDF_BUILD_OK` | `build-2026-11-01/20-idf-py-build.log`; source pin `build-2026-11-01/22-source-hashes.txt` (`sha256sum -c` from `firmware/`). `sdkconfig` is regenerated by `set-target`, so the image is compile-proven but not bit-reproducible from git alone |
| Flashing / energizing | **NOT RUN** — deliberately out of scope for a code delivery | — |
| Physical hardware acceptance of W04 | **NOT MET** — see §1 and §2 | — |

Three things were corrected as part of this delivery, all tooling or wording,
none changing firmware behaviour:

- `tests/test_cg_check_firmware_w04.py` pinned its mutation anchor to
  `#define CG_TELEMETRY_LINE_MAX 1536`, but the budget had already moved to
  2560, so the suite failed 1/181 and the W04 gate could not be reported GREEN.
  The anchor is now read from the shipped configuration instead of being
  hard-coded.
- `docs/06` used to state `PHYSICAL POWER TEST NOT YET AUTHORIZED` while the H6
  capture committed in this same PR shows a real 60 s energization. Its status
  block, gate ladder note and the coupled checker assertions now state the true
  split: production output stage unauthorized, supervised H6 bench energization
  already executed.
- `run_all_checks_w04.py` decoded child output as strict UTF-8; a Vietnamese
  evidence string emitted in the Windows codepage raised
  `UnicodeDecodeError` in the reader thread and the runner printed `[FAIL]` with
  **no** diagnostics. Children now run in UTF-8 mode and the decode is
  replace-tolerant, so a failure shows its reason.

The 2026-10-29 G1 build log predates five source edits (`cg_commission.c`,
`cg_log.c`, `coldguard_config.h`, and the two W04 test files), so it does **not**
prove the delivered bytes compile; `build-2026-11-01/` is the proof for this tree.

## 4. Open items this PR does not resolve

TEAM_DEPENDENCY — need project-level review, not Member A wording:

1. **T2 measurement semantics.** `docs/01` freezes T1/T2/T3 as chamber-air
   region measurements, while ROM `28AEBF2200000006` is used as hot-side
   protection in later bench reports. `evidence/A/W02/sensor-rom-map.yaml`
   still records that ROM as `position_semantics: center` with
   `physical_position_verified: false`. Changing the semantic requires updating
   `docs/01` first, per its change policy. The delivered firmware does **not**
   take a side: it emits `t_hot_side_c=NOT_ASSIGNED`.
2. **`docs/06` gate plan vs canonical W04 scope.** `docs/06` defers first
   actuation to a G3 that requires an interlock `docs/01` never mandated, while
   `docs/05A` W04 already asks for H4–H6 to pass. The reconciliation (which
   gates bind which bench) belongs to the team, not to this file.
3. **HW deviation register.** `TTL485-V2.0` instead of canonical `MAX3485`
   (CR-A-W01-01, still open), the unverified conductor class against
   `2 × 2.5 mm²`, the out-of-range crimp, and the extra `SPARE` DS18B20 (no
   canonical role exists for it) remain unfrozen.

Explicitly **not** claimed by this PR:

- W04 as a GREEN week, or H4/H5/H6 as complete.
- Any thermal cooling performance from the delivered code.
- A continuous TEC rating or a safe operating envelope (W08 work). The 10 A
  software ceiling belongs to the later H8 bench image, not to this firmware,
  whose seven limits are all `UNRESOLVED`.
- Any canonical H8 closed-loop result. Canonical H8 requires
  Controller A → command → ACK → electrical → thermal → verification
  (`docs/03` H8, shared A+C+D); an attended bench run with a local console does
  not satisfy it.
