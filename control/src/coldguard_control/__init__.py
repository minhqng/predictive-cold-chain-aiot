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
from .device_safety import (
    ActuatorSafetyDecision,
    ActuatorSafetyFinding,
    ActuatorSafetyState,
    DeviceSafetyInputError,
    check_actuator_safety,
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
    DeviceMode,
    FailureDisposition,
    ModelHealth,
    PhysicalVerificationState,
    PolicyState,
    QualityState,
    CoolingHealthState,
    ReasonCode,
    EnvelopeQualification,
)
# New modules
from .controller_a import (
    ControllerAConfig,
    ControllerASample,
    ControllerADecision,
    ControllerA,
    replay_controller_a,
)
from .safe_local import SafeLocalSession, SafeLocalStep
from .verification import (
    VerificationPolicy,
    VerificationObservation,
    VerificationSnapshot,
    VerificationTracker,
    start_verification,
)

__version__ = "0.1.0"

# W10‑W13 exported symbols
from .types import VerificationStatus, IncidentAction
from .faults import (
    FaultProtocol,
    InjectionCheckResult,
    InjectionVerdict,
    FaultProtocolStatus,
    FORBIDDEN_TECHNIQUE_IDS,
    get_protocol,
    check_injection,
    assert_protocol_allowed,
    audit_protocols,
)
from .incident import (
    CANDIDATE_MAP_VERSION,
    IncidentRecommendation,
    recommend_incident_actions,
)
from .aiw import AIWInput, AIWResult, AIWStatus, TimingEvidence, assess_aiw
from .verification_bridge import (
    A_LIFECYCLE_ORDER,
    AObservationalLifecycle,
    AtoDVerificationDecision,
    assess_a_lifecycle_for_d,
)

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
    "ControllerId",
    "CoolingState",
    "DeviceMode",
    "DeviceSafetyInputError",
    "FailureDisposition",
    "FailureRule",
    "LocalSafetyEvidence",
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
    "EnvelopeQualification",
    "CoolingHealthState",
    "RemotePathView",
    "ThermalView",
    "UnknownFailureError",
    "all_failure_rules",
    "assess_quality",
    "check_actuator_safety",
    "classify_failure",
    "evaluate_policy",
    "failures_with_disposition",
    "safe_local_exit_status",
    "validate_command",
    "ControllerAConfig",
    "ControllerASample",
    "ControllerADecision",
    "ControllerA",
    "replay_controller_a",
    "SafeLocalSession",
    "SafeLocalStep",
    "VerificationPolicy",
    "VerificationObservation",
    "VerificationSnapshot",
    "VerificationTracker",
    "start_verification",
    "VerificationStatus",
    "CoolingHealthState",
    "IncidentAction",
    "FaultProtocol",
    "InjectionCheckResult",
    "InjectionVerdict",
    "FaultProtocolStatus",
    "check_injection",
    "assert_protocol_allowed",
    "audit_protocols",
    "FORBIDDEN_TECHNIQUE_IDS",
    "get_protocol",
    "CANDIDATE_MAP_VERSION",
    "IncidentRecommendation",
    "recommend_incident_actions",
    "AIWInput",
    "AIWResult",
    "AIWStatus",
    "TimingEvidence",
    "assess_aiw",
    "A_LIFECYCLE_ORDER",
    "AObservationalLifecycle",
    "AtoDVerificationDecision",
    "assess_a_lifecycle_for_d",

]
