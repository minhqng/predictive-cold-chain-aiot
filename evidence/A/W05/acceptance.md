# A-W05 acceptance

Slice: W05 coherent firmware telemetry at ~1 Hz · Branch `feat/a-w05-telemetry`
Compiled: ESP-IDF v6.1 / esp32s3 (see `build/`) · Flashed: **NO**
Executed on hardware: **NO**

Status vocabulary: `VERIFIED` (proven by an executable check on the delivered
code), `NEED_USER_ACTION` (a physical action only the operator can authorize and
perform), `NEED_USER_INPUT` (a fact the repository does not contain),
`TEAM_DEPENDENCY` (belongs to another member or to a project-level decision),
`BLOCKED` (cannot proceed, with the reason).

## 1. Requirement matrix

| ID | Canonical ask (docs/05A §14) | Status | Evidence |
|---|---|---|---|
| **A-W05-01** | Separate thermal / BME / door / PZEM / command state / quality / telemetry / health | **VERIFIED (software)** | Eight distinct boundaries exist and are observable: `cg_ds18b20`+`sensor_task`, `BME` (declared, unimplemented, producer `CG_PRODUCER_BME`), `cg_door`+`door_task`, `cg_power`+`cg_pzem`, `cg_tec_control`/`cg_tec_command`, `cg_quality.c` (new), `cg_telemetry.c`, `cg_health.c` (new). Each producer beats into a shared registry from its own task context and telemetry names the worst producer. Scenarios 9–12, 23–24; static checks 5 of `cg_check_firmware_w05.py`. |
| | "PZEM timeout must not block local safety forever" | **VERIFIED (existing, re-pinned)** | `CG_PZEM_RESPONSE_TIMEOUT_MS 250`, `CG_PZEM_MAX_ATTEMPTS 2`, bounded by `cg_rs485` idle-gap detection; the poll runs in its own task at priority 4, and a timed-out poll still publishes an invalid observation plus a heartbeat, so the control loop never waits on RS-485. W05 adds the liveness view; the bound itself predates this slice and is re-checked, not re-claimed. |
| **A-W05-02** | `device_id` `boot_id` `seq` `uptime` `firmware_version` `hardware_config_id` `calibration_id` | **VERIFIED (software)** | All seven are on the schema-2 line: `device_id=coldguard-001`, per-boot `boot_id`, monotonic `seq` starting at 1, `uptime_ms`, `firmware_version=cg-w05-0.1.0`, `hardware_config_id=CG-HW-001`, `calibration_id=UNRECORDED`. Scenario 13; `schema-fixture.json`; docs/02 633-646 dedup tuple satisfied. |
| **A-W05-03** | Collect ≥ 30 min; measure sample intervals, mean, P95, max gap, DS18B20 read failures, PZEM read failures | **PARTIAL — tool VERIFIED, 30-minute capture NEED_USER_ACTION** | `cg_timing_analysis.py` computes every listed quantity, including per-source read-failure tallies, and is tested (14 tests) against a real capture. The executed pilot is the committed 60-second W04 window: mean 1001.279 ms, median 980 ms, p95/p99 1080 ms, max 1080 ms, 0 non-positive gaps, 0.9987 Hz over 61 078 ms; thermal `OK` 61 / `NO_DATA` 1, electrical `INVALID` 61 / `NO_DATA` 1, door `UNVERIFIED` 62. `30min-telemetry.csv` and a real `timing-jitter.csv` do **not** exist and are not fabricated. |
| **A-W05-04** | Each published row carries T1 T2 T3 / BME T/RH / door / PZEM V/I/P/Wh / applied cooling / quality, with clear missing-state semantics | **VERIFIED (software)** | T1/T2/T3/SPARE as `raw_t*_c` with per-role status and ROM; BME T/RH present as `nan`+`SENSOR_NOT_PRESENT` (honest missing state, not an omission); door with `door_age_ms`/transitions/cycles; **V/I/P/Wh** — `energy_wh` was decoded and logged since W03 but never reached the snapshot; applied cooling as `cooling_applied` **plus** `cooling_evidence`; quality as five names. Missing value ⇒ `nan` + status token, never 0.0, never the previous value. Scenarios 14–22. |
| **A-W05-05** | Implement VALID / DEGRADED / INVALID / UNKNOWN; do not replace missing current with a previous "fresh" value | **VERIFIED (software)** | `cg_quality.c` derives the canonical four per source with the documented collapse order; `CG_QUALITY_UNKNOWN` added to the thermal enum and made the snapshot's pre-first-publication state (W04 initialised it to `INVALID`, which asserted a failure with no evidence). The prohibition is enforced structurally: `cg_snapshot_publish_power(valid=false, …)` replaces the observation with an invalid one carrying its own timestamp, and `fmt_float(false,…)` emits `nan`; there is no code path that reuses a previous current value. Scenarios 1–8, 16–21. Physical fault injection: **UNVERIFIED** (host-only, see §3). |
| Deliverable | `firmware tag/commit` | **VERIFIED** | This PR's head commit; the built image hash is pinned in `build/`. No release tag is created by a Member A slice. |
| Deliverable | `schema-fixture.json` | **VERIFIED** | 7.9 KB. The `raw_line` was rendered by the delivered `cg_telemetry.c` through the host harness and re-parsed by the delivered parser; labelled `is_synthetic_frame: true`, `is_physical_measurement: false`. |
| Deliverable | `quality-test.md` | **VERIFIED (as host evidence)** | 33 C scenarios + 125 static checks + 31 mutations and 1 must-not-fire control, with the not-fault-injection boundary stated at the top. |
| Deliverable | `30min-telemetry.csv` | **NEED_USER_ACTION** | See §4. |
| Deliverable | `timing-jitter.csv` | **NEED_USER_ACTION** | The tool writes it from a real capture (`--jitter-csv`); the committed `timing-pilot-jitter.csv` is the 60-second W04 pilot, clearly named as such. A W05-image jitter table requires the capture in §4. |

## 2. Weekly gate statement

W05 is **not** a GREEN week. It is delivered as **software-complete,
physically-uncaptured**. The canonical text itself authorizes exactly this
shape (docs/05A §13.3: with the W04 physical gate incomplete, "W05 real telemetry
may continue only for safe sensors; high-power work remains blocked"), and this
slice touches only safe sensors, keeps `CG_TEC_OUTPUT_STAGE_ENABLED 0`,
`CG_TEC_REQUEST_DUTY_PERMILLE 0`, and leaves all seven operating limits
`UNRESOLVED`.

## 3. What was proven, and by what

| Claim | Proof class |
|---|---|
| Quality, liveness, identity, coherence and applied-state rules behave as documented | Executable: the delivered C files compiled and run on the host (28 scenarios) |
| The static contract holds across the tree | Executable: 125 checker assertions, 32 mutation/positive-control tests proving they can fail |
| The W04 evidence stream still parses | Executable: 62 real committed schema-1 lines re-parsed, 0 rejected |
| Cadence statistics are computable from real bytes | Executable: pilot over a committed 60 s capture |
| The delivered tree compiles | ESP-IDF v6.1 `idf.py build` recorded in `build/` |
| Any of this runs correctly **on the device** | **NOT proven.** The W05 image has never been flashed. |
| Any physical fault response | **NOT proven.** No sensor was disconnected or disturbed. |
| Any cooling performance | **NOT proven and not claimed.** No energization in this slice. |

## 4. Physical actions required to close A-W05-03

Order matters; each step needs its own operator authorization.

1. **Confirm what is installed.** The device last ran the H8 bench image
   (`01cedce3…`, flashed 2026-10-31). The W05 build (`build/` records its hash)
   has never run on this board.
2. **Preserve recovery before any write.** Full 16 MB flash read, or a verified
   `idf.py read_flash` equivalent plus the existing H8 `.bin`, with the restore
   command written down and its target hash verified. Nothing is flashed until
   the backup is confirmed readable.
3. **Set up a second console.** The native USB-Serial-JTAG port drops when board
   power is removed, so a cold-boot banner cannot be captured through it; UART0
   on GPIO43/44 must be attached for the run to record its own start.
4. **Isolate the TEC branch** (branch fuse holder out or branch PSU off) so the
   30-minute idle capture is provably a no-energization run.
5. **Authorize and flash** the W05 image.
6. **Capture ≥ 30 minutes** with `firmware/tools/cg_capture.py`, then run
   `cg_timing_analysis.py --jitter-csv … --json …` and append the result here.
7. Optionally, and only with separate supervision, one short run with the branch
   energized to characterize cadence while the PZEM is measuring real current —
   the pilot's 61 `INVALID` electrical frames show this is currently unknown.

Nothing in step 1–7 is performed by this PR.

## 5. Items this slice does not own

| Item | Owner / status |
|---|---|
| T2 physical semantics vs `docs/01` chamber-air roles | TEAM_DEPENDENCY. Unchanged: `t_hot_side_c=nan NOT_ASSIGNED`, `t_inside_src=T2`, `role_status=…PENDING`. Amending the semantic requires editing `docs/01` first, per its own change policy. |
| 1.75 mm² conductor vs canonical `2 × 2.5 mm²`; 15 A branch fuse basis | Open deviation register (`CR-A-W04-01`, `CR-A-W04-02`). The GitHub issues were closed administratively on 2026-11-02 for lack of an available reviewer; that closure certifies nothing. W08 owes the engineering assessment. |
| `sensor-rom-map.yaml` `physical_position_verified: false` | NEED_USER_INPUT (label/marker observation), unchanged since W02. |
| Backend envelope, MQTT topics, schema negotiation | Member C. `handoff-w05.md` §2 states the device-side contract and the ingest rules. |
| Control freshness thresholds as policy | Member D. The 2×/4× liveness multipliers here are firmware observability choices, not canonical policy. |
| BME280 driver | Not implemented (A-W02-06). Its producer is declared and reports `NEVER`; humidity is `SENSOR_NOT_PRESENT`. |
| Command/ACK idempotency, expiry, applied-state reporting for commands | W06. `seq` restarts per boot but a reset that keeps `boot_id` is not yet distinguishable from continued running. |

## 6. Build-provenance note for this branch

`evidence/A/W04/build-2026-11-01/22-source-hashes.txt` pins the sources as they
stood at the W04 commit. **Thirteen of those files differ on this branch**
(`CMakeLists.txt`, `app_main.c`, `cg_commission.c`, `cg_ds18b20.c/.h`,
`cg_power.c`, `cg_snapshot.c/.h`, `cg_tec_control.c/.h`, `cg_telemetry.c/.h`), so
`sha256sum -c` against that W04 list fails here by design and the W04 record must
not be read as proof of these bytes.

The chain for W05 is: `build/22-source-hashes.txt` (the exact sources of this
branch, cross-checked identical against the tree that was compiled) →
`build/20-idf-py-build.log` (the ESP-IDF v6.1 run) →
`build/21-artifact-hashes.txt` (app image
`7487cc8148489a31a4151477c3c65460e77f80bb56ebd1e688a41f9f772bc8eb`, 248 512
bytes). The W04 pins remain valid for the W04 commit; neither record proves the
other's bytes, and neither has ever been run on the device.

## 7. Defects found and fixed during this slice

Recorded because each one was a real bug in delivered or in-flight code, not a
style pass.

1. **Thermal quality counted the wrong thing.** The first `cg_quality.c`
   returned DEGRADED whenever `0 < probes_ok < probes_expected`, i.e. 1 valid
   probe out of 3 was DEGRADED. `docs/01` 924-942 counts *failed* probes, so that
   case is INVALID. Caught by harness scenario 4 before commit.
2. **`collapse_order` test was self-contradictory** — it asserted VALID while two
   sources were still DEGRADED. The test, not the code, was wrong.
3. **`health_states` boundaries were computed against the wrong multipliers**
   (1.5× asserted as LATE). Fixed to the documented 2×/4× with explicit 1500 /
   2001 / 4001 ms cases.
4. **`snprintf` used without `<stdio.h>`** in `cg_quality.c`; and the health
   module's state-name helper was referenced under its old name after renaming.
   Caught by compilation, not by inspection.
5. **Empty `fault_reason=` token would have broken the parser.** The W05 fixture
   left `ctl.reason` zeroed, and the formatter emitted `fault_reason=` with no
   value, which the schema rejects as an empty token. This is why the fixture now
   sets `BOOT_SAFE_OFF`; a device always sets a reason, but the harness had
   created an impossible state.
6. **The timing analyzer reported absent measurements as zeros.** A schema-1
   capture has no `seq`, so "0 duplicates / 0 missing" read as a clean dedup key;
   likewise `thermal_seq` stalls. Both now report `None`/absent. Also fixed the
   rate: 12 frames spanning 11 s is 1.0 Hz, not 1.09 Hz.
7. **`cooling_evidence` conflated "off and zero" with "driven and zero".** The
   first version returned the same token for both, which would have hidden a
   failed output stage. Now `MEASURED_IDLE_AND_ZERO` vs
   `MEASURED_CONTRADICTS_APPLIED`, with `MEASURED_APPLIED_AND_DRAWING` for the
   agreement case.
8. **Three checker assertions could not fail.** `energy_wh` matched the parameter
   name after the assignment was deleted; `outputs_energized` matched the private
   control struct after the public field was removed; `CG_TELEM_HEALTH_UNKNOWN`
   matched one remaining site after the overall fallback was changed to OK. Each
   was rewritten to scope the assertion to the right construct, then re-proved by
   a mutation test.
9. **`environment_quality` cannot reach VALID in this build.** With BME280
   unimplemented, `quality` collapses to DEGRADED at best. Left as-is deliberately:
   hiding a missing BOM sensor behind a VALID verdict would be the worse
   outcome. Consumers must read the per-source names, which is what §2 of the
   handoff tells B and C to do.

### Found by the independent review, then fixed and re-proved

Two read-only reviewers were given the diff and an adversarial brief. Their
findings are recorded here because every one of them was a real defect in
in-flight code or in evidence that over-stated its own guard.

10. **`probes_ok`/`probes_expected` were never copied into the snapshot**
    (`cg_snapshot_publish_thermal()` had no assignment), so every real frame
    would have published `probes_valid=0 probes_expected=0` and collapsed chamber
    air to `UNKNOWN` — a BLOCKER invisible to the harness because the harness
    wrote snapshot fields by hand. Fixed by publishing the driver's counts
    (`cg_snapshot.c`) and by making the harness compile the real
    `cg_snapshot.c` (host lock no-op via `ESP_PLATFORM`), so scenarios 29–33 now
    drive the actual publish/read copy.
11. **The canonical DEGRADED state was unreachable.** The thermal source state was
    derived from `thermal_valid`, which the W04 control gate sets false for a
    single failed probe, so the probe counter was never consulted and one bad
    probe reported INVALID. Fixed to derive from the quality word
    (`cg_telemetry.c`), leaving the control gate strict; scenario 30 now proves
    DEGRADED end-to-end, and a checker assertion prevents the inversion coming
    back.
12. **`outputs_energized` was cleared even when the disengage call failed**
    (`safe_stop_outputs`), so telemetry could have reported `cooling_applied=OFF`
    while the platform had refused to take the outputs down. Fixed to clear only
    on success. The shipped adapter refuses every enable, so this build cannot
    reach the state today — the defect mattered for the day the stage is enabled.
13. **The frame presented configured ROM bytes as sensor identity.**
    `cg_rom_map_bytes()` returns the frozen table, never a per-frame 1-Wire match,
    so the comment claiming the line "names the eight bytes behind each channel
    instead of leaving the role label as an unbacked assertion" was over-claiming.
    Fixed: the line now carries `rom_source=FROZEN_CONFIG_MAP`, the comment states
    the limit, and per-boot detection evidence is named as the `#CG ROM` lines.
14. **An oversized numeric field would have been silently truncated.** The value
    buffers were 16 bytes; the widest PZEM energy register renders to 16
    characters, i.e. zero margin, and `fmt_float` ignored `snprintf`'s return.
    Fixed: 24-byte buffers plus a refuse path that emits the missing token.
15. **The door group skipped the independent age cross-check** that thermal and
    power get, so the comment claiming no caller could hide a stale observation
    was untrue for the door. Fixed with `door_age_over_limit` (scenario 32).
16. **Two W05 checker assertions could not fail**, exactly as the reviewer
    predicted: the hot-side guard only required `CG_TELEM_STATUS_NOT_ASSIGNED`
    somewhere in the file, and the ROM guard passed on `or "rom_keys" in source`.
    Both rewritten to bind the value-and-status argument pair and the actual
    emit call, and each now has a mutation test that proves it fires. The parity
    loop was also changed to require the emitted `key=` token rather than a bare
    name, and to check the ROM keys against the table.
17. **Three document numbers were stale or over-claimed**: the pilot said the
    serial link had carried 1841–2069-byte frames (it carried 1007–1012-byte W04
    frames; the larger figures are a host budget calculation and no schema-2
    frame has ever been on the wire), "gaps of 980/1080 ms only" contradicted the
    same table's own 1078 ms bin, and the budget guard was documented as 85 %
    where the test enforces 90 %. All three corrected, together with the fixture
    length after the field additions (1873 typical / 2098 worst case).

## Dated correction — 2026-11-03 (Member A, production RC)

`schema-fixture.json` in this dossier is a derived artifact: the committed
generator re-renders it from the current firmware emitter. It has been
re-derived on 2026-11-03 on **this** branch, so it still carries
`schema_version=2` and `firmware_version=cg-w05-0.1.0` - schema 3 arrives with
W06, not here. What changed is the probe the chamber-air value is taken from.

The re-derived frame now emits `t_inside_src=T1` (as-built
`CHAMBER_CENTER`, ROM `287088CA00000051`) and `t_hot_side_src=T2` (as-built
`TEC_HOT_SIDE`, ROM `28AEBF2200000006`). The previous emitter sourced the
chamber-air value from T2, which is the hot-side probe; that was a real defect
and the validator now refuses a fixture that loses either source token.

What this does NOT change: no 30-minute capture exists, the fixture is still
`is_synthetic_frame=true` / `is_physical_measurement=false`, and no schema-3
frame has ever been on the wire from a device. The schema-2/1841-2069-byte
history above stays as the record of what was actually measured on the serial
link. `firmware/tools/run_all_checks_w05.py` now invokes the generator with
`--check`; before this change it ran in write mode, so every run silently
rewrote the evidence that the step before it had just hash-verified.
