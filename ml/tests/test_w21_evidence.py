"""W21 evidence admission, promotion and missingness controls."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from coldguard_ml.w21_evidence import (
    CHECK_FAILED,
    CHECK_NOT_APPLICABLE,
    CHECK_NOT_VERIFIED,
    CHECK_VERIFIED,
    CLASS_DOWNGRADE_ALLOWED,
    CLASS_PROMOTION_REFUSED,
    CLASS_UNCHANGED,
    EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT,
    EVIDENCE_CONTRACT_REFERENCE,
    EVIDENCE_HOST_SOFTWARE_SIMULATION,
    EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
    EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
    GATE_BOUNDED_ON_DEVICE_EVIDENCE,
    GATE_CONTRACT_REFERENCE_ONLY,
    GATE_F_NOT_OPENED,
    GATE_F_OPEN,
    GATE_NOT_ADMISSIBLE,
    GATE_NOT_ESTABLISHED,
    GATE_PHYSICALLY_VERIFIED,
    GATE_SOFTWARE_TEST_ONLY,
    PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED,
    PROVENANCE_SOURCE_BYTES_VERIFIED,
    SourceRecord,
    W21EvidenceError,
    admit_source,
    assess_class_promotion,
    assess_gate_f,
    audit_capabilities,
    canonical_sha256,
    count_independent_sessions,
    degraded_model_inference_allowed,
    electrical_measurement,
    energy_delta,
    normalize_door_state,
    normalize_temperature,
    predictive_training_eligible,
    recovery_supported,
    refuse_class_promotion,
    require_no_capability,
    sha256_bytes,
    source_bytes_match,
    validate_source_register,
    verify_source_bytes,
)


def _record(**overrides) -> SourceRecord:
    payload = {
        "source_id": "SRC-1",
        "source_path": "evidence/A/W21/source.json",
        "source_revision": "a" * 40,
        "source_sha256": sha256_bytes(b"payload"),
        "size_bytes": 7,
        "producer": "Member A",
        "identity": {"session_key": "s1", "device_id": "d1", "boot_id": "b1"},
        "evidence_class": EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
        "scenario": "software injection",
        "observed_outcome": "explicit degraded state",
        "admissible_inference": ("explicit degraded state",),
        "unsupported_inference": ("physical failure",),
        "review_state": "RECORDED",
        "gate": GATE_BOUNDED_ON_DEVICE_EVIDENCE,
        "in_w20_ancestry": False,
        "verified_at_authoring": True,
        "measurement_bearing": True,
    }
    payload.update(overrides)
    return SourceRecord(**payload)


def test_valid_record_is_admitted_to_bounded_gate():
    admission = admit_source(_record())
    assert admission.gate == GATE_BOUNDED_ON_DEVICE_EVIDENCE
    assert admission.checks[PROVENANCE_SOURCE_BYTES_VERIFIED] == CHECK_VERIFIED
    assert (
        admission.checks[PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED]
        == CHECK_NOT_VERIFIED
    )
    assert "ACCEPTANCE_AUTHORITY_NOT_VERIFIED" in admission.refusal_reasons


def test_pinned_hashes_are_actually_checked_from_bytes(tmp_path):
    record = _record(in_w20_ancestry=True)
    path = tmp_path / record.source_path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"payload")
    ok, basis = verify_source_bytes(record, tmp_path)
    assert ok and basis == "SOURCE_SHA256_MATCH"
    path.write_bytes(b"tamper!")
    ok, basis = verify_source_bytes(record, tmp_path)
    assert not ok and basis == "SOURCE_SHA256_MISMATCH"
    path.write_bytes(b"payload-longer")
    ok, basis = verify_source_bytes(record, tmp_path)
    assert not ok and basis == "SOURCE_SIZE_MISMATCH"


def test_missing_source_file_fails_closed(tmp_path):
    record = _record(in_w20_ancestry=True)
    ok, basis = verify_source_bytes(record, tmp_path)
    assert not ok and basis == "SOURCE_FILE_MISSING_OR_SYMLINK"
    admission = admit_source(record, root=tmp_path)
    assert admission.gate == GATE_NOT_ADMISSIBLE
    assert admission.checks[PROVENANCE_SOURCE_BYTES_VERIFIED] == CHECK_FAILED


def test_source_bytes_match_is_pure():
    record = _record()
    assert source_bytes_match(record, b"payload")
    assert not source_bytes_match(record, b"payload!")
    assert not source_bytes_match(record, b"tampered")


def test_evidence_class_promotion_is_refused():
    assert (
        assess_class_promotion(
            EVIDENCE_HOST_SOFTWARE_SIMULATION, EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION
        )
        == CLASS_PROMOTION_REFUSED
    )
    assert (
        assess_class_promotion(
            EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
        )
        == CLASS_PROMOTION_REFUSED
    )
    assert (
        assess_class_promotion(
            EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
            EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT,
        )
        == CLASS_PROMOTION_REFUSED
    )
    with pytest.raises(W21EvidenceError, match=CLASS_PROMOTION_REFUSED):
        refuse_class_promotion(
            EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT,
        )


def test_evidence_class_downgrade_is_conservative_not_a_promotion():
    assert (
        assess_class_promotion(
            EVIDENCE_ACCEPTED_PHYSICAL_RESILIENCE_RESULT,
            EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
        )
        == CLASS_DOWNGRADE_ALLOWED
    )
    assert (
        assess_class_promotion(
            EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
        )
        == CLASS_UNCHANGED
    )


def test_host_simulation_reaches_only_the_software_gate():
    admission = admit_source(
        _record(
            evidence_class=EVIDENCE_HOST_SOFTWARE_SIMULATION,
            gate=GATE_SOFTWARE_TEST_ONLY,
        )
    )
    assert admission.gate == GATE_SOFTWARE_TEST_ONLY


def test_gate_must_match_the_evidence_class():
    with pytest.raises(W21EvidenceError):
        _record(
            evidence_class=EVIDENCE_HOST_SOFTWARE_SIMULATION,
            gate=GATE_PHYSICALLY_VERIFIED,
        ).validate()
    with pytest.raises(W21EvidenceError):
        _record(
            evidence_class=EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            gate=GATE_SOFTWARE_TEST_ONLY,
        ).validate()
    with pytest.raises(W21EvidenceError):
        _record(
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            gate=GATE_BOUNDED_ON_DEVICE_EVIDENCE,
            measurement_bearing=False,
        ).validate()
    _record(
        evidence_class=EVIDENCE_HOST_SOFTWARE_SIMULATION,
        gate=GATE_SOFTWARE_TEST_ONLY,
    ).validate()


def test_contract_reference_is_not_a_measurement():
    with pytest.raises(W21EvidenceError):
        _record(
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            measurement_bearing=True,
        ).validate()
    admission = admit_source(
        _record(
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            measurement_bearing=False,
        )
    )
    assert admission.gate == GATE_CONTRACT_REFERENCE_ONLY
    assert (
        admission.checks["MEASUREMENT_INTERPRETATION_SUPPORTED"]
        == CHECK_NOT_APPLICABLE
    )


def test_physical_class_without_authority_stays_unestablished():
    admission = admit_source(
        _record(
            evidence_class=EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
            gate=GATE_PHYSICALLY_VERIFIED,
        )
    )
    assert admission.gate == GATE_NOT_ESTABLISHED
    assert "PHYSICAL_ACCEPTANCE_AUTHORITY_ABSENT" in admission.refusal_reasons
    assert (
        admission.checks[PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED]
        == CHECK_NOT_VERIFIED
    )


def test_manifest_and_recorded_checks_default_fail_closed():
    admission = admit_source(_record())
    assert admission.checks["MANIFEST_COHERENT"] == CHECK_NOT_VERIFIED
    assert admission.checks["RECORDED_CHECK_PASSED"] == CHECK_NOT_VERIFIED
    assert (
        admission.checks["MEASUREMENT_INTERPRETATION_SUPPORTED"]
        == CHECK_NOT_VERIFIED
    )
    assert "CROSS_CHECK_NOT_PERFORMED" in admission.basis["MANIFEST_COHERENT"]
    crossed = admit_source(
        _record(), manifest_coherent=True, recorded_check_passed=True
    )
    assert crossed.checks["MANIFEST_COHERENT"] == CHECK_VERIFIED
    assert crossed.checks["RECORDED_CHECK_PASSED"] == CHECK_VERIFIED
    assert (
        crossed.checks["MEASUREMENT_INTERPRETATION_SUPPORTED"] == CHECK_VERIFIED
    )


def test_manifest_mismatch_fails_closed():
    admission = admit_source(_record(), manifest_coherent=False)
    assert admission.gate == GATE_NOT_ADMISSIBLE
    assert admission.checks["MANIFEST_COHERENT"] == CHECK_FAILED
    assert "MANIFEST_IDENTITY_MISMATCH" in admission.refusal_reasons


def test_recorded_check_failure_fails_closed():
    admission = admit_source(_record(), recorded_check_passed=False)
    assert admission.checks["RECORDED_CHECK_PASSED"] == CHECK_FAILED
    assert "RECORDED_CHECK_FAILED" in admission.refusal_reasons


def test_malformed_records_are_rejected():
    with pytest.raises(W21EvidenceError):
        _record(source_sha256="not-a-sha").validate()
    with pytest.raises(W21EvidenceError):
        _record(source_path="../escape.json").validate()
    with pytest.raises(W21EvidenceError):
        _record(identity={}).validate()
    with pytest.raises(W21EvidenceError):
        _record(admissible_inference=()).validate()
    with pytest.raises(W21EvidenceError):
        validate_source_register([_record(), _record()])


def test_independent_sessions_ignore_contracts_and_count_boots():
    records = [
        _record(source_id="A", identity={"session_key": "s1"}),
        _record(source_id="B", identity={"session_key": "s1"}),
        _record(
            source_id="C",
            identity={"session_key": "doc"},
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            measurement_bearing=False,
        ),
    ]
    assert count_independent_sessions(records) == 1


def test_gate_f_requires_a_bound_artifact_and_complete_core_evidence():
    assert assess_gate_f(None).status == GATE_F_NOT_OPENED
    bare = assess_gate_f({"status": "APPROVED"})
    assert bare.status == GATE_F_NOT_OPENED
    assert "UNBOUND_APPROVAL_STRING" in bare.reasons
    bound = {
        "authority_id": "LEAD-1",
        "canonical_ref": "doc-03-gate-f",
        "evidence_sha256": "a" * 64,
        "scope": "OPTIONAL_ENERGY_ANALYSIS",
        "bytes_verified": True,
    }
    no_bytes = dict(bound)
    del no_bytes["bytes_verified"]
    assert assess_gate_f(
        no_bytes, core_evidence_complete=True
    ).status == GATE_F_NOT_OPENED
    assert "AUTHORIZATION_BYTES_NOT_VERIFIED" in assess_gate_f(
        no_bytes, core_evidence_complete=True
    ).reasons
    assert assess_gate_f(bound, core_evidence_complete=False).status == (
        GATE_F_NOT_OPENED
    )
    well_formed = assess_gate_f(bound, core_evidence_complete=True)
    assert well_formed.status != GATE_F_OPEN
    assert "AUTHORIZATION_NOT_VERIFIABLE_FROM_W21" in well_formed.reasons
    assert well_formed.energy_analysis_run is False
    wrong_scope = dict(bound, scope="WHOLE_SYSTEM_ENERGY")
    assert assess_gate_f(
        wrong_scope, core_evidence_complete=True
    ).status == GATE_F_NOT_OPENED


def test_missingness_guards_never_invent_values():
    assert normalize_door_state("UNKNOWN") == "UNKNOWN"
    assert normalize_door_state(None) == "UNKNOWN"
    assert normalize_door_state("CLOSED") == "CLOSED"
    assert normalize_temperature("INVALID", 4.0) is None
    assert normalize_temperature("UNKNOWN", 4.0) is None
    assert normalize_temperature("VALID", 4.0) == 4.0
    assert normalize_temperature("VALID", float("nan")) is None
    assert electrical_measurement("VALID", 1.2, stale=True)["status"] == "MISSING"
    assert electrical_measurement("INVALID", None, stale=False)["value"] is None
    assert electrical_measurement("VALID", None, stale=False)["status"] == "MISSING"
    assert electrical_measurement("VALID", float("inf"), stale=False)["status"] == (
        "MISSING"
    )
    assert electrical_measurement("VALID", 0.0, stale=False)["status"] == "MEASURED"
    assert energy_delta(10.0, 5.0)["status"] == "COUNTER_RESET_DETECTED"
    assert energy_delta(10.0, 10.0)["delta_wh"] == 0.0
    assert energy_delta(float("nan"), 10.0)["status"] == "MISSING"
    assert energy_delta(None, 10.0)["status"] == "MISSING"
    assert recovery_supported(True, 0) is False
    assert recovery_supported(True, 1) is True
    assert recovery_supported(None, 10) is False


def test_model_and_training_guards_refuse_w21_evidence():
    assert degraded_model_inference_allowed(False) is False
    assert degraded_model_inference_allowed(True) is True
    assert predictive_training_eligible(EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION) is False
    assert predictive_training_eligible(EVIDENCE_HOST_SOFTWARE_SIMULATION) is False
    assert predictive_training_eligible(EVIDENCE_CONTRACT_REFERENCE) is False


def test_capability_audit_detects_forbidden_import_and_call(tmp_path):
    clean = tmp_path / "clean.py"
    clean.write_text("import json\njson.dumps({})\n", encoding="utf-8")
    audit = audit_capabilities([clean], base=tmp_path)
    require_no_capability(audit)
    assert all(value is False for value in audit["capabilities"].values())

    dirty = tmp_path / "dirty.py"
    dirty.write_text(
        "import socket\ndef go():\n    connect('broker', 1)\n    publish('x')\n",
        encoding="utf-8",
    )
    audit = audit_capabilities([dirty], base=tmp_path)
    with pytest.raises(W21EvidenceError):
        require_no_capability(audit)
    assert audit["capabilities"]["publish_actuator_message"] is True
    assert audit["capabilities"]["command_tec"] is True


def test_canonical_hash_is_deterministic():
    payload = {"b": [2, 1], "a": {"d": 4, "c": 3}}
    assert canonical_sha256(payload) == canonical_sha256(
        {"a": {"c": 3, "d": 4}, "b": [2, 1]}
    )
    assert canonical_sha256(payload) == hashlib.sha256(
        b'{"a":{"c":3,"d":4},"b":[2,1]}'
    ).hexdigest()
