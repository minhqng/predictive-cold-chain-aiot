"""ColdGuard ML package (Member B).

The W01 contracts (``ml/data-dictionary-v0.md``, ``ml/leakage-risk-register.md``,
``ml/artifact-convention.md``, ``ml/claim-data-matrix.md``) define what is
legal; W02 makes the data-side rules executable:

* ``observations`` — canonical sample identity, event-time semantics,
  QoS-1 dedup and boot-scoped ordering;
* ``synthetic`` — deterministic synthetic fixture runs (B-W02-01);
* ``splitting`` — grouped run-level splitting (B-W02-02);
* ``windows`` — causal run-bounded windows (B-W02-03);
* ``labels`` — horizon labels ``y_t(H)`` with explicit statuses (B-W02-04);
* ``manifests`` — manifest parsing and cross-bindings (B-W02-05).

No model fitting, feature registry, or evaluation logic exists yet.
"""

from .errors import (
    ColdguardError,
    DataContractError,
    IdentityContradictionError,
    LabelError,
    ManifestError,
    OrderContradictionError,
    SplitError,
    WindowError,
)
from .labels import (
    CriticalEvent,
    CriticalEventSeries,
    LabelRecord,
    LabelSpec,
    LabelStatus,
    generate_label_records,
    labels_and_windows,
)
from .manifests import (
    DatasetManifest,
    ExcludedRunEntry,
    RunRecordManifest,
    SplitManifest,
    bind_dataset_to_run_records,
    bind_split_to_dataset,
    bind_split_to_run_records,
    canonical_manifest_yaml,
    manifest_content_sha256,
    parse_dataset_manifest,
    parse_run_manifest,
    parse_run_manifests,
    parse_split_manifest,
)
from .observations import (
    Observation,
    SampleIdentity,
    TIMEZONE_UTC,
    TrajectoryKey,
    canonical_order,
    deduplicate_by_identity,
    event_time_to_rfc3339,
    parse_event_time,
    rows_by_run,
    trajectory_end,
    validate_observation,
    validate_rows,
)
from .splitting import (
    ExcludedRun,
    RunInfo,
    SplitConfig,
    SplitProportions,
    SplitResult,
    split_runs,
)
from .synthetic import (
    DEFAULT_SYNTHETIC_START,
    SCENARIO_NAME_BY_ID,
    SYNTHETIC_NOTE,
    SyntheticRun,
    SyntheticRunSpec,
    TrajectoryShape,
    build_synthetic_dataset,
    build_synthetic_run,
    build_synthetic_runs,
)
from .windows import (
    AbsentCounts,
    QualityCounts,
    Window,
    WindowConfig,
    generate_windows,
    window_anchors,
)

__version__ = "0.1.0"

__all__ = [
    # package identity
    "__version__",
    # errors
    "ColdguardError",
    "DataContractError",
    "IdentityContradictionError",
    "OrderContradictionError",
    "ManifestError",
    "SplitError",
    "WindowError",
    "LabelError",
    # observations
    "Observation",
    "SampleIdentity",
    "TrajectoryKey",
    "TIMEZONE_UTC",
    "parse_event_time",
    "event_time_to_rfc3339",
    "validate_observation",
    "validate_rows",
    "deduplicate_by_identity",
    "canonical_order",
    "rows_by_run",
    "trajectory_end",
    # synthetic (B-W02-01)
    "TrajectoryShape",
    "SyntheticRunSpec",
    "SyntheticRun",
    "SCENARIO_NAME_BY_ID",
    "SYNTHETIC_NOTE",
    "DEFAULT_SYNTHETIC_START",
    "build_synthetic_run",
    "build_synthetic_runs",
    "build_synthetic_dataset",
    # splitting (B-W02-02)
    "RunInfo",
    "SplitProportions",
    "SplitConfig",
    "ExcludedRun",
    "SplitResult",
    "split_runs",
    # windows (B-W02-03)
    "WindowConfig",
    "Window",
    "QualityCounts",
    "AbsentCounts",
    "window_anchors",
    "generate_windows",
    # labels (B-W02-04)
    "CriticalEvent",
    "CriticalEventSeries",
    "LabelSpec",
    "LabelStatus",
    "LabelRecord",
    "generate_label_records",
    "labels_and_windows",
    # manifests (B-W02-05)
    "DatasetManifest",
    "SplitManifest",
    "RunRecordManifest",
    "ExcludedRunEntry",
    "parse_dataset_manifest",
    "parse_split_manifest",
    "parse_run_manifest",
    "parse_run_manifests",
    "bind_split_to_dataset",
    "bind_dataset_to_run_records",
    "bind_split_to_run_records",
    "canonical_manifest_yaml",
    "manifest_content_sha256",
]
