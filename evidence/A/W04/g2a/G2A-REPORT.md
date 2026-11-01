# ColdGuard W04 — G2-A Physical Probe Identification & Safety Limit Audit

Date: 2026-10-29
Mode: BUILD (hardware-safe verification, TEC branch isolated throughout)
Result: **G2-A PARTIAL**

Evidence bundle (all local, uncommitted): `_w04-g2a-evidence/`

| File | Content |
|---|---|
| `10-probe-warm-session.log` | raw console, boot_count 23, 480 s, 480 TELEM frames |
| `11-probe-warm-session-2.log` | raw console, boot_count 24, 241 s, 241 TELEM frames |
| `20-probe-identification.md` | stimulus test method, rounds, transients, safety counts |
| `21-placement-plan.md` | role semantics, placement plan, cold/hot-side gap, SPARE proposal |
| `22-six-limit-audit.md` | per-limit audit, evidence inventory, verdicts |
| `tools/g2a_capture.py` | host capture tool (opens COM4 without pulsing DTR/RTS) |

Safety state during the whole task: 12 V PSU OFF and disconnected, 15 A branch fuse
still removed, no TEC ON, no PWM, no actuation-gate change, no GPIO change, no
reflash. 721/721 TELEM frames reported `output_stage=DISABLED`, `pwm_duty=0`,
`tec_state=OFF`, `fault_code=0x00000000`.

---

## A. Exact firmware / source identity

| Item | Value |
|---|---|
| Worktree | `A-W04-tec-commissioning` |
| Branch / HEAD | `feat/a-w04-tec-commissioning-foundation` / `0d350a57874d53f9b48bfd6b639eae0f50e6f450` |
| Pre-existing W04 changes | no tracked file modified; only the untracked `_w04-g2a-evidence/` was added; HEAD and branch unchanged |
| `firmware_version` | `cg-w04-0.1.0` |
| `hardware_config_id` | `CG-HW-001` |
| ESP-IDF / target | ESP-IDF v6.1, `esp32s3` |
| App compile time | `Oct 29 2026 18:03:49` (bootloader `18:04:23`) |
| `coldguard_firmware.bin` SHA-256 | `39dd8332442fc45d394e70a41b7c7fac3bd16e2383a92f8f44cf085c4b15e299` |
| `coldguard_firmware.elf` SHA-256 | `73a7b9e7dcee89d4066cff79e865c619b503c33fe5e5bcc12a2e396e873566f2` |
| Bootloader / partition SHA-256 | `b1aeaf744710bc1aa533c7ac428f814cd8ba8469fd304585cd344e1fa52aef94` / `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` |
| Flashed target | ESP32-S3 (QFN56) rev v0.2, MAC `e0:72:a1:bc:cf:4c`, COM4 native USB-Serial/JTAG |
| Flash provenance | esptool v5.6.0; per-segment "Hash of data verified"; no erase-flash |
| Boot identity in captures | boot_id `e1c19658` / boot_count 23; boot_id `42b5bb00` / boot_count 24 |

Identity chain: the ELF SHA-256 printed by the ROM/app boot line in the G1 capture
(`73a7b9e7d…`) equals the SHA-256 of the built ELF in
`_w04-g1-evidence/fw-build/firmware/build/`, so the image under test is the image
built from this source tree (including the TWDT fix in `cg_commission.c`, mtime
18:14:45, older than the 18:15:59 binary).

Nothing was rebuilt, reflashed, edited or committed during G2-A. No safety constant
was touched: `CG_ACTUATOR_ENABLE_ALLOWED=0`, `CG_TEC_OUTPUT_STAGE_ENABLED=0`,
`CG_TEC_HARDWARE_GATES_VERIFIED=0`, `CG_TEC_REQUEST_DUTY_PERMILLE=0`, and all six
limits still `UNRESOLVED`.

---

## B. Four ROMs and physical-probe identification evidence

Expected and observed mapping (read-only; canonical files untouched):

| Role | ROM code | Bus presence | Stimulus result | Identity status |
|---|---|---|---|---|
| T1 | `287088CA00000051` | present, `status=OK` | round 3: **+2.875 °C**, others 0.00 | **STIMULUS-VERIFIED** |
| T2 | `28AEBF2200000006` | present, `status=OK` | round 1: **+2.750 °C**, others ≤0.125 | **STIMULUS-VERIFIED** |
| T3 | `28CBE9CA00000072` | present, `status=OK` | round 2: **+3.188 °C**, others ≤0.44 (decay from round 1) | **STIMULUS-VERIFIED** |
| SPARE | `283BE5C9000000A9` | present, `status=OK` | round 4 paused by operator | **UNCONFIRMED_BY_STIMULUS** (present and reading; exclusion-only) |

Method: stable baseline from 10 consecutive `#CG TELEM` frames; the operator warmed
exactly one physically distinguishable probe between fingers for 10–15 s (no hot air,
flame, water, powered heater, no TEC); identification came from which `raw_t*_c`
channel rose in the actual 1 Hz telemetry, not from enumeration order; probes were
allowed to settle between rounds. The ROM→role map was only read afterwards for
confirmation and was not modified.

Concurrent findings:

- All four probes were continuously available and plausible (29.2–32.6 °C) except two
  one-sample `CRC_FAIL` events during cable handling (host +166.3 s T3/SPARE,
  +353.3 s T2). Firmware reported `DEGRADED` for one sample and recovered; no value
  was fabricated.
- One reset occurred between the two captures (boot 23→24, boot_id change) caused by
  closing the first serial handle (DTR/RTS deassertion), not by firmware; the first
  post-reset frame was `tec_state=OFF`, `output_stage=DISABLED`, `fault_code=0`.

Detailed numbers: `20-probe-identification.md`.

---

## C. Physical role and placement status

| Item | Status |
|---|---|
| T1 = near-door, T2 = center (`t_inside_c` source), T3 = far/opposite | contract semantics fixed (docs/01 §6.4); firmware map unchanged |
| SPARE | unassigned (`assigned_role: null`), PHY-DS-002 forbids implicit substitution |
| Physical labels | **NOT APPLIED** — `physical_label: PENDING` in `evidence/A/W02/sensor-rom-map.yaml` |
| Mounting positions | **NOT VERIFIED** — no photos, coordinates or operator statement |
| Installation in chamber | **NOT CLAIMED** — test was on accessible probes |
| Mechanical H0 (box/probe fixture) | DEFERRED (A-W02-01) |
| Placement plan | prepared in `21-placement-plan.md`; execution requires operator + photos |

Moving or labelling a probe is a configuration change (PHY-DS-003); the map and
`coldguard_config.h` remain byte-identical and must be updated only in a separately
reviewed change after the operator confirms placement.

---

## D. Hot-side / cold-side monitoring gap

- Every telemetry frame in this session reported `t_cold_side_c=nan`,
  `t_hot_side_c=nan`, both `NOT_ASSIGNED`, and `t_inside_src=T2`. T1–T3 are
  chamber-air probes; none is a contact probe on a TEC face or heatsink.
- **Separate cold-side and hot-side measurement is NOT AVAILABLE and still REQUIRED.**
  Two independent contact measurements are needed; the single SPARE probe could cover
  at most one of them.
- SPARE (`283BE5C9000000A9`) is the natural hot-side candidate (same bus, explicit
  non-role in the frozen table), but adopting it requires: (1) a documented ROM→new
  role config change with review, (2) mechanical contact with the hot block and
  thermal paste, (3) a telemetry-contract change for `t_hot_side_c` /
  `t_hot_side_status` with tests, (4) docs/06 §9 conditions. **This is a proposal, not
  an approved remapping**; nothing was installed or relabelled.
- Consequence for safety: `PHY-TEC-001` refuses START while no valid hot-side channel
  exists, so the controller cannot energize the branch. That refusal is correct and
  remains in force.

---

## E. Six-limit audit matrix

Exact identifiers from `firmware/main/cg_tec_limits.h` / `.c` (ship table
`cg_tec_limits_shipped`). `cg_tec_limits_all_resolved()` gates `cg_tec_start()`
(`cg_tec_control.c:289`).

| # | Identifier (name token, unit) | Physical meaning / fault source | Current value | TEC-OFF establishable | Powered characterization | Primary safety dependency | Status |
|---|---|---|---|---|---|---|---|
| L1 | `CG_LIMIT_CURRENT_MAX_A` (`current_max_a`, A) | max branch current; `OVERCURRENT` (`cg_tec_control.c:160`) | `0.0`, `UNRESOLVED`, `TEC_CONTINUOUS_RATING_NOT_ESTABLISHED` | no | yes | IBT-2/wire thermal, fuse coordination | **UNRESOLVED** |
| L2 | `CG_LIMIT_VOLTAGE_MAX_V` (`voltage_max_v`, V) | max branch voltage; `OVERVOLTAGE` (`:164`) | `0.0`, `UNRESOLVED`, `TEC_VMAX_NOT_ESTABLISHED` | partially (no-load only) | yes | PSU setpoint, load transients | **UNRESOLVED** |
| L3 | `CG_LIMIT_VOLTAGE_MIN_V` (`voltage_min_v`, V) | min branch voltage under load; `UNDERVOLTAGE` (`:168`) | `0.0`, `UNRESOLVED`, `PSU_LOAD_REGULATION_NOT_MEASURED` | no (needs load) | yes | collapsing supply / bad contact | **UNRESOLVED** |
| L4 | `CG_LIMIT_HOT_SIDE_MAX_C` (`hot_side_max_c`, °C) | max hot-side temperature; `OVERTEMP` (`:172`); also `PHY-TEC-001` | `0.0`, `UNRESOLVED`, `HOT_SIDE_LIMIT_NOT_ESTABLISHED` | partially (contact/response only) | yes | highest-severity thermal limit, heatsink/fan | **UNRESOLVED** |
| L5 | `CG_LIMIT_DUTY_MAX_PERMILLE` (`duty_max_permille`, ‰) | max commanded duty; `START_OUTSIDE_LIMITS` (`:294-296`) | `0.0`, `UNRESOLVED`, `DUTY_NOT_CHARACTERISED` | no | yes | couples current + hot-side limits | **UNRESOLVED** |
| L6 | `CG_LIMIT_ON_TIME_MAX_MS` (`on_time_max_ms`, ms) | max run duration; `START_OUTSIDE_LIMITS` (`:294-296`) | `0.0`, `UNRESOLVED`, `ON_TIME_NOT_CHARACTERISED` | no | yes | unattended-run / thermal accumulation | **UNRESOLVED** |

No value was changed and no temporary number was introduced. Per-limit required
evidence, proposed acceptance method and remaining gap: `22-six-limit-audit.md`.
The single `≈ 0.98 A @ 10 % PWM` short observation does **not** establish any maximum
current, duty, thermal threshold or on-time.

---

## F. Existing accepted test evidence and remaining blockers

Usable evidence actually present in the repository:

| Evidence | Class | What it supports |
|---|---|---|
| TEST 132B: 600/600 PZEM samples, 598.99 s, branch 11.94–11.95 V (mean 11.9483), 0.00 A, gate `RESULT: REVIEW REQUIRED` | MEASURED (Arduino bench, not ESP-IDF) | PZEM validity; TEC-OFF branch voltage |
| TEST 133B: 120/120 windows 0 A / 0 W | OPERATOR-REPORTED | reset/default-OFF observation; pin levels are printed constants, not measurements |
| TEST 129D: four ROMs read on GPIO33 | MEASURED | probe presence and bus wiring |
| TEST 131: 50 A PZEM profile frame | OPERATOR-REPORTED + host CRC | PZEM profile readback, not TEC current |
| G1 run + G2-A captures (721 TELEM frames) | MEASURED | safe-OFF telemetry, TWDT clean, 1 Hz |
| Shunt `50 A / 75 mV FL-2 0.5`; B−↔GND ≈ 0 Ω; fuse set 10/15/20 A unselected | SOURCE VERIFIED / OPERATOR-REPORTED | topology only; no calibration |

Referenced by the task but **not found anywhere in the repository** (searched all
worktrees/evidence): TEST 119, 120, 124, 125, 126; "XL4015 no-load 5.01 V / loaded
4.99 V" (the repo records ~5.00 V no-load on XL4015 and 4.99 V on the TB4506 rail —
both 5 V logic rails, **not** the 12 V TEC branch). These were not used.

Remaining blockers to limit resolution:

1. TEC branch must stay unpowered by design — current, loaded voltage, duty and
   on-time cannot be characterized yet.
2. No hot-side contact probe, no thermal-paste/contact evidence, no fan
   installation/rating record (docs/06 U9/U10), so L4 has no temperature basis.
3. No manufacturer/measured basis for the exact TEC1-12715 SKU (docs/01 §13.2
   forbids assuming Imax=15 A, Vmax=15.4 V, Qmax=150 W).
4. No shunt calibration against a reference; no loaded PSU regulation curve.
5. No recorded G0 power-off electrical verification (docs/06 §11) — the continuity
   and branch-isolation record is still missing.
6. SPARE probe not stimulus-confirmed; no probes labelled or position-verified.

---

## G. G2-A status

**G2-A PARTIAL.**

- Phase 1 (probe identification): T1/T2/T3 identified unambiguously by thermal
  stimulus against live telemetry; SPARE present and plausible but not
  stimulus-confirmed (round paused). Identity was not inferred from enumeration order.
- Phase 2 (placement): plan and role semantics prepared; nothing installed, moved or
  labelled; positions unverified. Hot/cold-side measurement is absent and required;
  SPARE-as-hot-side remains a proposal.
- Phase 3 (limits): all six exact identifiers audited with current values, required
  evidence, existing ColdGuard evidence, TEC-OFF feasibility, powered-characterization
  need, safety dependency and acceptance path. All six remain **UNRESOLVED**.
- Phase 4: this report; no TEC power, no fuse, no PSU, no source or git change.

Not PASS: SPARE identity, placement/labels, fan/hot-side contact, and all six limits
are open. Not BLOCKED: the safe scope of G2-A was executed and produced usable
evidence.

---

## H. Exactly one next recommended action

**Execute docs/06 G0 — power-off electrical verification, and record it in
`evidence/A/W04/g0-electrical-verification.md`.**

With the 12 V PSU OFF and disconnected, the 15 A fuse still removed, and USB
disconnected, measure with a DMM: branch dead at `IBT-2 B+`/`B−` vs PSU−; continuity
GPIO5↔RPWM, GPIO6↔R_EN, GPIO10↔L_EN, GPIO33↔DS18B20 DATA, GPIO36/37↔TTL485 (correct
direction); shunt position and `B−`↔GND relationship; branch fuse position/label;
IBT-2 input topology (or record `NOT VERIFIED`). Do not reinsert the fuse, do not
power the PSU, do not reflash. G0 must PASS before any further gate work; until then
the six limits stay `UNRESOLVED` and G3 remains unauthorized.
