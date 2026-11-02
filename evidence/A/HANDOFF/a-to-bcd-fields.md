# A → B / A → C / A → D handoff fields (docs/05A §6.1-§6.3)

Field-by-field, against what the repository can actually produce today. Every "available"
below was checked against the committed capture columns or a delivered branch, not asserted.

The single real thermal session is `evidence/A/W04/tec-cooling-response-600s.csv`: 957 rows,
one `boot_id` `56044b74`, columns verified this pass — `t1..t4_status` = `OK` in 957/957;
`current_status` and `voltage_status` **empty** in 957/957; no `power_status` column at all;
`door_open` = `0` in 940 and `UNKNOWN` in 17 with `door_polarity` `CONFIRMED` 940 /
`UNCONFIRMED` 17; `limits_policy` = `APPROVED` 957; `physical_output` empty 957;
`pwm_applied_permille` 999 in 600 rows and 0 in 357.

## §6.1 A → B (training data)

| Required field | State | Source / why |
|---|---|---|
| valid / invalid run status | **Tool ready, zero valid runs** | W09 validity engine on `feat/a-w09-dataset-tooling`; today it rejects the only session rather than passing it |
| `run_id` | **Present but not an independence key** | the capture holds two values (`run-00000000` 226 rows, `run-00000001` 731 rows) **inside one `boot_id`**, so run_id cannot certify a separate run; W09 blocks both instead of handing them over |
| `hardware_config_id` | **NOT AVAILABLE as a justified identity** | no dedicated column exists. The only discriminators are the `session` string (embeds image `01cedce3...`) and `limits_policy`. Deriving a stable id from those is exactly what W12's `configuration_of` got wrong (two different images collapsed to one key) and it is under repair |
| `calibration_id` | **DOES NOT EXIST** | no calibration measurement has ever been taken on this rig; inventing an id would fabricate provenance |
| sensor identity / placement | **PARTIAL** | placement is frozen by operator response (`evidence/A/W07/geometry-v1.md` §1). The in-frame `t1..t4_role` fields are `UNASSIGNED` except `t2_role=HOT_SIDE`, and the ROM ids come from `coldguard_config.h:229-235` *by source*, never read back from the devices |
| door disturbance timestamps | **NO SUCH EVENT EXISTS** | `door_open` is `0`/`UNKNOWN` across all 957 rows and across every other committed capture. Session S-3 is the only way to produce these |
| applied cooling | **AVAILABLE** | `pwm_applied_permille` (+ `_req`, + `_readback`) |
| PZEM V/I/P | **AVAILABLE, UNQUALIFIED** | `voltage_v` / `current_a` / `power_w` / `energy_wh` are present, but their validity fields are empty or absent, so they are values without a recorded check. B must treat them as unqualified features |
| quality flags | **PARTIAL** | probe quality is real (`t*_status` all `OK`, plus `t*_age_ms`); electrical quality is unrecorded at the source |
| physical response delay | **SINGLE SAMPLE** | W13 reports 1.094 s command→electrical from the H6 trace with n=1; publishing median/P95/max over one sample is not a distribution, and the code path that could have shifted it is being fixed |
| pairing context | **NOT AVAILABLE** | W10 `pairing-physics.json` tolerance is `null` by design; matching variation cannot be estimated without repeated real disturbances |

**What B can consume right now:** the schema, the validity/invalidation rules, the export
format and the chamber-air representation set — i.e. the pipeline — plus one unqualified
cooling session for plumbing tests. **What B cannot consume:** any claim of dataset
sufficiency. There are 0 valid S1 runs and 0 valid S2 disturbances.

## §6.2 A → C (device/backend contract)

| Required field | State | Source |
|---|---|---|
| real telemetry fixture | **AVAILABLE** | committed W05/W06 logs and schema-3 frames on PR #16 / PR #17 |
| field semantics | **AVAILABLE** | docs/02 §28-§32 plus the W05/W06 acceptance dossiers |
| device boot / seq behaviour | **AVAILABLE** | `boot_id` and `seq` are in the capture; opening the serial port resets the board and changes `boot_id`, which is recorded and matters for any session-scoped assumption |
| firmware version | **PARTIAL** | the image identity present in the data is the `session` string's `01cedce3...`; the built image itself is local-only (258 544 B, hash recorded in `geometry-v1.md` §2) and was never read back from flash |
| quality status | **AVAILABLE, with the electrical gap stated** | §19 vocabulary implemented; electrical validity absent at source, and tooling must not infer it |
| command applied state | **AVAILABLE** | `pwm_req_permille` vs `pwm_applied_permille` vs `pwm_readback_permille` give intent and application separately |
| ACK device-side info | **AVAILABLE** | W06 emits `#CG CMDACK` with `device_id` taken from authoritative device context (not the command field), plus `boot_id`; freshness fails closed because a receipt-time TTL cannot establish a command's original age |

## §6.3 A → D (control safety inputs)

| Required field | State | Source |
|---|---|---|
| OFF electrical envelope | **AVAILABLE with one unresolved exception** | 357 zero-applied-duty frames: current values are 0.0, 0.02 (idle floor), 0.56 and **7.15 A**. The 7.15 A frame at `device_ms=826894` is docs/01 §22.4's candidate `CONTROL_ELECTRICAL_ANOMALY` (high severity) and is **not** resolved |
| healthy ON current / power range | **ONE SESSION, UNQUALIFIED** | mean 7.2247 A, peak 9.99 A, mean 85.1593 W over 600 driven frames. A range from one session is an observation, not a rating |
| allowed duty / state | **TEAM_DEPENDENCY** | firmware is fail-closed: output stage compiled out, six limits `UNRESOLVED`. Thresholds belong to Member D |
| thermal response window | **ONE SESSION** | chamber-air mean -8.7083 C over 9.98 min; 1 C at 0.85 min; W13 tau proxies 174 s cooling / 86 s recovery, labelled as biased-low proxies |
| default-off behaviour | **AVAILABLE** | W04 evidence: stage disabled at compile time, actuator enable disallowed, REN/LEN readback recorded |
| sensor degraded behaviour | **AVAILABLE at the vocabulary level** | `t*_status`, `t*_age_ms`, `snapshot`/`missing`/`invalid`/`stale` bitfields; the rule "unknown must not silently become normal" is enforced in W05/W06/W09 tooling |
| physical failure evidence | **AVAILABLE, sparse** | the 7.15 A zero-duty frame; `fan_status=NOT_COMMANDABLE` in all 62 committed G1 rows (no tachometer feedback on CG-HW-001); one `ECHO_ONLY` poll retried once, documented as transport latency in `evidence/A/W04/h6/41-h6-run-analysis.md`, not as zero current |

## §5 definition-of-done cross-check

Of the 16 handover items in docs/05A §5, Member A can produce today: hardware configuration
record (partial — the conductor line is missing), final pin map, sensor ROM map (by source),
placement map (frozen by response), healthy electrical envelope (one session), S1/S2 physical
protocols, H0-H8 evidence, physical limitations, and the run/recovery runbook in this
directory. **Not producible without sessions:** calibration/consistency evidence, repeatability
data, PZEM configuration proof against a reference, TEC safe operating point beyond the
observed point, and thermal response windows from more than one run.
