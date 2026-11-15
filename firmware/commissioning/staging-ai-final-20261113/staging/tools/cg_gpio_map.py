"""GPIO ownership validation for the ColdGuard as-built pin map.

The firmware would only find a pin conflict at runtime (two drivers
configuring the same pad) or, worse, never - a duplicate assignment that
happens to look plausible can silently disable one peripheral. This module
turns the map into an explicit ownership table so the host checkers and
their unit tests reject a conflicting map *before* a build, and so the
same rules are exercised with synthetic negative cases.

Authority: ``evidence/A/as-built-pinmap-2026-10-27.md`` (map v2). The table
below is the expected effective mapping for the MAKDRIVERONE ESP32-S3R2 +
W25Q32 profile; a deliberate wiring change must update the record, this
table and ``CG_PIN_MAP_VERSION`` together.

Standard library only.
"""

from __future__ import annotations

import dataclasses
import re

# Logical function -> authoritative macro. Aliases (CG_ONEWIRE_PIN,
# CG_ACTUATOR_*) must not be added here: one authoritative name per pin.
LOGICAL_PINS = {
    "DS18B20_DATA": "CG_PIN_DS18B20_DATA",
    "BME280_SDA": "CG_PIN_BME280_SDA",
    "BME280_SCL": "CG_PIN_BME280_SCL",
    "MC38": "CG_PIN_MC38",
    "RS485_TX": "CG_PIN_UART_TX_TO_MAX3485_DI",
    "RS485_RX": "CG_PIN_UART_RX_FROM_MAX3485_RO",
    "ACTUATOR_RPWM": "CG_PIN_IBT2_COOLING_PWM",
    "ACTUATOR_REN": "CG_PIN_IBT2_REN",
    "ACTUATOR_LEN": "CG_PIN_IBT2_LEN",
}

# As-built values reported by the operator and exercised on the bench:
# TEST 129D (four DS18B20 ROMs on GPIO33), BME280 bench (SDA 21, SCL 34
# after the header was wired), MC-38 as-built on GPIO35, TTL485-V2.0 on
# 36/37, IBT-2 RPWM/R_EN/L_EN on 5/6/10.
AS_BUILT_PINS = {
    "DS18B20_DATA": 33,
    "BME280_SDA": 21,
    "BME280_SCL": 34,
    "MC38": 35,
    "RS485_TX": 36,
    "RS485_RX": 37,
    "ACTUATOR_RPWM": 5,
    "ACTUATOR_REN": 6,
    "ACTUATOR_LEN": 10,
}

FLASH_BUS = range(26, 33)            # SPI0/1 flash (W25Q32), quad
OCTAL_PSRAM_PINS = range(33, 38)     # occupied on S3R8/S3R8V only
STRAPPING_PINS = {0, 3, 45, 46}      # ESP32-S3 strapping pins
GPIO_MAX = 48

RS485_DIR_AUTO = 0
RS485_DIR_MANUAL = 1

DEFINE_RE = re.compile(r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+([^\s/]+)", re.MULTILINE)


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", text)


def parse_defines(text: str) -> dict[str, str]:
    return {match.group(1): match.group(2) for match in DEFINE_RE.finditer(text)}


def _resolve_int(name: str, defines: dict[str, str], _seen: set[str] | None = None) -> int | None:
    """Follow macro aliases and return an integer, or None for a non-integer."""
    seen = _seen or set()
    token = name
    while token in defines:
        if token in seen:
            return None
        seen.add(token)
        token = defines[token]
    try:
        return int(token, 0)
    except ValueError:
        return None


@dataclasses.dataclass(frozen=True)
class GpioMap:
    pins: dict[str, int | None]
    dir_mode: int | None
    de_re_pin: int | None
    octal_psram: int
    pin_map_version: int | None

    def active_pins(self) -> dict[str, int | None]:
        return dict(self.pins)


def evaluate(config_text: str) -> GpioMap:
    defines = parse_defines(config_text)
    pins = {key: _resolve_int(macro, defines) for key, macro in LOGICAL_PINS.items()}
    return GpioMap(
        pins=pins,
        dir_mode=_resolve_int("CG_RS485_DIR_MODE", defines),
        de_re_pin=_resolve_int("CG_PIN_MAX3485_DE_RE", defines),
        octal_psram=_resolve_int("CG_HW_PSRAM_OCTAL", defines) or 0,
        pin_map_version=_resolve_int("CG_PIN_MAP_VERSION", defines),
    )


def conflicts(gpio: GpioMap, *, require_rs485: bool = True) -> list[str]:
    """Every static contradiction in the map, as human-readable messages."""
    problems: list[str] = []

    for key, pin in gpio.pins.items():
        if pin is None:
            problems.append(f"{key}: pin macro has no integer value")
            continue
        if pin < 0 or pin > GPIO_MAX:
            problems.append(f"{key}=GPIO{pin} is outside the ESP32-S3 GPIO range")
        if pin in FLASH_BUS:
            problems.append(
                f"{key}=GPIO{pin} is on the SPI0/1 flash bus (GPIO26-32) of the W25Q32 profile"
            )
        if pin in STRAPPING_PINS:
            problems.append(f"{key}=GPIO{pin} is a strapping pin (GPIO0/3/45/46)")
        if gpio.octal_psram and pin in OCTAL_PSRAM_PINS:
            problems.append(
                f"{key}=GPIO{pin} is reserved on an Octal-PSRAM profile (S3R8/S3R8V)"
            )

    by_value: dict[int, list[str]] = {}
    for key, pin in gpio.pins.items():
        if pin is not None:
            by_value.setdefault(pin, []).append(key)
    for pin, owners in sorted(by_value.items()):
        if len(owners) > 1:
            problems.append(
                f"GPIO{pin} is claimed by multiple functions: {', '.join(sorted(owners))}"
            )

    if gpio.pins.get("DS18B20_DATA") is not None and (
        gpio.pins.get("DS18B20_DATA") == gpio.pins.get("ACTUATOR_LEN")
    ):
        problems.append(
            "DS18B20 DATA and IBT-2 L_EN share one pin; the 1-Wire bus and a "
            "half-bridge enable cannot coexist"
        )
    if gpio.pins.get("BME280_SCL") is not None and (
        gpio.pins.get("BME280_SCL") == gpio.pins.get("MC38")
    ):
        problems.append("BME280 SCL and the MC-38 door input share one pin")

    if require_rs485:
        if gpio.dir_mode not in (RS485_DIR_AUTO, RS485_DIR_MANUAL):
            problems.append(f"CG_RS485_DIR_MODE must be 0 (AUTO) or 1 (MANUAL), got {gpio.dir_mode}")
        if gpio.dir_mode == RS485_DIR_MANUAL:
            if gpio.de_re_pin is None:
                problems.append("MANUAL RS-485 direction needs CG_PIN_MAX3485_DE_RE")
            else:
                for key, pin in gpio.pins.items():
                    if pin == gpio.de_re_pin:
                        problems.append(
                            f"MANUAL RS-485 DE/RE on GPIO{gpio.de_re_pin} collides with {key}"
                        )

    return problems


def as_built_mismatches(gpio: GpioMap, *, require_rs485: bool = True) -> list[str]:
    """Differences from the recorded as-built map (not from docs/01 v1)."""
    problems: list[str] = []
    for key, expected in AS_BUILT_PINS.items():
        actual = gpio.pins.get(key)
        if actual != expected:
            problems.append(
                f"{key}=GPIO{actual} does not match the as-built GPIO{expected} "
                "(evidence/A/as-built-pinmap-2026-10-27.md)"
            )
    if gpio.octal_psram != 0:
        problems.append(
            "CG_HW_PSRAM_OCTAL must stay 0 for the ESP32-S3R2 (Quad PSRAM) profile"
        )
    if require_rs485 and gpio.dir_mode != RS485_DIR_AUTO:
        problems.append(
            "the as-built TTL485-V2.0 has no DE/RE pin; CG_RS485_DIR_MODE must stay 0 (AUTO)"
        )
    return problems


def extract_function_body(text: str, signature_re: str) -> str | None:
    match = re.search(signature_re + r"\s*\{", text)
    if not match:
        return None
    end = text.find("\n}", match.end())
    if end == -1:
        return None
    return text[match.end():end]


def safe_off_problems(
    source: str,
    *,
    rpwm: str,
    ren: str,
    len_pin: str,
    signature: str,
) -> list[str]:
    """Check the force-OFF routine against all three active control pins.

    A W03 regression that drops L_EN from the mask or the level writes is
    exactly the failure this check exists to catch, so each pin is
    required explicitly rather than inferred from "two pins were handled".
    """
    problems: list[str] = []
    body = extract_function_body(strip_comments(source), signature)
    if body is None:
        return ["force_off routine not found"]

    for macro in (rpwm, ren, len_pin):
        if macro not in body:
            problems.append(f"force_off does not handle {macro}")
        if f"gpio_set_level({macro}, 0)" not in body:
            problems.append(f"force_off never writes {macro}=0")

    cleared = []
    for macro in (ren, len_pin, rpwm):
        index = body.find(f"gpio_set_level({macro}, 0)")
        if index != -1:
            cleared.append((index, macro))
    if len(cleared) == 3:
        order = [macro for _, macro in sorted(cleared)]
        if order[-1] != rpwm:
            problems.append("force_off must clear both enables before RPWM")

    if re.search(r"gpio_set_level\s*\([^,]+,\s*1\s*\)", body):
        problems.append("force_off writes a logical 1 to an actuator pin")

    return problems


def direction_problems(sources: dict[str, str]) -> list[str]:
    """Static input/output ownership checks across the driver modules."""
    problems: list[str] = []

    door = strip_comments(sources.get("cg_door.c", ""))
    if "gpio_config" not in door or "GPIO_MODE_INPUT" not in door:
        problems.append("cg_door.c does not configure the MC-38 pin as an input")
    if "CG_PIN_MC38" not in door:
        problems.append("cg_door.c does not use CG_PIN_MC38")

    onewire = strip_comments(sources.get("cg_onewire.c", ""))
    if "GPIO_MODE_INPUT_OUTPUT_OD" not in onewire:
        problems.append("cg_onewire.c does not configure 1-Wire as open-drain bidirectional")

    for name in ("cg_rs485.c", "cg_power.c", "cg_ds18b20.c"):
        text = strip_comments(sources.get(name, ""))
        if "CG_PIN_MC38" in text:
            problems.append(f"{name} touches the MC-38 pin (owner is cg_door.c)")

    for name in ("cg_door.c", "cg_onewire.c", "cg_rs485.c", "cg_power.c"):
        text = strip_comments(sources.get(name, ""))
        for macro in ("CG_PIN_IBT2_COOLING_PWM", "CG_PIN_IBT2_REN", "CG_PIN_IBT2_LEN"):
            if macro in text:
                problems.append(f"{name} touches an IBT-2 control pin (owner is the actuator module)")

    return problems
