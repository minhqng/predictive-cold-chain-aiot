"""W20 final campaign-lock gate: positive fixture, refusal and drift controls."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from coldguard_ml.w19_no_peeking import W19OutcomeExposureError
from coldguard_ml.w20_campaign_lock import (
    ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION,
    ANALYSIS_PREFLIGHT_BLOCKED,
    BUNDLE_PHYSICAL,
    BUNDLE_SYNTHETIC,
    CLOSEOUT_CAMPAIGN_LOCK_INCOMPLETE,
    CLOSEOUT_CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW,
    CLOSEOUT_PAIR_TARGET_NOT_FROZEN,
    CLOSEOUT_PAIR_TARGET_NOT_REACHED,
    CLOSEOUT_PAIR_TARGET_REACHED_PENDING_INTEGRITY,
    GROUP_AUTHORIZATION,
    GROUP_EXPORT,
    GROUP_PAIR_COMPLETION,
    GROUP_PAIR_TARGET,
    GROUP_SCIENTIFIC_FREEZE,
    GROUP_STABILITY,
    PROOF_TEST_ONLY,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
    W20EvidenceError,
    W20OutcomeAccessError,
    MetadataOnlyReader,
    assess_campaign_lock,
    audit_w20_capability,
    canonical_sha256,
    verify_checksum_listing,
)

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
SCRIPT = ML_ROOT / "scripts" / "w20-campaign-preflight-W20.py"
W16 = ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"
W18_BASELINE = ML_ROOT / "reports" / "W18" / "freeze-baseline-W18.json"
A_W19 = REPO_ROOT / "evidence" / "A" / "W19"
A_W20 = REPO_ROOT / "evidence" / "A" / "W20"


def _load_driver():
    spec = importlib.util.spec_from_file_location("w20_driver_campaign", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver():
    return _load_driver()


@pytest.fixture(scope="module")
def inputs(driver):
    reader = driver._make_reader()
    w16 = reader.read_json(W16.relative_to(REPO_ROOT).as_posix())
    w18 = reader.read_json(W18_BASELINE.relative_to(REPO_ROOT).as_posix())
    return w16, w18


@pytest.fixture()
def base(driver, inputs):
    w16, w18 = inputs
    return driver.build_test_only_metadata_bundle(w16, w18)


def _mutate(bundle, path, value):
    mutated = copy.deepcopy(bundle)
    cursor = mutated
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if part.isdigit() else cursor[part]
    last = parts[-1]
    if last.isdigit():
        cursor[int(last)] = value
    else:
        cursor[last] = value
    return mutated


def test_valid_fixture_passes_structural_groups_but_stays_test_only(base):
    assessment = assess_campaign_lock(base)
    assert assessment.gate_decision == ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION
    assert assessment.closeout_state == CLOSEOUT_CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW
    assert assessment.proof_class == PROOF_TEST_ONLY
    assert assessment.counted_valid_pairs == 1
    assert assessment.outcome_access is False
    assert assessment.analysis_actions == ()


def test_current_metadata_is_blocked_without_a_frozen_target(driver):
    reader = driver._make_reader()
    raw = reader.read_json(
        driver.CAMPAIGN_METADATA.relative_to(REPO_ROOT).as_posix()
    )
    assessment = assess_campaign_lock(raw)
    assert assessment.gate_decision == ANALYSIS_PREFLIGHT_BLOCKED
    assert assessment.closeout_state == CLOSEOUT_PAIR_TARGET_NOT_FROZEN
    assert assessment.pair_target_status != "FROZEN"
    for group in assessment.groups:
        assert group.status == STATUS_FAIL


def test_fake_approval_string_is_refused(base):
    mutated = _mutate(base, "authorization.record", {"status": "APPROVED"})
    assessment = assess_campaign_lock(mutated)
    assert assessment.gate_decision == ANALYSIS_PREFLIGHT_BLOCKED
    assert assessment.group(GROUP_AUTHORIZATION).status == STATUS_FAIL


def test_missing_g4_blocks(base):
    mutated = _mutate(base, "authorization.record.g4_status", "NOT_READY")
    assessment = assess_campaign_lock(mutated)
    assert assessment.gate_decision == ANALYSIS_PREFLIGHT_BLOCKED
    assert any(
        "G4" in reason for reason in assessment.group(GROUP_AUTHORIZATION).reasons
    )


def test_development_baseline_is_not_a_freeze(base):
    mutated = _mutate(
        _mutate(base, "campaign_freeze", None), "pair_ledger.campaign_freeze", None
    )
    assessment = assess_campaign_lock(mutated)
    assert assessment.gate_decision == ANALYSIS_PREFLIGHT_BLOCKED
    assert assessment.group(GROUP_SCIENTIFIC_FREEZE).status == STATUS_FAIL


def test_null_freeze_field_blocks_even_when_approved(base):
    mutated = _mutate(
        _mutate(
            _mutate(base, "campaign_freeze.fields.hardware_config_id.value", None),
            "pair_ledger.campaign_freeze.fields.hardware_config_id.value",
            None,
        ),
        "changes",
        [],
    )
    assessment = assess_campaign_lock(mutated)
    assert assessment.gate_decision == ANALYSIS_PREFLIGHT_BLOCKED
    reasons = assessment.group(GROUP_SCIENTIFIC_FREEZE).reasons
    assert any("CAMPAIGN_FREEZE_NOT_APPROVED" in reason for reason in reasons)


def test_target_change_after_attempts_started_blocks(base):
    mutated = _mutate(
        base,
        "target_history",
        [
            {
                "target_record_sha256": "1" * 64,
                "pairs_recorded_when_changed": 1,
                "approved_by": {
                    "authority_id": "TEST_FIXTURE_ONLY",
                    "authority_role": "TEAM_LEAD",
                    "canonical_ref": "test://w20/target-change",
                },
            }
        ],
    )
    assessment = assess_campaign_lock(mutated)
    assert assessment.gate_decision == ANALYSIS_PREFLIGHT_BLOCKED
    assert any(
        "TARGET_CHANGED_AFTER_ATTEMPTS_STARTED" in reason
        for reason in assessment.group(GROUP_PAIR_TARGET).reasons
    )


def test_target_not_reached_closeout(base):
    mutated = copy.deepcopy(base)
    ledger = mutated["pair_ledger"]
    ledger["attempts"] = [
        attempt for attempt in ledger["attempts"] if attempt["controller_arm"] == "A"
    ]
    ledger["pairs"][0]["attempt_ids"] = ["ATT-TEST-001-A"]
    assessment = assess_campaign_lock(mutated)
    assert assessment.closeout_state == CLOSEOUT_PAIR_TARGET_NOT_REACHED
    assert assessment.counted_valid_pairs == 0


def test_target_reached_pending_integrity_closeout(base):
    mutated = _mutate(base, "pinned_baseline", None)
    assessment = assess_campaign_lock(mutated)
    assert assessment.group(GROUP_STABILITY).status == STATUS_UNKNOWN
    assert assessment.closeout_state == CLOSEOUT_PAIR_TARGET_REACHED_PENDING_INTEGRITY
    assert assessment.gate_decision == ANALYSIS_PREFLIGHT_BLOCKED


def test_integrity_failure_closeout(base):
    mutated = _mutate(base, "export.backup", {"status": "MISSING"})
    assessment = assess_campaign_lock(mutated)
    assert assessment.closeout_state == CLOSEOUT_CAMPAIGN_LOCK_INCOMPLETE
    assert assessment.group(GROUP_EXPORT).status == STATUS_FAIL


def test_model_drift_requires_comparability_evidence(base):
    mutated = _mutate(base, "pair_ledger.attempts.1.model_artifact_sha256", "2" * 64)
    assessment = assess_campaign_lock(mutated)
    assert assessment.group(GROUP_STABILITY).status == STATUS_FAIL
    assert assessment.gate_decision == ANALYSIS_PREFLIGHT_BLOCKED


def test_complete_approved_change_record_is_applied(base):
    mutated = copy.deepcopy(base)
    freeze = mutated["campaign_freeze"]["fields"]["cooling_action_magnitude"]
    freeze["value"] = {"duty": 0.5, "duration_s": 60, "status": "FROZEN_APPROVED"}
    mutated["pair_ledger"]["campaign_freeze"]["fields"]["cooling_action_magnitude"][
        "value"
    ] = freeze["value"]
    mutated["changes"] = [
        {
            "change_id": "CHG-TEST-001",
            "identity_id": "cooling_action_magnitude",
            "old_version": "duty=1.0,duration=120",
            "new_version": "duty=0.5,duration=60",
            "reason": "test fixture comparability review",
            "approver": {
                "authority_id": "TEST_FIXTURE_ONLY",
                "authority_role": "TEAM_LEAD",
                "canonical_ref": "test://w20/change-approval",
            },
            "affected_attempts": ["*"],
            "affected_pairs": ["PAIR-TEST-001"],
            "comparability_decision": "COMPARABLE",
            "analysis_implications": "declared test-only comparability",
        }
    ]
    assessment = assess_campaign_lock(mutated)
    assert assessment.group(GROUP_STABILITY).status == STATUS_PASS
    assert "CHG-TEST-001" in assessment.stability.applied_change_ids


def test_incomplete_change_record_blocks(base):
    mutated = copy.deepcopy(base)
    mutated["campaign_freeze"]["fields"]["cooling_action_magnitude"]["value"] = {
        "duty": 0.5,
        "duration_s": 60,
        "status": "FROZEN_APPROVED",
    }
    mutated["changes"] = [
        {"change_id": "CHG-INCOMPLETE", "identity_id": "cooling_action_magnitude"}
    ]
    assessment = assess_campaign_lock(mutated)
    assert assessment.group(GROUP_STABILITY).status == STATUS_FAIL
    assert any(
        "CHANGE_CONTROL_FIELDS_INCOMPLETE" in reason
        for reason in assessment.group(GROUP_STABILITY).reasons
    )


def test_pair_roster_mismatch_blocks(base):
    mutated = _mutate(
        base, "campaign_manifest.registered_pair_ids", ["PAIR-TEST-999"]
    )
    assessment = assess_campaign_lock(mutated)
    assert assessment.group(GROUP_PAIR_COMPLETION).status == STATUS_FAIL


def test_export_attempt_mismatch_blocks(base):
    mutated = _mutate(
        base, "export.manifest.attempt_ids", ["ATT-TEST-001-A"]
    )
    assessment = assess_campaign_lock(mutated)
    assert assessment.group(GROUP_EXPORT).status == STATUS_FAIL


def test_embedded_authorization_never_reaches_real_state(base):
    mutated = copy.deepcopy(base)
    mutated["evidence_class"] = BUNDLE_PHYSICAL
    mutated["pair_ledger"]["evidence_class"] = BUNDLE_PHYSICAL
    mutated["fixture_markers"] = []
    mutated["analysis_execution_authorization"] = {
        "status": "ISSUED",
        "verification_status": "VERIFIED_EXTERNAL",
        "authority_id": "TEST_FIXTURE_ONLY",
        "authority_role": "TEAM_LEAD",
        "canonical_ref": "test://w20/analysis-authorization",
        "campaign_id": base["campaign_id"],
        "verification_binding": "EMBEDDED_CANONICAL_BYTES",
        "verification_artifact": {"authorization": "TEST_ONLY"},
        "verification_artifact_sha256": canonical_sha256({"authorization": "TEST_ONLY"}),
    }
    assessment = assess_campaign_lock(mutated)
    assert assessment.gate_decision != "ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION"
    assert any(
        "REQUIRES_EXTERNAL_FILE_BINDING" in reason
        for reason in assessment.refusal_reasons
    )


def test_physical_bundle_cannot_claim_fixture_markers(base):
    mutated = _mutate(base, "evidence_class", BUNDLE_PHYSICAL)
    with pytest.raises(W20EvidenceError):
        assess_campaign_lock(mutated)


def test_analysis_authorization_requires_leader_scoped_file_binding(base):
    mutated = copy.deepcopy(base)
    artifact_path = "evidence/A/W20/campaign-wave2-index.json"
    mutated["analysis_execution_authorization"] = {
        "status": "ISSUED",
        "verification_status": "VERIFIED_EXTERNAL",
        "authority_id": "TEST_FIXTURE_ONLY",
        "authority_role": "TEAM_LEAD",
        "canonical_ref": "test://w20/analysis-authorization",
        "campaign_id": base["campaign_id"],
        "verification_binding": "VERIFIED_FILE_BYTES",
        "verification_artifact_path": artifact_path,
        "verification_artifact_sha256": "0" * 64,
    }
    assessment = assess_campaign_lock(
        mutated, verified_artifacts={artifact_path: "0" * 64}
    )
    assert assessment.gate_decision == ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION
    assert any(
        "ARTIFACT_PATH_NOT_AUTHORIZED" in reason
        for reason in assessment.refusal_reasons
    )


def test_ledger_contracts_must_match_top_level_records(base):
    for path, group_id, token in (
        (
            "pair_ledger.campaign_id",
            GROUP_AUTHORIZATION,
            "LEDGER_CAMPAIGN_IDENTITY=MISMATCH",
        ),
        (
            "pair_ledger.frozen_target.planned_pair_target",
            GROUP_PAIR_TARGET,
            "LEDGER_FROZEN_TARGET=MISMATCH",
        ),
        (
            "pair_ledger.statistical_freeze",
            GROUP_SCIENTIFIC_FREEZE,
            "LEDGER_STATISTICAL_FREEZE=MISMATCH",
        ),
        (
            "pair_ledger.campaign_freeze",
            GROUP_SCIENTIFIC_FREEZE,
            "LEDGER_CAMPAIGN_FREEZE=MISMATCH",
        ),
    ):
        value = 2 if path.endswith("planned_pair_target") else (
            "CG-OTHER-CAMPAIGN" if path.endswith("campaign_id") else None
        )
        mutated = _mutate(base, path, value)
        if path.endswith("planned_pair_target"):
            mutated["pair_target"] = copy.deepcopy(base["pair_target"])
        assessment = assess_campaign_lock(mutated)
        assert assessment.gate_decision == ANALYSIS_PREFLIGHT_BLOCKED
        assert any(
            token in reason for reason in assessment.group(group_id).reasons
        ), (path, assessment.group(group_id).reasons)


def test_missing_or_malformed_w16_holdout_fails_closed(base):
    missing = _mutate(
        base,
        "external_links",
        {"d_policy_freeze": base["external_links"]["d_policy_freeze"]},
    )
    assessment = assess_campaign_lock(missing)
    assert assessment.group(GROUP_PAIR_COMPLETION).status == STATUS_FAIL
    assert any(
        "W16_HOLDOUT_STATUS=MISSING" in reason
        for reason in assessment.group(GROUP_PAIR_COMPLETION).reasons
    )
    malformed = _mutate(base, "external_links.w16_holdout", "NOT_OPENED")
    assessment = assess_campaign_lock(malformed)
    assert assessment.group(GROUP_PAIR_COMPLETION).status == STATUS_FAIL


def test_malformed_histories_are_not_treated_as_absent(base):
    target_history = assess_campaign_lock(
        _mutate(base, "target_history", {"hidden": 1})
    )
    assert target_history.group(GROUP_PAIR_TARGET).status == STATUS_FAIL
    assert any(
        "TARGET_HISTORY_MALFORMED" in reason
        for reason in target_history.group(GROUP_PAIR_TARGET).reasons
    )
    inflation = assess_campaign_lock(
        _mutate(base, "n_inflation_claims", {"count": 100})
    )
    assert inflation.group(GROUP_PAIR_COMPLETION).status == STATUS_FAIL
    assert any(
        "TELEMETRY_WINDOW_INFLATION_CLAIM_MALFORMED" in reason
        for reason in inflation.group(GROUP_PAIR_COMPLETION).reasons
    )


def test_physical_g4_claim_must_match_w18_evidence(base):
    mutated = copy.deepcopy(base)
    mutated["evidence_class"] = BUNDLE_PHYSICAL
    mutated["fixture_markers"] = []
    mutated["pair_ledger"]["evidence_class"] = BUNDLE_PHYSICAL
    mutated["external_links"]["w18_g4"] = "NOT_READY"
    assessment = assess_campaign_lock(mutated)
    assert assessment.group(GROUP_AUTHORIZATION).status == STATUS_FAIL
    assert any(
        "G4_STATUS_DISAGREES_WITH_W18_EVIDENCE" in reason
        for reason in assessment.group(GROUP_AUTHORIZATION).reasons
    )


def test_outcome_payload_in_metadata_is_refused(base):
    mutated = copy.deepcopy(base)
    mutated["pair_ledger"]["attempts"][0]["thermal_exposure"] = 12.0
    with pytest.raises(W19OutcomeExposureError):
        assess_campaign_lock(mutated)


def test_unknown_bundle_field_is_refused(base):
    mutated = copy.deepcopy(base)
    mutated["force_analysis"] = True
    with pytest.raises(W20EvidenceError):
        assess_campaign_lock(mutated)


def test_metadata_reader_refuses_non_allowlisted_and_outcome_paths(tmp_path):
    decoy = tmp_path / "outcomes"
    decoy.mkdir()
    (decoy / "thermal_series.csv").write_text("t,temp\n0,24\n", encoding="utf-8")
    (decoy / "power_series.csv").write_text("t,power\n0,12\n", encoding="utf-8")
    allowlisted = tmp_path / "allowlisted"
    allowlisted.mkdir()
    (allowlisted / "thermal_series.csv").write_text("x\n", encoding="utf-8")
    reader = MetadataOnlyReader(
        tmp_path,
        ["allowlisted/thermal_series.csv", "allowlisted/metadata.md"],
    )
    with pytest.raises(W20OutcomeAccessError):
        reader.read_bytes("outcomes/thermal_series.csv")
    with pytest.raises(W20OutcomeAccessError):
        reader.read_bytes("outcomes/power_series.csv")
    with pytest.raises(W20OutcomeAccessError):
        reader.read_bytes("allowlisted/thermal_series.csv")
    with pytest.raises(W20OutcomeAccessError):
        reader.read_bytes("not-listed.md")
    assert reader.read_log == []


def test_metadata_reader_reads_only_allowlisted_bytes(tmp_path):
    file = tmp_path / "meta.md"
    file.write_bytes(b"ok\n")
    reader = MetadataOnlyReader(tmp_path, ["meta.md"])
    assert reader.read_bytes("meta.md") == b"ok\n"
    assert reader.read_log == ["meta.md"]


def test_member_a_checksum_listings_verify_against_actual_bytes(driver):
    reader = driver._make_reader()
    for directory, prefix in ((A_W19, "evidence/A/W19"), (A_W20, "evidence/A/W20")):
        verification = verify_checksum_listing(
            reader,
            root=prefix,
            sums_path=f"{prefix}/SHA256SUMS.txt",
            allowed_files=[
                f"{prefix}/{path.name}"
                for path in sorted(directory.iterdir())
                if path.is_file()
            ],
        )
        assert verification.passed
        assert verification.verified


def test_w20_sources_pass_the_capability_audit(driver):
    audit = audit_w20_capability(
        [
            ML_ROOT / "src" / "coldguard_ml" / "w20_campaign_lock.py",
            ML_ROOT / "src" / "coldguard_ml" / "w20_outcome_contract.py",
            ML_ROOT / "src" / "coldguard_ml" / "w20_causal_boundary.py",
            SCRIPT,
        ],
        display_root=ML_ROOT,
    )
    assert audit.passed, audit.findings


def test_capability_audit_detects_forbidden_analysis(tmp_path):
    source = tmp_path / "forbidden.py"
    source.write_text(
        "import scipy\n"
        "def compute_p_value(x):\n"
        "    return 0.5\n"
        "def paired_effect(x):\n"
        "    return x\n",
        encoding="utf-8",
    )
    audit = audit_w20_capability([source])
    assert not audit.passed
    kinds = {finding.kind for finding in audit.findings}
    assert "FORBIDDEN_IMPORT" in kinds
    assert "FORBIDDEN_DEFINITION" in kinds


def test_synthetic_bundle_is_permanently_marked(base):
    assert base["fixture_markers"] == ["TEST_ONLY", "SYNTHETIC_SOFTWARE_CONTROL_ONLY"]
    assert base["evidence_class"] == BUNDLE_SYNTHETIC
    assert base["pair_ledger"]["evidence_class"] == BUNDLE_SYNTHETIC


def test_manifest_json_has_no_direct_outcome_values(base):
    serialized = json.dumps(base, sort_keys=True)
    for forbidden in (
        '"A_value"',
        '"B_value"',
        '"paired_improvement"',
        '"thermal_exposure_c_s"',
        '"branch_energy_wh"',
    ):
        assert forbidden not in serialized
