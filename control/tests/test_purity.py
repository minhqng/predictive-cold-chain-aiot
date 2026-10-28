"""Purity guards: no transport/DB/GPIO/web imports, no hidden numeric policy."""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

from coldguard_control import PolicyConfig, PolicyDecision

SRC = Path(__file__).resolve().parents[1] / "src" / "coldguard_control"

FORBIDDEN_ROOTS = {
    "paho",
    "pymqtt",
    "asyncio_mqtt",
    "gmqtt",
    "psycopg",
    "psycopg2",
    "sqlalchemy",
    "sqlite3",
    "fastapi",
    "starlette",
    "uvicorn",
    "flask",
    "requests",
    "httpx",
    "socket",
    "serial",
    "pymodbus",
    "RPi",
    "gpiozero",
    "machine",
    "time",
    "datetime",
}

FORBIDDEN_CALLS = {
    "publish",
    "subscribe",
    "actuate",
    "digital_write",
    "gpio_write",
    "sleep",
    "monotonic",
}


def _module_files() -> list[Path]:
    return sorted(SRC.glob("*.py"))


def test_core_imports_no_transport_db_gpio_or_web_modules() -> None:
    violations: list[str] = []
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                root = name.split(".")[0]
                if root in FORBIDDEN_ROOTS:
                    violations.append(f"{path.name}: imports {name}")

    assert violations == [], "\n".join(violations)


def test_core_never_calls_transport_actuation_or_clock_functions() -> None:
    violations: list[str] = []
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
                violations.append(f"{path.name}: calls .{func.attr}()")
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                violations.append(f"{path.name}: calls {func.id}()")

    assert violations == [], "\n".join(violations)


def test_policy_config_has_no_numeric_defaults() -> None:
    tree = ast.parse((SRC / "config.py").read_text(encoding="utf-8"))
    policy_config = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PolicyConfig"
    )

    offenders: list[str] = []
    for node in policy_config.body:
        if not isinstance(node, ast.AnnAssign) or node.value is None:
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(
            value.value, (int, float)
        ) and not isinstance(value.value, bool):
            offenders.append(
                f"{node.target.id} has default {value.value!r}"
            )

    assert offenders == [], "\n".join(offenders)


def test_required_policy_values_cannot_be_omitted() -> None:
    required = {
        "policy_version",
        "representative_source",
        "upper_on_c",
        "lower_off_c",
        "thermal_max_age_s",
        "command_max_future_skew_s",
        "broker_offline_grace_s",
        "backend_state_max_age_s",
        "safe_local_exit_min_stable_s",
        "predictive_enabled",
    }
    fields = {field.name: field for field in dataclasses.fields(PolicyConfig)}

    assert required <= set(fields)
    for name in required:
        assert fields[name].default is dataclasses.MISSING
        assert fields[name].default_factory is dataclasses.MISSING


def test_decision_has_no_actuator_or_transport_fields() -> None:
    field_names = {field.name for field in dataclasses.fields(PolicyDecision)}

    assert not {
        "gpio",
        "pwm_output",
        "mqtt_client",
        "db_session",
        "relay_state",
    } & field_names
    assert "actuation_intent" in field_names
