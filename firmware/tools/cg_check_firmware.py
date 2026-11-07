"""Static contract checks for the ColdGuard W02 firmware (Member A).

The team machine has no ESP-IDF installation and no C compiler, so the
firmware cannot be compiled here (the documented build path is the
Espressif Docker image, see the root README). This script therefore checks
the invariants that *can* be checked from the sources, and refuses to
certify anything it cannot see:

1. ROM map parity - the ROM bytes in ``firmware/main/coldguard_config.h``
   must equal ``evidence/A/W02/sensor-rom-map.yaml``, and every ROM must
   carry a valid Dallas CRC8 (a transcription typo is caught here).
2. Identity by ROM, never by bus order - the read path must use MATCH_ROM
   on frozen ROMs; no role may be assigned from a loop index.
3. Shared conversion - broadcast SKIP_ROM + CONVERT_T, then per-ROM
   scratchpad reads; the per-probe read function must contain no
   conversion token or call at all (docs/01 PHY-DS-006).
4. Invalid readings stay invalid - the ``nan`` token must exist and be
   produced by the temperature formatter.
5. Door polarity is not assumed - ``CG_DOOR_POLARITY_CONFIRMED`` must be 0,
   the commissioned branch must map raw -> OPEN/CLOSED, and the
   uncommissioned branch must return UNVERIFIED and never OPEN/CLOSED.
6. Configurability - debounce and sample period must come from named
   configuration macros, not inline literals.
7. Boot safety order - the actuator must be forced off before any task or
   sensor initialisation.
8. Build completeness - every ``.c`` file in ``firmware/main`` must be
   listed in ``CMakeLists.txt``.
9. BME280 driver honesty - ``firmware/main`` owns an ambient producer
   (A-W02-06). The driver must be registered in the build, must refuse to
   publish a reading it did not measure, and must not claim the physical
   acceptance half of A-W02-06, which is still an open bench question.
10. No unmeasurable counters - the ROM summary must not print an
    "unknown devices" count (W02 has no bus scan).
11. GPIO ownership - the effective pin map must match the as-built map and
    must not assign one pad to two peripherals, a flash/PSRAM/strapping
    pin, or leave the actuator safe-OFF incomplete (see cg_gpio_map.py).

Exit codes: 0 = every check passed, 1 = at least one check failed,
2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

TOOLS_DIR = pathlib.Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import cg_gpio_map  # noqa: E402  (local module, path set above)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FIRMWARE_MAIN = REPO_ROOT / "firmware" / "main"
ROM_MAP_YAML = REPO_ROOT / "evidence" / "A" / "W02" / "sensor-rom-map.yaml"

ROLE_TO_MACRO = {"T1": "CG_ROM_T1_BYTES", "T2": "CG_ROM_T2_BYTES",
                 "T3": "CG_ROM_T3_BYTES", "SPARE": "CG_ROM_SPARE_BYTES"}

MACRO_RE = re.compile(r"#define\s+(CG_ROM_\w+_BYTES)\s*\{([^}]*)\}")


def dallas_crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        for _ in range(8):
            mix = (crc ^ byte) & 0x01
            crc >>= 1
            if mix:
                crc ^= 0x8C
            byte >>= 1
    return crc


def parse_firmware_roms(header_text: str) -> dict[str, str]:
    macro_to_rom: dict[str, str] = {}
    for match in MACRO_RE.finditer(header_text):
        name = match.group(1)
        values = [part.strip() for part in match.group(2).split(",") if part.strip()]
        if len(values) != 8:
            continue
        try:
            raw = bytes(int(value, 0) for value in values)
        except ValueError:
            continue
        macro_to_rom[name] = raw.hex().upper()
    return {role: macro_to_rom[macro] for role, macro in ROLE_TO_MACRO.items() if macro in macro_to_rom}


def parse_yaml_roms(text: str) -> dict[str, str]:
    """Read role -> rom_hex pairs from the evidence map.

    Uses PyYAML when available and a narrow regex fallback otherwise, so
    the check still runs on a bare interpreter.
    """

    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None

    if yaml is not None:
        data = yaml.safe_load(text)
        out: dict[str, str] = {}
        for key in ("roles", "probes"):
            for entry in data.get(key) or []:
                role = entry.get("role")
                rom = entry.get("rom_hex")
                if role and rom:
                    out[str(role)] = str(rom).upper()
        for entry in data.get("spare") or []:
            rom = entry.get("rom_hex")
            if rom:
                out["SPARE"] = str(rom).upper()
        return out

    out = {}
    current_role = None
    for line in text.splitlines():
        match = re.match(r"\s*-?\s*role:\s*(\w+)", line)
        if match:
            current_role = match.group(1)
        match = re.match(r"\s*rom_hex:\s*\"?([0-9A-Fa-f]{16})\"?", line)
        if match and current_role:
            out[current_role] = match.group(1).upper()
    return out


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", text)


def extract_function_body(text: str, signature_re: str) -> str | None:
    """Return a function body whose closing brace starts at column zero.

    ``text`` should already be comment-stripped. Returns ``None`` when the
    function cannot be found or does not end with a column-zero brace.
    """

    match = re.search(signature_re + r"\s*\{", text)
    if not match:
        return None
    end = text.find("\n}", match.end())
    if end == -1:
        return None
    return text[match.end():end]


def read_probe_never_converts(ds18b20_text: str) -> bool:
    """True when the per-probe reader contains no conversion token or call.

    Rejecting only the literal ``DS18B20_CMD_CONVERT_T`` was not enough: a
    reader that calls ``cg_ds18b20_convert_all()`` must fail this check too.
    """

    body = extract_function_body(
        strip_comments(ds18b20_text), r"void\s+cg_ds18b20_read_probe\s*\([^)]*\)"
    )
    return body is not None and re.search(r"convert", body, re.IGNORECASE) is None


def polarity_gate_ok(door_text: str) -> bool:
    """True when the polarity gate cannot leak a guessed OPEN/CLOSED state.

    The ``#if CG_DOOR_POLARITY_CONFIRMED`` branch must contain the raw-open
    level comparison and both semantic names; the ``#else`` branch must
    return UNVERIFIED and must never mention OPEN/CLOSED. This is checked
    per branch, so swapping the two branches cannot pass.
    """

    text = strip_comments(door_text)
    blocks = re.findall(
        r"#if\s+CG_DOOR_POLARITY_CONFIRMED(.*?)#else(.*?)#endif", text, re.DOTALL
    )
    if not blocks:
        return False
    for confirmed, unconfirmed in blocks:
        if "CG_DOOR_RAW_OPEN_LEVEL" not in confirmed:
            return False
        if "CG_DOOR_OPEN" not in confirmed or "CG_DOOR_CLOSED" not in confirmed:
            return False
        if "CG_DOOR_UNVERIFIED" not in unconfirmed:
            return False
        if "CG_DOOR_OPEN" in unconfirmed or "CG_DOOR_CLOSED" in unconfirmed:
            return False
    return True


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
    rom_map_c = checker.read("firmware/main/cg_rom_map.c")
    ds18b20 = checker.read("firmware/main/cg_ds18b20.c")
    door_c = checker.read("firmware/main/cg_door.c")
    log_h = checker.read("firmware/main/cg_log.h")
    log_c = checker.read("firmware/main/cg_log.c")
    app_main = checker.read("firmware/main/app_main.c")
    cmake = checker.read("firmware/main/CMakeLists.txt")
    safety_c = checker.read("firmware/main/cg_safety.c")
    onewire_c = checker.read("firmware/main/cg_onewire.c")

    # 1. ROM map parity + CRC
    firmware_roms = parse_firmware_roms(config)
    yaml_roms = parse_yaml_roms(ROM_MAP_YAML.read_text(encoding="utf-8"))
    for role in ROLE_TO_MACRO:
        fw = firmware_roms.get(role)
        record = yaml_roms.get(role)
        checker.check(fw is not None, f"firmware defines a ROM for {role}")
        checker.check(
            fw is not None and record is not None and fw == record,
            f"{role} ROM matches evidence/A/W02/sensor-rom-map.yaml ({record} vs {fw})",
        )
        if fw is not None:
            raw = bytes.fromhex(fw)
            checker.check(
                dallas_crc8(raw[:7]) == raw[7],
                f"{role} ROM {fw} carries a valid Dallas CRC8",
            )
    checker.check(len(set(firmware_roms.values())) == len(firmware_roms), "firmware ROMs are pairwise distinct")

    # 2. Identity by ROM
    checker.check(
        "cg_rom_map_match" in ds18b20 or "cg_rom_map_bytes" in ds18b20,
        "DS18B20 read path resolves probes through the frozen ROM map",
    )
    checker.check(
        "DS18B20_CMD_MATCH_ROM" in ds18b20 and "cg_rom_map_bytes" in ds18b20,
        "each probe read addresses its frozen ROM with MATCH_ROM",
    )
    forbidden = re.findall(r"role\s*=\s*[^;]*(\[\s*(?:i|idx|index)\s*\])", strip_comments(ds18b20 + app_main))
    checker.check(not forbidden, "no role is assigned from a loop/discovery index")

    # 3. Shared conversion
    convert_body = extract_function_body(
        strip_comments(ds18b20), r"bool\s+cg_ds18b20_convert_all\s*\([^)]*\)"
    )
    checker.check(
        convert_body is not None
        and "DS18B20_CMD_SKIP_ROM" in convert_body
        and "DS18B20_CMD_CONVERT_T" in convert_body,
        "shared conversion uses a broadcast SKIP_ROM + CONVERT_T",
    )
    checker.check(
        read_probe_never_converts(ds18b20),
        "per-probe read never starts its own conversion (no convert token or call, PHY-DS-006)",
    )

    # 4. Invalid stays invalid
    checker.check(
        'CG_INVALID_VALUE_TOKEN "nan"' in config,
        "config defines the nan sentinel for an invalid reading",
    )
    checker.check(
        "CG_INVALID_VALUE_TOKEN" in log_c and "cg_log_temp_or_nan" in log_c,
        "the temperature formatter emits the nan sentinel instead of a number",
    )

    # 5. Door polarity not assumed
    checker.check(
        re.search(r"#define\s+CG_DOOR_POLARITY_CONFIRMED\s+0\b", config) is not None,
        "CG_DOOR_POLARITY_CONFIRMED is still 0 (polarity not commissioned)",
    )
    checker.check(
        polarity_gate_ok(door_c),
        "the commissioned branch maps raw -> OPEN/CLOSED and the uncommissioned branch returns UNVERIFIED",
    )

    # 6. Configurability
    checker.check(
        re.search(r"#define\s+CG_DOOR_DEBOUNCE_MS\s+\d+", config) is not None
        and "CG_DOOR_DEBOUNCE_MS" in door_c,
        "debounce window comes from CG_DOOR_DEBOUNCE_MS",
    )
    checker.check(
        re.search(r"#define\s+CG_SAMPLE_PERIOD_MS\s+1000\b", config) is not None
        and "CG_SAMPLE_PERIOD_MS" in app_main,
        "sample period comes from CG_SAMPLE_PERIOD_MS (1 Hz target)",
    )
    checker.check(
        "next_deadline_us" in app_main,
        "the sample loop is deadline paced so uptime_ms is a real observation time",
    )
    checker.check(
        "raw_edges" in door_c and "discarded_edges" in door_c,
        "the door module exposes raw-edge and discarded-edge counts as bounce evidence",
    )

    # ROM summary must not print counters the firmware cannot measure
    checker.check(
        "CG_ROLE_COUNT" in log_c and "unknown=" not in log_c and "unknown=" not in ds18b20,
        "ROM summary counts all frozen roles and prints no unmeasurable 'unknown' devices",
    )

    # 7. Boot safety order
    safety_call = app_main.find("cg_safety_force_actuator_off()")
    init_calls = [
        app_main.find("cg_ds18b20_init()"),
        app_main.find("xTaskCreate"),
        app_main.find("nvs_flash_init()"),
    ]
    checker.check(
        safety_call != -1 and all(call == -1 or safety_call < call for call in init_calls),
        "the actuator is forced OFF before NVS, sensor init and task creation",
    )

    # 8. Build completeness
    sources = sorted(path.name for path in FIRMWARE_MAIN.glob("*.c"))
    missing = [name for name in sources if f'"{name}"' not in cmake]
    checker.check(not missing, f"CMakeLists lists every source file (missing: {missing or 'none'})")

    # 9. BME280 driver honesty (A-W02-06): the software half is owned here, the
    #    physical half is not, and the checker must be able to tell those apart.
    main_files = sorted(path.name for path in FIRMWARE_MAIN.glob("*.c") if path.is_file())
    main_files += sorted(path.name for path in FIRMWARE_MAIN.glob("*.h") if path.is_file())
    all_sources = "\n".join(
        strip_comments((FIRMWARE_MAIN / name).read_text(encoding="utf-8")) for name in main_files
    )
    checker.check(
        (FIRMWARE_MAIN / "cg_bme280.c").is_file() and (FIRMWARE_MAIN / "cg_bme280.h").is_file(),
        "the ambient producer exists in firmware/main (A-W02-06 software half)",
    )
    checker.check(
        "esp_driver_i2c" in cmake,
        "the main component requires esp_driver_i2c (the v6.x split means the "
        "legacy driver meta-component no longer re-exports i2c_master.h)",
    )
    bme_src = strip_comments((FIRMWARE_MAIN / "cg_bme280.c").read_text(encoding="utf-8"))
    checker.check(
        bme_src.count("out->valid = true") == 1,
        "exactly one site may declare an ambient reading valid (docs/01 forbids a "
        "fabricated reading standing in for a measured one)",
    )
    checker.check(
        bme_src.count("s->seq++") == 1,
        "exactly one site may consume an ambient sequence number, so a refused "
        "transaction cannot mint one",
    )
    # The physical half of A-W02-06 stays open: the firmware must keep absence a
    # distinct, reported state rather than assuming a module is fitted.
    checker.check(
        "CG_BME_STATE_ABSENT" in all_sources and "cg_bme280_is_present" in all_sources,
        "absence stays a nameable state rather than being assumed or scored as a fault",
    )
    # The real publication gate lives in the producer task, not in the driver, so
    # a grep over cg_bme280.c alone cannot prove a value is not fabricated. These
    # two assertions pin the gate itself: the ambient pair may only reach the
    # snapshot through obs.valid, and the trim decode stays fail-closed until
    # someone flips the macro deliberately with evidence in hand.
    app_src = strip_comments((FIRMWARE_MAIN / "app_main.c").read_text(encoding="utf-8"))
    checker.check(
        "obs.valid" in app_src and "cg_snapshot_publish_env(cg_bme280_is_present(&state), obs.valid" in app_src,
        "the ambient publication is gated by the producer's own validity flag",
    )
    cfg_src = (FIRMWARE_MAIN / "coldguard_config.h").read_text(encoding="utf-8")
    checker.check(
        re.search(r"^#define\s+CG_BME280_TRIM_LAYOUT_CONFIRMED\s+0\s*$", cfg_src, re.MULTILINE)
        is not None,
        "the humidity trim decode stays fail-closed by default; enabling it must be a "
        "deliberate change backed by a comparison against a reference instrument",
    )
    pure_src = strip_comments((FIRMWARE_MAIN / "cg_bme280.c").read_text(encoding="utf-8"))
    idf_src = strip_comments((FIRMWARE_MAIN / "cg_bme280_idf.c").read_text(encoding="utf-8"))
    checker.check(
        "driver/i2c_master.h" in idf_src and "driver/i2c_master.h" not in pure_src,
        "the transport boundary is real: only cg_bme280_idf.c reaches the I2C driver, "
        "which is what lets the host harness compile the decision logic unchanged",
    )

    # Grammar tokens the host tools depend on
    for token in ("LOG", "BOOT", "ROM", "ROMS", "SAMPLE", "DOOR_EDGE", "DOOR_STATE", "DOOR_POLARITY", "SAFETY"):
        checker.check(
            f'"{token}"' in config or f'"{token}"' in log_h,
            f"log grammar declares the {token} line kind",
        )

    # 11. GPIO ownership and actuator safe-OFF
    # W02 has no RS-485 driver, so the DE/RE checks are not applicable here;
    # they are enforced by the W03 checker with the same shared module.
    gpio = cg_gpio_map.evaluate(config)
    for problem in cg_gpio_map.conflicts(gpio, require_rs485=False):
        checker.fail(f"GPIO map: {problem}")
    for problem in cg_gpio_map.as_built_mismatches(gpio, require_rs485=False):
        checker.fail(f"GPIO map: {problem}")
    if not cg_gpio_map.conflicts(gpio, require_rs485=False) and not cg_gpio_map.as_built_mismatches(
        gpio, require_rs485=False
    ):
        checker.notes.append(
            "ok   GPIO map has one owner per pad and matches the as-built map v2"
        )
    checker.check(
        gpio.pin_map_version == 2,
        f"CG_PIN_MAP_VERSION is 2 for the as-built map (got {gpio.pin_map_version})",
    )

    # The pin work may live in cg_safety.c (W02) or be delegated to
    # cg_actuator.c (W03); either way the boot path must clear all three
    # actuator inputs, enables first.
    if "cg_actuator_force_off()" in strip_comments(safety_c):
        try:
            actuator_c = checker.read("firmware/main/cg_actuator.c")
        except OSError:
            checker.fail("cg_safety delegates safe-OFF to cg_actuator, but cg_actuator.c is unreadable")
        else:
            problems = cg_gpio_map.safe_off_problems(
                actuator_c,
                rpwm="CG_ACTUATOR_RPWM_PIN",
                ren="CG_ACTUATOR_REN_PIN",
                len_pin="CG_ACTUATOR_LEN_PIN",
                signature=r"void\s+cg_actuator_force_off\s*\([^)]*\)",
            )
            for problem in problems:
                checker.fail(f"delegated safe-OFF: {problem}")
            checker.check(
                not problems,
                "delegated safe-OFF (cg_actuator_force_off) covers RPWM, R_EN and L_EN, enables first",
            )
    else:
        problems = cg_gpio_map.safe_off_problems(
            safety_c,
            rpwm="CG_PIN_IBT2_COOLING_PWM",
            ren="CG_PIN_IBT2_REN",
            len_pin="CG_PIN_IBT2_LEN",
            signature=r"void\s+cg_safety_force_actuator_off\s*\([^)]*\)",
        )
        for problem in problems:
            checker.fail(f"safe-OFF: {problem}")
        checker.check(
            not problems,
            "boot safe-OFF drives RPWM, R_EN and L_EN low (enables cleared first)",
        )

    for problem in cg_gpio_map.direction_problems(
        {"cg_door.c": door_c, "cg_onewire.c": onewire_c, "cg_ds18b20.c": ds18b20}
    ):
        checker.fail(f"pin direction: {problem}")

    return checker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static contract checks for the W02 firmware sources.")
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    args = parser.parse_args(argv)

    checker = run_checks()

    if not args.quiet:
        for note in checker.notes:
            print(note)

    if checker.failures:
        print()
        print("STATIC FIRMWARE CHECK: FAIL")
        for failure in checker.failures:
            print(f"  - {failure}")
        return 1

    print()
    print(f"STATIC FIRMWARE CHECK: PASS ({len(checker.notes)} checks)")
    print("Reminder: this does NOT compile the firmware. The compile check is the")
    print("Espressif Docker build documented in the repository README.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
