"""ColdGuard control policy core (Member D, W01-W03).

The package is a pure decision layer:

```text
PolicyInput  -> PolicyDecision
CommandRequest + LocalSafetyEvidence -> CommandDecision
failure id   -> FailureRule
```

It imports no MQTT client, database driver, GPIO library, web framework or
hardware module, owns no clock, and never actuates. Operating numbers
(thresholds, freshness, persistence, safe-local stability) are supplied by the
caller through ``PolicyConfig``; the package ships no physical defaults.

Canonical sources: Docs 00-02 for correctness, Doc 04 for ownership, Doc 05D
for Member D scope. W04+ owns command transport/actuation and W07+ owns the
real controller; nothing here is a controller implementation.
"""

from .commands import (
    SUPPORTED_SCHEMA_VERSION,
    CommandDecision,
    CommandRequest,
    CommandSchemaError,
    LocalSafetyEvidence,
    validate_command,
)
from .config import ConfigError, PolicyConfig
from .controller_a import (
    ControllerA, ControllerAConfig, ControllerADecision,
    ControllerASample, replay_controller_a,
)
from .device_safety import (
    ActuatorSafetyDecision,
    ActuatorSafetyFinding,
    ActuatorSafetyState,
    DeviceSafetyInputError,
    check_actuator_safety,
)
from .faults import (
    FORBIDDEN_TECHNIQUE_IDS, FaultProtocol, FaultProtocolStatus,
    InjectionCheckResult, InjectionVerdict, assert_protocol_allowed,
    audit_protocols, check_injection, get_protocol,
)
from .incident import (
    CANDIDATE_MAP_VERSION, IncidentRecommendation, recommend_incident_actions,
)
from .policy import (
    PolicyDecision,
    PolicyInput,
    PolicyInputError,
    PolicyPreconditionError,
    PredictionView,
    RemotePathView,
    ThermalView,
    evaluate_policy,
    safe_local_exit_status,
)
from .quality import (
    ChannelObservation,
    QualityAssessment,
    QualityBlocker,
    QualityInputError,
    assess_quality,
)
from .safe_local import SafeLocalSession, SafeLocalStep
from .taxonomy import (
    FailureRule,
    UnknownFailureError,
    all_failure_rules,
    classify_failure,
    failures_with_disposition,
)
from .types import (
    AckStatus,
    ActuationIntent,
    ControllerId,
    CoolingState,
    CoolingHealthState,
    IncidentAction,
    DeviceMode,
    EnvelopeQualification,
    FailureDisposition,
    ModelHealth,
    PhysicalVerificationState,
    PolicyState,
    QualityState,
    ReasonCode,
    VerificationStatus,
)
from .verification import (
    VerificationObservation, VerificationPolicy, VerificationSnapshot,
    VerificationTracker, start_verification,
)

__version__ = "0.1.0"

__all__ = [
    "SUPPORTED_SCHEMA_VERSION",
    "AckStatus",
    "ActuationIntent",
    "ActuatorSafetyDecision",
    "ActuatorSafetyFinding",
    "ActuatorSafetyState",
    "ChannelObservation",
    "CommandDecision",
    "CommandRequest",
    "CommandSchemaError",
    "ConfigError",
    "ControllerA",
    "ControllerAConfig",
    "ControllerADecision",
    "ControllerASample",
    "ControllerId",
    "CoolingState",
    "CoolingHealthState",
    "CANDIDATE_MAP_VERSION",
    "DeviceMode",
    "EnvelopeQualification",
    "DeviceSafetyInputError",
    "FailureDisposition",
    "FailureRule",
    "FaultProtocol",
    "FaultProtocolStatus",
    "FORBIDDEN_TECHNIQUE_IDS",
    "LocalSafetyEvidence",
    "InjectionCheckResult",
    "InjectionVerdict",
    "IncidentAction",
    "IncidentRecommendation",
    "ModelHealth",
    "PhysicalVerificationState",
    "PolicyConfig",
    "PolicyDecision",
    "PolicyInput",
    "PolicyInputError",
    "PolicyPreconditionError",
    "PolicyState",
    "PredictionView",
    "QualityAssessment",
    "QualityBlocker",
    "QualityInputError",
    "QualityState",
    "ReasonCode",
    "VerificationStatus",
    "SafeLocalSession",
    "SafeLocalStep",
    "RemotePathView",
    "ThermalView",
    "UnknownFailureError",
    "all_failure_rules",
    "assert_protocol_allowed",
    "audit_protocols",
    "assess_quality",
    "check_actuator_safety",
    "check_injection",
    "classify_failure",
    "evaluate_policy",
    "failures_with_disposition",
    "get_protocol",
    "safe_local_exit_status",
    "replay_controller_a",
    "recommend_incident_actions",
    "validate_command",
    "VerificationObservation",
    "VerificationPolicy",
    "VerificationSnapshot",
    "VerificationTracker",
    "start_verification",
]
