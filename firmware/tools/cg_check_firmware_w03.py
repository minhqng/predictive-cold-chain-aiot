"""Static contract checks for the ColdGuard W03 power/RS-485/PZEM firmware.

The team machine has no ESP-IDF installation (the compile check runs on
GitHub Actions), so this script checks the invariants that *can* be checked
from the sources and refuses to certify anything it cannot see:

1.  Register map parity - the PZEM register addresses, range codes and LSB
    scalings in `coldguard_config.h` must equal the host-side reference in
    `firmware/tools/cg_modbus.py` (docs/01 section 9.3).
2.  READ-ONLY - no write function code (0x05/0x06/0x0F/0x10) may exist in
    the PZEM protocol module, and the host codec refuses non-read builders
    (A-W03-04: a register write must not be possible, not merely unused).
3.  CRC16/MODBUS - init 0xFFFF, polynomial 0xA001, validated *before* any
    field of a response is trusted.
4.  Transport - UART framing comes from named configuration macros with
    compile-time validation, the default direction mode is AUTO (as-built
    module has no DE/RE; the MAX3485-shaped manual mode is compiled out),
    and retries are bounded (a timeout is a classified result, not an
    infinite loop).
5.  Error classification - the C status tokens equal the host
    `cg_modbus.Status` token set, so a capture can be re-decoded host-side.
6.  Scaling in C - power/energy are 32-bit little-word-first and all four
    quantities use the configured LSB macros.
7.  Actuator default-OFF - `CG_ACTUATOR_ENABLE_ALLOWED` is 0, the W03
    firmware contains no PWM peripheral usage, no path writes a 1 to the
    two actuator pins, force_off clears enable before PWM, and the guard
    refuses output while authorization is absent.
8.  Boot order - the actuator is forced off before NVS, sensor init, task
    creation and the PZEM poll task.
9.  Log grammar - the PZEM line kinds and fields the host parser expects
    are declared and used.
10. Build completeness - every `.c` file in `firmware/main` is listed in
    `CMakeLists.txt`.
11. GPIO ownership - the effective map equals the as-built map v2, no pad
    is owned twice, flash/PSRAM/strapping pins are rejected, a MANUAL
    DE/RE on the MC-38 pin (GPIO35) is rejected, and the actuator safe-OFF
    drives RPWM + R_EN + L_EN low with the enables cleared first.

Exit codes: 0 = every check passed, 1 = at least one check failed,
2 = usage/IO error.
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

import cg_gpio_map  # noqa: E402  (shared GPIO ownership rules)

FORBIDDEN_WRITE_FC = re.compile(r"0[xX](?:05|06|0[Ff]|10)\b")
STATUS_TOKEN_RE = re.compile(r'return\s+"([A-Z_]+)"\s*;')

# Two decimal LSB values are compared as integers of 1/100 units to avoid
# float comparison surprises.
LSB_SCALE = 100


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", text)


def extract_function_body(text: str, signature_re: str) -> str | None:
    """Return a function body whose closing brace starts at column zero."""

    match = re.search(signature_re + r"\s*\{", text)
    if not match:
        return None
    end = text.find("\n}", match.end())
    if end == -1:
        return None
    return text[match.end():end]


def define_int(text: str, name: str) -> int | None:
    match = re.search(rf"#define\s+{name}\s+([^\s/]+)", text)
    if not match:
        return None
    try:
        return int(match.group(1), 0)
    except ValueError:
        return None


def define_float(text: str, name: str) -> float | None:
    match = re.search(rf"#define\s+{name}\s+([^\s/]+)", text)
    if not match:
        return None
    token = match.group(1)
    if token.endswith(("f", "F")):
        token = token[:-1]
    try:
        return float(token)
    except ValueError:
        return None


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
    crc16_c = checker.read("firmware/main/cg_crc16.c")
    pzem_c = checker.read("firmware/main/cg_pzem.c")
    pzem_h = checker.read("firmware/main/cg_pzem.h")
    power_c = checker.read("firmware/main/cg_power.c")
    rs485_c = checker.read("firmware/main/cg_rs485.c")
    actuator_c = checker.read("firmware/main/cg_actuator.c")
    actuator_h = checker.read("firmware/main/cg_actuator.h")
    safety_c = checker.read("firmware/main/cg_safety.c")
    door_c = checker.read("firmware/main/cg_door.c")
    onewire_c = checker.read("firmware/main/cg_onewire.c")
    ds18b20_c = checker.read("firmware/main/cg_ds18b20.c")
    log_h = checker.read("firmware/main/cg_log.h")
    app_main = checker.read("firmware/main/app_main.c")
    cmake = checker.read("firmware/main/CMakeLists.txt")

    sys.path.insert(0, str(TOOLS))
    import cg_modbus  # type: ignore

    # 1. Register/scaling parity with the host reference -------------------
    parity_ints = [
        ("CG_PZEM_REG_VOLTAGE", cg_modbus.REG_VOLTAGE),
        ("CG_PZEM_REG_CURRENT", cg_modbus.REG_CURRENT),
        ("CG_PZEM_REG_POWER_L", cg_modbus.REG_POWER_L),
        ("CG_PZEM_REG_POWER_H", cg_modbus.REG_POWER_H),
        ("CG_PZEM_REG_ENERGY_L", cg_modbus.REG_ENERGY_L),
        ("CG_PZEM_REG_ENERGY_H", cg_modbus.REG_ENERGY_H),
        ("CG_PZEM_REG_INPUT_COUNT", cg_modbus.INPUT_REGISTER_COUNT),
        ("CG_PZEM_HOLDING_CURRENT_RANGE", cg_modbus.HOLDING_CURRENT_RANGE),
        ("CG_PZEM_RANGE_100A", cg_modbus.RANGE_100A),
        ("CG_PZEM_RANGE_50A", cg_modbus.RANGE_50A),
        ("CG_PZEM_RANGE_200A", cg_modbus.RANGE_200A),
        ("CG_PZEM_RANGE_300A", cg_modbus.RANGE_300A),
        ("CG_PZEM_FC_READ_HOLDING", cg_modbus.FC_READ_HOLDING),
        ("CG_PZEM_FC_READ_INPUT", cg_modbus.FC_READ_INPUT),
    ]
    for macro, expected in parity_ints:
        actual = define_int(config, macro)
        checker.check(
            actual == expected,
            f"{macro} == {expected:#06x} as in cg_modbus.py (got {actual})",
        )

    parity_floats = [
        ("CG_PZEM_VOLT_LSB", cg_modbus.VOLT_LSB),
        ("CG_PZEM_CURRENT_LSB", cg_modbus.CURRENT_LSB),
        ("CG_PZEM_POWER_LSB", cg_modbus.POWER_LSB),
        ("CG_PZEM_ENERGY_LSB", cg_modbus.ENERGY_LSB),
    ]
    for macro, expected in parity_floats:
        actual = define_float(config, macro)
        checker.check(
            actual is not None and abs(actual - expected) < 1e-9,
            f"{macro} == {expected} as in cg_modbus.py (got {actual})",
        )

    # 2. READ-ONLY ---------------------------------------------------------
    pzem_c_stripped = strip_comments(pzem_c)
    pzem_h_stripped = strip_comments(pzem_h)
    write_hits = FORBIDDEN_WRITE_FC.findall(pzem_c_stripped + pzem_h_stripped)
    checker.check(
        not write_hits,
        f"cg_pzem.{{c,h}} contains no write function code (found: {write_hits})",
    )
    for token in ("build_write", "write_register", "write_holding", "FC_WRITE"):
        checker.check(
            token not in pzem_c_stripped and token not in pzem_h_stripped,
            f"cg_pzem.{{c,h}} has no {token} path",
        )
    checker.check(
        "cg_pzem_build_read_input" in pzem_c and "cg_pzem_build_read_range" in pzem_c,
        "cg_pzem builds exactly the two documented read requests",
    )
    modbus_py = checker.read("firmware/tools/cg_modbus.py")
    checker.check(
        "only read function codes 0x03/0x04 are allowed" in modbus_py,
        "cg_modbus.py refuses non-read function codes in build_read_request",
    )
    checker.check(
        not FORBIDDEN_WRITE_FC.findall(strip_comments_python(modbus_py)),
        "cg_modbus.py contains no write function code literal",
    )

    # 3. CRC16/MODBUS ------------------------------------------------------
    crc_stripped = strip_comments(crc16_c)
    checker.check(
        "0xFFFF" in crc_stripped and "0xA001" in crc_stripped,
        "cg_crc16 uses init 0xFFFF and polynomial 0xA001",
    )
    checker.check(
        "cg_crc16_check" in crc_stripped and "cg_crc16_append" in crc_stripped,
        "cg_crc16 exposes check (RX) and append (low byte first) helpers",
    )
    parse_input_body = extract_function_body(
        pzem_c_stripped, r"cg_pzem_status_t\s+cg_pzem_parse_input\s*\([^)]*\)"
    )
    parse_range_body = extract_function_body(
        pzem_c_stripped, r"cg_pzem_status_t\s+cg_pzem_parse_range\s*\([^)]*\)"
    )
    for name, body in (
        ("cg_pzem_parse_input", parse_input_body),
        ("cg_pzem_parse_range", parse_range_body),
    ):
        checker.check(
            body is not None
            and body.find("cg_crc16_check") != -1
            and body.find("cg_crc16_check") < body.find("frame[0]"),
            f"{name} validates CRC before trusting any frame field",
        )
        checker.check(
            body is not None
            and "CG_PZEM_EXCEPTION_FRAME_LEN" in body
            and "BAD_FUNCTION" in body
            and "frame[1] != (uint8_t)" in body,
            f"{name} accepts only the matching exception function and length",
        )

    # 4. Transport / retry bound ------------------------------------------
    checker.check(
        define_int(config, "CG_RS485_DIR_MODE") == 0,
        "default direction mode is AUTO (as-built module has no DE/RE)",
    )
    checker.check(
        define_int(config, "CG_RS485_DATA_BITS") == 8
        and define_int(config, "CG_RS485_PARITY") == 0
        and define_int(config, "CG_RS485_STOP_BITS") in (1, 2),
        "8N1-class framing configured via named macros (no assumption hidden in the driver)",
    )
    rs485_stripped = strip_comments(rs485_c)
    for guard in (
        '#if CG_RS485_PARITY != 0 && CG_RS485_PARITY != 1 && CG_RS485_PARITY != 2',
        "#if CG_RS485_STOP_BITS != 1 && CG_RS485_STOP_BITS != 2",
        "#if CG_RS485_DATA_BITS != 8",
    ):
        checker.check(guard in rs485_stripped, f"cg_rs485.c has compile-time guard: {guard}")
    checker.check(
        "UART_DATA_8_BITS" in rs485_stripped and "UART_SCLK_DEFAULT" in rs485_stripped,
        "cg_rs485 maps the configuration onto the UART driver",
    )
    manual_blocks = re.findall(
        r"#if\s+CG_RS485_DIR_MODE\s*==\s*CG_RS485_DIR_MANUAL(.*?)#endif",
        rs485_stripped,
        re.DOTALL,
    )
    checker.check(
        bool(manual_blocks),
        "DE/RE drive exists only behind the MANUAL compile-time branch",
    )
    de_pin_outside_manual = re.sub(
        r"#if\s+CG_RS485_DIR_MODE\s*==\s*CG_RS485_DIR_MANUAL.*?#endif", " ", rs485_stripped, flags=re.DOTALL
    )
    checker.check(
        "CG_PIN_RS485_DE_RE" not in de_pin_outside_manual,
        "no DE/RE pin access outside the MANUAL branch (AUTO build never touches GPIO35)",
    )
    checker.check(
        "cg_rs485_write" in rs485_stripped
        and "cg_rs485_read" in rs485_stripped
        and "cg_rs485_flush_input" in rs485_stripped,
        "cg_rs485 exposes write/read/flush primitives",
    )

    power_stripped = strip_comments(power_c)
    checker.check(
        re.search(
            r"for\s*\(\s*uint8_t\s+attempt\s*=\s*1\s*;\s*attempt\s*<=\s*CG_PZEM_MAX_ATTEMPTS\s*;",
            power_stripped,
        )
        is not None,
        "retry loop is bounded by CG_PZEM_MAX_ATTEMPTS (a timeout cannot loop forever)",
    )
    checker.check(
        "CG_PZEM_RESPONSE_TIMEOUT_MS" in power_stripped
        and define_int(config, "CG_PZEM_RESPONSE_TIMEOUT_MS") is not None,
        "per-response timeout comes from CG_PZEM_RESPONSE_TIMEOUT_MS",
    )
    checker.check(
        "CG_PZEM_POLL_PERIOD_MS" in power_stripped,
        "poll cadence comes from CG_PZEM_POLL_PERIOD_MS",
    )
    checker.check(
        define_int(config, "CG_PZEM_SLAVE_ADDRESS") == 1,
        "PZEM slave address is the documented commissioning default (1)",
    )
    extract_body = extract_function_body(
        pzem_c_stripped, r"cg_pzem_status_t\s+cg_pzem_extract_response\s*\([^)]*\)"
    )
    checker.check(
        extract_body is not None
        and "cg_crc16_check" in extract_body
        and "start + candidate_len != rx_len" in extract_body
        and "valid_count > 1U" in extract_body,
        "response extraction validates CRC and accepts only one frame ending at the RX tail",
    )
    checker.check(
        "cg_pzem_extract_response" in power_stripped
        and "CG_PZEM_RX_MAX" in power_stripped
        and "CG_PZEM_RESPONSE_TIMEOUT_MS" in power_stripped
        and "expected_frame" in power_stripped
        and "link.rx + link.frame_offset" in power_stripped
        and "link.frame_len" in power_stripped,
        "cg_power reads a bounded raw window and gives only the extracted frame to the parser",
    )
    checker.check(
        define_int(config, "CG_RS485_RX_IDLE_MS") is not None
        and "uart_get_buffered_data_len" in rs485_stripped
        and "CG_RS485_RX_IDLE_MS" in rs485_stripped
        and "timeout_ticks == 0U" in rs485_stripped
        and "timeout_ticks = 1U" in rs485_stripped,
        "cg_rs485 drains available bytes, stops on an idle gap, and keeps a non-zero timeout tick",
    )

    # 5. Status token parity ----------------------------------------------
    status_body = extract_function_body(
        pzem_c_stripped, r"const\s+char\s+\*cg_pzem_status_name\s*\([^)]*\)"
    )
    c_tokens = set(STATUS_TOKEN_RE.findall(status_body)) if status_body else set()
    host_tokens = {status.value for status in cg_modbus.Status}
    checker.check(
        c_tokens == host_tokens,
        f"C status tokens == host Status tokens (C {sorted(c_tokens)} vs host {sorted(host_tokens)})",
    )

    # 6. Scaling in C ------------------------------------------------------
    decode_body = extract_function_body(
        pzem_c_stripped, r"void\s+cg_pzem_decode_input\s*\([^)]*\)"
    )
    checker.check(
        decode_body is not None
        and "regs[3] << 16" in decode_body
        and "regs[2]" in decode_body
        and "regs[5] << 16" in decode_body
        and "regs[4]" in decode_body,
        "decode composes power/energy as 32-bit little-word-first values",
    )
    for macro in (
        "CG_PZEM_VOLT_LSB",
        "CG_PZEM_CURRENT_LSB",
        "CG_PZEM_POWER_LSB",
        "CG_PZEM_ENERGY_LSB",
    ):
        checker.check(
            decode_body is not None and macro in decode_body,
            f"decode applies {macro} (scaling is not a display detail)",
        )

    # 7. Actuator default-OFF ---------------------------------------------
    checker.check(
        re.search(r"#define\s+CG_ACTUATOR_ENABLE_ALLOWED\s+0\b", config) is not None,
        "CG_ACTUATOR_ENABLE_ALLOWED is 0 (W03 has no output authorization)",
    )
    actuator_stripped = strip_comments(actuator_c)
    checker.check(
        "ledc" not in actuator_stripped.lower() and "mcpwm" not in actuator_stripped.lower(),
        "cg_actuator.c uses no PWM peripheral",
    )
    main_sources = "\n".join(
        strip_comments((FIRMWARE_MAIN / path.name).read_text(encoding="utf-8"))
        for path in sorted(FIRMWARE_MAIN.glob("*.c"))
    )
    checker.check(
        re.search(r"ledc|mcpwm", main_sources, re.IGNORECASE) is None,
        "no PWM peripheral usage anywhere in firmware/main",
    )
    checker.check(
        re.search(
            r"gpio_set_level\s*\(\s*CG_ACTUATOR_(?:RPWM|ENABLE|REN|LEN)_PIN\s*,\s*1\s*\)",
            main_sources,
        )
        is None,
        "no source writes 1 to RPWM, R_EN or L_EN (only 0 is ever written)",
    )
    force_off_body = extract_function_body(
        actuator_stripped, r"void\s+cg_actuator_force_off\s*\([^)]*\)"
    )
    checker.check(
        force_off_body is not None
        and force_off_body.count("gpio_set_level") >= 3
        and force_off_body.find("gpio_set_level(CG_ACTUATOR_REN_PIN, 0)")
        != -1
        and force_off_body.find("gpio_set_level(CG_ACTUATOR_LEN_PIN, 0)")
        != -1
        and force_off_body.find("gpio_set_level(CG_ACTUATOR_RPWM_PIN, 0)")
        != -1
        and force_off_body.find("gpio_set_level(CG_ACTUATOR_REN_PIN, 0)")
        < force_off_body.find("gpio_set_level(CG_ACTUATOR_RPWM_PIN, 0)")
        and force_off_body.find("gpio_set_level(CG_ACTUATOR_LEN_PIN, 0)")
        < force_off_body.find("gpio_set_level(CG_ACTUATOR_RPWM_PIN, 0)"),
        "force_off clears both enables (R_EN, L_EN) before it writes the PWM level",
    )
    checker.check(
        force_off_body is not None
        and "CG_ACTUATOR_REN_PIN" in force_off_body
        and "CG_ACTUATOR_LEN_PIN" in force_off_body
        and "CG_ACTUATOR_RPWM_PIN" in force_off_body
        and "pin_bit_mask" in force_off_body,
        "force_off configures all three control pins as outputs",
    )
    allowed_body = extract_function_body(
        actuator_stripped, r"bool\s+cg_actuator_outputs_allowed\s*\([^)]*\)"
    )
    checker.check(
        allowed_body is not None
        and "CG_ACTUATOR_ENABLE_ALLOWED" in allowed_body
        and allowed_body.count("return false") >= 2,
        "outputs_allowed refuses output while ENABLE_ALLOWED=0 (and on simultaneous duty on both directions)",
    )
    # The invariant is documented in a header comment, so this check reads the
    # raw header instead of stripped comments. The corrected physics matters:
    # equal duty on both bridges gives equal outputs (no differential), not a
    # commanded reverse, so the documented rule is "one half-bridge at a time".
    checker.check(
        "one half-bridge at a time" in actuator_h.lower()
        or "single half-bridge" in actuator_h.lower()
        or "single-sided" in actuator_h.lower(),
        "cg_actuator.h documents the single-sided command invariant "
        "(one half-bridge at a time; equal duty is not a reverse command)",
    )
    checker.check(
        "gpio_" not in strip_comments(power_c),
        "cg_power.c touches no GPIO directly (transport stays in cg_rs485)",
    )

    # 8. Boot order --------------------------------------------------------
    safety_call = app_main.find("cg_safety_force_actuator_off()")
    init_calls = [
        app_main.find("cg_ds18b20_init()"),
        app_main.find("xTaskCreate"),
        app_main.find("nvs_flash_init()"),
        app_main.find("cg_power_start()"),
    ]
    checker.check(
        safety_call != -1 and all(call == -1 or safety_call < call for call in init_calls),
        "actuator is forced OFF before NVS, sensor init, task creation and PZEM start",
    )
    checker.check(
        "cg_power_start()" in app_main,
        "app_main starts the W03 PZEM poll task",
    )
    checker.check(
        "cg_actuator_force_off()" in strip_comments(safety_c),
        "safety module delegates the pin work to cg_actuator",
    )

    # 9. Log grammar -------------------------------------------------------
    for token, macro in (
        ("PZEM_CFG", "CG_LOG_PZEM_CFG"),
        ("PZEM_RANGE", "CG_LOG_PZEM_RANGE"),
        ("PZEM", "CG_LOG_PZEM"),
    ):
        checker.check(
            f'#define {macro} "{token}"' in config,
            f"config declares the {token} log kind ({macro})",
        )
    checker.check(
        define_int(config, "CG_LOG_GRAMMAR_VERSION") == 2,
        "log grammar version is 2 (v1 kinds unchanged plus PZEM kinds)",
    )
    checker.check(
        "PZEM_CFG" in log_h and "PZEM_RANGE" in log_h and "#CG PZEM " in log_h,
        "cg_log.h documents the PZEM line grammar",
    )
    serial_py = checker.read("firmware/tools/cg_serial.py")
    checker.check(
        "GRAMMAR_VERSION = 2" in serial_py,
        "host parser cg_serial.py declares GRAMMAR_VERSION = 2",
    )
    for field in (
        "uptime_ms=",
        "seq=",
        "status=",
        "v=",
        "i=",
        "p=",
        "e=",
        "crc_ok=",
        "attempts=",
        "tx=",
        "rx=",
    ):
        checker.check(
            field in power_stripped,
            f"cg_power.c PZEM line carries {field}",
        )
    for field in ("slave=", "baud=", "framing=", "dir=", "read_only=1"):
        checker.check(field in power_stripped, f"cg_power.c config line carries {field}")
    checker.check(
        "CG_INVALID_VALUE_TOKEN" in power_stripped,
        "invalid values are printed through the nan sentinel",
    )

    # 10. Build completeness ----------------------------------------------
    sources = sorted(path.name for path in FIRMWARE_MAIN.glob("*.c"))
    missing = [name for name in sources if f'"{name}"' not in cmake]
    checker.check(not missing, f"CMakeLists lists every source file (missing: {missing or 'none'})")

    # 11. GPIO ownership / as-built map -----------------------------------
    gpio = cg_gpio_map.evaluate(config)
    map_problems = cg_gpio_map.conflicts(gpio) + cg_gpio_map.as_built_mismatches(gpio)
    for problem in map_problems:
        checker.fail(f"GPIO map: {problem}")
    checker.check(
        not map_problems,
        "effective pin map matches as-built map v2 with one owner per pad",
    )
    checker.check(
        gpio.pin_map_version == 2,
        f"CG_PIN_MAP_VERSION is 2 for the as-built map (got {gpio.pin_map_version})",
    )

    for problem in cg_gpio_map.safe_off_problems(
        actuator_c,
        rpwm="CG_ACTUATOR_RPWM_PIN",
        ren="CG_ACTUATOR_REN_PIN",
        len_pin="CG_ACTUATOR_LEN_PIN",
        signature=r"void\s+cg_actuator_force_off\s*\([^)]*\)",
    ):
        checker.fail(f"safe-OFF: {problem}")
    checker.check(
        not cg_gpio_map.safe_off_problems(
            actuator_c,
            rpwm="CG_ACTUATOR_RPWM_PIN",
            ren="CG_ACTUATOR_REN_PIN",
            len_pin="CG_ACTUATOR_LEN_PIN",
            signature=r"void\s+cg_actuator_force_off\s*\([^)]*\)",
        ),
        "cg_actuator_force_off covers RPWM, R_EN and L_EN (no pin omitted)",
    )

    for problem in cg_gpio_map.direction_problems(
        {
            "cg_door.c": door_c,
            "cg_onewire.c": onewire_c,
            "cg_rs485.c": rs485_c,
            "cg_power.c": power_c,
            "cg_ds18b20.c": ds18b20_c,
        }
    ):
        checker.fail(f"pin direction: {problem}")

    # A MANUAL DE/RE on the MC-38 pin must be rejected by the same rules.
    manual_config = config.replace(
        "#define CG_RS485_DIR_MODE 0", "#define CG_RS485_DIR_MODE 1"
    )
    if manual_config != config:
        manual_gpio = cg_gpio_map.evaluate(manual_config)
        manual_problems = cg_gpio_map.conflicts(manual_gpio)
        checker.check(
            any("collides with MC38" in problem for problem in manual_problems),
            "MANUAL RS-485 DE/RE on GPIO35 is rejected (MC-38 owns the pin)",
        )
        free_pin_config = manual_config.replace(
            "#define CG_PIN_MAX3485_DE_RE 35", "#define CG_PIN_MAX3485_DE_RE 4"
        )
        free_gpio = cg_gpio_map.evaluate(free_pin_config)
        checker.check(
            not cg_gpio_map.conflicts(free_gpio),
            "MANUAL RS-485 DE/RE on a free pin is accepted",
        )
    else:
        checker.fail("CG_RS485_DIR_MODE is not a single #define line the check can vary")

    checker.check(
        "MANUAL RS-485 DE/RE collides with another pin" in config,
        "config has a compile-time #error for a MANUAL DE/RE collision",
    )

    return checker


def strip_comments_python(text: str) -> str:
    """Remove # comments and docstrings enough for a literal scan."""

    text = re.sub(r'""".*?"""', " ", text, flags=re.DOTALL)
    text = re.sub(r"'''.*?'''", " ", text, flags=re.DOTALL)
    return re.sub(r"#[^\n]*", " ", text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Static contract checks for the W03 power/RS-485 firmware sources."
    )
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    args = parser.parse_args(argv)

    checker = run_checks()

    if not args.quiet:
        for note in checker.notes:
            print(note)

    if checker.failures:
        print()
        print("W03 STATIC FIRMWARE CHECK: FAIL")
        for failure in checker.failures:
            print(f"  - {failure}")
        return 1

    print()
    print(f"W03 STATIC FIRMWARE CHECK: PASS ({len(checker.notes)} checks)")
    print("Reminder: this does NOT compile the firmware. The compile check is the")
    print("Espressif Docker build (GitHub Actions, see evidence/A/W03/).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
