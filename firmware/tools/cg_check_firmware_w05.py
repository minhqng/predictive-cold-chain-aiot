"""Static contract checks for the ColdGuard W05 telemetry foundation.

Like the W04 checker, this certifies only what is provable from the sources. It
does not compile the firmware and does not touch hardware.

Checks:

1.  Identity - the docs/02 dedup key (device_id, boot_id, seq) is on the wire,
    seq is monotonic and nothing resets it, and calibration_id is the honest
    UNRECORDED token rather than an invented bundle identifier.
2.  Sensor identity - the frozen ROM travels in the frame, the role status
    token is carried, and no channel's assignment was silently changed.
3.  Coherence - the snapshot publishes an observation time and a sequence per
    producer, and the frame reports an age per group. W04 published no door
    timestamp and no energy, so both are asserted here.
4.  Quality vocabulary - the four canonical states exist, an unobserved source
    is UNKNOWN rather than INVALID, and the collapse order is the documented
    one.
5.  Producer liveness - every producer that publishes into the snapshot beats
    into the registry, the registry is initialised before those tasks start,
    and the liveness thresholds are not presented as canonical.
6.  Applied state - cooling_applied comes from the output layer's own record,
    never from the requested duty, and the corroboration token set is closed.
7.  Host parity - every W05_REQUIRED_FIELDS token is emitted by the formatter,
    so a schema-2 line the device can produce is never unparseable by the host.
8.  Scope guard - W05 adds observability only: the output stage stays compiled
    out, no command path was added, and no network entry point exists.

Exit codes: 0 = every check passed, 1 = at least one failed, 2 = usage/IO.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cg_check_firmware_w04 as w04  # noqa: E402
from cg_check_firmware_w04 import (  # noqa: E402
    Checker,
    define_value,
    extract_function_body,
    strip_comments,
)
import cg_telemetry_schema as telemetry_schema  # noqa: E402

CALIBRATION_UNRECORDED = "UNRECORDED"


def run_checks() -> Checker:
    checker = Checker()

    config = checker.read("firmware/main/coldguard_config.h")
    quality_c = strip_comments(checker.read("firmware/main/cg_quality.c"))
    quality_h = checker.read("firmware/main/cg_quality.h")
    health_c = strip_comments(checker.read("firmware/main/cg_health.c"))
    health_h = checker.read("firmware/main/cg_health.h")
    snapshot_c = strip_comments(checker.read("firmware/main/cg_snapshot.c"))
    snapshot_h = checker.read("firmware/main/cg_snapshot.h")
    telemetry_c = strip_comments(checker.read("firmware/main/cg_telemetry.c"))
    telemetry_h = checker.read("firmware/main/cg_telemetry.h")
    commission_c = strip_comments(checker.read("firmware/main/cg_commission.c"))
    app_main = strip_comments(checker.read("firmware/main/app_main.c"))
    power_c = strip_comments(checker.read("firmware/main/cg_power.c"))
    ds18b20_h = checker.read("firmware/main/cg_ds18b20.h")
    control_c = strip_comments(checker.read("firmware/main/cg_tec_control.c"))
    control_h = checker.read("firmware/main/cg_tec_control.h")

    # 1. Identity --------------------------------------------------------
    checker.check('#define CG_DEVICE_ID "' in config,
                  "device_id is a configuration value, not a per-file guess")
    checker.check(f'#define CG_CALIBRATION_ID "{CALIBRATION_UNRECORDED}"' in config,
                  "calibration_id is the UNRECORDED token; no calibration bundle has been "
                  "measured, so inventing a CG-CAL-... value would be a fabricated identity")
    checker.check("calibration_id=%s" in telemetry_c and "CG_CALIBRATION_ID" in telemetry_c,
                  "telemetry carries calibration_id")
    checker.check("device_id=%s" in telemetry_c and "CG_DEVICE_ID" in telemetry_c,
                  "telemetry carries device_id")
    checker.check("seq=%lu" in telemetry_c and "frame->seq" in telemetry_c,
                  "telemetry carries the per-boot sequence")
    checker.check("boot_id=%s" in telemetry_c,
                  "telemetry still carries boot_id, so (device_id, boot_id, seq) is complete")

    emit_body = extract_function_body(commission_c, r"static void emit_telemetry\([^)]*\)")
    checker.check(emit_body is not None and ".seq = ++s_telem_seq" in emit_body,
                  "the frame counter is incremented per emitted frame in one place")
    checker.check("static uint32_t s_telem_seq;" in commission_c,
                  "the frame counter is a boot-scoped static (zero-initialised, starts at 1)")
    apply_body = extract_function_body(commission_c, r"static void apply_command\([^)]*\)")
    checker.check(apply_body is not None, "the console command handler was located")
    checker.check(apply_body is not None and "s_telem_seq" not in apply_body,
                  "no console command resets or replays the frame counter")

    # 2. Sensor identity -------------------------------------------------
    checker.check('" %s=%s", rom_keys[role]' in telemetry_c
                  and "frame->probe_rom[role]" in telemetry_c
                  and "CG_TELEM_ROM_UNREAD" in telemetry_c,
                  "telemetry emits the ROM values from the frame and names the unread case")
    checker.check("rom_source=%s" in telemetry_c and '"FROZEN_CONFIG_MAP"' in telemetry_h,
                  "the line states that the ROM bytes are the configured map, not a per-frame "
                  "detection - otherwise a configured identity reads as a measured one")
    checker.check("role_status=%s" in telemetry_c,
                  "telemetry states that the physical role label is still pending")
    checker.check("CG_ROM_STATUS" in config and "ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING" in config,
                  "the pending-label token exists and is not softened")
    # Value AND status bound to the same field. A check that only required
    # `t_hot_side_c=%s` plus the literal somewhere in the file still passed after
    # the hot-side status argument was swapped for a real reading.
    checker.check("fmt_float(false, 0.0f, t_hot, sizeof(t_hot)), CG_TELEM_STATUS_NOT_ASSIGNED"
                  in telemetry_c,
                  "the hot-side field is hard-wired to a missing value with NOT_ASSIGNED")
    checker.check("t_inside_src=T2" in telemetry_c,
                  "the chamber-air channel still names its source ROM role")

    # 3. Coherence -------------------------------------------------------
    for field in ("thermal_obs_ms", "power_obs_ms", "door_obs_ms", "thermal_seq", "power_seq",
                  "door_transitions", "door_cycles", "energy_wh", "probes_ok", "probes_expected"):
        checker.check(field in snapshot_h, f"snapshot carries {field}")
    checker.check("s_snap.probes_ok = snap->measurement_ok;" in snapshot_c
                  and "s_snap.probes_expected = snap->measurement_expected;" in snapshot_c,
                  "the driver's probe counts are copied into the snapshot; without them every "
                  "frame would report 0/0 and collapse chamber air to UNKNOWN")
    checker.check("s_snap.door_obs_ms = obs_ms;" in snapshot_c,
                  "the door publication records an observation time (W04 recorded none)")
    checker.check("s_snap.energy_wh = energy_wh;" in snapshot_c and "values.energy_wh" in power_c,
                  "the decoded PZEM energy register reaches the snapshot (W04 logged it only)")
    checker.check("s_snap.thermal_seq = seq;" in snapshot_c and "s_snap.power_seq = seq;" in snapshot_c,
                  "each producer publishes its own sequence into the snapshot")
    for field in ("thermal_age_ms", "power_age_ms", "door_age_ms"):
        checker.check(f"{field}=%llu" in telemetry_c, f"telemetry reports {field}")
    checker.check("UINT64_MAX" in telemetry_c,
                  "an age is saturated, never wrapped, when the clock appears to go backwards")
    checker.check("CG_QUALITY_UNKNOWN" in ds18b20_h and "CG_QUALITY_UNKNOWN" in snapshot_c,
                  "a snapshot before the first thermal publication is UNKNOWN, not INVALID")

    # 4. Quality vocabulary ---------------------------------------------
    for token in ("VALID", "DEGRADED", "INVALID", "UNKNOWN"):
        checker.check(f'#define CG_Q_{token} "{token}"' in quality_c,
                      f"cg_quality.c names the canonical state {token}")
    # The counting direction is the contract (docs/01 924-942 counts *failed*
    # probes). Pinned here so a later edit cannot invert it silently; the C
    # harness owns the arithmetic itself.
    checker.check(quality_c.find("const int failed = in->probes_expected - in->probes_ok;")
                  != -1,
                  "thermal quality counts failed probes, not good probes")
    # DEGRADED is only reachable if the thermal source state is not the strict
    # control gate. Binding this expression is what keeps docs/01 924-942 live.
    checker.check("snap->thermal_quality != CG_QUALITY_INVALID" in telemetry_c,
                  "the thermal source state is derived from the quality word, not from the "
                  "strict control gate, so DEGRADED is reachable")
    checker.check("quality_in.door_age_over_limit = " in telemetry_c
                  and "in->door_age_over_limit" in quality_c,
                  "the door quality gets the same independent age cross-check as thermal and power")
    checker.check(re.search(r"written = snprintf\(buf, cap, \"%\.4f\"", telemetry_c) is not None
                  and "if (written < 0 || (size_t)written >= cap)" in telemetry_c,
                  "a numeric field that cannot fit its buffer becomes the missing token, "
                  "never a truncated prefix of a plausible number")
    checker.check(quality_c.count("return CG_Q_UNKNOWN;") >= 2,
                  "an unobserved source resolves to UNKNOWN")
    checker.check('default:\n            return "UNKNOWN";' in checker.read("firmware/main/cg_ds18b20.c")
                  or 'return "UNKNOWN";' in checker.read("firmware/main/cg_ds18b20.c"),
                  "cg_quality_name maps an out-of-range thermal quality to UNKNOWN, not INVALID")
    for field in ("thermal_quality", "environment_quality", "door_quality", "electrical_quality"):
        checker.check(f"{field}=%s" in telemetry_c, f"telemetry emits {field}")
    checker.check("quality=%s" in telemetry_c and "cg_quality_collapse" in quality_c,
                  "telemetry emits the collapsed overall quality")
    collapse_body = extract_function_body(quality_c, r"const char \*cg_quality_collapse\([^)]*\)")
    checker.check(collapse_body is not None, "cg_quality_collapse was located")
    if collapse_body is not None:
        # The precedence is the order of the returns inside the collapse function,
        # not the order the four #defines happen to appear in.
        order = [name for name in ("CG_Q_INVALID", "CG_Q_UNKNOWN", "CG_Q_DEGRADED", "CG_Q_VALID")
                 if collapse_body.find(f"return {name};") != -1]
        checker.check(order == ["CG_Q_INVALID", "CG_Q_UNKNOWN", "CG_Q_DEGRADED", "CG_Q_VALID"],
                      f"collapse order is INVALID > UNKNOWN > DEGRADED > VALID, found {order}")

    # 5. Producer liveness ----------------------------------------------
    for producer in ("CG_PRODUCER_THERMAL", "CG_PRODUCER_DOOR", "CG_PRODUCER_POWER",
                     "CG_PRODUCER_CONTROL", "CG_PRODUCER_TELEMETRY", "CG_PRODUCER_BME"):
        checker.check(producer in health_h, f"health registry declares {producer}")
    checker.check("cg_health_registry_beat(CG_PRODUCER_THERMAL" in app_main
                  and "cg_health_registry_beat(CG_PRODUCER_DOOR" in app_main,
                  "the thermal and door tasks beat from their own contexts")
    checker.check("cg_health_registry_beat(CG_PRODUCER_POWER" in power_c,
                  "the PZEM task beats once per poll attempt, so a failing poll is still a heartbeat")
    checker.check("cg_health_registry_beat(CG_PRODUCER_CONTROL" in commission_c
                  and "cg_health_registry_beat(CG_PRODUCER_TELEMETRY" in commission_c,
                  "the control loop and the telemetry emitter beat separately")
    # Runtime ordering, not textual order: the producers' beat calls live in the
    # task functions above app_main(), so comparing file positions would fail on
    # correct code. What has to hold is that inside app_main the registry is
    # initialised before the PZEM task starts and before the door/sensor tasks
    # are created.
    app_main_body = extract_function_body(app_main, r"void app_main\(void\)")
    init_index = app_main_body.find("cg_health_registry_init") if app_main_body else -1
    first_task_start = min(
        index
        for index in (
            (app_main_body or "").find("cg_power_start"),
            (app_main_body or "").find('xTaskCreate(door_task'),
            (app_main_body or "").find('xTaskCreate(sensor_task'),
        )
        if index != -1
    ) if app_main_body else -1
    checker.check(init_index != -1 and first_task_start != -1
                  and init_index < first_task_start,
                  "the registry is initialised before any producer task can start")
    checker.check("CG_HEALTH_THERMAL_PERIOD_MS" in config and "CG_HEALTH_DOOR_PERIOD_MS" in config,
                  "producer periods are configuration, not scattered literals")
    checker.check("CG_DOOR_POLL_MS" in config and "door_request_ms=%d" in app_main,
                  "the boot line records the requested door period next to the liveness period, "
                  "so the FreeRTOS tick rounding is visible instead of hidden")
    checker.check("health=%s" in telemetry_c and "health_thermal=%s" in telemetry_c,
                  "telemetry names which producer is unhealthy, not only that something is")
    checker.check("frame->health != NULL ? frame->health->overall : CG_TELEM_HEALTH_UNKNOWN"
                  in telemetry_c,
                  "a frame without a liveness report says UNKNOWN for the overall state")
    checker.check(telemetry_c.count("CG_TELEM_HEALTH_UNKNOWN") >= 2,
                  "both the overall and the per-producer liveness fallbacks are UNKNOWN, "
                  "so one site cannot be quietly changed to OK")
    eval_body = extract_function_body(health_c, r"void cg_health_registry_eval\([^)]*\)")
    beat_body = extract_function_body(health_c, r"void cg_health_registry_beat\([^)]*\)")
    checker.check(eval_body is not None and "CG_HEALTH_LOCK()" in eval_body,
                  "the shared registry is read under a critical section")
    checker.check(beat_body is not None and "CG_HEALTH_LOCK()" in beat_body,
                  "the shared registry is written under a critical section")

    # 6. Applied state ---------------------------------------------------
    # Scoped to the status struct: `outputs_energized` also exists on the private
    # control struct, so a plain substring test would pass with the public field
    # removed.
    status_struct = re.search(r"typedef struct \{.*?\} cg_tec_status_t;", control_h, re.DOTALL)
    checker.check(status_struct is not None and "outputs_energized" in status_struct.group(0),
                  "the controller status exposes what the outputs were left driving")
    checker.check("out->outputs_energized = ctl->outputs_energized;" in control_c,
                  "cg_tec_get_status copies the applied state rather than deriving it from state")
    safe_stop = extract_function_body(control_c, r"static bool safe_stop_outputs\([^)]*\)")
    checker.check(safe_stop is not None and "if (ok) {\n        ctl->outputs_energized = false;"
                  in safe_stop,
                  "a failed disengage must not clear outputs_energized: claiming OFF while the "
                  "branch is still being driven is the most dangerous field in the frame")
    applied_body = extract_function_body(telemetry_c,
                                         r"static const char \*cooling_evidence\([^)]*\)")
    checker.check(applied_body is not None, "the cooling_evidence helper was located")
    checker.check(applied_body is not None and "duty_permille" not in applied_body,
                  "cooling evidence is never inferred from the requested duty")
    checker.check("tec.outputs_energized ? CG_TELEM_APPLIED_ON : CG_TELEM_APPLIED_OFF" in telemetry_c,
                  "cooling_applied comes from the output layer's own record")
    for token in ("MEASURED_APPLIED_AND_DRAWING", "MEASURED_IDLE_AND_ZERO",
                  "MEASURED_CONTRADICTS_APPLIED", "UNOBSERVED_STALE", "UNOBSERVED_NO_DATA"):
        checker.check(f'"{token}"' in telemetry_h, f"evidence token {token} is declared")
    checker.check("CG_TELEM_EVIDENCE_STALE" in (applied_body or ""),
                  "a stale electrical reading is reported as unobserved, not as an idle branch")

    # 7. Host parity -----------------------------------------------------
    checker.check(define_value(config, "CG_TELEMETRY_SCHEMA_VERSION")
                  == str(telemetry_schema.SCHEMA_VERSION),
                  "firmware and host agree on the current serial schema version")
    checker.check(telemetry_schema.SUPPORTED_SCHEMAS[0] == 1,
                  "the host parser still accepts schema 1, so committed W04 captures parse")
    # Parity is asserted on the emitted `key=` token, not on the bare name: the
    # four ROM channels are formatted through rom_keys[], so their names appear
    # in a table even if the emit were deleted. They have their own check above.
    rom_fields = {"t1_rom", "t2_rom", "t3_rom", "spare_rom"}
    for field in telemetry_schema.W05_REQUIRED_FIELDS:
        if field in rom_fields:
            checker.check(f'"{field}"' in telemetry_c,
                          f"the formatter names the W05 required field {field} in its key table")
            continue
        checker.check(f"{field}=" in telemetry_c,
                      f"telemetry emits the W05 required field {field}")

    # 8. Scope guard -----------------------------------------------------
    checker.check(define_value(config, "CG_TEC_OUTPUT_STAGE_ENABLED") == "0",
                  "W05 did not enable the TEC output stage")
    checker.check(define_value(config, "CG_TEC_REQUEST_DUTY_PERMILLE") == "0",
                  "W05 did not introduce a requested duty")
    for source in ("firmware/main/cg_quality.c", "firmware/main/cg_health.c",
                   "firmware/main/cg_telemetry.c"):
        text = checker.read(source)
        checker.check(w04.NETWORK_TOKEN.search(strip_comments(text)) is None,
                      f"{source} opens no network entry point")
    cmake = checker.read("firmware/main/CMakeLists.txt")
    for source in ("cg_quality.c", "cg_health.c"):
        checker.check(f'"{source}"' in cmake, f"{source} is in the build")

    return checker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Static contract checks for the W05 telemetry foundation sources."
    )
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    args = parser.parse_args(argv)

    try:
        checker = run_checks()
    except OSError as exc:
        print(f"cannot read firmware sources: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        for note in checker.notes:
            print(note)

    if checker.failures:
        print()
        print("W05 STATIC FIRMWARE CHECK: FAIL")
        for failure in checker.failures:
            print(f"  - {failure}")
        return 1

    print()
    print(f"W05 STATIC FIRMWARE CHECK: PASS ({len(checker.notes)} checks)")
    print("Reminder: this does NOT compile the firmware and does not touch hardware.")
    print("The compile check is the ESP-IDF v6.1 build; the executable behaviour check is")
    print("firmware/tools/tests/cg_w05_harness.c run through test_cg_w05_harness.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
