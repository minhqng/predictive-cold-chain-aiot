"""Leader-owned portable runtime configuration.

ColdGuard's integration logic is bound to no particular demo machine: no
serial port name, broker address, database port or install path is
hardcoded in any code path. This module resolves the effective runtime
configuration from (1) optional ``runtime-config.json`` sitting NEXT TO the
repository checkout (or pointed at by ``COLDGUARD_RUNTIME_CONFIG``) and
(2) environment variables, in that order of increasing priority, with the
current environment as the shipped default file.

Provision credentials outside the repository and inject them through the environment.

Serial device selection is by USB identity, not by a fixed port name
(COM4 is only the current machine's name for the same plug):

1. ``COLDGUARD_SERIAL_PORT`` - explicit name override;
2. ``COLDGUARD_SERIAL_HINT`` - substring match against the port's
   description/serial number/hwid (default: the ESP32-S3 USB-Serial/JTAG
   identity string);
3. the only USB serial port present, when exactly one exists.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# The hardware identity of the as-built ColdGuard controller's console
# (chip: ESP32-S3 with the native USB-Serial/JTAG peripheral exposed).
# Windows enumerates that peripheral under the generic usbser driver with
# a plain description, so the stable identity is Espressif's vendor id
# (VID 303A) in the USB hwid string - the same token on every host.
DEFAULT_SERIAL_HINT = "303A"
# Distinctive defaults of the CURRENT environment; every value is here so a
# different host can override it without touching code.
DEFAULTS = {
    "serial_port": "",
    "serial_hint": DEFAULT_SERIAL_HINT,
    "broker_host": "127.0.0.1",
    "broker_port": 18830,
    "backend_port": 8000,
    "postgres_port": 54329,
    "device_id": "coldguard-001",
    # Enable only where this host's power/wiring makes going offline
    # impossible - unchecked clock stays fail-closed by default.
    "require_clock_check": True,
}


@dataclass
class RuntimeConfig:
    serial_port: str = ""
    serial_hint: str = DEFAULT_SERIAL_HINT
    broker_host: str = "127.0.0.1"
    broker_port: int = 18830
    backend_port: int = 8000
    postgres_port: int = 54329
    device_id: str = "coldguard-001"
    require_clock_check: bool = True
    sources: dict = field(default_factory=dict)


def _config_paths() -> list[Path]:
    """Candidate portable config files (optional; absence is normal)."""
    candidates: list[Path] = []
    over = os.environ.get("COLDGUARD_RUNTIME_CONFIG")
    if over:
        candidates.append(Path(over))
    candidates.append(Path(__file__).resolve().parents[3] / "runtime-config.json")
    return candidates


def _apply_file(config: RuntimeConfig, sources: dict) -> None:
    for path in _config_paths():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sources["file"] = f"unreadable: {path}"
            break
        if data:
            _apply_mapping(config, data, "file", sources)
            break


def _apply_mapping(config: RuntimeConfig, data: dict, source: str, sources: dict) -> None:
    if data.get("serial_port"):
        config.serial_port = str(data["serial_port"])
        sources[source] = sources.get(source, []) + ["serial_port"]
    if data.get("serial_hint"):
        config.serial_hint = str(data["serial_hint"])
    for key in ("broker_host", "device_id"):
        if data.get(key):
            setattr(config, key, str(data[key]))
            sources.setdefault(source, [])
    for key in ("broker_port", "backend_port", "postgres_port"):
        if data.get(key) is not None:
            setattr(config, key, int(data[key]))
    if data.get("require_clock_check") is not None:
        config.require_clock_check = bool(data["require_clock_check"])


def _apply_env(config: RuntimeConfig, sources: dict) -> None:
    port = os.environ.get("COLDGUARD_SERIAL_PORT")
    if port:
        config.serial_port = port
        sources.setdefault("env", []).append("COLDGUARD_SERIAL_PORT")
    hint = os.environ.get("COLDGUARD_SERIAL_HINT")
    if hint:
        config.serial_hint = hint
    for env_key, attr in (("COLDGUARD_BROKER_HOST", "broker_host"),
                          ("COLDGUARD_DEVICE_ID", "device_id")):
        value = os.environ.get(env_key)
        if value:
            setattr(config, attr, value)
    for env_key, attr in (("COLDGUARD_BROKER_PORT", "broker_port"),
                          ("COLDGUARD_BACKEND_PORT", "backend_port"),
                          ("COLDGUARD_POSTGRES_PORT", "postgres_port")):
        value = os.environ.get(env_key)
        if value:
            setattr(config, attr, int(value))


def resolve_runtime_config() -> RuntimeConfig:
    config = RuntimeConfig(serial_hint=DEFAULTS["serial_hint"])
    sources: dict = {}
    _apply_file(config, sources)
    _apply_env(config, sources)
    config.sources = sources
    return config


def select_serial_port(config: RuntimeConfig | None = None) -> dict:
    """Identity-based device selection. Returns
    ``{'port': name|None, 'reason': token, 'candidate': description|None}``."""
    cfg = config or resolve_runtime_config()
    if cfg.serial_port:
        return {"port": cfg.serial_port, "reason": "EXPLICIT", "candidate": None}
    try:
        from serial.tools import list_ports
    except ImportError:  # pyserial is a backend dependency; never arrive here live
        return {"port": None, "reason": "PYserial_MISSING", "candidate": None}
    ports = [p for p in list_ports.comports()]
    usb_ports = [p for p in ports if "USB" in (p.hwid or "").upper()
                 or "COM" in (p.device or "").upper()]
    hint = (cfg.serial_hint or DEFAULT_SERIAL_HINT).upper()
    for port in ports:
        haystack = " ".join(filter(None, [port.description, port.serial_number,
                                          port.hwid, port.manufacturer])).upper()
        if hint in haystack:
            return {"port": port.device, "reason": "IDENTITY_MATCH",
                    "candidate": port.description}
    if len(usb_ports) == 1:
        return {"port": usb_ports[0].device, "reason": "ONLY_USB",
                "candidate": usb_ports[0].description}
    # Fail PRECISELY instead of guessing: a wrong serial port is a wrong
    # device, and a wrong device must never anchor time or accept commands.
    names = ", ".join(sorted({p.device for p in ports})) or "none"
    return {"port": None, "reason": "IDENTITY_NOT_FOUND", "candidate": names}
