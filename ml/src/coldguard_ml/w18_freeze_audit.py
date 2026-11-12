"""W18 no-online-tuning enforcement and freeze-drift detection (B-W18-03).

Canonical rule (Doc 04 §11.4, §58; Doc 05B §46 B-W18-03):

> Do not adjust the model or threshold after each physical run.

This module is read-only.  It snapshots the protected development identities,
detects drift against a fresh observation of the same files, verifies that the
native model bytes still match their declared hash, and evaluates a future
change-control request.  It implements no tuner, updater, retrainer,
recalibrator or threshold optimizer.

A stable development baseline is NOT an approved release freeze.  The two
statuses are always reported separately and the former is never promoted to the
latter by this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .feature_registry import FeatureRegistry
from .w18_runtime_monitor import ordered_feature_ids_sha256

DEVELOPMENT_BASELINE_UNCHANGED = "DEVELOPMENT_BASELINE_UNCHANGED"
DEVELOPMENT_BASELINE_CHANGED = "DEVELOPMENT_BASELINE_CHANGED"
DEVELOPMENT_BASELINE_NOT_DECLARED = "DEVELOPMENT_BASELINE_NOT_DECLARED"
APPROVED_RELEASE_FREEZE_UNCHANGED = "APPROVED_RELEASE_FREEZE_UNCHANGED"
APPROVED_RELEASE_FREEZE_DECLARED_UNVERIFIED = (
    "APPROVED_RELEASE_FREEZE_DECLARED_UNVERIFIED"
)
MISSING_FREEZE_RECORD = "MISSING_FREEZE_RECORD"

BASELINE_SCHEMA = "coldguard-w18-freeze-baseline-v1"
BASELINE_REQUIRED_FIELDS = (
    "authority_id",
    "evidence_sha256",
    "canonical_ref",
    "model_artifact_sha256",
)

CHANGE_ACCEPTED_PENDING_REVIEW = "CHANGE_ACCEPTED_PENDING_REVIEW"
CHANGE_ACCEPTED_REQUIRES_NEW_EVALUATION = (
    "CHANGE_ACCEPTED_REQUIRES_NEW_INDEPENDENT_EVALUATION"
)
CHANGE_REFUSED_INCOMPLETE = "CHANGE_REFUSED_INCOMPLETE"
CHANGE_REFUSED_NOT_A_NEW_IDENTITY = "CHANGE_REFUSED_NOT_A_NEW_IDENTITY"
CHANGE_REFUSED_LOCKED_TEST_REUSE = "CHANGE_REFUSED_LOCKED_TEST_REUSE"
CHANGE_REFUSED_FAKE_APPROVAL = "CHANGE_REFUSED_FAKE_APPROVAL_METADATA"
CHANGE_REFUSED_COMPARABILITY_UNDECLARED = (
    "CHANGE_REFUSED_COMPARABILITY_UNDECLARED"
)

FIELD_STATUS_UNCHANGED = "UNCHANGED"
FIELD_STATUS_CHANGED = "CHANGED"
FIELD_STATUS_NOT_DECLARED = "NOT_DECLARED"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class FreezeAuditError(ValueError):
    """The baseline cannot be established from the declared source files."""


@dataclass(frozen=True)
class ProtectedFieldSpec:
    field_id: str
    requirement: str
    canonical_ref: str


PROTECTED_FIELD_SPECS: tuple[ProtectedFieldSpec, ...] = (
    ProtectedFieldSpec(
        "model_artifact_id",
        "Model artifact/version identity.",
        "03 §92; 05B §46",
    ),
    ProtectedFieldSpec(
        "model_artifact_sha256",
        "Native model artifact SHA-256.",
        "03 §92",
    ),
    ProtectedFieldSpec(
        "model_config_sha256",
        "Model configuration SHA-256.",
        "03 §92",
    ),
    ProtectedFieldSpec(
        "feature_version",
        "Feature-registry version identity.",
        "03 §92; 05B §9",
    ),
    ProtectedFieldSpec(
        "feature_schema_hash",
        "Feature schema SHA-256.",
        "03 §92",
    ),
    ProtectedFieldSpec(
        "ordered_feature_ids_sha256",
        "Ordered feature identity hash.",
        "03 §92; 02 §60.5",
    ),
    ProtectedFieldSpec(
        "primary_horizon",
        "Primary horizon value and freeze status.",
        "03 §44, §92",
    ),
    ProtectedFieldSpec(
        "critical_target",
        "Critical-target definition and freeze status.",
        "03 §42-43, §92",
    ),
    ProtectedFieldSpec(
        "operating_threshold",
        "Operating threshold value and freeze status.",
        "03 §87, §92",
    ),
    ProtectedFieldSpec(
        "warning_persistence",
        "Warning persistence rule and freeze status.",
        "03 §88, §92",
    ),
    ProtectedFieldSpec(
        "calibration_semantics",
        "Calibration / output semantics.",
        "03 §58-60, §92",
    ),
    ProtectedFieldSpec(
        "event_matching_policy",
        "Warning-episode and event-association policy.",
        "03 §89-90",
    ),
    ProtectedFieldSpec(
        "model_library_version",
        "Runtime model library version.",
        "03 §92",
    ),
    ProtectedFieldSpec(
        "w15_model_manifest_sha256",
        "W15 model manifest bytes (all manifest-level identities).",
        "05B §46; 03 §92",
    ),
)


def _validate_approved_freeze_record(
    record: Mapping[str, Any], *, expected_model_sha: str
) -> None:
    for field in BASELINE_REQUIRED_FIELDS:
        if not record.get(field):
            raise FreezeAuditError(
                f"approved freeze record lacks required field {field!r}"
            )
    if not _is_hex64(record.get("evidence_sha256")):
        raise FreezeAuditError("approved freeze record evidence hash is invalid")
    if record.get("model_artifact_sha256") != expected_model_sha:
        raise FreezeAuditError(
            "approved freeze record does not bind the declared model artifact"
        )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


@dataclass(frozen=True)
class FreezeBaseline:
    values: Mapping[str, Any]
    model_file_sha256: str
    manifest_sha256: str
    approved_freeze_record: Mapping[str, Any] | None
    approved_freeze_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": dict(self.values),
            "model_file_sha256": self.model_file_sha256,
            "manifest_sha256": self.manifest_sha256,
            "approved_freeze_record": (
                dict(self.approved_freeze_record)
                if self.approved_freeze_record is not None
                else None
            ),
            "approved_freeze_status": self.approved_freeze_status,
            "development_only": True,
        }


def build_freeze_baseline(
    *,
    model_manifest: Mapping[str, Any],
    manifest_path: str | Path,
    registry: FeatureRegistry,
    config: Any,
    model_path: str | Path,
) -> FreezeBaseline:
    """Snapshot the protected development identities from actual files."""
    ordered = tuple(model_manifest["ordered_feature_ids"])
    computed_order_sha = ordered_feature_ids_sha256(ordered)
    problems: list[str] = []
    if computed_order_sha != model_manifest.get("ordered_feature_ids_sha256"):
        problems.append("ORDERED_FEATURE_IDS_HASH_INVALID")
    if model_manifest.get("feature_schema_hash") != registry.schema_sha256:
        problems.append("FEATURE_SCHEMA_BINDING_BROKEN")
    if model_manifest.get("model_config_hash") != config.config_sha256:
        problems.append("MODEL_CONFIG_BINDING_BROKEN")
    model_file = Path(model_path)
    if not model_file.is_file():
        problems.append("MODEL_FILE_MISSING")
        actual_model_sha = ""
    else:
        actual_model_sha = _sha256_file(model_file)
        if actual_model_sha != model_manifest.get("model_artifact_sha256"):
            problems.append("MODEL_BYTES_CHANGED_WITHOUT_IDENTITY_UPDATE")
    if problems:
        raise FreezeAuditError(
            "freeze baseline cannot be established: " + ",".join(sorted(problems))
        )
    raw = config.raw
    label = raw.get("label") or {}
    baseline = raw.get("baseline") or {}
    episode = (baseline.get("episode_policy") or {}).get("status")
    association = (baseline.get("association_policy") or {}).get("status")
    values: dict[str, Any] = {
        "model_artifact_id": model_manifest["artifact_id"],
        "model_artifact_sha256": model_manifest["model_artifact_sha256"],
        "model_config_sha256": model_manifest["model_config_hash"],
        "feature_version": registry.feature_version,
        "feature_schema_hash": registry.schema_sha256,
        "ordered_feature_ids_sha256": computed_order_sha,
        "primary_horizon": {
            "horizon_s": model_manifest["horizon_s"],
            "horizon_status": model_manifest["horizon_status"],
            "config_horizon_s": label.get("horizon_s"),
        },
        "critical_target": {
            "target_spec_version": model_manifest["target_spec_version"],
            "target_status": model_manifest["target_status"],
            "config_target_status": label.get("status"),
            "boundary_c": label.get("boundary_c"),
        },
        "operating_threshold": {
            "value": model_manifest["operating_threshold"],
            "status": model_manifest["operating_threshold_status"],
            "config_value": config.risk_threshold,
        },
        "warning_persistence": {
            "status": model_manifest["warning_persistence_status"],
            "k": model_manifest.get("warning_persistence_k"),
        },
        "calibration_semantics": {
            "status": model_manifest["calibration_status"],
            "score_semantics": model_manifest["score_semantics"],
            "config_status": config.calibration_status,
        },
        "event_matching_policy": {
            "episode_status": episode,
            "association_status": association,
        },
        "model_library_version": model_manifest["model_library_version"],
        "w15_model_manifest_sha256": _sha256_file(Path(manifest_path)),
    }
    approved_record = model_manifest.get("approved_freeze_record")
    if approved_record is not None:
        if not isinstance(approved_record, Mapping):
            raise FreezeAuditError(
                "approved_freeze_record must be an object when present"
            )
        _validate_approved_freeze_record(
            approved_record,
            expected_model_sha=model_manifest["model_artifact_sha256"],
        )
    approved_status = (
        APPROVED_RELEASE_FREEZE_DECLARED_UNVERIFIED
        if approved_record is not None
        else MISSING_FREEZE_RECORD
    )
    return FreezeBaseline(
        values=values,
        model_file_sha256=actual_model_sha,
        manifest_sha256=_sha256_file(Path(manifest_path)),
        approved_freeze_record=dict(approved_record) if approved_record else None,
        approved_freeze_status=approved_status,
    )


@dataclass(frozen=True)
class FreezeComparison:
    development_status: str
    approved_status: str
    drift_fields: tuple[str, ...]
    field_rows: tuple[Mapping[str, Any], ...]
    issues: tuple[str, ...]
    identity_reused: bool
    development_unchanged_implies_release_freeze: bool = False

    @property
    def drift_detected(self) -> bool:
        return bool(self.drift_fields or self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "development_status": self.development_status,
            "approved_status": self.approved_status,
            "drift_detected": self.drift_detected,
            "drift_fields": list(self.drift_fields),
            "field_rows": [dict(row) for row in self.field_rows],
            "issues": list(self.issues),
            "identity_reused": self.identity_reused,
            "development_unchanged_implies_release_freeze": (
                self.development_unchanged_implies_release_freeze
            ),
        }


def observe_protected_values(
    *,
    registry: FeatureRegistry,
    config: Any,
    model_manifest: Mapping[str, Any],
    manifest_path: str | Path,
    model_path: str | Path,
    installed_library_version: str | None = None,
) -> dict[str, Any]:
    """Compute the protected values from the actual current files."""
    if installed_library_version is None:
        import xgboost

        installed_library_version = xgboost.__version__
    raw = config.raw
    label = raw.get("label") or {}
    baseline_cfg = raw.get("baseline") or {}
    episode = (baseline_cfg.get("episode_policy") or {}).get("status")
    association = (baseline_cfg.get("association_policy") or {}).get("status")
    return {
        "model_artifact_id": model_manifest["artifact_id"],
        "model_artifact_sha256": _sha256_file(Path(model_path)),
        "model_config_sha256": config.config_sha256,
        "feature_version": registry.feature_version,
        "feature_schema_hash": registry.schema_sha256,
        "ordered_feature_ids_sha256": ordered_feature_ids_sha256(
            config.feature_policy.allowlist
        ),
        "primary_horizon": {
            "horizon_s": model_manifest["horizon_s"],
            "horizon_status": model_manifest["horizon_status"],
            "config_horizon_s": label.get("horizon_s"),
        },
        "critical_target": {
            "target_spec_version": model_manifest["target_spec_version"],
            "target_status": model_manifest["target_status"],
            "config_target_status": label.get("status"),
            "boundary_c": label.get("boundary_c"),
        },
        "operating_threshold": {
            "value": model_manifest["operating_threshold"],
            "status": model_manifest["operating_threshold_status"],
            "config_value": config.risk_threshold,
        },
        "warning_persistence": {
            "status": model_manifest["warning_persistence_status"],
            "k": model_manifest.get("warning_persistence_k"),
        },
        "calibration_semantics": {
            "status": model_manifest["calibration_status"],
            "score_semantics": model_manifest["score_semantics"],
            "config_status": config.calibration_status,
        },
        "event_matching_policy": {
            "episode_status": episode,
            "association_status": association,
        },
        "model_library_version": installed_library_version,
        "w15_model_manifest_sha256": _sha256_file(Path(manifest_path)),
    }


def load_pinned_baseline(path: str | Path) -> FreezeBaseline:
    """Load the committed development-baseline snapshot (an input, not output)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise FreezeAuditError("pinned baseline root must be an object")
    if payload.get("schema") != BASELINE_SCHEMA:
        raise FreezeAuditError("pinned baseline schema mismatch")
    values = payload.get("values")
    if not isinstance(values, Mapping):
        raise FreezeAuditError("pinned baseline values must be an object")
    missing = [
        spec.field_id
        for spec in PROTECTED_FIELD_SPECS
        if spec.field_id not in values
    ]
    if missing:
        raise FreezeAuditError(
            "pinned baseline is missing protected fields: " + ",".join(missing)
        )
    approved_record = payload.get("approved_freeze_record")
    if approved_record is not None:
        if not isinstance(approved_record, Mapping):
            raise FreezeAuditError("pinned approved freeze record must be an object")
        _validate_approved_freeze_record(
            approved_record,
            expected_model_sha=str(values["model_artifact_sha256"]),
        )
    model_file_sha256 = str(payload.get("model_file_sha256") or "")
    manifest_sha256 = str(payload.get("manifest_sha256") or "")
    if not _is_hex64(model_file_sha256) or not _is_hex64(manifest_sha256):
        raise FreezeAuditError("pinned baseline file hashes are invalid")
    if values.get("w15_model_manifest_sha256") != manifest_sha256:
        raise FreezeAuditError("pinned baseline manifest hash is inconsistent")
    approved_status = (
        APPROVED_RELEASE_FREEZE_DECLARED_UNVERIFIED
        if approved_record is not None
        else MISSING_FREEZE_RECORD
    )
    return FreezeBaseline(
        values={field: values[field] for field in values},
        model_file_sha256=model_file_sha256,
        manifest_sha256=manifest_sha256,
        approved_freeze_record=dict(approved_record) if approved_record else None,
        approved_freeze_status=approved_status,
    )


def compare_freeze_state(
    baseline: FreezeBaseline,
    observed_values: Mapping[str, Any] | None = None,
) -> FreezeComparison:
    """Compare a pinned baseline snapshot with a fresh file observation."""
    if observed_values is None:
        observed_values = baseline.values
    spec_ids = [spec.field_id for spec in PROTECTED_FIELD_SPECS]
    missing_baseline = [field for field in spec_ids if field not in baseline.values]
    if missing_baseline:
        raise FreezeAuditError(
            "baseline is missing protected fields: " + ",".join(missing_baseline)
        )
    rows: list[dict[str, Any]] = []
    drift_fields: list[str] = []
    issues: list[str] = []
    for spec in PROTECTED_FIELD_SPECS:
        baseline_value = baseline.values[spec.field_id]
        observed_value = observed_values.get(spec.field_id)
        if observed_value is None:
            status = FIELD_STATUS_CHANGED
            drift_fields.append(spec.field_id)
            issues.append(f"{spec.field_id}: observed value missing")
        elif _canonical_sha256(baseline_value) != _canonical_sha256(observed_value):
            status = FIELD_STATUS_CHANGED
            drift_fields.append(spec.field_id)
        else:
            status = FIELD_STATUS_UNCHANGED
        rows.append(
            {
                "field_id": spec.field_id,
                "baseline_value": baseline_value,
                "observed_value": observed_value,
                "status": status,
                "development_only": True,
                "approved_value": None,
                "approved_freeze_status": (
                    baseline.approved_freeze_status
                ),
                "canonical_ref": spec.canonical_ref,
            }
        )
    identity_reused = (
        observed_values.get("model_artifact_sha256")
        != baseline.values.get("model_artifact_sha256")
        and observed_values.get("model_artifact_id")
        == baseline.values.get("model_artifact_id")
    )
    if identity_reused:
        issues.append("MODEL_IDENTITY_REUSED_FOR_NEW_BYTES")
    development_status = (
        DEVELOPMENT_BASELINE_CHANGED
        if drift_fields or issues
        else DEVELOPMENT_BASELINE_UNCHANGED
    )
    return FreezeComparison(
        development_status=development_status,
        approved_status=baseline.approved_freeze_status,
        drift_fields=tuple(sorted(set(drift_fields))),
        field_rows=tuple(rows),
        issues=tuple(sorted(set(issues))),
        identity_reused=identity_reused,
    )


def verify_model_file_binding(
    baseline: FreezeBaseline, model_path: str | Path
) -> dict[str, Any]:
    """Re-hash the native model file against the recorded baseline bytes."""
    path = Path(model_path)
    if not path.is_file():
        return {
            "matches": False,
            "reason_code": "MODEL_FILE_MISSING",
            "observed_sha256": None,
            "expected_sha256": baseline.model_file_sha256,
        }
    observed = _sha256_file(path)
    matches = observed == baseline.model_file_sha256
    return {
        "matches": matches,
        "reason_code": None if matches else "MODEL_BYTES_CHANGED_WITHOUT_IDENTITY_UPDATE",
        "observed_sha256": observed,
        "expected_sha256": baseline.model_file_sha256,
    }


def apply_declared_change(
    baseline: FreezeBaseline, changes: Mapping[str, Any]
) -> dict[str, Any]:
    """Helper for tests and audits: a declared observed snapshot with changes."""
    observed = json.loads(json.dumps(baseline.values, sort_keys=True))
    for field_id, value in changes.items():
        if field_id not in observed:
            raise FreezeAuditError(f"unknown protected field {field_id!r}")
        observed[field_id] = value
    return observed


@dataclass(frozen=True)
class ChangeDecision:
    decision: str
    refusal_reasons: tuple[str, ...]
    required_followups: tuple[str, ...]
    approval_effect: str = "NONE_B_W18_READ_ONLY_ASSESSMENT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "refusal_reasons": list(self.refusal_reasons),
            "required_followups": list(self.required_followups),
            "approval_effect": self.approval_effect,
        }


CHANGE_REQUIRED_FIELDS = (
    "artifact_id",
    "model_artifact_sha256",
    "model_config_sha256",
    "feature_schema_hash",
    "ordered_feature_ids_sha256",
    "reason",
    "owner",
    "affected_evidence",
    "evaluation_implications",
    "review_gate",
)


def assess_change_request(
    request: Mapping[str, Any],
    *,
    baseline: FreezeBaseline,
    locked_test_exposed: bool,
) -> ChangeDecision:
    """Evaluate a future model-change request without granting approval."""
    if not isinstance(request, Mapping):
        raise FreezeAuditError("change request must be an object")
    missing = [
        field
        for field in CHANGE_REQUIRED_FIELDS
        if request.get(field) in (None, "", [], {})
    ]
    if missing:
        return ChangeDecision(
            decision=CHANGE_REFUSED_INCOMPLETE,
            refusal_reasons=(f"MISSING_CHANGE_CONTROL_FIELD:{','.join(sorted(missing))}",),
            required_followups=(),
        )
    affected = request.get("affected_evidence")
    if not isinstance(affected, list) or any(
        not isinstance(item, str) or not item for item in affected
    ):
        return ChangeDecision(
            decision=CHANGE_REFUSED_INCOMPLETE,
            refusal_reasons=("AFFECTED_EVIDENCE_INVALID",),
            required_followups=(),
        )
    for field in (
        "model_artifact_sha256",
        "model_config_sha256",
        "feature_schema_hash",
        "ordered_feature_ids_sha256",
    ):
        if not _is_hex64(request.get(field)):
            return ChangeDecision(
                decision=CHANGE_REFUSED_INCOMPLETE,
                refusal_reasons=(f"INVALID_IDENTITY_FIELD:{field}",),
                required_followups=(),
            )
    new_model_sha = request["model_artifact_sha256"]
    same_model = new_model_sha == baseline.values["model_artifact_sha256"]
    same_artifact = request["artifact_id"] == baseline.values["model_artifact_id"]
    if same_model and same_artifact:
        return ChangeDecision(
            decision=CHANGE_REFUSED_NOT_A_NEW_IDENTITY,
            refusal_reasons=("ARTIFACT_ID_AND_MODEL_SHA_UNCHANGED",),
            required_followups=(
                "issue a new artifact/version identity before any change is reviewed",
            ),
        )
    review_gate = request.get("review_gate")
    if not isinstance(review_gate, Mapping):
        return ChangeDecision(
            decision=CHANGE_REFUSED_INCOMPLETE,
            refusal_reasons=("REVIEW_GATE_INVALID",),
            required_followups=(),
        )
    review_status = review_gate.get("status")
    if review_status not in ("PENDING_REVIEW", "APPROVED_BY_AUTHORITY"):
        return ChangeDecision(
            decision=CHANGE_REFUSED_INCOMPLETE,
            refusal_reasons=("REVIEW_GATE_STATUS_INVALID",),
            required_followups=(),
        )
    if review_status == "APPROVED_BY_AUTHORITY":
        if not review_gate.get("reviewer") or not _is_hex64(
            review_gate.get("evidence_sha256")
        ):
            return ChangeDecision(
                decision=CHANGE_REFUSED_FAKE_APPROVAL,
                refusal_reasons=("APPROVAL_WITHOUT_BOUND_EVIDENCE",),
                required_followups=(
                    "a real approval requires a reviewer identity and bound evidence hash",
                ),
            )
    comparability = request.get("comparability")
    if locked_test_exposed:
        if comparability not in (
            "PRIOR_TESTS_COMPARABLE",
            "REQUIRES_NEW_INDEPENDENT_EVALUATION",
        ):
            return ChangeDecision(
                decision=CHANGE_REFUSED_COMPARABILITY_UNDECLARED,
                refusal_reasons=("POST_LOCKED_TEST_COMPARABILITY_NOT_DECLARED",),
                required_followups=(
                    "declare whether prior locked-test results remain comparable",
                ),
            )
        if comparability == "PRIOR_TESTS_COMPARABLE":
            return ChangeDecision(
                decision=CHANGE_REFUSED_LOCKED_TEST_REUSE,
                refusal_reasons=("POST_TEST_REVISION_REUSES_LOCKED_TEST",),
                required_followups=(
                    "collect new independent data; the old locked test is no longer untouched",
                ),
            )
    if comparability == "REQUIRES_NEW_INDEPENDENT_EVALUATION":
        return ChangeDecision(
            decision=CHANGE_ACCEPTED_REQUIRES_NEW_EVALUATION,
            refusal_reasons=(),
            required_followups=(
                "new independent evaluation population",
                "new freeze and release authorization",
            ),
        )
    return ChangeDecision(
        decision=CHANGE_ACCEPTED_PENDING_REVIEW,
        refusal_reasons=(),
        required_followups=(
            "review by the owning authority",
            "explicit comparability decision before reusing any prior evidence",
        ),
    )
