"""Frozen vocabulary for the ColdGuard policy core (Member D, W01-W03).

Every name and meaning here is traceable to the canonical documents:

- quality states          -> Doc 01 section 19 (VALID/DEGRADED/INVALID/UNKNOWN)
- cooling action family   -> Doc 01 sections 24.1-24.4, Doc 02 section 110
- device modes            -> Doc 02 section 2.1
- policy states           -> Doc 02 section 23 (plus 05D section 3/34)
- model health            -> Doc 02 section 19.8
- ACK statuses            -> Doc 02 section 32.1
- reason codes            -> Doc 02 sections 58/59 and 05D section 28
- failure dispositions    -> 05D section 35 D-W03-03 (Doc 01 section 28 ids)

This module deliberately contains no operating thresholds. Every numeric
operating value is supplied by a versioned ``PolicyConfig`` owned by Member D
and only frozen after physical characterization; Docs 01 section 39.3 and
Doc 02 section 24.4 forbid hidden magic constants.
"""

from __future__ import annotations

from enum import Enum


class QualityState(str, Enum):
    """Physical data-quality vocabulary (Doc 01 section 19).

    ``UNKNOWN`` must never be silently treated as healthy or as ``VALID``
    (Doc 01 section 19.4, Doc 02 SW-SAFE-010).
    """

    VALID = "VALID"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class CoolingState(str, Enum):
    """Legal P0 cooling action family (Doc 01 sections 24.1-24.4).

    ``PWM_DUTY`` is conditional and ``REVERSE`` is not legal in normal P0
    operation. Neither is part of the W03 skeleton action family; a duty is
    only accepted when the caller's configuration explicitly enables the
    characterized PWM range.
    """

    OFF = "OFF"
    ON = "ON"


class ActuationIntent(str, Enum):
    """What the pure policy asks a future command layer to consider.

    ``HOLD`` means "no new actuation request; keep the currently applied
    legal state". It is not an actuator command: W03 produces decisions only
    (Doc 02 sections 21-23; Doc 04 W03).
    """

    HOLD = "HOLD"
    OFF = "OFF"
    ON = "ON"


class DeviceMode(str, Enum):
    """Device-side modes (Doc 02 section 2.1)."""

    BOOT = "BOOT"
    SELF_TEST = "SELF_TEST"
    ONLINE_NORMAL = "ONLINE_NORMAL"
    ONLINE_DEGRADED = "ONLINE_DEGRADED"
    SAFE_LOCAL = "SAFE_LOCAL"
    FAULT_LOCKOUT = "FAULT_LOCKOUT"


class PolicyState(str, Enum):
    """Canonical high-level policy states (Doc 02 section 23, 05D section 3).

    ``FAULT_LOCKOUT`` is added by 05D section 3/34 as the state in which safe
    actuation cannot be guaranteed (Doc 02 section 2.7). Doc 02 section 3
    allows implementation to extend internal states while preserving the
    externally meaningful semantics.
    """

    NORMAL = "NORMAL"
    WATCH = "WATCH"
    PREEMPTIVE_COOLING = "PREEMPTIVE_COOLING"
    CRITICAL_PROTECTION = "CRITICAL_PROTECTION"
    FAULT = "FAULT"
    SAFE_LOCAL = "SAFE_LOCAL"
    FAULT_LOCKOUT = "FAULT_LOCKOUT"


class ControllerId(str, Enum):
    """Controller identity recorded with a decision (Doc 02 section 50.2)."""

    REACTIVE = "REACTIVE"
    PREDICTIVE = "PREDICTIVE"


class ModelHealth(str, Enum):
    """Runtime model status (Doc 02 section 19.8).

    Only ``READY`` may feed predictive action. An unavailable, invalid,
    mismatched or degraded model falls back to Controller A / local behavior;
    one old risk score is never reused indefinitely (Doc 02 sections 41, 94).
    """

    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"
    FEATURE_INVALID = "FEATURE_INVALID"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    DEGRADED = "DEGRADED"


class AckStatus(str, Enum):
    """Command acknowledgement status vocabulary (Doc 02 section 32.1).

    An ACK is protocol evidence only; it is not physical verification
    (Doc 02 section 32.2, SW-SAFE-008).
    """

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DUPLICATE_CANONICAL = "DUPLICATE_CANONICAL"
    EXPIRED = "EXPIRED"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    INVALID_STATE = "INVALID_STATE"
    OUT_OF_RANGE = "OUT_OF_RANGE"


class PhysicalVerificationState(str, Enum):
    """Independent physical-response verification state, separate from ACK.

    VERIFIED requires qualified physical evidence; an ACK alone is insufficient.
    """

    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    ELECTRICAL_VERIFIED = "ELECTRICAL_VERIFIED"
    THERMAL_VERIFIED = "THERMAL_VERIFIED"
    VERIFIED = "VERIFIED"
    FAILED_ELECTRICAL = "FAILED_ELECTRICAL"
    FAILED_THERMAL = "FAILED_THERMAL"
    UNKNOWN = "UNKNOWN"


VerificationState = PhysicalVerificationState


class CoolingHealthState(str, Enum):
    """Cooling-health derived states (Doc 01, Doc 02 section 36).

    The state classifies the observable response only. It never asserts a
    component-level root cause (05D section 15).
    """

    HEALTHY_RESPONSE = "HEALTHY_RESPONSE"
    ELECTRICAL_RESPONSE_MISSING = "ELECTRICAL_RESPONSE_MISSING"
    THERMAL_EFFECTIVENESS_DEGRADED = "THERMAL_EFFECTIVENESS_DEGRADED"
    CONTROL_ELECTRICAL_ANOMALY = "CONTROL_ELECTRICAL_ANOMALY"
    UNKNOWN = "UNKNOWN"


class EnvelopeQualification(str, Enum):
    """Provenance status of a verification envelope.

    ``QUALIFIED`` means the envelope is frozen from an approved characterization
    source. ``CANDIDATE_UNQUALIFIED`` means the numbers are observations that
    have not been accepted as evidence (for example Member A's W08/W09
    electrical status tokens are empty). ``UNRESOLVED`` means no envelope is
    available yet.
    """

    QUALIFIED = "QUALIFIED"
    CANDIDATE_UNQUALIFIED = "CANDIDATE_UNQUALIFIED"
    UNRESOLVED = "UNRESOLVED"



class FailureDisposition(str, Enum):
    """Allowed failure-handling dispositions for W03 (05D D-W03-03).

    Docs 00-02 never authorize silently ignoring a listed physical failure,
    so there is no ``IGNORE`` member. ``NOT_CONTRACTED`` marks a failure whose
    control disposition is not yet specified by an approved contract; it must
    be resolved by the named owner before being treated as a policy rule.
    """

    DEGRADE = "DEGRADE"
    FALLBACK = "FALLBACK"
    LOCKOUT = "LOCKOUT"
    NOT_CONTRACTED = "NOT_CONTRACTED"


class ReasonCode(str, Enum):
    """Control/audit reason-code baseline.

    Primary source: Doc 02 section 59. Command and physical-quality error
    names come from Doc 02 section 58; ``COMMAND_WRONG_DEVICE`` and
    ``AUTHORIZATION_FAILED`` are the 05D section 28 supplementary vocabulary.
    Doc 02 section 59's ``COMMAND_REJECTED_*`` names are retained as aliases
    where the same condition is represented.
    """

    # Doc 02 section 59
    THRESHOLD_HIGH = "THRESHOLD_HIGH"
    THRESHOLD_RECOVERED = "THRESHOLD_RECOVERED"
    PREDICTED_CRITICAL = "PREDICTED_CRITICAL"
    RISK_PERSISTENT = "RISK_PERSISTENT"
    DOOR_DISTURBANCE = "DOOR_DISTURBANCE"
    ELECTRICAL_RESPONSE_MISSING = "ELECTRICAL_RESPONSE_MISSING"
    THERMAL_EFFECTIVENESS_DEGRADED = "THERMAL_EFFECTIVENESS_DEGRADED"
    CONTROL_ELECTRICAL_ANOMALY = "CONTROL_ELECTRICAL_ANOMALY"
    SENSOR_DEGRADED = "SENSOR_DEGRADED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    COMMAND_REJECTED_STALE = "COMMAND_REJECTED_STALE"
    COMMAND_REJECTED_DUPLICATE = "COMMAND_REJECTED_DUPLICATE"
    COMMAND_REJECTED_RANGE = "COMMAND_REJECTED_RANGE"
    COMMAND_REJECTED_SAFETY = "COMMAND_REJECTED_SAFETY"
    RECOVERY_VERIFIED = "RECOVERY_VERIFIED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    SAFE_LOCAL_ENTER = "SAFE_LOCAL_ENTER"
    SAFE_LOCAL_EXIT = "SAFE_LOCAL_EXIT"

    # Doc 02 section 58 (protocol / physical-quality / command / AI)
    INVALID_JSON = "INVALID_JSON"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    DEVICE_ID_MISMATCH = "DEVICE_ID_MISMATCH"
    SENSOR_INVALID = "SENSOR_INVALID"
    PZEM_UNAVAILABLE = "PZEM_UNAVAILABLE"
    PZEM_CONFIG_INVALID = "PZEM_CONFIG_INVALID"
    THERMAL_STATE_INVALID = "THERMAL_STATE_INVALID"
    COMMAND_EXPIRED = "COMMAND_EXPIRED"
    COMMAND_DUPLICATE = "COMMAND_DUPLICATE"
    COMMAND_OUT_OF_RANGE = "COMMAND_OUT_OF_RANGE"
    COMMAND_SAFETY_BLOCKED = "COMMAND_SAFETY_BLOCKED"
    COMMAND_STATE_STALE = "COMMAND_STATE_STALE"
    COMMAND_UNAUTHORIZED = "COMMAND_UNAUTHORIZED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    FEATURE_INVALID = "FEATURE_INVALID"
    MODEL_VERSION_MISMATCH = "MODEL_VERSION_MISMATCH"
    BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
    DB_UNAVAILABLE = "DB_UNAVAILABLE"

    # 05D section 28 supplementary vocabulary
    COMMAND_WRONG_DEVICE = "COMMAND_WRONG_DEVICE"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"

    # Non-normative acknowledgement sentinel used by the Doc 02 section 64
    # ACK example ("reason_code": "OK"). It is not a decision reason.
    OK = "OK"
