"""H8 bench console grammar.

The H8 image is a real supervised bench image with its own command set:
STAGE/SUPERVISE/ARM/START/STOP/ESTOP/CLEAR/FAN/DOOR/ACK/STATUS. Its START
takes no duration; the selected stage fixes both duty and duration. It also
requires a fresh host ACK before START and during the run. These builders
never guess: every token, stage and run word is validated first.
"""

from __future__ import annotations

import re

from .protocol import CommandError, TelemetryFrame

_TOKEN_RE = re.compile(r"^[0-9A-Fa-f]{1,8}$")
_STAGE_RE = re.compile(r"^[A-Fa-f]$")
_SEQ_MAX = 0xFFFFFFFF


def token(value: str) -> str:
    text = (value or "").strip()
    if not _TOKEN_RE.match(text):
        raise CommandError("H8 token must be 1..8 hexadecimal characters")
    return text.upper()


def stage(letter: str) -> bytes:
    value = (letter or "").strip().upper()
    if not _STAGE_RE.match(value):
        raise CommandError("H8 stage must be one of A..F")
    return f"STAGE {value}\n".encode("ascii")


def supervise(token_value: str) -> bytes:
    return f"SUPERVISE {token(token_value)}\n".encode("ascii")


def arm(token_value: str) -> bytes:
    return f"ARM {token(token_value)}\n".encode("ascii")


def start() -> bytes:
    return b"START\n"


def stop() -> bytes:
    return b"STOP\n"


def estop() -> bytes:
    return b"ESTOP\n"


def clear(token_value: str) -> bytes:
    return f"CLEAR {token(token_value)}\n".encode("ascii")


def fan(token_value: str) -> bytes:
    return f"FAN {token(token_value)}\n".encode("ascii")


def door(near_low: bool, token_value: str) -> bytes:
    polarity = "NEAR_LOW" if near_low else "NEAR_HIGH"
    return f"DOOR {polarity} {token(token_value)}\n".encode("ascii")


def run_word(run_id: str) -> int | None:
    text = (run_id or "").strip().lower()
    if text.startswith("run-"):
        text = text[4:]
    if not text or len(text) > 8:
        return None
    try:
        return int(text, 16)
    except ValueError:
        return None


def ack(run_id: str | int, seq: int) -> bytes:
    word = run_id if isinstance(run_id, int) else run_word(run_id)
    if word is None or not 0 <= word <= 0xFFFFFFFF:
        raise CommandError("H8 ACK run id must be a 1..8 hex run word")
    sequence = int(seq)
    if not 0 <= sequence <= _SEQ_MAX:
        raise CommandError("H8 ACK seq must be an unsigned 32-bit integer")
    return f"ACK {word:08x} {sequence}\n".encode("ascii")


def ack_from_frame(frame: TelemetryFrame) -> bytes | None:
    if not frame.is_h8:
        return None
    run_id = frame.kv.get("run_id")
    seq = frame.seq
    if run_id is None or seq is None:
        return None
    try:
        return ack(run_id, seq)
    except CommandError:
        return None


def status() -> bytes:
    return b"STATUS\n"


def parse_door_polarity(value: str) -> str | None:
    text = (value or "").strip().upper()
    if text in {"NEAR_LOW", "LOW"}:
        return "NEAR_LOW"
    if text in {"NEAR_HIGH", "HIGH"}:
        return "NEAR_HIGH"
    return None
