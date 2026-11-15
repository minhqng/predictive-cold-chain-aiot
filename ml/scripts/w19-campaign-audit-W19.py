"""W19 campaign-integrity driver (B-W19-01...04).

Validates the in-memory campaign state and a permanently marked synthetic
fixture, runs the ledger/validity/no-peeking/progress controls and writes a
deterministic W19 report family.  It never collects a physical run, dispatches a
command, changes a model/policy artifact, opens the W16 holdout or computes a
physical A/B outcome.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from coldguard_ml.w19_no_peeking import (
    ALLOWED_STOP_REASONS,
    ALLOWED_W19_COMPUTATIONS,
    FORBIDDEN_OUTCOME_FIELD_NAMES,
    FREEZE_FROZEN_APPROVED,
    PROHIBITED_W19_COMPUTATIONS,
    REGISTERED_SIGN_CONVENTION,
    STATISTICAL_FREEZE_FIELDS,
    W19OutcomeExposureError,
    W19PeekingError,
    assert_outcome_blind,
    audit_source_capability,
    classify_w19_operation,
    require_w19_operation,
    validate_stop_reason,
    w16_holdout_status,
)
from coldguard_ml.w19_pair_ledger import (
    AUTHORIZATION_AUTHORIZED,
    AUTHORIZATION_FAKE_APPROVAL,
    CAMPAIGN_FREEZE_FIELD_IDS,
    DEVELOPMENT_BASELINE_DOES_NOT_IMPLY_FREEZE,
    EVIDENCE_PHYSICAL_CAMPAIGN,
    FAILURE_INVALIDATE_PAIR,
    FIXTURE_MARKERS,
    FREEZE_STATUS_APPROVED,
    PAIR_LEDGER_LAYER_VERSION,
    PAIR_LEDGER_SCHEMA,
    PAIR_STATUSES,
    PAIR_VALID,
    W19LedgerError,
    assess_campaign_freeze,
    build_test_only_fixture_ledger,
    validate_pair_ledger,
)
from coldguard_ml.w19_progress import (
    TARGET_FROZEN,
    TARGET_NOT_APPROVED,
    TARGET_UNKNOWN_UNFROZEN,
    assess_pair_target,
    assess_target_change,
    compute_campaign_progress,
)
from coldguard_ml.w19_validity import (
    ALLOWED_INPUT_FIELDS,
    METRIC_CONTRACTS,
    PREDECLARED_VALIDITY_REASON_CODES,
    VALIDITY_INVALID,
    VALIDITY_VALID,
    VALIDITY_METHOD_VERSION,
    W19ValidityError,
    assess_attempt_validity,
)

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
W15_MODEL_MANIFEST = ML_ROOT / "reports" / "W15" / "model" / "model-manifest-W15.json"
W16_MANIFEST = ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"
W17_MANIFEST = ML_ROOT / "reports" / "W17" / "w17-manifest.json"
W18_MANIFEST = ML_ROOT / "reports" / "W18" / "w18-manifest.json"
W18_FREEZE_BASELINE = ML_ROOT / "reports" / "W18" / "freeze-baseline-W18.json"
STATISTICAL_PLAN = ML_ROOT / "statistical-analysis-plan-v0.md"
METRIC_SPEC = ML_ROOT / "metric-spec.md"
SAMPLE_SIZE_SCRIPT = ML_ROOT / "scripts" / "sample_size_planning.py"
W19_DIR = ML_ROOT / "reports" / "W19"
CAMPAIGN_RECORDS = W19_DIR / "campaign-records-W19.json"

W19_LAYER_VERSION = PAIR_LEDGER_LAYER_VERSION
W19_BASE_REVISION = "54c030ce9096a7e85b62570420f6596ff756d4f3"
W19_BASE_REVISION_SEMANTICS = "W18_STACK_HEAD_BASE_NOT_W19_DELIVERY_COMMIT"

EXPECTED_REPORTS = (
    "pair-ledger-contract-W19.md",
    "validity-discipline-W19.md",
    "no-significance-peeking-W19.md",
    "campaign-readiness-W19.md",
)

W19_SOURCE_FILES = (
    ML_ROOT / "src" / "coldguard_ml" / "w19_no_peeking.py",
    ML_ROOT / "src" / "coldguard_ml" / "w19_validity.py",
    ML_ROOT / "src" / "coldguard_ml" / "w19_pair_ledger.py",
    ML_ROOT / "src" / "coldguard_ml" / "w19_progress.py",
    ML_ROOT / "scripts" / "w19-campaign-audit-W19.py",
    ML_ROOT / "tests" / "test_w19_pair_ledger.py",
    ML_ROOT / "tests" / "test_w19_validity.py",
    ML_ROOT / "tests" / "test_w19_no_peeking.py",
    ML_ROOT / "tests" / "test_w19_progress.py",
    ML_ROOT / "tests" / "test_w19_delivery.py",
)

EVIDENCE_LABELS = (
    "Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17/W18 artifacts "
    "and Member B contracts), SYNTHETIC_SOFTWARE_FIXTURE (permanently marked "
    "W19 fixture ledger), DERIVED_SOFTWARE_ASSERTION (ledger/validity/progress "
    "results), EXTERNAL_DEPENDENCY (A/C/D and leader prerequisites), "
    "NOT_VERIFIED (absent physical campaign data)."
)

NEXT_MEMBER_B_ACTION = (
    "Prepare only W20 campaign-lock verification scaffolding (integrity "
    "precondition checks and frozen-target close-out reporting); do not open "
    "final physical-outcome analysis until the leader freezes the campaign "
    "target and Gate G4 is GREEN."
)


class W19DriverError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    _write(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
    )


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise W19DriverError(f"{label} is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_optional(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise W19DriverError(f"{path} must contain a JSON object")
    return payload


def _input_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ML_ROOT).as_posix(),
        "sha256": _sha256(path) if path.is_file() else "ABSENT",
        "present": path.is_file(),
    }


def _analysis_code_sha256() -> str:
    digest = hashlib.sha256()
    for path in W19_SOURCE_FILES:
        digest.update(path.relative_to(ML_ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(str(header) for header in headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def _campaign_document(
    records: Mapping[str, Any] | None, w18_g4: str
) -> tuple[dict[str, Any], str]:
    records = records or {}
    authorization = records.get("campaign_authorization")
    claim = "NO_AUTHORIZATION_RECORD"
    if isinstance(authorization, Mapping) and authorization.get("authorized") is True:
        if w18_g4 != "READY":
            claim = "REFUSED_BY_W18_G4_NOT_READY"
            authorization = dict(authorization)
            authorization["authorized"] = False
        else:
            claim = "AUTHORIZATION_CLAIM_PRESENT"
    document = {
        "schema": PAIR_LEDGER_SCHEMA,
        "campaign_id": str(
            records.get("campaign_id") or "CG-S2-FINAL-CAMPAIGN-UNREGISTERED"
        ),
        "evidence_class": EVIDENCE_PHYSICAL_CAMPAIGN,
        "analysis_plan_version": str(
            records.get("analysis_plan_version") or "w03-analysis-contract-v1"
        ),
        "campaign_authorization": authorization,
        "campaign_freeze": records.get("campaign_freeze"),
        "matching_policy": records.get("matching_policy"),
        "failure_policy": records.get("failure_policy"),
        "randomization": records.get("randomization"),
        "frozen_target": records.get("frozen_target"),
        "statistical_freeze": records.get("statistical_freeze"),
        "pairs": records.get("pairs") or [],
        "attempts": records.get("attempts") or [],
    }
    return document, claim


def _validity_input(
    *,
    arm: str = "B",
    quality_status: str = "QUALITY_PASS",
    completeness: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "attempt_id": "ATT-VALIDITY-PROBE",
        "pair_id": "PAIR-VALIDITY-PROBE",
        "run_id": "RUN-VALIDITY-PROBE",
        "controller_arm": arm,
        "hardware_config_id": "CG-HW-FIXTURE-001",
        "calibration_id": "CG-CAL-FIXTURE-001",
        "firmware_version": "fw-fixture-1.0.0",
        "protocol_version": "test-fixture-protocol-v1",
        "disturbance_execution": "EXECUTED_WITHIN_TOLERANCE",
        "reset_criterion": "MET_VERIFIED",
        "quality_status": quality_status,
        "completeness": dict(
            completeness
            or {
                "thermal_primary": "COMPLETE",
                "thermal_recovery": "COMPLETE",
                "electrical_energy": "COMPLETE",
            }
        ),
        "time_sequence_validity": "VALID",
        "controller_order_recorded": True,
        "safety_stop_recorded": False,
        "operator_intervention": "NONE",
    }


def _expect_raises(exception_type: type[BaseException], fn: Callable[[], Any]) -> bool:
    try:
        fn()
    except exception_type:
        return True
    except Exception:
        return False
    return False


def _probe(name: str, fn: Callable[[], bool], expectation: str) -> dict[str, Any]:
    passed = bool(fn())
    return {"name": name, "passed": passed, "expectation": expectation}


def _ledger_controls() -> list[dict[str, Any]]:
    base = build_test_only_fixture_ledger()
    baseline = validate_pair_ledger(base)
    probes: list[dict[str, Any]] = []

    probes.append(
        _probe(
            "valid_pair_control",
            lambda: baseline.pairs[0].status == PAIR_VALID
            and baseline.software_valid_pairs == 1
            and baseline.physical_valid_pairs == 0,
            "one protocol-valid synthetic pair is PAIR_VALID but never physically admitted",
        )
    )

    def mutated(mutator: Callable[[dict[str, Any]], None]) -> Any:
        document = copy.deepcopy(base)
        mutator(document)
        return validate_pair_ledger(document)

    def two_a_arms() -> bool:
        result = mutated(lambda d: d["attempts"][1].__setitem__("controller_arm", "A"))
        return (
            result.pairs[0].status != PAIR_VALID
            and "AMBIGUOUS_ARM_HISTORY" in result.pairs[0].reason_codes
        )

    probes.append(
        _probe("two_a_arms_refused", two_a_arms, "two A arms cannot form a pair")
    )

    def three_arms() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            extra = copy.deepcopy(doc["attempts"][1])
            extra["attempt_id"] = "ATT-TEST-001-B2"
            extra["run_id"] = "RUN-TEST-001-B2"
            extra["source_sha256"] = hashlib.sha256(b"extra-B").hexdigest()
            extra["source_path"] = "test://w19/fixture/run-B2"
            doc["attempts"].append(extra)
            doc["pairs"][0]["attempt_ids"].append(extra["attempt_id"])

        result = mutated(mutate)
        return result.pairs[0].status != PAIR_VALID

    probes.append(
        _probe("three_arms_refused", three_arms, "three terminal arms are ambiguous")
    )

    def duplicate_run() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            extra = copy.deepcopy(doc["attempts"][0])
            extra["attempt_id"] = "ATT-TEST-001-A2"
            extra["source_sha256"] = hashlib.sha256(b"extra-A").hexdigest()
            extra["source_path"] = "test://w19/fixture/run-A2"
            doc["attempts"].append(extra)
            doc["pairs"][0]["attempt_ids"].append(extra["attempt_id"])

        result = mutated(mutate)
        return "DUPLICATE_RUN_ID_ACROSS_RECORDS" in result.refusal_reasons

    probes.append(
        _probe("duplicate_run_id_refused", duplicate_run, "a run id may appear once")
    )

    def duplicate_source() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            extra = copy.deepcopy(doc["attempts"][1])
            extra["attempt_id"] = "ATT-TEST-001-B2"
            extra["run_id"] = "RUN-TEST-001-B2"
            extra["source_path"] = "test://w19/fixture/run-B2"
            doc["attempts"].append(extra)
            doc["pairs"][0]["attempt_ids"].append(extra["attempt_id"])

        result = mutated(mutate)
        return "DUPLICATE_SOURCE_SHA256_ACROSS_RECORDS" in result.refusal_reasons

    probes.append(
        _probe(
            "duplicate_source_refused",
            duplicate_source,
            "one physical source cannot appear twice",
        )
    )

    def scenario_mismatch() -> bool:
        result = mutated(
            lambda d: d["attempts"][1].__setitem__("scenario_id", "S9_OTHER_SCENARIO")
        )
        return (
            result.pairs[0].status != PAIR_VALID
            and "SCENARIO_MISMATCH" in result.pairs[0].reason_codes
        )

    probes.append(
        _probe("scenario_mismatch_refused", scenario_mismatch, "scenario must match")
    )

    def hardware_mismatch() -> bool:
        result = mutated(
            lambda d: d["attempts"][1].__setitem__(
                "hardware_config_id", "CG-HW-OTHER"
            )
        )
        return "HARDWARE_CONFIG_MISMATCH" in result.pairs[0].reason_codes

    probes.append(
        _probe(
            "hardware_mismatch_refused",
            hardware_mismatch,
            "hardware configuration must match",
        )
    )

    def calibration_mismatch() -> bool:
        result = mutated(
            lambda d: d["attempts"][1].__setitem__("calibration_id", "CG-CAL-OTHER")
        )
        return "CALIBRATION_LINEAGE_MISMATCH" in result.pairs[0].reason_codes

    probes.append(
        _probe(
            "calibration_mismatch_refused",
            calibration_mismatch,
            "calibration lineage must match",
        )
    )

    def order_deviation() -> bool:
        result = mutated(
            lambda d: d["pairs"][0].__setitem__(
                "actual_controller_order", ["B", "A"]
            )
        )
        return "CONTROLLER_ORDER_DEVIATION" in result.pairs[0].reason_codes

    probes.append(
        _probe(
            "order_deviation_refused",
            order_deviation,
            "actual order must follow the registered order",
        )
    )

    def randomization_missing() -> bool:
        result = mutated(
            lambda d: d.__setitem__(
                "randomization", {"status": "NOT_REGISTERED", "order_list": None,
                                   "seed": None, "canonical_ref": None}
            )
        )
        return (
            result.pairs[0].status == "PAIR_BLOCKED_MISSING_FREEZE"
            and "RANDOMIZATION_NOT_REGISTERED" in result.pairs[0].reason_codes
        )

    probes.append(
        _probe(
            "randomization_missing_blocks",
            randomization_missing,
            "an unregistered order cannot produce a valid pair",
        )
    )

    def matching_unfrozen() -> bool:
        result = mutated(
            lambda d: d["matching_policy"].__setitem__("status", "NOT_FROZEN")
        )
        return (
            result.pairs[0].status == "PAIR_BLOCKED_MISSING_FREEZE"
            and "PAIR_MATCHING_TOLERANCES_UNFROZEN" in result.pairs[0].reason_codes
        )

    probes.append(
        _probe(
            "unfrozen_tolerances_block",
            matching_unfrozen,
            "pilot-era tolerances are not an approved matching policy",
        )
    )

    def initial_delta() -> bool:
        result = mutated(
            lambda d: d["pairs"][0]["initial_state"]["arms"]["B"].__setitem__(
                "initial_tmean_c", 25.0
            )
        )
        return "INITIAL_TMEAN_DELTA_EXCEEDED" in result.pairs[0].reason_codes

    probes.append(
        _probe(
            "initial_tolerance_refused",
            initial_delta,
            "initial-state delta beyond the frozen tolerance invalidates the pair",
        )
    )

    def invalid_arm_unfrozen_policy() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            doc["failure_policy"]["status"] = "NOT_FROZEN"
            attempt = doc["attempts"][1]
            attempt["quality_status"] = "QUALITY_FAIL"
            attempt["validity_status"] = "INVALID"
            attempt["validity_reason_codes"] = ["PHYSICAL_QUALITY_INVALID"]

        result = mutated(mutate)
        return (
            result.pairs[0].status == "PAIR_BLOCKED_MISSING_FREEZE"
            and "INVALID_ARM_HANDLING_UNFROZEN" in result.pairs[0].reason_codes
        )

    probes.append(
        _probe(
            "invalid_arm_requires_frozen_rule",
            invalid_arm_unfrozen_policy,
            "a failure cannot trigger an automatic rerun or invalidation",
        )
    )

    def invalid_arm_rerun_pending() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            attempt = doc["attempts"][1]
            attempt["quality_status"] = "QUALITY_FAIL"
            attempt["validity_status"] = "INVALID"
            attempt["validity_reason_codes"] = ["PHYSICAL_QUALITY_INVALID"]

        result = mutated(mutate)
        return (
            result.pairs[0].status == "PAIR_UNRESOLVED"
            and "PERMISSIBLE_RERUN_NOT_COMPLETED" in result.pairs[0].reason_codes
        )

    probes.append(
        _probe(
            "invalid_arm_rerun_pending",
            invalid_arm_rerun_pending,
            "an invalid arm contributes zero valid pairs until a rerun completes",
        )
    )

    def rerun_preserves_history() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            original = doc["attempts"][1]
            original["quality_status"] = "QUALITY_FAIL"
            original["validity_status"] = "INVALID"
            original["validity_reason_codes"] = ["PHYSICAL_QUALITY_INVALID"]
            rerun = copy.deepcopy(original)
            rerun["attempt_id"] = "ATT-TEST-001-B-R1"
            rerun["run_id"] = "RUN-TEST-001-B-R1"
            rerun["attempt_kind"] = "RERUN"
            rerun["supersedes"] = original["attempt_id"]
            rerun["superseded_by"] = None
            rerun["quality_status"] = "QUALITY_PASS"
            rerun["validity_status"] = "VALID"
            rerun["validity_reason_codes"] = []
            rerun["source_sha256"] = hashlib.sha256(b"rerun-B").hexdigest()
            rerun["source_path"] = "test://w19/fixture/run-B-rerun"
            rerun["audit_events"] = [
                {"seq": 1, "event": "ATTEMPT_CREATED", "actor": "test-fixture"},
                {"seq": 2, "event": "RERUN_RECORDED", "actor": "test-fixture"},
                {"seq": 3, "event": "VALIDITY_RECORDED", "actor": "test-fixture"},
            ]
            original["superseded_by"] = rerun["attempt_id"]
            original["audit_events"] = original["audit_events"] + [
                {"seq": 3, "event": "ATTEMPT_SUPERSEDED", "actor": "test-fixture"}
            ]
            doc["attempts"].append(rerun)
            doc["pairs"][0]["attempt_ids"].append(rerun["attempt_id"])

        result = mutated(mutate)
        return (
            result.pairs[0].status == PAIR_VALID
            and result.attempt_accounting.superseded_attempts == 1
            and result.attempt_accounting.invalid_attempts == 1
        )

    probes.append(
        _probe(
            "rerun_preserves_attempt_history",
            rerun_preserves_history,
            "a permitted rerun keeps the invalid attempt and the original pair identity",
        )
    )

    def fixture_in_physical() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            doc["evidence_class"] = EVIDENCE_PHYSICAL_CAMPAIGN

        result = mutated(mutate)
        return (
            "FIXTURE_MARKER_IN_PHYSICAL_LEDGER" in result.refusal_reasons
            and result.pairs[0].status != PAIR_VALID
            and not result.physical_pair_evidence_accepted
        )

    probes.append(
        _probe(
            "fixture_in_physical_refused",
            fixture_in_physical,
            "a marked fixture can never enter a physical ledger",
        )
    )

    def outcome_injection() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            doc["attempts"][0]["thermal_exposure"] = 12.5

        return _expect_raises(
            W19OutcomeExposureError,
            lambda: mutated(mutate),
        )

    probes.append(
        _probe(
            "outcome_injection_refused",
            outcome_injection,
            "an outcome column cannot enter the ledger validation route",
        )
    )

    def missing_source_hash() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            del doc["attempts"][0]["source_sha256"]

        return _expect_raises(W19LedgerError, lambda: mutated(mutate))

    probes.append(
        _probe(
            "missing_source_hash_refused",
            missing_source_hash,
            "an attempt without a source hash is not physical evidence",
        )
    )

    def fake_authorization() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            doc["campaign_authorization"] = {
                "authorized": True,
                "authority_id": "",
                "authority_role": "TEAM_LEAD",
                "canonical_ref": "",
                "g4_status": "NOT_READY",
                "pair_target_frozen": False,
                "analysis_freeze_accepted": False,
            }

        result = mutated(mutate)
        return result.authorization["status"] == AUTHORIZATION_FAKE_APPROVAL

    probes.append(
        _probe(
            "fake_authorization_refused",
            fake_authorization,
            "an authorization claim without authority/evidence is refused",
        )
    )

    def fixture_never_authorized() -> bool:
        authorized = baseline.authorization["status"] == AUTHORIZATION_AUTHORIZED
        return not authorized and baseline.physical_valid_pairs == 0

    probes.append(
        _probe(
            "fixture_never_authorized",
            fixture_never_authorized,
            "a synthetic ledger cannot claim physical authorization",
        )
    )

    def rerun_of_valid_arm_refused() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            original = next(
                attempt
                for attempt in doc["attempts"]
                if attempt["controller_arm"] == "B"
            )
            rerun = copy.deepcopy(original)
            rerun["attempt_id"] = "ATT-TEST-001-B-R1"
            rerun["run_id"] = "RUN-TEST-001-B-R1"
            rerun["attempt_kind"] = "RERUN"
            rerun["supersedes"] = original["attempt_id"]
            rerun["source_sha256"] = hashlib.sha256(
                b"rerun-of-valid-B"
            ).hexdigest()
            rerun["source_path"] = "test://w19/fixture/run-B-rerun"
            original["superseded_by"] = rerun["attempt_id"]
            original["audit_events"] = original["audit_events"] + [
                {"seq": 3, "event": "ATTEMPT_SUPERSEDED", "actor": "test-fixture"}
            ]
            doc["attempts"].append(rerun)
            doc["pairs"][0]["attempt_ids"].append(rerun["attempt_id"])

        result = mutated(mutate)
        return (
            result.pairs[0].status == "PAIR_INVALID"
            and "RERUN_OF_NON_INVALID_ARM_REFUSED" in result.pairs[0].reason_codes
            and result.software_valid_pairs == 0
        )

    probes.append(
        _probe(
            "rerun_of_valid_arm_refused",
            rerun_of_valid_arm_refused,
            "a protocol-valid arm cannot be replaced by an eligible-looking rerun",
        )
    )

    def invalidate_pair_policy_not_bypassed() -> bool:
        def mutate(doc: dict[str, Any]) -> None:
            doc["failure_policy"]["invalid_arm_handling"] = FAILURE_INVALIDATE_PAIR
            original = next(
                attempt
                for attempt in doc["attempts"]
                if attempt["controller_arm"] == "B"
            )
            original["quality_status"] = "QUALITY_FAIL"
            original["validity_status"] = "INVALID"
            original["validity_reason_codes"] = ["PHYSICAL_QUALITY_INVALID"]
            rerun = copy.deepcopy(original)
            rerun["attempt_id"] = "ATT-TEST-001-B-R1"
            rerun["run_id"] = "RUN-TEST-001-B-R1"
            rerun["attempt_kind"] = "RERUN"
            rerun["supersedes"] = original["attempt_id"]
            rerun["quality_status"] = "QUALITY_PASS"
            rerun["validity_status"] = "VALID"
            rerun["validity_reason_codes"] = []
            rerun["source_sha256"] = hashlib.sha256(b"bypass-rerun").hexdigest()
            rerun["source_path"] = "test://w19/fixture/run-B-bypass"
            original["superseded_by"] = rerun["attempt_id"]
            original["audit_events"] = original["audit_events"] + [
                {"seq": 3, "event": "ATTEMPT_SUPERSEDED", "actor": "test-fixture"}
            ]
            doc["attempts"].append(rerun)
            doc["pairs"][0]["attempt_ids"].append(rerun["attempt_id"])

        result = mutated(mutate)
        return (
            result.pairs[0].status == "PAIR_INVALID"
            and "FROZEN_POLICY_INVALIDATES_PAIR" in result.pairs[0].reason_codes
            and result.software_valid_pairs == 0
        )

    probes.append(
        _probe(
            "invalidate_policy_not_bypassed_by_rerun",
            invalidate_pair_policy_not_bypassed,
            "a frozen INVALIDATE_PAIR rule cannot be bypassed by a rerun",
        )
    )

    def null_freeze_value_not_approved() -> bool:
        fields = {
            field_id: {
                "value": f"FROZEN-{field_id}",
                "provenance": "test://w19/fixture-freeze",
                "status": FREEZE_FROZEN_APPROVED,
            }
            for field_id in CAMPAIGN_FREEZE_FIELD_IDS
        }
        fields["operating_threshold"]["value"] = None
        assessment = assess_campaign_freeze(
            {
                "fields": fields,
                "approval": {
                    "authority_id": "TEST_FIXTURE_ONLY",
                    "authority_role": "TEAM_LEAD",
                    "canonical_ref": "test://w19/fixture-freeze-approval",
                },
            }
        )
        return assessment.freeze_status != FREEZE_STATUS_APPROVED

    probes.append(
        _probe(
            "null_freeze_value_not_approved",
            null_freeze_value_not_approved,
            "a frozen field without a value blocks campaign freeze approval",
        )
    )

    return probes


def _validity_controls() -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []

    def protocol_valid_worse_b() -> bool:
        decision = assess_attempt_validity(_validity_input(arm="B"))
        return (
            decision.validity_status == VALIDITY_VALID
            and decision.primary_pair_eligible
            and decision.outcome_fields_used is False
        )

    probes.append(
        _probe(
            "protocol_valid_worse_b_retained",
            protocol_valid_worse_b,
            "a protocol-valid B arm stays valid regardless of performance",
        )
    )

    def protocol_invalid_better_b() -> bool:
        decision = assess_attempt_validity(
            _validity_input(arm="B", quality_status="QUALITY_FAIL")
        )
        return (
            decision.validity_status == VALIDITY_INVALID
            and "PHYSICAL_QUALITY_INVALID" in decision.reason_codes
        )

    probes.append(
        _probe(
            "protocol_invalid_better_b_rejected",
            protocol_invalid_better_b,
            "a protocol-invalid B arm is rejected regardless of performance",
        )
    )

    def swap_arms_invariant() -> bool:
        a = assess_attempt_validity(_validity_input(arm="A"))
        b = assess_attempt_validity(_validity_input(arm="B"))
        return (
            a.validity_status == b.validity_status
            and a.reason_codes == b.reason_codes
        )

    probes.append(
        _probe(
            "arm_swap_does_not_change_validity",
            swap_arms_invariant,
            "controller-arm identity is not an outcome and cannot change validity",
        )
    )

    def outcome_payload_refused() -> bool:
        payload = _validity_input()
        payload["p_value"] = 0.04
        return _expect_raises(
            W19OutcomeExposureError,
            lambda: assess_attempt_validity(payload),
        )

    probes.append(
        _probe(
            "validity_outcome_payload_refused",
            outcome_payload_refused,
            "the validity route refuses outcome-shaped fields",
        )
    )

    def energy_missing_not_zero() -> bool:
        decision = assess_attempt_validity(
            _validity_input(
                completeness={
                    "thermal_primary": "COMPLETE",
                    "thermal_recovery": "COMPLETE",
                    "electrical_energy": "MISSING",
                }
            )
        )
        energy = next(
            metric
            for metric in decision.metric_admissibility
            if metric.metric_id == "branch_energy"
        )
        serialized = decision.to_dict()
        return (
            decision.validity_status == VALIDITY_VALID
            and decision.primary_pair_eligible
            and energy.admissibility == "UNDEFINED_INCOMPLETE"
            and "branch_energy_value" not in serialized
        )

    probes.append(
        _probe(
            "missing_energy_stays_undefined",
            energy_missing_not_zero,
            "missing PZEM coverage is undefined, never zero energy",
        )
    )

    def thermal_missing_invalidates() -> bool:
        decision = assess_attempt_validity(
            _validity_input(
                completeness={
                    "thermal_primary": "MISSING",
                    "thermal_recovery": "COMPLETE",
                    "electrical_energy": "COMPLETE",
                }
            )
        )
        return (
            decision.validity_status == VALIDITY_INVALID
            and "TELEMETRY_GAP_COVERS_PRIMARY_EVENT" in decision.reason_codes
            and not decision.primary_pair_eligible
        )

    probes.append(
        _probe(
            "primary_gap_invalidates",
            thermal_missing_invalidates,
            "a primary-outcome telemetry gap invalidates the attempt",
        )
    )

    def invalid_decision_has_reasons() -> bool:
        decision = assess_attempt_validity(
            _validity_input(quality_status="QUALITY_FAIL")
        )
        return decision.validity_status == VALIDITY_INVALID and bool(
            decision.reason_codes
        )

    probes.append(
        _probe(
            "invalid_decision_records_reasons",
            invalid_decision_has_reasons,
            "no refusal without objective, recorded reasons",
        )
    )

    def input_has_no_outcome_fields() -> bool:
        signature = inspect.signature(assess_attempt_validity)
        parameters = set(signature.parameters)
        fields = set(ALLOWED_INPUT_FIELDS)
        return not (parameters | fields) & FORBIDDEN_OUTCOME_FIELD_NAMES

    probes.append(
        _probe(
            "validity_input_carries_no_outcomes",
            input_has_no_outcome_fields,
            "the validity API has no outcome parameter or field",
        )
    )

    return probes


def _no_peeking_controls(
    source_audit: Any, holdout_status: str
) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []

    probes.append(
        _probe(
            "static_source_capability_audit",
            lambda: source_audit.passed,
            "no W19 source imports or calls an outcome-analysis capability",
        )
    )

    probes.append(
        _probe(
            "prohibited_operation_refused",
            lambda: _expect_raises(
                W19PeekingError,
                lambda: require_w19_operation("headline_p_value"),
            ),
            "a prohibited computation identifier is refused at runtime",
        )
    )

    probes.append(
        _probe(
            "unknown_operation_refused",
            lambda: _expect_raises(
                W19PeekingError,
                lambda: require_w19_operation("not_a_declared_operation"),
            ),
            "the guard fails closed for unknown operations",
        )
    )

    probes.append(
        _probe(
            "allowed_operation_is_outcome_blind",
            lambda: (
                classify_w19_operation("pair_eligibility").outcome_access is False
                and not classify_w19_operation("pair_eligibility").outcome_access
            ),
            "allowed operations carry no outcome access",
        )
    )

    probes.append(
        _probe(
            "outcome_payload_refused_globally",
            lambda: _expect_raises(
                W19OutcomeExposureError,
                lambda: assert_outcome_blind({"p_value": 0.04}),
            ),
            "an outcome-shaped payload is refused before use",
        )
    )

    probes.append(
        _probe(
            "statistical_stop_reason_refused",
            lambda: validate_stop_reason(
                "FAVORABLE_INTERIM_RESULT", "test://interim-note"
            ).decision
            == "STOP_REFUSED",
            "a favorable interim result is not a permitted stop reason",
        )
    )

    probes.append(
        _probe(
            "safety_stop_is_operational",
            lambda: (
                validate_stop_reason(
                    "SAFETY_RESTRICTION", "test://safety-log"
                ).decision
                == "STOP_PERMITTED_OPERATIONAL_REASON"
                and validate_stop_reason(
                    "SAFETY_RESTRICTION", "test://safety-log"
                ).effect_on_analysis
                == "OPERATIONAL_STOP_NOT_STATISTICAL_EVIDENCE"
            ),
            "a safety stop is operational evidence, never a statistical win",
        )
    )

    probes.append(
        _probe(
            "w16_holdout_isolated",
            lambda: holdout_status == "NOT_OPENED",
            "the W16 locked holdout is not opened by W19",
        )
    )

    return probes


def _progress_controls(ledger: Any) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    fixture = validate_pair_ledger(build_test_only_fixture_ledger())

    probes.append(
        _probe(
            "missing_target_stays_unknown",
            lambda: (
                compute_campaign_progress(fixture, target_record=None).pair_target_freeze_status
                == TARGET_UNKNOWN_UNFROZEN
                and compute_campaign_progress(
                    fixture, target_record=None
                ).remaining_target
                == "NOT_COMPUTABLE"
            ),
            "a missing target is UNKNOWN_UNFROZEN, never a numeric zero",
        )
    )

    def invalid_target_control() -> bool:
        record = {
            "status": "FROZEN_APPROVED",
            "planned_pair_target": 16,
            "approval": {
                "authority_id": "TEST_FIXTURE_ONLY",
                "authority_role": "TEAM_LEAD",
                "canonical_ref": "test://w19/fixture-target",
            },
            "variance_justification_ref": None,
        }
        return assess_pair_target(record).status == TARGET_NOT_APPROVED

    probes.append(
        _probe(
            "unjustified_target_not_approved",
            invalid_target_control,
            "a planning number without approval/justification is not a target",
        )
    )

    def synthetic_excluded() -> bool:
        target = {
            "status": "FROZEN_APPROVED",
            "planned_pair_target": 2,
            "approval": {
                "authority_id": "TEST_FIXTURE_ONLY",
                "authority_role": "TEAM_LEAD",
                "canonical_ref": "test://w19/fixture-target",
            },
            "variance_justification_ref": "test://w19/fixture-variance",
        }
        progress = compute_campaign_progress(fixture, target_record=target)
        return (
            progress.valid_pairs_completed == 0
            and progress.software_validated_pairs == 1
            and progress.valid_pair_progress_status == "NOT_ESTABLISHED"
            and progress.remaining_target == "NOT_COMPUTABLE"
            and progress.first_wave_status == "NOT_COMPUTABLE"
        )

    probes.append(
        _probe(
            "synthetic_fixture_never_counts",
            synthetic_excluded,
            "fixture pairs never contribute to physical progress or the 50% wave",
        )
    )

    probes.append(
        _probe(
            "unavailable_ledger_distinguished",
            lambda: (
                compute_campaign_progress(None).invalid_attempts is None
                and compute_campaign_progress(None).invalid_attempts_status
                == "UNKNOWN_ATTEMPT_LEDGER_UNAVAILABLE"
            ),
            "an unavailable attempt ledger is not reported as zero invalid attempts",
        )
    )

    def target_change_guard() -> bool:
        current = None
        proposed = {
            "status": "FROZEN_APPROVED",
            "planned_pair_target": 2,
            "approval": {
                "authority_id": "TEST_FIXTURE_ONLY",
                "authority_role": "TEAM_LEAD",
                "canonical_ref": "test://w19/fixture-target",
            },
            "variance_justification_ref": "test://w19/fixture-variance",
        }
        return (
            assess_target_change(
                current, proposed, valid_pairs_completed=1
            ).decision
            == "REFUSED_AFTER_CAMPAIGN_START"
        )

    probes.append(
        _probe(
            "post_start_target_change_refused",
            target_change_guard,
            "the target cannot change once pairs are recorded",
        )
    )

    def recorded_pairs_guard() -> bool:
        proposed = {
            "status": "FROZEN_APPROVED",
            "planned_pair_target": 4,
            "approval": {
                "authority_id": "TEST_FIXTURE_ONLY",
                "authority_role": "TEAM_LEAD",
                "canonical_ref": "test://w19/fixture-target",
            },
            "variance_justification_ref": "test://w19/fixture-variance",
        }
        decision = assess_target_change(
            None, proposed, valid_pairs_completed=0, pairs_recorded=3
        )
        return decision.decision == "REFUSED_AFTER_CAMPAIGN_START"

    probes.append(
        _probe(
            "recorded_invalid_pairs_block_target_change",
            recorded_pairs_guard,
            "recorded pairs, even if invalid, freeze the denominator",
        )
    )

    def synthetic_authorization_cannot_establish_progress() -> bool:
        document = build_test_only_fixture_ledger()
        document["campaign_authorization"] = {
            "authorized": True,
            "authority_id": "TEST_FIXTURE_ONLY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "test://w19/fixture-authorization",
            "g4_status": "READY",
            "pair_target_frozen": True,
            "analysis_freeze_accepted": True,
        }
        ledger = validate_pair_ledger(document)
        progress = compute_campaign_progress(ledger)
        return (
            progress.valid_pair_progress_status == "NOT_ESTABLISHED"
            and progress.physical_campaign_status == "NOT_STARTED_BLOCKED"
            and progress.valid_pairs_completed == 0
        )

    probes.append(
        _probe(
            "synthetic_ledger_cannot_establish_progress",
            synthetic_authorization_cannot_establish_progress,
            "a synthetic ledger never establishes physical campaign progress",
        )
    )

    return probes


def _report_header(title: str) -> list[str]:
    return [
        f"# {title}",
        "",
        "Evidence class: SYNTHETIC_SOFTWARE_CONTROL_ONLY (software verification; "
        "no physical campaign data).",
        "",
        EVIDENCE_LABELS,
        "",
    ]


def _verdict_block(lines: Sequence[str]) -> list[str]:
    return ["```text", *lines, "```", ""]


def _pair_ledger_report(
    source_revision: str,
    controls: Sequence[Mapping[str, Any]],
    validation: Any,
) -> str:
    physical_evidence = (
        "ACCEPTED" if validation.physical_pair_evidence_accepted else "NOT_ESTABLISHED"
    )
    document = build_test_only_fixture_ledger()
    lines = _report_header("W19 Pair-Ledger Contract (B-W19-01)")
    lines += [
        "## Scope",
        "",
        f"Schema: `{PAIR_LEDGER_SCHEMA}`; layer: `{PAIR_LEDGER_LAYER_VERSION}`; "
        f"base revision `{source_revision}` ({W19_BASE_REVISION_SEMANTICS}).",
        "",
        "The statistical unit is one valid matched Controller A/B pair. A physical "
        "run is one arm of a pair; a telemetry row or feature window is never an "
        "independent A/B observation. One pair contributes at most one paired "
        "observation to the eventual W20 analysis.",
        "",
        "## Pair identity fields",
        "",
    ]
    lines += _table(
        ("Field", "Level", "Rule"),
        [
            ("pair_id", "pair", "unique ledger identity"),
            ("campaign_id / scenario_id / block_id / session_id", "pair + attempt", "must agree"),
            ("planned_controller_order", "pair", "registered A/B permutation"),
            ("actual_controller_order", "pair", "recorded permutation, must equal planned"),
            ("run_id / attempt_id", "attempt", "globally unique"),
            ("controller_arm", "attempt", "A or B; exactly one selected terminal arm each"),
            ("hardware_config_id / calibration_id / firmware_version", "attempt", "match across arms and campaign freeze"),
            ("model_artifact_id / model_artifact_sha256 / feature_version", "attempt", "Controller B identity; frozen model only"),
            ("policy_version / protocol_version / disturbance_protocol_id", "attempt", "frozen controller/protocol identity"),
            ("source_path / source_manifest_id / source_sha256", "attempt", "provenance; SHA-256 bound"),
            ("quality_status / validity_status / validity_reason_codes", "attempt", "predeclared outcomes only"),
            ("validity_method / audit_events / corrections", "attempt", "append-only decision history"),
            ("initial_state", "pair", "comparability evidence and criterion version"),
        ],
    )
    lines += [
        "",
        "## Pair state machine",
        "",
    ]
    lines += _table(
        ("Status", "Transition evidence"),
        [
            ("PLANNED", "pair exists, no attempt recorded"),
            ("AWAITING_SECOND_ARM", "exactly one terminal arm recorded"),
            ("AWAITING_VALIDITY", "both arms recorded, validity review pending"),
            ("PAIR_VALID", "both arms VALID + matching + registered order + frozen tolerances + initial comparability"),
            ("PAIR_INVALID", "a proven protocol/matching/comparability violation, or the frozen rule invalidates the pair"),
            ("PAIR_BLOCKED_MISSING_FREEZE", "an invalid-arm rule, matching policy or registered order is not frozen"),
            ("PAIR_UNRESOLVED", "ambiguous history, missing evidence, duplicate identity, drift or an incomplete rerun"),
        ],
    )
    lines += [
        "",
        "A pair never becomes VALID merely because two run IDs exist.",
        "",
        "## Attempt history and rerun semantics",
        "",
        "Every attempt is retained: initial, aborted, invalid, eligible reruns and "
        "superseded attempts. A rerun keeps the original `pair_id` and controller "
        "arm, declares `supersedes`, and the superseded record keeps its invalid "
        "status. Reusing the same `run_id` or source hash anywhere is refused. "
        "Corrections are explicit records; nothing is silently overwritten.",
        "",
        "## Synthetic fixture policy",
        "",
        "Every fixture attempt carries `TEST_ONLY` and "
        "`SYNTHETIC_SOFTWARE_CONTROL_ONLY`. A fixture-marked record can never be "
        "physically admitted, and a synthetic ledger cannot claim authorization.",
        "",
        f"Fixture pairs: {len(document['pairs'])}; fixture attempts: "
        f"{len(document['attempts'])}. Full pair rows are not reported as campaign data.",
        "",
        "## Adversarial controls",
        "",
    ]
    lines += _table(
        ("Control", "Expectation", "Passed"),
        [[probe["name"], probe["expectation"], probe["passed"]] for probe in controls],
    )
    lines += [""]
    lines += _verdict_block(
        [
            "PAIR_LEDGER_SCHEMA = VERIFIED",
            "PAIR_LEDGER_SOFTWARE = VERIFIED",
            f"PHYSICAL_PAIR_LEDGER_EVIDENCE = {physical_evidence}",
            "SYNTHETIC_FIXTURES_ADMITTED = 0",
        ]
    )
    lines += [
        "No approval, signature, date or signoff record is fabricated by this report.",
        "",
    ]
    return "\n".join(lines)


def _validity_report(controls: Sequence[Mapping[str, Any]]) -> str:
    lines = _report_header("W19 Outcome-Blinded Validity Discipline (B-W19-02)")
    lines += [
        "## Separation of validity and outcome",
        "",
        "Validity review asks whether a run met the frozen protocol. Outcome "
        "analysis asks whether Controller B improved the physical result. W19 "
        "implements only the former; final outcome analysis remains locked to W20.",
        "",
        "The validity input contract carries identity, hardware/calibration "
        "provenance, protocol version, disturbance execution, reset eligibility, "
        "quality/completeness flags, time/sequence validity, the controller-order "
        "record and predeclared reason codes. It has no exposure, recovery, energy, "
        "p-value or effect-size field, so treatment direction cannot enter the decision.",
        "",
        "## Predeclared reason codes",
        "",
    ]
    lines += _table(
        ("Reason code",),
        [[code] for code in sorted(PREDECLARED_VALIDITY_REASON_CODES)],
    )
    lines += [
        "",
        "## Metric-specific completeness",
        "",
    ]
    lines += _table(
        ("Metric", "Role", "Coverage key", "Rule"),
        [
            (
                contract.metric_id,
                contract.role,
                contract.coverage_key,
                "missing/incomplete primary coverage invalidates the attempt; a "
                "missing secondary metric is UNDEFINED_INCOMPLETE, never zero-filled",
            )
            for contract in METRIC_CONTRACTS
        ],
    )
    lines += [
        "",
        "## Invariants",
        "",
        "- A pair where Controller B performs worse can still be perfectly valid.",
        "- A pair where Controller B performs better is rejected when protocol-invalid.",
        "- Swapping A/B performance cannot change eligibility because performance is "
        "not an input.",
        "- An invalid primary arm cannot count as a valid pair.",
        "- A decision without objective recorded reasons is structurally refused.",
        "- Missing PZEM coverage is reported as undefined, never as zero energy.",
        "",
        "## Controls",
        "",
    ]
    lines += _table(
        ("Control", "Expectation", "Passed"),
        [[probe["name"], probe["expectation"], probe["passed"]] for probe in controls],
    )
    lines += [""]
    lines += _verdict_block(
        [
            "VALIDITY_REVIEW = SOFTWARE_VERIFIED",
            "OUTCOME_FIELDS_IN_VALIDITY_PATH = 0",
            "FINAL_OUTCOME_ANALYSIS = LOCKED",
        ]
    )
    lines += [
        "No approval, signature, date or signoff record is fabricated by this report.",
        "",
    ]
    return "\n".join(lines)


def _peeking_report(
    source_audit: Any,
    controls: Sequence[Mapping[str, Any]],
    holdout: Any,
) -> str:
    lines = _report_header("W19 No-Significance-Peeking Verification (B-W19-03)")
    lines += [
        "## Permitted and prohibited W19 computations",
        "",
    ]
    lines += _table(
        ("Allowed in W19", "Prohibited in W19"),
        [
            [
                f"`{allowed}`",
                f"`{prohibited}`",
            ]
            for allowed, prohibited in zip(
                sorted(ALLOWED_W19_COMPUTATIONS), sorted(PROHIBITED_W19_COMPUTATIONS)
            )
        ],
    )
    lines += [
        "",
        "The prohibition is structural: no W19 source implements an outcome "
        "analysis, prohibited operations are refused at runtime, and the static "
        "audit rejects forbidden imports, calls and definitions.",
        "",
        "## Campaign stop reasons",
        "",
    ]
    lines += _table(
        ("Permitted operational stop", "Rule"),
        [[f"`{code}`", description] for code, description in ALLOWED_STOP_REASONS.items()],
    )
    lines += [
        "",
        "A statistically favorable interim result is not a permitted stop reason. "
        "A safety stop is recorded as operational evidence, never as a win.",
        "",
        "## Static capability audit",
        "",
        f"Files scanned: {len(source_audit.files_scanned)}; findings: "
        f"{len(source_audit.findings)}; passed: {source_audit.passed}.",
        "",
    ]
    if source_audit.findings:
        lines += _table(
            ("Path", "Line", "Kind", "Target"),
            [
                (finding.path, finding.line, finding.kind, finding.target)
                for finding in source_audit.findings
            ],
        )
        lines += [""]
    lines += [
        "## W16 isolation",
        "",
        f"W16 locked holdout status: `{holdout.status}` "
        f"(frozen={holdout.frozen}, opened_at={holdout.opened_at}, "
        f"test_partition_used={holdout.test_partition_used}). A W19 ledger never "
        "releases the W16 restriction.",
        "",
        "## Runtime controls",
        "",
    ]
    lines += _table(
        ("Control", "Expectation", "Passed"),
        [[probe["name"], probe["expectation"], probe["passed"]] for probe in controls],
    )
    lines += [""]
    lines += _verdict_block(
        [
            "NO_PEEKING = SOFTWARE_VERIFIED",
            "P_VALUE_COMPUTED = NONE",
            "CONFIDENCE_INTERVAL_COMPUTED = NONE",
            "PAIRED_EFFECT_COMPUTED = NONE",
            f"W16_HOLDOUT = {holdout.status}",
        ]
    )
    lines += [
        "No approval, signature, date or signoff record is fabricated by this report.",
        "",
    ]
    return "\n".join(lines)


def _readiness_report(
    validation: Any,
    progress: Any,
    *,
    w18_g4: str,
    controller_b_signoff: str,
    holdout: Any,
    handoff_rows: Sequence[Sequence[Any]],
    authorization_claim: str,
) -> str:
    lines = _report_header("W19 Campaign Readiness and Pair-Target Accounting (B-W19-04)")
    lines += [
        "## Current campaign state",
        "",
    ]
    lines += _table(
        ("Item", "Observed"),
        [
            ("Campaign authorization", validation.authorization["status"]),
            ("Authorization claim", authorization_claim),
            ("Campaign freeze", validation.campaign_freeze["freeze_status"]),
            ("Pair target", progress.pair_target_freeze_status),
            ("Statistical freeze", validation.statistical_freeze["status"]),
            ("Registered sign convention", validation.statistical_freeze["registered_sign_convention"]),
            ("Gate G4", w18_g4),
            ("Controller B signoff", controller_b_signoff),
            ("W16 holdout", holdout.status),
            ("Physical pairs", "NOT_ESTABLISHED"),
        ],
    )
    lines += [
        "",
        "Development-baseline continuity is never a campaign freeze: "
        f"`{DEVELOPMENT_BASELINE_DOES_NOT_IMPLY_FREEZE}`.",
        "",
        "## Progress accounting",
        "",
    ]
    lines += _table(
        ("Field", "Value"),
        [
            ("planned_pair_target", progress.planned_pair_target),
            ("pair_target_freeze_status", progress.pair_target_freeze_status),
            ("valid_pairs_completed", progress.valid_pairs_completed),
            ("invalid_attempts", progress.invalid_attempts),
            ("invalid_attempts_status", progress.invalid_attempts_status),
            ("remaining_target", progress.remaining_target),
            ("pairs_started", progress.pairs_started),
            ("pairs_awaiting_second_arm", progress.pairs_awaiting_second_arm),
            ("pairs_awaiting_validity", progress.pairs_awaiting_validity),
            ("invalid_pairs", progress.invalid_pairs),
            ("superseded_attempts", progress.superseded_attempts),
            ("campaign_authorization_status", progress.campaign_authorization_status),
            ("physical_evidence_class", progress.physical_evidence_class),
            ("physical_campaign_status", progress.physical_campaign_status),
            ("valid_pair_progress_status", progress.valid_pair_progress_status),
            ("target_progress_status", progress.target_progress_status),
            ("first_wave_status", progress.first_wave_status),
        ],
    )
    lines += [
        "",
        "Invalid attempts are not invalid pairs. A missing target stays "
        "`UNKNOWN_UNFROZEN`; a missing remaining count stays `NOT_COMPUTABLE`.",
        "",
        "## Unmet prerequisite handoff",
        "",
    ]
    lines += _table(
        ("Dimension", "Owner", "Observed", "Canonical ref"),
        handoff_rows,
    )
    lines += [""]
    lines += _verdict_block(
        [
            "PROGRESS_ACCOUNTING = SOFTWARE_VERIFIED",
            "PAIR_TARGET = "
            + ("FROZEN" if progress.pair_target_freeze_status == TARGET_FROZEN else "UNFROZEN"),
            f"PHYSICAL_CAMPAIGN = {progress.physical_campaign_status}",
            f"VALID_PAIR_PROGRESS = {progress.valid_pair_progress_status}",
            f"TARGET_PROGRESS = {progress.target_progress_status}",
            "FINAL_CAMPAIGN = "
            + (
                "AUTHORIZED"
                if validation.authorization["status"] == AUTHORIZATION_AUTHORIZED
                else "NOT_AUTHORIZED"
            ),
            "W20_ANALYSIS = NOT_UNLOCKED",
            f"G4 = {w18_g4}",
        ]
    )
    lines += [
        "No approval, signature, date or signoff record is fabricated by this report.",
        "",
        "## One next action",
        "",
        NEXT_MEMBER_B_ACTION,
        "",
    ]
    return "\n".join(lines)


def generate(out_dir: Path, *, source_revision: str = W19_BASE_REVISION) -> dict[str, Any]:
    w18 = _read_json(W18_MANIFEST, "W18 manifest")
    w16 = _read_json(W16_MANIFEST, "W16 locked-test manifest")
    _read_json(W17_MANIFEST, "W17 manifest")
    _read_json(W18_FREEZE_BASELINE, "W18 freeze baseline")
    records = _read_json_optional(CAMPAIGN_RECORDS)

    verdicts18 = w18.get("verdicts", {}) if isinstance(w18.get("verdicts"), dict) else {}
    w18_g4 = str(verdicts18.get("G4", "NOT_READY"))
    controller_b_signoff = str(
        w18.get("readiness", {}).get("signoff", "WITHHELD")
        if isinstance(w18.get("readiness"), dict)
        else "WITHHELD"
    )
    holdout = w16_holdout_status(w16)
    campaign_document, authorization_claim = _campaign_document(records, w18_g4)
    validation = validate_pair_ledger(campaign_document)
    target_record = (records or {}).get("frozen_target")
    # Without the campaign-records file there is no authoritative attempt
    # ledger; an empty in-memory document must not be reported as recorded zero.
    progress = compute_campaign_progress(
        validation if records is not None else None,
        target_record=target_record,
    )

    source_audit = audit_source_capability(
        W19_SOURCE_FILES, display_root=ML_ROOT
    )
    ledger_controls = _ledger_controls()
    validity_controls = _validity_controls()
    peeking_controls = _no_peeking_controls(source_audit, holdout.status)
    progress_controls = _progress_controls(validation)

    all_probes = [
        *ledger_controls,
        *validity_controls,
        *peeking_controls,
        *progress_controls,
    ]
    failed = [probe["name"] for probe in all_probes if not probe["passed"]]
    if failed:
        raise W19DriverError(
            "negative control(s) failed: " + ", ".join(failed)
        )

    ledger_verified = all(probe["passed"] for probe in ledger_controls)
    validity_verified = all(probe["passed"] for probe in validity_controls)
    peeking_verified = source_audit.passed and all(
        probe["passed"] for probe in peeking_controls
    )
    progress_verified = all(probe["passed"] for probe in progress_controls)
    software_complete = (
        ledger_verified and validity_verified and peeking_verified and progress_verified
    )

    fixture_validation = validate_pair_ledger(build_test_only_fixture_ledger())

    dimensions = (
        w18.get("readiness", {}).get("dimensions", [])
        if isinstance(w18.get("readiness"), dict)
        else []
    )
    handoff_rows = [
        [
            dimension.get("dimension_id", "UNKNOWN"),
            dimension.get("owner", "UNKNOWN"),
            dimension.get("observed", "UNKNOWN"),
            dimension.get("canonical_ref", ""),
        ]
        for dimension in dimensions
        if isinstance(dimension, Mapping) and dimension.get("status") != "READY"
    ]

    reports = {
        "pair-ledger-contract-W19.md": _pair_ledger_report(
            source_revision, ledger_controls, validation
        ),
        "validity-discipline-W19.md": _validity_report(validity_controls),
        "no-significance-peeking-W19.md": _peeking_report(
            source_audit, peeking_controls, holdout
        ),
        "campaign-readiness-W19.md": _readiness_report(
            validation,
            progress,
            w18_g4=w18_g4,
            controller_b_signoff=controller_b_signoff,
            holdout=holdout,
            handoff_rows=handoff_rows,
            authorization_claim=authorization_claim,
        ),
    }
    report_hashes: dict[str, str] = {}
    for name, text in reports.items():
        _write(out_dir / name, text)
        report_hashes[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    verdicts = {
        "SOFTWARE": "COMPLETE_PERMITTED_W19_SCOPE" if software_complete else "PARTIAL",
        "B_W19_01_PAIR_LEDGER": "SOFTWARE_VERIFIED" if ledger_verified else "PARTIAL",
        "B_W19_02_VALIDITY_DISCIPLINE": "SOFTWARE_VERIFIED" if validity_verified else "PARTIAL",
        "B_W19_03_NO_SIGNIFICANCE_PEEKING": "SOFTWARE_VERIFIED" if peeking_verified else "PARTIAL",
        "B_W19_04_PAIR_PROGRESS": "SOFTWARE_VERIFIED" if progress_verified else "PARTIAL",
        "PAIR_LEDGER_SCHEMA": "VERIFIED" if ledger_verified else "NOT_VERIFIED",
        "VALIDITY_REVIEW": "SOFTWARE_VERIFIED" if validity_verified else "PARTIAL",
        "NO_PEEKING": "SOFTWARE_VERIFIED" if peeking_verified else "PARTIAL",
        "PROGRESS_ACCOUNTING": "SOFTWARE_VERIFIED" if progress_verified else "PARTIAL",
        "PAIR_LEDGER_SOFTWARE": "VERIFIED" if ledger_verified else "NOT_VERIFIED",
        "PHYSICAL_PAIRS": (
            "ACCEPTED" if validation.physical_pair_evidence_accepted else "NOT_ESTABLISHED"
        ),
        "CAMPAIGN_TARGET": (
            "FROZEN" if progress.pair_target_freeze_status == TARGET_FROZEN else "UNFROZEN"
        ),
        "FINAL_CAMPAIGN": (
            "AUTHORIZED"
            if validation.authorization["status"] == AUTHORIZATION_AUTHORIZED
            else "NOT_AUTHORIZED"
        ),
        "W20_ANALYSIS": "NOT_UNLOCKED",
        "G4": w18_g4,
        "W16_HOLDOUT": holdout.status,
        "DELIVERY": "PENDING_PUBLICATION",
    }

    unfinished: list[str] = []
    if not validation.authorization["authorized"]:
        unfinished.append("FINAL_AB_CAMPAIGN_AUTHORIZATION")
    if validation.campaign_freeze["freeze_status"] != FREEZE_STATUS_APPROVED:
        unfinished.append("FINAL_AB_CAMPAIGN_FREEZE_APPROVAL")
    if progress.pair_target_freeze_status != TARGET_FROZEN:
        unfinished.append("PAIR_TARGET_FREEZE")
    if validation.statistical_freeze["status"] != "FROZEN_APPROVED":
        unfinished.append("STATISTICAL_ANALYSIS_FREEZE")
    if w18_g4 != "READY":
        unfinished.append("GATE_G4_READY")
    if controller_b_signoff == "WITHHELD":
        unfinished.append("CONTROLLER_B_SIGNOFF")
    if holdout.status != "NOT_OPENED":
        unfinished.append("W16_HOLDOUT_ACCESS_CONFLICT")
    unfinished.append("ACCEPTED_PHYSICAL_PAIR_EVIDENCE")

    manifest = {
        "schema": "coldguard-w19-campaign-integrity-v1",
        "layer_version": W19_LAYER_VERSION,
        "scientific_evidence_class": "SYNTHETIC_SOFTWARE_CONTROL_ONLY",
        "physical_authorization_status": (
            "FINAL_AB_CAMPAIGN_AUTHORIZED"
            if validation.authorization["status"] == AUTHORIZATION_AUTHORIZED
            else "FINAL_AB_CAMPAIGN_NOT_AUTHORIZED"
        ),
        "source_revision": source_revision,
        "revision_semantics": W19_BASE_REVISION_SEMANTICS,
        "analysis_code_sha256": _analysis_code_sha256(),
        "generation_inputs": {
            "w15_model_manifest": _input_record(W15_MODEL_MANIFEST),
            "w16_locked_manifest": _input_record(W16_MANIFEST),
            "w17_manifest": _input_record(W17_MANIFEST),
            "w18_manifest": _input_record(W18_MANIFEST),
            "w18_freeze_baseline": _input_record(W18_FREEZE_BASELINE),
            "statistical_analysis_plan": _input_record(STATISTICAL_PLAN),
            "metric_spec": _input_record(METRIC_SPEC),
            "sample_size_planning": _input_record(SAMPLE_SIZE_SCRIPT),
            "campaign_records": _input_record(CAMPAIGN_RECORDS),
        },
        "campaign_state": {
            "campaign_id": validation.campaign_id,
            "authorization_claim": authorization_claim,
            "authorization": validation.authorization,
            "campaign_freeze": validation.campaign_freeze,
            "statistical_freeze": validation.statistical_freeze,
            "pair_target": progress.to_dict()["pair_target_freeze_status"],
            "planned_pair_target": progress.planned_pair_target,
            "pairs_recorded": len(validation.pairs),
            "attempts_recorded": validation.attempt_accounting.total_attempts,
            "physical_pairs": verdicts["PHYSICAL_PAIRS"],
            "g4": w18_g4,
            "controller_b_signoff": controller_b_signoff,
            "w16_holdout": holdout.to_dict(),
            "development_baseline_implication": DEVELOPMENT_BASELINE_DOES_NOT_IMPLY_FREEZE,
        },
        "pair_ledger_contract": {
            "schema": PAIR_LEDGER_SCHEMA,
            "layer_version": PAIR_LEDGER_LAYER_VERSION,
            "statistical_unit": "one valid matched Controller A/B pair",
            "pair_statuses": list(PAIR_STATUSES),
            "identity_fields": sorted(
                {
                    "pair_id",
                    "campaign_id",
                    "scenario_id",
                    "block_id",
                    "session_id",
                    "planned_controller_order",
                    "actual_controller_order",
                    "run_id",
                    "attempt_id",
                    "controller_arm",
                    "hardware_config_id",
                    "calibration_id",
                    "firmware_version",
                    "model_artifact_id",
                    "model_artifact_sha256",
                    "feature_version",
                    "policy_version",
                    "protocol_version",
                    "disturbance_protocol_id",
                    "source_manifest_id",
                    "source_path",
                    "source_sha256",
                    "quality_status",
                    "validity_status",
                    "validity_reason_codes",
                }
            ),
            "fixture_markers": list(FIXTURE_MARKERS),
            "campaign_freeze_fields": list(CAMPAIGN_FREEZE_FIELD_IDS),
            "rerun_semantics": "same pair_id and arm; supersedes chain; invalid history retained",
        },
        "fixture_validation": {
            "pairs": len(fixture_validation.pairs),
            "pair_status_counts": dict(fixture_validation.pair_status_counts),
            "attempt_accounting": fixture_validation.attempt_accounting.to_dict(),
            "physical_valid_pairs": fixture_validation.physical_valid_pairs,
            "software_valid_pairs": fixture_validation.software_valid_pairs,
            "admitted_to_physical_campaign": False,
        },
        "adversarial_controls": {
            "probe_count": len(all_probes),
            "probes_passed": sum(1 for probe in all_probes if probe["passed"]),
            "probes": all_probes,
        },
        "validity_discipline": {
            "method": VALIDITY_METHOD_VERSION,
            "metric_contracts": [
                {
                    "metric_id": contract.metric_id,
                    "role": contract.role,
                    "coverage_key": contract.coverage_key,
                    "canonical_ref": contract.canonical_ref,
                }
                for contract in METRIC_CONTRACTS
            ],
            "reason_codes": sorted(PREDECLARED_VALIDITY_REASON_CODES),
            "controls": validity_controls,
        },
        "no_peeking": {
            "guard_version": "coldguard-w19-peeking-guard-v1",
            "allowed_operations": sorted(ALLOWED_W19_COMPUTATIONS),
            "prohibited_operations": sorted(PROHIBITED_W19_COMPUTATIONS),
            "permitted_stop_reasons": sorted(ALLOWED_STOP_REASONS),
            "registered_sign_convention": REGISTERED_SIGN_CONVENTION,
            "statistical_freeze_fields": list(STATISTICAL_FREEZE_FIELDS),
            "source_capability_audit": source_audit.to_dict(),
            "controls": peeking_controls,
        },
        "progress": progress.to_dict(),
        "readiness_handoff": {
            "g4": w18_g4,
            "controller_b_signoff": controller_b_signoff,
            "dimensions": handoff_rows,
        },
        "verdicts": verdicts,
        "capabilities": {
            "campaign_authorization": False,
            "command_transport": False,
            "hardware_actuation": False,
            "model_training": False,
            "network": False,
            "outcome_analysis": False,
            "physical_control": False,
            "w16_holdout_access": False,
        },
        "unfinished_physical_requirements": unfinished,
        "next_member_b_action": NEXT_MEMBER_B_ACTION,
        "reports": report_hashes,
        "limitations": [
            "No final physical A/B results are produced or opened.",
            "No valid-pair campaign progress exists without admitted physical data.",
            "No early treatment-effect analysis exists; W20 remains locked.",
            "The W16 locked predictive holdout is not opened or evaluated.",
            "Controller B remains unauthorized for physical intervention.",
            "Gate G5 is not promoted.",
            "Approval metadata is shape-checked only; external signatures cannot be verified offline.",
            "All fixture attempts are synthetic, permanently marked and never admitted.",
            "The 50% first-wave indicator is non-computable without a frozen target and accepted physical pairs.",
        ],
    }
    _write_json(out_dir / "w19-manifest.json", manifest)

    return {
        "verdicts": verdicts,
        "validation": {
            "pair_status_counts": dict(validation.pair_status_counts),
            "attempt_accounting": validation.attempt_accounting.to_dict(),
            "authorization": validation.authorization["status"],
            "campaign_freeze": validation.campaign_freeze["freeze_status"],
            "physical_valid_pairs": validation.physical_valid_pairs,
        },
        "progress": progress.to_dict(),
        "controls": {"probes": len(all_probes), "passed": sum(
            1 for probe in all_probes if probe["passed"]
        )},
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True).encode(
                "utf-8"
            )
            + b"\n"
        ).hexdigest(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the W19 campaign-integrity report family"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=W19_DIR,
        help="output directory (default: ml/reports/W19)",
    )
    parser.add_argument(
        "--source-revision",
        default=W19_BASE_REVISION,
        help="implementation base revision recorded in the manifest",
    )
    args = parser.parse_args(argv)
    try:
        summary = generate(args.out_dir, source_revision=args.source_revision)
    except Exception as exc:
        print(f"W19 driver refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
