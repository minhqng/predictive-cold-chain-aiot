# W04 acceptance — Member A TEC commissioning

## 0. Metadata (`docs/05A` evidence block)

| Field | Value |
|---|---|
| Dossier date | 2026-11-01, extended 2026-11-02 |
| Bench sessions covered | 2026-10-29 (G0, G1, H6); 2026-11-01 box-cooling run cross-referenced as later-week data |
| Operator | Member A (GitHub `giaback`), attended bench, per-session explicit authorization |
| `hardware_config_id` | `CG-HW-001` (device-emitted, `h6/03-w04-boot-before-flash.log`) |
| Firmware under review | the production tree delivered by this PR, based on `origin/main` `8b73da8` |
| Built image of that tree | `coldguard_firmware.bin` SHA-256 `0acd230c77698a83de7d124d53fe4f9df9965c68c4dd1a673da0ad20b240769e`, 244,496 bytes (`build-2026-11-01/`, rebuilt 2026-11-01 after the review wording edits; compile-only, never flashed) |
| H6 bench image (different program) | app SHA-256 `963f3cd623b8c8fade910adda723c0f178e7bc303528b63ed6520fd12110858d` (`h6/h6-image-hashes.txt`), source hashes `h6/h6-source-hashes.txt` |
| Test IDs | `A-W04-01`…`A-W04-07`, `ACT-H4-01..03`, `PWR-H5-01..03`, `THERM-H6-01/02`, `docs/06` gates G0–G3 |
| Operator statements recorded 2026-11-02 | branch fuse **installed, 15 A** (label photo pending); TEC branch conductor **1.75 mm²**; TEC cold block inside the box with hot block and fan outside; T1 `287088CA…`, T3 `28CBE9CA…`, SPARE `283BE5C9…` and the BME280 in inside-box air; T2 `28AEBF22…` attached to the hot block. Recorded as statements: none of these is photographed or independently measured in this repository |
| Overall result | **W04 PARTIAL — foundation delivered and all six canonical deliverable files now exist; physical acceptance not met** |

## 1. Requirement status

| ID | Canonical ask | State | Evidence |
|---|---|---|---|
| A-W04-01 | Power path review | PARTIAL | `g0-electrical-verification.md`, drawn as `power-topology-v1.png` with a per-link evidence class; branch de-energized is **inferred**, not measured (`g0…:185-188` `INFERRED_ONLY`, verdict `SUY LUẬN` at `:393`), and the `PSU+ → IBT-2 B+` bypass check is still open (`g0…:251` `NOT_VERIFIED`) |
| A-W04-02 | Wiring class `2 × 2.5 mm²`, no PCT218/Dupont in the TEC path | **DEVIATION — change review raised** | conductor is 1.75 mm² per the operator statement of 2026-11-02; the repository record still says HW-19 `UNVERIFIED` with no photo (`g0…:331`, `evidence/A/W01/bom-audit.csv:20`). FDD2-250 (1.5–2.5 mm²) is in range for 1.75 mm²; the out-of-range case is the same terminal on 0.75 mm² auxiliary wire (HW-20), a different circuit. Raised as `change-review-request-CR-A-W04-02.md`; **not accepted by Member A** |
| A-W04-03 | Conservative defensible fuse choice | PARTIAL — **not frozen** | `fuse-commissioning-note.md`. 15 A installed (operator 2026-11-02, label photo pending); reinsertion is operator-reported (`h6/09-pzem-gate-pass.md:8`) and the G0 position check is `NOT_VERIFIED` (`g0…:231-239,345-354`); no marking of any kind is recorded anywhere (`evidence/A/W01/photos/07-fusebox.jpg`). A rating cannot be frozen until the conductor's installed ampacity is known |
| A-W04-04 | Default-OFF at boot/reset, 5 cold boots + 5 resets | PARTIAL — reset half satisfied, cold-boot and pin halves impossible from existing data | `boot-default-off.csv`, built by `firmware/tools/cg_build_boot_default_off_csv.py` from 101 raw captures: **132 ROM banners deduplicated to 116 unique start events** (16 events existed as identical captures in more than one working copy). **7 unique resets on the delivered `cg-w04-0.1.0`**, all seven reporting `tec_state=OFF output_stage=DISABLED pwm_duty=0 fan_command=OFF fault_reason=BOOT_SAFE_OFF`; **0 genuine `rst:0x1 POWERON` events in any session**; **0 pin-level DMM/scope records**; PZEM current was never live during any start (branch PSU off), so no boot has ever been shown to draw no branch current with the branch energized |
| A-W04-05 | First conservative actuation, immediate stop on abnormal | DONE (electrical only) | one H6 run, PWM 10 %, guard-capped 60 s, 60/60 valid PZEM samples, peak 0.97 A / 11.3 W (modal 0.96 A / 11.2 W) at 11.71 V, automatic OFF `source=guard_timer reason=TIMEOUT elapsed_ms=60000`, outputs 0 after (`h6/40-h6-run.log:132-133`, `h6/41-h6-run-analysis.md` plus its dated 2026-11-01 correction) |
| A-W04-06 | Polarity frozen with a record | PARTIAL — direction recorded against the stated placement, photograph missing | `polarity-photo.md`: no reverse path exists in code (`cg_tec_hw.c:28-41`, `cg_tec_platform.h`); **conditional on the operator-stated placement**, the 2026-11-01 cross-week measurement (H8 image, 100 % duty) is consistent with pumping from the inside face to the outside face — the four inside channels fell 7.75–9.25 K while the hot-side channel rose 9.69 K to a 39.938 °C peak. The measurement cannot itself establish the placement, so without a photograph there is no canonical freeze |
| A-W04-07 | First response trace: command/applied, V/I/P, T1/T2/T3, time | PARTIAL | `h6/first-tec-trace.csv` + `h6/first-tec-plot.png` carry command, applied state, V/I/P and time; **no thermal channels**, because the H6 bench image reads no DS18B20/BME280. Thermal response exists only in the cross-week `tec-cooling-response-600s.csv/.png` (100 % duty, H8 image), which is labelled as such and is not a conservative W04 trace |
| H4 (`ACT-H4-01..03`) | no unintended energization, no reverse | PARTIAL | refusal and default-OFF proven in host tests, in the 34-scenario harness and in 7 unique production resets; the physical 5-cold-boot set and pin-level proof do not exist |
| H5 (`PWR-H5-01..03`) | branch fuse, conductor class, fan whenever TEC can energize | PARTIAL | fuse installed but unverified and unfrozen; conductor class is a deviation; fan dependency unproven — `fan_status=NOT_COMMANDABLE` in all 62 committed G1 telemetry rows, CG-HW-001 has no tachometer feedback |
| H6 (`THERM-H6-01/02`) | conservative TEC response | PARTIAL | conservative electrical response measured once; conservative thermal response and a polarity photograph not evidenced |

## 2. Canonical W04 deliverables (`docs/05A` §W04)

| Deliverable | Now in this PR |
|---|---|
| `power-topology-v1.png` | **present** — generated by `tools/render_power_topology.ps1` from an explicit node/edge list; every link carries its evidence class and the one unverified link is drawn dashed rather than omitted |
| `fuse-commissioning-note.md` | **present** — states the demand, the installed fuse, the conductor dependency and the decision table; deliberately does **not** freeze a rating |
| `boot-default-off.csv` | **present** — 116 unique start events (132 banners, duplicate captures merged) classified by reset cause, image and evidence level; 7 production resets, zero power-on boots, zero pin-level readings |
| `first-tec-trace.csv` | **present** — derived from the raw H6 capture by `firmware/tools/cg_build_h6_trace_csv.py`, which refuses to emit unless the session is clean |
| `first-tec-plot.png` | **present** — rendered from that CSV; peak and mean are recomputed onto the figure |
| `polarity-photo.md` | **present as a record, not as a photograph** — documents the confirmed orientation, the code-level no-reverse guarantee and the measured gradient direction, and lists the two exact photographs that would close it |

## 3. Verification executed for this delivery

| Check | Result | Where |
|---|---|---|
| Host suite `py firmware/tools/run_all_checks_w04.py` — 1 unittest run + 3 static checkers + 3 dossier validators | PASS 7/7 | `build-2026-11-01/30-host-suite-run.log`; 185 unittest tests (179 on the 2026-10-29 first pass, 181 after the W04 tests, 185 after the disclosure and network-token mutation tests) |
| W04 static contract checker | PASS, 131 contracts | `g1/11-static-checks.log`, `g1/51-static-checks.log` |
| Negative/mutation tests for the checker | PASS | `g1/12-negative-tests.log`, `g1/52-negative-tests.log` |
| TEC state-machine harness against the real control core, 34 scenarios, fake backend | PASS (host compile + run) | `firmware/tools/tests/cg_tec_harness.c` via `tests/test_cg_tec_state_machine.py` |
| ESP-IDF v6.1 compile of the delivered `firmware/main` tree | PASS, `IDF_BUILD_OK` | `build-2026-11-01/20-idf-py-build.log`; source pin `22-source-hashes.txt` (`sha256sum -c` from `firmware/`). `sdkconfig` is regenerated by `set-target`, so the image is compile-proven but not bit-reproducible from git alone |
| Derived-artifact reproducibility | PASS for in-git sources, PARTIAL for one file | `cg_build_h6_trace_csv.py`, `cg_build_boot_default_off_csv.py`, `cg_build_cooling_trace_csv.py` and the two `tools/*.ps1` renderers regenerate every CSV and PNG here. From a clean checkout you can reproduce `h6/first-tec-trace.csv` and both figures; `boot-default-off.csv` needs Member A's local H7/H8 trees for its later-week rows, and `tec-cooling-response-600s.csv` cannot be regenerated from git alone because its raw `samples.jsonl` stays local and is pinned by hash only (`ARTIFACT-MANIFEST.md` §2.2) |
| Flashing / energizing | **NOT RUN** — deliberately out of scope | — |
| Physical hardware acceptance of W04 | **NOT MET** — see §1, §4 | — |

Corrections made as part of this delivery, all tooling or wording, none changing firmware behaviour:

- `tests/test_cg_check_firmware_w04.py` pinned a mutation anchor to
  `#define CG_TELEMETRY_LINE_MAX 1536` while the shipped value is 2560, so the
  suite failed 1/181; the anchor is now read from the configuration.
- `docs/06` used to state `PHYSICAL POWER TEST NOT YET AUTHORIZED` while the H6
  capture committed beside it shows a real 60 s energization; its status block,
  gate-ladder note and the coupled checker assertions now state the true split.
- `run_all_checks_w04.py` decoded child output as strict UTF-8, so one
  Vietnamese evidence string raised `UnicodeDecodeError` and printed `[FAIL]`
  with no diagnostics; children now run in UTF-8 mode.
- `h6/41-h6-run-analysis.md` frame tally corrected by appended dated note
  (61 `class=OK` + 1 `ECHO_ONLY`, not 60 + 2); the 2026-10-29 text is untouched.
- The 2026-10-29 G1 build log predates five source edits and therefore does not
  prove the delivered bytes compile; `build-2026-11-01/` is that proof.

## 4. Open items this PR does not resolve

TEAM_DEPENDENCY — project-level review, not Member A wording:

1. **T2 measurement semantics** — written up as
   `change-review-request-CR-A-W04-01.md`. `docs/01` freezes T1/T2/T3 as
   chamber air; the operator and the device's own `t2_role=HOT_SIDE` frames say
   ROM `28AEBF2200000006` sits on the hot block. The delivered firmware takes no
   side (`t_hot_side_c=NOT_ASSIGNED`) and hot-side protection is preserved in
   every option.
2. **Conductor class deviation** — `change-review-request-CR-A-W04-02.md`;
   blocks any fuse freeze and blocks W08's envelope work.
3. **`docs/06` gate plan vs canonical W04 scope** — the G3 interlock is a Member
   A precondition, not a canonical requirement, while `docs/05A` W04 asks for
   H4–H6 to pass.
4. **HW deviation register** — `TTL485-V2.0` vs canonical `MAX3485`
   (CR-A-W01-01, still open) and the extra `SPARE` DS18B20 with no canonical role.

NEED_USER_INPUT / NEED_USER_ACTION, with the exact minimum in
`boot-default-off-note.md` §3 and `polarity-photo.md` §5:

- five genuine `POWER_ON` cold boots on the installed production build;
- one DMM or scope reading of GPIO5/GPIO6/GPIO10 during a cold boot;
- a photograph of the installed fuse label and of the branch conductor marking;
- two photographs of the TEC blocks and probe tips to make the polarity record
  photo-verified;
- the open unpowered G0 continuity check `PSU+ → IBT-2 B+`.

Explicitly **not** claimed by this PR:

- W04 as a GREEN week, or H4/H5/H6 as complete.
- Any thermal cooling performance produced by the delivered code.
- A continuous TEC rating or safe operating envelope (W08). The 10 A software
  ceiling belongs to the later H8 bench image; the seven limits delivered here
  are all `UNRESOLVED`.
- Any canonical H8 closed-loop result. Canonical H8 needs Controller A →
  command → ACK → electrical → thermal → verification (`docs/03`, shared A+C+D);
  an attended bench run on a local console does not satisfy it.
- That the operator statements of 2026-11-02 are photographs or measurements.
  They are recorded as statements until the images exist.
