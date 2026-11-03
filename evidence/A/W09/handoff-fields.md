# Run-manifest edge fields (A-W09 handoff to Member C)

Derived from the export schema in `firmware/tools/cg_w09_export.py` (w09-run-export-v2) and the example export `exports/CG-S1-H8C-600S.json`. Status: **IMPLEMENTED / HOST_VERIFIED**.

These are the fields a run manifest must carry for the backend to join a capture without guessing. Every one is present in the shipped export; none is inferred.

| field | value in the example export | notes |
|---|---|---|
| `run_id` | `None` (`run_id_status=UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID`) | the source carries several run_id segments inside one boot_id; they are listed in `run_ids` and never merged into a joined id, so this run is not publishable for a B join |
| `run_ids` | `['run-00000000', 'run-00000001']` | the segments as the device stated them |
| `boot_id` | `56044b74` (`boot_id_status=SOURCE_CARRIED_SINGLE`) | per boot; opening the port changes it |
| `device_id` | `NOT_CARRIED_BY_THIS_ENCODING` | not carried by the H8S/CSV encodings |
| `hardware_config_id` | `CG-HW-001` | from the `#CG LOG` boot line |
| `firmware_version` | `cg-w04-0.1.0` | from the `#CG LOG` boot line |
| `schema_version` | `None` | wire schema of the source line |
| `timestamp_utc` | `null` + `timestamp_utc_status=UNAVAILABLE` | device has no wall clock |
| `host_capture_time_utc` | separate field, host-labelled | only where the transcript prefixed it |
| `dedup_key` | `(device_id, boot_id, seq)` | docs/02 §4.2/§4.3 |

## Sensor identity C receives

| raw slot | ROM | ROM source | physical position | in chamber mean |
|---|---|---|---|---|
| `t1` | `287088CA00000051` | `BOOT_LOG_CG_ROM_LINE` | CHAMBER_CENTER | yes |
| `t2` | `28AEBF2200000006` | `BOOT_LOG_CG_ROM_LINE` | TEC_HOT_SIDE | **no** |
| `t3` | `28CBE9CA00000072` | `BOOT_LOG_CG_ROM_LINE` | CHAMBER_BOTTOM | yes |
| `t4` | `283BE5C9000000A9` | `BOOT_LOG_CG_ROM_LINE` | CHAMBER_NEAR_DOOR | yes |

ROMs are stated **by source** from the firmware ROM map and the per-boot `#CG ROM` lines; no readback was performed, and the export says so in `rom_readback_verified: false`.

## Experiment phases

* `ACTIVE_COOLING` - 600 frame(s)
* `COOLDOWN` - 5 frame(s)
* `OFF_IDLE` - 335 frame(s)
* `PRE_FIRST_SNAPSHOT` - 17 frame(s)

## Invalidation C must propagate

Of 957 frames, 0 are usable for the S1 scenario and 940 are clean enough for a mixed-probe thermal statistic. The two are different claims: the scenario additionally requires the door and environment domains to be qualified, and this derived table carries no qualifier column for them, so those domains are reported UNKNOWN rather than assumed good. Reasons are per frame in `frames[].invalidation_reasons` and counted in `invalidation.summary.reason_counts`. No frame is deleted.
