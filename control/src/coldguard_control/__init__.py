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
    PolicyState,
    QualityState,
    ReasonCode,
)

__version__ = "0.1.0"

__all__ = [
    "SUPPORTED_SCHEMA_VERSION",
    "AckStatus",
    "ActuationIntent",
    "CommandDecision",
    "CommandRequest",
    "CommandSchemaError",
    "ConfigError",
    "ControllerId",
    "CoolingState",
    "DeviceMode",
    "FailureDisposition",
    "FailureRule",
    "LocalSafetyEvidence",
    "ModelHealth",
    "PolicyConfig",
    "PolicyDecision",
    "PolicyInput",
    "PolicyInputError",
    "PolicyPreconditionError",
    "PolicyState",
    "PredictionView",
    "QualityState",
    "ReasonCode",
    "RemotePathView",
    "ThermalView",
    "UnknownFailureError",
    "all_failure_rules",
    "classify_failure",
    "evaluate_policy",
    "failures_with_disposition",
    "safe_local_exit_status",
    "validate_command",
]
