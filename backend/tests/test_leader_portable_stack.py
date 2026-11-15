"""Leader portable runtime: config precedence + identity-based serial select.

ColdGuard must run unmodified on a different demo host: every endpoint is
configuration (env > portable runtime-config.json > shipped defaults) and
the device port is chosen by USB identity, never a hardcoded name.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from integration.leader_portable_stack import (  # noqa: E402
    RuntimeConfig, resolve_runtime_config, select_serial_port,
)


def test_defaults_match_the_current_environment_ports():
    cfg = resolve_runtime_config()
    assert cfg.broker_port == 18830
    assert cfg.postgres_port == 54329
    assert cfg.backend_port == 8000
    assert cfg.device_id == "coldguard-001"
    assert cfg.require_clock_check is True


def test_env_overrides_every_default(monkeypatch):
    monkeypatch.setenv("COLDGUARD_SERIAL_PORT", "COM17")
    monkeypatch.setenv("COLDGUARD_BROKER_PORT", "28830")
    monkeypatch.setenv("COLDGUARD_DEVICE_ID", "coldguard-002")
    monkeypatch.setenv("COLDGUARD_POSTGRES_PORT", "55329")
    cfg = resolve_runtime_config()
    assert cfg.serial_port == "COM17"
    assert cfg.broker_port == 28830
    assert cfg.device_id == "coldguard-002"
    assert cfg.postgres_port == 55329


def test_config_file_between_env_and_defaults(monkeypatch, tmp_path):
    cfg_file = tmp_path / "runtime-config.json"
    cfg_file.write_text('{"broker_port": 38830, "device_id": "cg-x"}', encoding="utf-8")
    monkeypatch.setenv("COLDGUARD_RUNTIME_CONFIG", str(cfg_file))
    # env wins over the file, file wins over defaults:
    monkeypatch.delenv("COLDGUARD_BROKER_PORT", raising=False)
    monkeypatch.setenv("COLDGUARD_DEVICE_ID", "cg-env")
    cfg = resolve_runtime_config()
    assert cfg.broker_port == 38830
    assert cfg.device_id == "cg-env"


class FakePort:
    def __init__(self, device, description="", hwid="", serial_number="", manufacturer=""):
        self.device = device
        self.description = description
        self.hwid = hwid
        self.serial_number = serial_number
        self.manufacturer = manufacturer


def fake_ports(monkeypatch, ports):
    from serial.tools import list_ports as _lp

    class FakeList:
        @staticmethod
        def comports():
            return ports

    monkeypatch.setattr(_lp, "comports", FakeList.comports)


def test_serial_select_matches_the_s3_identity_not_the_port_name(monkeypatch):
    fake_ports(monkeypatch, [
        FakePort("COM10", description="Arduino Uno", hwid="USB VID:PID=2341:0043"),
        FakePort("COM7",  description="USB Serial Device (COM7)",
                 hwid="USB VID:PID=303A:1001 SER=54:32:04"),
    ])
    cfg = RuntimeConfig()  # default hint: the Espressif VID the S3 enumerates under
    assert "303A" in "USB VID:PID=303A:1001".upper()
    result = select_serial_port(cfg)
    assert result["port"] == "COM7", result


def test_serial_select_hint_matches_description(monkeypatch):
    fake_ports(monkeypatch, [
        FakePort("COM4", description="USB Serial Device (COM4)"),
    ])
    monkeypatch.setenv("COLDGUARD_SERIAL_HINT", "USB Serial")
    cfg = resolve_runtime_config()
    assert select_serial_port(cfg)["port"] == "COM4"


def test_serial_select_refuses_to_guess_among_many(monkeypatch):
    """No hint, several USB ports: it must name the conflict instead of
    picking a device that may be someone else's (a wrong port is a wrong
    device, and a wrong device must never anchor time)."""
    fake_ports(monkeypatch, [
        FakePort("COM5", description="USB Serial A"),
        FakePort("COM9", description="USB Serial B"),
    ])
    result = select_serial_port(RuntimeConfig(serial_hint="NO-SUCH-ID"))
    assert result["port"] is None
    assert result["reason"] == "IDENTITY_NOT_FOUND"
    assert "COM5" in result["candidate"] and "COM9" in result["candidate"]


def test_serial_select_explicit_name_beats_everything(monkeypatch):
    fake_ports(monkeypatch, [FakePort("COM20", description="USB X")])
    cfg = RuntimeConfig(serial_port="COM4")
    assert select_serial_port(cfg) == {"port": "COM4", "reason": "EXPLICIT",
                                       "candidate": None}
