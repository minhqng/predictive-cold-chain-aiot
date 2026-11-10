"""Clock-quality-aware timing and transmission latency metrics (C-W05-05).

Only calculate:
    backend_received_at - captured_at
when the clocks have sufficiently verified compatible timing semantics.

For clockless or untrusted timestamps:
    latency_ms = None
with an explicit status and reason.

Invariants:
- Never derive UTC from uptime.
- Do not silently substitute gateway time for device event time.
- Always expose backend_received_at.
- Explicitly cover unavailable, negative, future, replay and synchronized cases.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

TimingStatus = Literal[
    "SYNCHRONIZED",
    "UNVERIFIED_CLOCK",
    "UNAVAILABLE",
    "NEGATIVE_LATENCY",
    "FUTURE_TIMESTAMP",
    "REPLAY",
    "UNTRUSTED_CLOCK",
    "EXCESSIVE_SKEW",
]

# 24 hours in milliseconds: any latency greater than this without explicit
# offline store-and-forward context is classified as excessive clock drift/skew.
DEFAULT_MAX_PLAUSIBLE_LATENCY_MS = 86_400_000.0


@dataclass(frozen=True)
class TimingMetrics:
    """Explicit, auditable transmission timing metrics."""

    backend_received_at: datetime
    captured_at: datetime | None
    latency_ms: float | None
    status: TimingStatus
    reason: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["backend_received_at"] = self.backend_received_at.isoformat()
        if self.captured_at is not None:
            result["captured_at"] = self.captured_at.isoformat()
        return result


def compute_timing_metrics(
    backend_received_at: datetime,
    captured_at: datetime | None,
    *,
    clock_sync_verified: bool = False,
    clock_quality: str | None = None,
    serial_source: Any | None = None,
    is_replay: bool = False,
    max_plausible_latency_ms: float = DEFAULT_MAX_PLAUSIBLE_LATENCY_MS,
) -> TimingMetrics:
    """Compute clock-quality-aware transmission latency.

    Rules:
    1. If backend_received_at lacks timezone info: status UNTRUSTED_CLOCK.
    2. If is_replay is True: historical replay does not represent live network
       transmission. latency_ms is None with status REPLAY.
    3. If captured_at is None, or serial_source is present, or clock_quality
       is UNAVAILABLE: the device has no wall clock. latency_ms is None with status UNAVAILABLE.
    4. If captured_at lacks timezone info: status UNTRUSTED_CLOCK.
    5. If clock_sync_verified is False: presence of timezone-aware timestamp does
       NOT prove clock synchronization (Doc 01 §18, Doc 02 §4). Clocks are unverified;
       latency_ms is None with status UNVERIFIED_CLOCK.
    6. When clock synchronization has been authoritatively verified:
       a. If captured_at > backend_received_at: device clock claims a time in the
          future (negative latency). latency_ms is None with status NEGATIVE_LATENCY.
       b. If latency exceeds max_plausible_latency_ms: latency_ms is None with status
          EXCESSIVE_SKEW.
       c. Otherwise: latency_ms is computed as (backend_received_at - captured_at)
          in milliseconds with status SYNCHRONIZED.
    """
    if backend_received_at.tzinfo is None:
        return TimingMetrics(
            backend_received_at=backend_received_at,
            captured_at=captured_at,
            latency_ms=None,
            status="UNTRUSTED_CLOCK",
            reason="backend_received_at lacks timezone information",
        )

    # Replay check takes precedence over live latency
    if is_replay:
        return TimingMetrics(
            backend_received_at=backend_received_at,
            captured_at=captured_at,
            latency_ms=None,
            status="REPLAY",
            reason="Replayed telemetry delivery; live transmission latency is not applicable",
        )

    # Clockless device check
    if (
        captured_at is None
        or serial_source is not None
        or clock_quality == "UNAVAILABLE"
    ):
        return TimingMetrics(
            backend_received_at=backend_received_at,
            captured_at=captured_at,
            latency_ms=None,
            status="UNAVAILABLE",
            reason=(
                "Device has no wall clock; clockless observation. "
                "Gateway receipt time is not substituted for device event time."
            ),
        )

    if captured_at.tzinfo is None:
        return TimingMetrics(
            backend_received_at=backend_received_at,
            captured_at=captured_at,
            latency_ms=None,
            status="UNTRUSTED_CLOCK",
            reason="Device captured_at lacks timezone information",
        )

    if not clock_sync_verified:
        return TimingMetrics(
            backend_received_at=backend_received_at,
            captured_at=captured_at,
            latency_ms=None,
            status="UNVERIFIED_CLOCK",
            reason=(
                "Device captured_at timestamp present but clock synchronization has not "
                "been verified by an authoritative trusted source. Latency calculation withheld."
            ),
        )

    delta_seconds = (backend_received_at - captured_at).total_seconds()
    delta_ms = delta_seconds * 1000.0

    if delta_ms < 0:
        return TimingMetrics(
            backend_received_at=backend_received_at,
            captured_at=captured_at,
            latency_ms=None,
            status="NEGATIVE_LATENCY",
            reason=(
                f"Device captured_at is in the future relative to backend_received_at "
                f"by {-delta_ms:.1f} ms (clock skew)"
            ),
        )

    if delta_ms > max_plausible_latency_ms:
        return TimingMetrics(
            backend_received_at=backend_received_at,
            captured_at=captured_at,
            latency_ms=None,
            status="EXCESSIVE_SKEW",
            reason=(
                f"Latency of {delta_ms:.1f} ms exceeds plausible limit of "
                f"{max_plausible_latency_ms:.1f} ms"
            ),
        )

    return TimingMetrics(
        backend_received_at=backend_received_at,
        captured_at=captured_at,
        latency_ms=round(delta_ms, 3),
        status="SYNCHRONIZED",
        reason="Clocks are verified synchronized within plausible bounds",
    )
