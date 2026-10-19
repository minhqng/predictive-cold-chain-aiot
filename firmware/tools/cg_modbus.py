"""ColdGuard W03 - Modbus RTU codec and PZEM-017 register decoding.

This is the host-side reference for the rules the firmware implements in C
(``firmware/main/cg_crc16.c`` and ``cg_pzem.c``):

* CRC16/MODBUS, init 0xFFFF, polynomial 0xA001, low byte first on the wire;
* read-only function codes 0x03 (holding) and 0x04 (input);
* PZEM-017 register map from docs/01 section 9.3:
    - input 0x0000 voltage, 0.01 V/count
    - input 0x0001 current, 0.01 A/count
    - input 0x0002..0x0003 power, 0.1 W/count, low word first
    - input 0x0004..0x0005 energy, 1 Wh/count, low word first
    - holding 0x0003 current range: 0x0000=100 A, 0x0001=50 A,
      0x0002=200 A, 0x0003=300 A
* response classification: TIMEOUT (transport), CRC_ERR, BAD_SLAVE,
  BAD_FUNCTION, BAD_LENGTH, EXCEPTION, UART_ERR.

The module never builds a write request. A-W03-04 is READ ONLY: a register
write must not be possible through this tool, not merely "not used".
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Sequence

FC_READ_HOLDING = 0x03
FC_READ_INPUT = 0x04

REG_VOLTAGE = 0x0000
REG_CURRENT = 0x0001
REG_POWER_L = 0x0002
REG_POWER_H = 0x0003
REG_ENERGY_L = 0x0004
REG_ENERGY_H = 0x0005
INPUT_REGISTER_COUNT = 6

HOLDING_CURRENT_RANGE = 0x0003
RANGE_100A = 0x0000
RANGE_50A = 0x0001
RANGE_200A = 0x0002
RANGE_300A = 0x0003

VOLT_LSB = 0.01
CURRENT_LSB = 0.01
POWER_LSB = 0.1
ENERGY_LSB = 1.0

INPUT_FRAME_LEN = 17  # slave + fc + count + 12 data + 2 crc
RANGE_FRAME_LEN = 7  # slave + fc + count + 2 data + 2 crc
EXCEPTION_FRAME_LEN = 5  # slave + fc|0x80 + code + 2 crc

PROFILE_NAMES = {
    RANGE_100A: "100A",
    RANGE_50A: "50A",
    RANGE_200A: "200A",
    RANGE_300A: "300A",
}


class Status(str, enum.Enum):
    """Stable status tokens, identical to ``cg_pzem_status_name`` in C."""

    OK = "OK"
    TIMEOUT = "TIMEOUT"
    CRC_ERR = "CRC_ERR"
    BAD_SLAVE = "BAD_SLAVE"
    BAD_FUNCTION = "BAD_FUNCTION"
    BAD_LENGTH = "BAD_LENGTH"
    EXCEPTION = "EXCEPTION"
    UART_ERR = "UART_ERR"


class FrameError(ValueError):
    """Raised when a frame cannot be decoded at all (programming error)."""


def crc16(data: bytes) -> int:
    """CRC16/MODBUS (init 0xFFFF, reflected polynomial 0xA001)."""

    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc(payload: bytes) -> bytes:
    """Append the CRC in Modbus wire order (low byte, then high byte)."""

    crc = crc16(payload)
    return payload + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def crc_ok(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    return crc16(frame[:-2]) == (frame[-2] | (frame[-1] << 8))


def build_read_request(slave: int, function: int, register: int, count: int) -> bytes:
    if not 1 <= slave <= 247:
        raise ValueError(f"slave address out of range: {slave}")
    if function not in (FC_READ_HOLDING, FC_READ_INPUT):
        raise ValueError("only read function codes 0x03/0x04 are allowed")
    if not 0 <= register <= 0xFFFF or not 1 <= count <= 0x7D:
        raise ValueError("register/count out of range")
    payload = bytes(
        (
            slave,
            function,
            (register >> 8) & 0xFF,
            register & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
        )
    )
    return append_crc(payload)


def build_read_input(slave: int) -> bytes:
    """Read input registers 0x0000..0x0005 (V, I, P, E)."""

    return build_read_request(slave, FC_READ_INPUT, REG_VOLTAGE, INPUT_REGISTER_COUNT)


def build_read_range(slave: int) -> bytes:
    """Read holding register 0x0003 (current-range profile). READ ONLY."""

    return build_read_request(slave, FC_READ_HOLDING, HOLDING_CURRENT_RANGE, 1)


@dataclasses.dataclass(frozen=True)
class ParsedFrame:
    status: Status
    exception_code: int | None = None
    registers: tuple[int, ...] = ()


def _classify(frame: bytes, slave: int, function: int) -> tuple[Status, int | None]:
    """Common checks. Returns (status, exception_code)."""

    if len(frame) < 4:
        return Status.BAD_LENGTH, None
    if not crc_ok(frame):
        return Status.CRC_ERR, None
    if frame[0] != slave:
        return Status.BAD_SLAVE, None
    if frame[1] & 0x80:
        code = frame[2] if len(frame) >= EXCEPTION_FRAME_LEN else None
        return Status.EXCEPTION, code
    if frame[1] != function:
        return Status.BAD_FUNCTION, None
    return Status.OK, None


def parse_input(frame: bytes, slave: int) -> ParsedFrame:
    """Parse a 0x04 response into six raw registers."""

    status, exception = _classify(frame, slave, FC_READ_INPUT)
    if status is not Status.OK:
        return ParsedFrame(status=status, exception_code=exception)
    if len(frame) != INPUT_FRAME_LEN or frame[2] != 12:
        return ParsedFrame(status=Status.BAD_LENGTH)
    registers = tuple(
        (frame[3 + index * 2] << 8) | frame[4 + index * 2] for index in range(6)
    )
    return ParsedFrame(status=Status.OK, registers=registers)


def parse_range(frame: bytes, slave: int) -> ParsedFrame:
    """Parse a 0x03 response into the raw current-range value."""

    status, exception = _classify(frame, slave, FC_READ_HOLDING)
    if status is not Status.OK:
        return ParsedFrame(status=status, exception_code=exception)
    if len(frame) != RANGE_FRAME_LEN or frame[2] != 2:
        return ParsedFrame(status=Status.BAD_LENGTH)
    return ParsedFrame(status=Status.OK, registers=((frame[3] << 8) | frame[4],))


@dataclasses.dataclass(frozen=True)
class Values:
    voltage_v: float
    current_a: float
    power_w: float
    energy_wh: float


def decode_input(registers: Sequence[int]) -> Values:
    """Apply the canonical scaling to six input registers."""

    if len(registers) < INPUT_REGISTER_COUNT:
        raise FrameError(f"need {INPUT_REGISTER_COUNT} registers, got {len(registers)}")
    power_raw = (registers[REG_POWER_H] << 16) | registers[REG_POWER_L]
    energy_raw = (registers[REG_ENERGY_H] << 16) | registers[REG_ENERGY_L]
    return Values(
        voltage_v=registers[REG_VOLTAGE] * VOLT_LSB,
        current_a=registers[REG_CURRENT] * CURRENT_LSB,
        power_w=power_raw * POWER_LSB,
        energy_wh=energy_raw * ENERGY_LSB,
    )


def profile_name(raw_value: int) -> str:
    return PROFILE_NAMES.get(raw_value, "UNKNOWN")


def range_hex(raw_value: int) -> str:
    return f"0x{raw_value:04X}"


def format_range_readback(frame: bytes, slave: int) -> dict:
    """Decode a range response for the readback evidence file."""

    parsed = parse_range(frame, slave)
    if parsed.status is not Status.OK:
        return {
            "status": parsed.status.value,
            "exception_code": parsed.exception_code,
            "raw_value": None,
            "value_hex": "nan",
            "profile": "nan",
            "crc_ok": crc_ok(frame),
        }
    raw = parsed.registers[0]
    return {
        "status": parsed.status.value,
        "exception_code": None,
        "raw_value": raw,
        "value_hex": range_hex(raw),
        "profile": profile_name(raw),
        "crc_ok": True,
    }
