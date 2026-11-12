"""W16 locked-test pre-registration and fail-closed readiness gate (B-W16-01).

This module is a PREFLIGHT GATE, not a locked-test runner.  It consumes
immutable, structured prerequisite metadata and returns a deterministic
readiness decision.  It cannot open holdout observations, cannot compute a
predictive metric and cannot invoke any evaluator:

* the module imports only the Python standard library;
* its only file access is re-hashing artifacts explicitly declared with an
  allowed role (native/secondary model files) under an explicit root;
* paths that look like holdout payloads are refused before any read;
* there is no ``--force`` / ``--ignore-gates`` / ``--unlock`` path anywhere.

Canonical anchors (Doc ``03`` §44/§47/§49/§59/§87/§88/§92/§93/§137,
Doc ``04`` §31 Gate G4, Doc ``05B`` §44 B-W16-01…04):

* one primary horizon frozen before the final test;
* threshold and warning persistence selected on development data and frozen;
* model, feature version, artifact hash and calibration method frozen before
  opening the locked test;
* the locked test is evaluated exactly once, and a post-test revision makes
  the old test no longer untouched;
* a software-only control can never substitute for physical evidence.

Missing information is never equivalent to PASS.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "coldguard-w16-preregistration-v1"
EVIDENCE_SCHEMA = "coldguard-w16-evidence-v1"
REPORT_SCHEMA = "coldguard-w16-preflight-report-v1"
LAYER_VERSION = "coldguard-w16-locked-test-preregistration-v1"

MANIFEST_KIND = "PRE_REGISTRATION_ONLY"
HOLDOUT_ACCESS = "NOT_AUTHORIZED"
EVALUATION_STATUS = "NOT_RUN"

DECISION_REFUSED = "REFUSED_PREREQUISITES_UNMET"
DECISION_READY = "READY_FOR_AUTHORIZED_EVALUATION_PREFLIGHT_ONLY"

# Evidence statuses (same vocabulary as the W12 Gate G3 matrix).
PASS_VERIFIED = "PASS_VERIFIED"
FAIL_VERIFIED = "FAIL_VERIFIED"
BLOCKED_BY_MISSING_EVIDENCE = "BLOCKED_BY_MISSING_EVIDENCE"
NOT_VERIFIED = "NOT_VERIFIED"
NOT_APPLICABLE = "NOT_APPLICABLE"

# Freeze-field classifications required by the W16 packet.
FROZEN_APPROVED = "FROZEN_APPROVED"
DEVELOPMENT_CANDIDATE_ONLY = "DEVELOPMENT_CANDIDATE_ONLY"
UNFROZEN = "UNFROZEN"
MISSING_EVIDENCE = "MISSING_EVIDENCE"
FREEZE_STATUSES = (
    FROZEN_APPROVED,
    DEVELOPMENT_CANDIDATE_ONLY,
    UNFROZEN,
    MISSING_EVIDENCE,
)

# Evidence scopes keep a PASS on synthetic metadata from reading as a
# physical result.
SCOPE_PHYSICAL = "PHYSICAL"
SCOPE_DECLARED_METADATA_ONLY = "DECLARED_METADATA_ONLY"
SCOPE_ARTIFACT_HASH = "ARTIFACT_HASH"
SCOPE_PROCESS = "PROCESS"

PHYSICAL_EVIDENCE_CLASSES = frozenset(
    {"MEASURED_PHYSICAL_DATA", "REAL_PHYSICAL_EVIDENCE"}
)
SYNTHETIC_EVIDENCE_CLASSES = frozenset(
    {"SYNTHETIC_SOFTWARE_CONTROL_ONLY", "SYNTHETIC_FIXTURE"}
)
RELEASE_ELIGIBLE_CLASSES = frozenset(
    {"RELEASE_APPROVED_CANDIDATE", "APPROVED_RELEASE_CANDIDATE"}
)

HOLDOUT_HISTORY_KNOWN = "NO_RECORDED_OPENING"

ALLOWED_ARTIFACT_ROLES = frozenset({"model_native", "model_secondary"})
ALLOWED_ARTIFACT_SUFFIXES = frozenset({".ubj", ".json"})
FORBIDDEN_ARTIFACT_PATH_TOKENS = (
    "locked",
    "holdout",
    "observations",
    "test_features",
    "test_labels",
    "test_predictions",
    "prediction_output",
)
METRIC_FIELD_NAMES = (
    "ap",
    "average_precision",
    "precision",
    "recall",
    "auc",
    "roc_auc",
    "ewt",
    "aiw",
    "brier",
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class W16ReadinessError(ValueError):
    """The preflight input is structurally invalid and cannot be evaluated."""


@dataclass(frozen=True)
class FreezeFieldSpec:
    field_id: str
    description: str
    canonical_ref: str
    permitted_authorities: tuple[str, ...]


@dataclass(frozen=True)
class ApprovalSpec:
    approval_id: str
    role: str
    description: str
    canonical_ref: str


@dataclass(frozen=True)
class RequirementResult:
    requirement_id: str
    requirement: str
    canonical_ref: str
    status: str
    reason_code: str | None
    observed: str
    evidence_scope: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "requirement": self.requirement,
            "canonical_ref": self.canonical_ref,
            "status": self.status,
            "reason_code": self.reason_code,
            "observed": self.observed,
            "evidence_scope": self.evidence_scope,
        }


@dataclass(frozen=True)
class W16ReadinessReport:
    decision: str
    refusal_reasons: tuple[str, ...]
    requirements: tuple[RequirementResult, ...]
    manifest: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.manifest)


FREEZE_FIELD_SPECS: tuple[FreezeFieldSpec, ...] = (
    FreezeFieldSpec(
        "model_version",
        "Model artifact/version identity used by the future one-time test.",
        "03 §92",
        ("B",),
    ),
    FreezeFieldSpec(
        "native_model_sha256",
        "SHA-256 of the native model artifact bound to the future test.",
        "03 §92",
        ("B",),
    ),
    FreezeFieldSpec(
        "model_config_sha256",
        "Canonical SHA-256 of the model configuration (hyperparameters).",
        "03 §92",
        ("B",),
    ),
    FreezeFieldSpec(
        "feature_version",
        "Feature-registry version identity.",
        "03 §92; 05B §9",
        ("B",),
    ),
    FreezeFieldSpec(
        "ordered_feature_ids_sha256",
        "Hash of the ordered feature identities consumed by the model.",
        "03 §92; 02 §60.5",
        ("B",),
    ),
    FreezeFieldSpec(
        "training_dataset_identity",
        "Training dataset identity and immutable source hashes.",
        "03 §92; 05B §7",
        ("B", "A"),
    ),
    FreezeFieldSpec(
        "target_definition",
        "Critical-target label definition (boundary, representative temperature).",
        "03 §42-43, §92; 05B §54",
        ("D",),
    ),
    FreezeFieldSpec(
        "representative_temperature",
        "Representative temperature selection for the final label.",
        "03 §42-43",
        ("A",),
    ),
    FreezeFieldSpec(
        "primary_horizon",
        "Single primary prediction horizon H.",
        "03 §44, §84, §92",
        ("B", "TEAM_LEAD"),
    ),
    FreezeFieldSpec(
        "risk_score_calibration_semantics",
        "Output semantics: calibrated probability or risk score only.",
        "03 §58-60, §92",
        ("B",),
    ),
    FreezeFieldSpec(
        "operating_threshold",
        "Warning operating threshold selected on development data.",
        "03 §87, §92",
        ("D",),
    ),
    FreezeFieldSpec(
        "warning_persistence",
        "Warning persistence rule k (consecutive seconds/samples).",
        "03 §88, §92",
        ("D",),
    ),
    FreezeFieldSpec(
        "event_matching_policy",
        "Warning-episode and event-association policy.",
        "03 §89-90",
        ("B",),
    ),
    FreezeFieldSpec(
        "missingness_policy",
        "Missing-data policy used by the frozen feature schema.",
        "03 §125; registry policy",
        ("B",),
    ),
    FreezeFieldSpec(
        "analysis_code_version",
        "Analysis/preflight code identity executed for the future test.",
        "03 §92, §133, §158",
        ("B",),
    ),
    FreezeFieldSpec(
        "physical_dataset_identity",
        "Authoritative physical dataset identity with immutable source hashes.",
        "01 §17; 03 §137 Gate B",
        ("A",),
    ),
    FreezeFieldSpec(
        "hardware_configuration",
        "Verified hardware configuration / lineage for the physical population.",
        "01 §39.1; 03 §137 Gate B",
        ("A",),
    ),
    FreezeFieldSpec(
        "telemetry_time_provenance",
        "Trusted event-time and clock-synchronization provenance.",
        "01 §18; 03 §137 Gate B",
        ("C",),
    ),
    FreezeFieldSpec(
        "run_identity_and_pairing",
        "Resolved physical run identity and pair/group lineage.",
        "03 §47; 05B §7-8",
        ("A", "C"),
    ),
    FreezeFieldSpec(
        "calibration_provenance",
        "Physical calibration provenance for measurement traceability.",
        "01 §39.2; 03 §137 Gate B",
        ("A",),
    ),
)

APPROVAL_SPECS: tuple[ApprovalSpec, ...] = (
    ApprovalSpec(
        "approval.methodological_freeze",
        "B_METHOD",
        "Member B methodological freeze: features, model, horizon, metrics, analysis code.",
        "05B §44; 03 §92",
    ),
    ApprovalSpec(
        "approval.physical_measurement",
        "A_PHYSICAL",
        "Member A authorization of physical measurement validity and provenance.",
        "01 §17-18; 05B §44",
    ),
    ApprovalSpec(
        "approval.critical_threshold",
        "D_POLICY",
        "Member D authorization of critical target, threshold and persistence policy.",
        "03 §42, §87-88; 05B §54",
    ),
    ApprovalSpec(
        "approval.time_provenance",
        "C_TELEMETRY",
        "Member C support of telemetry time-domain and clock provenance.",
        "01 §18; 05B §54",
    ),
    ApprovalSpec(
        "approval.release_authorization",
        "TEAM_LEAD",
        "Team-lead release authorization for the one-time locked evaluation.",
        "03 §92-93; 04 §31",
    ),
)

# Pre-declared statistical analysis registration.  These are definitions only;
# no value will exist until an authorized one-time evaluation produces them.
ANALYSIS_REGISTRATION: Mapping[str, Any] = {
    "primary_metric": {
        "name": "non_interpolated_average_precision",
        "canonical_constant": "PRIMARY_PREDICTIVE_METRIC (evaluation_contract)",
        "definition": (
            "Average precision from the precision/recall curve of risk scores "
            "against the frozen binary label, with no interpolation."
        ),
        "unit": "dimensionless, range [0, 1]",
        "population": (
            "eligible trusted locked-test anchors from frozen independent test "
            "runs, partitioned exactly as registered"
        ),
        "denominator": (
            "all eligible positive and negative anchors; AP averages precision "
            "at each positive rank"
        ),
        "implementation": (
            "coldguard_ml.grouped_evaluation.classification_metrics "
            "(average_precision_score); no second metric engine"
        ),
        "undefined_cases": [
            "single-class locked-test population",
            "zero eligible anchors",
            "frozen label unavailable for any test run",
        ],
        "undefined_behavior": (
            "report UNDEFINED_SINGLE_CLASS_TEST / UNDEFINED_NO_ELIGIBLE_ANCHORS; "
            "never report 0 or 1 for an uncomputable metric"
        ),
    },
    "supporting_metrics": {
        "precision": {
            "definition": "tp / (tp + fp) at the frozen operating threshold and persistence rule",
            "unit": "dimensionless",
            "denominator": "predicted positive anchors",
            "undefined_cases": ["no predicted positives"],
            "undefined_behavior": "NO_PREDICTED_POSITIVES; never report 0",
        },
        "recall": {
            "definition": "tp / positive anchors at the frozen operating threshold and persistence rule",
            "unit": "dimensionless",
            "denominator": "eligible positive anchors",
            "undefined_cases": ["zero positive anchors"],
            "undefined_behavior": "UNDEFINED_NO_POSITIVES; never report 0",
        },
    },
    "event_metrics": {
        "warning_episode_definition": (
            "contiguous samples above the frozen operating threshold for at least "
            "the frozen persistence rule k; bridging follows the frozen event "
            "matching policy only"
        ),
        "false_warning_burden": {
            "metric": "false_warning_episodes_per_eligible_hour",
            "denominator": "trusted eligible run-hours in the locked test",
        },
        "missed_events": {
            "metric": "missed_critical_event_count",
            "denominator": "eligible critical events in the locked test",
        },
        "implementation": "coldguard_ml.event_evaluator.evaluate_events",
    },
    "ewt": {
        "name": "EWT",
        "definition": "t_reactive - t_predictive in seconds (negative kept, never clamped)",
        "preconditions": [
            "qualified common trajectory",
            "trusted event time",
            "no intervening predictive intervention",
            "uncensored reactive crossing",
            "frozen reactive criterion",
        ],
        "undefined_behavior": "NOT_ESTIMABLE with the exact missing precondition; never zero",
        "implementation": "coldguard_ml.evaluation_contract.compute_ewt",
    },
    "aiw": {
        "name": "AIW",
        "definition": (
            "t_critical - t_warning - T_system - T_physical in seconds; T_system is "
            "sensing + inference + policy + command overhead"
        ),
        "preconditions": [
            "measured command-to-effect latency chain",
            "frozen critical criterion",
            "trusted warning time",
        ],
        "undefined_behavior": "NOT_ESTIMABLE with the exact missing precondition; never zero",
        "implementation": "coldguard_ml.evaluation_contract.compute_aiw",
    },
    "calibration": {
        "applicability": (
            "only when the frozen output semantics are a calibrated probability; "
            "with risk_score semantics calibration metrics are NOT_APPLICABLE and "
            "no probability wording is permitted"
        ),
        "fit_population": "development data only; never the locked test",
        "implementation": "coldguard_ml.w14_calibration (development-only diagnostics)",
    },
    "aggregation": {
        "independent_unit": "run_id (pair_id lineage collapses paired runs into one group)",
        "reporting": (
            "per independent test run/group and pooled across groups; correlated "
            "windows and correlated folds are never counted as independent experiments"
        ),
    },
    "invalid_and_censored_data": {
        "rule": (
            "exclude only per predeclared validity rules; report exclusion counts and "
            "run/group denominators; never impute, never zero-fill missingness"
        ),
        "implementation": "coldguard_ml.grouped_evaluation + registry missingness policy",
    },
    "interpretation_categories": [
        "SUPPORTS_PREDICTIVE_USEFULNESS",
        "MIXED_EVIDENCE",
        "DOES_NOT_SUPPORT",
    ],
    "not_run_interpretation": "NO_INTERPRETATION_TEST_NOT_RUN",
    "uncertainty_reporting": [
        "independent run/group counts",
        "class and event denominators",
        "excluded/censored counts with reasons",
        "explicit non-estimable statuses for every undefined metric",
        "limitations section stating the tested prototype/configuration only",
    ],
}


def _ordered_feature_ids_sha256(feature_ids: Sequence[str]) -> str:
    # Matches the existing W15 artifact recipe: hash of json.dumps(list(ids))
    # with default separators.
    return hashlib.sha256(json.dumps(list(feature_ids)).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise W16ReadinessError(f"evidence section '{name}' must be a mapping")
    return value


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))


def _requirement(
    requirement_id: str,
    requirement: str,
    canonical_ref: str,
    status: str,
    reason_code: str | None,
    observed: str,
    evidence_scope: str,
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement_id,
        requirement=requirement,
        canonical_ref=canonical_ref,
        status=status,
        reason_code=reason_code,
        observed=observed,
        evidence_scope=evidence_scope,
    )


def _artifact_path_forbidden(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    normalized = lowered.replace("-", "_")
    if not any(
        lowered.endswith(suffix) for suffix in ALLOWED_ARTIFACT_SUFFIXES
    ):
        return True
    return any(token in normalized for token in FORBIDDEN_ARTIFACT_PATH_TOKENS)


def _verify_declared_artifacts(
    evidence: Mapping[str, Any], artifact_root: str | Path | None
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Re-hash only explicitly declared model artifacts.

    Returns (records, problems, observed_notes).  A problem is a deterministic
    reason fragment; any problem fails closed.
    """
    records: list[dict[str, Any]] = []
    problems: list[str] = []
    notes: list[str] = []
    raw = evidence.get("artifacts")
    if not isinstance(raw, list) or not raw:
        return records, ["ARTIFACT_DECLARATIONS_MISSING"], [
            "no declared artifact files to hash"
        ]
    root = None if artifact_root is None else Path(artifact_root)
    for item in raw:
        if not isinstance(item, Mapping):
            problems.append("ARTIFACT_DECLARATION_INVALID")
            continue
        role = _text(item.get("role"))
        relative = _text(item.get("path")).replace("\\", "/")
        declared = _text(item.get("declared_sha256"))
        record: dict[str, Any] = {
            "role": role,
            "path": relative,
            "declared_sha256": declared,
            "recomputed_sha256": None,
            "matches": False,
        }
        if role not in ALLOWED_ARTIFACT_ROLES:
            problems.append("ARTIFACT_ROLE_NOT_ALLOWED")
            record["refusal"] = "ARTIFACT_ROLE_NOT_ALLOWED"
            records.append(record)
            continue
        if _artifact_path_forbidden(relative) or relative.startswith("/") or ".." in relative.split("/"):
            problems.append("ARTIFACT_PATH_FORBIDDEN")
            record["refusal"] = "ARTIFACT_PATH_FORBIDDEN"
            records.append(record)
            continue
        if root is None:
            problems.append("ARTIFACT_ROOT_MISSING")
            record["refusal"] = "ARTIFACT_ROOT_MISSING"
            records.append(record)
            continue
        file_path = root / relative
        root_resolved = root.resolve()
        file_resolved = file_path.resolve()
        if root_resolved != file_resolved and root_resolved not in file_resolved.parents:
            problems.append("ARTIFACT_PATH_FORBIDDEN")
            record["refusal"] = "ARTIFACT_PATH_FORBIDDEN"
            records.append(record)
            continue
        if not file_path.is_file():
            problems.append("ARTIFACT_FILE_MISSING")
            record["refusal"] = "ARTIFACT_FILE_MISSING"
            records.append(record)
            continue
        recomputed = _sha256_file(file_path)
        record["recomputed_sha256"] = recomputed
        record["matches"] = recomputed == declared
        if not record["matches"]:
            problems.append("ARTIFACT_HASH_MISMATCH")
        notes.append(f"{relative} -> {recomputed[:16]}...")
        records.append(record)
    return records, sorted(set(problems)), notes


def _run_partition_map(
    train_runs: list[str], validation_runs: list[str], test_runs: list[str]
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    duplicates: set[str] = set()
    for partition, runs in (
        ("train", train_runs),
        ("validation", validation_runs),
        ("test", test_runs),
    ):
        for run_id in runs:
            if run_id in mapping:
                duplicates.add(run_id)
            mapping[run_id] = partition
    if duplicates:
        mapping["__duplicates__"] = ",".join(sorted(duplicates))
    return mapping


def _audit_pair_lineage(
    pair_lineage: list[Any],
    run_partitions: Mapping[str, str],
) -> dict[str, Any]:
    problems: list[str] = []
    pair_partitions: dict[str, set[str]] = {}
    run_owner: dict[str, str] = {}
    duplicates = set(
        filter(None, _text(run_partitions.get("__duplicates__")).split(","))
    )
    if duplicates:
        problems.append("RUN_PARTITION_AMBIGUOUS")
    for entry in pair_lineage:
        if not isinstance(entry, Mapping):
            problems.append("PAIR_LINEAGE_INVALID")
            continue
        pair_id = _text(entry.get("pair_id"))
        partition = _text(entry.get("partition"))
        raw_runs = entry.get("run_ids")
        if (
            not isinstance(raw_runs, (list, tuple))
            or not raw_runs
            or any(not isinstance(run, str) or not run for run in raw_runs)
        ):
            problems.append("PAIR_LINEAGE_INVALID")
            continue
        runs = list(raw_runs)
        if not pair_id or partition not in {"train", "validation", "test"}:
            problems.append("PAIR_LINEAGE_INVALID")
            continue
        pair_partitions.setdefault(pair_id, set()).add(partition)
        for run_id in runs:
            if run_id in run_owner and run_owner[run_id] != pair_id:
                problems.append("PAIR_LINEAGE_INVALID")
            run_owner[run_id] = pair_id
            observed_partition = run_partitions.get(run_id)
            if observed_partition is None or observed_partition != partition:
                problems.append("PAIR_PARTITION_RUN_MISMATCH")
    straddling = sorted(
        pair_id for pair_id, parts in pair_partitions.items() if len(parts) > 1
    )
    if straddling:
        problems.append("PAIR_LINEAGE_CROSSES_PARTITIONS")
    observed_test_pairs = sorted(
        pair_id for pair_id, parts in pair_partitions.items() if "test" in parts
    )
    return {
        "problems": problems,
        "straddling": straddling,
        "pair_count": len(pair_partitions),
        "run_owner": run_owner,
        "observed_test_pairs": observed_test_pairs,
    }


def _custom_metric_payload_present(evidence: Mapping[str, Any]) -> bool:
    for key in ("metric_values", "test_metrics", "holdout_metrics", "results"):
        value = evidence.get(key)
        if isinstance(value, Mapping) and value:
            return True
        if isinstance(value, list) and value:
            return True
    for key in METRIC_FIELD_NAMES:
        if evidence.get(key) is not None:
            return True
    return False


def _freeze_ledger(
    evidence: Mapping[str, Any], inputs: Mapping[str, Any]
) -> list[dict[str, Any]]:
    model = _mapping(evidence.get("model", {}), "model")
    config = _mapping(evidence.get("config", {}), "config")
    registry = _mapping(evidence.get("registry", {}), "registry")
    dataset = _mapping(evidence.get("dataset", {}), "dataset")
    horizon = _mapping(evidence.get("horizon_decision", {}), "horizon_decision")
    registration = _mapping(evidence.get("registration", {}), "registration")

    def sha_of(path: str) -> str | None:
        if not isinstance(inputs, Mapping):
            return None
        entry = inputs.get(path)
        if isinstance(entry, Mapping):
            return entry.get("sha256")
        if isinstance(entry, str):
            return entry
        return None

    model_manifest_path = _text(
        _mapping(evidence.get("source_paths") or {}, "source_paths").get("model_manifest")
    )
    config_path = _text(
        _mapping(evidence.get("source_paths") or {}, "source_paths").get("model_config")
    )
    registry_path = _text(
        _mapping(evidence.get("source_paths") or {}, "source_paths").get("feature_registry")
    )

    physical = _text(dataset.get("evidence_class")) in PHYSICAL_EVIDENCE_CLASSES
    releasable = _text(model.get("release_eligibility")) in RELEASE_ELIGIBLE_CLASSES
    model_status = (
        FROZEN_APPROVED if physical and releasable else DEVELOPMENT_CANDIDATE_ONLY
    )
    dataset_status = FROZEN_APPROVED if physical else DEVELOPMENT_CANDIDATE_ONLY
    registry_status = (
        FROZEN_APPROVED
        if registry.get("registry_status") == "FROZEN_DEFINITIONS"
        else MISSING_EVIDENCE
    )
    target_status = (
        FROZEN_APPROVED if config.get("target_status") == "FROZEN" else UNFROZEN
    )
    representative_status = (
        FROZEN_APPROVED
        if config.get("representative_temperature_status") == "FROZEN"
        else UNFROZEN
    )
    horizon_status = (
        FROZEN_APPROVED if horizon.get("freeze_status") == "FROZEN" else UNFROZEN
    )
    calibration_semantics_status = (
        FROZEN_APPROVED
        if _text(model.get("calibration_status"))
        in {"RISK_SCORE_ONLY", "CALIBRATED"}
        else DEVELOPMENT_CANDIDATE_ONLY
    )
    threshold_status = (
        FROZEN_APPROVED
        if model.get("operating_threshold_status") == "FROZEN"
        else UNFROZEN
    )
    persistence_status = (
        FROZEN_APPROVED
        if model.get("warning_persistence_status") == "FROZEN"
        else UNFROZEN
    )
    matching_status = (
        FROZEN_APPROVED
        if (
            config.get("episode_policy_status") == "FROZEN"
            and config.get("association_policy_status") == "FROZEN"
        )
        else DEVELOPMENT_CANDIDATE_ONLY
    )
    physical_dataset_status = (
        FROZEN_APPROVED
        if dataset.get("physical_dataset_id") and dataset.get("source_sha256")
        else MISSING_EVIDENCE
    )
    hardware_status = (
        FROZEN_APPROVED
        if dataset.get("hardware_config_status") == "VERIFIED"
        else MISSING_EVIDENCE
    )
    time_status = (
        FROZEN_APPROVED
        if (
            _text(dataset.get("time_domain"))
            not in {"", "BOOT_SCOPED_UPTIME", "UNKNOWN"}
            and _text(dataset.get("clock_sync")) == "EVIDENCED"
        )
        else MISSING_EVIDENCE
    )
    run_identity_status = (
        FROZEN_APPROVED
        if _text(dataset.get("run_identity_status")) in {"RESOLVED", "VALIDATED"}
        else MISSING_EVIDENCE
    )
    calibration_provenance_status = (
        FROZEN_APPROVED
        if _text(dataset.get("calibration_status"))
        not in {"", "NOT_AVAILABLE", "UNVERIFIED"}
        else MISSING_EVIDENCE
    )

    rows: list[dict[str, Any]] = []

    def row(
        field_id: str,
        value: Any,
        status: str,
        authority: str,
        source: str,
        canonical_ref: str,
        blocking_effect: str,
    ) -> None:
        if status not in FREEZE_STATUSES:
            raise W16ReadinessError(f"unknown freeze status for {field_id}")
        rows.append(
            {
                "field_id": field_id,
                "value": value,
                "status": status,
                "authority": authority,
                "authority_evidence": (
                    f"{source} @ {sha_of(source)}" if sha_of(source) else source or None
                ),
                "source": source or None,
                "source_sha256": sha_of(source),
                "canonical_ref": canonical_ref,
                "blocking_effect": blocking_effect,
            }
        )

    row(
        "model_version",
        model.get("artifact_id"),
        model_status,
        "B",
        model_manifest_path,
        "03 §92",
        "a model that is not release-approved cannot be used for the final test",
    )
    row(
        "native_model_sha256",
        model.get("model_artifact_sha256"),
        model_status,
        "B",
        model_manifest_path,
        "03 §92",
        "artifact hash is registered but its candidate is non-deployable",
    )
    row(
        "model_config_sha256",
        model.get("model_config_hash"),
        model_status,
        "B",
        model_manifest_path,
        "03 §92",
        "configuration is a development candidate, not a frozen release config",
    )
    row(
        "feature_version",
        registry.get("feature_version"),
        registry_status,
        "B",
        registry_path,
        "03 §92; 05B §9",
        "feature definitions must stay frozen once referenced",
    )
    row(
        "ordered_feature_ids_sha256",
        model.get("ordered_feature_ids_sha256"),
        registry_status,
        "B",
        model_manifest_path,
        "03 §92",
        "ordered feature identities must stay frozen once referenced",
    )
    row(
        "training_dataset_identity",
        model.get("training_dataset_id"),
        dataset_status,
        "B",
        model_manifest_path,
        "03 §92; 05B §7",
        "training dataset is synthetic; no physical training identity exists",
    )
    row(
        "target_definition",
        {
            "target_spec_version": config.get("target_spec_version")
            or model.get("target_spec_version"),
            "target_status": config.get("target_status")
            or model.get("target_status"),
            "boundary_c": config.get("target_boundary_c"),
        },
        target_status,
        "D",
        config_path,
        "03 §42-43, §92",
        "critical-target definition must be frozen by its policy owner",
    )
    row(
        "representative_temperature",
        config.get("representative_temperature_status"),
        representative_status,
        "A",
        config_path,
        "03 §42-43",
        "representative temperature is a physical measurement decision",
    )
    row(
        "primary_horizon",
        {
            "horizon_s": model.get("horizon_s"),
            "horizon_status": model.get("horizon_status"),
            "decision_freeze_status": horizon.get("freeze_status"),
            "decision_primary_horizon_s": horizon.get("primary_horizon_s"),
        },
        horizon_status,
        "B",
        _text(
            _mapping(evidence.get("source_paths") or {}, "source_paths").get(
                "horizon_manifest"
            )
        ),
        "03 §44, §84, §92",
        "no final test may run without one frozen primary horizon",
    )
    row(
        "risk_score_calibration_semantics",
        {
            "score_semantics": model.get("score_semantics"),
            "calibration_status": model.get("calibration_status"),
        },
        calibration_semantics_status,
        "B",
        model_manifest_path,
        "03 §58-60, §92",
        "score-only semantics are legal but must be confirmed by the release authority",
    )
    row(
        "operating_threshold",
        {
            "value": model.get("operating_threshold"),
            "status": model.get("operating_threshold_status"),
            "source": model.get("operating_threshold_source"),
        },
        threshold_status,
        "D",
        model_manifest_path,
        "03 §87, §92",
        "an illustrative threshold can never become the final operating threshold",
    )
    row(
        "warning_persistence",
        {
            "status": model.get("warning_persistence_status"),
            "k": model.get("warning_persistence_k"),
        },
        persistence_status,
        "D",
        model_manifest_path,
        "03 §88, §92",
        "persistence k must be frozen before the final test",
    )
    row(
        "event_matching_policy",
        {
            "episode_policy_status": config.get("episode_policy_status"),
            "association_policy_status": config.get("association_policy_status"),
        },
        matching_status,
        "B",
        config_path,
        "03 §89-90",
        "episode/association policy is a synthetic illustrative policy",
    )
    row(
        "missingness_policy",
        registry.get("missingness_policy"),
        registry_status,
        "B",
        registry_path,
        "03 §125",
        "explicit-missing policy is part of the frozen feature schema",
    )
    row(
        "analysis_code_version",
        registration.get("analysis_code_sha256"),
        (
            FROZEN_APPROVED
            if _is_hex64(registration.get("analysis_code_sha256"))
            else MISSING_EVIDENCE
        ),
        "B",
        "ml/scripts/w16-preflight-W16.py",
        "03 §92, §133, §158",
        "analysis code identity is frozen by this pre-registration",
    )
    row(
        "physical_dataset_identity",
        dataset.get("physical_dataset_id"),
        physical_dataset_status,
        "A",
        "reports/W08/gate-b-manifest-W08.json",
        "01 §17; 03 §137 Gate B",
        "no authoritative physical dataset exists",
    )
    row(
        "hardware_configuration",
        {
            "hardware_config_id": dataset.get("hardware_config_id"),
            "status": dataset.get("hardware_config_status"),
        },
        hardware_status,
        "A",
        "reports/W08/gate-b-manifest-W08.json",
        "01 §39.1; 03 §137 Gate B",
        "declared hardware is not verified hardware",
    )
    row(
        "telemetry_time_provenance",
        {
            "time_domain": dataset.get("time_domain"),
            "clock_sync": dataset.get("clock_sync"),
        },
        time_status,
        "C",
        "reports/W08/gate-b-manifest-W08.json",
        "01 §18; 03 §137 Gate B",
        "boot-scoped uptime is not trusted physical event time",
    )
    row(
        "run_identity_and_pairing",
        {
            "run_identity_status": dataset.get("run_identity_status"),
            "split_dataset_id": _mapping(evidence.get("split", {}), "split").get(
                "dataset_id"
            ),
        },
        run_identity_status,
        "A",
        "reports/W08/gate-b-manifest-W08.json",
        "03 §47; 05B §7-8",
        "physical run identity is unresolved",
    )
    row(
        "calibration_provenance",
        dataset.get("calibration_status"),
        calibration_provenance_status,
        "A",
        "reports/W08/gate-b-manifest-W08.json",
        "01 §39.2; 03 §137 Gate B",
        "measurement calibration provenance is absent",
    )
    for ledger_row in rows:
        if ledger_row["field_id"] == "analysis_code_version":
            ledger_row["source_sha256"] = registration.get("analysis_code_sha256")
            if ledger_row["source_sha256"]:
                ledger_row["authority_evidence"] = (
                    f"{ledger_row['source']} "
                    f"(registered analysis_code_sha256 {ledger_row['source_sha256']})"
                )
    return rows


def evaluate_w16_readiness(
    evidence: Mapping[str, Any],
    *,
    artifact_root: str | Path | None = None,
) -> W16ReadinessReport:
    """Evaluate W16 readiness from immutable metadata.

    Fails closed: any missing, unfrozen or contradictory prerequisite produces a
    deterministic refusal reason.  Never opens holdout observations and never
    computes a predictive metric.
    """
    if not isinstance(evidence, Mapping):
        raise W16ReadinessError("evidence must be a mapping")
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise W16ReadinessError(
            f"evidence schema must be {EVIDENCE_SCHEMA!r}, got {evidence.get('schema')!r}"
        )
    header = _mapping(evidence.get("header", {}), "header")
    if header.get("holdout_access") != HOLDOUT_ACCESS:
        raise W16ReadinessError(
            "the preflight may only run with holdout_access = NOT_AUTHORIZED"
        )
    if header.get("evaluation_status") != EVALUATION_STATUS:
        raise W16ReadinessError(
            "the preflight may only run while evaluation_status = NOT_RUN"
        )
    holdout_opened = header.get("holdout_opened")
    if not isinstance(holdout_opened, bool):
        raise W16ReadinessError(
            "header.holdout_opened must be an explicit boolean derived from tracked metadata"
        )

    dataset = _mapping(evidence.get("dataset", {}), "dataset")
    split = _mapping(evidence.get("split", {}), "split")
    registration = _mapping(evidence.get("registration", {}), "registration")
    model = _mapping(evidence.get("model", {}), "model")
    config = _mapping(evidence.get("config", {}), "config")
    registry = _mapping(evidence.get("registry", {}), "registry")
    gates = _mapping(evidence.get("gates", {}), "gates")
    horizon = _mapping(evidence.get("horizon_decision", {}), "horizon_decision")
    calibration = _mapping(evidence.get("calibration", {}), "calibration")
    approvals = _mapping(evidence.get("approvals", {}), "approvals")
    source_paths = _mapping(evidence.get("source_paths") or {}, "source_paths")
    inputs = evidence.get("inputs", {})
    if not isinstance(inputs, Mapping):
        raise W16ReadinessError("evidence 'inputs' must be a mapping when present")

    results: list[RequirementResult] = []

    def add(
        requirement_id: str,
        requirement: str,
        ref: str,
        status: str,
        reason: str | None,
        observed: str,
        scope: str = SCOPE_PROCESS,
    ) -> None:
        results.append(
            _requirement(
                requirement_id, requirement, ref, status, reason, observed, scope
            )
        )

    # ---- Pre-registration record hygiene -----------------------------------
    metric_payload = _custom_metric_payload_present(evidence)
    add(
        "W16-PR-01",
        "The pre-registration record must not contain any final metric value or test-derived result.",
        "05B §44; 03 §92",
        FAIL_VERIFIED if metric_payload else PASS_VERIFIED,
        "PREREGISTRATION_CONTAINS_METRIC_VALUES" if metric_payload else None,
        "metric-bearing fields present" if metric_payload
        else "no metric values or test results in the record",
    )

    history_status = _text(header.get("prior_access_status"))
    prior_openings = header.get("prior_opening_records") or []
    if not isinstance(prior_openings, list):
        raise W16ReadinessError(
            "header.prior_opening_records must be a list of recorded openings"
        )
    if history_status == HOLDOUT_HISTORY_KNOWN and not prior_openings:
        add(
            "W16-PR-02",
            "Prior holdout access must be accounted for from tracked metadata.",
            "03 §49, §92",
            PASS_VERIFIED,
            None,
            "no recorded opening in W11-W15 tracked metadata; limitation disclosed",
            SCOPE_DECLARED_METADATA_ONLY,
        )
    elif history_status == "RECORDED_OPENING" or prior_openings:
        add(
            "W16-PR-02",
            "Prior holdout access must be accounted for from tracked metadata.",
            "03 §49, §92",
            FAIL_VERIFIED,
            "HOLDOUT_PRIOR_OPENING_RECORDED",
            f"recorded prior opening(s): {sorted(map(str, prior_openings))}",
        )
    else:
        add(
            "W16-PR-02",
            "Prior holdout access must be accounted for from tracked metadata.",
            "03 §49, §92",
            BLOCKED_BY_MISSING_EVIDENCE,
            "HOLDOUT_HISTORY_UNACCOUNTED",
            f"prior access status = {history_status or 'MISSING'}",
        )

    if holdout_opened:
        add(
            "W16-PR-03",
            "The tracked locked-test record must not already be opened.",
            "03 §49, §92-93",
            FAIL_VERIFIED,
            "HOLDOUT_ALREADY_OPENED",
            "header.holdout_opened is true",
        )
    else:
        add(
            "W16-PR-03",
            "The tracked locked-test record must not already be opened.",
            "03 §49, §92-93",
            PASS_VERIFIED,
            None,
            "header.holdout_opened is false",
            SCOPE_DECLARED_METADATA_ONLY,
        )

    # ---- Dataset identity and physical eligibility -------------------------
    physical_id = dataset.get("physical_dataset_id")
    if physical_id:
        add(
            "W16-DS-01",
            "An authoritative physical dataset identity with immutable source hashes must exist.",
            "01 §17; 03 §137 Gate B",
            PASS_VERIFIED if dataset.get("source_sha256") else BLOCKED_BY_MISSING_EVIDENCE,
            None if dataset.get("source_sha256") else "DATASET_SOURCE_HASH_MISSING",
            f"dataset={physical_id}, sources={len(dataset.get('source_sha256') or [])}",
            SCOPE_PHYSICAL,
        )
    else:
        add(
            "W16-DS-01",
            "An authoritative physical dataset identity with immutable source hashes must exist.",
            "01 §17; 03 §137 Gate B",
            BLOCKED_BY_MISSING_EVIDENCE,
            "PHYSICAL_DATASET_IDENTITY_MISSING",
            "no physical dataset identity is registered",
        )

    evidence_class = _text(dataset.get("evidence_class"))
    is_physical = evidence_class in PHYSICAL_EVIDENCE_CLASSES
    dataset_id_text = _text(split.get("dataset_id")).lower()
    contradictory = is_physical and (
        "synthetic" in dataset_id_text or "synthetic" in _text(dataset.get("provenance")).lower()
    )
    if contradictory:
        add(
            "W16-DS-02",
            "Dataset evidence class must be physical and not contradict its provenance.",
            "03 §137 Gate B; 00 §5.2",
            FAIL_VERIFIED,
            "DATASET_EVIDENCE_CLASS_CONTRADICTION",
            f"declared {evidence_class} but dataset/provenance is synthetic",
        )
    elif is_physical:
        add(
            "W16-DS-02",
            "Dataset evidence class must be physical and not contradict its provenance.",
            "03 §137 Gate B; 00 §5.2",
            PASS_VERIFIED,
            None,
            evidence_class,
            SCOPE_PHYSICAL,
        )
    else:
        add(
            "W16-DS-02",
            "Dataset evidence class must be physical and not contradict its provenance.",
            "03 §137 Gate B; 00 §5.2",
            FAIL_VERIFIED,
            "DATASET_EVIDENCE_CLASS_NOT_PHYSICAL",
            f"declared evidence class = {evidence_class or 'MISSING'}",
        )

    frozen_at = split.get("locked_test_frozen_at")
    if frozen_at:
        add(
            "W16-DS-03",
            "Locked-test membership must be frozen with an immutable identity before any evaluation.",
            "03 §47, §49, §92",
            PASS_VERIFIED,
            None,
            f"frozen_at={frozen_at}",
        )
    else:
        add(
            "W16-DS-03",
            "Locked-test membership must be frozen with an immutable identity before any evaluation.",
            "03 §47, §49, §92",
            BLOCKED_BY_MISSING_EVIDENCE,
            "TEST_MEMBERSHIP_NOT_FROZEN",
            "locked_test.frozen_at is null",
        )

    opened_at = split.get("locked_test_opened_at")
    if opened_at:
        add(
            "W16-DS-04",
            "The locked-test record must not already be opened.",
            "03 §92-93",
            FAIL_VERIFIED,
            "HOLDOUT_ALREADY_OPENED",
            f"locked_test.opened_at={opened_at}",
        )
    else:
        add(
            "W16-DS-04",
            "The locked-test record must not already be opened.",
            "03 §92-93",
            PASS_VERIFIED,
            None,
            "locked_test.opened_at is null",
            SCOPE_DECLARED_METADATA_ONLY,
        )

    test_runs = list(split.get("test_runs") or [])
    train_runs = list(split.get("train_runs") or [])
    validation_runs = list(split.get("validation_runs") or [])
    development_runs = set(train_runs) | set(validation_runs)
    duplicate_test_ids = len(test_runs) != len(set(test_runs))
    overlap = sorted(set(test_runs) & development_runs)
    if not test_runs:
        add(
            "W16-DS-05",
            "Registered locked-test membership must be non-empty and unambiguous.",
            "03 §47, §49",
            BLOCKED_BY_MISSING_EVIDENCE,
            "TEST_MEMBERSHIP_AMBIGUOUS",
            "no test runs registered",
        )
    elif duplicate_test_ids:
        add(
            "W16-DS-05",
            "Registered locked-test membership must be non-empty and unambiguous.",
            "03 §47, §49",
            FAIL_VERIFIED,
            "TEST_MEMBERSHIP_AMBIGUOUS",
            "duplicate run IDs in test membership",
        )
    elif overlap:
        add(
            "W16-DS-05",
            "Registered locked-test membership must be non-empty and unambiguous.",
            "03 §47, §49",
            FAIL_VERIFIED,
            "DEVELOPMENT_TEST_RUN_OVERLAP",
            f"overlapping runs: {overlap}",
        )
    else:
        add(
            "W16-DS-05",
            "Registered locked-test membership must be non-empty and unambiguous.",
            "03 §47, §49",
            PASS_VERIFIED,
            None,
            f"{len(test_runs)} test runs disjoint from {len(development_runs)} development runs",
            SCOPE_DECLARED_METADATA_ONLY,
        )

    pair_lineage = list(split.get("pair_lineage") or [])
    run_partitions = _run_partition_map(train_runs, validation_runs, test_runs)
    pair_audit = _audit_pair_lineage(pair_lineage, run_partitions)
    pair_problems = list(dict.fromkeys(pair_audit["problems"]))
    pair_runs = set(pair_audit["run_owner"])
    unmapped_test_runs = sorted(set(test_runs) - pair_runs) if pair_lineage else []
    if not pair_lineage:
        add(
            "W16-DS-06",
            "A pair/group lineage must never cross partitions or contain ambiguous membership.",
            "03 §47; 05B §8",
            BLOCKED_BY_MISSING_EVIDENCE,
            "PAIR_LINEAGE_MISSING",
            "no pair lineage declared",
        )
    elif "PAIR_LINEAGE_CROSSES_PARTITIONS" in pair_problems:
        add(
            "W16-DS-06",
            "A pair/group lineage must never cross partitions or contain ambiguous membership.",
            "03 §47; 05B §8",
            FAIL_VERIFIED,
            "PAIR_LINEAGE_CROSSES_PARTITIONS",
            f"straddling pairs: {pair_audit['straddling']}",
        )
    elif pair_problems:
        add(
            "W16-DS-06",
            "A pair/group lineage must never cross partitions or contain ambiguous membership.",
            "03 §47; 05B §8",
            FAIL_VERIFIED,
            pair_problems[0],
            "pair audit problems: " + ",".join(pair_problems),
        )
    elif unmapped_test_runs:
        add(
            "W16-DS-06",
            "A pair/group lineage must never cross partitions or contain ambiguous membership.",
            "03 §47; 05B §8",
            FAIL_VERIFIED,
            "TEST_MEMBERSHIP_AMBIGUOUS",
            f"test runs absent from pair lineage: {unmapped_test_runs}",
        )
    else:
        add(
            "W16-DS-06",
            "A pair/group lineage must never cross partitions or contain ambiguous membership.",
            "03 §47; 05B §8",
            PASS_VERIFIED,
            None,
            f"{pair_audit['pair_count']} pairs, none straddling partitions",
            SCOPE_DECLARED_METADATA_ONLY,
        )

    population_locked = list(split.get("observed_locked_test_runs") or [])
    fold_test_runs = list(split.get("fold_test_runs") or [])
    membership_conflicts: list[str] = []
    if population_locked and sorted(population_locked) != sorted(test_runs):
        membership_conflicts.append("W13-W15 population locked_test_runs differ from split test_runs")
    if fold_test_runs and sorted(fold_test_runs) != sorted(test_runs):
        membership_conflicts.append("fold manifest test_runs differ from split test_runs")
    membership_by_layer = split.get("membership_by_layer") or {}
    if isinstance(membership_by_layer, Mapping):
        for layer_name in sorted(membership_by_layer):
            layer_runs = list(membership_by_layer[layer_name] or [])
            if sorted(layer_runs) != sorted(test_runs):
                membership_conflicts.append(
                    f"{layer_name} membership differs from split test_runs"
                )
    if membership_conflicts:
        add(
            "W16-DS-07",
            "Locked-test membership must be identical across every tracked manifest.",
            "03 §47, §49",
            FAIL_VERIFIED,
            "SPLIT_POPULATION_MISMATCH",
            "; ".join(membership_conflicts),
        )
    elif population_locked and fold_test_runs:
        add(
            "W16-DS-07",
            "Locked-test membership must be identical across every tracked manifest.",
            "03 §47, §49",
            PASS_VERIFIED,
            None,
            "split, fold manifest and W13-W15 population agree",
            SCOPE_DECLARED_METADATA_ONLY,
        )
    else:
        add(
            "W16-DS-07",
            "Locked-test membership must be identical across every tracked manifest.",
            "03 §47, §49",
            BLOCKED_BY_MISSING_EVIDENCE,
            "SPLIT_POPULATION_EVIDENCE_MISSING",
            "population or fold-manifest membership missing",
        )

    registered_test_runs = list(registration.get("test_runs") or [])
    if not registered_test_runs:
        add(
            "W16-DS-08",
            "Observed test membership must equal the registered membership (no change after freeze).",
            "03 §47, §49, §92",
            BLOCKED_BY_MISSING_EVIDENCE,
            "TEST_MEMBERSHIP_REGISTRATION_MISSING",
            "no registered test membership",
        )
    elif sorted(registered_test_runs) != sorted(test_runs):
        add(
            "W16-DS-08",
            "Observed test membership must equal the registered membership (no change after freeze).",
            "03 §47, §49, §92",
            FAIL_VERIFIED,
            "TEST_MEMBERSHIP_CHANGED_AFTER_REGISTRATION",
            (
                f"registered={sorted(registered_test_runs)} "
                f"observed={sorted(test_runs)}"
            ),
        )
    else:
        add(
            "W16-DS-08",
            "Observed test membership must equal the registered membership (no change after freeze).",
            "03 §47, §49, §92",
            PASS_VERIFIED,
            None,
            f"registered == observed ({len(test_runs)} runs)",
            SCOPE_DECLARED_METADATA_ONLY,
        )

    registered_test_pairs = sorted(map(str, registration.get("test_pairs") or []))
    observed_test_pairs = list(pair_audit["observed_test_pairs"])
    if not registered_test_pairs or not observed_test_pairs:
        add(
            "W16-DS-12",
            "Registered test pairs must match the observed pair lineage.",
            "03 §47; 05B §8",
            BLOCKED_BY_MISSING_EVIDENCE,
            "PAIR_MEMBERSHIP_REGISTRATION_MISSING",
            (
                f"registered={registered_test_pairs or 'MISSING'}, "
                f"observed={observed_test_pairs or 'MISSING'}"
            ),
        )
    elif sorted(registered_test_pairs) != sorted(observed_test_pairs):
        add(
            "W16-DS-12",
            "Registered test pairs must match the observed pair lineage.",
            "03 §47; 05B §8",
            FAIL_VERIFIED,
            "TEST_PAIR_MEMBERSHIP_CHANGED_AFTER_REGISTRATION",
            f"registered={registered_test_pairs}, observed={observed_test_pairs}",
        )
    else:
        add(
            "W16-DS-12",
            "Registered test pairs must match the observed pair lineage.",
            "03 §47; 05B §8",
            PASS_VERIFIED,
            None,
            f"registered == observed ({len(observed_test_pairs)} test pairs)",
            SCOPE_DECLARED_METADATA_ONLY,
        )

    source_hashes = _mapping(dataset.get("run_source_hashes") or {}, "dataset.run_source_hashes")
    if not source_hashes:
        add(
            "W16-DS-09",
            "No physical run may appear twice under different identifiers (source-hash lineage).",
            "05B §8; 03 §47",
            BLOCKED_BY_MISSING_EVIDENCE,
            "RUN_SOURCE_IDENTITY_MISSING",
            "no per-run physical source hashes declared",
        )
    else:
        all_runs = set(train_runs) | set(validation_runs) | set(test_runs)
        uncovered_runs = sorted(all_runs - {_text(run) for run in source_hashes})
        by_source: dict[str, list[str]] = {}
        for run_id, source_sha in source_hashes.items():
            by_source.setdefault(_text(source_sha), []).append(_text(run_id))
        duplicates = {
            source: sorted(runs) for source, runs in by_source.items() if len(set(runs)) > 1
        }
        source_in_both = sorted(
            {
                run_id
                for run_id, source_sha in source_hashes.items()
                if run_id in set(test_runs)
                and any(
                    other in development_runs
                    for other in by_source.get(_text(source_sha), [])
                    if other != run_id
                )
            }
        )
        if duplicates or source_in_both:
            add(
                "W16-DS-09",
                "No physical run may appear twice under different identifiers (source-hash lineage).",
                "05B §8; 03 §47",
                FAIL_VERIFIED,
                "DUPLICATE_PHYSICAL_RUN_SOURCE",
                f"duplicated sources across runs: {duplicates or source_in_both}",
            )
        elif uncovered_runs:
            add(
                "W16-DS-09",
                "No physical run may appear twice under different identifiers (source-hash lineage).",
                "05B §8; 03 §47",
                BLOCKED_BY_MISSING_EVIDENCE,
                "RUN_SOURCE_IDENTITY_INCOMPLETE",
                f"runs without source hashes: {uncovered_runs}",
            )
        else:
            add(
                "W16-DS-09",
                "No physical run may appear twice under different identifiers (source-hash lineage).",
                "05B §8; 03 §47",
                PASS_VERIFIED,
                None,
                f"{len(source_hashes)} run source hashes, all unique",
                SCOPE_PHYSICAL,
            )

    if gates.get("test_partition_used") is False and split.get("test_partition_used") is False:
        add(
            "W16-DS-10",
            "Recorded evaluation history must show the test partition was never used.",
            "03 §49, §92; 05B §44",
            PASS_VERIFIED,
            None,
            "test_partition_used=false across recorded layer manifests",
            SCOPE_DECLARED_METADATA_ONLY,
        )
    elif gates.get("test_partition_used") is None or split.get("test_partition_used") is None:
        add(
            "W16-DS-10",
            "Recorded evaluation history must show the test partition was never used.",
            "03 §49, §92; 05B §44",
            BLOCKED_BY_MISSING_EVIDENCE,
            "TEST_USAGE_HISTORY_UNACCOUNTED",
            "test_partition_used flag missing",
        )
    else:
        add(
            "W16-DS-10",
            "Recorded evaluation history must show the test partition was never used.",
            "03 §49, §92; 05B §44",
            FAIL_VERIFIED,
            "TEST_PARTITION_ALREADY_USED",
            "a recorded layer reports test_partition_used=true",
        )

    # ---- Physical validity provenance --------------------------------------
    validity = _text(dataset.get("physical_run_validity"))
    add(
        "W16-PV-01",
        "Physical run validity must be established for the final population.",
        "01 §17, §33; 03 §137 Gate B",
        PASS_VERIFIED if validity in {"VALID", "VALIDATED"} else BLOCKED_BY_MISSING_EVIDENCE,
        None if validity in {"VALID", "VALIDATED"} else "PHYSICAL_RUN_VALIDITY_MISSING",
        f"physical_run_validity={validity or 'MISSING'}",
        SCOPE_PHYSICAL,
    )

    hardware_status = _text(dataset.get("hardware_config_status"))
    add(
        "W16-PV-02",
        "Hardware configuration/lineage must be verified for the final population.",
        "01 §39.1; 03 §137 Gate B",
        PASS_VERIFIED if hardware_status == "VERIFIED" else BLOCKED_BY_MISSING_EVIDENCE,
        None if hardware_status == "VERIFIED" else "HARDWARE_CONFIG_NOT_VERIFIED",
        f"hardware_config_status={hardware_status or 'MISSING'}",
        SCOPE_PHYSICAL,
    )

    time_ok = (
        _text(dataset.get("time_domain")) not in {"", "BOOT_SCOPED_UPTIME", "UNKNOWN"}
        and _text(dataset.get("clock_sync")) == "EVIDENCED"
    )
    add(
        "W16-PV-03",
        "Physical event time and clock synchronization must be evidenced.",
        "01 §18; 03 §137 Gate B",
        PASS_VERIFIED if time_ok else BLOCKED_BY_MISSING_EVIDENCE,
        None if time_ok else "TIME_PROVENANCE_INADEQUATE",
        (
            f"time_domain={_text(dataset.get('time_domain')) or 'MISSING'}, "
            f"clock_sync={_text(dataset.get('clock_sync')) or 'MISSING'}"
        ),
        SCOPE_PHYSICAL,
    )

    quality = _text(dataset.get("sample_quality_status"))
    add(
        "W16-PV-04",
        "Sample quality must be trusted under the predeclared completeness policy.",
        "01 §33; W08 completeness policy",
        PASS_VERIFIED if quality == "TRUSTED" else BLOCKED_BY_MISSING_EVIDENCE,
        None if quality == "TRUSTED" else "SAMPLE_QUALITY_UNTRUSTED",
        f"sample_quality_status={quality or 'MISSING'}",
        SCOPE_PHYSICAL,
    )

    calibration_status = _text(dataset.get("calibration_status"))
    add(
        "W16-PV-05",
        "Measurement calibration provenance must be traceable for the final population.",
        "01 §39.2; 03 §137 Gate B",
        PASS_VERIFIED if calibration_status not in {"", "NOT_AVAILABLE", "UNVERIFIED"} else BLOCKED_BY_MISSING_EVIDENCE,
        None if calibration_status not in {"", "NOT_AVAILABLE", "UNVERIFIED"} else "CALIBRATION_PROVENANCE_MISSING",
        f"calibration_status={calibration_status or 'MISSING'}",
        SCOPE_PHYSICAL,
    )

    # ---- Split staleness ----------------------------------------------------
    model_dataset = _text(model.get("training_dataset_id"))
    split_dataset = _text(split.get("dataset_id"))
    if not model_dataset or not split_dataset:
        add(
            "W16-DS-11",
            "The split manifest must refer to the same dataset identity as the registered model.",
            "05B §8 B1-B2",
            BLOCKED_BY_MISSING_EVIDENCE,
            "SPLIT_DATASET_IDENTITY_MISSING",
            f"model dataset={model_dataset or 'MISSING'}, split dataset={split_dataset or 'MISSING'}",
        )
    elif model_dataset != split_dataset:
        add(
            "W16-DS-11",
            "The split manifest must refer to the same dataset identity as the registered model.",
            "05B §8 B1-B2",
            FAIL_VERIFIED,
            "SPLIT_DATASET_MISMATCH",
            f"model dataset={model_dataset}, split dataset={split_dataset}",
        )
    else:
        add(
            "W16-DS-11",
            "The split manifest must refer to the same dataset identity as the registered model.",
            "05B §8 B1-B2",
            PASS_VERIFIED,
            None,
            f"dataset identity={split_dataset}",
            SCOPE_DECLARED_METADATA_ONLY,
        )

    # ---- Model and inference identity --------------------------------------
    artifact_records, artifact_problems, artifact_notes = _verify_declared_artifacts(
        evidence, artifact_root
    )
    add(
        "W16-MD-01",
        "Declared model artifacts must re-hash to their registered SHA-256 values.",
        "03 §92; artifact-convention §4-5",
        PASS_VERIFIED if not artifact_problems else (
            BLOCKED_BY_MISSING_EVIDENCE if all(
                problem in {"ARTIFACT_ROOT_MISSING", "ARTIFACT_DECLARATIONS_MISSING"} for problem in artifact_problems
            ) else FAIL_VERIFIED
        ),
        None if not artifact_problems else ",".join(artifact_problems),
        "; ".join(artifact_notes) or "no artifact hashes verified",
        SCOPE_DECLARED_METADATA_ONLY,
    )

    model_sha = _text(model.get("model_artifact_sha256"))
    file_ubj = _mapping(_mapping(model.get("files", {}), "model.files").get("ubj", {}), "model.files.ubj")
    bound_sha = _text(file_ubj.get("sha256"))
    registered_model_sha = _text(registration.get("model_artifact_sha256"))
    registered_config_sha = _text(registration.get("model_config_sha256"))
    registered_schema_sha = _text(registration.get("feature_schema_hash"))
    sha_chain_ok = (
        _is_hex64(model_sha)
        and model_sha == bound_sha
        and registered_model_sha == model_sha
    )
    add(
        "W16-MD-02",
        "Model identity must be identical across the manifest, the native file declaration and the registration.",
        "03 §92",
        PASS_VERIFIED if sha_chain_ok else (
            BLOCKED_BY_MISSING_EVIDENCE if not (_is_hex64(model_sha) and _is_hex64(bound_sha))
            else FAIL_VERIFIED
        ),
        None if sha_chain_ok else (
            "MODEL_IDENTITY_DRIFT" if _is_hex64(model_sha) and _is_hex64(bound_sha)
            else "MODEL_IDENTITY_MISSING"
        ),
        f"manifest={model_sha[:16] or 'MISSING'}, file={bound_sha[:16] or 'MISSING'}, registered={registered_model_sha[:16] or 'MISSING'}",
        SCOPE_DECLARED_METADATA_ONLY,
    )

    config_hash = _text(model.get("model_config_hash"))
    config_declared = _text(config.get("config_sha256"))
    config_ok = (
        bool(config_hash)
        and config_hash == config_declared
        and registered_config_sha == config_hash
    )
    add(
        "W16-MD-03",
        "The model configuration hash must match the registered configuration.",
        "03 §92",
        PASS_VERIFIED if config_ok else (
            BLOCKED_BY_MISSING_EVIDENCE if not (config_hash and config_declared)
            else FAIL_VERIFIED
        ),
        None if config_ok else (
            "MODEL_CONFIG_HASH_MISMATCH" if config_hash and config_declared else "MODEL_CONFIG_HASH_MISSING"
        ),
        (
            f"manifest={config_hash[:16] or 'MISSING'}, "
            f"config={config_declared[:16] or 'MISSING'}, "
            f"registered={registered_config_sha[:16] or 'MISSING'}"
        ),
        SCOPE_DECLARED_METADATA_ONLY,
    )

    schema_hash = _text(model.get("feature_schema_hash"))
    registry_schema = _text(registry.get("schema_sha256"))
    schema_ok = (
        bool(schema_hash)
        and schema_hash == registry_schema
        and registered_schema_sha == schema_hash
    )
    add(
        "W16-MD-04",
        "The feature schema hash must match the registry identity and the registration.",
        "03 §92; 05B §9",
        PASS_VERIFIED if schema_ok else (
            BLOCKED_BY_MISSING_EVIDENCE if not (schema_hash and registry_schema) else FAIL_VERIFIED
        ),
        None if schema_ok else (
            "FEATURE_SCHEMA_HASH_MISMATCH" if schema_hash and registry_schema else "FEATURE_SCHEMA_HASH_MISSING"
        ),
        (
            f"manifest={schema_hash[:16] or 'MISSING'}, "
            f"registry={registry_schema[:16] or 'MISSING'}, "
            f"registered={registered_schema_sha[:16] or 'MISSING'}"
        ),
        SCOPE_DECLARED_METADATA_ONLY,
    )

    ordered = list(model.get("ordered_feature_ids") or [])
    allowlist = list(config.get("feature_allowlist") or [])
    computed_order_sha = _ordered_feature_ids_sha256(ordered) if ordered else ""
    model_order_sha = _text(model.get("ordered_feature_ids_sha256"))
    registered_order_sha = _text(registration.get("ordered_feature_ids_sha256"))
    order_ok = (
        bool(ordered)
        and ordered == allowlist
        and computed_order_sha == model_order_sha
        and registered_order_sha == model_order_sha
    )
    add(
        "W16-MD-05",
        "Ordered feature identities must match the allowlist, their recorded hash and the registration.",
        "03 §92; 02 §60.5",
        PASS_VERIFIED if order_ok else (
            BLOCKED_BY_MISSING_EVIDENCE if not ordered or not model_order_sha
            else FAIL_VERIFIED
        ),
        None if order_ok else (
            "ORDERED_FEATURE_IDS_MISMATCH" if ordered and model_order_sha
            else "ORDERED_FEATURE_IDS_MISSING"
        ),
        f"{len(ordered)} features, allowlist={len(allowlist)}, order_sha={model_order_sha[:16] or 'MISSING'}",
        SCOPE_DECLARED_METADATA_ONLY,
    )

    target_version = _text(model.get("target_spec_version"))
    config_target_version = _text(config.get("target_spec_version"))
    add(
        "W16-MD-06",
        "The target definition version must be identical across model and configuration.",
        "03 §92; 05B §54",
        PASS_VERIFIED if target_version and target_version == config_target_version else (
            BLOCKED_BY_MISSING_EVIDENCE if not (target_version and config_target_version) else FAIL_VERIFIED
        ),
        None if target_version and target_version == config_target_version else (
            "TARGET_VERSION_MISMATCH" if target_version and config_target_version else "TARGET_VERSION_MISSING"
        ),
        f"model={target_version or 'MISSING'}, config={config_target_version or 'MISSING'}",
        SCOPE_DECLARED_METADATA_ONLY,
    )

    model_class = _text(model.get("data_evidence_class"))
    release_eligibility = _text(model.get("release_eligibility"))
    synthetic_model = (
        model_class not in PHYSICAL_EVIDENCE_CLASSES
        or release_eligibility not in RELEASE_ELIGIBLE_CLASSES
    )
    add(
        "W16-MD-07",
        "A synthetic/non-deployable model must never acquire release or locked-test eligibility.",
        "03 §103, §137; 05B §44",
        FAIL_VERIFIED if synthetic_model else PASS_VERIFIED,
        "MODEL_SYNTHETIC_NON_DEPLOYABLE" if synthetic_model else None,
        f"evidence_class={model_class or 'MISSING'}, release_eligibility={release_eligibility or 'MISSING'}",
        SCOPE_DECLARED_METADATA_ONLY,
    )

    # ---- Frozen scientific decisions ---------------------------------------
    target_frozen = (
        config.get("target_status") == "FROZEN"
        and config.get("target_boundary_c") is not None
    )
    add(
        "W16-MD-08",
        "The critical target definition must be frozen by its policy authority.",
        "03 §42-43, §92; 05B §54",
        PASS_VERIFIED if target_frozen else FAIL_VERIFIED,
        None if target_frozen else "CRITICAL_TARGET_UNFROZEN",
        f"target_status={config.get('target_status')}, boundary_c={config.get('target_boundary_c')}",
        SCOPE_DECLARED_METADATA_ONLY,
    )

    representative = _text(config.get("representative_temperature_status"))
    representative_frozen = representative == "FROZEN"
    add(
        "W16-MD-09",
        "The representative temperature for the final label must be frozen.",
        "03 §42-43",
        PASS_VERIFIED if representative_frozen else FAIL_VERIFIED,
        None if representative_frozen else "REPRESENTATIVE_TEMPERATURE_UNFROZEN",
        f"representative_temperature={representative or 'MISSING'}",
        SCOPE_DECLARED_METADATA_ONLY,
    )

    horizon_frozen = (
        horizon.get("freeze_status") == "FROZEN"
        and horizon.get("primary_horizon_s") is not None
        and model.get("horizon_status") == "FROZEN"
    )
    add(
        "W16-MD-10",
        "One primary horizon must be frozen before the final test.",
        "03 §44, §84, §92",
        PASS_VERIFIED if horizon_frozen else FAIL_VERIFIED,
        None if horizon_frozen else "PRIMARY_HORIZON_UNFROZEN",
        (
            f"horizon_status={model.get('horizon_status')}, "
            f"decision={horizon.get('freeze_status')}, "
            f"primary_horizon_s={horizon.get('primary_horizon_s')}"
        ),
        SCOPE_DECLARED_METADATA_ONLY,
    )

    threshold_status = _text(model.get("operating_threshold_status"))
    threshold_value = model.get("operating_threshold")
    threshold_record = _mapping(
        model.get("operating_threshold_record") or {}, "operating_threshold_record"
    )
    threshold_source = _text(threshold_record.get("selection_basis"))
    threshold_record_ok = (
        threshold_source in {"DEVELOPMENT_SELECTED", "FROZEN_DOCUMENT"}
        and isinstance(threshold_value, (int, float))
        and not isinstance(threshold_value, bool)
        and isinstance(threshold_record.get("threshold"), (int, float))
        and not isinstance(threshold_record.get("threshold"), bool)
        and float(threshold_record.get("threshold")) == float(threshold_value)
        and _text(threshold_record.get("model_artifact_sha256"))
        == _text(registration.get("model_artifact_sha256"))
        and _text(threshold_record.get("analysis_code_sha256"))
        == _text(registration.get("analysis_code_sha256"))
        and _is_hex64(_text(threshold_record.get("evidence_sha256")))
    )
    threshold_frozen = threshold_status == "FROZEN" and threshold_record_ok
    add(
        "W16-MD-11",
        "The operating threshold must be selected on development data and frozen.",
        "03 §87, §92",
        PASS_VERIFIED if threshold_frozen else FAIL_VERIFIED,
        None if threshold_frozen else "OPERATING_THRESHOLD_UNFROZEN",
        (
            f"operating_threshold_status={threshold_status or 'MISSING'}, "
            f"value={threshold_value}, source={threshold_source or 'MISSING'}"
        ),
        SCOPE_DECLARED_METADATA_ONLY,
    )

    persistence_status = _text(model.get("warning_persistence_status"))
    persistence_k = model.get("warning_persistence_k")
    persistence_frozen = (
        persistence_status == "FROZEN"
        and isinstance(persistence_k, (int, float))
        and not isinstance(persistence_k, bool)
        and persistence_k > 0
    )
    add(
        "W16-MD-12",
        "The warning persistence rule must be frozen before the final test.",
        "03 §88, §92",
        PASS_VERIFIED if persistence_frozen else FAIL_VERIFIED,
        None if persistence_frozen else "WARNING_PERSISTENCE_UNFROZEN",
        (
            f"warning_persistence_status={persistence_status or 'MISSING'}, "
            f"k={persistence_k}"
        ),
        SCOPE_DECLARED_METADATA_ONLY,
    )

    score_semantics = _text(model.get("score_semantics"))
    calibration_status_model = _text(model.get("calibration_status"))
    if score_semantics == "risk_score":
        calibration_consistent = (
            calibration_status_model == "RISK_SCORE_ONLY"
            and _text(calibration.get("decision")) == "RISK_SCORE_ONLY"
            and calibration.get("probabilistic_claim") is not True
            and config.get("allow_locked_test_access") is False
        )
    elif score_semantics in {"calibrated_probability", "calibrated_probability_estimate"}:
        calibration_consistent = (
            calibration_status_model == "CALIBRATED"
            and _text(calibration.get("fit_population")) == "DEVELOPMENT_ONLY"
            and calibration.get("locked_test_used") is False
            and config.get("allow_locked_test_access") is False
        )
    else:
        calibration_consistent = False
    add(
        "W16-MD-13",
        "Calibration and output semantics must match the declared output contract (risk score or development-fit probability).",
        "03 §58-60, §92",
        PASS_VERIFIED if calibration_consistent else FAIL_VERIFIED,
        None if calibration_consistent else "CALIBRATION_SEMANTICS_INCONSISTENT",
        (
            f"score_semantics={score_semantics or 'MISSING'}, "
            f"calibration={calibration_status_model or 'MISSING'}, "
            f"decision={calibration.get('decision')}"
        ),
        SCOPE_DECLARED_METADATA_ONLY,
    )

    episode_status = _text(config.get("episode_policy_status"))
    association_status = _text(config.get("association_policy_status"))
    matching_frozen = episode_status == "FROZEN" and association_status == "FROZEN"
    add(
        "W16-MD-14",
        "The warning-episode and event-association policy must be frozen.",
        "03 §89-90",
        PASS_VERIFIED if matching_frozen else FAIL_VERIFIED,
        None if matching_frozen else "EVENT_MATCHING_POLICY_UNFROZEN",
        f"episode={episode_status or 'MISSING'}, association={association_status or 'MISSING'}",
        SCOPE_DECLARED_METADATA_ONLY,
    )

    missingness = _text(registry.get("missingness_policy"))
    add(
        "W16-MD-15",
        "The missingness policy must be part of the frozen feature schema.",
        "03 §125; registry policy",
        PASS_VERIFIED if missingness else FAIL_VERIFIED,
        None if missingness else "MISSINGNESS_POLICY_UNFROZEN",
        f"missingness_policy={missingness or 'MISSING'}",
        SCOPE_DECLARED_METADATA_ONLY,
    )

    analysis_code = _text(registration.get("analysis_code_sha256"))
    current_analysis_code = _text(evidence.get("current_analysis_code_sha256"))
    if not _is_hex64(analysis_code) or not _is_hex64(current_analysis_code):
        analysis_status = BLOCKED_BY_MISSING_EVIDENCE
        analysis_reason = "ANALYSIS_CODE_IDENTITY_MISSING"
    elif analysis_code != current_analysis_code:
        analysis_status = FAIL_VERIFIED
        analysis_reason = "ANALYSIS_CODE_CHANGED_AFTER_REGISTRATION"
    else:
        analysis_status = PASS_VERIFIED
        analysis_reason = None
    add(
        "W16-MD-16",
        "The analysis/preflight code identity must be registered and unchanged.",
        "03 §92, §133, §158",
        analysis_status,
        analysis_reason,
        (
            f"registered={analysis_code[:16] or 'MISSING'}, "
            f"current={current_analysis_code[:16] or 'MISSING'}"
        ),
    )

    # ---- Freeze-authority consistency --------------------------------------
    ledger = _freeze_ledger(evidence, inputs)
    spec_by_id = {spec.field_id: spec for spec in FREEZE_FIELD_SPECS}
    authority_problems: list[str] = []
    for row in ledger:
        spec = spec_by_id.get(row["field_id"])
        if spec is None:
            authority_problems.append(f"unknown freeze field {row['field_id']}")
            continue
        if row["status"] not in FREEZE_STATUSES:
            authority_problems.append(f"{row['field_id']} has invalid status")
        if row["status"] == FROZEN_APPROVED and row["authority"] not in spec.permitted_authorities:
            authority_problems.append(
                f"{row['field_id']} frozen by unauthorized {row['authority']}"
            )
        if row["authority"] not in spec.permitted_authorities:
            authority_problems.append(
                f"{row['field_id']} recorded authority {row['authority']} not permitted"
            )
    add(
        "W16-GV-01",
        "Every freeze field must record an authority permitted for that decision.",
        "05B §44 freeze authority",
        PASS_VERIFIED if not authority_problems else FAIL_VERIFIED,
        None if not authority_problems else "FREEZE_AUTHORITY_NOT_PERMITTED",
        "; ".join(authority_problems) or "all freeze authorities permitted",
    )

    contradiction_checks = {
        "primary_horizon": horizon_frozen,
        "target_definition": target_frozen,
        "operating_threshold": threshold_frozen,
        "warning_persistence": persistence_frozen,
        "physical_dataset_identity": bool(physical_id),
        "telemetry_time_provenance": time_ok,
    }
    contradictions = sorted(
        field_id
        for field_id, observed_frozen in contradiction_checks.items()
        if next(row for row in ledger if row["field_id"] == field_id)["status"]
        == FROZEN_APPROVED
        and not observed_frozen
    )
    add(
        "W16-GV-02",
        "No field may claim FROZEN_APPROVED while its observed evidence is unfrozen or missing.",
        "05B §44; 03 §92",
        PASS_VERIFIED if not contradictions else FAIL_VERIFIED,
        None if not contradictions else "FREEZE_CLAIM_CONTRADICTS_EVIDENCE",
        "; ".join(contradictions) or "no contradicted freeze claims",
    )

    incomplete_freeze_fields = sorted(
        row["field_id"] for row in ledger if row["status"] != FROZEN_APPROVED
    )
    add(
        "W16-GV-10",
        "Every freeze field required for the final test must be FROZEN_APPROVED.",
        "03 §92; 05B §44",
        PASS_VERIFIED if not incomplete_freeze_fields else FAIL_VERIFIED,
        None if not incomplete_freeze_fields else "FREEZE_LEDGER_INCOMPLETE",
        (
            "unfrozen or missing fields: " + ", ".join(incomplete_freeze_fields)
            if incomplete_freeze_fields
            else "all freeze fields FROZEN_APPROVED"
        ),
    )

    # ---- Approvals and release authorization -------------------------------
    approval_records = approvals.get("approvals")
    approval_records = list(approval_records) if isinstance(approval_records, list) else []
    records_by_role: dict[str, list[Mapping[str, Any]]] = {}
    for record in approval_records:
        if isinstance(record, Mapping):
            records_by_role.setdefault(_text(record.get("role")), []).append(record)
    approval_rows: list[dict[str, Any]] = []
    for index, spec in enumerate(APPROVAL_SPECS, start=1):
        role_records = records_by_role.get(spec.role, [])
        valid = [
            record
            for record in role_records
            if _text(record.get("approved_by"))
            and _text(record.get("model_artifact_sha256")) == registered_model_sha
            and _text(record.get("analysis_code_sha256")) == analysis_code
            and _text(record.get("canonical_ref"))
        ]
        if valid:
            status = PASS_VERIFIED
            reason = None
            observed = f"{len(valid)} binding record(s) for role {spec.role}"
        elif role_records:
            status = FAIL_VERIFIED
            reason = "APPROVAL_BINDING_INVALID"
            observed = f"role {spec.role} records do not bind the registered model/code identity"
        else:
            status = BLOCKED_BY_MISSING_EVIDENCE
            reason = f"APPROVAL_MISSING:{spec.role}"
            observed = "no approval record issued"
        add(
            f"W16-GV-{2 + index:02d}",
            f"Required approval must be issued: {spec.description}",
            spec.canonical_ref,
            status,
            reason,
            observed,
        )
        approval_rows.append(
            {
                "approval_id": spec.approval_id,
                "role": spec.role,
                "description": spec.description,
                "canonical_ref": spec.canonical_ref,
                "status": status,
                "reason_code": reason,
                "records": len(valid),
            }
        )

    release_authorized = any(
        _text(record.get("role")) == "TEAM_LEAD"
        and _text(record.get("release_authorization")) == "AUTHORIZED_ONE_TIME_EVALUATION"
        for record in approval_records
        if isinstance(record, Mapping)
    )
    add(
        "W16-GV-08",
        "Explicit release authorization for the one-time locked evaluation must exist.",
        "03 §92-93; 04 §31",
        PASS_VERIFIED if release_authorized else BLOCKED_BY_MISSING_EVIDENCE,
        None if release_authorized else "RELEASE_AUTHORIZATION_MISSING",
        "authorization record present" if release_authorized else "no release authorization record",
    )

    # ---- Scientific prerequisites ------------------------------------------
    gate_b = _text(gates.get("gate_b_observed_status"))
    gate_g3 = _text(gates.get("gate_g3_decision"))
    eligible_runs = gates.get("predictive_eligible_runs")
    prerequisites_ok = (
        gate_b == "GREEN"
        and gate_g3 == "GO"
        and isinstance(eligible_runs, int)
        and not isinstance(eligible_runs, bool)
        and eligible_runs > 0
    )
    add(
        "W16-GV-09",
        "Physical/data prerequisites must permit a predictive evaluation (Gate B GREEN, Gate G3 GO).",
        "03 §137; 04 §31; 05B §54",
        PASS_VERIFIED if prerequisites_ok else FAIL_VERIFIED,
        None if prerequisites_ok else "SCIENTIFIC_PREREQUISITES_BLOCKED",
        (
            f"gate_b={gate_b or 'MISSING'}, gate_g3={gate_g3 or 'MISSING'}, "
            f"predictive_eligible_runs={eligible_runs}"
        ),
    )

    # ---- Once-only and no-execution guarantees -----------------------------
    add(
        "W16-EX-01",
        "The preflight must not have executed the locked test or produced an evaluation receipt.",
        "03 §92-93; 05B §44",
        PASS_VERIFIED if evidence.get("evaluation_receipt") is None else FAIL_VERIFIED,
        None if evidence.get("evaluation_receipt") is None else "PREFLIGHT_FOUND_EVALUATION_RECEIPT",
        "no evaluation receipt supplied or produced",
    )

    # ---- Decision -----------------------------------------------------------
    reasons = sorted(
        {result.reason_code for result in results if result.reason_code}
    )
    decision = DECISION_REFUSED if reasons else DECISION_READY

    refusal_ledger = [result.to_dict() for result in results if result.reason_code]
    observations_used = sorted(
        {
            _text(source_paths.get(key))
            for key in source_paths
            if _text(source_paths.get(key))
        }
    )

    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "layer_version": LAYER_VERSION,
        "manifest_kind": MANIFEST_KIND,
        "holdout_access": HOLDOUT_ACCESS,
        "holdout_opened": bool(holdout_opened),
        "evaluation_status": EVALUATION_STATUS,
        "dataset_identity": {
            "physical_dataset_id": physical_id,
            "dataset_id": split.get("dataset_id"),
            "evidence_class": evidence_class,
            "source_sha256": list(dataset.get("source_sha256") or []),
            "hardware_config_id": dataset.get("hardware_config_id"),
            "hardware_config_status": dataset.get("hardware_config_status"),
            "run_identity_status": dataset.get("run_identity_status"),
            "calibration_status": dataset.get("calibration_status"),
            "time_domain": dataset.get("time_domain"),
            "clock_sync": dataset.get("clock_sync"),
            "sample_quality_status": dataset.get("sample_quality_status"),
            "physical_run_validity": dataset.get("physical_run_validity"),
            "status": (
                PASS_VERIFIED
                if is_physical and physical_id and not contradictory
                else FAIL_VERIFIED
            ),
        },
        "split_identity": {
            "dataset_id": split.get("dataset_id"),
            "provenance": split.get("provenance"),
            "registered": {
                "test_runs": sorted(registered_test_runs),
                "test_pairs": sorted(registration.get("test_pairs") or []),
            },
            "observed": {
                "test_runs": sorted(test_runs),
                "train_runs": sorted(train_runs),
                "validation_runs": sorted(validation_runs),
                "population_locked_test_runs": sorted(population_locked),
                "fold_test_runs": sorted(fold_test_runs),
                "pair_lineage": sorted(
                    (
                        {
                            "pair_id": _text(entry.get("pair_id")),
                            "partition": _text(entry.get("partition")),
                            "run_ids": (
                                sorted(str(run) for run in entry.get("run_ids"))
                                if isinstance(entry.get("run_ids"), (list, tuple))
                                else []
                            ),
                        }
                        for entry in pair_lineage
                        if isinstance(entry, Mapping)
                    ),
                    key=lambda item: (item["pair_id"], item["partition"]),
                ),
                "grouping_key": split.get("grouping_key") or "run_id+pair_id",
            },
            "locked_test": {
                "frozen_at": frozen_at,
                "opened_at": opened_at,
                "test_partition_used": split.get("test_partition_used"),
                "frozen": bool(frozen_at),
            },
            "disjointness": {
                "dev_test_overlap": overlap,
                "pair_straddling": pair_audit["straddling"],
                "pair_problems": pair_problems,
                "duplicate_test_ids": duplicate_test_ids,
                "duplicate_physical_sources": sorted(
                    {
                        run_id
                        for run_id, source_sha in source_hashes.items()
                        if sum(
                            1
                            for other in source_hashes.values()
                            if _text(other) == _text(source_sha)
                        )
                        > 1
                    }
                ),
            },
        },
        "holdout_isolation": {
            "audit_basis": "DECLARED_REPORT_METADATA_ONLY",
            "never_used_for": {
                "feature_selection": "NO_RECORDED_TEST_EXPOSURE",
                "model_architecture_selection": "NO_RECORDED_TEST_EXPOSURE",
                "hyperparameter_tuning": "NO_RECORDED_TEST_EXPOSURE",
                "class_weight_or_sampling_decisions": "NO_RECORDED_TEST_EXPOSURE",
                "calibration_fitting": "NO_RECORDED_TEST_EXPOSURE",
                "threshold_selection": "NO_RECORDED_TEST_EXPOSURE",
                "persistence_selection": "NO_RECORDED_TEST_EXPOSURE",
                "primary_horizon_selection": "NO_RECORDED_TEST_EXPOSURE",
                "ablation_based_winner_selection": "NO_RECORDED_TEST_EXPOSURE",
            },
            "prior_access": {
                "status": history_status or "MISSING",
                "records": sorted(map(str, prior_openings)),
                "scan": dict(header.get("prior_access_evidence") or {}),
                "basis": (
                    "test_partition_used=false and locked_test_used=false across "
                    "W11-W15 tracked manifests; no opening receipt exists"
                ),
                "limitation": (
                    "tracked metadata cannot prove absence of out-of-band access "
                    "that left no repository record"
                ),
            },
        },
        "model_inference_identity": {
            "artifact_id": model.get("artifact_id"),
            "native_model_sha256": model_sha,
            "native_model_file_sha256": bound_sha,
            "model_config_version": model.get("model_config_version"),
            "model_config_sha256": config_hash,
            "feature_version": model.get("feature_version"),
            "feature_schema_hash": schema_hash,
            "ordered_feature_ids": ordered,
            "ordered_feature_ids_sha256": model_order_sha,
            "training_dataset_id": model.get("training_dataset_id"),
            "target_spec_version": target_version,
            "horizon_s": model.get("horizon_s"),
            "horizon_status": model.get("horizon_status"),
            "risk_score_semantics": model.get("score_semantics"),
            "calibration_status": model.get("calibration_status"),
            "operating_threshold": model.get("operating_threshold"),
            "operating_threshold_status": threshold_status,
            "operating_threshold_source": threshold_source or None,
            "operating_threshold_record_evidence_sha256": _text(
                threshold_record.get("evidence_sha256")
            )
            or None,
            "warning_persistence_status": persistence_status,
            "warning_persistence_k": model.get("warning_persistence_k"),
            "event_matching_policy_status": {
                "episode": episode_status,
                "association": association_status,
            },
            "data_evidence_class": model_class,
            "release_eligibility": release_eligibility,
            "analysis_code_sha256": analysis_code,
        },
        "freeze_ledger": ledger,
        "registration": {
            "test_runs": sorted(registered_test_runs),
            "test_pairs": sorted(map(str, registration.get("test_pairs") or [])),
            "model_artifact_sha256": registered_model_sha,
            "model_config_sha256": _text(registration.get("model_config_sha256")),
            "feature_schema_hash": _text(registration.get("feature_schema_hash")),
            "ordered_feature_ids_sha256": registered_order_sha,
            "analysis_code_sha256": analysis_code,
        },
        "required_approvals": approval_rows,
        "statistical_analysis_registration": dict(ANALYSIS_REGISTRATION),
        "evaluation_disposition": {
            "locked_evaluation": "NOT_EXECUTED_PREREQUISITES_UNMET",
            "interpretation": "NO_INTERPRETATION_TEST_NOT_RUN",
            "model_release_candidate": "NOT_ISSUED",
            "metrics_reported": False,
            "metrics_policy": (
                "AP, precision, recall, EWT, AIW and calibration metrics have no "
                "value; they are NOT_ESTIMABLE/NOT_APPLICABLE until an authorized "
                "one-time evaluation produces them"
            ),
        },
        "readiness_decision": {
            "decision": decision,
            "refusal_reasons": reasons,
            "refused_requirements": refusal_ledger,
            "permitted_actions": ["static metadata checks", "pre-registration review"],
            "forbidden_actions": [
                "opening locked-test observations",
                "computing locked-test predictive metrics",
                "tuning any model/threshold/persistence on test data",
                "issuing a model release candidate",
                "granting Gate G4",
            ],
        },
        "requirements": [result.to_dict() for result in results],
        "artifact_hashes": artifact_records,
        "inputs_observed": observations_used,
        "limitations": [
            "PRE_REGISTRATION_ONLY: no locked-test evaluation has run and none is authorized.",
            "No physical dataset, no predictive-eligible real run and no frozen primary horizon exist; every predictive prerequisite is blocked.",
            "The registered model is a synthetic software control and is not deployable.",
            "Holdout isolation is audited from declared report metadata; it cannot prove absence of out-of-band access.",
            "This gate validates metadata and declared artifact hashes; it does not validate future physical data quality.",
            "A preflight PASS would only mean 'ready for an operator-authorized evaluation'; it would not authorize the evaluation itself.",
        ],
        "synthetic_evidence_statement": (
            "All currently registered population, model and split identities are "
            "synthetic software controls. They cannot support a physical predictive claim."
        ),
    }

    return W16ReadinessReport(
        decision=decision,
        refusal_reasons=tuple(reasons),
        requirements=tuple(results),
        manifest=manifest,
    )
