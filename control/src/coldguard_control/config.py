"""Versioned policy configuration supplied by the caller.

Design rule: this package has no built-in operating numbers. Thermal
thresholds, freshness windows, permission to enable predictive/preemptive
action and the safe-local exit stability window are all explicit constructor
arguments. Tests use synthetic values only to exercise logic; synthetic test
values are never physical truth and carry no commissioning authority
(Doc 04 section 10.3: "D does not invent safety thresholds before
measurement").

Sources:
- thresholds / hysteresis / persistence: Doc 02 sections 24, 67;
- "no magic constants": Doc 02 section 24.4, section 98;
- representative temperature choice must be explicit: Doc 01 sections 37,
  20.5;
- PWM conditional: Doc 01 section 24.3, Doc 02 section 70;
- SAFE_LOCAL exit: Doc 02 section 38, 05D section 19.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class ConfigError(ValueError):
    """Raised when policy configuration is inconsistent or incomplete."""


def _require_finite(name: str, value: object) -> float:
    """Require a finite ``int``/``float`` (``bool`` rejected) and return it.

    ``bool`` is a subclass of ``int`` in Python, so it must be excluded
    explicitly. NaN and +/-inf are rejected because a comparison such as
    ``value <= 0`` is *false* for NaN, which would let a missing/broken
    characterization silently pass validation (fail-open).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ConfigError(f"{name} must be a finite number")
    return number


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    """Explicit, versioned policy parameters.

    All values are mandatory (no defaults) so a caller cannot silently inherit
    an invented threshold. ``policy_version`` must identify the frozen
    configuration used in a run (Doc 02 section 60.7).
    """

    policy_version: str

    # Doc 01 sections 20.5/37: which temperature representation is control
    # truth must be an explicit, versioned policy choice (e.g. "TMAX").
    representative_source: str

    # Controller A boundary and hysteresis (Doc 02 sections 24.1, 25.3).
    upper_on_c: float
    lower_off_c: float

    # Control freshness for physical state (Doc 01 section 18.4,
    # Doc 02 section 67).
    thermal_max_age_s: float

    # Command timestamps must not be accepted from the far future. A command
    # created "later" than local time by more than this window is treated as a
    # schema/clock problem rather than as a valid future command (Doc 02
    # section 31.2 expiry semantics; the exact bound is frozen by Member A/C
    # during command-v0 integration).
    command_max_future_skew_s: float

    # SAFE_LOCAL entry timing (Doc 02 sections 37.1, 38).
    broker_offline_grace_s: float
    backend_state_max_age_s: float
    safe_local_exit_min_stable_s: float

    # Predictive path. Disabled unless Member B's frozen warning contract
    # exists (Doc 04 section 10.6, Doc 02 sections 21.1, 52.4).
    predictive_enabled: bool
    watch_threshold: float | None = None
    preemptive_threshold: float | None = None
    persistence_required_s: float | None = None
    prediction_max_age_s: float | None = None

    # Conditional PWM support (Doc 01 section 24.3). W03 core defaults to
    # OFF/ON only; enabling this requires a characterized duty range.
    allow_pwm_duty: bool = False
    allowed_duty_min: float | None = None
    allowed_duty_max: float | None = None

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ConfigError("policy_version must be non-empty")
        if not self.representative_source.strip():
            raise ConfigError("representative_source must be non-empty")
        if not isinstance(self.predictive_enabled, bool):
            raise ConfigError("predictive_enabled must be a boolean")
        if not isinstance(self.allow_pwm_duty, bool):
            raise ConfigError("allow_pwm_duty must be a boolean")

        # Fail closed on non-finite/bool numerics before any comparison.
        # ``nan <= 0`` / ``nan < 0`` are false, so an unguarded comparison
        # would accept a broken value and undermine staleness checks.
        upper_on = _require_finite("upper_on_c", self.upper_on_c)
        lower_off = _require_finite("lower_off_c", self.lower_off_c)
        _require_finite("thermal_max_age_s", self.thermal_max_age_s)
        _require_finite(
            "command_max_future_skew_s", self.command_max_future_skew_s
        )
        _require_finite(
            "broker_offline_grace_s", self.broker_offline_grace_s
        )
        _require_finite(
            "backend_state_max_age_s", self.backend_state_max_age_s
        )
        _require_finite(
            "safe_local_exit_min_stable_s",
            self.safe_local_exit_min_stable_s,
        )

        # Optional numerics are validated whenever supplied, even while the
        # feature is disabled, so a latent non-finite value cannot sit in a
        # configuration and become active later without review.
        for name, value in (
            ("watch_threshold", self.watch_threshold),
            ("preemptive_threshold", self.preemptive_threshold),
            ("persistence_required_s", self.persistence_required_s),
            ("prediction_max_age_s", self.prediction_max_age_s),
            ("allowed_duty_min", self.allowed_duty_min),
            ("allowed_duty_max", self.allowed_duty_max),
        ):
            if value is not None:
                _require_finite(name, value)

        if not upper_on > lower_off:
            raise ConfigError("upper_on_c must be greater than lower_off_c")
        if self.thermal_max_age_s <= 0:
            raise ConfigError("thermal_max_age_s must be positive")
        if self.command_max_future_skew_s < 0:
            raise ConfigError("command_max_future_skew_s cannot be negative")
        if self.broker_offline_grace_s < 0:
            raise ConfigError("broker_offline_grace_s cannot be negative")
        if self.backend_state_max_age_s <= 0:
            raise ConfigError("backend_state_max_age_s must be positive")
        if self.safe_local_exit_min_stable_s < 0:
            raise ConfigError(
                "safe_local_exit_min_stable_s cannot be negative"
            )

        if self.predictive_enabled:
            for name, value in (
                ("watch_threshold", self.watch_threshold),
                ("preemptive_threshold", self.preemptive_threshold),
                ("persistence_required_s", self.persistence_required_s),
                ("prediction_max_age_s", self.prediction_max_age_s),
            ):
                if value is None:
                    raise ConfigError(
                        f"{name} is required when predictive_enabled is true"
                    )
            assert self.watch_threshold is not None  # for type checkers
            assert self.preemptive_threshold is not None
            assert self.persistence_required_s is not None
            assert self.prediction_max_age_s is not None
            if not 0.0 <= self.watch_threshold <= 1.0:
                raise ConfigError("watch_threshold must be within [0, 1]")
            if not 0.0 <= self.preemptive_threshold <= 1.0:
                raise ConfigError(
                    "preemptive_threshold must be within [0, 1]"
                )
            if self.preemptive_threshold < self.watch_threshold:
                raise ConfigError(
                    "preemptive_threshold must not be below watch_threshold"
                )
            if self.persistence_required_s <= 0:
                raise ConfigError("persistence_required_s must be positive")
            if self.prediction_max_age_s <= 0:
                raise ConfigError("prediction_max_age_s must be positive")

        if self.allow_pwm_duty:
            if self.allowed_duty_min is None or self.allowed_duty_max is None:
                raise ConfigError(
                    "allowed duty bounds are required when allow_pwm_duty "
                    "is true"
                )
            if not (
                0.0
                < self.allowed_duty_min
                <= self.allowed_duty_max
                <= 1.0
            ):
                raise ConfigError(
                    "allowed duty bounds must satisfy "
                    "0 < min <= max <= 1"
                )
        else:
            if (
                self.allowed_duty_min is not None
                or self.allowed_duty_max is not None
            ):
                raise ConfigError(
                    "duty bounds are only meaningful when allow_pwm_duty "
                    "is true"
                )
