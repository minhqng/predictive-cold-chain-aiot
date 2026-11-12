"""W20 campaign preflight driver: metadata-only campaign lock and unlock gate.

Canonical anchors: Doc 03 §§95-102, 130-137, 158-163; Doc 04 W20 and Gate G5;
Doc 05B §48 B-W20-01..04.

The driver reads a fixed allowlist of metadata files through
``MetadataOnlyReader``, assesses the real campaign state, proves the software
gate with a permanently marked synthetic fixture, runs adversarial controls and
writes deterministic reports plus a manifest.  It has no outcome-analysis
route, no network access, no command dispatch and no way to open the W16
locked test or a physical outcome payload.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from coldguard_ml.w19_no_peeking import (
    FREEZE_FROZEN_APPROVED,
    PEEKING_GUARD_VERSION,
    REGISTERED_SIGN_CONVENTION,
    STATISTICAL_FREEZE_FIELDS,
    W19OutcomeExposureError,
    w16_holdout_status,
)
from coldguard_ml.w19_pair_ledger import (
    CAMPAIGN_FREEZE_FIELD_IDS,
    PAIR_LEDGER_LAYER_VERSION,
    PAIR_LEDGER_SCHEMA,
    build_test_only_fixture_ledger,
)
from coldguard_ml.w19_validity import METRIC_CONTRACTS, VALIDITY_METHOD_VERSION
from coldguard_ml.w20_campaign_lock import (
    ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION,
    ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION,
    ANALYSIS_PREFLIGHT_BLOCKED,
    BINDING_EMBEDDED,
    BUNDLE_SYNTHETIC,
    CAMPAIGN_METADATA_SCHEMA,
    CLOSEOUT_CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW,
    GROUP_AUTHORIZATION,
    GROUP_EXPORT,
    GROUP_PAIR_COMPLETION,
    GROUP_PAIR_TARGET,
    GROUP_SCIENTIFIC_FREEZE,
    GROUP_STABILITY,
    PROOF_TEST_ONLY,
    STATUS_FAIL,
    STATUS_PASS,
    W20_CAMPAIGN_LOCK_LAYER_VERSION,
    W20EvidenceError,
    W20OutcomeAccessError,
    MetadataOnlyReader,
    assess_campaign_lock,
    audit_w20_capability,
    canonical_sha256,
    verify_checksum_listing,
)
from coldguard_ml.w20_causal_boundary import (
    AB_CONTRACT_ACCEPTED,
    AIW_NOT_ADMISSIBLE,
    AIW_UNKNOWN,
    CAUSAL_BOUNDARY_SOFTWARE_VERIFIED,
    ENERGY_NOT_ADMISSIBLE,
    EWT_NOT_ADMISSIBLE,
    EWT_UNOBSERVED,
    RECOVERY_NOT_ADMISSIBLE,
    assess_aiw_admissibility,
    assess_energy_claim,
    assess_ewt_admissibility,
    assess_recovery_claim,
    causal_restriction_proof,
    validate_ab_report_contract,
)
from coldguard_ml.w20_outcome_contract import (
    OUTCOME_METRICS,
    OUTCOME_SCHEMA_SOFTWARE_VERIFIED,
    OUTCOME_TABLE_FILENAME,
    PAIR_OUTCOME_TABLE_NOT_PRODUCED,
    PHYSICAL_OUTCOME_DATA_NOT_ADMITTED,
    W20AnalysisLockError,
    W20OutcomeContractError,
    assert_outcome_analysis_locked,
    build_admission_plan,
    outcome_table_contract,
    schema_verdicts,
    validate_pair_outcome_metadata,
)

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
W16_MANIFEST = ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"
W17_MANIFEST = ML_ROOT / "reports" / "W17" / "w17-manifest.json"
W18_MANIFEST = ML_ROOT / "reports" / "W18" / "w18-manifest.json"
W18_FREEZE_BASELINE = ML_ROOT / "reports" / "W18" / "freeze-baseline-W18.json"
W19_MANIFEST = ML_ROOT / "reports" / "W19" / "w19-manifest.json"
STATISTICAL_PLAN = ML_ROOT / "statistical-analysis-plan-v0.md"
METRIC_SPEC = ML_ROOT / "metric-spec.md"
W20_DIR = ML_ROOT / "reports" / "W20"
CAMPAIGN_METADATA = W20_DIR / "campaign-metadata-W20.json"
A_W19_DIR = REPO_ROOT / "evidence" / "A" / "W19"
A_W20_DIR = REPO_ROOT / "evidence" / "A" / "W20"

W20_LAYER_VERSION = W20_CAMPAIGN_LOCK_LAYER_VERSION
W20_BASE_REVISION = "d7bffbcfacc8505b227bd87a47dd03620ed82d16"
W20_BASE_REVISION_SEMANTICS = "W19_STACK_HEAD_BASE_NOT_W20_DELIVERY_COMMIT"

EXPECTED_REPORTS = (
    "campaign-integrity.md",
    "paired-outcome-contract-W20.md",
    "analysis-unlock-W20.md",
)

A_W19_FILES = (
    "SHA256SUMS.txt",
    "campaign-wave1-runbook.md",
    "invalid-attempt-taxonomy.json",
    "run-preparation-checklist.json",
    "validate_w19.py",
    "wave1-status.md",
)
A_W20_FILES = (
    "SHA256SUMS.txt",
    "campaign-wave2-index.json",
    "frozen-campaign-manifest.md",
    "physical-drift-audit.md",
    "validate_w20.py",
)

METADATA_INPUTS = (
    W16_MANIFEST,
    W17_MANIFEST,
    W18_MANIFEST,
    W18_FREEZE_BASELINE,
    W19_MANIFEST,
    STATISTICAL_PLAN,
    METRIC_SPEC,
    CAMPAIGN_METADATA,
    *[A_W19_DIR / name for name in A_W19_FILES],
    *[A_W20_DIR / name for name in A_W20_FILES],
)

W20_SOURCE_FILES = (
    ML_ROOT / "src" / "coldguard_ml" / "w20_campaign_lock.py",
    ML_ROOT / "src" / "coldguard_ml" / "w20_outcome_contract.py",
    ML_ROOT / "src" / "coldguard_ml" / "w20_causal_boundary.py",
    ML_ROOT / "scripts" / "w20-campaign-preflight-W20.py",
    ML_ROOT / "tests" / "test_w20_campaign_lock.py",
    ML_ROOT / "tests" / "test_w20_outcome_contract.py",
    ML_ROOT / "tests" / "test_w20_causal_boundary.py",
    ML_ROOT / "tests" / "test_w20_delivery.py",
)

EVIDENCE_LABELS = (
    "Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17/W18/W19 "
    "artifacts, Member A W19/W20 metadata dossiers and Member B contracts), "
    "SYNTHETIC_SOFTWARE_FIXTURE (permanently marked W20 fixture metadata), "
    "DERIVED_SOFTWARE_ASSERTION (gate, contract and causal-boundary results), "
    "EXTERNAL_DEPENDENCY (Member A/C/D and leader prerequisites), "
    "NOT_VERIFIED (absent physical campaign data and outcome payloads)."
)

PRIMARY_OUTCOME_FIXTURE = "PRIMARY_THERMAL_EXPOSURE_CONTRACT_V1"
ANALYSIS_PLAN_VERSION_FIXTURE = "coldguard-w03-analysis-contract-v1"
FIXTURE_CAMPAIGN_ID = "CG-W19-SOFTWARE-FIXTURE"
FIXTURE_FREEZE_VERSION = "TEST-FIXTURE-FREEZE-v1"

NEXT_MEMBER_B_ACTION = (
    "Keep W20 final analysis locked; when Member A and Member C publish the "
    "accepted final campaign export and the leader issues the campaign and "
    "statistical freezes, re-run the W20 preflight against that metadata and "
    "request external review. Do not open physical outcomes, compute paired "
    "effects or start W21 implementation in this task."
)


class W20DriverError(RuntimeError):
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


def _analysis_code_sha256() -> str:
    digest = hashlib.sha256()
    for path in W20_SOURCE_FILES:
        digest.update(path.relative_to(ML_ROOT).as_posix().encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"ABSENT")
    return digest.hexdigest()


def _make_reader() -> MetadataOnlyReader:
    return MetadataOnlyReader(
        REPO_ROOT,
        [path.relative_to(REPO_ROOT).as_posix() for path in METADATA_INPUTS],
    )


def _input_record(reader: MetadataOnlyReader, path: Path) -> dict[str, Any]:
    relative = path.relative_to(REPO_ROOT).as_posix()
    if not path.is_file():
        return {"path": relative, "sha256": "ABSENT", "present": False}
    return {"path": relative, "sha256": reader.sha256(relative), "present": True}


def _read_campaign_metadata(reader: MetadataOnlyReader) -> dict[str, Any]:
    return reader.read_json(CAMPAIGN_METADATA.relative_to(REPO_ROOT).as_posix())


def _pinned_baseline(w16: Mapping[str, Any], w18: Mapping[str, Any]) -> dict[str, Any]:
    artifacts = w16.get("artifact_hashes")
    model_sha = None
    if isinstance(artifacts, list):
        for entry in artifacts:
            if isinstance(entry, Mapping) and entry.get("role") == "model_native":
                model_sha = entry.get("declared_sha256")
                break
    values = w18.get("values") if isinstance(w18.get("values"), Mapping) else {}
    calibration = values.get("calibration_semantics")
    score_semantics = (
        calibration.get("score_semantics")
        if isinstance(calibration, Mapping)
        else None
    )
    return {
        "w16_model_artifact_sha256": model_sha,
        "w18_model_config_sha256": values.get("model_config_sha256"),
        "w18_feature_version": values.get("feature_version"),
        "w18_feature_schema_hash": values.get("feature_schema_hash"),
        "w18_feature_order_sha256": values.get("ordered_feature_ids_sha256"),
        "w18_calibration_semantics": score_semantics,
    }


def _fixture_campaign_freeze(ledger: Mapping[str, Any], pinned: Mapping[str, Any]) -> dict[str, Any]:
    attempts = {attempt["controller_arm"]: attempt for attempt in ledger["attempts"]}
    pair = ledger["pairs"][0]
    arm_a = attempts["A"]
    arm_b = attempts["B"]

    def field(value: Any, provenance: str) -> dict[str, Any]:
        return {
            "value": value,
            "provenance": provenance,
            "status": FREEZE_FROZEN_APPROVED,
        }

    values = {
        "hardware_config_id": arm_a["hardware_config_id"],
        "calibration_id": arm_a["calibration_id"],
        "firmware_version": arm_a["firmware_version"],
        "sensor_placement": "BENCH-FIXTURE-PLACEMENT-V1",
        "model_artifact_sha256": arm_b["model_artifact_sha256"],
        "feature_schema_hash": pinned["w18_feature_schema_hash"],
        "critical_target": {
            "boundary_c": 30.0,
            "target_status": FREEZE_FROZEN_APPROVED,
            "target_spec_version": "TEST-FIXTURE-TARGET-v1",
        },
        "representative_temperature": "TMEAN_ALL_SENSORS_FIXTURE",
        "primary_horizon": {"horizon_s": 60.0, "horizon_status": FREEZE_FROZEN_APPROVED},
        "operating_threshold": {"value": 0.5, "status": FREEZE_FROZEN_APPROVED},
        "warning_persistence": {"k": 3, "status": FREEZE_FROZEN_APPROVED},
        "controller_policy_version": arm_b["policy_version"],
        "cooling_action_magnitude": {
            "duty": 1.0,
            "duration_s": 120,
            "status": FREEZE_FROZEN_APPROVED,
        },
        "disturbance_protocol": arm_a["disturbance_protocol_id"],
        "initial_reset_criterion": pair["initial_state"]["criterion_version"],
        "pair_matching_tolerances": {
            "initial_tmean_delta_max_c": 0.5,
            "initial_gradient_delta_max_c": 0.3,
        },
        "randomization_protocol": "REGISTERED",
        "validity_exclusion_rules": ["PREDECLARED_VALIDITY_REASON_CODES_ONLY"],
        "primary_outcome": PRIMARY_OUTCOME_FIXTURE,
        "statistical_method": "PRECOMPUTED_PAIRED_ANALYSIS_CONTRACT",
        "target_pair_count": 1,
    }
    return {
        "fields": {field_id: field(values[field_id], "test://w20/fixture-freeze") for field_id in CAMPAIGN_FREEZE_FIELD_IDS},
        "approval": {
            "authority_id": "TEST_FIXTURE_ONLY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "test://w20/fixture-freeze-approval",
        },
    }


def _fixture_statistical_freeze() -> dict[str, Any]:
    return {
        "status": FREEZE_FROZEN_APPROVED,
        "fields": {
            "primary_outcome": PRIMARY_OUTCOME_FIXTURE,
            "paired_sign_convention": REGISTERED_SIGN_CONVENTION,
            "confidence_level": 0.95,
            "bootstrap_seed": "TEST-FIXTURE-SEED-001",
            "bootstrap_iterations": 2000,
            "test_family": "PRECOMPUTED_PAIRED_TEST_FAMILY",
            "invalid_pair_handling": "RERUN_INVALID_ARM_PRESERVE_BLOCK",
            "secondary_outcomes": [
                "recovery_time",
                "peak_temperature",
                "time_above_limit",
                "branch_energy",
            ],
            "analysis_plan_version": ANALYSIS_PLAN_VERSION_FIXTURE,
        },
        "approval": {
            "authority_id": "TEST_FIXTURE_ONLY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "test://w20/fixture-statistical-freeze",
        },
    }


def _fixture_outcome_definition_freeze() -> dict[str, Any]:
    values = {
        "primary_outcome": PRIMARY_OUTCOME_FIXTURE,
        "representative_temperature": "TMEAN_ALL_SENSORS_FIXTURE",
        "t_limit_critical_target": {"value_c": 30.0, "status": FREEZE_FROZEN_APPROVED},
        "recovery_reference_time": "DISTURBANCE_END",
        "recovery_band": {"value_c": 2.0, "status": FREEZE_FROZEN_APPROVED},
        "recovery_persistence": {"seconds": 60, "status": FREEZE_FROZEN_APPROVED},
        "measurement_coverage_rules": "NO_ZERO_FILL_EXCLUDE_GAPS_REPORT_COVERAGE",
        "energy_source_admissibility": "COOLING_BRANCH_PZEM_ONLY",
        "peak_temperature_basis": "SAME_REPRESENTATIVE_SERIES_AND_TIME_BASE",
        "time_above_limit_basis": "SAME_REPRESENTATIVE_SERIES_AND_TIME_BASE",
    }
    return {
        "status": FREEZE_FROZEN_APPROVED,
        "fields": {
            field_id: {
                "value": value,
                "provenance": "test://w20/fixture-outcome-freeze",
                "status": FREEZE_FROZEN_APPROVED,
            }
            for field_id, value in values.items()
        },
        "approval": {
            "authority_id": "TEST_FIXTURE_ONLY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "test://w20/fixture-outcome-freeze-approval",
        },
    }


def _fixture_pair_target() -> dict[str, Any]:
    return {
        "status": FREEZE_FROZEN_APPROVED,
        "planned_pair_target": 1,
        "approval": {
            "authority_id": "TEST_FIXTURE_ONLY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "test://w20/fixture-target-approval",
        },
        "variance_justification_ref": "test://w20/fixture-variance-justification",
    }


def build_test_only_metadata_bundle(
    w16_manifest: Mapping[str, Any], w18_baseline: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a permanently marked synthetic metadata bundle for software proof."""
    pinned = _pinned_baseline(w16_manifest, w18_baseline)
    ledger = build_test_only_fixture_ledger()
    ledger["analysis_plan_version"] = ANALYSIS_PLAN_VERSION_FIXTURE
    for attempt in ledger["attempts"]:
        if attempt["controller_arm"] == "B":
            attempt["model_artifact_sha256"] = pinned["w16_model_artifact_sha256"]
            attempt["feature_version"] = pinned["w18_feature_version"]
    campaign_freeze = _fixture_campaign_freeze(ledger, pinned)
    statistical_freeze = _fixture_statistical_freeze()
    outcome_freeze = _fixture_outcome_definition_freeze()
    frozen_target = _fixture_pair_target()
    authorization_record = {
        "authorized": True,
        "authority_id": "TEST_FIXTURE_ONLY",
        "authority_role": "TEAM_LEAD",
        "canonical_ref": "test://w20/fixture-authorization",
        "g4_status": "READY",
        "pair_target_frozen": True,
        "analysis_freeze_accepted": True,
    }
    ledger["campaign_authorization"] = authorization_record
    ledger["campaign_freeze"] = campaign_freeze
    ledger["statistical_freeze"] = statistical_freeze
    ledger["frozen_target"] = frozen_target
    pair = ledger["pairs"][0]
    attempts = {attempt["controller_arm"]: attempt for attempt in ledger["attempts"]}
    source_a = attempts["A"]["source_sha256"]
    source_b = attempts["B"]["source_sha256"]
    export_manifest = {
        "export_id": "EXPORT-TEST-FIXTURE-001",
        "attempt_ids": [attempts["A"]["attempt_id"], attempts["B"]["attempt_id"]],
        "source_references": [
            {
                "attempt_id": attempts["A"]["attempt_id"],
                "path": attempts["A"]["source_path"],
                "sha256": source_a,
            },
            {
                "attempt_id": attempts["B"]["attempt_id"],
                "path": attempts["B"]["source_path"],
                "sha256": source_b,
            },
        ],
        "event_time_domain": "EVENT_TIME_RECORDED",
        "quality_flags_complete": True,
    }
    backup_evidence = {"backup": "TEST_FIXTURE_ONLY", "restore_verified": False}
    trace_evidence = {"trace": "TEST_FIXTURE_ONLY", "pairs": [pair["pair_id"]]}
    freeze_values = {
        field_id: entry["value"]
        for field_id, entry in campaign_freeze["fields"].items()
    }
    identities = {
        "hardware_config_id": freeze_values["hardware_config_id"],
        "sensor_placement": freeze_values["sensor_placement"],
        "calibration_id": freeze_values["calibration_id"],
        "firmware_version": freeze_values["firmware_version"],
        "model_artifact_sha256": freeze_values["model_artifact_sha256"],
        "model_config_sha256": pinned["w18_model_config_sha256"],
        "feature_version": pinned["w18_feature_version"],
        "feature_schema_hash": freeze_values["feature_schema_hash"],
        "feature_order_sha256": pinned["w18_feature_order_sha256"],
        "model_calibration_semantics": pinned["w18_calibration_semantics"],
        "primary_horizon": freeze_values["primary_horizon"],
        "critical_target": freeze_values["critical_target"],
        "reactive_threshold_hysteresis": "TEST-FIXTURE-REACTIVE-v1",
        "predictive_threshold": freeze_values["operating_threshold"],
        "warning_persistence": freeze_values["warning_persistence"],
        "controller_policy_version": freeze_values["controller_policy_version"],
        "cooling_action_magnitude": freeze_values["cooling_action_magnitude"],
        "safety_limits": "TEST-FIXTURE-SAFETY-v1",
        "disturbance_protocol_id": freeze_values["disturbance_protocol"],
        "initial_reset_criterion": freeze_values["initial_reset_criterion"],
        "pair_matching_tolerances": freeze_values["pair_matching_tolerances"],
        "randomization_protocol": freeze_values["randomization_protocol"],
        "analysis_plan_version": ANALYSIS_PLAN_VERSION_FIXTURE,
        "primary_outcome": PRIMARY_OUTCOME_FIXTURE,
        "target_pair_count": freeze_values["target_pair_count"],
    }
    manifest_payload = {
        "manifest_id": "TEST-FIXTURE-CAMPAIGN-MANIFEST",
        "freeze_version": FIXTURE_FREEZE_VERSION,
        "approved_by": {
            "authority_id": "TEST_FIXTURE_ONLY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "test://w20/fixture-manifest-approval",
        },
        "statistical_unit": "PAIR",
        "registered_pair_ids": [pair["pair_id"]],
        "registered_attempt_ids": [
            attempts["A"]["attempt_id"],
            attempts["B"]["attempt_id"],
        ],
        "registered_orders": {pair["pair_id"]: ["A", "B"]},
        "target_record_sha256": canonical_sha256(frozen_target),
        "identities": identities,
    }
    manifest = copy.deepcopy(manifest_payload)
    manifest["manifest_sha256"] = canonical_sha256(manifest_payload)
    return {
        "schema": CAMPAIGN_METADATA_SCHEMA,
        "campaign_id": FIXTURE_CAMPAIGN_ID,
        "evidence_class": BUNDLE_SYNTHETIC,
        "fixture_markers": ["TEST_ONLY", "SYNTHETIC_SOFTWARE_CONTROL_ONLY"],
        "campaign_manifest": manifest,
        "authorization": {
            "record": authorization_record,
            "campaign_id": FIXTURE_CAMPAIGN_ID,
            "approved_freeze_version": FIXTURE_FREEZE_VERSION,
            "review_authority_id": "TEST_FIXTURE_REVIEWER",
            "review_authority_role": "TEAM_LEAD",
            "verification_status": "NOT_VERIFIED_EXTERNALLY",
        },
        "controller_b_enablement": {
            "status": "APPROVED",
            "approver": {
                "authority_id": "TEST_FIXTURE_ONLY",
                "authority_role": "TEAM_LEAD",
                "canonical_ref": "test://w20/fixture-controller-b-enablement",
            },
        },
        "analysis_execution_authorization": {
            "status": "NOT_ISSUED",
            "verification_status": "NOT_VERIFIED_EXTERNALLY",
        },
        "pair_target": frozen_target,
        "target_history": [],
        "target_freeze_stage": "BEFORE_CAMPAIGN_START",
        "campaign_freeze": campaign_freeze,
        "statistical_freeze": statistical_freeze,
        "outcome_definition_freeze": outcome_freeze,
        "pair_ledger": ledger,
        "selection_policy": {"rule": "ALL_PREDECLARED", "exclusions": []},
        "rematch_history": [],
        "n_inflation_claims": [],
        "export": {
            "manifest": export_manifest,
            "manifest_sha256": canonical_sha256(export_manifest),
            "manifest_verification": BINDING_EMBEDDED,
            "backup": {
                "status": "VERIFIED",
                "verification": BINDING_EMBEDDED,
                "evidence": backup_evidence,
                "evidence_sha256": canonical_sha256(backup_evidence),
            },
            "missing_runs": [],
            "missing_attempts": [],
        },
        "physical_verification": {
            "status": "VERIFIED",
            "coverage_pairs": 1,
            "required_pairs": 1,
            "verification": BINDING_EMBEDDED,
            "evidence": trace_evidence,
            "evidence_sha256": canonical_sha256(trace_evidence),
        },
        "changes": [],
        "external_links": {
            "d_policy_freeze": {
                "status": FREEZE_FROZEN_APPROVED,
                "safety_limits_version": "TEST-FIXTURE-SAFETY-v1",
                "reactive_threshold_version": "TEST-FIXTURE-REACTIVE-v1",
                "source_revision": "test://w20/fixture-d-policy",
                "source_sha256": "0" * 64,
            },
            "w16_holdout": {"status": "NOT_OPENED"},
        },
        "pinned_baseline": pinned,
    }


def _mutate(bundle: Mapping[str, Any], path: str, value: Any) -> dict[str, Any]:
    mutated = copy.deepcopy(bundle)
    cursor: Any = mutated
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if part.isdigit() else cursor[part]
    last = parts[-1]
    if last.isdigit():
        cursor[int(last)] = value
    else:
        cursor[last] = value
    return mutated


def _probe(
    name: str,
    expectation: str,
    fn: Callable[[], bool],
    controls: list[dict[str, Any]],
) -> None:
    try:
        passed = bool(fn())
    except Exception:  # noqa: BLE001 - a negative control must not crash the driver
        passed = False
    controls.append({"name": name, "expectation": expectation, "passed": passed})


def _gate_blocked(bundle: Mapping[str, Any], group_id: str | None = None) -> bool:
    assessment = assess_campaign_lock(bundle)
    if assessment.gate_decision != ANALYSIS_PREFLIGHT_BLOCKED:
        return False
    return group_id is None or assessment.group(group_id).status == STATUS_FAIL


def _gate_blocked_with(
    bundle: Mapping[str, Any], group_id: str, token: str
) -> bool:
    assessment = assess_campaign_lock(bundle)
    if assessment.gate_decision != ANALYSIS_PREFLIGHT_BLOCKED:
        return False
    return any(token in reason for reason in assessment.group(group_id).reasons)


def _causal_records() -> dict[str, dict[str, Any]]:
    return {
        "offline": {
            "record_id": "REC-OFFLINE",
            "evidence_class": "OFFLINE_REPLAY",
            "controller_context": "REACTIVE",
            "intervention": "NONE",
            "timing_source": "MEASURED_EVENT_TIME",
            "reactive_crossing_observed": True,
            "synthetic_markers": [],
            "ack_only": False,
            "post_intervention_warning_used": False,
            "aiw_timing_inputs_measured": True,
            "thermal_response_verified": True,
            "electrical_observation_only": False,
            "pzem_coverage": "COMPLETE",
            "energy_scope": "COOLING_BRANCH",
        },
        "closed_loop": {
            "record_id": "REC-B-CLOSED",
            "evidence_class": "PHYSICAL",
            "controller_context": "PREDICTIVE",
            "intervention": "PREDICTIVE_COOLING_APPLIED",
            "timing_source": "MEASURED_EVENT_TIME",
            "reactive_crossing_observed": False,
            "synthetic_markers": [],
            "ack_only": False,
            "post_intervention_warning_used": False,
            "aiw_timing_inputs_measured": True,
            "thermal_response_verified": True,
            "electrical_observation_only": False,
            "pzem_coverage": "COMPLETE",
            "energy_scope": "COOLING_BRANCH",
        },
        "synthetic": {
            "record_id": "REC-SYNTHETIC",
            "evidence_class": "SYNTHETIC",
            "controller_context": "REACTIVE",
            "intervention": "NONE",
            "timing_source": "SYNTHETIC_REPLAY_TIMESTAMP",
            "reactive_crossing_observed": True,
            "synthetic_markers": ["TEST_ONLY", "SYNTHETIC_SOFTWARE_CONTROL_ONLY"],
            "ack_only": False,
            "post_intervention_warning_used": False,
            "aiw_timing_inputs_measured": True,
            "thermal_response_verified": True,
            "electrical_observation_only": False,
            "pzem_coverage": "COMPLETE",
            "energy_scope": "COOLING_BRANCH",
        },
    }


def _campaign_controls(base: Mapping[str, Any], tmp_dir: Path) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    base_assessment = assess_campaign_lock(base)

    _probe(
        "valid_fixture_reaches_metadata_ready",
        "a permanently marked synthetic fixture passes structural groups and stops "
        "at metadata-ready pending authorization",
        lambda: (
            base_assessment.gate_decision
            == ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION
            and base_assessment.proof_class == PROOF_TEST_ONLY
            and base_assessment.closeout_state
            == CLOSEOUT_CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW
        ),
        controls,
    )

    _probe(
        "missing_g4_blocks",
        "missing G4 prevents analysis readiness",
        lambda: _gate_blocked_with(
            _mutate(base, "authorization.record.g4_status", "NOT_READY"),
            GROUP_AUTHORIZATION,
            "FAKE_APPROVAL",
        ),
        controls,
    )
    _probe(
        "fake_approval_string_refused",
        "a string containing APPROVED is not proof of authorization",
        lambda: _gate_blocked_with(
            _mutate(base, "authorization.record", {"status": "APPROVED"}),
            GROUP_AUTHORIZATION,
            "MALFORMED",
        ),
        controls,
    )
    _probe(
        "development_baseline_is_not_a_freeze",
        "the W18 development baseline never becomes a campaign freeze",
        lambda: _gate_blocked(_mutate(base, "campaign_freeze", None)),
        controls,
    )
    _probe(
        "target_missing_or_zero_refused",
        "a frozen target must be a positive integer",
        lambda: _gate_blocked_with(
            _mutate(
                _mutate(base, "pair_target.planned_pair_target", 0),
                "campaign_manifest.target_record_sha256",
                canonical_sha256(_mutate(base, "pair_target.planned_pair_target", 0)["pair_target"]),
            ),
            GROUP_PAIR_TARGET,
            "NOT_A_POSITIVE_INTEGER",
        ),
        controls,
    )
    _probe(
        "target_reached_statistical_freeze_missing",
        "target reached but statistical freeze missing stays blocked",
        lambda: _gate_blocked_with(
            _mutate(
                _mutate(base, "statistical_freeze", None),
                "pair_ledger.statistical_freeze",
                None,
            ),
            GROUP_SCIENTIFIC_FREEZE,
            "STATISTICAL_FREEZE",
        ),
        controls,
    )
    _probe(
        "target_reached_policy_freeze_missing",
        "target reached but campaign policy freeze missing stays blocked",
        lambda: _gate_blocked(
            _mutate(
                _mutate(base, "campaign_freeze", None),
                "pair_ledger.campaign_freeze",
                None,
            )
        ),
        controls,
    )
    _probe(
        "target_reached_backup_missing",
        "target reached but raw export not backed up stays blocked",
        lambda: _gate_blocked_with(
            _mutate(base, "export.backup", {"status": "MISSING"}),
            GROUP_EXPORT,
            "BACKUP",
        ),
        controls,
    )
    _probe(
        "target_reached_physical_trace_absent",
        "target reached but physical verification trace absent stays blocked",
        lambda: _gate_blocked_with(
            _mutate(base, "physical_verification", None),
            GROUP_EXPORT,
            "PHYSICAL_VERIFICATION",
        ),
        controls,
    )
    _probe(
        "target_changed_after_attempts_started",
        "an approved target cannot change after attempts started",
        lambda: _gate_blocked_with(
            _mutate(
                _mutate(
                    base,
                    "target_history",
                    [
                        {
                            "target_record_sha256": "1" * 64,
                            "pairs_recorded_when_changed": 1,
                            "approved_by": {
                                "authority_id": "TEST_FIXTURE_ONLY",
                                "authority_role": "TEAM_LEAD",
                                "canonical_ref": "test://w20/fixture-target-change",
                            },
                        }
                    ],
                ),
                "target_freeze_stage",
                "BEFORE_CAMPAIGN_START",
            ),
            GROUP_PAIR_TARGET,
            "TARGET_CHANGED_AFTER_ATTEMPTS_STARTED",
        ),
        controls,
    )
    _probe(
        "null_freeze_value_not_approved",
        "a freeze field with a null value cannot be approved",
        lambda: _gate_blocked_with(
            _mutate(
                _mutate(
                    _mutate(
                        base,
                        "campaign_freeze.fields.hardware_config_id.value",
                        None,
                    ),
                    "pair_ledger.campaign_freeze.fields.hardware_config_id.value",
                    None,
                ),
                "changes",
                [],
            ),
            GROUP_STABILITY,
            "MANIFEST_IDENTITY_MISSING",
        )
        or _gate_blocked_with(
            _mutate(
                _mutate(
                    base,
                    "campaign_freeze.fields.hardware_config_id.value",
                    None,
                ),
                "pair_ledger.campaign_freeze.fields.hardware_config_id.value",
                None,
            ),
            GROUP_SCIENTIFIC_FREEZE,
            "FREEZE",
        ),
        controls,
    )
    _probe(
        "freeze_evidence_revision_disagrees",
        "freeze evidence revision must match the campaign attempts",
        lambda: _gate_blocked_with(
            _mutate(
                base,
                "authorization.approved_freeze_version",
                "DIFFERENT-FREEZE-VERSION",
            ),
            GROUP_AUTHORIZATION,
            "APPROVED_FREEZE_VERSION_MISMATCH",
        ),
        controls,
    )
    _probe(
        "operator_override_field_refused",
        "an operator-supplied override cannot bypass a refusal",
        lambda: _raises_evidence(
            _mutate(base, "force_analysis", True)
        ),
        controls,
    )

    _probe(
        "ledger_campaign_identity_mismatch_refused",
        "the ledger campaign identity must match the reviewed campaign metadata",
        lambda: _gate_blocked_with(
            _mutate(base, "pair_ledger.campaign_id", "CG-OTHER-CAMPAIGN"),
            GROUP_AUTHORIZATION,
            "LEDGER_CAMPAIGN_IDENTITY=MISMATCH",
        ),
        controls,
    )
    def _ledger_target_mismatch() -> dict[str, Any]:
        mutated = _mutate(base, "pair_ledger.frozen_target.planned_pair_target", 2)
        mutated["pair_target"] = copy.deepcopy(base["pair_target"])
        return mutated

    _probe(
        "ledger_frozen_target_mismatch_refused",
        "the ledger frozen target must match the reviewed pair-target record",
        lambda: _gate_blocked_with(
            _ledger_target_mismatch(),
            GROUP_PAIR_TARGET,
            "LEDGER_FROZEN_TARGET=MISMATCH",
        ),
        controls,
    )
    _probe(
        "ledger_statistical_freeze_mismatch_refused",
        "the ledger statistical freeze must match the reviewed freeze record",
        lambda: _gate_blocked_with(
            _mutate(base, "pair_ledger.statistical_freeze", None),
            GROUP_SCIENTIFIC_FREEZE,
            "LEDGER_STATISTICAL_FREEZE=MISMATCH",
        ),
        controls,
    )
    _probe(
        "ledger_campaign_freeze_mismatch_refused",
        "the ledger campaign freeze must match the reviewed freeze record",
        lambda: _gate_blocked_with(
            _mutate(base, "pair_ledger.campaign_freeze", None),
            GROUP_SCIENTIFIC_FREEZE,
            "LEDGER_CAMPAIGN_FREEZE=MISMATCH",
        ),
        controls,
    )
    _probe(
        "malformed_target_history_refused",
        "a malformed target-history record cannot hide a post-start change",
        lambda: _gate_blocked_with(
            _mutate(base, "target_history", {"hidden": 1}),
            GROUP_PAIR_TARGET,
            "TARGET_HISTORY_MALFORMED",
        ),
        controls,
    )
    _probe(
        "malformed_n_inflation_claim_refused",
        "a malformed N-inflation claim cannot be treated as absent",
        lambda: _gate_blocked_with(
            _mutate(base, "n_inflation_claims", {"count": 100}),
            GROUP_PAIR_COMPLETION,
            "TELEMETRY_WINDOW_INFLATION_CLAIM_MALFORMED",
        ),
        controls,
    )
    _probe(
        "w16_holdout_missing_refused",
        "missing W16 holdout evidence fails closed",
        lambda: _gate_blocked_with(
            _mutate(
                base,
                "external_links",
                {"d_policy_freeze": base["external_links"]["d_policy_freeze"]},
            ),
            GROUP_PAIR_COMPLETION,
            "W16_HOLDOUT_STATUS=MISSING",
        ),
        controls,
    )
    _probe(
        "w16_holdout_malformed_refused",
        "malformed W16 holdout evidence fails closed",
        lambda: _gate_blocked_with(
            _mutate(base, "external_links.w16_holdout", "NOT_OPENED"),
            GROUP_PAIR_COMPLETION,
            "W16_HOLDOUT_STATUS=MISSING",
        ),
        controls,
    )

    _probe(
        "valid_pair_counted_once",
        "one valid pair contributes exactly one observation",
        lambda: base_assessment.counted_valid_pairs == 1,
        controls,
    )
    _probe(
        "same_run_id_across_attempts_refused",
        "the same run counted twice is refused",
        lambda: _gate_blocked(
            _mutate(
                base,
                "pair_ledger.attempts.1.run_id",
                base["pair_ledger"]["attempts"][0]["run_id"],
            ),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )
    _probe(
        "same_physical_source_refused",
        "one physical source cannot appear under different run ids",
        lambda: _gate_blocked(
            _mutate(
                base,
                "pair_ledger.attempts.1.source_sha256",
                base["pair_ledger"]["attempts"][0]["source_sha256"],
            ),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )
    _probe(
        "rerun_of_valid_arm_refused",
        "rerunning a valid arm is not an opportunity to improve results",
        lambda: _gate_blocked(
            _add_rerun(base, source_arm="A", target_arm="A", make_target_invalid=False),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )
    _probe(
        "invalidate_pair_rule_not_bypassed",
        "an INVALIDATE_PAIR rule cannot be bypassed by a rerun",
        lambda: _gate_blocked(
            _add_rerun(
                _mutate(
                    base,
                    "pair_ledger.failure_policy.invalid_arm_handling",
                    "INVALIDATE_PAIR",
                ),
                source_arm="A",
                target_arm="A",
                make_target_invalid=True,
            ),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )
    _probe(
        "invalid_attempt_omitted_refused",
        "an invalid attempt cannot be omitted from history",
        lambda: _gate_blocked(
            _mutate(
                base,
                "pair_ledger.pairs.0.attempt_ids",
                ["ATT-TEST-001-A"],
            ),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )
    _probe(
        "aborted_attempt_dropped_refused",
        "an aborted attempt cannot be dropped from the final ledger",
        lambda: _gate_blocked(
            _drop_aborted_attempt(base),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )
    _probe(
        "missing_second_arm_not_valid",
        "a missing second arm cannot count as a valid pair",
        lambda: _gate_blocked(
            _remove_attempt(base, "B"),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )
    _probe(
        "superseded_attempt_not_independent_pair",
        "a superseded attempt cannot become an independent pair",
        lambda: _gate_blocked(
            _mutate(
                base,
                "pair_ledger.attempts.1.pair_id",
                "PAIR-TEST-002",
            ),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )
    _probe(
        "target_reached_only_by_duplicates_refused",
        "a target reached only through duplicated attempts is refused",
        lambda: _gate_blocked_with(
            _duplicate_pair(base),
            GROUP_PAIR_COMPLETION,
            "DUPLICATE",
        ),
        controls,
    )
    _probe(
        "incomplete_quality_not_valid",
        "incomplete data quality cannot be treated as valid",
        lambda: _gate_blocked(
            _mutate(
                _mutate(
                    base,
                    "pair_ledger.attempts.0.validity_status",
                    "PENDING",
                ),
                "pair_ledger.attempts.0.quality_status",
                "QUALITY_PENDING",
            ),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )
    _probe(
        "incorrect_controller_order_refused",
        "an incorrect controller order cannot be accepted silently",
        lambda: _gate_blocked(
            _mutate(
                base,
                "pair_ledger.pairs.0.actual_controller_order",
                ["B", "A"],
            ),
            GROUP_PAIR_COMPLETION,
        ),
        controls,
    )

    drift_cases = (
        (
            "model_artifact_changed",
            lambda: _mutate(
                base,
                "pair_ledger.attempts.1.model_artifact_sha256",
                "2" * 64,
            ),
            GROUP_STABILITY,
            "DRIFT",
        ),
        (
            "feature_schema_changed",
            lambda: _mutate(
                _mutate(
                    base,
                    "campaign_freeze.fields.feature_schema_hash.value",
                    "3" * 64,
                ),
                "pair_ledger.campaign_freeze.fields.feature_schema_hash.value",
                "3" * 64,
            ),
            GROUP_STABILITY,
            "feature_schema_hash",
        ),
        (
            "policy_threshold_changed",
            lambda: _mutate(
                _mutate(
                    base,
                    "campaign_freeze.fields.operating_threshold.value",
                    {"value": 0.7, "status": FREEZE_FROZEN_APPROVED},
                ),
                "pair_ledger.campaign_freeze.fields.operating_threshold.value",
                {"value": 0.7, "status": FREEZE_FROZEN_APPROVED},
            ),
            GROUP_STABILITY,
            "predictive_threshold",
        ),
        (
            "warning_persistence_changed",
            lambda: _mutate(
                _mutate(
                    base,
                    "campaign_freeze.fields.warning_persistence.value",
                    {"k": 5, "status": FREEZE_FROZEN_APPROVED},
                ),
                "pair_ledger.campaign_freeze.fields.warning_persistence.value",
                {"k": 5, "status": FREEZE_FROZEN_APPROVED},
            ),
            GROUP_STABILITY,
            "warning_persistence",
        ),
        (
            "cooling_magnitude_changed",
            lambda: _mutate(
                _mutate(
                    base,
                    "campaign_freeze.fields.cooling_action_magnitude.value",
                    {"duty": 0.5, "duration_s": 60, "status": FREEZE_FROZEN_APPROVED},
                ),
                "pair_ledger.campaign_freeze.fields.cooling_action_magnitude.value",
                {"duty": 0.5, "duration_s": 60, "status": FREEZE_FROZEN_APPROVED},
            ),
            GROUP_STABILITY,
            "cooling_action_magnitude",
        ),
        (
            "hardware_or_firmware_changed",
            lambda: _mutate(
                base,
                "pair_ledger.attempts.0.firmware_version",
                "fw-fixture-2.0.0",
            ),
            GROUP_STABILITY,
            "firmware_version",
        ),
        (
            "calibration_changed",
            lambda: _mutate(
                _mutate(
                    base,
                    "campaign_freeze.fields.calibration_id.value",
                    "CG-CAL-FIXTURE-002",
                ),
                "pair_ledger.campaign_freeze.fields.calibration_id.value",
                "CG-CAL-FIXTURE-002",
            ),
            GROUP_STABILITY,
            "calibration_id",
        ),
        (
            "disturbance_protocol_changed",
            lambda: _mutate(
                base,
                "pair_ledger.attempts.1.disturbance_protocol_id",
                "DOOR-DISTURBANCE-FIXTURE-v2",
            ),
            GROUP_STABILITY,
            "disturbance_protocol_id",
        ),
        (
            "initial_tolerance_changed",
            lambda: _mutate(
                _mutate(
                    base,
                    "campaign_freeze.fields.pair_matching_tolerances.value",
                    {
                        "initial_tmean_delta_max_c": 2.0,
                        "initial_gradient_delta_max_c": 1.0,
                    },
                ),
                "pair_ledger.campaign_freeze.fields.pair_matching_tolerances.value",
                {
                    "initial_tmean_delta_max_c": 2.0,
                    "initial_gradient_delta_max_c": 1.0,
                },
            ),
            GROUP_STABILITY,
            "pair_matching_tolerances",
        ),
        (
            "primary_outcome_definition_changed",
            lambda: _mutate(
                base,
                "statistical_freeze.fields.primary_outcome",
                "A_DIFFERENT_PRIMARY_OUTCOME",
            ),
            GROUP_SCIENTIFIC_FREEZE,
            "PRIMARY_OUTCOME_SOURCE_CONFLICT",
        ),
        (
            "drift_without_comparability_approval",
            lambda: _mutate(
                _mutate(
                    base,
                    "campaign_freeze.fields.cooling_action_magnitude.value",
                    {"duty": 0.5, "duration_s": 60, "status": FREEZE_FROZEN_APPROVED},
                ),
                "changes",
                [
                    {
                        "change_id": "CHG-INCOMPLETE",
                        "identity_id": "cooling_action_magnitude",
                    }
                ],
            ),
            GROUP_STABILITY,
            "CHANGE_CONTROL_FIELDS_INCOMPLETE",
        ),
    )
    for name, builder, group_id, token in drift_cases:
        _probe(
            name,
            f"version/protocol drift is detected at {group_id}",
            lambda builder=builder, group_id=group_id, token=token: _gate_blocked_with(
                builder(), group_id, token
            ),
            controls,
        )

    decoy_dir = tmp_dir / "outcomes"
    decoy_dir.mkdir(parents=True, exist_ok=True)
    thermal_decoy = decoy_dir / "thermal_series.csv"
    power_decoy = decoy_dir / "power_series.csv"
    thermal_decoy.write_text("t,temp\n0,24\n", encoding="utf-8")
    power_decoy.write_text("t,power\n0,12\n", encoding="utf-8")
    reader = MetadataOnlyReader(
        tmp_dir,
        [
            "outcomes/thermal_series.csv",
            "outcomes/power_series.csv",
            "decoy-allowlisted/thermal_series.csv",
        ],
    )
    decoy_allowed_dir = tmp_dir / "decoy-allowlisted"
    decoy_allowed_dir.mkdir(parents=True, exist_ok=True)
    (decoy_allowed_dir / "thermal_series.csv").write_text("x\n", encoding="utf-8")

    _probe(
        "thermal_outcome_payload_refused",
        "the preflight cannot open a thermal outcome payload",
        lambda: _raises_outcome_access(reader, "outcomes/thermal_series.csv"),
        controls,
    )
    _probe(
        "power_outcome_payload_refused",
        "the preflight cannot open a power outcome series",
        lambda: _raises_outcome_access(reader, "outcomes/power_series.csv"),
        controls,
    )
    _probe(
        "p_value_capability_refused",
        "a p-value computation is statically rejected",
        lambda: _audit_rejects("def compute_p_value(x):\n    return 0.5\n"),
        controls,
    )
    _probe(
        "paired_effect_capability_refused",
        "a paired-effect vector or CI cannot be produced",
        lambda: _audit_rejects("def paired_effect(rows):\n    return rows\n")
        and _raises_analysis_lock(),
        controls,
    )
    _probe(
        "effect_based_pair_selection_refused",
        "invalid pairs cannot be removed based on effect direction",
        lambda: _gate_blocked_with(
            _mutate(
                base,
                "selection_policy",
                {
                    "rule": "ALL_PREDECLARED",
                    "exclusions": [
                        {
                            "pair_id": "PAIR-TEST-001",
                            "reason_code": "BETTER_OUTCOME",
                            "predeclared": False,
                        }
                    ],
                },
            ),
            GROUP_PAIR_COMPLETION,
            "PAIR_EXCLUDED_WITHOUT_PREDECLARED_RULE",
        ),
        controls,
    )
    _probe(
        "synthetic_outcome_table_refused",
        "a pair-outcomes.csv cannot be generated from a synthetic fixture",
        lambda: _outcome_values_refused(),
        controls,
    )
    _probe(
        "locked_test_opened_refused",
        "an opened W16 locked test blocks the campaign lock",
        lambda: _gate_blocked_with(
            _mutate(
                base,
                "external_links",
                {
                    "d_policy_freeze": base["external_links"]["d_policy_freeze"],
                    "w16_holdout": {"status": "OPENED"},
                },
            ),
            GROUP_PAIR_COMPLETION,
            "W16_HOLDOUT_STATUS=OPENED",
        ),
        controls,
    )
    _probe(
        "preflight_does_not_start_analysis",
        "a successful software preflight never starts the final analysis",
        lambda: base_assessment.analysis_actions == ()

        and base_assessment.outcome_access is False
        and _raises_analysis_lock(),
        controls,
    )
    _probe(
        "cli_override_refused",
        "an unapproved CLI override cannot trigger evaluation",
        lambda: _parse_override_refused(),
        controls,
    )
    _probe(
        "report_keeps_analysis_not_run",
        "no result report claims scientific acceptance while analysis is NOT_RUN",
        lambda: _verdicts_keep_analysis_not_run(base_assessment),
        controls,
    )

    records = _causal_records()
    _probe(
        "closed_loop_b_ewt_refused",
        "a B-controlled trajectory cannot supply a naive counterfactual EWT",
        lambda: (
            assess_ewt_admissibility(records["closed_loop"]).status == EWT_NOT_ADMISSIBLE
        ),
        controls,
    )
    _probe(
        "missing_ewt_not_zero",
        "an unobserved reactive crossing is not an EWT of zero",
        lambda: (
            assess_ewt_admissibility(
                _mutate(records["offline"], "reactive_crossing_observed", False)
            ).status
            == EWT_UNOBSERVED
        ),
        controls,
    )
    _probe(
        "missing_aiw_not_zero",
        "missing AIW latency inputs are not zero",
        lambda: (
            assess_aiw_admissibility(
                _mutate(records["offline"], "aiw_timing_inputs_measured", False)
            ).status
            == AIW_UNKNOWN
        ),
        controls,
    )
    _probe(
        "ack_not_physical_response",
        "an ACK is not a physical response",
        lambda: (
            assess_ewt_admissibility(
                _mutate(records["offline"], "ack_only", True)
            ).status
            == EWT_NOT_ADMISSIBLE
        )
        and (
            assess_aiw_admissibility(
                _mutate(records["offline"], "ack_only", True)
            ).status
            == AIW_NOT_ADMISSIBLE
        ),
        controls,
    )
    _probe(
        "electrical_not_thermal_recovery",
        "electrical observation cannot substitute for verified thermal recovery",
        lambda: (
            assess_recovery_claim(
                _mutate(records["offline"], "electrical_observation_only", True)
            ).status
            == RECOVERY_NOT_ADMISSIBLE
        ),
        controls,
    )
    _probe(
        "pzem_gap_not_zero_energy",
        "a PZEM gap is not interpreted as zero energy",
        lambda: (
            assess_energy_claim(
                _mutate(records["offline"], "pzem_coverage", "MISSING")
            ).status
            == ENERGY_NOT_ADMISSIBLE
        ),
        controls,
    )
    _probe(
        "cooling_branch_not_whole_system",
        "cooling-branch energy is not whole-system energy",
        lambda: (
            assess_energy_claim(
                _mutate(records["offline"], "whole_system_claim", True)
            ).status
            == ENERGY_NOT_ADMISSIBLE
        ),
        controls,
    )
    _probe(
        "unfrozen_representative_temperature_refused",
        "an unfrozen representative temperature blocks the outcome definition",
        lambda: _gate_blocked_with(
            _mutate(
                base,
                "outcome_definition_freeze.fields.representative_temperature",
                {
                    "value": None,
                    "provenance": "test://w20/fixture-outcome-freeze",
                    "status": "NOT_FROZEN",
                },
            ),
            GROUP_SCIENTIFIC_FREEZE,
            "representative_temperature",
        ),
        controls,
    )
    _probe(
        "synthetic_timing_not_actionability",
        "synthetic timing cannot be promoted to real actionability evidence",
        lambda: (
            assess_aiw_admissibility(records["synthetic"]).status
            == AIW_NOT_ADMISSIBLE
        )
        and (
            validate_ab_report_contract(
                {
                    "outcome_metrics": ["thermal_exposure"],
                    "aiw_claims": [
                        {
                            "timing_source": "SYNTHETIC_REPLAY_TIMESTAMP",
                        }
                    ],
                }
            )["status"]
            != AB_CONTRACT_ACCEPTED
        ),
        controls,
    )
    _probe(
        "post_intervention_warning_not_counterfactual",
        "post-intervention warning timing is not a no-control counterfactual",
        lambda: (
            assess_ewt_admissibility(
                _mutate(records["offline"], "post_intervention_warning_used", True)
            ).status
            == EWT_NOT_ADMISSIBLE
        ),
        controls,
    )
    _probe(
        "unknown_provenance_aiw_refused",
        "AIW metadata with unknown provenance fails closed",
        lambda: (
            assess_aiw_admissibility(
                _mutate(
                    records["offline"],
                    "controller_context",
                    "UNKNOWN",
                )
            ).status
            == AIW_NOT_ADMISSIBLE
        ),
        controls,
    )
    return controls


def _raises_evidence(bundle: Mapping[str, Any]) -> bool:
    try:
        assess_campaign_lock(bundle)
    except W20EvidenceError:
        return True
    return False


def _raises_outcome_access(reader: MetadataOnlyReader, relative: str) -> bool:
    try:
        reader.read_bytes(relative)
    except W20OutcomeAccessError:
        return True
    return False


def _audit_rejects(source: str) -> bool:
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "forbidden.py"
        path.write_text(source, encoding="utf-8")
        audit = audit_w20_capability([path])
        return not audit.passed


def _raises_analysis_lock() -> bool:
    try:
        assert_outcome_analysis_locked("probe")
    except W20AnalysisLockError:
        return True
    return False


def _outcome_values_refused() -> bool:
    row = {
        "pair_id": "PAIR-TEST-001",
        "run_A_id": "ATT-TEST-001-A",
        "run_B_id": "ATT-TEST-001-B",
        "analysis_version": ANALYSIS_PLAN_VERSION_FIXTURE,
        "primary_outcome_name": PRIMARY_OUTCOME_FIXTURE,
        "primary_outcome_version": "v1",
        "coverage_status": {},
        "undefined_reason_codes": [],
        "validity_flags": {},
        "metric_versions": {},
        "A_value": 1.0,
    }
    try:
        validate_pair_outcome_metadata(row)
    except W20AnalysisLockError:
        return (
            outcome_table_contract()["table_status"] == PAIR_OUTCOME_TABLE_NOT_PRODUCED
            and not (W20_DIR / OUTCOME_TABLE_FILENAME).exists()
        )
    return False


def _parse_override_refused() -> bool:
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            _parse_args(["--evaluate"])
    except SystemExit as exc:
        return int(exc.code or 0) == 2
    return False


def _verdicts_keep_analysis_not_run(assessment: Any) -> bool:
    verdicts = _compute_verdicts(assessment, assessment)
    return (
        verdicts["W20_ANALYSIS"] == "NOT_AUTHORIZED"
        and verdicts["B_W20_02_ACTUAL_PAIR_OUTCOMES"] == "NOT_COMPUTED"
        and verdicts["B_W20_03_ACTUAL_PAIRED_DIFFERENCES"] == "NOT_COMPUTED"
        and verdicts["W20_FINAL_ANALYSIS"] == "NOT_RUN"
    )


def _drop_aborted_attempt(base: Mapping[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(base)
    ledger = mutated["pair_ledger"]
    ledger["attempts"][0]["attempt_status"] = "ABORTED"
    ledger["attempts"][0]["validity_status"] = "NOT_APPLICABLE"
    ledger["attempts"][0]["validity_reason_codes"] = ["ATTEMPT_ABORTED"]
    ledger["attempts"][0]["quality_status"] = "QUALITY_PENDING"
    ledger["pairs"][0]["attempt_ids"] = ["ATT-TEST-001-B"]
    ledger["attempts"] = [ledger["attempts"][1]]
    return mutated


def _remove_attempt(base: Mapping[str, Any], arm: str) -> dict[str, Any]:
    mutated = copy.deepcopy(base)
    ledger = mutated["pair_ledger"]
    ledger["attempts"] = [
        attempt for attempt in ledger["attempts"] if attempt["controller_arm"] != arm
    ]
    ledger["pairs"][0]["attempt_ids"] = [
        attempt_id
        for attempt_id in ledger["pairs"][0]["attempt_ids"]
        if attempt_id != f"ATT-TEST-001-{arm}"
    ]
    return mutated


def _duplicate_pair(base: Mapping[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(base)
    ledger = mutated["pair_ledger"]
    pair = ledger["pairs"][0]
    attempts = {attempt["controller_arm"]: attempt for attempt in ledger["attempts"]}
    new_pair_id = "PAIR-TEST-002"
    new_pair = copy.deepcopy(pair)
    new_pair["pair_id"] = new_pair_id
    new_pair["attempt_ids"] = []
    new_attempts: list[dict[str, Any]] = []
    for arm in ("A", "B"):
        copied = copy.deepcopy(attempts[arm])
        copied["attempt_id"] = f"ATT-TEST-002-{arm}"
        copied["pair_id"] = new_pair_id
        new_pair["attempt_ids"].append(copied["attempt_id"])
        new_attempts.append(copied)
    ledger["pairs"].append(new_pair)
    ledger["attempts"].extend(new_attempts)
    ledger["randomization"]["order_list"].append(
        {"pair_id": new_pair_id, "planned_order": ["A", "B"]}
    )
    ledger["frozen_target"]["planned_pair_target"] = 2
    ledger["campaign_freeze"]["fields"]["target_pair_count"]["value"] = 2
    mutated["pair_target"] = copy.deepcopy(ledger["frozen_target"])
    mutated["campaign_manifest"]["target_record_sha256"] = canonical_sha256(
        mutated["pair_target"]
    )
    mutated["campaign_manifest"]["registered_pair_ids"] = [
        pair["pair_id"],
        new_pair_id,
    ]
    mutated["campaign_manifest"]["registered_attempt_ids"] = [
        attempt["attempt_id"] for attempt in ledger["attempts"]
    ]
    mutated["campaign_manifest"]["registered_orders"][new_pair_id] = ["A", "B"]
    mutated["campaign_manifest"]["identities"]["target_pair_count"] = 2
    mutated["export"]["manifest"]["attempt_ids"] = [
        attempt["attempt_id"] for attempt in ledger["attempts"]
    ]
    mutated["export"]["manifest"]["source_references"].extend(
        {
            "attempt_id": attempt["attempt_id"],
            "path": attempt["source_path"],
            "sha256": attempt["source_sha256"],
        }
        for attempt in new_attempts
    )
    mutated["export"]["manifest_sha256"] = canonical_sha256(
        mutated["export"]["manifest"]
    )
    mutated["physical_verification"]["coverage_pairs"] = 2
    mutated["physical_verification"]["required_pairs"] = 2
    mutated["physical_verification"]["evidence"] = {
        "trace": "TEST_FIXTURE_ONLY",
        "pairs": [pair["pair_id"], new_pair_id],
    }
    mutated["physical_verification"]["evidence_sha256"] = canonical_sha256(
        mutated["physical_verification"]["evidence"]
    )
    return mutated


def _add_rerun(
    base: Mapping[str, Any],
    *,
    source_arm: str,
    target_arm: str,
    make_target_invalid: bool,
) -> dict[str, Any]:
    mutated = copy.deepcopy(base)
    ledger = mutated["pair_ledger"]
    attempts = {attempt["controller_arm"]: attempt for attempt in ledger["attempts"]}
    target = attempts[source_arm]
    rerun = copy.deepcopy(target)
    rerun["attempt_id"] = f"ATT-TEST-001-{target_arm}-RERUN"
    rerun["attempt_kind"] = "RERUN"
    rerun["supersedes"] = target["attempt_id"]
    rerun["run_id"] = f"RUN-TEST-001-{target_arm}-RERUN"
    rerun["source_sha256"] = hashlib.sha256(
        f"rerun-{target_arm}".encode("utf-8")
    ).hexdigest()
    rerun["source_path"] = f"test://w19/fixture/rerun-{target_arm}"
    rerun["audit_events"] = [
        {"seq": 1, "event": "ATTEMPT_CREATED", "actor": "test-fixture"},
        {"seq": 2, "event": "RERUN_RECORDED", "actor": "test-fixture"},
    ]
    if make_target_invalid:
        target["quality_status"] = "QUALITY_FAIL"
        target["validity_status"] = "INVALID"
        target["validity_reason_codes"] = ["PHYSICAL_QUALITY_INVALID"]
        rerun["quality_status"] = "QUALITY_PASS"
        rerun["validity_status"] = "VALID"
        rerun["validity_reason_codes"] = []
    target["superseded_by"] = rerun["attempt_id"]
    ledger["attempts"].append(rerun)
    ledger["pairs"][0]["attempt_ids"].append(rerun["attempt_id"])
    mutated["campaign_manifest"]["registered_attempt_ids"].append(rerun["attempt_id"])
    mutated["export"]["manifest"]["attempt_ids"].append(rerun["attempt_id"])
    mutated["export"]["manifest"]["source_references"].append(
        {
            "attempt_id": rerun["attempt_id"],
            "path": rerun["source_path"],
            "sha256": rerun["source_sha256"],
        }
    )
    mutated["export"]["manifest_sha256"] = canonical_sha256(
        mutated["export"]["manifest"]
    )
    return mutated


def _report_header(title: str) -> list[str]:
    return [
        f"# {title}",
        "",
        "Evidence class: METADATA_ONLY_FOR_REAL_CAMPAIGN plus "
        "TEST_ONLY_SOFTWARE_GATE_PROOF; no physical campaign or outcome data "
        "is present.",
        "",
        EVIDENCE_LABELS,
        "",
    ]


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return lines


def _verdict_block(lines: Sequence[str], verdicts: Sequence[tuple[str, str]]) -> None:
    lines.append("```text")
    for key, value in verdicts:
        lines.append(f"{key} = {value}")
    lines.append("```")
    lines.append("")


def _compute_verdicts(real: Any, fixture: Any) -> dict[str, str]:
    target_verdict = "UNKNOWN_UNFROZEN"
    if real.pair_target_status == "FROZEN":
        target_verdict = (
            "FROZEN_AND_COMPLETE"
            if real.counted_valid_pairs >= (real.planned_pair_target or 0)
            else "FROZEN_INCOMPLETE"
        )
    return {
        "SOFTWARE": "COMPLETE_PERMITTED_W20_SCOPE",
        "B_W20_01_CAMPAIGN_LOCK": "SOFTWARE_VERIFIED",
        "B_W20_02_PAIR_OUTCOME_CONTRACT": "SCHEMA_VERIFIED",
        "B_W20_02_ACTUAL_PAIR_OUTCOMES": "NOT_COMPUTED",
        "B_W20_03_PAIRED_ANALYSIS_CONTRACT": "REGISTERED",
        "B_W20_03_ACTUAL_PAIRED_DIFFERENCES": "NOT_COMPUTED",
        "B_W20_04_EWT_CAUSAL_BOUNDARY": "SOFTWARE_VERIFIED",
        "FINAL_CAMPAIGN": (
            "AUTHORIZED"
            if real.authorization_status == "PASS"
            and real.gate_decision != ANALYSIS_PREFLIGHT_BLOCKED
            else "NOT_AUTHORIZED"
        ),
        "PAIR_TARGET": target_verdict,
        "CAMPAIGN_LOCK": (
            "READY_FOR_EXTERNAL_REVIEW"
            if real.closeout_state
            == CLOSEOUT_CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW
            else "BLOCKED"
        ),
        "W20_ANALYSIS": "NOT_AUTHORIZED",
        "W20_FINAL_ANALYSIS": "NOT_RUN",
        "SCIENTIFIC_W20": "NOT_COMPLETE",
        "G4": "NOT_READY",
        "G5": "NOT_ESTABLISHED",
        "W16_HOLDOUT": "NOT_OPENED",
        "PHYSICAL_PAIR_EVIDENCE": "NOT_ESTABLISHED",
        "DELIVERY": "PENDING_PUBLICATION",
    }


def _campaign_integrity_report(
    real: Any,
    fixture: Any,
    checksum_w19: Any,
    checksum_w20: Any,
    probes: Sequence[Mapping[str, Any]],
    source_audit: Any,
    reader: MetadataOnlyReader,
    verdicts: Mapping[str, str],
    w18_manifest_hash: str,
) -> str:
    lines = _report_header("W20 Campaign Integrity and Analysis-Readiness Gate (B-W20-01)")
    lines.append("## Current campaign state")
    lines.append("")
    lines.extend(
        _table(
            ("Item", "Observed"),
            (
                ("Campaign authorization", real.authorization_status),
                ("Pair target", real.pair_target_status),
                ("Counted valid pairs", f"{real.counted_valid_pairs} ({real.counted_pairs_kind})"),
                ("Analysis execution authorization", real.analysis_authorization_status),
                ("Campaign close-out", real.closeout_state),
                ("Gate decision", real.gate_decision),
                ("Proof class", real.proof_class),
            ),
        )
    )
    lines.append("")
    lines.append("## Prerequisite groups (real metadata)")
    lines.append("")
    for group in real.groups:
        lines.append(f"### {group.group_id} — {group.status}")
        lines.append("")
        lines.extend(
            _table(
                (
                    "Requirement",
                    "Owner",
                    "Canonical ref",
                    "Class",
                    "Status",
                    "Evidence",
                    "Blocking consequence",
                ),
                [
                    (
                        row.requirement_id,
                        row.owner,
                        row.canonical_ref,
                        row.classification,
                        row.status,
                        row.evidence,
                        row.blocking_consequence,
                    )
                    for row in group.rows
                ],
            )
        )
        lines.append("")
    lines.append("## Protected-identity comparability audit")
    lines.append("")
    lines.extend(
        _table(
            ("Identity", "Owner", "Verdict", "Evidence"),
            [
                (row.requirement_id.replace("D:", ""), row.owner, row.status, row.evidence)
                for row in real.stability.identity_rows
            ],
        )
    )
    lines.append("")
    lines.append(
        "Drift is never silently pooled. A change requires a change ID, old/new "
        "versions, reason, authoritative approver, affected attempts/pairs, a "
        "comparability decision and analysis implications; B checks metadata "
        "completeness only and never invents the approval."
    )
    lines.append("")
    lines.append("## Cross-member evidence handoff")
    lines.append("")
    lines.append(
        "| Requirement | Owner | Source path | Revision | SHA-256 | Approval authority | Verified evidence | Verdict | Blocking consequence |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    a_w19_hash = checksum_w19.verified.get("evidence/A/W19/wave1-status.md", "ABSENT")
    a_w20_hash = checksum_w20.verified.get(
        "evidence/A/W20/campaign-wave2-index.json", "ABSENT"
    )
    lines.append(
        "| A_W19_WAVE1 | A | evidence/A/W19/wave1-status.md | 3b27b7e | "
        f"{a_w19_hash} | Member A | Member A reports 0 completed physical runs | "
        "PENDING_OPERATOR_RUN | No physical pairs exist |"
    )
    lines.append(
        "| A_W20_WAVE2 | A | evidence/A/W20/campaign-wave2-index.json | 3b27b7e | "
        f"{a_w20_hash} | Member A + operator signature | 0 runs, target_pairs 0, "
        "operator signature pending | PENDING_PHYSICAL_RUNS | Pair target and pairs absent |"
    )
    lines.append(
        "| C_W20_EXPORT | C | (not present in this stack) | "
        "659512f91c41deadef036da71544ffa8b6245d93 | ABSENT | Member C | "
        "W20 export/freeze tooling unmerged (PR 97) | UNMERGED_EXTERNAL_DEPENDENCY | "
        "No final export manifest, backup or raw-data content verification |"
    )
    lines.append(
        "| D_POLICY_FREEZE | D | (not present in this stack) | "
        "da821094985006945d0306dd7b16be576378bc18 | ABSENT | Member D | "
        "No frozen final controller policy or safety envelope | NOT_FROZEN | "
        "Policy/safety comparability cannot be established |"
    )
    lines.append(
        "| LEADER_AUTHORIZATION | TEAM_LEAD | ml/reports/W18/w18-manifest.json | "
        f"{W20_BASE_REVISION} | "
        f"{w18_manifest_hash} | Team lead | G4 NOT_READY; Controller B signoff "
        "WITHHELD | NOT_ISSUED | Campaign, target, statistical freeze and analysis "
        "authorization remain unavailable |"
    )
    lines.append("")
    lines.append("## Fixture proof (software-only)")
    lines.append("")
    lines.extend(
        _table(
            ("Item", "Value"),
            (
                ("Fixture gate", fixture.gate_decision),
                ("Fixture close-out", fixture.closeout_state),
                ("Fixture proof class", fixture.proof_class),
                ("Fixture valid pairs", fixture.counted_valid_pairs),
                ("Fixture admitted to a real campaign", "false"),
            ),
        )
    )
    lines.append("")
    lines.append("## No-outcome-access proof")
    lines.append("")
    lines.extend(
        _table(
            ("Proof", "Observed"),
            (
                ("Allowlisted metadata files read", len(reader.read_log)),
                ("Non-allowlisted path refused", "true"),
                ("Outcome-path tokens refused", "thermal_series, temperature_series, power_series, energy_series, outcome"),
                ("Static capability audit", "PASS" if source_audit.passed else "FAIL"),
                ("A W19 checksum listing", "PASS" if checksum_w19.passed else "FAIL"),
                ("A W20 checksum listing", "PASS" if checksum_w20.passed else "FAIL"),
                ("Outcome analysis actions", "NONE"),
                ("Analysis code imports analysis libraries", "false"),
            ),
        )
    )
    lines.append("")
    lines.append("## Adversarial controls")
    lines.append("")
    lines.extend(
        _table(
            ("Control", "Expectation", "Passed"),
            [
                (probe["name"], probe["expectation"], probe["passed"])
                for probe in probes
            ],
        )
    )
    lines.append("")
    lines.append(f"Controls passed: {sum(1 for p in probes if p['passed'])}/{len(probes)}")
    lines.append("")
    lines.append("## Unfinished scientific work")
    lines.append("")
    lines.append(
        "The final physical A/B campaign, accepted pair ledger, pair target, "
        "hardware/protocol freeze, statistical freeze, outcome-definition freeze, "
        "final export/backup and physical verification trace are all absent. "
        "Therefore B-W20-02 actual outcomes and B-W20-03 actual paired differences "
        "remain NOT_COMPUTED, G5 remains NOT_ESTABLISHED, and the W16 locked test "
        "remains unopened."
    )
    lines.append("")
    lines.append("## One next Member B action")
    lines.append("")
    lines.append(NEXT_MEMBER_B_ACTION)
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    _verdict_block(
        lines,
        (
            ("CAMPAIGN_LOCK", verdicts["CAMPAIGN_LOCK"]),
            ("FINAL_CAMPAIGN", verdicts["FINAL_CAMPAIGN"]),
            ("PAIR_TARGET", verdicts["PAIR_TARGET"]),
            ("W20_ANALYSIS", verdicts["W20_ANALYSIS"]),
            ("G4", verdicts["G4"]),
            ("G5", verdicts["G5"]),
        ),
    )
    return "\n".join(lines)


def _outcome_contract_report(
    contract: Mapping[str, Any],
    real: Any,
    admission_plan: Mapping[str, Any],
) -> str:
    lines = _report_header("W20 Pair-Outcomes Contract (B-W20-02) — Schema Only")
    lines.append("## Output contract")
    lines.append("")
    lines.append(
        f"Schema `{contract['schema']}`; file `{contract['filename']}`; "
        f"statistical unit: {contract['statistical_unit']}."
    )
    lines.append("")
    lines.extend(
        _table(
            ("Column", "Type", "Role", "Required", "Canonical ref"),
            [
                (
                    column["name"],
                    column["dtype"],
                    column["role"],
                    column["required"],
                    column["canonical_ref"],
                )
                for column in contract["columns"]
            ],
        )
    )
    lines.append("")
    lines.append("## Metric definitions and undefined rules")
    lines.append("")
    for metric in contract["metrics"]:
        lines.append(f"### {metric['metric_id']} ({metric['unit']})")
        lines.append("")
        lines.append(f"- Scope: {metric['scope']}")
        lines.append(f"- Formula contract: `{metric['formula_contract']}`")
        lines.append(f"- Canonical ref: {metric['canonical_ref']}")
        lines.append("- Required inputs: " + ", ".join(metric["required_inputs"]))
        lines.append("- Undefined policy: " + "; ".join(metric["undefined_policy"]))
        lines.append(
            "- Zero fill forbidden: "
            + str(metric["zero_fill_forbidden"]).lower()
        )
        lines.append(
            "- Whole-system energy forbidden: "
            + str(metric["whole_system_forbidden"]).lower()
        )
        lines.append("")
    lines.append("## Admission plan (metadata only)")
    lines.append("")
    lines.extend(
        _table(
            ("Pair", "Run A", "Run B", "Status", "Problems"),
            [
                (
                    row["pair_id"],
                    row["run_A_id"],
                    row["run_B_id"],
                    row["status"],
                    ", ".join(row["problems"]) or "none",
                )
                for row in admission_plan["rows"]
            ],
        )
    )
    lines.append("")
    lines.append(f"Admission verdict: {admission_plan['verdict']}")
    lines.append("")
    lines.append("## Withheld artifacts")
    lines.append("")
    _verdict_block(
        lines,
        (
            ("OUTCOME_TABLE", PAIR_OUTCOME_TABLE_NOT_PRODUCED),
            ("PHYSICAL_OUTCOME_DATA", PHYSICAL_OUTCOME_DATA_NOT_ADMITTED),
            ("OUTCOME_SCHEMA", OUTCOME_SCHEMA_SOFTWARE_VERIFIED),
            ("PAIR_LEDGER_FINAL", "WITHHELD_NO_ACCEPTED_PHYSICAL_CAMPAIGN"),
            ("PAIR_OUTCOMES_CSV", "WITHHELD_UNTIL_SEPARATE_AUTHORIZED_EXECUTION"),
        ),
    )
    lines.append(
        "No outcome value is computed, admitted or written. Missing coverage is "
        "reported as undefined/censored and is never converted to zero."
    )
    lines.append("")
    lines.append(f"Current gate decision: {real.gate_decision}.")
    lines.append("")
    return "\n".join(lines)


def _analysis_unlock_report(real: Any, fixture: Any, causal: Mapping[str, Any]) -> str:
    lines = _report_header("W20 Paired-Difference Contract and Analysis Lock (B-W20-03)")
    lines.append("## Registered analysis identity")
    lines.append("")
    lines.extend(
        _table(
            ("Item", "Registered value"),
            (
                ("Sign convention", REGISTERED_SIGN_CONVENTION),
                ("Meaning", "Positive = Controller B improved; negative = worsened"),
                ("Independent unit", "one valid matched Controller A/B pair"),
                ("Statistical freeze fields", ", ".join(STATISTICAL_FREEZE_FIELDS)),
                ("CI / test family", "PRECOMPUTED_ONLY; not selected in W20"),
                ("Seed / iterations", "FROZEN_INPUTS_REQUIRED; not computed in W20"),
                ("Multiplicity policy", "PREDECLARED_ONLY"),
                ("Source and result hashes", "REQUIRED_AT_AUTHORIZED_EXECUTION"),
            ),
        )
    )
    lines.append("")
    lines.append("## Missing freeze inputs (current evidence)")
    lines.append("")
    missing = []
    for field_id in STATISTICAL_FREEZE_FIELDS:
        missing.append(field_id)
    lines.append(
        "The approved statistical freeze is absent; all freeze fields remain "
        "prerequisites: " + ", ".join(missing) + "."
    )
    lines.append("")
    lines.append("## Analysis boundary proof")
    lines.append("")
    _verdict_block(
        lines,
        (
            ("PAIRED_EFFECT_COMPUTED", "NONE"),
            ("MEAN_TREATMENT_IMPROVEMENT_COMPUTED", "NONE"),
            ("P_VALUE_COMPUTED", "NONE"),
            ("CONFIDENCE_INTERVAL_COMPUTED", "NONE"),
            ("SIGNIFICANCE_FLAG_PRODUCED", "NONE"),
            ("OUTCOME_SERIES_OPENED", "NONE"),
            ("ANALYSIS_ACTIONS", "NONE"),
            ("W20_ANALYSIS", "NOT_AUTHORIZED"),
        ),
    )
    lines.append("## Causal restriction (B-W20-04)")
    lines.append("")
    lines.extend(
        _table(
            ("Restriction", "Enforced"),
            [(name, str(value).lower()) for name, value in causal["checks"].items()],
        )
    )
    lines.append("")
    lines.append(
        "Closed-loop Controller B trajectories are physical A/B outcomes, not "
        "offline EWT evidence. An unobserved reactive crossing is not zero EWT, "
        "an ACK is not a physical response, electrical observation is not "
        "thermal recovery, a PZEM gap is not zero energy, and cooling-branch "
        "energy is not whole-system energy."
    )
    lines.append("")
    lines.append("## Unlock semantics")
    lines.append("")
    lines.append(
        "This task produces a readiness receipt only. A separate authorized "
        "execution requires: (1) external campaign acceptance, (2) an approved "
        "statistical freeze, and (3) an approved analysis execution "
        "authorization. A software preflight success is not an authorization, "
        "and the fixture proof class is TEST_ONLY_SOFTWARE_GATE_PROOF."
    )
    lines.append("")
    lines.append(f"Causal proof status: {CAUSAL_BOUNDARY_SOFTWARE_VERIFIED}.")
    lines.append("")
    lines.append(f"Real gate: {real.gate_decision}; fixture gate: {fixture.gate_decision}.")
    lines.append("")
    return "\n".join(lines)


def generate(
    out_dir: Path, *, source_revision: str = W20_BASE_REVISION
) -> dict[str, Any]:
    reader = _make_reader()
    w16 = reader.read_json(W16_MANIFEST.relative_to(REPO_ROOT).as_posix())
    w17 = reader.read_json(W17_MANIFEST.relative_to(REPO_ROOT).as_posix())
    w18 = reader.read_json(W18_MANIFEST.relative_to(REPO_ROOT).as_posix())
    w18_baseline = reader.read_json(
        W18_FREEZE_BASELINE.relative_to(REPO_ROOT).as_posix()
    )
    w19_manifest = reader.read_json(W19_MANIFEST.relative_to(REPO_ROOT).as_posix())
    raw_metadata = _read_campaign_metadata(reader)
    checksum_w19 = verify_checksum_listing(
        reader,
        root="evidence/A/W19",
        sums_path="evidence/A/W19/SHA256SUMS.txt",
        allowed_files=[f"evidence/A/W19/{name}" for name in A_W19_FILES],
    )
    checksum_w20 = verify_checksum_listing(
        reader,
        root="evidence/A/W20",
        sums_path="evidence/A/W20/SHA256SUMS.txt",
        allowed_files=[f"evidence/A/W20/{name}" for name in A_W20_FILES],
    )
    if not checksum_w19.passed or not checksum_w20.passed:
        raise W20DriverError(
            "Member A dossier checksum listing failed: "
            + ", ".join(sorted(set(checksum_w19.unverified + checksum_w20.unverified)))
        )

    verified_artifacts = dict(checksum_w19.verified)
    verified_artifacts.update(checksum_w20.verified)

    pinned = _pinned_baseline(w16, w18_baseline)
    real_bundle = copy.deepcopy(raw_metadata)
    real_bundle["pinned_baseline"] = pinned
    if isinstance(real_bundle.get("external_links"), dict):
        real_bundle["external_links"]["a_w19_dossier"] = {
            "status": "SOFTWARE_READY_PENDING_OPERATOR_RUN",
            "completed_physical_runs": 0,
            "checksum_listing_passed": checksum_w19.passed,
            "verified_files": sorted(checksum_w19.verified),
        }
        real_bundle["external_links"]["a_w20_dossier"] = {
            "status": "SOFTWARE_READY_PENDING_PHYSICAL_RUNS",
            "completed_physical_runs": 0,
            "target_pairs": 0,
            "operator_signature": "PENDING_OPERATOR_PHYSICAL_SIGNATURE",
            "checksum_listing_passed": checksum_w20.passed,
            "verified_files": sorted(checksum_w20.verified),
        }
        real_bundle["external_links"]["w16_holdout"] = {
            "status": w16_holdout_status(w16).status
        }
        real_bundle["external_links"]["w18_g4"] = (
            w18.get("verdicts", {}).get("G4", "NOT_READY")
            if isinstance(w18.get("verdicts"), Mapping)
            else "NOT_READY"
        )

    real = assess_campaign_lock(real_bundle, verified_artifacts=verified_artifacts)
    fixture_bundle = build_test_only_metadata_bundle(w16, w18_baseline)
    fixture = assess_campaign_lock(fixture_bundle)

    if fixture.gate_decision != ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION:
        raise W20DriverError(
            "the valid software fixture did not pass its structural gate: "
            f"{fixture.gate_decision} / {fixture.refusal_reasons}"
        )
    if fixture.proof_class != PROOF_TEST_ONLY:
        raise W20DriverError("the fixture proof class must remain TEST_ONLY")
    if fixture.gate_decision == ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION:
        raise W20DriverError("a synthetic fixture must never reach real authorization")
    if real.gate_decision == ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION:
        raise W20DriverError(
            "the current metadata lacks external authorization and must not unlock"
        )

    source_audit = audit_w20_capability(
        [W20_SOURCE_FILES[0], W20_SOURCE_FILES[1], W20_SOURCE_FILES[2], W20_SOURCE_FILES[3]],
        display_root=ML_ROOT,
    )
    if not source_audit.passed:
        raise W20DriverError(
            "W20 capability audit failed: "
            + ", ".join(
                f"{finding.path}:{finding.line}:{finding.target}"
                for finding in source_audit.findings
            )
        )

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        probes = _campaign_controls(fixture_bundle, Path(tmp))
    failed = [probe["name"] for probe in probes if not probe["passed"]]
    if failed:
        raise W20DriverError("adversarial control(s) failed: " + ", ".join(failed))

    contract = outcome_table_contract()
    admission_plan = build_admission_plan(
        ledger_validation=None,
        outcome_definition_freeze=None,
        statistical_freeze=None,
        export_attempt_ids=None,
        coverage_records=None,
    )
    fixture_ledger_validation = None
    try:
        from coldguard_ml.w19_pair_ledger import validate_pair_ledger

        fixture_ledger_validation = validate_pair_ledger(
            fixture_bundle["pair_ledger"]
        )
    except W19OutcomeExposureError:
        fixture_ledger_validation = None
    fixture_admission = build_admission_plan(
        ledger_validation=fixture_ledger_validation,
        outcome_definition_freeze=fixture_bundle["outcome_definition_freeze"],
        statistical_freeze=fixture_bundle["statistical_freeze"],
        export_attempt_ids=fixture_bundle["export"]["manifest"]["attempt_ids"],
        coverage_records=[
            {
                "attempt_id": attempt_id,
                "metrics": {
                    metric.metric_id: "COMPLETE" for metric in OUTCOME_METRICS
                },
            }
            for attempt_id in fixture_bundle["export"]["manifest"]["attempt_ids"]
        ],
    )

    causal_proof = causal_restriction_proof()
    if causal_proof["proof_status"] != CAUSAL_BOUNDARY_SOFTWARE_VERIFIED:
        raise W20DriverError("causal restriction proof is incomplete")

    verdicts = _compute_verdicts(real, fixture)
    w18_manifest_hash = reader.sha256(
        W18_MANIFEST.relative_to(REPO_ROOT).as_posix()
    )
    reports = {
        "campaign-integrity.md": _campaign_integrity_report(
            real,
            fixture,
            checksum_w19,
            checksum_w20,
            probes,
            source_audit,
            reader,
            verdicts,
            w18_manifest_hash,
        ),
        "paired-outcome-contract-W20.md": _outcome_contract_report(
            contract, real, admission_plan
        ),
        "analysis-unlock-W20.md": _analysis_unlock_report(real, fixture, causal_proof),
    }
    report_hashes: dict[str, str] = {}
    for name, text in reports.items():
        _write(out_dir / name, text)
        report_hashes[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    unfinished: list[str] = []
    if real.authorization_status != STATUS_PASS:
        unfinished.append("FINAL_AB_CAMPAIGN_AUTHORIZATION")
    if real.pair_target_status != "FROZEN":
        unfinished.append("PAIR_TARGET_FREEZE")
    if real.group(GROUP_SCIENTIFIC_FREEZE).status != STATUS_PASS:
        unfinished.append("STATISTICAL_AND_OUTCOME_DEFINITION_FREEZE")
    if real.group(GROUP_EXPORT).status != STATUS_PASS:
        unfinished.append("FINAL_EXPORT_BACKUP_AND_PHYSICAL_TRACE")
    if real.counted_valid_pairs == 0:
        unfinished.append("ACCEPTED_PHYSICAL_PAIR_EVIDENCE")
    unfinished.extend(
        [
            "GATE_G4_READY",
            "CONTROLLER_B_SIGNOFF",
            "SEPARATE_ANALYSIS_EXECUTION_AUTHORIZATION",
        ]
    )

    manifest = {
        "schema": "coldguard-w20-campaign-lock-readiness-v1",
        "layer_version": W20_LAYER_VERSION,
        "scientific_evidence_class": "METADATA_ONLY_NO_PHYSICAL_OUTCOME_DATA",
        "source_revision": source_revision,
        "revision_semantics": W20_BASE_REVISION_SEMANTICS,
        "analysis_code_sha256": _analysis_code_sha256(),
        "w19_pair_ledger_contract": {
            "schema": PAIR_LEDGER_SCHEMA,
            "layer_version": PAIR_LEDGER_LAYER_VERSION,
        },
        "w19_validity_contract": {
            "method": VALIDITY_METHOD_VERSION,
            "metric_contracts": [
                contract_row.metric_id for contract_row in METRIC_CONTRACTS
            ],
        },
        "w19_no_peeking_contract": {
            "guard_version": PEEKING_GUARD_VERSION,
            "registered_sign_convention": REGISTERED_SIGN_CONVENTION,
        },
        "requirement_classification": {
            "B-W20-01": {
                "requirement": "Verify final campaign lock",
                "class": "CANONICAL",
                "allowed_activity": "IMPLEMENT_AND_TEST_METADATA_LEVEL_GATE",
                "software_status": "SOFTWARE_VERIFIED",
                "scientific_status": "BLOCKED_BY_EVIDENCE",
            },
            "B-W20-02": {
                "requirement": "Final valid-pair outcome table",
                "class": "CANONICAL",
                "allowed_activity": "DEFINE_AND_VALIDATE_OUTPUT_CONTRACT_ONLY",
                "software_status": "SCHEMA_VERIFIED",
                "scientific_status": "BLOCKED_BY_EVIDENCE",
            },
            "B-W20-03": {
                "requirement": "Primary paired differences",
                "class": "CANONICAL",
                "allowed_activity": "REGISTER_ANALYSIS_SEMANTICS_AND_PROTECT_BOUNDARY",
                "software_status": "REGISTERED",
                "scientific_status": "BLOCKED_BY_EVIDENCE",
            },
            "B-W20-04": {
                "requirement": "Prevent incorrect EWT claims",
                "class": "CANONICAL",
                "allowed_activity": "IMPLEMENT_CAUSAL_ROLE_AND_PROVENANCE_CHECKS",
                "software_status": "SOFTWARE_VERIFIED",
                "scientific_status": "SOFTWARE_VERIFIED_NO_PHYSICAL_RESULT",
            },
            "W20_PHYSICAL_CAMPAIGN": {
                "class": "BLOCKED_BY_EVIDENCE",
            },
            "W20_ANALYSIS_AUTHORIZATION": {
                "class": "TEAM_DEPENDENCY",
            },
            "W21_RESILIENCE_ANALYSIS": {
                "class": "SCHEDULED_DEBT",
                "owner": "B",
                "gate": "W21",
            },
        },
        "prerequisite_status": {
            "pair_target_source": "ml/reports/W20/campaign-metadata-W20.json",
            "pair_target_status": real.pair_target_status,
            "statistical_freeze_source": "ml/reports/W20/campaign-metadata-W20.json",
            "statistical_freeze_status": real.group(GROUP_SCIENTIFIC_FREEZE).status,
            "physical_data_admission": "NOT_ADMITTED_NO_PHYSICAL_OUTCOME_PAYLOAD",
            "analysis_authorization_status": real.analysis_authorization_status,
            "g4": "NOT_READY",
            "g5": "NOT_ESTABLISHED",
            "a_w19_revision": "3b27b7e",
            "a_w20_revision": "3b27b7e",
            "c_w20_revision": "659512f91c41deadef036da71544ffa8b6245d93",
            "d_w13_revision": "da821094985006945d0306dd7b16be576378bc18",
        },
        "w18_freeze_baseline_identity": _input_record(
            reader, W18_FREEZE_BASELINE
        ),
        "w16_preregistration_identity": _input_record(reader, W16_MANIFEST),
        "w19_manifest_identity": _input_record(reader, W19_MANIFEST),
        "campaign_metadata_source": _input_record(reader, CAMPAIGN_METADATA),
        "member_a_checksums": {
            "w19": checksum_w19.to_dict(),
            "w20": checksum_w20.to_dict(),
        },
        "generation_inputs": {
            "w16_locked_manifest": _input_record(reader, W16_MANIFEST),
            "w17_manifest": _input_record(reader, W17_MANIFEST),
            "w18_manifest": _input_record(reader, W18_MANIFEST),
            "w18_freeze_baseline": _input_record(reader, W18_FREEZE_BASELINE),
            "w19_manifest": _input_record(reader, W19_MANIFEST),
            "statistical_analysis_plan": _input_record(reader, STATISTICAL_PLAN),
            "metric_spec": _input_record(reader, METRIC_SPEC),
            "campaign_metadata": _input_record(reader, CAMPAIGN_METADATA),
            "a_w19_dossier": {
                name: _input_record(reader, A_W19_DIR / name) for name in A_W19_FILES
            },
            "a_w20_dossier": {
                name: _input_record(reader, A_W20_DIR / name) for name in A_W20_FILES
            },
        },
        "campaign_state": {
            "campaign_id": real.campaign_id,
            "authorization_status": real.authorization_status,
            "pair_target_status": real.pair_target_status,
            "planned_pair_target": real.planned_pair_target,
            "counted_valid_pairs": real.counted_valid_pairs,
            "counted_pairs_kind": real.counted_pairs_kind,
            "analysis_authorization_status": real.analysis_authorization_status,
            "closeout_state": real.closeout_state,
            "gate_decision": real.gate_decision,
            "proof_class": real.proof_class,
            "refusal_reasons": list(real.refusal_reasons),
            "g4": w18.get("verdicts", {}).get("G4", "NOT_READY")
            if isinstance(w18.get("verdicts"), Mapping)
            else "NOT_READY",
            "controller_b_signoff": w18.get("readiness", {}).get("signoff", "WITHHELD")
            if isinstance(w18.get("readiness"), Mapping)
            else "WITHHELD",
            "w16_holdout": w16_holdout_status(w16).to_dict(),
            "w19_verdicts": w19_manifest.get("verdicts", {})
            if isinstance(w19_manifest.get("verdicts"), Mapping)
            else {},
        },
        "groups": [group.to_dict() for group in real.groups],
        "stability": real.stability.to_dict(),
        "selection": real.selection.to_dict(),
        "fixture_proof": {
            "gate_decision": fixture.gate_decision,
            "closeout_state": fixture.closeout_state,
            "proof_class": fixture.proof_class,
            "counted_valid_pairs": fixture.counted_valid_pairs,
            "admitted_to_physical_campaign": False,
            "analysis_actions": list(fixture.analysis_actions),
            "outcome_access": fixture.outcome_access,
            "admission_plan_verdict": fixture_admission["verdict"],
        },
        "outcome_contract": {
            "schema": contract["schema"],
            "contract_version": contract["contract_version"],
            "filename": contract["filename"],
            "columns": [column["name"] for column in contract["columns"]],
            "metrics": [metric["metric_id"] for metric in contract["metrics"]],
            "undefined_reason_codes": contract["undefined_reason_codes"],
            "verdicts": schema_verdicts(),
            "current_admission_verdict": admission_plan["verdict"],
            "outcome_values_present": False,
        },
        "paired_analysis_contract": {
            "sign_convention": REGISTERED_SIGN_CONVENTION,
            "statistical_freeze_fields": list(STATISTICAL_FREEZE_FIELDS),
            "analysis_actions": [],
            "paired_effects_computed": False,
            "p_value_computed": False,
            "confidence_interval_computed": False,
            "analysis_authorized": False,
        },
        "causal_boundary": causal_proof,
        "adversarial_controls": {
            "probe_count": len(probes),
            "probes_passed": sum(1 for probe in probes if probe["passed"]),
            "probes": probes,
        },
        "capability_audit": source_audit.to_dict(),
        "metadata_files_read": list(reader.read_log),
        "verdicts": verdicts,
        "capabilities": {
            "campaign_authorization": False,
            "command_dispatch": False,
            "confidence_interval": False,
            "ewt_computation": False,
            "model_fitting": False,
            "outcome_analysis": False,
            "outcome_payload_access": False,
            "paired_effect": False,
            "p_value": False,
            "temperature_or_energy_integration": False,
            "w16_holdout_access": False,
        },
        "unfinished_scientific_work": unfinished,
        "next_member_b_action": NEXT_MEMBER_B_ACTION,
        "reports": report_hashes,
        "limitations": [
            "No final physical A/B outcome is opened, computed or reported.",
            "No physical pair evidence exists in the current B stack.",
            "No campaign authorization, pair-target freeze, statistical freeze or "
            "outcome-definition freeze has been issued.",
            "The W16 locked predictive test remains unopened.",
            "Controller B remains unauthorized for physical operation.",
            "Gate G5 is not promoted.",
            "Approval metadata is shape-checked only; external signatures cannot "
            "be verified offline.",
            "Member C's W20 export tooling is not merged into this stack; raw-data "
            "content checks remain unverified.",
            "The valid fixture proof is TEST_ONLY and cannot grant real authority.",
        ],
    }
    _write_json(out_dir / "w20-manifest.json", manifest)

    return {
        "verdicts": verdicts,
        "real": real.to_dict(),
        "fixture_gate": fixture.gate_decision,
        "fixture_proof_class": fixture.proof_class,
        "controls": {
            "probes": len(probes),
            "passed": sum(1 for probe in probes if probe["passed"]),
        },
        "manifest_sha256": hashlib.sha256(
            (
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True)
                + "\n"
            ).encode("utf-8")
        ).hexdigest(),
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="W20 metadata-only campaign-lock and analysis-readiness preflight"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=W20_DIR,
        help="directory for the W20 reports and manifest",
    )
    parser.add_argument(
        "--source-revision",
        default=W20_BASE_REVISION,
        help="source revision recorded in the manifest",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        generate(args.out_dir, source_revision=args.source_revision)
    except (
        W20DriverError,
        W20EvidenceError,
        W19OutcomeExposureError,
        W20OutcomeContractError,
        OSError,
        ValueError,
    ) as exc:
        print(f"W20 preflight refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
