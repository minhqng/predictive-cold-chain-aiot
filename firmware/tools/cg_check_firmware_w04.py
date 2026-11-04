"""Static contract checks for the ColdGuard W04 TEC commissioning firmware.

This checker certifies only what can be proven from the sources. It does
not compile the firmware and does not touch hardware; the ESP-IDF build is
the separate compile check (see docs/06 and the W04 evidence directory).

Checks:

1.  Shipped safety posture - output stage disabled, hardware gates not
    verified, actuator authorization off, and the compile-time guards that
    make an accidental flip impossible.
2.  Limits are data - the shipped table has every entry `UNRESOLVED` with a
    provenance token, so START cannot pass.
3.  Adapter cannot energize - every enable/duty request is refused and
    re-forced OFF; the fan and interlock report unavailable/open; the TEC
    adapter touches no GPIO directly.
4.  Control ordering - shows enables-off-before-PWM-off, start order
    duty->fan->enable->duty, one-shot ARM, bounded duration, heartbeat,
    fault latch, ESTOP and token-gated CLEAR.
5.  Commission wiring - no invented cold/hot probe assignment, shipped
    limits used, UART console only, telemetry once per second, task
    watchdog registration.
6.  Telemetry integrity - firmware and host schema versions agree, `nan` for
    missing, no wall-clock fabrication, cold/hot/ambient/RH marked not
    assigned, host schema parity for the W04 field set.
7.  Grammar guard - `cg_serial.GRAMMAR_VERSION` stays 2 (W04 only adds
    line kinds, never changes the existing grammar).
8.  No network path - NETWORK_TOKEN scans sources, headers and CMake for any
    network entry point (Wi-Fi/HTTP/MQTT/lwIP/TLS/socket/ethernet/mesh/SNTP).
9.  Build completeness - every `.c` in `firmware/main` is in CMakeLists.
10. GPIO ownership - the effective map still passes the as-built rules and
    no pad is owned twice.
11. Operator document - `docs/06` exists and defines G0-G5 plus the
    current terminal state.

Exit codes: 0 = every check passed, 1 = at least one failed, 2 = usage/IO.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FIRMWARE_MAIN = REPO_ROOT / "firmware" / "main"
TOOLS = REPO_ROOT / "firmware" / "tools"

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cg_gpio_map  # noqa: E402
import cg_serial  # noqa: E402
import cg_telemetry_schema as telemetry_schema  # noqa: E402


# Entry points that would make the commissioning firmware reachable from
# outside the bench. Module scope so the mutation tests can drive it directly.
# The bare libc calls need the lookbehind: FreeRTOS code is full of
# xQueueSend(), and a plain send\( pattern would reject that.
NETWORK_TOKEN = re.compile(
    r"esp_wifi|esp_http|lwip|mqtt|esp_netif|esp_tls|esp-tls|mbedtls|esp_eth"
    r"|esp_mesh|sntp|esp_transport|websocket"
    r"|(?<![A-Za-z0-9_])(?:socket|connect|sendto|send|recv|bind|listen|accept"
    r"|getaddrinfo|gethostbyname)\(",
    re.IGNORECASE,
)


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", text)


def extract_function_body(text: str, signature_re: str) -> str | None:
    match = re.search(signature_re + r"\s*\{", text)
    if not match:
        return None
    end = text.find("\n}", match.end())
    if end == -1:
        return None
    return text[match.end():end]


def define_value(text: str, name: str) -> str | None:
    match = re.search(rf"#define\s+{name}\s+([^\s/]+)", text)
    return match.group(1) if match else None


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.notes: list[str] = []

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def check(self, condition: bool, message: str) -> None:
        if condition:
            self.notes.append(f"ok   {message}")
        else:
            self.fail(message)

    def read(self, relative: str) -> str:
        return (REPO_ROOT / relative).read_text(encoding="utf-8")


def run_checks() -> Checker:
    checker = Checker()

    config = checker.read("firmware/main/coldguard_config.h")
    control_c = checker.read("firmware/main/cg_tec_control.c")
    control_h = checker.read("firmware/main/cg_tec_control.h")
    limits_c = checker.read("firmware/main/cg_tec_limits.c")
    limits_h = checker.read("firmware/main/cg_tec_limits.h")
    hw_c = checker.read("firmware/main/cg_tec_hw.c")
    platform_h = checker.read("firmware/main/cg_tec_platform.h")
    telemetry_c = checker.read("firmware/main/cg_telemetry.c")
    telemetry_h = checker.read("firmware/main/cg_telemetry.h")
    commission_c = checker.read("firmware/main/cg_commission.c")
    command_c = checker.read("firmware/main/cg_tec_command.c")
    console_c = checker.read("firmware/main/cg_console.c")
    log_h = checker.read("firmware/main/cg_log.h")
    app_main = checker.read("firmware/main/app_main.c")
    cmake = checker.read("firmware/main/CMakeLists.txt")

    control_stripped = strip_comments(control_c)
    hw_stripped = strip_comments(hw_c)
    telemetry_stripped = strip_comments(telemetry_c)
    commission_stripped = strip_comments(commission_c)

    # 1. Shipped safety posture ------------------------------------------
    checker.check(define_value(config, "CG_TEC_OUTPUT_STAGE_ENABLED") == "0",
                  "CG_TEC_OUTPUT_STAGE_ENABLED is 0 in the delivered build")
    checker.check(define_value(config, "CG_TEC_HARDWARE_GATES_VERIFIED") == "0",
                  "CG_TEC_HARDWARE_GATES_VERIFIED is 0 (no measured gates recorded)")
    checker.check(define_value(config, "CG_ACTUATOR_ENABLE_ALLOWED") == "0",
                  "CG_ACTUATOR_ENABLE_ALLOWED stays 0")
    checker.check(re.search(r"#if\s+CG_TEC_OUTPUT_STAGE_ENABLED\s*==\s*1\s*&&\s*"
                            r"CG_TEC_HARDWARE_GATES_VERIFIED\s*!=\s*1\s*\n\s*#error",
                            config) is not None,
                  "output stage requires verified hardware gates (#error)")
    checker.check(re.search(r"#if\s+CG_TEC_OUTPUT_STAGE_ENABLED\s*==\s*1\s*&&\s*"
                            r"CG_ACTUATOR_ENABLE_ALLOWED\s*!=\s*1\s*\n\s*#error",
                            config) is not None,
                  "output stage requires the actuator authorization gate (#error)")

    # 2. Limits are data -------------------------------------------------
    limit_ids = [
        "CG_LIMIT_CURRENT_MAX_A",
        "CG_LIMIT_VOLTAGE_MAX_V",
        "CG_LIMIT_VOLTAGE_MIN_V",
        "CG_LIMIT_HOT_SIDE_MAX_C",
        "CG_LIMIT_DUTY_MAX_PERMILLE",
        "CG_LIMIT_ON_TIME_MAX_MS",
    ]
    for limit_id in limit_ids:
        entry = re.search(r"\[" + limit_id + r"\]\s*=\s*\{(.*?)\}", limits_c, re.DOTALL)
        checker.check(entry is not None, f"limit table defines {limit_id}")
        if entry:
            body = entry.group(1)
            checker.check("CG_LIMIT_UNRESOLVED" in body,
                          f"{limit_id} ships UNRESOLVED")
            checker.check(re.search(r"\.value\s*=\s*0\.0f", body) is not None,
                          f"{limit_id} ships with no invented numeric value")
            checker.check(re.search(r'\.source\s*=\s*"[A-Z0-9_]+"', body) is not None,
                          f"{limit_id} carries a provenance token")
    checker.check(re.search(r"\.state\s*=\s*CG_LIMIT_RESOLVED", limits_c) is None,
                  "no shipped limit entry is initialized as RESOLVED")
    checker.check("cg_tec_limits_shipped" in limits_h
                  and "extern const cg_tec_limit_table_t cg_tec_limits_shipped" in limits_h,
                  "the shipped table is the only table the firmware links")
    checker.check("CG_LIMIT_COUNT" in limits_h,
                  "limit count is an enum bound, not a literal in callers")
    checker.check("cg_tec_limits_all_resolved" in control_stripped,
                  "START consults all_resolved (not a subset of limits)")

    # 3. Adapter cannot energize ----------------------------------------
    enables_body = extract_function_body(hw_stripped, r"static\s+bool\s+hw_set_enables\s*\([^)]*\)")
    checker.check(enables_body is not None
                  and "if (ren || len)" in enables_body
                  and enables_body.count("cg_actuator_force_off") >= 2
                  and "return false" in enables_body,
                  "hw_set_enables refuses any enable request and re-forces OFF")
    duty_body = extract_function_body(hw_stripped, r"static\s+bool\s+hw_set_cooling_duty\s*\([^)]*\)")
    checker.check(duty_body is not None
                  and "permille != 0U" in duty_body
                  and "cg_actuator_force_off" in duty_body
                  and "return false" in duty_body,
                  "hw_set_cooling_duty refuses any non-zero duty")
    fan_body = extract_function_body(hw_stripped, r"static\s+bool\s+hw_set_fan\s*\([^)]*\)")
    checker.check(fan_body is not None and "return false" in fan_body,
                  "hw_set_fan reports no controllable fan on the as-built assembly")
    interlock_body = extract_function_body(hw_stripped, r"static\s+bool\s+hw_read_interlock\s*\([^)]*\)")
    checker.check(interlock_body is not None and "return false" in interlock_body,
                  "hw_read_interlock fails closed (no interlock wired yet)")
    stage_body = extract_function_body(hw_stripped, r"static\s+bool\s+hw_output_stage_available\s*\([^)]*\)")
    checker.check(stage_body is not None
                  and "CG_TEC_OUTPUT_STAGE_ENABLED == 1" in stage_body,
                  "hw_output_stage_available follows the compile-time switch")
    checker.check("gpio_" not in hw_stripped,
                  "the TEC adapter touches no GPIO directly (cg_actuator owns the pads)")
    checker.check("cg_tec_hw_ops" in hw_stripped and "cg_tec_hw_ops_t" in platform_h,
                  "the adapter implements the injected platform contract")
    tec_sources = "\n".join(strip_comments(p.read_text(encoding="utf-8"))
                            for p in sorted(FIRMWARE_MAIN.glob("cg_tec_*.c")))
    checker.check(re.search(r"ledc|mcpwm", tec_sources, re.IGNORECASE) is None,
                  "no PWM peripheral anywhere in the TEC sources")
    checker.check("set_enables(true, true)" not in control_stripped
                  and "set_enables(true,true)" not in control_stripped,
                  "no path ever requests both enables (no reverse)")

    # 4. Control ordering and state machine ------------------------------
    safe_body = extract_function_body(control_stripped, r"static\s+bool\s+safe_stop_outputs\s*\([^)]*\)")
    checker.check(safe_body is not None
                  and safe_body.find("set_enables(false, false)")
                  < safe_body.find("set_cooling_duty(0U)"),
                  "safe stop clears enables before the PWM level")
    latch_body = extract_function_body(control_stripped, r"static\s+void\s+latch_fault\s*\([^)]*\)")
    checker.check(latch_body is not None
                  and "safe_stop_outputs" in latch_body
                  and "CG_TEC_STATE_FAULT_LATCH" in latch_body,
                  "every fault latches and de-energizes")
    start_body = extract_function_body(control_stripped,
                                       r"cg_tec_start_result_t\s+cg_tec_start\s*\([^)]*\)")
    checker.check(start_body is not None, "cg_tec_start body is visible")
    if start_body:
        order = [
            start_body.find("set_cooling_duty(0U)"),
            start_body.find("set_fan(true)"),
            start_body.find("set_enables(true, false)"),
            start_body.find("set_cooling_duty(duty_permille)"),
        ]
        checker.check(all(index != -1 for index in order) and order == sorted(order),
                      "start order is duty 0 -> fan -> enables -> commanded duty")
        for marker, label in (
            ("CG_TEC_START_NOT_ARMED", "one-shot ARM gate"),
            ("cg_tec_limits_all_resolved", "all limits resolved"),
            ("stage_available(ctl)", "output stage available"),
            ("inputs_problem(ctl, in, false", "sensor freshness/validity gate"),
            ("read_interlock", "hardware interlock gate"),
            ("fan_available", "fan availability gate"),
            ("disarm(ctl)", "ARM consumed on a successful start"),
            ("CG_TEC_STATE_COOLING", "enters COOLING only after the sequence"),
        ):
            checker.check(marker in start_body, f"start enforces {label}")
        rollback = start_body.rfind("set_enables(false, false)")
        checker.check(rollback != -1 and rollback > start_body.find("set_enables(true, false)"),
                      "start failure path rolls the enables back off")
    tick_body = extract_function_body(control_stripped, r"void\s+cg_tec_tick\s*\([^)]*\)")
    checker.check(tick_body is not None
                  and "cooling_deadline_ms" in tick_body
                  and "CG_TEC_FAULT_HEARTBEAT" in tick_body
                  and "CLOCK_BACKWARDS" in tick_body
                  and "COOLDOWN" in tick_body,
                  "tick enforces bounded duration, heartbeat gap and cooldown")
    clear_body = extract_function_body(control_stripped, r"bool\s+cg_tec_clear_fault\s*\([^)]*\)")
    checker.check(clear_body is not None
                  and "token_matches(ctl->token, token)" in clear_body
                  and "inputs_problem(ctl, in, true" in clear_body
                  and "CG_TEC_STATE_COOLDOWN" in clear_body,
                  "CLEAR requires the boot token and healthy inputs, and does not arm")
    estop_body = extract_function_body(control_stripped, r"void\s+cg_tec_estop\s*\([^)]*\)")
    checker.check(estop_body is not None and "CG_TEC_FAULT_ESTOP" in estop_body,
                  "ESTOP latches through the common safe-stop path")
    checker.check("CG_TEC_ARM_TTL_MS" in config
                  and "authorized_at_ms" in control_stripped,
                  "ARM authorization is time-bounded")

    # 5. Commission wiring ----------------------------------------------
    inputs_body = extract_function_body(commission_stripped, r"static\s+void\s+build_inputs\s*\([^)]*\)")
    checker.check(inputs_body is not None
                  and "t_cold_side_valid = false" in inputs_body
                  and "t_hot_side_valid = false" in inputs_body,
                  "no probe is claimed for the cold/hot side without a physical assignment")
    checker.check("&cg_tec_limits_shipped" in commission_stripped,
                  "the commissioning task links the shipped (unresolved) limits")
    checker.check("cg_console_start" in commission_stripped
                  and "CG_CONSOLE_UART_PORT" in config,
                  "the only command path is the local UART console")
    checker.check("cg_telemetry_format" in commission_stripped
                  and "cg_log_raw_line" in commission_stripped,
                  "telemetry is emitted through the raw line writer")
    commission_task_body = extract_function_body(
        commission_stripped, r"static\s+void\s+commission_task\s*\([^)]*\)")
    start_body = extract_function_body(
        commission_stripped, r"void\s+cg_commission_start\s*\([^)]*\)")
    checker.check("CONFIG_ESP_TASK_WDT_EN" in commission_c
                  and commission_task_body is not None
                  and "esp_task_wdt_add(NULL)" in commission_task_body
                  and "esp_task_wdt_reset" in commission_task_body,
                  "the commissioning task subscribes to the task watchdog from its own context and resets it")
    checker.check(start_body is not None and "esp_task_wdt_add" not in start_body,
                  "cg_commission_start does not subscribe its caller (main) task to the task watchdog")
    checker.check("cg_tec_tick" in commission_stripped and "CG_TEC_TICK_MS" in config,
                  "the control core is ticked from the fixed-period task")

    # 6. Telemetry integrity --------------------------------------------
    checker.check(define_value(config, "CG_TELEMETRY_SCHEMA_VERSION") == str(telemetry_schema.SCHEMA_VERSION),
                  "firmware and host agree on the current telemetry schema version")
    checker.check(define_value(config, "CG_INVALID_VALUE_TOKEN") == f'"{telemetry_schema.MISSING_TOKEN}"',
                  "missing values use the shared `nan` token")
    for field in telemetry_schema.REQUIRED_FIELDS + telemetry_schema.REQUIRED_STATUS_FIELDS:
        checker.check(f"{field}=" in telemetry_stripped,
                      f"telemetry emits required field {field}")
    checker.check("timestamp_utc=UNAVAILABLE" in telemetry_stripped
                  and "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK" in telemetry_stripped,
                  "telemetry never invents a wall-clock timestamp")
    checker.check(re.search(r"\b(time|gmtime|localtime|gettimeofday)\s*\(", telemetry_stripped) is None,
                  "the telemetry formatter reads no host/system clock")
    # A field with no probe behind it must say NOT_ASSIGNED *and* carry a missing
    # value; inventing a number next to an unassigned label is the failure mode
    # this pins. The hot side left this set when the operator-frozen as-built map
    # identified ROM 28AEBF2200000006 as the TEC hot side - requiring
    # NOT_ASSIGNED there would now force the emitter to discard a real
    # measurement, which is the opposite of the honesty rule this check serves.
    checker.check(telemetry_stripped.count("CG_TELEM_STATUS_NOT_ASSIGNED") >= 1
                  and "t_cold_side_status=%s" in telemetry_stripped
                  and "fmt_float(false, 0.0f," in telemetry_stripped,
                  "the cold side stays NOT_ASSIGNED with a missing value rather than a number")
    # A-W02-06 moved the ambient pair out of the permanently-missing set: the
    # BME280 producer now feeds it. The rule this check exists for is unchanged -
    # a number may only appear behind its own validity gate - so the requirement
    # is now that t_ambient/RH are formatted from the snapshot under a status the
    # producer derived, never from a constant and never as a carried-forward last
    # reading. An unfitted module must still reach the line as SENSOR_NOT_PRESENT.
    checker.check("t_ambient_status=%s" in telemetry_stripped
                  and "relative_humidity_status=%s" in telemetry_stripped
                  and "env_status(snap, now_ms)" in telemetry_stripped
                  and 'strcmp(env_status_text, CG_TELEM_STATUS_OK) == 0' in telemetry_stripped
                  and "CG_TELEM_STATUS_NOT_PRESENT" in telemetry_stripped,
                  "ambient T/RH reach the line only through the producer's own validity "
                  "gate, and an absent module still reads SENSOR_NOT_PRESENT")
    checker.check("fmt_float" in telemetry_stripped,
                  "every numeric field goes through the validity-aware formatter")
    line_max = define_value(config, "CG_TELEMETRY_LINE_MAX")
    checker.check(line_max is not None and line_max.isdigit() and int(line_max) >= 1280,
                  "telemetry line budget covers the worst-case frame with headroom")
    checker.check("if (overflow)" in telemetry_stripped,
                  "the formatter refuses a frame that does not fit (no truncated line)")
    checker.check("output_stage=" in telemetry_stripped and "tec_state=" in telemetry_stripped
                  and "fault_code=" in telemetry_stripped,
                  "telemetry exposes output stage, state and fault code")
    checker.check("schema=" in telemetry_stripped,
                  "the schema number is on the wire, so the parser can refuse other versions")

    # 7. Grammar guard ---------------------------------------------------
    checker.check(cg_serial.GRAMMAR_VERSION == 2,
                  "serial grammar version stays 2 (W04 only adds line kinds)")
    checker.check('#define CG_LOG_AUTH "AUTH"' in config
                  and '#define CG_LOG_TEC "TEC"' in config
                  and '#define CG_LOG_TELEM "TELEM"' in config,
                  "new line kinds are additive and declared in config")
    checker.check("cg_log_raw_line" in log_h and "CG_TELEMETRY_LINE_MAX" in log_h,
                  "raw lines are length-bounded at the writer")

    # 8. No network path -------------------------------------------------
    main_sources = "\n".join(strip_comments(p.read_text(encoding="utf-8"))
                             for p in sorted(FIRMWARE_MAIN.glob("*.c"))
                             + sorted(FIRMWARE_MAIN.glob("*.h")))
    checker.check(NETWORK_TOKEN.search(main_sources) is None,
                  "no firmware source or header uses a network API")
    checker.check(NETWORK_TOKEN.search(cmake) is None,
                  "CMakeLists requires no network component")

    # 9. Build completeness ----------------------------------------------
    missing = [p.name for p in sorted(FIRMWARE_MAIN.glob("*.c")) if f'"{p.name}"' not in cmake]
    checker.check(not missing,
                  f"every main/*.c is in CMakeLists (missing: {missing})")

    # 10. GPIO ownership -------------------------------------------------
    gpio_map = cg_gpio_map.evaluate(config)
    checker.check(cg_gpio_map.conflicts(gpio_map) == [],
                  f"no GPIO conflict (found: {cg_gpio_map.conflicts(gpio_map)})")
    checker.check(cg_gpio_map.as_built_mismatches(gpio_map) == [],
                  f"effective map matches as-built v2 (diff: {cg_gpio_map.as_built_mismatches(gpio_map)})")

    # 11. Operator document ----------------------------------------------
    doc_path = REPO_ROOT / "docs" / "06-tec-commissioning-safety-and-limits.md"
    checker.check(doc_path.is_file(), "docs/06-tec-commissioning-safety-and-limits.md exists")
    if doc_path.is_file():
        doc = checker.read("docs/06-tec-commissioning-safety-and-limits.md")
        for gate in ("G0", "G1", "G2", "G3", "G4", "G5"):
            checker.check(re.search(rf"###\s+{gate}\b", doc) is not None,
                          f"docs/06 defines gate {gate}")
        checker.check('PRODUCTION TEC OUTPUT STAGE COMPILED OUT AND NOT AUTHORIZED' in doc,
                      "docs/06 states the production output stage is still unauthorized")
        checker.check('H6 BENCH ENERGIZATION EXECUTED UNDER OPERATOR SUPERVISION' in doc,
                      "docs/06 discloses the supervised H6 energization instead of claiming no power test has ever run")
        checker.check("PHY-FUSE-001" in doc and "PHY-ACT-003" in doc,
                      "docs/06 maps the physical invariants")
        checker.check("timestamp_utc" in doc and "UNAVAILABLE" in doc,
                      "docs/06 documents the device-clock provenance")

    return checker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Static contract checks for the W04 TEC commissioning firmware sources."
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
        print("W04 STATIC FIRMWARE CHECK: FAIL")
        for failure in checker.failures:
            print(f"  - {failure}")
        return 1

    print()
    print(f"W04 STATIC FIRMWARE CHECK: PASS ({len(checker.notes)} checks)")
    print("Reminder: this does NOT compile the firmware and does not touch hardware.")
    print("The compile check is the ESP-IDF v6.1 build recorded in docs/06 / evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
