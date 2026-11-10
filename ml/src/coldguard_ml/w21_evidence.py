"""W21 evidence admission and provenance (B-W21-01..04 source layer).

Canonical anchors: Doc 01 sections 1.10-1.17, 6.5-6.8, 9, 19, 26; Doc 02
sections 37-44; Doc 03 sections 66, 103-107, 115, 137; Doc 05B section 49.

The layer is read-only.  It records what a source actually is, which evidence
class it belongs to, which bytes were seen and which inference the bytes
permit.  A host simulation, an on-device software injection and a physical
control response are distinct classes; promotion between them is refused
rather than inferred from a PASS field.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

W21_EVIDENCE_LAYER_VERSION = "coldguard-w21-evidence-v1"
W21_SOURCE_REGISTER_SCHEMA = "coldguard-w21-source-register-v1"

EVIDENCE_HOST_SOFTWARE_SIMULATION = "HOST_SOFTWARE_SIMULATION"
EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION = "ON_DEVICE_SOFTWARE_INJECTION"
EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE = "OBSERVED_PHYSICAL_CONTROL_RESPONSE"
EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT = "ACCEPTED_PHYSICAL_RESILIENCE_RESULT"
EVIDENCE_CONTRACT_REFERENCE = "CONTRACT_REFERENCE"

EVIDENCE_CLASSES = (
    EVIDENCE_HOST_SOFTWARE_SIMULATION,
    EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
    EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
    EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT,
    EVIDENCE_CONTRACT_REFERENCE,
)

EVIDENCE_CLASS_RANK = {
    EVIDENCE_HOST_SOFTWARE_SIMULATION: 0,
    EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION: 1,
    EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE: 2,
    EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT: 3,
}

GATE_SOFTWARE_TEST_ONLY = "SOFTWARE_TEST_ONLY"
GATE_CONTRACT_REFERENCE_ONLY = "CONTRACT_REFERENCE_ONLY"
GATE_BOUNDED_ON_DEVICE_EVIDENCE = "BOUNDED_ON_DEVICE_EVIDENCE"
GATE_PHYSICALLY_VERIFIED = "PHYSICALLY_VERIFIED"
GATE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
GATE_NOT_ADMISSIBLE = "NOT_ADMISSIBLE"

CHECK_VERIFIED = "VERIFIED"
CHECK_NOT_VERIFIED = "NOT_VERIFIED"
CHECK_NOT_APPLICABLE = "NOT_APPLICABLE"
CHECK_FAILED = "FAILED"

PROVENANCE_SOURCE_BYTES_VERIFIED = "SOURCE_BYTES_VERIFIED"
PROVENANCE_MANIFEST_COHERENT = "MANIFEST_COHERENT"
PROVENANCE_RECORDED_CHECK_PASSED = "RECORDED_CHECK_PASSED"
PROVENANCE_MEASUREMENT_INTERPRETATION_SUPPORTED = (
    "MEASUREMENT_INTERPRETATION_SUPPORTED"
)
PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED = "ACCEPTANCE_AUTHORITY_VERIFIED"

PROVENANCE_CHECKS = (
    PROVENANCE_SOURCE_BYTES_VERIFIED,
    PROVENANCE_MANIFEST_COHERENT,
    PROVENANCE_RECORDED_CHECK_PASSED,
    PROVENANCE_MEASUREMENT_INTERPRETATION_SUPPORTED,
    PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED,
)

GATE_F_OPEN = "OPEN"
GATE_F_NOT_OPENED = "NOT_OPENED"

GATE_F_CLOSED_REASONS = (
    "NO_AUTHORITATIVE_AUTHORIZATION_ARTIFACT",
    "CORE_EVIDENCE_INCOMPLETE",
    "OPTIONAL_SCOPE_CANCELLED_OR_NOT_OPENED",
)

CLASS_PROMOTION_REFUSED = "EVIDENCE_CLASS_PROMOTION_REFUSED"
CLASS_DOWNGRADE_ALLOWED = "EVIDENCE_CLASS_DOWNGRADE_ALLOWED"
CLASS_UNCHANGED = "EVIDENCE_CLASS_UNCHANGED"

FORBIDDEN_IMPORTS = frozenset(
    {
        "asyncio",
        "grpc",
        "http",
        "httpx",
        "multiprocessing",
        "paho",
        "requests",
        "scipy",
        "serial",
        "sklearn",
        "socket",
        "ssl",
        "statsmodels",
        "subprocess",
        "urllib",
        "xgboost",
    }
)

FORBIDDEN_CALL_NAMES = frozenset(
    {
        "actuate",
        "connect",
        "gpio_set_level",
        "publish",
        "publish_command",
        "pwm_write",
        "send_command",
        "send_fault_injection",
        "set_duty",
        "set_output",
    }
)

CAPABILITY_KEYS = (
    "activate_controller_b",
    "change_policy_or_threshold",
    "command_tec",
    "instantiate_hardware_or_broker_client",
    "physical_fault_injection",
    "publish_actuator_message",
    "run_energy_experiment",
)

_ALLOWED_GATES_BY_CLASS = {
    EVIDENCE_HOST_SOFTWARE_SIMULATION: frozenset({GATE_SOFTWARE_TEST_ONLY}),
    EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION: frozenset(
        {GATE_BOUNDED_ON_DEVICE_EVIDENCE}
    ),
    EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE: frozenset(
        {GATE_PHYSICALLY_VERIFIED, GATE_NOT_ESTABLISHED}
    ),
    EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT: frozenset(
        {GATE_PHYSICALLY_VERIFIED, GATE_NOT_ESTABLISHED}
    ),
    EVIDENCE_CONTRACT_REFERENCE: frozenset({GATE_CONTRACT_REFERENCE_ONLY}),
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class W21EvidenceError(ValueError):
    """Raised for malformed evidence records or refused promotions."""


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_path: str
    source_revision: str
    source_sha256: str | None
    size_bytes: int | None
    producer: str
    identity: Mapping[str, str]
    evidence_class: str
    scenario: str
    observed_outcome: str
    admissible_inference: tuple[str, ...]
    unsupported_inference: tuple[str, ...]
    review_state: str
    gate: str
    in_w20_ancestry: bool
    verified_at_authoring: bool
    measurement_bearing: bool = True

    def validate(self) -> None:
        if not self.source_id or not self.source_id.strip():
            raise W21EvidenceError("source_id must be non-empty")
        if not self.source_path or self.source_path.startswith(("/", "\\")):
            raise W21EvidenceError(f"{self.source_id}: source_path must be relative")
        if ".." in Path(self.source_path).parts:
            raise W21EvidenceError(f"{self.source_id}: source_path escapes the root")
        if not self.source_revision:
            raise W21EvidenceError(f"{self.source_id}: source_revision is required")
        if self.source_sha256 is not None and not _SHA256_RE.match(self.source_sha256):
            raise W21EvidenceError(f"{self.source_id}: malformed sha256")
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise W21EvidenceError(f"{self.source_id}: unknown evidence class")
        if self.evidence_class == EVIDENCE_CONTRACT_REFERENCE and (
            self.measurement_bearing
        ):
            raise W21EvidenceError(
                f"{self.source_id}: a contract reference is not a measurement"
            )
        if self.gate not in {
            GATE_SOFTWARE_TEST_ONLY,
            GATE_CONTRACT_REFERENCE_ONLY,
            GATE_BOUNDED_ON_DEVICE_EVIDENCE,
            GATE_PHYSICALLY_VERIFIED,
            GATE_NOT_ESTABLISHED,
            GATE_NOT_ADMISSIBLE,
        }:
            raise W21EvidenceError(f"{self.source_id}: unknown gate")
        allowed = _ALLOWED_GATES_BY_CLASS[self.evidence_class]
        if self.gate not in allowed:
            raise W21EvidenceError(
                f"{self.source_id}: gate {self.gate} is not admissible for "
                f"{self.evidence_class}"
            )
        if not isinstance(self.identity, Mapping) or "session_key" not in self.identity:
            raise W21EvidenceError(f"{self.source_id}: identity needs a session_key")
        if not self.admissible_inference:
            raise W21EvidenceError(
                f"{self.source_id}: admissible inference must be declared"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_path": self.source_path,
            "source_revision": self.source_revision,
            "source_sha256": self.source_sha256,
            "size_bytes": self.size_bytes,
            "producer": self.producer,
            "identity": dict(self.identity),
            "evidence_class": self.evidence_class,
            "scenario": self.scenario,
            "observed_outcome": self.observed_outcome,
            "admissible_inference": list(self.admissible_inference),
            "unsupported_inference": list(self.unsupported_inference),
            "review_state": self.review_state,
            "gate": self.gate,
            "in_w20_ancestry": self.in_w20_ancestry,
            "verified_at_authoring": self.verified_at_authoring,
            "measurement_bearing": self.measurement_bearing,
        }


@dataclass(frozen=True)
class Admission:
    source_id: str
    checks: Mapping[str, str]
    basis: Mapping[str, str]
    gate: str
    refusal_reasons: tuple[str, ...] = ()

    @property
    def failed(self) -> bool:
        return any(status == CHECK_FAILED for status in self.checks.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "checks": dict(self.checks),
            "basis": dict(self.basis),
            "gate": self.gate,
            "refusal_reasons": list(self.refusal_reasons),
        }


@dataclass(frozen=True)
class GateFAssessment:
    status: str
    optional_deliverable: str
    reasons: tuple[str, ...]
    cooling_branch_boundary: str = "COOLING_BRANCH_ONLY"
    energy_analysis_run: bool = False
    pwm_search_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "optional_deliverable": self.optional_deliverable,
            "reasons": list(self.reasons),
            "cooling_branch_boundary": self.cooling_branch_boundary,
            "energy_analysis_run": self.energy_analysis_run,
            "pwm_search_run": self.pwm_search_run,
        }


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_source_register(records: Sequence[SourceRecord]) -> None:
    if not records:
        raise W21EvidenceError("source register is empty")
    seen: set[str] = set()
    for record in records:
        record.validate()
        if record.source_id in seen:
            raise W21EvidenceError(f"duplicate source_id: {record.source_id}")
        seen.add(record.source_id)


def verify_source_bytes(record: SourceRecord, root: Path) -> tuple[bool, str]:
    """Read a source from a read-only checkout and compare its pinned bytes."""
    record.validate()
    root = Path(root)
    if not root.is_dir():
        raise W21EvidenceError(f"evidence root is not a directory: {root}")
    path = root / record.source_path
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise W21EvidenceError(f"{record.source_id}: path escapes the root") from exc
    if path.is_symlink() or not path.is_file():
        return False, "SOURCE_FILE_MISSING_OR_SYMLINK"
    content = path.read_bytes()
    if record.size_bytes is not None and len(content) != record.size_bytes:
        return False, "SOURCE_SIZE_MISMATCH"
    if record.source_sha256 is None:
        return False, "SOURCE_HASH_NOT_PINNED"
    if sha256_bytes(content) != record.source_sha256:
        return False, "SOURCE_SHA256_MISMATCH"
    return True, "SOURCE_SHA256_MATCH"


def admit_source(
    record: SourceRecord,
    *,
    root: Path | None = None,
    manifest_coherent: bool | None = None,
    recorded_check_passed: bool | None = None,
) -> Admission:
    """Admit one source without ever promoting its evidence class.

    Checks that were not actually performed stay ``NOT_VERIFIED``.  In
    particular, a recorded evaluator PASS is not an independent replay and a
    physical acceptance authority cannot be granted from inside W21.
    """
    record.validate()
    checks: dict[str, str] = {}
    basis: dict[str, str] = {}
    refusals: list[str] = []

    if root is not None:
        verified, basis_text = verify_source_bytes(record, root)
        checks[PROVENANCE_SOURCE_BYTES_VERIFIED] = (
            CHECK_VERIFIED if verified else CHECK_FAILED
        )
        basis[PROVENANCE_SOURCE_BYTES_VERIFIED] = basis_text
        if not verified:
            refusals.append(basis_text)
    elif record.verified_at_authoring and record.source_sha256 is not None:
        checks[PROVENANCE_SOURCE_BYTES_VERIFIED] = CHECK_VERIFIED
        basis[PROVENANCE_SOURCE_BYTES_VERIFIED] = (
            "PINNED_SHA256_VERIFIED_AT_W21_AUTHORING"
        )
    else:
        checks[PROVENANCE_SOURCE_BYTES_VERIFIED] = CHECK_NOT_VERIFIED
        basis[PROVENANCE_SOURCE_BYTES_VERIFIED] = "SOURCE_BYTES_NOT_AVAILABLE"
        refusals.append("SOURCE_BYTES_NOT_AVAILABLE")

    if manifest_coherent is None:
        checks[PROVENANCE_MANIFEST_COHERENT] = (
            CHECK_NOT_APPLICABLE
            if not record.measurement_bearing
            else CHECK_NOT_VERIFIED
        )
        basis[PROVENANCE_MANIFEST_COHERENT] = (
            "NOT_A_MEASUREMENT_SOURCE"
            if not record.measurement_bearing
            else "CROSS_CHECK_NOT_PERFORMED"
        )
        if record.measurement_bearing:
            refusals.append("MANIFEST_CROSS_CHECK_NOT_PERFORMED")
    else:
        checks[PROVENANCE_MANIFEST_COHERENT] = (
            CHECK_VERIFIED if manifest_coherent else CHECK_FAILED
        )
        basis[PROVENANCE_MANIFEST_COHERENT] = "CALLER_CROSS_CHECK"
        if not manifest_coherent:
            refusals.append("MANIFEST_IDENTITY_MISMATCH")

    if recorded_check_passed is None:
        checks[PROVENANCE_RECORDED_CHECK_PASSED] = (
            CHECK_NOT_APPLICABLE
            if not record.measurement_bearing
            else CHECK_NOT_VERIFIED
        )
        basis[PROVENANCE_RECORDED_CHECK_PASSED] = (
            "NOT_A_MEASUREMENT_SOURCE"
            if not record.measurement_bearing
            else "RECORDED_EVALUATOR_NOT_INDEPENDENTLY_REPLAYED"
        )
        if record.measurement_bearing:
            refusals.append("RECORDED_CHECK_NOT_CROSS_CHECKED")
    else:
        checks[PROVENANCE_RECORDED_CHECK_PASSED] = (
            CHECK_VERIFIED if recorded_check_passed else CHECK_FAILED
        )
        basis[PROVENANCE_RECORDED_CHECK_PASSED] = "CALLER_CROSS_CHECK"
        if not recorded_check_passed:
            refusals.append("RECORDED_CHECK_FAILED")

    if (
        record.measurement_bearing
        and record.gate
        in {
            GATE_BOUNDED_ON_DEVICE_EVIDENCE,
            GATE_PHYSICALLY_VERIFIED,
            GATE_SOFTWARE_TEST_ONLY,
        }
        and recorded_check_passed is True
    ):
        checks[PROVENANCE_MEASUREMENT_INTERPRETATION_SUPPORTED] = CHECK_VERIFIED
        basis[PROVENANCE_MEASUREMENT_INTERPRETATION_SUPPORTED] = (
            "BOUNDED_INTERPRETATION_DECLARED"
        )
    elif record.measurement_bearing:
        checks[PROVENANCE_MEASUREMENT_INTERPRETATION_SUPPORTED] = (
            CHECK_NOT_VERIFIED
        )
        basis[PROVENANCE_MEASUREMENT_INTERPRETATION_SUPPORTED] = (
            "BOUNDED_INTERPRETATION_DECLARED_BUT_RECORDED_CHECK_NOT_CROSS_CHECKED"
        )
    else:
        checks[PROVENANCE_MEASUREMENT_INTERPRETATION_SUPPORTED] = (
            CHECK_NOT_APPLICABLE
        )
        basis[PROVENANCE_MEASUREMENT_INTERPRETATION_SUPPORTED] = (
            "CONTRACT_REFERENCE_NOT_A_MEASUREMENT"
        )

    checks[PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED] = CHECK_NOT_VERIFIED
    basis[PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED] = (
        "EVALUATOR_LINEAGE_NOT_ON_MAIN"
        if record.measurement_bearing
        else "NO_AUTHORITATIVE_APPROVAL_RECORD"
    )
    refusals.append("ACCEPTANCE_AUTHORITY_NOT_VERIFIED")

    if any(status == CHECK_FAILED for status in checks.values()):
        gate = GATE_NOT_ADMISSIBLE
    elif record.evidence_class in {
        EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
        EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT,
    }:
        # W21 has no authority to grant physical acceptance; even a physically
        # classified source stays unestablished without an external approval.
        gate = GATE_NOT_ESTABLISHED
        refusals.append("PHYSICAL_ACCEPTANCE_AUTHORITY_ABSENT")
    elif record.evidence_class == EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION:
        gate = GATE_BOUNDED_ON_DEVICE_EVIDENCE
    elif record.evidence_class == EVIDENCE_HOST_SOFTWARE_SIMULATION:
        gate = GATE_SOFTWARE_TEST_ONLY
    elif record.evidence_class == EVIDENCE_CONTRACT_REFERENCE:
        gate = GATE_CONTRACT_REFERENCE_ONLY
    else:  # pragma: no cover - unreachable after validate()
        gate = GATE_NOT_ADMISSIBLE

    if gate in {GATE_NOT_ADMISSIBLE, GATE_NOT_ESTABLISHED}:
        refusals.append(f"GATE_{gate}")

    return Admission(
        source_id=record.source_id,
        checks=checks,
        basis=basis,
        gate=gate,
        refusal_reasons=tuple(dict.fromkeys(refusals)),
    )


def assess_class_promotion(actual: str, claimed: str) -> str:
    if actual not in EVIDENCE_CLASS_RANK or claimed not in EVIDENCE_CLASS_RANK:
        raise W21EvidenceError("unknown evidence class")
    if EVIDENCE_CLASS_RANK[claimed] > EVIDENCE_CLASS_RANK[actual]:
        return CLASS_PROMOTION_REFUSED
    if EVIDENCE_CLASS_RANK[claimed] < EVIDENCE_CLASS_RANK[actual]:
        return CLASS_DOWNGRADE_ALLOWED
    return CLASS_UNCHANGED


def refuse_class_promotion(actual: str, claimed: str) -> None:
    verdict = assess_class_promotion(actual, claimed)
    if verdict == CLASS_PROMOTION_REFUSED:
        raise W21EvidenceError(
            f"{CLASS_PROMOTION_REFUSED}: {actual} cannot be reported as {claimed}"
        )


def count_independent_sessions(records: Iterable[SourceRecord]) -> int:
    keys = set()
    for record in records:
        record.validate()
        if record.measurement_bearing:
            keys.add(record.identity["session_key"])
    return len(keys)


def assess_gate_f(
    authorization: Mapping[str, Any] | None = None,
    *,
    core_evidence_complete: bool = False,
) -> GateFAssessment:
    """Gate F is closed unless an authoritative, byte-bound artifact opens it.

    The canonical condition (Doc 03 Gate F, Doc 04 W21 optional opening, Doc
    05B B-W21-04) is an authorized optional scope after core evidence is
    complete.  A bare status string is not an authorization.
    """
    reasons: list[str] = []
    if authorization is None:
        reasons.extend(GATE_F_CLOSED_REASONS)
        return GateFAssessment(
            status=GATE_F_NOT_OPENED,
            optional_deliverable="NOT_APPLICABLE_OPTIONAL_GATE_CLOSED",
            reasons=tuple(reasons),
        )
    if not isinstance(authorization, Mapping):
        raise W21EvidenceError("Gate F authorization must be a mapping")
    required = ("authority_id", "canonical_ref", "evidence_sha256", "scope")
    missing = [name for name in required if not authorization.get(name)]
    if missing:
        reasons.append("UNBOUND_APPROVAL_STRING")
        reasons.extend(GATE_F_CLOSED_REASONS)
        return GateFAssessment(
            status=GATE_F_NOT_OPENED,
            optional_deliverable="NOT_APPLICABLE_OPTIONAL_GATE_CLOSED",
            reasons=tuple(dict.fromkeys(reasons)),
        )
    digest = authorization.get("evidence_sha256")
    if not isinstance(digest, str) or not _SHA256_RE.match(digest):
        reasons.append("AUTHORIZATION_HASH_MALFORMED")
    if authorization.get("bytes_verified") is not True:
        reasons.append("AUTHORIZATION_BYTES_NOT_VERIFIED")
    if authorization.get("scope") != "OPTIONAL_ENERGY_ANALYSIS":
        reasons.append("AUTHORIZATION_SCOPE_MISMATCH")
    if not core_evidence_complete:
        reasons.append("CORE_EVIDENCE_INCOMPLETE")
    if reasons:
        return GateFAssessment(
            status=GATE_F_NOT_OPENED,
            optional_deliverable="NOT_APPLICABLE_OPTIONAL_GATE_CLOSED",
            reasons=tuple(dict.fromkeys(reasons)),
        )
    # W21 can validate the shape of a hypothetical artifact but cannot verify
    # the external authority that would open Gate F.  The optional scope stays
    # closed here and must be opened by a separate authorized activity.
    return GateFAssessment(
        status=GATE_F_NOT_OPENED,
        optional_deliverable="NOT_APPLICABLE_OPTIONAL_GATE_CLOSED",
        reasons=("AUTHORIZATION_NOT_VERIFIABLE_FROM_W21",),
    )


def audit_capabilities(
    paths: Sequence[Path], *, base: Path | None = None
) -> dict[str, Any]:
    """Static proof that W21 code has no control or actuation capability."""
    scanned: list[str] = []
    imports: set[str] = set()
    calls: set[str] = set()
    capabilities = {key: False for key in CAPABILITY_KEYS}
    for path in paths:
        path = Path(path)
        if not path.is_file():
            raise W21EvidenceError(f"capability audit target missing: {path}")
        if base is not None:
            scanned.append(path.relative_to(base).as_posix())
        else:
            scanned.append(path.as_posix())
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                target = ""
                if isinstance(node.func, ast.Name):
                    target = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    target = node.func.attr
                if target:
                    calls.add(target)
    forbidden_imports = sorted(imports & FORBIDDEN_IMPORTS)
    forbidden_calls = sorted(calls & FORBIDDEN_CALL_NAMES)
    if forbidden_imports:
        capabilities["instantiate_hardware_or_broker_client"] = True
        capabilities["publish_actuator_message"] = True
        capabilities["physical_fault_injection"] = True
    if forbidden_calls:
        capabilities["command_tec"] = True
        capabilities["publish_actuator_message"] = True
        capabilities["physical_fault_injection"] = True
        capabilities["activate_controller_b"] = True
        capabilities["change_policy_or_threshold"] = True
        capabilities["run_energy_experiment"] = True
    return {
        "files_scanned": scanned,
        "imports": sorted(imports),
        "calls": sorted(calls),
        "forbidden_imports": forbidden_imports,
        "forbidden_calls": forbidden_calls,
        "capabilities": capabilities,
    }


def require_no_capability(audit: Mapping[str, Any]) -> None:
    active = sorted(key for key, value in audit["capabilities"].items() if value)
    if active:
        raise W21EvidenceError(f"W21 code exposes forbidden capability: {active}")


def build_source_inventory(records: Sequence[SourceRecord]) -> list[dict[str, Any]]:
    validate_source_register(records)
    return [record.to_dict() for record in records]


def source_register_identity(records: Sequence[SourceRecord]) -> dict[str, Any]:
    validate_source_register(records)
    return {
        "schema": W21_SOURCE_REGISTER_SCHEMA,
        "source_count": len(records),
        "independent_session_count": count_independent_sessions(records),
        "register_sha256": canonical_sha256(
            [record.to_dict() for record in records]
        ),
    }


def source_bytes_match(record: SourceRecord, content: bytes) -> bool:
    if record.source_sha256 is None:
        return False
    if record.size_bytes is not None and len(content) != record.size_bytes:
        return False
    return sha256_bytes(content) == record.source_sha256


def normalize_door_state(value: str | None) -> str:
    """UNKNOWN stays UNKNOWN; it never becomes CLOSED or OPEN."""
    if value in {"OPEN", "CLOSED"}:
        return value
    return "UNKNOWN"


def normalize_temperature(quality: str, value: float | None) -> float | None:
    """An invalid, non-valid or non-finite temperature stays unusable."""
    if quality != "VALID" or value is None or not math.isfinite(value):
        return None
    return value


def electrical_measurement(
    quality: str, value: float | None, *, stale: bool
) -> dict[str, Any]:
    """Missing, invalid, stale or non-finite electrical data is never 0."""
    if (
        quality != "VALID"
        or stale
        or value is None
        or not math.isfinite(value)
    ):
        return {"status": "MISSING", "value": None}
    return {"status": "MEASURED", "value": value}


def energy_delta(previous_wh: float | None, current_wh: float | None) -> dict[str, Any]:
    if (
        previous_wh is None
        or current_wh is None
        or not math.isfinite(previous_wh)
        or not math.isfinite(current_wh)
    ):
        return {"status": "MISSING", "delta_wh": None}
    if current_wh < previous_wh:
        return {"status": "COUNTER_RESET_DETECTED", "delta_wh": None}
    return {"status": "OK", "delta_wh": current_wh - previous_wh}


def recovery_supported(
    recovery_observed: bool | None, recovery_valid_frames: int
) -> bool:
    return recovery_observed is True and recovery_valid_frames > 0


def predictive_training_eligible(evidence_class: str) -> bool:
    """W21 evidence never becomes predictive-model training data."""
    if evidence_class not in EVIDENCE_CLASS_RANK:
        return False
    return False


def degraded_model_inference_allowed(
    model_validated_for_missing_channel: bool,
) -> bool:
    return bool(model_validated_for_missing_channel)
