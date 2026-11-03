# G2-A — Audit of the six W04 commissioning limits

Source of truth: `firmware/main/cg_tec_limits.c` (`cg_tec_limits_shipped`) and
`firmware/main/cg_tec_limits.h` (enum/order), plus `docs/06 §4` (acceptance contract).
All six entries ship as `state = CG_LIMIT_UNRESOLVED`, `value = 0.0f`, with a
provenance token. `cg_tec_limits_all_resolved()` gates `cg_tec_start()`
(`cg_tec_control.c:289`), so START always returns `START_LIMITS_UNRESOLVED` on this build.

## 1. Audit matrix

### L1 — `CG_LIMIT_CURRENT_MAX_A` (`current_max_a`, A)
- **Physical meaning:** maximum TEC branch current accepted during operation; source of
  the `OVERCURRENT` fault (`cg_tec_control.c:160`).
- **Current configuration:** `0.0`, `UNRESOLVED`, source `TEC_CONTINUOUS_RATING_NOT_ESTABLISHED`.
- **Required evidence:** continuous-load current vs duty/voltage on the real TEC,
  wire/connector/IBT-2 thermal behaviour, fuse coordination, and manufacturer data for
  the exact purchased TEC1-12715 SKU (docs/01 §13.2 forbids assuming `Imax = 15 A`).
- **Existing ColdGuard evidence:** one operator-reported point `≈ 0.98 A @ PWM 10 %` for
  a short time (pinmap §5 / provenance P25, `OPERATOR-REPORTED`); shunt 50 A / 75 mV
  `FL-2 0.5` seen in a photo (`SOURCE VERIFIED`) but not calibrated; TEST 132B shows
  `0.00 A` only within PZEM's 0.01 A display resolution at TEC OFF.
- **Establishable with TEC OFF:** no (current under load is the measurement).
- **Powered characterization required:** yes.
- **Safety dependency:** overtemperature of IBT-2/wiring; final fuse choice
  (W01 HW-15 leaves 10/15/20 A unselected); overcurrent latch.
- **Proposed acceptance:** stepped G3 runs; at each step record branch V/I, T_hot,
  IBT-2 case temperature and time; set `current_max_a` below measured component limits
  with margin; cite the evidence file in `source`.
- **Remaining gap:** no continuous-load data, no IBT-2 thermal data, no SKU datasheet,
  no shunt calibration against a reference.

### L2 — `CG_LIMIT_VOLTAGE_MAX_V` (`voltage_max_v`, V)
- **Physical meaning:** maximum branch voltage; source of `OVERVOLTAGE`
  (`cg_tec_control.c:164`).
- **Current configuration:** `0.0`, `UNRESOLVED`, `TEC_VMAX_NOT_ESTABLISHED`.
- **Required evidence:** loaded branch voltage at operating points and the PSU's
  regulated setpoint; SKU Vmax evidence.
- **Existing evidence:** branch `11.94–11.95 V` (mean 11.9483) with TEC OFF over
  598.99 s — TEST 132B, `MEASURED` bench artifact (Arduino sketch, gate
  `RESULT: REVIEW REQUIRED`). PSU label 12 V / 33.3 A / 400 W (`SOURCE VERIFIED`).
- **Establishable with TEC OFF:** partially — the no-load branch voltage is measured;
  the value that matters (loaded) is not.
- **Powered characterization required:** yes.
- **Safety dependency:** PSU setting; overvoltage latch during load transients; IBT-2
  voltage stress.
- **Proposed acceptance:** measure branch V under load at every G3 step, including
  switch-on transients; set `voltage_max_v` above the highest measured operating voltage
  with margin, from a documented SKU/PSU basis.
- **Remaining gap:** no loaded branch measurement; no SKU Vmax document.

### L3 — `CG_LIMIT_VOLTAGE_MIN_V` (`voltage_min_v`, V)
- **Physical meaning:** minimum branch voltage while under load; source of
  `UNDERVOLTAGE` (`cg_tec_control.c:168`, evaluated only `under_load`). Detects PSU
  sag, bad contacts and a collapsing branch.
- **Current configuration:** `0.0`, `UNRESOLVED`, `PSU_LOAD_REGULATION_NOT_MEASURED`.
- **Required evidence:** loaded branch voltage vs load; PSU regulation and wiring drop.
- **Existing evidence:** only the TEC-OFF branch voltage (TEST 132B). No loaded data.
- **Establishable with TEC OFF:** no (definition requires load).
- **Powered characterization required:** yes.
- **Safety dependency:** prevents operating from a collapsing supply; distinguishes a
  bad connection from a TEC fault; interacts with `current_max_a`.
- **Proposed acceptance:** record branch V at each G3 step and at the moment of load
  switching; set the threshold above the level where IBT-2/control behaviour is
  compromised, with margin, and document the PSU regulation curve.
- **Remaining gap:** no load-switching or steady-load voltage data.

### L4 — `CG_LIMIT_HOT_SIDE_MAX_C` (`hot_side_max_c`, °C)
- **Physical meaning:** maximum hot-side temperature; source of `OVERTEMP`
  (`cg_tec_control.c:172`). `PHY-TEC-001` also refuses START without a valid hot-side
  channel.
- **Current configuration:** `0.0`, `UNRESOLVED`, `HOT_SIDE_LIMIT_NOT_ESTABLISHED`.
- **Required evidence:** hot-side block curve (T_hot vs input power and time) with the
  installed heatsink/fan, contact-mounted probe, plus a temperature basis for the TEC
  and heatsink (datasheet or measured derating).
- **Existing evidence:** none for temperature. No probe assigned
  (`t_hot_side_status=NOT_ASSIGNED` in every session); no fan installation/rating record
  found (docs/06 U9/U10 open). The chamber probes measure air, not the hot block.
- **Establishable with TEC OFF:** partially — probe contact and response can be
  validated by gently warming the block externally (docs/06 §G2), but the limit itself
  needs TEC heat.
- **Powered characterization required:** yes (fan may run on its own supply at G2;
  the limit needs TEC).
- **Safety dependency:** highest-severity thermal limit; PHY-TEC-001; heatsink/fan
  adequacy; OVERTEMP latch.
- **Proposed acceptance:** G2 — fix a contact probe with thermal paste, warm the block
  externally, record response and 5 min stability; G3/G4 — record T_hot vs time and
  power with the fan at rating; set the limit below the documented device/heatsink
  rating with margin.
- **Remaining gap:** no hot-side probe, no contact evidence, no fan data, no thermal
  model.

### L5 — `CG_LIMIT_DUTY_MAX_PERMILLE` (`duty_max_permille`, ‰)
- **Physical meaning:** maximum commanded duty; rejects `START_OUTSIDE_LIMITS`
  (`cg_tec_control.c:294-296`) and caps output power.
- **Current configuration:** `0.0`, `UNRESOLVED`, `DUTY_NOT_CHARACTERISED`.
- **Required evidence:** current and temperature vs duty across the intended envelope;
  IBT-2 switching behaviour; TEC response.
- **Existing evidence:** the single `≈ 0.98 A @ 10 %` operator-reported point — a
  short-duration observation with no thermal or repeat data. Explicitly insufficient;
  it must not be extrapolated to a maximum duty.
- **Establishable with TEC OFF:** no.
- **Powered characterization required:** yes.
- **Safety dependency:** couples to `current_max_a` and `hot_side_max_c`; the accepted
  duty must satisfy both.
- **Proposed acceptance:** G3 duty sweep in safe steps, each step derived from the
  previous measurement; `duty_max_permille` = largest duty satisfying current and
  thermal limits with margin.
- **Remaining gap:** no sustained-load data, no duty sweep, no repeatability, no thermal correlation.

### L6 — `CG_LIMIT_ON_TIME_MAX_MS` (`on_time_max_ms`, ms)
- **Physical meaning:** maximum permitted run duration; rejects
  `START_OUTSIDE_LIMITS` (`cg_tec_control.c:294-296`); drives the bounded run and
  COOLDOWN cycle.
- **Current configuration:** `0.0`, `UNRESOLVED`, `ON_TIME_NOT_CHARACTERISED`.
- **Required evidence:** hot-side and cold-side time constants under load; time to
  approach thermal limits at the accepted duty; at least one complete
  COOLING→COOLDOWN→OFF cycle.
- **Existing evidence:** none under load. G1 only shows TEC-OFF telemetry.
- **Establishable with TEC OFF:** no.
- **Powered characterization required:** yes.
- **Safety dependency:** unattended-run protection; thermal accumulation; COOLDOWN
  adequacy; interacts with `hot_side_max_c`.
- **Proposed acceptance:** timed G3/G4 runs with T_hot tracking until the approach to
  the hot-side limit is characterised; set `on_time_max_ms` with margin; verify one
  full cooldown with the fan.
- **Remaining gap:** no time-series under load, no cooldown data.

## 2. Evidence inventory actually used (and what is missing)

| Evidence | Class | What it supports | File |
|---|---|---|---|
| TEST 132B, 600/600 PZEM samples, 598.99 s, 11.94–11.95 V, 0.00 A, gate REVIEW REQUIRED | MEASURED (bench, Arduino) | PZEM validity; TEC-OFF branch voltage | `evidence/A/W03/hardware-2026-10-27/raw/test-132b-off-envelope.log` + CSV; README |
| TEST 133B, 120/120 windows 0 A / 0 W | OPERATOR-REPORTED | reset/default-OFF observation; pin levels are printed constants, not measurements | `evidence/A/W03/hardware-2026-10-27/test-133b-reset-default-off.md` |
| TEST 129D, 4 ROMs on GPIO33 | MEASURED | probe presence/bus, not limits | pinmap §2 |
| TEST 131 (50 A PZEM profile frame) | OPERATOR-REPORTED + host CRC | PZEM profile readback, not TEC current | provenance matrix §2 |
| `≈ 0.98 A @ 10 % PWM`, short | OPERATOR-REPORTED | proof of conduction only | pinmap §5 / provenance P25 |
| Shunt 50 A / 75 mV `FL-2 0.5`; B−↔GND ≈ 0 Ω | SOURCE VERIFIED / OPERATOR-REPORTED | topology; not calibrated | pinmap §5; provenance P21–P24 |
| Fuse set 10/15/20 A, final not selected; 15 A slot currently removed | OPERATOR-REPORTED | bench state; no TEC fuse commission | W01 `bom-audit.csv` HW-15 |
| PSU 12 V / 33.3 A / 400 W label | SOURCE VERIFIED | PSU identity only | W01 HW-12 |
| XL4015 ~5.00 V no-load; TB4506 4.99 V | OPERATOR-REPORTED (W01) | **5 V logic rails — not the TEC branch** | W01 HW-13; W03 as-built §5 |
| TEC marking `TEC1-12715 SR` in photo | SOURCE VERIFIED (marking) | family name only; docs/01 §13.2 forbids Imax/Vmax/Qmax inference | W01 R13 |

Referenced by the task but **not present anywhere in the repository** (searched all
worktrees/evidence):

- `TEST 119`, `TEST 120`, `TEST 124`, `TEST 125`, `TEST 126` — no file, log, CSV or
  document mentions them; the only TEST ids recorded are 129D, 131, 132B, 133B.
- `XL4015 no-load 5.01 V / loaded 4.99 V` — the repo records ~5.00 V no-load (XL4015)
  and 4.99 V (TB4506 rail). No loaded XL4015 measurement exists, and neither rail is the
  12 V TEC branch. These values were not used as limit evidence.
- A fan installation/current record — not found (docs/06 U9).

## 3. Verdict per limit

| Limit | Value now | Resolvable TEC-OFF? | Sufficient evidence? | Status |
|---|---|---|---|---|
| `current_max_a` | 0.0 | no | no | **UNRESOLVED** |
| `voltage_max_v` | 0.0 | partially (no-load only) | no (loaded missing) | **UNRESOLVED** |
| `voltage_min_v` | 0.0 | no | no | **UNRESOLVED** |
| `hot_side_max_c` | 0.0 | partially (contact/response only) | no | **UNRESOLVED** |
| `duty_max_permille` | 0.0 | no | no (one short point) | **UNRESOLVED** |
| `on_time_max_ms` | 0.0 | no | no | **UNRESOLVED** |

No value was changed; no temporary numbers were introduced. Any future change must follow
`docs/06 §4`: measure on the real hardware, write the number and conditions to
`evidence/A/W04/`, point `source` at that file, and review before build.
