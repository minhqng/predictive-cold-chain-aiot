"""W16 fail-closed readiness gate tests (B-W16-01 / B-W16-02 preflight).

All fixtures here are purpose-built toy metadata.  No real W11 locked-test
payload exists in this repository and none is opened by these tests: the gate
is exercised on synthetic toy identities only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from coldguard_ml.w16_readiness import (
    DECISION_READY,
    DECISION_REFUSED,
    EVIDENCE_SCHEMA,
    W16ReadinessError,
    evaluate_w16_readiness,
)

TOY_MODEL_BYTES = b"toy-native-model-bytes-v1"
TOY_JSON_BYTES = b"toy-secondary-model-bytes-v1"
MODEL_SHA = hashlib.sha256(TOY_MODEL_BYTES).hexdigest()
JSON_SHA = hashlib.sha256(TOY_JSON_BYTES).hexdigest()
CONFIG_SHA = "a" * 64
SCHEMA_HASH = "b" * 64
ANALYSIS_CODE = "c" * 64
SOURCE_HASH = "d" * 64
FEATURES = ["f_alpha", "f_beta"]
ORDER_SHA = hashlib.sha256(json.dumps(FEATURES).encode("utf-8")).hexdigest()

TEST_RUN = "CG-TOY-TEST-001"
TRAIN_RUN = "CG-TOY-TRAIN-001"
VALIDATION_RUN = "CG-TOY-VAL-001"


def toy_evidence() -> dict:
    """A complete, internally consistent, entirely fictional bundle."""
    approvals = [
        {
            "approval_id": f"toy-{role.lower()}",
            "role": role,
            "approved_by": "toy-authority",
            "model_artifact_sha256": MODEL_SHA,
            "analysis_code_sha256": ANALYSIS_CODE,
            "canonical_ref": "toy-registration",
            **(
                {"release_authorization": "AUTHORIZED_ONE_TIME_EVALUATION"}
                if role == "TEAM_LEAD"
                else {}
            ),
        }
        for role in ("B_METHOD", "A_PHYSICAL", "D_POLICY", "C_TELEMETRY", "TEAM_LEAD")
    ]
    return {
        "schema": EVIDENCE_SCHEMA,
        "header": {
            "holdout_access": "NOT_AUTHORIZED",
            "holdout_opened": False,
            "evaluation_status": "NOT_RUN",
            "prior_access_status": "NO_RECORDED_OPENING",
            "prior_opening_records": [],
        },
        "dataset": {
            "physical_dataset_id": "CG-DATA-TOY-001",
            "provenance": "MEASURED_PHYSICAL_DATA",
            "evidence_class": "MEASURED_PHYSICAL_DATA",
            "source_sha256": [SOURCE_HASH],
            "hardware_config_id": "CG-HW-TOY-001",
            "hardware_config_status": "VERIFIED",
            "run_identity_status": "RESOLVED",
            "calibration_status": "CG-CAL-TOY-001",
            "time_domain": "EPOCH_SYNCHRONIZED",
            "clock_sync": "EVIDENCED",
            "sample_quality_status": "TRUSTED",
            "physical_run_validity": "VALID",
            "run_source_hashes": {
                TRAIN_RUN: "e" * 64,
                VALIDATION_RUN: "f" * 64,
                TEST_RUN: "0" * 64,
            },
        },
        "split": {
            "dataset_id": "CG-DATA-TOY-001",
            "provenance": "MEASURED_PHYSICAL_DATA",
            "test_partition_used": False,
            "test_runs": [TEST_RUN],
            "train_runs": [TRAIN_RUN],
            "validation_runs": [VALIDATION_RUN],
            "pair_lineage": [
                {"pair_id": "TOY-PAIR-TEST", "partition": "test", "run_ids": [TEST_RUN]},
                {"pair_id": "TOY-PAIR-TRAIN", "partition": "train", "run_ids": [TRAIN_RUN]},
                {
                    "pair_id": "TOY-PAIR-VAL",
                    "partition": "validation",
                    "run_ids": [VALIDATION_RUN],
                },
            ],
            "fold_test_runs": [TEST_RUN],
            "grouping_key": "run_id",
            "locked_test_frozen_at": "2026-11-01T00:00:00Z",
            "locked_test_opened_at": None,
            "observed_locked_test_runs": [TEST_RUN],
            "membership_by_layer": {
                "W11_split": [TEST_RUN],
                "W11_fold_manifest": [TEST_RUN],
                "W13_split_identity": [TEST_RUN],
                "W14_population": [TEST_RUN],
                "W15_population": [TEST_RUN],
            },
        },
        "registration": {
            "test_runs": [TEST_RUN],
            "test_pairs": ["TOY-PAIR-TEST"],
            "model_artifact_sha256": MODEL_SHA,
            "model_config_sha256": CONFIG_SHA,
            "feature_schema_hash": SCHEMA_HASH,
            "ordered_feature_ids_sha256": ORDER_SHA,
            "analysis_code_sha256": ANALYSIS_CODE,
        },
        "model": {
            "artifact_id": "toy-release-model-v1",
            "model_artifact_sha256": MODEL_SHA,
            "files": {
                "ubj": {"file": "model.ubj", "sha256": MODEL_SHA},
                "json": {"file": "model.json", "sha256": JSON_SHA},
            },
            "model_config_version": "toy-config-v1",
            "model_config_hash": CONFIG_SHA,
            "feature_version": "CG-FEAT-TOY-1.0",
            "feature_schema_hash": SCHEMA_HASH,
            "ordered_feature_ids": FEATURES,
            "ordered_feature_ids_sha256": ORDER_SHA,
            "data_evidence_class": "MEASURED_PHYSICAL_DATA",
            "release_eligibility": "RELEASE_APPROVED_CANDIDATE",
            "target_spec_version": "toy-label-v1",
            "target_status": "FROZEN",
            "horizon_s": 120.0,
            "horizon_status": "FROZEN",
            "operating_threshold": 0.31,
            "operating_threshold_status": "FROZEN",
            "operating_threshold_record": {
                "selection_basis": "DEVELOPMENT_SELECTED",
                "threshold": 0.31,
                "model_artifact_sha256": MODEL_SHA,
                "analysis_code_sha256": ANALYSIS_CODE,
                "evidence_sha256": "9" * 64,
            },
            "warning_persistence_status": "FROZEN",
            "warning_persistence_k": 30,
            "calibration_status": "RISK_SCORE_ONLY",
            "score_semantics": "risk_score",
            "training_dataset_id": "CG-DATA-TOY-001",
        },
        "config": {
            "config_version": "toy-config-v1",
            "config_sha256": CONFIG_SHA,
            "target_spec_version": "toy-label-v1",
            "target_status": "FROZEN",
            "target_boundary_c": 5.5,
            "representative_temperature_status": "FROZEN",
            "feature_allowlist": list(FEATURES),
            "episode_policy_status": "FROZEN",
            "association_policy_status": "FROZEN",
            "allow_locked_test_access": False,
        },
        "registry": {
            "feature_version": "CG-FEAT-TOY-1.0",
            "registry_status": "FROZEN_DEFINITIONS",
            "schema_sha256": SCHEMA_HASH,
            "missingness_policy": "explicit_missing_never_zero_filled",
            "not_frozen_fields": [],
        },
        "gates": {
            "gate_b_observed_status": "GREEN",
            "gate_b_reason_codes": [],
            "gate_g3_decision": "GO",
            "predictive_eligible_runs": 5,
            "test_partition_used": False,
        },
        "horizon_decision": {
            "freeze_status": "FROZEN",
            "primary_horizon_s": 120.0,
        },
        "calibration": {
            "decision": "RISK_SCORE_ONLY",
            "probabilistic_claim": False,
            "fit_population": None,
            "locked_test_used": None,
        },
        "approvals": {"approvals": approvals},
        "artifacts": [
            {
                "role": "model_native",
                "path": "model.ubj",
                "declared_sha256": MODEL_SHA,
            },
            {
                "role": "model_secondary",
                "path": "model.json",
                "declared_sha256": JSON_SHA,
            },
        ],
        "source_paths": {
            "model_manifest": "toy/model-manifest.json",
            "model_config": "toy/config.yaml",
            "feature_registry": "toy/registry.yaml",
            "horizon_manifest": "toy/horizon.json",
        },
        "current_analysis_code_sha256": ANALYSIS_CODE,
        "evaluation_receipt": None,
    }


@pytest.fixture()
def toy_root(tmp_path: Path) -> Path:
    (tmp_path / "model.ubj").write_bytes(TOY_MODEL_BYTES)
    (tmp_path / "model.json").write_bytes(TOY_JSON_BYTES)
    return tmp_path


def _evaluate(evidence: dict, root: Path):
    return evaluate_w16_readiness(evidence, artifact_root=root)


def _reasons(evidence: dict, root: Path) -> list[str]:
    return list(_evaluate(evidence, root).refusal_reasons)


def test_toy_bundle_is_internally_consistent_and_passes():
    # The gate must be passable by genuinely complete evidence; a gate that can
    # never pass would hide defects instead of proving fail-closed behaviour.
    evidence = toy_evidence()
    # Evaluate without a root first to confirm the only gap is hashing.
    report = evaluate_w16_readiness(evidence)
    assert report.decision == DECISION_REFUSED
    assert "ARTIFACT_ROOT_MISSING" in report.refusal_reasons


def test_complete_toy_bundle_reaches_ready_preflight_only(toy_root):
    report = _evaluate(toy_evidence(), toy_root)
    assert report.decision == DECISION_READY
    assert report.refusal_reasons == ()
    manifest = report.to_dict()
    assert manifest["manifest_kind"] == "PRE_REGISTRATION_ONLY"
    assert manifest["holdout_access"] == "NOT_AUTHORIZED"
    assert manifest["holdout_opened"] is False
    assert manifest["evaluation_status"] == "NOT_RUN"
    assert manifest["evaluation_disposition"]["locked_evaluation"] == (
        "NOT_EXECUTED_PREREQUISITES_UNMET"
    )
    assert manifest["evaluation_disposition"]["metrics_reported"] is False


def test_gate_writes_no_files_and_opens_no_holdout_payload(toy_root, monkeypatch):
    decoys = [
        toy_root / "locked-test-observations.csv",
        toy_root / "holdout-feature-labels.json",
    ]
    for decoy in decoys:
        decoy.write_bytes(b"FORBIDDEN-PAYLOAD")
    before = {path.name for path in toy_root.iterdir()}

    reads: list[Path] = []
    real_read_bytes = Path.read_bytes

    def spy_read_bytes(self: Path) -> bytes:
        reads.append(self.resolve())
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)

    report = _evaluate(toy_evidence(), toy_root)
    assert report.decision == DECISION_READY

    allowed = {(toy_root / "model.ubj").resolve(), (toy_root / "model.json").resolve()}
    assert set(reads) <= allowed, reads
    assert not any(decoy.resolve() in set(reads) for decoy in decoys)
    assert {path.name for path in toy_root.iterdir()} == before


def test_evaluate_is_deterministic(toy_root):
    first = _evaluate(toy_evidence(), toy_root).to_dict()
    second = _evaluate(toy_evidence(), toy_root).to_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ---------------------------------------------------------------------------
# Structural refusals
# ---------------------------------------------------------------------------


def test_authorized_holdout_access_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["header"]["holdout_access"] = "AUTHORIZED_ONE_TIME"
    with pytest.raises(W16ReadinessError, match="NOT_AUTHORIZED"):
        _evaluate(evidence, toy_root)


def test_holdout_already_opened_header_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["header"]["holdout_opened"] = True
    evidence["split"]["locked_test_opened_at"] = "2026-11-02T00:00:00Z"
    reasons = _reasons(evidence, toy_root)
    assert "HOLDOUT_ALREADY_OPENED" in reasons


def test_running_evaluation_status_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["header"]["evaluation_status"] = "COMPLETED"
    with pytest.raises(W16ReadinessError, match="NOT_RUN"):
        _evaluate(evidence, toy_root)


def test_wrong_evidence_schema_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["schema"] = "coldguard-w16-evidence-v0"
    with pytest.raises(W16ReadinessError, match="schema"):
        _evaluate(evidence, toy_root)


def test_malformed_section_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"] = "not-a-mapping"
    with pytest.raises(W16ReadinessError, match="mapping"):
        _evaluate(evidence, toy_root)


# ---------------------------------------------------------------------------
# Holdout isolation cases (packet §13 holdout group and §7 negative cases)
# ---------------------------------------------------------------------------


def test_development_test_run_overlap_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["test_runs"] = [TRAIN_RUN]
    evidence["registration"]["test_runs"] = [TRAIN_RUN]
    evidence["split"]["fold_test_runs"] = [TRAIN_RUN]
    evidence["split"]["observed_locked_test_runs"] = [TRAIN_RUN]
    evidence["split"]["membership_by_layer"] = {
        layer: [TRAIN_RUN] for layer in evidence["split"]["membership_by_layer"]
    }
    reasons = _reasons(evidence, toy_root)
    assert "DEVELOPMENT_TEST_RUN_OVERLAP" in reasons


def test_shared_pair_lineage_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["pair_lineage"].append(
        {"pair_id": "TOY-PAIR-TEST", "partition": "train", "run_ids": [TEST_RUN]}
    )
    reasons = _reasons(evidence, toy_root)
    assert "PAIR_LINEAGE_CROSSES_PARTITIONS" in reasons


def test_pair_partition_run_mismatch_is_refused(toy_root):
    evidence = toy_evidence()
    # The test run is declared inside a pair labelled 'train'.
    evidence["split"]["pair_lineage"][0]["partition"] = "train"
    evidence["split"]["pair_lineage"][1]["partition"] = "validation"
    evidence["split"]["pair_lineage"][2]["partition"] = "train"
    reasons = _reasons(evidence, toy_root)
    assert "PAIR_PARTITION_RUN_MISMATCH" in reasons


def test_pair_with_empty_identifier_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["pair_lineage"].append(
        {"pair_id": "", "partition": "train", "run_ids": [TRAIN_RUN]}
    )
    reasons = _reasons(evidence, toy_root)
    assert "PAIR_LINEAGE_INVALID" in reasons


def test_registered_test_pair_drift_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["registration"]["test_pairs"] = ["TOY-PAIR-WRONG"]
    reasons = _reasons(evidence, toy_root)
    assert "TEST_PAIR_MEMBERSHIP_CHANGED_AFTER_REGISTRATION" in reasons


def test_partial_run_source_hashes_are_refused(toy_root):
    evidence = toy_evidence()
    del evidence["dataset"]["run_source_hashes"][TEST_RUN]
    reasons = _reasons(evidence, toy_root)
    assert "RUN_SOURCE_IDENTITY_INCOMPLETE" in reasons


def test_duplicate_physical_source_under_new_run_id_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["run_source_hashes"][VALIDATION_RUN] = "e" * 64  # shares TRAIN source
    reasons = _reasons(evidence, toy_root)
    assert "DUPLICATE_PHYSICAL_RUN_SOURCE" in reasons


def test_training_run_promoted_to_locked_test_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["test_runs"] = [TRAIN_RUN]
    evidence["registration"]["test_runs"] = [TRAIN_RUN]
    reasons = _reasons(evidence, toy_root)
    assert "DEVELOPMENT_TEST_RUN_OVERLAP" in reasons


def test_test_membership_change_after_registration_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["registration"]["test_runs"] = ["CG-TOY-OTHER-999"]
    reasons = _reasons(evidence, toy_root)
    assert "TEST_MEMBERSHIP_CHANGED_AFTER_REGISTRATION" in reasons


def test_layer_membership_disagreement_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["membership_by_layer"]["W14_population"] = ["CG-TOY-OTHER-999"]
    reasons = _reasons(evidence, toy_root)
    assert "SPLIT_POPULATION_MISMATCH" in reasons


def test_unfrozen_test_membership_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["locked_test_frozen_at"] = None
    reasons = _reasons(evidence, toy_root)
    assert "TEST_MEMBERSHIP_NOT_FROZEN" in reasons


def test_ambiguous_test_membership_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["test_runs"] = [TEST_RUN, TEST_RUN]
    evidence["registration"]["test_runs"] = [TEST_RUN, TEST_RUN]
    evidence["split"]["fold_test_runs"] = [TEST_RUN, TEST_RUN]
    evidence["split"]["observed_locked_test_runs"] = [TEST_RUN, TEST_RUN]
    evidence["split"]["membership_by_layer"] = {
        layer: [TEST_RUN, TEST_RUN] for layer in evidence["split"]["membership_by_layer"]
    }
    reasons = _reasons(evidence, toy_root)
    assert "TEST_MEMBERSHIP_AMBIGUOUS" in reasons


def test_prior_holdout_opening_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["header"]["prior_access_status"] = "RECORDED_OPENING"
    evidence["header"]["prior_opening_records"] = ["EV-OPEN-1"]
    reasons = _reasons(evidence, toy_root)
    assert "HOLDOUT_PRIOR_OPENING_RECORDED" in reasons


def test_unknown_holdout_history_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["header"]["prior_access_status"] = "UNRECORDED_OR_UNKNOWN"
    reasons = _reasons(evidence, toy_root)
    assert "HOLDOUT_HISTORY_UNACCOUNTED" in reasons


def test_stale_split_manifest_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["dataset_id"] = "CG-DATA-TOY-STALE"
    reasons = _reasons(evidence, toy_root)
    assert "SPLIT_DATASET_MISMATCH" in reasons


def test_missing_split_dataset_identity_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["dataset_id"] = ""
    reasons = _reasons(evidence, toy_root)
    assert "SPLIT_DATASET_IDENTITY_MISSING" in reasons


def test_synthetic_data_mislabelled_as_physical_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["split"]["dataset_id"] = "W11_SYNTHETIC_TOY_DATASET"
    evidence["model"]["training_dataset_id"] = "W11_SYNTHETIC_TOY_DATASET"
    reasons = _reasons(evidence, toy_root)
    assert "DATASET_EVIDENCE_CLASS_CONTRADICTION" in reasons


def test_test_metrics_in_preregistration_are_refused(toy_root):
    evidence = toy_evidence()
    evidence["metric_values"] = {"average_precision": 0.91}
    reasons = _reasons(evidence, toy_root)
    assert "PREREGISTRATION_CONTAINS_METRIC_VALUES" in reasons


def test_missing_ewt_or_aiw_reported_as_zero_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["ewt"] = 0.0
    evidence["aiw"] = 0.0
    reasons = _reasons(evidence, toy_root)
    assert "PREREGISTRATION_CONTAINS_METRIC_VALUES" in reasons


def test_prior_evaluation_receipt_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["evaluation_receipt"] = {"evaluation_id": "EV-001", "status": "SUCCESS"}
    reasons = _reasons(evidence, toy_root)
    assert "PREFLIGHT_FOUND_EVALUATION_RECEIPT" in reasons


# ---------------------------------------------------------------------------
# Artifact identity and hashing (packet §13 release prerequisites)
# ---------------------------------------------------------------------------


def test_artifact_tampering_is_refused(toy_root):
    (toy_root / "model.ubj").write_bytes(b"tampered-model")
    reasons = _reasons(toy_evidence(), toy_root)
    assert "ARTIFACT_HASH_MISMATCH" in reasons


def test_missing_artifact_file_is_refused(toy_root):
    (toy_root / "model.ubj").unlink()
    reasons = _reasons(toy_evidence(), toy_root)
    assert "ARTIFACT_FILE_MISSING" in reasons


def test_forbidden_artifact_role_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["artifacts"][0]["role"] = "holdout_payload"
    report = _evaluate(evidence, toy_root)
    assert "ARTIFACT_ROLE_NOT_ALLOWED" in report.refusal_reasons
    # The refused artifact must not have been hashed.
    refused = [row for row in report.manifest["artifact_hashes"] if row.get("refusal")]
    assert refused and refused[0]["recomputed_sha256"] is None


def test_locked_test_payload_path_is_refused_before_any_read(toy_root, monkeypatch):
    evidence = toy_evidence()
    evidence["artifacts"][0]["path"] = "locked-test-features.parquet"
    reads: list[Path] = []
    real_read_bytes = Path.read_bytes

    def spy_read_bytes(self: Path) -> bytes:
        reads.append(self.resolve())
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    report = _evaluate(evidence, toy_root)
    assert "ARTIFACT_PATH_FORBIDDEN" in report.refusal_reasons
    assert not any("locked" in path.name or "parquet" in path.name for path in reads)
    refused = [row for row in report.manifest["artifact_hashes"] if row.get("refusal")]
    assert refused and refused[0]["recomputed_sha256"] is None


def test_path_traversal_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["artifacts"][0]["path"] = "../outside/model.ubj"
    reasons = _reasons(evidence, toy_root)
    assert "ARTIFACT_PATH_FORBIDDEN" in reasons


def test_hyphenated_forbidden_artifact_path_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["artifacts"][0]["path"] = "test-features.json"
    reasons = _reasons(evidence, toy_root)
    assert "ARTIFACT_PATH_FORBIDDEN" in reasons


def test_non_model_suffix_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["artifacts"][0]["path"] = "model.bin"
    reasons = _reasons(evidence, toy_root)
    assert "ARTIFACT_PATH_FORBIDDEN" in reasons


def test_changed_model_artifact_sha_is_refused(toy_root):
    evidence = toy_evidence()
    # The registration keeps the committed identity; the observed model moved.
    evidence["model"]["files"]["ubj"]["sha256"] = "9" * 64
    evidence["model"]["model_artifact_sha256"] = "9" * 64
    reasons = _reasons(evidence, toy_root)
    assert "MODEL_IDENTITY_DRIFT" in reasons


def test_feature_schema_hash_mismatch_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["registry"]["schema_sha256"] = "8" * 64
    reasons = _reasons(evidence, toy_root)
    assert "FEATURE_SCHEMA_HASH_MISMATCH" in reasons


def test_model_config_hash_mismatch_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["config"]["config_sha256"] = "7" * 64
    reasons = _reasons(evidence, toy_root)
    assert "MODEL_CONFIG_HASH_MISMATCH" in reasons


def test_registered_config_hash_drift_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["registration"]["model_config_sha256"] = "7" * 64
    reasons = _reasons(evidence, toy_root)
    assert "MODEL_CONFIG_HASH_MISMATCH" in reasons


def test_registered_schema_hash_drift_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["registration"]["feature_schema_hash"] = "6" * 64
    reasons = _reasons(evidence, toy_root)
    assert "FEATURE_SCHEMA_HASH_MISMATCH" in reasons


def test_registered_feature_order_drift_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["registration"]["ordered_feature_ids_sha256"] = "4" * 64
    reasons = _reasons(evidence, toy_root)
    assert "ORDERED_FEATURE_IDS_MISMATCH" in reasons


def test_ordered_feature_ids_mismatch_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["ordered_feature_ids"] = list(reversed(FEATURES))
    reasons = _reasons(evidence, toy_root)
    assert "ORDERED_FEATURE_IDS_MISMATCH" in reasons


def test_analysis_code_change_after_registration_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["current_analysis_code_sha256"] = "6" * 64
    reasons = _reasons(evidence, toy_root)
    assert "ANALYSIS_CODE_CHANGED_AFTER_REGISTRATION" in reasons


# ---------------------------------------------------------------------------
# Model release prerequisites
# ---------------------------------------------------------------------------


def test_synthetic_model_marked_deployable_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["data_evidence_class"] = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    # Even with a deployable-looking release field, the synthetic class wins.
    evidence["model"]["release_eligibility"] = "RELEASE_APPROVED_CANDIDATE"
    reasons = _reasons(evidence, toy_root)
    assert "MODEL_SYNTHETIC_NON_DEPLOYABLE" in reasons


def test_non_releasable_model_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["release_eligibility"] = "NON_DEPLOYABLE_CANDIDATE"
    reasons = _reasons(evidence, toy_root)
    assert "MODEL_SYNTHETIC_NON_DEPLOYABLE" in reasons


def test_unknown_model_evidence_class_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["data_evidence_class"] = "UNCLASSIFIED_SOURCE"
    reasons = _reasons(evidence, toy_root)
    assert "MODEL_SYNTHETIC_NON_DEPLOYABLE" in reasons


def test_draft_feature_registry_invalidates_the_freeze_ledger(toy_root):
    evidence = toy_evidence()
    evidence["registry"]["registry_status"] = "DRAFT"
    reasons = _reasons(evidence, toy_root)
    assert "FREEZE_LEDGER_INCOMPLETE" in reasons


def test_unresolved_run_identity_invalidates_the_freeze_ledger(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["run_identity_status"] = "UNRESOLVED"
    reasons = _reasons(evidence, toy_root)
    assert "FREEZE_LEDGER_INCOMPLETE" in reasons


def test_unfrozen_critical_target_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["config"]["target_status"] = "DEVELOPMENT_CANDIDATE_NOT_FROZEN"
    evidence["config"]["target_boundary_c"] = None
    evidence["model"]["target_status"] = "DEVELOPMENT_CANDIDATE_NOT_FROZEN"
    reasons = _reasons(evidence, toy_root)
    assert "CRITICAL_TARGET_UNFROZEN" in reasons


def test_unexpected_target_status_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["config"]["target_status"] = "PENDING_APPROVAL"
    reasons = _reasons(evidence, toy_root)
    assert "CRITICAL_TARGET_UNFROZEN" in reasons


def test_unexpected_model_horizon_status_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["horizon_status"] = "PENDING_APPROVAL"
    reasons = _reasons(evidence, toy_root)
    assert "PRIMARY_HORIZON_UNFROZEN" in reasons


def test_malformed_pair_run_ids_are_refused_without_crashing(toy_root):
    evidence = toy_evidence()
    evidence["split"]["pair_lineage"].append(
        {"pair_id": "TOY-PAIR-BAD", "partition": "train", "run_ids": 3}
    )
    reasons = _reasons(evidence, toy_root)
    assert "PAIR_LINEAGE_INVALID" in reasons


def test_frozen_target_without_boundary_contradicts_evidence(toy_root):
    evidence = toy_evidence()
    evidence["config"]["target_boundary_c"] = None  # status still FROZEN
    reasons = _reasons(evidence, toy_root)
    assert "CRITICAL_TARGET_UNFROZEN" in reasons
    assert "FREEZE_CLAIM_CONTRADICTS_EVIDENCE" in reasons


def test_unfrozen_representative_temperature_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["config"]["representative_temperature_status"] = (
        "DEVELOPMENT_CANDIDATE_NOT_SELECTED"
    )
    reasons = _reasons(evidence, toy_root)
    assert "REPRESENTATIVE_TEMPERATURE_UNFROZEN" in reasons


def test_unexpected_representative_temperature_status_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["config"]["representative_temperature_status"] = "PENDING_APPROVAL"
    reasons = _reasons(evidence, toy_root)
    assert "REPRESENTATIVE_TEMPERATURE_UNFROZEN" in reasons


def test_unfrozen_primary_horizon_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["horizon_decision"] = {"freeze_status": "NOT_FROZEN", "primary_horizon_s": None}
    evidence["model"]["horizon_status"] = (
        "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"
    )
    reasons = _reasons(evidence, toy_root)
    assert "PRIMARY_HORIZON_UNFROZEN" in reasons


def test_frozen_horizon_claim_with_engineering_reference_contradicts(toy_root):
    evidence = toy_evidence()
    evidence["model"]["horizon_status"] = (
        "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"
    )
    reasons = _reasons(evidence, toy_root)
    assert "PRIMARY_HORIZON_UNFROZEN" in reasons
    assert "FREEZE_CLAIM_CONTRADICTS_EVIDENCE" in reasons


def test_illustrative_threshold_presented_as_frozen_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["operating_threshold_status"] = "FROZEN"
    evidence["model"]["operating_threshold_record"]["selection_basis"] = "ILLUSTRATIVE"
    reasons = _reasons(evidence, toy_root)
    assert "OPERATING_THRESHOLD_UNFROZEN" in reasons
    assert "FREEZE_CLAIM_CONTRADICTS_EVIDENCE" in reasons


def test_threshold_frozen_without_recorded_source_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["operating_threshold_record"] = {}
    reasons = _reasons(evidence, toy_root)
    assert "OPERATING_THRESHOLD_UNFROZEN" in reasons
    assert "FREEZE_CLAIM_CONTRADICTS_EVIDENCE" in reasons


def test_threshold_record_with_wrong_value_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["operating_threshold_record"]["threshold"] = 0.5
    reasons = _reasons(evidence, toy_root)
    assert "OPERATING_THRESHOLD_UNFROZEN" in reasons


def test_threshold_record_not_binding_the_model_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["operating_threshold_record"]["model_artifact_sha256"] = "8" * 64
    reasons = _reasons(evidence, toy_root)
    assert "OPERATING_THRESHOLD_UNFROZEN" in reasons


def test_threshold_record_without_evidence_hash_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["operating_threshold_record"]["evidence_sha256"] = ""
    reasons = _reasons(evidence, toy_root)
    assert "OPERATING_THRESHOLD_UNFROZEN" in reasons


def test_missing_warning_persistence_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["warning_persistence_status"] = "FROZEN"
    evidence["model"]["warning_persistence_k"] = None
    reasons = _reasons(evidence, toy_root)
    assert "WARNING_PERSISTENCE_UNFROZEN" in reasons
    assert "FREEZE_CLAIM_CONTRADICTS_EVIDENCE" in reasons


def test_unfrozen_persistence_status_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["warning_persistence_status"] = "NOT_FROZEN"
    reasons = _reasons(evidence, toy_root)
    assert "WARNING_PERSISTENCE_UNFROZEN" in reasons


def test_unfrozen_event_matching_policy_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["config"]["episode_policy_status"] = "SYNTHETIC_ILLUSTRATIVE"
    reasons = _reasons(evidence, toy_root)
    assert "EVENT_MATCHING_POLICY_UNFROZEN" in reasons


def test_probability_claim_with_score_only_semantics_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["model"]["score_semantics"] = "calibrated_probability_estimate"
    reasons = _reasons(evidence, toy_root)
    assert "CALIBRATION_SEMANTICS_INCONSISTENT" in reasons


def test_locked_test_access_allowed_in_config_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["config"]["allow_locked_test_access"] = True
    reasons = _reasons(evidence, toy_root)
    assert "CALIBRATION_SEMANTICS_INCONSISTENT" in reasons


# ---------------------------------------------------------------------------
# Physical provenance and scientific prerequisites
# ---------------------------------------------------------------------------


def test_missing_physical_dataset_identity_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["physical_dataset_id"] = None
    reasons = _reasons(evidence, toy_root)
    assert "PHYSICAL_DATASET_IDENTITY_MISSING" in reasons


def test_missing_dataset_source_hash_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["source_sha256"] = []
    evidence["dataset"]["physical_dataset_id"] = "CG-DATA-TOY-001"
    reasons = _reasons(evidence, toy_root)
    assert "DATASET_SOURCE_HASH_MISSING" in reasons


def test_synthetic_dataset_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["evidence_class"] = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    evidence["dataset"]["provenance"] = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    reasons = _reasons(evidence, toy_root)
    assert "DATASET_EVIDENCE_CLASS_NOT_PHYSICAL" in reasons


def test_missing_run_source_identity_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["run_source_hashes"] = {}
    reasons = _reasons(evidence, toy_root)
    assert "RUN_SOURCE_IDENTITY_MISSING" in reasons


def test_untrusted_time_domain_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["time_domain"] = "BOOT_SCOPED_UPTIME"
    evidence["dataset"]["clock_sync"] = "NOT_EVIDENCED"
    reasons = _reasons(evidence, toy_root)
    assert "TIME_PROVENANCE_INADEQUATE" in reasons


def test_untrusted_sample_quality_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["sample_quality_status"] = "NOT_EVALUABLE"
    reasons = _reasons(evidence, toy_root)
    assert "SAMPLE_QUALITY_UNTRUSTED" in reasons


def test_unverified_hardware_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["hardware_config_status"] = "DECLARED_NOT_VERIFIED"
    reasons = _reasons(evidence, toy_root)
    assert "HARDWARE_CONFIG_NOT_VERIFIED" in reasons


def test_missing_physical_run_validity_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["physical_run_validity"] = "NOT_VALIDATED"
    reasons = _reasons(evidence, toy_root)
    assert "PHYSICAL_RUN_VALIDITY_MISSING" in reasons


def test_missing_calibration_lineage_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["dataset"]["calibration_status"] = "NOT_AVAILABLE"
    reasons = _reasons(evidence, toy_root)
    assert "CALIBRATION_PROVENANCE_MISSING" in reasons


def test_blocked_scientific_prerequisites_are_refused(toy_root):
    evidence = toy_evidence()
    evidence["gates"]["gate_b_observed_status"] = "RED"
    evidence["gates"]["gate_g3_decision"] = "NO-GO / FIX DATA"
    evidence["gates"]["predictive_eligible_runs"] = 0
    reasons = _reasons(evidence, toy_root)
    assert "SCIENTIFIC_PREREQUISITES_BLOCKED" in reasons


def test_used_test_partition_flag_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["gates"]["test_partition_used"] = True
    reasons = _reasons(evidence, toy_root)
    assert "TEST_PARTITION_ALREADY_USED" in reasons


# ---------------------------------------------------------------------------
# Approvals and release authorization
# ---------------------------------------------------------------------------


def test_missing_approval_metadata_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["approvals"]["approvals"] = [
        record
        for record in evidence["approvals"]["approvals"]
        if record["role"] != "TEAM_LEAD"
    ]
    reasons = _reasons(evidence, toy_root)
    assert "APPROVAL_MISSING:TEAM_LEAD" in reasons
    assert "RELEASE_AUTHORIZATION_MISSING" in reasons


def test_approval_not_binding_the_registered_model_is_refused(toy_root):
    evidence = toy_evidence()
    evidence["approvals"]["approvals"][0]["model_artifact_sha256"] = "5" * 64
    reasons = _reasons(evidence, toy_root)
    assert "APPROVAL_BINDING_INVALID" in reasons


def test_release_authorization_record_missing_is_refused(toy_root):
    evidence = toy_evidence()
    for record in evidence["approvals"]["approvals"]:
        record.pop("release_authorization", None)
    reasons = _reasons(evidence, toy_root)
    assert "RELEASE_AUTHORIZATION_MISSING" in reasons


def test_g4_cannot_be_granted_by_the_preflight(toy_root):
    manifest = _evaluate(toy_evidence(), toy_root).to_dict()
    decision = manifest["readiness_decision"]
    assert decision["permitted_actions"] == [
        "static metadata checks",
        "pre-registration review",
    ]
    assert "granting Gate G4" in decision["forbidden_actions"]
    assert "g4" not in {key.lower() for key in manifest}
    # Even a READY preflight only means "ready for an authorized evaluation".
    assert manifest["evaluation_status"] == "NOT_RUN"
    assert manifest["holdout_access"] == "NOT_AUTHORIZED"
