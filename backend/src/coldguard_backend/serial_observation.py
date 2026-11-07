"""Map Member A's serial observation tokens to wire measurement sections."""

import math
import re

_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def _reading(fields, name, status):
    token = fields.get(name)
    if token is None or status not in fields:
        raise ValueError(f"serial frame is missing {name} or {status}")
    if token == "nan":
        return None
    if not _NUMBER.fullmatch(token) or not math.isfinite(value := float(token)):
        raise ValueError(f"{name} is not a finite serial reading")
    return value if fields.get(status) == "OK" else None


def serial_observation(fields: dict[str, str]) -> dict:
    """Map values and quality without promoting unverified source readings."""
    thermal = {
        slot: _reading(fields, f"raw_{slot}_c", f"raw_{slot}_status")
        for slot in ("t1", "t2", "t3")
    }
    environment = {
        "t_air": _reading(fields, "t_ambient_c", "t_ambient_status"),
        "rh": _reading(fields, "relative_humidity_pct", "relative_humidity_status"),
    }
    electrical = {
        f"{name}_{unit}": _reading(fields, f"{name}_{unit}", f"{name}_status")
        for name, unit in (("voltage", "v"), ("current", "a"), ("power", "w"), ("energy", "wh"))
    }
    quality = {"overall": fields.get("quality"), "device_mode": fields.get("device_mode")}
    for section, readings in (
        ("thermal", thermal), ("environment", environment), ("electrical", electrical),
    ):
        observed = fields.get(f"{section}_quality")
        quality[section] = "DEGRADED" if observed == "VALID" and None in readings.values() else observed

    duty = fields.get("pwm_duty", "")
    if not duty.isdecimal() or int(duty) > 1000:
        raise ValueError("applied PWM is outside the permille range")
    door = fields.get("door_open")
    if door not in ("0", "1", "nan") or "door_status" not in fields:
        raise ValueError("serial door state is invalid")
    door_state = {"0": "CLOSED", "1": "OPEN"}.get(door, "UNKNOWN")
    if fields.get("door_status") != "OK":
        door_state = "UNKNOWN"
    return {
        "thermal": thermal,
        "environment": environment,
        "electrical": electrical,
        "quality": quality,
        "door": {"state": door_state},
        "actuation": {"cooling": fields.get("cooling_applied"), "duty": int(duty) / 1000},
    }
