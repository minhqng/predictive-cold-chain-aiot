"""Leader-owned host clock verification (portable across hosts).

The PC system clock is the ColdGuard time authority - on whatever host runs
the stack, not one particular machine. This module verifies the running
host's UTC against a network time source BEFORE the gateway may anchor
device time for command admission:

- ``VERIFIED``: the host's timezone-aware UTC is within the configured
  tolerance of a reachable trusted NTP source;
- ``UNVERIFIED``: no trusted source answered (offline or wrong clock) - the
  caller must NOT anchor device time, and the device keeps the delivered
  fail-closed EPOCH_UNSYNCHRONIZED behavior. Being offline never grants
  control.

Timestamps are timezone-aware UTC end to end; a host in any local timezone
with a correct UTC produces identical protocol timestamps. Nothing about a
specific machine (name, address, install path) enters the protocol.

Configuration (environment, with shipped defaults):
- COLDGUARD_NTP_HOSTS: comma-separated NTP host list
- COLDGUARD_HOST_CLOCK_TOLERANCE_S: max accepted |host - NTP| in seconds
- COLDGUARD_CLOCK_RECHECK_S: how long a VERIFIED verdict is reused before
  the bridge probes again (long sessions can drift or lose the network)
"""

from __future__ import annotations

import os
import socket
import struct
from datetime import datetime, timezone

_EPOCH_1900 = 2208988800  # seconds between 1900-01-01 and the Unix epoch

DEFAULT_NTP_HOSTS = ("time.cloudflare.com", "pool.ntp.org", "time.google.com")
DEFAULT_TOLERANCE_S = 1.0
DEFAULT_RECHECK_S = 1800.0
PROBE_TIMEOUT = 2.0


def _env_hosts() -> tuple[str, ...]:
    raw = os.environ.get("COLDGUARD_NTP_HOSTS")
    if not raw:
        return DEFAULT_NTP_HOSTS
    hosts = tuple(h.strip() for h in raw.split(",") if h.strip())
    return hosts or DEFAULT_NTP_HOSTS


def _probe(host: str, timeout: float = PROBE_TIMEOUT, port: int = 123) -> float:
    """One NTP query; returns the network UTC epoch seconds, raises OSError."""
    packet = bytearray(48)
    packet[0] = 0x23  # LI=0, VN=4, Mode=3 (client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(bytes(packet), (host, port))
        data, _ = sock.recvfrom(48)
    if len(data) < 48:
        raise OSError("short NTP response")
    li_vn_mode = data[0]
    if li_vn_mode & 0x07 != 0x04:  # only a real server answer anchors time
        raise OSError("bad NTP mode")
    seconds, fraction = struct.unpack("!II", data[40:48])
    if seconds == 0:
        raise OSError("empty NTP timestamp")
    return seconds - _EPOCH_1900 + fraction / 2.0**32


def verify_host_clock(now: datetime | None = None) -> dict:
    """Returns a verdict dict; never raises for unreachable networks."""
    at = (now or datetime.now(timezone.utc))
    # The protocol clock must come from the running host's UTC state, taken
    # independently of any local timezone setting.
    system_utc = at if at.tzinfo is not None else at.replace(tzinfo=timezone.utc)
    system_epoch = system_utc.timestamp()
    tolerance = float(os.environ.get("COLDGUARD_HOST_CLOCK_TOLERANCE_S",
                                     DEFAULT_TOLERANCE_S))
    reasons = []
    for host in _env_hosts():
        try:
            ntp_epoch = _probe(host)
        except OSError as exc:
            reasons.append(f"{host}: {exc}")
            continue
        except socket.timeout:
            reasons.append(f"{host}: timeout")
            continue
        skew = abs(system_epoch - ntp_epoch)
        if skew <= tolerance:
            return {
                "verdict": "VERIFIED",
                "source": host,
                "skew_s": round(system_epoch - ntp_epoch, 3),
                "tolerance_s": tolerance,
                "system_utc": system_utc,
                "ntp_utc": datetime.fromtimestamp(ntp_epoch, timezone.utc),
            }
        return {
            "verdict": "OUT_OF_TOLERANCE",
            "source": host,
            "skew_s": round(system_epoch - ntp_epoch, 3),
            "tolerance_s": tolerance,
            "system_utc": system_utc,
            "ntp_utc": datetime.fromtimestamp(ntp_epoch, timezone.utc),
        }
    return {
        "verdict": "UNVERIFIED",
        "source": None,
        "reasons": reasons,
        "system_utc": system_utc,
    }


def recheck_interval_s() -> float:
    raw = os.environ.get("COLDGUARD_CLOCK_RECHECK_S")
    try:
        value = float(raw) if raw else DEFAULT_RECHECK_S
    except ValueError:
        value = DEFAULT_RECHECK_S
    return max(value, 0.0)
