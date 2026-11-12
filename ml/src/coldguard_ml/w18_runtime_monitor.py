"""W18 read-only model runtime monitoring (B-W18-01).

The monitor inspects a *declared* prediction record and decides whether it
matches the expected W15 model/feature/runtime identity.  It is read-only and
has no inference-time authority: it cannot deploy, register, dispatch, tune or
authorize anything.

Canonical anchors (Doc 05B §46 B-W18-01, Doc 04 §33, Doc 02 §4-5, Doc 03 §92):

* artifact hash, feature version, threshold and horizon must be identifiable;
* a hash match proves byte identity only, never release approval;
* the frozen development candidate is ``NON_DEPLOYABLE_CANDIDATE`` and every
  policy field (target, horizon, threshold, persistence) is unfrozen;
* a refused input may never produce a trusted risk score.

The result keeps four questions separate: identity match, evidence quality,
scientific release eligibility and physical authorization.  There is no single
``healthy`` flag.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .feature_registry import FeatureRegistry
from .w15_artifact import (
    ARTIFACT_ID,
    ENGINEERING_REFERENCE_HORIZON,
    ILLUSTRATIVE_THRESHOLD,
    NON_DEPLOYABLE,
    PERSISTENCE_NOT_FROZEN,
    RISK_SCORE_ONLY,
    SYNTHETIC_EVIDENCE_CLASS,
)

W18_MONITOR_VERSION = "coldguard-w18-runtime-monitor-v1"

MONITOR_SOFTWARE_VALID = "MONITOR_SOFTWARE_VALID"
REFUSED_MODEL_IDENTITY = "REFUSED_MODEL_IDENTITY"
REFUSED_FEATURE_IDENTITY = "REFUSED_FEATURE_IDENTITY"
REFUSED_POLICY_UNFROZEN = "REFUSED_POLICY_UNFROZEN"
REFUSED_STALE_INPUT = "REFUSED_STALE_INPUT"
REFUSED_UNTRUSTED_INPUT = "REFUSED_UNTRUSTED_INPUT"
REFUSED_EVIDENCE_CLASS = "REFUSED_EVIDENCE_CLASS"
REFUSED_RELEASE_AUTHORIZATION = "REFUSED_RELEASE_AUTHORIZATION"
REFUSED_PREDICTION_SEMANTICS = "REFUSED_PREDICTION_SEMANTICS"
REFUSED_TEMPORAL_ORDER = "REFUSED_TEMPORAL_ORDER"
DISPOSITIONS = (
    MONITOR_SOFTWARE_VALID,
    REFUSED_MODEL_IDENTITY,
    REFUSED_FEATURE_IDENTITY,
    REFUSED_POLICY_UNFROZEN,
    REFUSED_STALE_INPUT,
    REFUSED_UNTRUSTED_INPUT,
    REFUSED_EVIDENCE_CLASS,
    REFUSED_RELEASE_AUTHORIZATION,
    REFUSED_PREDICTION_SEMANTICS,
    REFUSED_TEMPORAL_ORDER,
)
DISPOSITION_PRECEDENCE = (
    REFUSED_MODEL_IDENTITY,
    REFUSED_FEATURE_IDENTITY,
    REFUSED_EVIDENCE_CLASS,
    REFUSED_RELEASE_AUTHORIZATION,
    REFUSED_PREDICTION_SEMANTICS,
    REFUSED_POLICY_UNFROZEN,
    REFUSED_TEMPORAL_ORDER,
    REFUSED_STALE_INPUT,
    REFUSED_UNTRUSTED_INPUT,
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_NOT_VERIFIED = "NOT_VERIFIED"

DIMENSION_MODEL = "MODEL_IDENTITY"
DIMENSION_FEATURE = "FEATURE_IDENTITY"
DIMENSION_PREDICTION = "PREDICTION_SEMANTICS"
DIMENSION_FRESHNESS = "FRESHNESS"

RUNTIME_FRESHNESS_POLICY_PENDING = "RUNTIME_FRESHNESS_POLICY_PENDING_C_D"
WARNING_RULE_STATUS = "SYNTHETIC_ILLUSTRATIVE"
WARNING_RULE_SOURCE = "W15_MANIFEST_OPERATING_THRESHOLD"
WARNING_WITHHELD = "WITHHELD_ANCHOR_REFUSED"
WARNING_TRIGGERED = "TRIGGERED_SYNTHETIC_ILLUSTRATIVE"
WARNING_NOT_TRIGGERED = "NOT_TRIGGERED_SYNTHETIC_ILLUSTRATIVE"
WARNING_STATUSES = (WARNING_TRIGGERED, WARNING_NOT_TRIGGERED, WARNING_WITHHELD)

FRESH = "FRESH"
READY_FOR_SOFTWARE_REPLAY = "READY_FOR_SOFTWARE_REPLAY"
REFUSED_STALE = "REFUSED_STALE_INPUT"
REFUSED_UNTRUSTED = "REFUSED_UNTRUSTED_INPUT"
REFUSED_TEMPORAL = "REFUSED_TEMPORAL_ORDER"

PHYSICAL_EVIDENCE_CLASSES = frozenset(
    {"MEASURED_PHYSICAL_DATA", "REAL_PHYSICAL_EVIDENCE"}
)
RELEASE_ELIGIBLE_CLASSES = frozenset(
    {"RELEASE_APPROVED_CANDIDATE", "APPROVED_RELEASE_CANDIDATE"}
)
FROZEN_CLAIM_VALUES = frozenset(
    {"FROZEN", "FROZEN_APPROVED", "APPROVED", "RELEASE_APPROVED"}
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class MonitorError(ValueError):
    """The expected identity contract itself is broken."""


class MonitorRecordError(MonitorError):
    """A declared record is structurally malformed and cannot be monitored."""


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def ordered_feature_ids_sha256(feature_ids: Sequence[str]) -> str:
    """The W15/W16 recipe: sha256 of json.dumps(list(ids)) default separators."""
    return hashlib.sha256(json.dumps(list(feature_ids)).encode("utf-8")).hexdigest()


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _rule_string(threshold: float) -> str:
    return f"risk_score >= {threshold:g}"


@dataclass(frozen=True)
class PolicyExpectation:
    target_status: str
    horizon_s: float
    horizon_status: str
    operating_threshold: float
    operating_threshold_status: str
    warning_persistence_status: str
    warning_rule_status: str
    warning_rule_source: str
    calibration_status: str
    runtime_freshness_policy_status: str


@dataclass(frozen=True)
class ExpectedRuntimeIdentity:
    artifact_id: str
    model_artifact_sha256: str
    model_config_sha256: str
    model_library_version: str
    feature_version: str
    feature_schema_sha256: str
    ordered_feature_ids: tuple[str, ...]
    ordered_feature_ids_sha256: str
    feature_count: int
    score_semantics: str
    calibration_status: str
    target_spec_version: str
    target_status: str
    horizon_s: float
    horizon_status: str
    operating_threshold: float
    operating_threshold_status: str
    warning_persistence_status: str
    data_evidence_class: str
    release_eligibility: str

    def policy_expectation(self) -> PolicyExpectation:
        return PolicyExpectation(
            target_status=self.target_status,
            horizon_s=self.horizon_s,
            horizon_status=self.horizon_status,
            operating_threshold=self.operating_threshold,
            operating_threshold_status=self.operating_threshold_status,
            warning_persistence_status=self.warning_persistence_status,
            warning_rule_status=WARNING_RULE_STATUS,
            warning_rule_source=WARNING_RULE_SOURCE,
            calibration_status=self.calibration_status,
            runtime_freshness_policy_status=RUNTIME_FRESHNESS_POLICY_PENDING,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.__dict__)
        payload["ordered_feature_ids"] = list(self.ordered_feature_ids)
        return payload


def expected_runtime_identity(
    *,
    model_manifest: Mapping[str, Any],
    registry: FeatureRegistry,
    config: Any,
    installed_library_version: str | None = None,
) -> ExpectedRuntimeIdentity:
    """Build the expected identity from actual authoritative files.

    Refuses (rather than adapting) when the W15 development contract has moved:
    a monitor that silently follows a changed baseline could bless a drift.
    """
    if installed_library_version is None:
        import xgboost

        installed_library_version = xgboost.__version__
    ordered = tuple(model_manifest["ordered_feature_ids"])
    problems: list[str] = []
    if model_manifest.get("data_evidence_class") != SYNTHETIC_EVIDENCE_CLASS:
        problems.append("EXPECTED_EVIDENCE_CLASS_CHANGED")
    if model_manifest.get("release_eligibility") != NON_DEPLOYABLE:
        problems.append("EXPECTED_RELEASE_ELIGIBILITY_CHANGED")
    if model_manifest.get("score_semantics") != "risk_score":
        problems.append("EXPECTED_SCORE_SEMANTICS_CHANGED")
    if model_manifest.get("calibration_status") != RISK_SCORE_ONLY:
        problems.append("EXPECTED_CALIBRATION_CHANGED")
    if model_manifest.get("horizon_status") != ENGINEERING_REFERENCE_HORIZON:
        problems.append("EXPECTED_HORIZON_STATUS_CHANGED")
    if (
        model_manifest.get("operating_threshold_status")
        != ILLUSTRATIVE_THRESHOLD
    ):
        problems.append("EXPECTED_THRESHOLD_STATUS_CHANGED")
    if model_manifest.get("warning_persistence_status") != PERSISTENCE_NOT_FROZEN:
        problems.append("EXPECTED_PERSISTENCE_STATUS_CHANGED")
    if model_manifest.get("feature_schema_hash") != registry.schema_sha256:
        problems.append("EXPECTED_FEATURE_SCHEMA_CHANGED")
    if model_manifest.get("model_config_hash") != config.config_sha256:
        problems.append("EXPECTED_CONFIG_CHANGED")
    if ordered != tuple(config.feature_policy.allowlist):
        problems.append("EXPECTED_ORDERED_FEATURES_CHANGED")
    if ordered_feature_ids_sha256(ordered) != model_manifest.get(
        "ordered_feature_ids_sha256"
    ):
        problems.append("EXPECTED_ORDERED_FEATURE_HASH_INVALID")
    if installed_library_version != model_manifest.get("model_library_version"):
        problems.append("EXPECTED_LIBRARY_VERSION_CHANGED")
    if model_manifest.get("artifact_id") != ARTIFACT_ID:
        problems.append("EXPECTED_ARTIFACT_ID_CHANGED")
    if problems:
        raise MonitorError(
            "expected runtime identity contract is broken: "
            + ",".join(sorted(problems))
        )
    return ExpectedRuntimeIdentity(
        artifact_id=str(model_manifest["artifact_id"]),
        model_artifact_sha256=str(model_manifest["model_artifact_sha256"]),
        model_config_sha256=str(model_manifest["model_config_hash"]),
        model_library_version=str(model_manifest["model_library_version"]),
        feature_version=str(model_manifest["feature_version"]),
        feature_schema_sha256=str(model_manifest["feature_schema_hash"]),
        ordered_feature_ids=ordered,
        ordered_feature_ids_sha256=str(
            model_manifest["ordered_feature_ids_sha256"]
        ),
        feature_count=len(ordered),
        score_semantics=str(model_manifest["score_semantics"]),
        calibration_status=str(model_manifest["calibration_status"]),
        target_spec_version=str(model_manifest["target_spec_version"]),
        target_status=str(model_manifest["target_status"]),
        horizon_s=float(model_manifest["horizon_s"]),
        horizon_status=str(model_manifest["horizon_status"]),
        operating_threshold=float(model_manifest["operating_threshold"]),
        operating_threshold_status=str(
            model_manifest["operating_threshold_status"]
        ),
        warning_persistence_status=str(
            model_manifest["warning_persistence_status"]
        ),
        data_evidence_class=str(model_manifest["data_evidence_class"]),
        release_eligibility=str(model_manifest["release_eligibility"]),
    )


def policy_expectation_from_w17_header(
    header: Mapping[str, Any], expected: ExpectedRuntimeIdentity
) -> PolicyExpectation:
    """Validate a W17 trace header against the expected development policy."""
    rule = header.get("warning_rule")
    if not isinstance(rule, Mapping):
        raise MonitorError("W17 trace header has no warning_rule block")
    if rule.get("threshold") != expected.operating_threshold:
        raise MonitorError("W17 trace header threshold moved from the W15 manifest")
    if rule.get("status") != WARNING_RULE_STATUS:
        raise MonitorError("W17 trace header warning rule is not illustrative")
    if rule.get("persistence") != expected.warning_persistence_status:
        raise MonitorError("W17 trace header persistence status changed")
    if rule.get("source") != WARNING_RULE_SOURCE:
        raise MonitorError("W17 trace header warning-rule provenance changed")
    parameters = header.get("freshness_parameters")
    if not isinstance(parameters, Mapping) or parameters.get(
        "class"
    ) != "SYNTHETIC_ILLUSTRATIVE_TEST_PARAMETER":
        raise MonitorError("W17 trace header freshness parameters are not synthetic")
    if header.get("freshness_policy_status") != RUNTIME_FRESHNESS_POLICY_PENDING:
        raise MonitorError("W17 runtime freshness policy is no longer pending")
    return expected.policy_expectation()


@dataclass(frozen=True)
class MonitorCheck:
    check_id: str
    dimension: str
    requirement: str
    status: str
    observed: str
    reason_code: str | None = None
    disposition: str | None = None
    canonical_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "dimension": self.dimension,
            "requirement": self.requirement,
            "status": self.status,
            "observed": self.observed,
            "reason_code": self.reason_code,
            "canonical_ref": self.canonical_ref,
        }


@dataclass(frozen=True)
class MonitorResult:
    record_key: str
    verdict: str
    identity_match: bool
    evidence_quality: bool
    scientific_release_eligibility: bool
    physical_authorization: bool
    release_claim: bool
    control_claim: bool
    checks: tuple[MonitorCheck, ...]
    refusal_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_key": self.record_key,
            "verdict": self.verdict,
            "identity_match": self.identity_match,
            "evidence_quality": self.evidence_quality,
            "scientific_release_eligibility": self.scientific_release_eligibility,
            "physical_authorization": self.physical_authorization,
            "release_claim": self.release_claim,
            "control_claim": self.control_claim,
            "refusal_reasons": list(self.refusal_reasons),
            "checks": [check.to_dict() for check in self.checks],
        }


def monitor_runtime_record(
    record: Mapping[str, Any],
    *,
    expected: ExpectedRuntimeIdentity,
    policy: PolicyExpectation | None = None,
) -> MonitorResult:
    """Monitor one declared prediction record against the expected identity."""
    if not isinstance(record, Mapping):
        raise MonitorRecordError("runtime record is not a mapping")
    features = record.get("features")
    if not isinstance(features, list) or not features:
        raise MonitorRecordError("runtime record features must be a non-empty list")
    model = record.get("model")
    if model is not None and not isinstance(model, Mapping):
        raise MonitorRecordError("runtime record model block must be a mapping")
    model_block: Mapping[str, Any] = model or {}
    freshness = record.get("freshness")
    if not isinstance(freshness, Mapping):
        raise MonitorRecordError("runtime record freshness block must be a mapping")
    policy = policy or expected.policy_expectation()

    checks: list[MonitorCheck] = []
    release_claim = False
    control_claim = False

    def add(
        check_id: str,
        dimension: str,
        requirement: str,
        status: str,
        observed: str,
        reason: str | None = None,
        disposition: str | None = None,
        canonical_ref: str = "",
    ) -> None:
        checks.append(
            MonitorCheck(
                check_id=check_id,
                dimension=dimension,
                requirement=requirement,
                status=status,
                observed=observed,
                reason_code=reason,
                disposition=disposition,
                canonical_ref=canonical_ref,
            )
        )

    run_id = str(record.get("run_id") or "")
    boot_id = str(record.get("boot_id") or "")
    prediction_id = str(record.get("prediction_id") or "")
    seq = record.get("seq")
    record_key = f"{run_id}/{boot_id}/{prediction_id or 'NO-PREDICTION'}"
    if not run_id or not boot_id or not prediction_id or not isinstance(seq, int):
        add(
            "W18-RM-ID-00",
            DIMENSION_MODEL,
            "Record identity fields (run_id, boot_id, seq, prediction_id) must be present.",
            STATUS_FAIL,
            f"run_id={run_id or 'MISSING'}, boot_id={boot_id or 'MISSING'}, "
            f"prediction_id={prediction_id or 'MISSING'}, seq={seq!r}",
            "RECORD_IDENTITY_MISSING",
            REFUSED_MODEL_IDENTITY,
            "02 §4.2; 05B §46",
        )

    # ---- Model identity -----------------------------------------------------
    artifact_id = str(model_block.get("artifact_id") or "")
    model_sha = str(model_block.get("model_artifact_sha256") or "")
    config_sha = model_block.get("model_config_sha256")
    library_version = str(model_block.get("model_library_version") or "")
    declared_config_sha = str(config_sha or "")
    if artifact_id != expected.artifact_id:
        add(
            "W18-RM-MD-01",
            DIMENSION_MODEL,
            "Exact model artifact ID must match the frozen development candidate.",
            STATUS_FAIL,
            f"declared={artifact_id or 'MISSING'}",
            "MODEL_ARTIFACT_ID_MISMATCH",
            REFUSED_MODEL_IDENTITY,
            "05B §46; 03 §92",
        )
    else:
        add(
            "W18-RM-MD-01",
            DIMENSION_MODEL,
            "Exact model artifact ID must match the frozen development candidate.",
            STATUS_PASS,
            artifact_id,
            None,
            None,
            "05B §46; 03 §92",
        )
    if model_sha != expected.model_artifact_sha256:
        add(
            "W18-RM-MD-02",
            DIMENSION_MODEL,
            "Native model SHA-256 must match the W15 artifact manifest.",
            STATUS_FAIL,
            f"declared={model_sha[:16] or 'MISSING'}",
            "MODEL_SHA256_MISMATCH" if _is_hex64(model_sha) else "MODEL_SHA256_MISSING",
            REFUSED_MODEL_IDENTITY,
            "03 §92; artifact-convention §4-5",
        )
    else:
        add(
            "W18-RM-MD-02",
            DIMENSION_MODEL,
            "Native model SHA-256 must match the W15 artifact manifest.",
            STATUS_PASS,
            model_sha,
            None,
            None,
            "03 §92; artifact-convention §4-5",
        )
    if declared_config_sha and declared_config_sha != expected.model_config_sha256:
        add(
            "W18-RM-MD-03",
            DIMENSION_MODEL,
            "Declared model configuration SHA-256 must match the W15 manifest.",
            STATUS_FAIL,
            f"declared={declared_config_sha[:16]}",
            "MODEL_CONFIG_SHA256_MISMATCH",
            REFUSED_MODEL_IDENTITY,
            "03 §92",
        )
    else:
        add(
            "W18-RM-MD-03",
            DIMENSION_MODEL,
            "Declared model configuration SHA-256 must match the W15 manifest.",
            STATUS_PASS,
            (
                declared_config_sha
                if declared_config_sha
                else "record omits config identity; source manifest/config binding verified"
            ),
            None,
            None,
            "03 §92",
        )
    if library_version != expected.model_library_version:
        add(
            "W18-RM-MD-04",
            DIMENSION_MODEL,
            "Model library version must match the artifact manifest.",
            STATUS_FAIL,
            f"declared={library_version or 'MISSING'}",
            "MODEL_LIBRARY_VERSION_MISMATCH",
            REFUSED_MODEL_IDENTITY,
            "03 §92",
        )
    else:
        add(
            "W18-RM-MD-04",
            DIMENSION_MODEL,
            "Model library version must match the artifact manifest.",
            STATUS_PASS,
            library_version,
            None,
            None,
            "03 §92",
        )
    release_eligibility = str(model_block.get("release_eligibility") or "")
    if (
        release_eligibility in RELEASE_ELIGIBLE_CLASSES
        or model_block.get("registered_for_operation") is True
        or model_block.get("deployed") is True
    ):
        release_claim = True
        add(
            "W18-RM-MD-05",
            DIMENSION_MODEL,
            "A synthetic development candidate may not claim release authorization.",
            STATUS_FAIL,
            f"release_eligibility={release_eligibility or 'MISSING'}, "
            f"registered={model_block.get('registered_for_operation')!r}, "
            f"deployed={model_block.get('deployed')!r}",
            "RELEASE_AUTHORIZATION_CLAIMED",
            REFUSED_RELEASE_AUTHORIZATION,
            "05B §46; 04 §31",
        )
    else:
        add(
            "W18-RM-MD-05",
            DIMENSION_MODEL,
            "A synthetic development candidate may not claim release authorization.",
            STATUS_PASS,
            f"release_eligibility={release_eligibility or 'MISSING'}, not registered, not deployed",
            None,
            None,
            "05B §46; 04 §31",
        )
    if release_eligibility != expected.release_eligibility:
        add(
            "W18-RM-MD-06",
            DIMENSION_MODEL,
            "Declared release eligibility must equal the artifact manifest value.",
            STATUS_FAIL,
            f"declared={release_eligibility or 'MISSING'}",
            "RELEASE_ELIGIBILITY_MISMATCH",
            (
                REFUSED_RELEASE_AUTHORIZATION
                if release_eligibility in RELEASE_ELIGIBLE_CLASSES
                else REFUSED_MODEL_IDENTITY
            ),
            "05B §46",
        )
    else:
        add(
            "W18-RM-MD-06",
            DIMENSION_MODEL,
            "Declared release eligibility must equal the artifact manifest value.",
            STATUS_PASS,
            release_eligibility,
            None,
            None,
            "05B §46",
        )

    record_evidence = str(record.get("evidence_class") or "")
    model_evidence = str(model_block.get("data_evidence_class") or "")
    evidence_problem = (
        record_evidence in PHYSICAL_EVIDENCE_CLASSES
        or model_evidence in PHYSICAL_EVIDENCE_CLASSES
        or record_evidence != expected.data_evidence_class
        or model_evidence != expected.data_evidence_class
    )
    if evidence_problem:
        add(
            "W18-RM-MD-07",
            DIMENSION_MODEL,
            "Evidence class must remain the declared synthetic software control.",
            STATUS_FAIL,
            f"record={record_evidence or 'MISSING'}, model={model_evidence or 'MISSING'}",
            "EVIDENCE_CLASS_CLAIM_MISMATCH",
            REFUSED_EVIDENCE_CLASS,
            "03 §3; 05B §44",
        )
    else:
        add(
            "W18-RM-MD-07",
            DIMENSION_MODEL,
            "Evidence class must remain the declared synthetic software control.",
            STATUS_PASS,
            record_evidence,
            None,
            None,
            "03 §3; 05B §44",
        )

    # ---- Feature identity ---------------------------------------------------
    feature_ids = [
        str(item.get("feature_id")) for item in features if isinstance(item, Mapping)
    ]
    if len(feature_ids) != len(features):
        raise MonitorRecordError("every feature entry must be a mapping")
    if tuple(feature_ids) != expected.ordered_feature_ids:
        add(
            "W18-RM-FD-01",
            DIMENSION_FEATURE,
            "The exact ordered 28-feature identity must be consumed.",
            STATUS_FAIL,
            f"declared_count={len(feature_ids)}",
            (
                "FEATURE_ORDER_OR_COUNT_MISMATCH"
                if len(feature_ids) == expected.feature_count
                else "FEATURE_COUNT_MISMATCH"
            ),
            REFUSED_FEATURE_IDENTITY,
            "05B §46; 03 §92; 02 §60.5",
        )
    elif len(set(feature_ids)) != len(feature_ids):
        add(
            "W18-RM-FD-01",
            DIMENSION_FEATURE,
            "The exact ordered 28-feature identity must be consumed.",
            STATUS_FAIL,
            "duplicate feature identifiers",
            "FEATURE_IDENTITY_DUPLICATED",
            REFUSED_FEATURE_IDENTITY,
            "05B §46; 03 §92",
        )
    else:
        add(
            "W18-RM-FD-01",
            DIMENSION_FEATURE,
            "The exact ordered 28-feature identity must be consumed.",
            STATUS_PASS,
            f"{len(feature_ids)} ordered features",
            None,
            None,
            "05B §46; 03 §92; 02 §60.5",
        )
    declared_version = str(record.get("feature_version") or "")
    declared_schema = str(record.get("feature_schema_sha256") or "")
    declared_registry = str(record.get("registry_sha256") or "")
    if declared_version != expected.feature_version:
        add(
            "W18-RM-FD-02",
            DIMENSION_FEATURE,
            "Feature-registry version must match the frozen feature definitions.",
            STATUS_FAIL,
            f"declared={declared_version or 'MISSING'}",
            "FEATURE_VERSION_MISMATCH",
            REFUSED_FEATURE_IDENTITY,
            "05B §46; 03 §92",
        )
    else:
        add(
            "W18-RM-FD-02",
            DIMENSION_FEATURE,
            "Feature-registry version must match the frozen feature definitions.",
            STATUS_PASS,
            declared_version,
            None,
            None,
            "05B §46; 03 §92",
        )
    if declared_schema != expected.feature_schema_sha256 or (
        declared_registry and declared_registry != expected.feature_schema_sha256
    ):
        add(
            "W18-RM-FD-03",
            DIMENSION_FEATURE,
            "Feature schema/registry hash must match the W10 registry and W15 manifest.",
            STATUS_FAIL,
            f"feature_schema={declared_schema[:16] or 'MISSING'}, "
            f"registry={declared_registry[:16] or 'MISSING'}",
            "FEATURE_SCHEMA_HASH_MISMATCH",
            REFUSED_FEATURE_IDENTITY,
            "05B §46; 03 §92",
        )
    else:
        add(
            "W18-RM-FD-03",
            DIMENSION_FEATURE,
            "Feature schema/registry hash must match the W10 registry and W15 manifest.",
            STATUS_PASS,
            declared_schema,
            None,
            None,
            "05B §46; 03 §92",
        )
    declared_order_sha = str(record.get("ordered_feature_ids_sha256") or "")
    computed_order_sha = ordered_feature_ids_sha256(feature_ids)
    if declared_order_sha != expected.ordered_feature_ids_sha256 or (
        computed_order_sha != expected.ordered_feature_ids_sha256
    ):
        add(
            "W18-RM-FD-04",
            DIMENSION_FEATURE,
            "Ordered-feature identity hash must bind the consumed feature order.",
            STATUS_FAIL,
            f"declared={declared_order_sha[:16] or 'MISSING'}, "
            f"computed={computed_order_sha[:16]}",
            "ORDERED_FEATURE_IDS_HASH_MISMATCH",
            REFUSED_FEATURE_IDENTITY,
            "05B §46; 03 §92",
        )
    else:
        add(
            "W18-RM-FD-04",
            DIMENSION_FEATURE,
            "Ordered-feature identity hash must bind the consumed feature order.",
            STATUS_PASS,
            declared_order_sha,
            None,
            None,
            "05B §46; 03 §92",
        )
    values = [item.get("value") for item in features]
    reasons = [str(item.get("missing_reason") or "") for item in features]
    vector_payload = {
        "feature_ids": feature_ids,
        "values": values,
        "missing_reasons": reasons,
        "feature_schema_version": declared_version,
        "registry_sha256": declared_registry,
    }
    computed_vector_sha = canonical_sha256(vector_payload)
    declared_vector_sha = str(record.get("feature_vector_sha256") or "")
    if declared_vector_sha != computed_vector_sha:
        add(
            "W18-RM-FD-05",
            DIMENSION_FEATURE,
            "Feature-vector hash must bind the recorded values and missing reasons.",
            STATUS_FAIL,
            f"declared={declared_vector_sha[:16] or 'MISSING'}, "
            f"computed={computed_vector_sha[:16]}",
            "FEATURE_VECTOR_HASH_MISMATCH",
            REFUSED_FEATURE_IDENTITY,
            "05B §46; 03 §92",
        )
    else:
        add(
            "W18-RM-FD-05",
            DIMENSION_FEATURE,
            "Feature-vector hash must bind the recorded values and missing reasons.",
            STATUS_PASS,
            declared_vector_sha,
            None,
            None,
            "05B §46; 03 §92",
        )
    missing_count = 0
    missingness_problem = None
    for feature_id, value, reason in zip(feature_ids, values, reasons):
        if value is None:
            missing_count += 1
            if not reason or reason == "PRESENT":
                missingness_problem = f"{feature_id}: missing value without a MISSING_ reason"
                break
        else:
            if reason != "PRESENT":
                missingness_problem = f"{feature_id}: numeric value with reason {reason!r}"
                break
            if not _is_finite_number(value):
                missingness_problem = f"{feature_id}: non-finite or non-numeric value"
                break
    if missingness_problem:
        add(
            "W18-RM-FD-06",
            DIMENSION_FEATURE,
            "Missing values must stay explicit; no zero-fill and no reason/value contradiction.",
            STATUS_FAIL,
            missingness_problem,
            "MISSINGNESS_SEMANTICS_BROKEN",
            REFUSED_FEATURE_IDENTITY,
            "03 §125; registry missingness policy",
        )
    else:
        add(
            "W18-RM-FD-06",
            DIMENSION_FEATURE,
            "Missing values must stay explicit; no zero-fill and no reason/value contradiction.",
            STATUS_PASS,
            f"{missing_count} explicit missing / {len(values)} features",
            None,
            None,
            "03 §125; registry missingness policy",
        )

    # ---- Prediction semantics ----------------------------------------------
    score_semantics = str(record.get("score_semantics") or "")
    if score_semantics != expected.score_semantics:
        add(
            "W18-RM-PS-01",
            DIMENSION_PREDICTION,
            "Output semantics must be risk_score, never a calibrated probability.",
            STATUS_FAIL,
            f"declared={score_semantics or 'MISSING'}",
            "SCORE_SEMANTICS_NOT_RISK_SCORE",
            REFUSED_PREDICTION_SEMANTICS,
            "03 §58-60; 05B §46",
        )
    else:
        add(
            "W18-RM-PS-01",
            DIMENSION_PREDICTION,
            "Output semantics must be risk_score, never a calibrated probability.",
            STATUS_PASS,
            score_semantics,
            None,
            None,
            "03 §58-60; 05B §46",
        )
    risk_score = record.get("risk_score")
    score_valid = _is_finite_number(risk_score) and 0.0 <= float(risk_score) <= 1.0
    if risk_score is not None and not score_valid:
        add(
            "W18-RM-PS-02",
            DIMENSION_PREDICTION,
            "A declared risk score must be a finite value in [0, 1].",
            STATUS_FAIL,
            f"risk_score={risk_score!r}",
            "RISK_SCORE_INVALID",
            REFUSED_PREDICTION_SEMANTICS,
            "05B §46",
        )
    else:
        add(
            "W18-RM-PS-02",
            DIMENSION_PREDICTION,
            "A declared risk score must be a finite value in [0, 1].",
            STATUS_PASS,
            "no score declared (input refusal)" if risk_score is None else str(risk_score),
            None,
            None,
            "05B §46",
        )
    prediction_policy = record.get("prediction_policy")
    if prediction_policy is not None and not isinstance(prediction_policy, Mapping):
        raise MonitorRecordError("prediction_policy must be a mapping when present")
    declared_policy: Mapping[str, Any] = prediction_policy or {}
    policy_claims: list[str] = []
    for key, expected_value, label in (
        ("target_status", policy.target_status, "target"),
        ("horizon_status", policy.horizon_status, "horizon"),
        ("operating_threshold_status", policy.operating_threshold_status, "threshold"),
        (
            "warning_persistence_status",
            policy.warning_persistence_status,
            "persistence",
        ),
        ("calibration_status", policy.calibration_status, "calibration"),
    ):
        declared = declared_policy.get(key)
        if declared is None:
            continue
        if str(declared) in FROZEN_CLAIM_VALUES:
            policy_claims.append(f"{label} claimed {declared}")
        elif str(declared) != str(expected_value):
            policy_claims.append(
                f"{label} declared {declared!r} != expected {expected_value!r}"
            )
    for key, expected_value, label in (
        ("horizon_s", policy.horizon_s, "horizon value"),
        (
            "operating_threshold",
            policy.operating_threshold,
            "threshold value",
        ),
    ):
        declared = declared_policy.get(key)
        if declared is not None and (
            not _is_finite_number(declared)
            or float(declared) != float(expected_value)
        ):
            policy_claims.append(f"{label} declared {declared!r}")
    warning = record.get("hypothetical_warning")
    if warning is not None and not isinstance(warning, Mapping):
        raise MonitorRecordError("hypothetical_warning must be a mapping when present")
    warning_block: Mapping[str, Any] = warning or {}
    warning_status = str(warning_block.get("status") or "")
    if warning_block:
        if str(warning_block.get("rule_status", "")) in FROZEN_CLAIM_VALUES:
            policy_claims.append(
                f"warning rule claimed {warning_block.get('rule_status')}"
            )
        if str(warning_block.get("persistence", "")) in FROZEN_CLAIM_VALUES:
            policy_claims.append(
                f"persistence claimed {warning_block.get('persistence')}"
            )
        if warning_block.get("rule_source") not in (None, policy.warning_rule_source):
            policy_claims.append(
                f"warning-rule provenance {warning_block.get('rule_source')!r}"
            )
        if warning_block.get("rule") not in (
            None,
            _rule_string(policy.operating_threshold),
        ):
            policy_claims.append(
                f"warning rule {warning_block.get('rule')!r} does not bind the illustrative threshold"
            )
        if warning_status and warning_status not in WARNING_STATUSES:
            policy_claims.append(f"unknown warning status {warning_status!r}")
        if (
            score_valid
            and warning_status == WARNING_TRIGGERED
            and float(risk_score) < policy.operating_threshold
        ):
            policy_claims.append(
                "warning triggered below the declared operating threshold"
            )
        if (
            score_valid
            and warning_status == WARNING_NOT_TRIGGERED
            and float(risk_score) >= policy.operating_threshold
        ):
            policy_claims.append(
                "warning not triggered at or above the declared operating threshold"
            )
    if policy_claims:
        add(
            "W18-RM-PS-03",
            DIMENSION_PREDICTION,
            "Horizon, target, threshold, persistence, calibration and warning provenance must stay as declared development candidates.",
            STATUS_FAIL,
            "; ".join(policy_claims),
            "POLICY_FREEZE_OR_PROVENANCE_CLAIM",
            REFUSED_POLICY_UNFROZEN,
            "05B §46; 03 §87-88; 04 §11.4",
        )
    else:
        add(
            "W18-RM-PS-03",
            DIMENSION_PREDICTION,
            "Horizon, target, threshold, persistence, calibration and warning provenance must stay as declared development candidates.",
            STATUS_PASS,
            (
                f"target={policy.target_status}, horizon={policy.horizon_s:g}s "
                f"({policy.horizon_status}), threshold={policy.operating_threshold:g} "
                f"({policy.operating_threshold_status}), "
                f"persistence={policy.warning_persistence_status}"
            ),
            None,
            None,
            "05B §46; 03 §87-88; 04 §11.4",
        )
    hypothetical_policy = record.get("hypothetical_policy")
    if hypothetical_policy is not None and not isinstance(
        hypothetical_policy, Mapping
    ):
        raise MonitorRecordError("hypothetical_policy must be a mapping when present")
    policy_block: Mapping[str, Any] = hypothetical_policy or {}
    policy_authorization_claims: list[str] = []
    if policy_block:
        if policy_block.get("dispatchable") not in (False, None):
            policy_authorization_claims.append("policy declared dispatchable")
        if policy_block.get("authorized_control_decision") not in (None, False):
            policy_authorization_claims.append(
                "policy declared an authorized control decision"
            )
        if policy_block.get("physical_control_path") not in (None, False, "NONE"):
            policy_authorization_claims.append(
                "policy declared a physical control path"
            )
        if policy_block.get("status") in FROZEN_CLAIM_VALUES:
            policy_authorization_claims.append(
                f"policy status {policy_block.get('status')!r}"
            )
    if policy_authorization_claims:
        control_claim = True
        add(
            "W18-RM-PS-04",
            DIMENSION_PREDICTION,
            "A hypothetical policy record may not be presented as an authorized or dispatchable command.",
            STATUS_FAIL,
            "; ".join(policy_authorization_claims),
            "POLICY_PRESENTED_AS_AUTHORIZED_CONTROL",
            REFUSED_RELEASE_AUTHORIZATION,
            "02 §1.6; 05B §46",
        )
    else:
        add(
            "W18-RM-PS-04",
            DIMENSION_PREDICTION,
            "A hypothetical policy record may not be presented as an authorized or dispatchable command.",
            STATUS_PASS,
            "no authorization or dispatch claim",
            None,
            None,
            "02 §1.6; 05B §46",
        )

    # ---- Freshness ----------------------------------------------------------
    verdict_value = str(freshness.get("verdict") or "")
    disposition_value = str(freshness.get("disposition") or "")
    freshness_status = str(freshness.get("policy_status") or "")
    input_state = "UNKNOWN"
    if verdict_value == FRESH and disposition_value in (
        READY_FOR_SOFTWARE_REPLAY,
        "",
    ):
        input_state = "FRESH"
    elif REFUSED_STALE in (verdict_value, disposition_value):
        input_state = "STALE"
    elif REFUSED_UNTRUSTED in (verdict_value, disposition_value):
        input_state = "UNTRUSTED"
    elif REFUSED_TEMPORAL in (verdict_value, disposition_value):
        input_state = "TEMPORAL"
    if freshness_status != policy.runtime_freshness_policy_status:
        add(
            "W18-RM-FR-01",
            DIMENSION_FRESHNESS,
            "Runtime freshness policy must still be declared pending C/D.",
            STATUS_FAIL,
            f"declared={freshness_status or 'MISSING'}",
            "RUNTIME_FRESHNESS_POLICY_UNEXPECTEDLY_FROZEN",
            REFUSED_POLICY_UNFROZEN,
            "05B §46; 04 §31",
        )
    else:
        add(
            "W18-RM-FR-01",
            DIMENSION_FRESHNESS,
            "Runtime freshness policy must still be declared pending C/D.",
            STATUS_PASS,
            freshness_status,
            None,
            None,
            "05B §46; 04 §31",
        )
    if input_state == "UNKNOWN":
        add(
            "W18-RM-FR-02",
            DIMENSION_FRESHNESS,
            "Freshness verdict must be a recognised FRESH or REFUSED_* disposition.",
            STATUS_NOT_VERIFIED,
            f"verdict={verdict_value or 'MISSING'}, disposition={disposition_value or 'MISSING'}",
            "FRESHNESS_VERDICT_UNRECOGNISED",
            REFUSED_STALE_INPUT,
            "05B §46; 02 §5",
        )
    else:
        add(
            "W18-RM-FR-02",
            DIMENSION_FRESHNESS,
            "Freshness verdict must be a recognised FRESH or REFUSED_* disposition.",
            STATUS_PASS,
            input_state,
            None,
            None,
            "05B §46; 02 §5",
        )
    if input_state in {"STALE", "UNTRUSTED", "TEMPORAL"} and risk_score is not None:
        add(
            "W18-RM-FR-03",
            DIMENSION_FRESHNESS,
            "A refused input must not produce a trusted risk score.",
            STATUS_FAIL,
            f"{input_state} input carried risk_score={risk_score!r}",
            "SCORE_PRODUCED_FOR_REFUSED_INPUT",
            (
                REFUSED_STALE_INPUT
                if input_state == "STALE"
                else REFUSED_UNTRUSTED_INPUT
                if input_state == "UNTRUSTED"
                else REFUSED_TEMPORAL_ORDER
            ),
            "02 §5; 05B §46",
        )
    elif input_state == "FRESH" and not score_valid:
        add(
            "W18-RM-FR-03",
            DIMENSION_FRESHNESS,
            "A refused input must not produce a trusted risk score.",
            STATUS_FAIL,
            "fresh input without a valid risk score",
            "MISSING_SCORE_FOR_FRESH_INPUT",
            REFUSED_PREDICTION_SEMANTICS,
            "02 §5; 05B §46",
        )
    else:
        add(
            "W18-RM-FR-03",
            DIMENSION_FRESHNESS,
            "A refused input must not produce a trusted risk score.",
            STATUS_PASS,
            (
                "input refused before scoring"
                if input_state != "FRESH"
                else "fresh input carries a valid risk score"
            ),
            None,
            None,
            "02 §5; 05B §46",
        )
    anchor_event = record.get("prediction_anchor_event_s")
    anchor_receipt = record.get(
        "anchor_simulated_receipt_s", record.get("prediction_receipt_s")
    )
    if not _is_finite_number(anchor_event):
        add(
            "W18-RM-FR-04",
            DIMENSION_FRESHNESS,
            "Prediction anchor must carry an event time; host receipt time may not substitute.",
            STATUS_FAIL,
            f"prediction_anchor_event_s={anchor_event!r}, receipt={anchor_receipt!r}",
            "MISSING_EVENT_TIME_PROVENANCE",
            REFUSED_TEMPORAL_ORDER,
            "02 §5.1; 01 §18",
        )
    elif anchor_receipt is not None and not _is_finite_number(anchor_receipt):
        add(
            "W18-RM-FR-04",
            DIMENSION_FRESHNESS,
            "Prediction anchor must carry an event time; host receipt time may not substitute.",
            STATUS_FAIL,
            f"receipt={anchor_receipt!r}",
            "INVALID_RECEIPT_TIME",
            REFUSED_TEMPORAL_ORDER,
            "02 §5.1; 01 §18",
        )
    elif anchor_receipt is not None and float(anchor_receipt) < float(anchor_event):
        add(
            "W18-RM-FR-04",
            DIMENSION_FRESHNESS,
            "Prediction anchor must carry an event time; host receipt time may not substitute.",
            STATUS_FAIL,
            f"receipt={anchor_receipt} < event={anchor_event}",
            "RECEIPT_BEFORE_EVENT_TIME",
            REFUSED_TEMPORAL_ORDER,
            "02 §5.1; 01 §18",
        )
    else:
        add(
            "W18-RM-FR-04",
            DIMENSION_FRESHNESS,
            "Prediction anchor must carry an event time; host receipt time may not substitute.",
            STATUS_PASS,
            f"event={anchor_event}, receipt={anchor_receipt}",
            None,
            None,
            "02 §5.1; 01 §18",
        )
    window_end = record.get("input_window_end_s")
    window_start = record.get("input_window_start_s")
    future_issue = None
    if future_issue is None and window_end is not None:
        if not _is_finite_number(window_end):
            future_issue = f"input_window_end_s={window_end!r}"
        elif _is_finite_number(anchor_event) and float(window_end) > float(anchor_event):
            future_issue = (
                f"input_window_end_s={window_end} > anchor event={anchor_event}"
            )
    if future_issue is None and window_start is not None and window_end is not None:
        if _is_finite_number(window_start) and _is_finite_number(window_end):
            if float(window_start) > float(window_end):
                future_issue = (
                    f"input_window_start_s={window_start} > end={window_end}"
                )
    if future_issue:
        add(
            "W18-RM-FR-05",
            DIMENSION_FRESHNESS,
            "No observation newer than the prediction anchor may enter the input window.",
            STATUS_FAIL,
            future_issue,
            "FUTURE_OBSERVATION_IN_PREDICTION",
            REFUSED_TEMPORAL_ORDER,
            "02 §5; 03 §125",
        )
    else:
        add(
            "W18-RM-FR-05",
            DIMENSION_FRESHNESS,
            "No observation newer than the prediction anchor may enter the input window.",
            STATUS_PASS,
            f"window=[{window_start}, {window_end}], anchor={anchor_event}",
            None,
            None,
            "02 §5; 03 §125",
        )
    input_ids = record.get("input_telemetry_ids")
    declared_input_sha = str(record.get("input_telemetry_ids_sha256") or "")
    if not isinstance(input_ids, list) or not input_ids:
        add(
            "W18-RM-FR-06",
            DIMENSION_FRESHNESS,
            "Input telemetry identity must bind the exact consumed observations.",
            STATUS_FAIL,
            "input_telemetry_ids missing or empty",
            "INPUT_TELEMETRY_IDS_MISSING",
            REFUSED_STALE_INPUT,
            "02 §4.2; 05B §46",
        )
    elif canonical_sha256(list(input_ids)) != declared_input_sha:
        add(
            "W18-RM-FR-06",
            DIMENSION_FRESHNESS,
            "Input telemetry identity must bind the exact consumed observations.",
            STATUS_FAIL,
            f"declared={declared_input_sha[:16] or 'MISSING'}",
            "INPUT_TELEMETRY_IDS_HASH_MISMATCH",
            REFUSED_STALE_INPUT,
            "02 §4.2; 05B §46",
        )
    else:
        add(
            "W18-RM-FR-06",
            DIMENSION_FRESHNESS,
            "Input telemetry identity must bind the exact consumed observations.",
            STATUS_PASS,
            f"{len(input_ids)} input records",
            None,
            None,
            "02 §4.2; 05B §46",
        )

    # ---- Verdict ------------------------------------------------------------
    present_dispositions = {
        check.disposition for check in checks if check.disposition is not None
    }
    verdict = MONITOR_SOFTWARE_VALID
    for candidate in DISPOSITION_PRECEDENCE:
        if candidate in present_dispositions:
            verdict = candidate
            break
    if verdict == MONITOR_SOFTWARE_VALID and input_state in {
        "STALE",
        "UNTRUSTED",
        "TEMPORAL",
    }:
        verdict = {
            "STALE": REFUSED_STALE_INPUT,
            "UNTRUSTED": REFUSED_UNTRUSTED_INPUT,
            "TEMPORAL": REFUSED_TEMPORAL_ORDER,
        }[input_state]
    refusal_reasons = tuple(
        dict.fromkeys(
            check.reason_code for check in checks if check.reason_code is not None
        )
    )
    approval_attribute_checks = {
        "W18-RM-MD-05",
        "W18-RM-MD-06",
        "W18-RM-MD-07",
    }
    identity_dimensions = {
        check.status
        for check in checks
        if check.dimension in (DIMENSION_MODEL, DIMENSION_FEATURE)
        and check.check_id not in approval_attribute_checks
    }
    identity_match = (
        STATUS_FAIL not in identity_dimensions
        and not any(
            check.status == STATUS_NOT_VERIFIED
            and check.dimension in (DIMENSION_MODEL, DIMENSION_FEATURE)
            and check.check_id not in approval_attribute_checks
            for check in checks
        )
    )
    freshness_failures = any(
        check.dimension == DIMENSION_FRESHNESS
        and check.status in (STATUS_FAIL, STATUS_NOT_VERIFIED)
        for check in checks
    )
    evidence_quality = input_state == "FRESH" and not freshness_failures
    return MonitorResult(
        record_key=record_key,
        verdict=verdict,
        identity_match=identity_match,
        evidence_quality=evidence_quality,
        scientific_release_eligibility=False,
        physical_authorization=False,
        release_claim=release_claim,
        control_claim=control_claim,
        checks=tuple(checks),
        refusal_reasons=refusal_reasons,
    )


@dataclass(frozen=True)
class SequenceAudit:
    record_count: int
    group_count: int
    groups: tuple[Mapping[str, Any], ...]
    issues: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": self.record_count,
            "group_count": self.group_count,
            "groups": [dict(group) for group in self.groups],
            "issues": list(self.issues),
            "passed": self.passed,
        }


def audit_runtime_sequence(records: Sequence[Mapping[str, Any]]) -> SequenceAudit:
    """Verify run/boot lineage, sequence continuity and prediction identity."""
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    issues: set[str] = set()
    prediction_owner: dict[str, str] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise MonitorRecordError("runtime record is not a mapping")
        run_id = str(record.get("run_id") or "")
        boot_id = str(record.get("boot_id") or "")
        if not run_id or not boot_id:
            issues.add("RUN_OR_BOOT_IDENTITY_MISSING")
            continue
        groups.setdefault((run_id, boot_id), []).append(record)
        prediction_id = str(record.get("prediction_id") or "")
        if not prediction_id:
            issues.add("PREDICTION_ID_MISSING")
            continue
        fingerprint = canonical_sha256(
            {
                "run_id": run_id,
                "boot_id": boot_id,
                "score": record.get("risk_score"),
                "vector": record.get("feature_vector_sha256"),
            }
        )
        owner = prediction_owner.get(prediction_id)
        if owner is None:
            prediction_owner[prediction_id] = fingerprint
        elif owner != fingerprint:
            issues.add("PREDICTION_ID_REUSED_WITH_CONTRADICTORY_CONTENT")
    summaries: list[dict[str, Any]] = []
    for (run_id, boot_id), group in sorted(groups.items()):
        seqs = [record.get("seq") for record in group]
        numeric = all(isinstance(seq, int) and not isinstance(seq, bool) for seq in seqs)
        duplicates = len(seqs) != len(set(seqs))
        if not numeric:
            issues.add("SEQUENCE_NUMBER_INVALID")
        if duplicates:
            issues.add("DUPLICATE_SEQUENCE_IN_BOOT")
        anchors = [
            record.get("prediction_anchor_event_s") for record in group
        ]
        chronological = all(_is_finite_number(value) for value in anchors)
        sorted_group = sorted(
            group,
            key=lambda record: (
                float(record.get("prediction_anchor_event_s") or 0.0),
                int(record.get("seq") or 0),
            ),
        )
        monotonic = True
        if chronological:
            anchor_times = [
                float(record.get("prediction_anchor_event_s")) for record in sorted_group
            ]
            if len(anchor_times) != len(set(anchor_times)):
                issues.add("DUPLICATE_ANCHOR_EVENT_TIME_IN_BOOT")
            for previous, current in zip(sorted_group, sorted_group[1:]):
                if int(current.get("seq") or 0) <= int(previous.get("seq") or 0):
                    monotonic = False
        else:
            issues.add("ANCHOR_EVENT_TIME_MISSING")
        if chronological and not monotonic:
            issues.add("SEQUENCE_DISCONTINUITY")
        summaries.append(
            {
                "run_id": run_id,
                "boot_id": boot_id,
                "record_count": len(group),
                "first_seq": min(seqs) if numeric and seqs else None,
                "last_seq": max(seqs) if numeric and seqs else None,
                "chronological": chronological,
                "monotonic": monotonic,
            }
        )
    return SequenceAudit(
        record_count=len(records),
        group_count=len(groups),
        groups=tuple(summaries),
        issues=tuple(sorted(issues)),
    )


@dataclass(frozen=True)
class RuntimeAudit:
    results: tuple[MonitorResult, ...]
    sequence: SequenceAudit

    @property
    def verdict_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in self.results:
            counts[result.verdict] = counts.get(result.verdict, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def reason_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in self.results:
            for reason in result.refusal_reasons:
                counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def identity_match_all(self) -> bool:
        return all(result.identity_match for result in self.results)

    @property
    def release_claim_count(self) -> int:
        return sum(1 for result in self.results if result.release_claim)

    @property
    def control_claim_count(self) -> int:
        return sum(1 for result in self.results if result.control_claim)

    def to_summary(self) -> dict[str, Any]:
        return {
            "record_count": len(self.results),
            "verdict_counts": self.verdict_counts,
            "reason_counts": self.reason_counts,
            "identity_match_all": self.identity_match_all,
            "release_claim_count": self.release_claim_count,
            "control_claim_count": self.control_claim_count,
            "scientific_release_eligibility": False,
            "physical_authorization": False,
            "sequence": self.sequence.to_dict(),
        }


def monitor_runtime_records(
    records: Sequence[Mapping[str, Any]],
    *,
    expected: ExpectedRuntimeIdentity,
    policy: PolicyExpectation | None = None,
) -> RuntimeAudit:
    policy = policy or expected.policy_expectation()
    results = tuple(
        monitor_runtime_record(record, expected=expected, policy=policy)
        for record in records
    )
    return RuntimeAudit(results=results, sequence=audit_runtime_sequence(records))
