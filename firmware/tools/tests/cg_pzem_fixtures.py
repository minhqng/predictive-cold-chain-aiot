"""Synthetic PZEM line/frame builders shared by the W03 host-tool tests.

These helpers produce *test fixtures only*: the frames and log lines exist
to exercise the parser, the codec and the CLIs. They are never written
into ``evidence/`` and are never quoted as measurements.
"""

from __future__ import annotations

import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cg_modbus  # noqa: E402


def input_response(
    slave: int, voltage_raw: int, current_raw: int, power_raw: int, energy_raw: int
) -> bytes:
    """A 0x04 response frame with six registers (power/energy low word first)."""

    registers = [
        voltage_raw & 0xFFFF,
        current_raw & 0xFFFF,
        power_raw & 0xFFFF,
        (power_raw >> 16) & 0xFFFF,
        energy_raw & 0xFFFF,
        (energy_raw >> 16) & 0xFFFF,
    ]
    payload = bytes((slave, 0x04, 12)) + b"".join(value.to_bytes(2, "big") for value in registers)
    return cg_modbus.append_crc(payload)


def range_response(slave: int, value: int) -> bytes:
    payload = bytes((slave, 0x03, 2, (value >> 8) & 0xFF, value & 0xFF))
    return cg_modbus.append_crc(payload)


def hexs(data: bytes) -> str:
    return data.hex().upper()


def cfg_line(
    slave: int = 1,
    baud: int = 9600,
    framing: str = "8N1",
    direction: str = "AUTO",
    read_only: int = 1,
) -> str:
    return (
        f"#CG PZEM_CFG slave={slave} baud={baud} framing={framing} dir={direction} "
        f"read_only={read_only}\n"
    )


def range_log_line(
    uptime_ms: int,
    value: int = 0x0001,
    slave: int = 1,
    damaged_rx: bool = False,
    status: str = "OK",
    prefix: bytes = b"",
) -> str:
    """One `#CG PZEM_RANGE` line with a complete, real (computed) frame pair."""

    tx = cg_modbus.build_read_range(slave)
    rx = prefix + range_response(slave, value)
    if damaged_rx:
        rx = rx[:-1] + bytes((rx[-1] ^ 0xFF,))
    crc_ok = 1 if cg_modbus.extract_response(rx).frame is not None else 0
    profile = cg_modbus.profile_name(value)
    return (
        f"#CG PZEM_RANGE uptime_ms={uptime_ms} status={status} value=0x{value:04X} "
        f"profile={profile} crc_ok={crc_ok} exc=0 tx={hexs(tx)} rx={hexs(rx)}\n"
    )


def poll_ok_line(
    uptime_ms: int,
    seq: int,
    voltage_v: float = 12.34,
    current_a: float = 0.0,
    power_w: float = 0.0,
    energy_wh: float = 0.0,
    slave: int = 1,
    attempts: int = 1,
    ok_count: int | None = None,
    fail_count: int = 0,
) -> str:
    """One `#CG PZEM` OK line; values are quantised to the register LSBs."""

    voltage_raw = round(voltage_v * 100)
    current_raw = round(current_a * 100)
    power_raw = round(power_w * 10)
    energy_raw = round(energy_wh)
    rx = input_response(slave, voltage_raw, current_raw, power_raw, energy_raw)
    if ok_count is None:
        ok_count = seq
    return (
        f"#CG PZEM uptime_ms={uptime_ms} seq={seq} status=OK slave={slave} "
        f"v={voltage_v:.2f} i={current_a:.2f} p={power_w:.1f} e={energy_wh:.0f} "
        f"crc_ok=1 attempts={attempts} exc=0 ok={ok_count} fail={fail_count} "
        f"tx={hexs(cg_modbus.build_read_input(slave))} rx={hexs(rx)}\n"
    )


def poll_fail_line(
    uptime_ms: int,
    seq: int,
    status: str = "TIMEOUT",
    crc_ok: int = 0,
    attempts: int = 2,
    exc: int = 0,
    ok_count: int = 0,
    fail_count: int | None = None,
    rx: str = "",
) -> str:
    if fail_count is None:
        fail_count = seq
    return (
        f"#CG PZEM uptime_ms={uptime_ms} seq={seq} status={status} slave=1 "
        f"v=nan i=nan p=nan e=nan crc_ok={crc_ok} attempts={attempts} exc={exc} "
        f"ok={ok_count} fail={fail_count} tx={hexs(cg_modbus.build_read_input(1))} rx={rx}\n"
    )
