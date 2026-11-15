"""W17 parity, model-guard and no-command proofs (B-W17-01, matrix A/D).

Every test drives real replay objects; none asserts prose.  The unused-feature
mutation test is the discriminator that prevents a score-only PASS.
"""

from __future__ import annotations

import ast
import json
import shutil
import socket
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from coldguard_ml.feature_registry import FeatureRegistry, load_registry
from coldguard_ml.w15_artifact import ArtifactError, load_guarded_artifact
from coldguard_ml.w17_shadow_parity import (
    FEATURE_TOLERANCE,
    MAX_FEATURE_TOLERANCE,
    MAX_SCORE_TOLERANCE,
    SCORE_TOLERANCE,
    AnchorDecision,
    FeatureVector,
    FreshnessPolicy,
    ReplaySession,
    ShadowTrace,
    TelemetryRecord,
    W17IdentityError,
    W17SchemaError,
    W17ToleranceError,
    W17TraceError,
    build_trace_record,
    compare_feature_vectors,
    compare_risk_scores,
    derive_illustrative_warning_rule,
    predict_vector,
    run_shadow_parity,
    validate_trace_record,
)
from coldguard_ml.xgb_benchmark import (
    build_expanded_w11_fixture,
    load_benchmark_config,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "reports" / "W15" / "model"
MODULE_PATH = ROOT / "src" / "coldguard_ml" / "w17_shadow_parity.py"
SCRIPT_PATH = ROOT / "scripts" / "w17-shadow-replay-W17.py"


@pytest.fixture(scope="module")
def registry() -> FeatureRegistry:
    return load_registry(ROOT / "feature-registry-v1.yaml")


@pytest.fixture(scope="module")
def config(registry):
    return load_benchmark_config(ROOT / "xgb-v1-config.yaml", registry)


@pytest.fixture(scope="module")
def model(registry, config):
    return load_guarded_artifact(
        manifest_path=MODEL_DIR / "model-manifest-W15.json",
        model_path=MODEL_DIR / "model.ubj",
        expected_feature_ids=config.feature_policy.allowlist,
        expected_feature_schema_hash=registry.schema_sha256,
        expected_model_config_hash=config.config_sha256,
    )


@pytest.fixture(scope="module")
def fixture():
    return build_expanded_w11_fixture()


@pytest.fixture(scope="module")
def sample_result(fixture, registry, model):
    runs = fixture.development_trajectories[:2]
    anchors = {
        item.run_id: (0.0, 40.0, 60.0, 100.0, 180.0) for item in runs
    }
    return run_shadow_parity(
        runs, registry, model=model, anchors_by_run=anchors
    )


def _decision(
    fixture, registry, model, run_index: int = 8, anchor: float = 100.0
) -> AnchorDecision:
    trajectory = fixture.development_trajectories[run_index]
    session = ReplaySession(
        template=trajectory,
        registry=registry,
        feature_ids=tuple(model.ordered_feature_ids),
    )
    for sample in trajectory.samples:
        session.ingest(
            TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
        )
    return session.feature_row_at(anchor, anchor + 1.0)


# ---------------------------------------------------------------------------
# A1-A2: clean parity and exact feature identity
# ---------------------------------------------------------------------------


def test_clean_development_replay_verifies_feature_and_prediction_parity(
    sample_result,
):
    assert sample_result.compared_anchor_count == 10
    assert sample_result.feature_parity_verified
    assert sample_result.prediction_parity_verified
    assert sample_result.offline_replay_verdict == "OFFLINE_REPLAY_VERIFIED"
    assert sample_result.first_mismatch is None
    assert sample_result.max_feature_deviation == 0.0
    assert sample_result.max_score_deviation == 0.0
    assert all(item.passed for item in sample_result.feature_comparisons)
    assert all(item.passed for item in sample_result.prediction_comparisons)


def test_all_28_ordered_model_features_are_compared(sample_result, model):
    assert len(sample_result.feature_ids) == 28
    assert sample_result.feature_ids == tuple(model.ordered_feature_ids)
    assert sample_result.defined_values + sample_result.missing_values == (
        28 * sample_result.compared_anchor_count
    )
    assert sample_result.defined_values > 0
    assert sample_result.missing_values > 0


def test_exact_feature_order_mismatch_is_rejected(sample_result):
    record = sample_result.trace["records"][0]
    ids = tuple(entry["feature_id"] for entry in record["features"])
    values = tuple(entry["value"] for entry in record["features"])
    reasons = tuple(entry["missing_reason"] for entry in record["features"])
    schema = record["feature_version"]
    registry_sha = record["registry_sha256"]
    vector = FeatureVector(ids, values, reasons, schema, registry_sha)
    swapped_ids = (ids[1], ids[0]) + ids[2:]
    swapped = replace(vector, feature_ids=swapped_ids)
    with pytest.raises(W17SchemaError):
        compare_feature_vectors(vector, swapped)


def test_missing_or_extra_feature_is_rejected(sample_result):
    record = sample_result.trace["records"][0]
    ids = tuple(entry["feature_id"] for entry in record["features"])
    values = tuple(entry["value"] for entry in record["features"])
    reasons = tuple(entry["missing_reason"] for entry in record["features"])
    vector = FeatureVector(ids, values, reasons, record["feature_version"], record["registry_sha256"])
    with pytest.raises(W17SchemaError):
        FeatureVector(ids[:-1], values, reasons, record["feature_version"], record["registry_sha256"])
    with pytest.raises(W17SchemaError):
        compare_feature_vectors(
            vector,
            FeatureVector(
                ids + ("extra_feature",),
                values + (0.0,),
                reasons + ("PRESENT",),
                record["feature_version"],
                record["registry_sha256"],
            ),
        )


# ---------------------------------------------------------------------------
# A4-A5: unused-feature mutation and model guards
# ---------------------------------------------------------------------------


def test_unused_feature_mutation_fails_parity_while_score_is_unchanged(
    sample_result, model
):
    proof = sample_result.mutation_proof
    assert proof["performed"] is True
    assert proof["detected"] is True
    assert proof["feature_parity_detected"] is True
    assert proof["score_unchanged"] is True
    assert proof["feature_id"] != "time_since_open"
    assert abs(proof["online_score"] - proof["mutated_score"]) <= SCORE_TOLERANCE


def test_model_byte_hash_mismatch_is_rejected(tmp_path, registry, config):
    manifest = tmp_path / "model-manifest-W15.json"
    model_file = tmp_path / "model.ubj"
    shutil.copy(MODEL_DIR / "model-manifest-W15.json", manifest)
    payload = bytearray((MODEL_DIR / "model.ubj").read_bytes())
    payload[-1] ^= 0xFF
    model_file.write_bytes(bytes(payload))
    with pytest.raises(ArtifactError):
        load_guarded_artifact(
            manifest_path=manifest,
            model_path=model_file,
            expected_feature_ids=config.feature_policy.allowlist,
            expected_feature_schema_hash=registry.schema_sha256,
        )


def test_feature_schema_hash_mismatch_is_rejected(registry, config):
    with pytest.raises(ArtifactError):
        load_guarded_artifact(
            manifest_path=MODEL_DIR / "model-manifest-W15.json",
            model_path=MODEL_DIR / "model.ubj",
            expected_feature_ids=config.feature_policy.allowlist,
            expected_feature_schema_hash="0" * 64,
        )


def test_wrong_library_version_is_rejected(config):
    with pytest.raises(ArtifactError):
        load_guarded_artifact(
            manifest_path=MODEL_DIR / "model-manifest-W15.json",
            model_path=MODEL_DIR / "model.ubj",
            expected_feature_ids=config.feature_policy.allowlist,
            expected_library_version="0.0.0",
        )


def test_ordered_feature_contract_mismatch_is_rejected(config):
    with pytest.raises(ArtifactError):
        load_guarded_artifact(
            manifest_path=MODEL_DIR / "model-manifest-W15.json",
            model_path=MODEL_DIR / "model.ubj",
            expected_feature_ids=tuple(reversed(config.feature_policy.allowlist)),
        )


# ---------------------------------------------------------------------------
# A8-A10: identity, trace integrity and tolerance
# ---------------------------------------------------------------------------


def test_reused_prediction_id_with_different_evidence_is_rejected(
    fixture, registry, model
):
    first = _decision(fixture, registry, model, anchor=100.0)
    second = _decision(fixture, registry, model, anchor=101.0)
    rule = derive_illustrative_warning_rule(model.manifest)[0]
    record_a = build_trace_record(
        decision=first, model=model, rule=rule, risk_score=0.1, seq=100
    )
    record_b = build_trace_record(
        decision=second, model=model, rule=rule, risk_score=0.1, seq=101
    )
    trace = ShadowTrace(header={})
    trace.add(record_a)
    trace.add(record_a)
    forged = dict(record_b)
    forged["prediction_id"] = record_a["prediction_id"]
    forged["feature_vector_sha256"] = record_a["feature_vector_sha256"]
    with pytest.raises(W17TraceError):
        trace.add(forged)


def test_contradictory_duplicate_identity_is_rejected(fixture, registry, model):
    trajectory = fixture.development_trajectories[8]
    session = ReplaySession(
        template=trajectory,
        registry=registry,
        feature_ids=tuple(model.ordered_feature_ids),
    )
    sample = next(item for item in trajectory.samples if item.time_s == 40.0)
    session.ingest(TelemetryRecord(sample=sample, arrival_time_s=40.25))
    contradictory = replace(sample, chamber_c=(("CHAMBER_CENTER", -99.0),))
    with pytest.raises(W17IdentityError):
        session.ingest(
            TelemetryRecord(sample=contradictory, arrival_time_s=40.3)
        )
    decision = session.feature_row_at(40.0, 41.0)
    assert decision.disposition == "REFUSED_IDENTITY_MISMATCH"
    assert decision.vector is None


def test_identical_duplicate_delivery_collapses(fixture, registry, model):
    trajectory = fixture.development_trajectories[8]
    session = ReplaySession(
        template=trajectory,
        registry=registry,
        feature_ids=tuple(model.ordered_feature_ids),
    )
    sample = trajectory.samples[40]
    record = TelemetryRecord(sample=sample, arrival_time_s=40.25)
    assert session.ingest(record) == "ACCEPTED"
    assert session.ingest(record) == "DUPLICATE_COLLAPSED"
    assert session.duplicate_count == 1
    assert session.accepted_count == 1


def test_feature_schema_hash_drift_is_rejected_after_loading(sample_result):
    record = sample_result.trace["records"][0]
    vector = FeatureVector(
        tuple(entry["feature_id"] for entry in record["features"]),
        tuple(entry["value"] for entry in record["features"]),
        tuple(entry["missing_reason"] for entry in record["features"]),
        record["feature_version"],
        record["registry_sha256"],
    )
    drifted = replace(vector, registry_sha256="0" * 64)
    with pytest.raises(W17SchemaError):
        compare_feature_vectors(vector, drifted)


def test_predict_vector_rejects_schema_drift(sample_result, model):
    record = sample_result.trace["records"][0]
    vector = FeatureVector(
        tuple(entry["feature_id"] for entry in record["features"]),
        tuple(entry["value"] for entry in record["features"]),
        tuple(entry["missing_reason"] for entry in record["features"]),
        record["feature_version"],
        record["registry_sha256"],
    )
    with pytest.raises(W17SchemaError):
        predict_vector(model, replace(vector, registry_sha256="0" * 64))
    with pytest.raises(W17SchemaError):
        predict_vector(model, replace(vector, feature_schema_version="OTHER"))


def test_tolerance_cannot_be_widened(sample_result):
    record = sample_result.trace["records"][0]
    vector = FeatureVector(
        tuple(entry["feature_id"] for entry in record["features"]),
        tuple(entry["value"] for entry in record["features"]),
        tuple(entry["missing_reason"] for entry in record["features"]),
        record["feature_version"],
        record["registry_sha256"],
    )
    with pytest.raises(W17ToleranceError):
        compare_feature_vectors(
            vector, vector, tolerance=MAX_FEATURE_TOLERANCE * 10
        )
    with pytest.raises(W17ToleranceError):
        compare_risk_scores(0.1, 0.1001, tolerance=MAX_SCORE_TOLERANCE * 10)


def test_tolerances_are_the_declared_constants():
    assert FEATURE_TOLERANCE == 1e-9
    assert SCORE_TOLERANCE == 1e-12
    assert MAX_FEATURE_TOLERANCE == FEATURE_TOLERANCE
    assert MAX_SCORE_TOLERANCE == SCORE_TOLERANCE


# ---------------------------------------------------------------------------
# D26-D32: shadow safety and scientific semantics
# ---------------------------------------------------------------------------


def test_compared_trace_records_verify_no_future_input(sample_result):
    for record in sample_result.trace["records"]:
        if record["risk_score"] is None:
            continue
        evidence = record["parity_evidence"]
        assert evidence["no_future_input_verified"] is True
        assert evidence["authorized_input_count"] == evidence["online_input_count"]
        assert evidence["online_input_count"] > 0
        assert evidence["offline_reference_source"] == "W10_CANONICAL_BATCH_PIPELINE"
        assert evidence["online_replay_source"] == "W17_STATEFUL_STREAMING_REPLAY"


def test_trace_record_is_not_dispatchable_and_has_no_authorized_decision(
    fixture, registry, model
):
    decision = _decision(fixture, registry, model, anchor=100.0)
    rule = derive_illustrative_warning_rule(model.manifest)[0]
    record = build_trace_record(
        decision=decision, model=model, rule=rule, risk_score=0.9, seq=100
    )
    policy = record["hypothetical_policy"]
    assert policy["status"] == "NOT_EVALUATED"
    assert policy["would_command"] is None
    assert policy["authorized_control_decision"] is None
    assert policy["dispatchable"] is False
    assert policy["physical_control_path"] is None
    assert record["hypothetical_warning"]["status"].startswith("TRIGGERED")
    assert record["hypothetical_warning"]["rule_status"] == "SYNTHETIC_ILLUSTRATIVE"
    assert record["hypothetical_warning"]["persistence"] == "NOT_FROZEN"
    assert record["hypothetical_timing"]["physical_latency"] == "NOT_MEASURED"
    assert record["hypothetical_timing"]["aiw"] != "ESTIMABLE"


def test_trace_record_rejects_a_command_or_dispatch_flag(fixture, registry, model):
    decision = _decision(fixture, registry, model, anchor=100.0)
    rule = derive_illustrative_warning_rule(model.manifest)[0]
    record = build_trace_record(
        decision=decision, model=model, rule=rule, risk_score=0.1, seq=100
    )
    tampered = dict(record)
    tampered["hypothetical_policy"] = dict(record["hypothetical_policy"])
    tampered["hypothetical_policy"]["dispatchable"] = True
    with pytest.raises(W17TraceError):
        validate_trace_record(tampered)
    tampered["hypothetical_policy"]["dispatchable"] = False
    tampered["hypothetical_policy"]["would_command"] = "COOLING_ON"
    with pytest.raises(W17TraceError):
        validate_trace_record(tampered)


def test_risk_score_semantics_are_not_probability(fixture, registry, model):
    decision = _decision(fixture, registry, model, anchor=100.0)
    rule = derive_illustrative_warning_rule(model.manifest)[0]
    record = build_trace_record(
        decision=decision, model=model, rule=rule, risk_score=0.2, seq=100
    )
    assert record["score_semantics"] == "risk_score"
    assert "probability" not in record
    assert "calibrated_probability" not in record
    tampered = dict(record)
    tampered["score_semantics"] = "probability"
    with pytest.raises(W17TraceError):
        validate_trace_record(tampered)


def test_w15_model_is_never_marked_deployable(fixture, registry, model):
    decision = _decision(fixture, registry, model, anchor=100.0)
    rule = derive_illustrative_warning_rule(model.manifest)[0]
    record = build_trace_record(
        decision=decision, model=model, rule=rule, risk_score=0.2, seq=100
    )
    assert record["model"]["release_eligibility"] == "NON_DEPLOYABLE_CANDIDATE"
    assert record["model"]["data_evidence_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert record["model"]["registered_for_operation"] is False
    assert record["model"]["deployed"] is False


def test_warning_rule_is_refused_when_the_manifest_status_changes():
    manifest = {
        "score_semantics": "risk_score",
        "calibration_status": "RISK_SCORE_ONLY",
        "operating_threshold": 0.5,
        "operating_threshold_status": "FROZEN",
    }
    rule, reason = derive_illustrative_warning_rule(manifest)
    assert rule is None
    assert reason == "REFUSED_RULE_UNAUTHORIZED"


def test_expected_feature_schema_refusal_is_reachable(fixture, registry, model):
    trajectory = fixture.development_trajectories[8]
    session = ReplaySession(
        template=trajectory,
        registry=registry,
        feature_ids=tuple(model.ordered_feature_ids),
        expected_schema_sha256="0" * 64,
    )
    for sample in trajectory.samples:
        if sample.time_s <= 40.0:
            session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    decision = session.feature_row_at(40.0, 41.0)
    assert decision.disposition == "REFUSED_FEATURE_SCHEMA_MISMATCH"
    assert "EXPECTED_FEATURE_SCHEMA_MISMATCH" in decision.reasons
    assert decision.vector is None


def test_anchor_age_is_measured_at_prediction_time(fixture, registry, model):
    trajectory = fixture.development_trajectories[8]
    session = ReplaySession(
        template=trajectory,
        registry=registry,
        feature_ids=tuple(model.ordered_feature_ids),
        policy=FreshnessPolicy(max_anchor_input_age_s=0.5),
    )
    for sample in trajectory.samples:
        if sample.time_s <= 40.0:
            session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    decision = session.feature_row_at(40.0, 41.0)
    assert decision.disposition == "REFUSED_STALE_INPUT"
    assert any("ANCHOR_INPUT_AGE" in reason for reason in decision.reasons)


def test_trace_binds_inputs_receipt_and_window(fixture, registry, model):
    decision = _decision(fixture, registry, model, anchor=100.0)
    rule = derive_illustrative_warning_rule(model.manifest)[0]
    record = build_trace_record(
        decision=decision, model=model, rule=rule, risk_score=0.2, seq=100
    )
    assert record["input_window_end_s"] == record["prediction_anchor_event_s"]
    assert record["input_window_start_s"] <= record["input_window_end_s"]
    assert record["input_telemetry_ids"]
    assert record["input_telemetry_ids_sha256"]
    tampered = json.loads(json.dumps(record))
    tampered["input_telemetry_ids"] = ["FORGED-IDENTITY"]
    with pytest.raises(W17TraceError):
        validate_trace_record(tampered)
    tampered = json.loads(json.dumps(record))
    tampered["anchor_simulated_receipt_s"] = (
        tampered["anchor_simulated_receipt_s"] + 0.5
    )
    with pytest.raises(W17TraceError):
        validate_trace_record(tampered)
    tampered = json.loads(json.dumps(record))
    tampered["input_window_end_s"] = tampered["input_window_end_s"] + 1.0
    with pytest.raises(W17TraceError):
        validate_trace_record(tampered)


def test_warning_status_must_follow_the_header_rule(fixture, registry, model):
    decision = _decision(fixture, registry, model, anchor=100.0)
    rule = derive_illustrative_warning_rule(model.manifest)[0]
    trace = ShadowTrace(
        header={
            "warning_rule": {
                "threshold": rule.threshold,
                "status": rule.status,
                "source": rule.source,
                "persistence": rule.persistence,
            }
        }
    )
    record = build_trace_record(
        decision=decision, model=model, rule=rule, risk_score=0.9, seq=100
    )
    trace.add(record)
    tampered = json.loads(json.dumps(record))
    tampered["hypothetical_warning"]["status"] = (
        "NOT_TRIGGERED_SYNTHETIC_ILLUSTRATIVE"
    )
    with pytest.raises(W17TraceError):
        trace.add(tampered)


# ---------------------------------------------------------------------------
# D26: no command-capable dependency in the replay path
# ---------------------------------------------------------------------------


def _imports(path: Path) -> list[tuple[str | None, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module, node.level))
    return found


def test_w17_modules_have_no_command_or_network_imports():
    denied = {
        "paho",
        "mqtt",
        "aiohttp",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "ssl",
        "subprocess",
        "multiprocessing",
        "serial",
        "smbus",
        "smbus2",
        "pymodbus",
        "RPi",
        "gpiozero",
        "asyncua",
        "coldguard_backend",
        "coldguard_control",
    }
    for path in (MODULE_PATH, SCRIPT_PATH):
        for module, level in _imports(path):
            if level:
                continue
            root = (module or "").split(".")[0]
            assert root not in denied, f"{path.name} imports {module}"


def test_w17_module_defines_no_command_entry_point():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    banned = {
        "publish",
        "publish_command",
        "send_command",
        "actuate",
        "dispatch",
        "set_actuator",
        "connect",
    }
    defined = {
        node.name.lower()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined & banned == set()
    for path in (MODULE_PATH, SCRIPT_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr.lower() in banned
            ):
                raise AssertionError(
                    f"{path.name} calls a command-style method "
                    f"{node.func.attr!r}"
                )


def test_w17_module_imports_only_the_guarded_w15_interface():
    for path, allowed in (
        (MODULE_PATH, {"GuardedModel"}),
        (SCRIPT_PATH, {"GuardedModel", "load_guarded_artifact"}),
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "w15_artifact":
                assert {alias.name for alias in node.names} <= allowed, path.name


def test_replay_execution_makes_no_network_or_subprocess_call(
    fixture, registry, model, monkeypatch
):
    def _boom(*args, **kwargs):
        raise AssertionError("the W17 replay attempted an external capability")

    monkeypatch.setattr(socket.socket, "connect", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    trajectory = fixture.development_trajectories[0]
    result = run_shadow_parity(
        [trajectory],
        registry,
        model=model,
        anchors_by_run={trajectory.run_id: (0.0, 40.0)},
    )
    assert result.compared_anchor_count == 2
    assert result.feature_parity_verified
