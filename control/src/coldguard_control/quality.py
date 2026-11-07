"""Physical-quality input contract (Member D, W05).

The policy layer consumes *quality + freshness*, never a bare number
(Doc 01 section 19; Doc 02 sections 40.1 and 67). This module separates three
questions that are often collapsed by mistake:

```text
thermal_safety_usable
    Can local deterministic protection still act on the thermal state?

predictive_inputs_available
    Are all channels the predictive path consumes present, VALID and fresh?

verification_confidence
    How much independent evidence exists for an electrical/thermal claim?
```

A missing PZEM does not remove local thermal protection, and it does not
become a measured zero: it makes electrical evidence ``UNKNOWN`` and blocks the
predictive path until a frozen model contract says the model can run without
it. Likewise a missing door channel cannot be treated as ``CLOSED``.

``UNKNOWN`` is never mapped to ``VALID``. A VALID quality with no age is not
control-fresh: the caller must supply the observation age, and the matching
maximum age must be explicitly configured (no hidden freshness constants).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .types import QualityState, ReasonCode


class QualityInputError(ValueError):
    """Raised when an observation contradicts the documented semantics."""


@dataclass(frozen=True, slots=True)
class ChannelObservation:
    """One channel's quality and age since acquisition.

    ``age_s`` is required for a control decision. ``None`` means the caller did
    not supply an observation age, which is not the same as fresh zero.
    """

    quality: QualityState
    age_s: float | None


@dataclass(frozen=True, slots=True)
class QualityBlocker:
    """A named reason why a channel cannot feed a decision."""

    channel: str
    quality: QualityState
    reason_code: ReasonCode
    detail: str


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    """Deterministic quality/freshness assessment for one policy evaluation."""

    thermal_safety_usable: bool
    predictive_inputs_available: bool
    verification_confidence: QualityState
    blockers: tuple[QualityBlocker, ...] = field(default_factory=tuple)

    @property
    def degraded(self) -> bool:
        return not self.predictive_inputs_available or self.blockers != ()


def _require_enum(name: str, value: object) -> None:
    if not isinstance(value, QualityState):
        raise QualityInputError(
            f"{name} must be a QualityState member, "
            f"got {value!r} ({type(value).__name__})"
        )


def _require_age(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualityInputError(f"{name} age_s must be a finite number")
    if not math.isfinite(float(value)):
        raise QualityInputError(f"{name} age_s must be a finite number")
    if float(value) < 0.0:
        raise QualityInputError(f"{name} age_s cannot be negative")


def _require_max_age(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualityInputError(f"{name} max age must be a finite number")
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise QualityInputError(f"{name} max age must be positive")


def _fresh(observation: ChannelObservation, max_age_s: float | None) -> bool:
    """True only for a configured, finite, non-negative age inside the bound.

    Both VALID and DEGRADED observations can be fresh; INVALID and UNKNOWN
    cannot be fresh because they represent unusable data.
    """
    if observation.quality not in (QualityState.VALID, QualityState.DEGRADED):
        return False
    if observation.age_s is None or max_age_s is None:
        return False
    return float(observation.age_s) <= float(max_age_s)


def _blocker(
    channel: str,
    observation: ChannelObservation,
    reason_code: ReasonCode,
    detail: str,
) -> QualityBlocker:
    return QualityBlocker(
        channel=channel,
        quality=observation.quality,
        reason_code=reason_code,
        detail=detail,
    )


def _verification_confidence(
    thermal: ChannelObservation,
    thermal_fresh: bool,
    electrical: ChannelObservation,
    electrical_fresh: bool,
) -> QualityState:
    """Collapse electrical/thermal evidence into a confidence state.

    Missing evidence is ``UNKNOWN`` (never a healthy default). A determined
    electrical failure is ``INVALID``. A degraded but usable temperature path
    is ``DEGRADED``. Only a fresh VALID thermal *and* electrical path is
    ``VALID``.

    For degraded thermal, freshness is evaluated separately; here we care about
    the quality combination when both are fresh enough to contribute.
    """

    if electrical.quality is QualityState.INVALID:
        return QualityState.INVALID
    if thermal.quality is QualityState.INVALID:
        return QualityState.INVALID
    if not electrical_fresh or not thermal_fresh:
        return QualityState.UNKNOWN
    if (
        thermal.quality is QualityState.VALID
        and electrical.quality is QualityState.VALID
    ):
        return QualityState.VALID
    if (
        thermal.quality is QualityState.DEGRADED
        and electrical.quality is QualityState.VALID
    ):
        return QualityState.DEGRADED
    if (
        thermal.quality is QualityState.VALID
        and electrical.quality is QualityState.DEGRADED
    ):
        return QualityState.DEGRADED
    if (
        thermal.quality is QualityState.DEGRADED
        and electrical.quality is QualityState.DEGRADED
    ):
        return QualityState.DEGRADED
    return QualityState.UNKNOWN


def assess_quality(
    *,
    thermal: ChannelObservation,
    electrical: ChannelObservation,
    door: ChannelObservation,
    thermal_max_age_s: float,
    electrical_max_age_s: float | None,
    door_max_age_s: float | None,
) -> QualityAssessment:
    """Assess local thermal safety, prediction availability and verification.

    The thermal bound is mandatory because local protection cannot use a
    stale temperature. Electrical and door bounds are optional only because
    their characterization may not be frozen yet; when the age is supplied but
    no bound exists, the channel is not considered fresh (fail closed).
    """
    _require_enum("thermal.quality", thermal.quality)
    _require_enum("electrical.quality", electrical.quality)
    _require_enum("door.quality", door.quality)
    _require_age("thermal", thermal.age_s)
    _require_age("electrical", electrical.age_s)
    _require_age("door", door.age_s)
    _require_max_age("thermal", thermal_max_age_s)
    _require_max_age("electrical", electrical_max_age_s)
    _require_max_age("door", door_max_age_s)

    thermal_fresh = _fresh(thermal, thermal_max_age_s)
    electrical_fresh = _fresh(electrical, electrical_max_age_s)
    door_fresh = _fresh(door, door_max_age_s)

    thermal_safety_usable = (
        thermal.quality is QualityState.VALID
        and thermal_fresh
    ) or (
        thermal.quality is QualityState.DEGRADED
        and thermal.age_s is not None
        and thermal_max_age_s is not None
        and float(thermal.age_s) <= float(thermal_max_age_s)
    )
    predictive_inputs_available = (
        thermal.quality is QualityState.VALID
        and thermal_fresh
        and electrical.quality is QualityState.VALID
        and electrical_fresh
        and door.quality is QualityState.VALID
        and door_fresh
    )

    blockers: list[QualityBlocker] = []
    if not thermal_safety_usable:
        blockers.append(
            _blocker(
                "thermal",
                thermal,
                (
                    ReasonCode.THERMAL_STATE_INVALID
                    if thermal.quality in (QualityState.INVALID, QualityState.UNKNOWN)
                    else ReasonCode.SENSOR_DEGRADED
                ),
                "thermal state is invalid, unknown or not control-fresh",
            )
        )
    elif thermal.quality is not QualityState.VALID:
        blockers.append(
            _blocker(
                "thermal",
                thermal,
                ReasonCode.SENSOR_DEGRADED,
                "thermal state is degraded; predictive action is prohibited "
                "unless a frozen model contract supports the missing channel",
            )
        )

    if electrical.quality is not QualityState.VALID or not electrical_fresh:
        if electrical.quality in (QualityState.INVALID, QualityState.UNKNOWN):
            reason = ReasonCode.PZEM_UNAVAILABLE
        else:
            reason = ReasonCode.SENSOR_DEGRADED
        blockers.append(
            _blocker(
                "electrical",
                electrical,
                reason,
                "electrical evidence is missing, invalid or stale; physical "
                "verification confidence is reduced",
            )
        )

    if door.quality is not QualityState.VALID or not door_fresh:
        blockers.append(
            _blocker(
                "door",
                door,
                ReasonCode.SENSOR_DEGRADED,
                "door channel is unknown, invalid or stale; it is never "
                "treated as CLOSED",
            )
        )

    return QualityAssessment(
        thermal_safety_usable=thermal_safety_usable,
        predictive_inputs_available=predictive_inputs_available,
        verification_confidence=_verification_confidence(
            thermal,
            thermal_fresh,
            electrical,
            electrical_fresh,
        ),
        blockers=tuple(blockers),
    )
