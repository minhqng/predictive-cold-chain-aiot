#!/usr/bin/env python3
"""ColdGuard W16 locked-test pre-registration readiness preflight (B-W16-01).

This driver evaluates immutable METADATA ONLY and emits a deterministic
pre-registration/readiness manifest.  It never opens locked-test observations,
never computes a predictive metric, never fits a model and never invokes any
evaluator.  There is no force/unlock/ignore-gates option by design.

Outputs (default ``reports/W16``):
  locked-test-manifest-W16.json

A refusal decision is a successful, expected result: the manifest records the
exact unmet requirements.  Exit code 2 is reserved for malformed inputs.

The committed manifest freezes the registration.  If the analysis code or any
registered identity changes before any holdout access, the operator must delete
the committed manifest, regenerate it, and review/commit the new pre-registration
explicitly.  After any holdout opening, re-registration must never be used to
hide the earlier opening.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:  # installed package
    from coldguard_ml.w16_readiness import (
        EVALUATION_STATUS,
        EVIDENCE_SCHEMA,
        HOLDOUT_ACCESS,
        W16ReadinessError,
        evaluate_w16_readiness,
    )
except ModuleNotFoundError:  # direct checkout invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from coldguard_ml.w16_readiness import (
        EVALUATION_STATUS,
        EVIDENCE_SCHEMA,
        HOLDOUT_ACCESS,
        W16ReadinessError,
        evaluate_w16_readiness,
    )

import yaml

MANIFEST_NAME = "locked-test-manifest-W16.json"
REVISION_SEMANTICS = "GENERATION_BASE_NOT_DELIVERY_COMMIT"
OPENED_TRUE_FLAGS = frozenset({"locked_test_used", "test_partition_used"})
OPENED_FALSE_FLAGS = frozenset({"locked_test_untouched"})
ANALYSIS_CODE_FILES = (
    "w16_readiness.py",
    "grouped_evaluation.py",
    "event_evaluator.py",
    "evaluation_contract.py",
    "w14_calibration.py",
    "feature_pipeline.py",
    "feature_registry.py",
    "labels.py",
    "splitting.py",
)


class W16PreflightError(RuntimeError):
    pass


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha(payload: Any) -> str:
    # Matches xgb_benchmark._canonical_sha / feature_registry.schema_sha256
    # (json.dumps sort_keys, compact separators, ensure_ascii=True).
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise W16PreflightError(f"required metadata input is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise W16PreflightError(f"expected a JSON object: {path}")
    return payload


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise W16PreflightError(f"required metadata input is missing: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise W16PreflightError(f"expected a YAML object: {path}")
    return payload


def _git_revision(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNRECORDED"
    return completed.stdout.strip() or "UNRECORDED"


def _resolve(ml_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (ml_root / path).resolve()


def _analysis_code_sha256(ml_root: Path) -> str:
    package = ml_root / "src" / "coldguard_ml"
    paths = [Path(__file__).resolve()] + [
        package / name for name in ANALYSIS_CODE_FILES
    ]
    paths.extend(
        [ml_root / "feature-registry-v1.yaml", ml_root / "xgb-v1-config.yaml"]
    )
    hasher = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _completeness_status(run: Mapping[str, Any]) -> str:
    statuses = {
        str(row.get("status"))
        for row in run.get("completeness") or []
        if isinstance(row, Mapping)
    }
    if not statuses:
        return "MISSING"
    if statuses <= {"NOT_EVALUABLE", "NOT_APPLICABLE"}:
        return "NOT_EVALUABLE"
    if "FAIL" in statuses:
        return "NOT_TRUSTED"
    return "TRUSTED" if statuses == {"PASS"} else "NOT_EVALUABLE"


def _config_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    label = payload.get("label") or {}
    feature_policy = payload.get("feature_policy") or {}
    baseline = payload.get("baseline") or {}
    evaluation = payload.get("evaluation") or {}
    return {
        "config_version": payload.get("config_version"),
        "config_sha256": _canonical_sha(payload),
        "target_spec_version": label.get("spec_version"),
        "target_status": label.get("status"),
        "target_boundary_c": label.get("boundary_c"),
        "representative_temperature_status": label.get("representative_temperature"),
        "feature_allowlist": list(feature_policy.get("allowlist") or []),
        "episode_policy_status": (baseline.get("episode_policy") or {}).get("status"),
        "association_policy_status": (baseline.get("association_policy") or {}).get(
            "status"
        ),
        "allow_locked_test_access": evaluation.get("allow_locked_test_access"),
    }


def _registry_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    policy = payload.get("policy") or {}
    return {
        "feature_version": payload.get("feature_version"),
        "registry_status": payload.get("registry_status"),
        "schema_sha256": _canonical_sha(payload),
        "missingness_policy": policy.get("missing_data_policy"),
        "not_frozen_fields": list(payload.get("not_frozen_here") or []),
    }


def _lock_timestamps(
    documents: Sequence[Mapping[str, Any]],
) -> tuple[Any, Any]:
    for document in documents:
        containers = (
            document.get("locked_test"),
            (document.get("split") or {}).get("locked_test"),
            (document.get("population") or {}).get("locked_test"),
        )
        for container in containers:
            if isinstance(container, Mapping):
                frozen_at = container.get("frozen_at")
                opened_at = container.get("opened_at")
                if frozen_at is not None or opened_at is not None:
                    return frozen_at, opened_at
    return None, None


def _scan_holdout_flags(
    documents: Mapping[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Recursively scan every tracked manifest for holdout-opening signals."""
    opened: list[str] = []
    observations = 0

    def walk(node: Any, path: str) -> None:
        nonlocal observations
        if isinstance(node, Mapping):
            for key, value in node.items():
                key_text = str(key)
                here = f"{path}.{key_text}" if path else key_text
                if key_text in OPENED_TRUE_FLAGS:
                    observations += 1
                    if value is True or str(value).strip().lower() == "true":
                        opened.append(here)
                elif key_text in OPENED_FALSE_FLAGS:
                    observations += 1
                    if value is False or str(value).strip().lower() == "false":
                        opened.append(here)
                elif key_text == "opened_at":
                    observations += 1
                    if value is not None:
                        opened.append(here)
                elif key_text == "LOCKED_TEST":
                    observations += 1
                    if str(value) != "UNTOUCHED":
                        opened.append(here)
                walk(value, here)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")

    for name in sorted(documents):
        walk(documents[name], name)
    evidence = {
        "scanned_documents": sorted(documents),
        "flag_observations": observations,
        "opened_flags": sorted(set(opened)),
    }
    return sorted(set(opened)), evidence


def _membership_by_layer(
    w11_split: Mapping[str, Any],
    fold_manifest: Mapping[str, Any],
    w13_manifest: Mapping[str, Any],
    w14_manifest: Mapping[str, Any],
    w15_manifest: Mapping[str, Any],
) -> dict[str, list[str]]:
    layers: dict[str, list[str]] = {
        "W11_split": list(w11_split.get("test_runs") or []),
        "W11_fold_manifest": list(fold_manifest.get("test_runs") or []),
        "W14_population": list(
            (w14_manifest.get("population") or {}).get("locked_test_runs") or []
        ),
        "W15_population": list(
            (w15_manifest.get("population") or {}).get("locked_test_runs") or []
        ),
    }
    split_identity = (w13_manifest.get("study") or {}).get("split_identity") or {}
    if split_identity.get("test_runs") is not None:
        layers["W13_split_identity"] = list(split_identity.get("test_runs") or [])
    return layers


def _derive_registration(
    w11_split: Mapping[str, Any],
    dataset_id: Any,
    model_manifest: Mapping[str, Any],
    analysis_code_sha256: str,
) -> dict[str, Any]:
    pair_lineage = list(w11_split.get("pair_lineage") or [])
    test_pairs = sorted(
        str(entry.get("pair_id"))
        for entry in pair_lineage
        if isinstance(entry, Mapping) and entry.get("partition") == "test"
    )
    return {
        "test_runs": sorted(str(run) for run in (w11_split.get("test_runs") or [])),
        "test_pairs": test_pairs,
        "dataset_id": dataset_id,
        "model_artifact_sha256": str(
            model_manifest.get("model_artifact_sha256") or ""
        ),
        "model_config_sha256": str(model_manifest.get("model_config_hash") or ""),
        "feature_schema_hash": str(model_manifest.get("feature_schema_hash") or ""),
        "ordered_feature_ids_sha256": str(
            model_manifest.get("ordered_feature_ids_sha256") or ""
        ),
        "analysis_code_sha256": analysis_code_sha256,
    }


def _prior_registration(manifest_path: Path) -> dict[str, Any] | None:
    if not manifest_path.is_file():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    registration = payload.get("registration")
    required = {
        "test_runs",
        "test_pairs",
        "model_artifact_sha256",
        "model_config_sha256",
        "feature_schema_hash",
        "ordered_feature_ids_sha256",
        "analysis_code_sha256",
    }
    if not isinstance(registration, dict) or not required <= set(registration):
        raise W16PreflightError(
            f"existing pre-registration manifest is incomplete or stale: {manifest_path}"
        )
    return registration


def _relative_path(ml_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(ml_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _input_record(ml_root: Path, path: Path) -> dict[str, Any]:
    return {"path": _relative_path(ml_root, path), "sha256": _sha256_file(path)}


def build_evidence(
    *,
    registry: Mapping[str, Any],
    config: Mapping[str, Any],
    model_manifest: Mapping[str, Any],
    w15_manifest: Mapping[str, Any],
    w14_manifest: Mapping[str, Any],
    w13_manifest: Mapping[str, Any],
    w12_manifest: Mapping[str, Any],
    w11_manifest: Mapping[str, Any],
    fold_manifest: Mapping[str, Any],
    w08_manifest: Mapping[str, Any],
    approvals: Mapping[str, Any],
    registration: Mapping[str, Any],
    threshold_record: Mapping[str, Any],
    inputs: Mapping[str, Any],
    source_paths: Mapping[str, str],
) -> dict[str, Any]:
    w11_split = w11_manifest.get("split") or {}
    w08_run = (w08_manifest.get("runs") or [{}])[0]
    if not isinstance(w08_run, Mapping):
        raise W16PreflightError("W08 run record is malformed")
    w14_calibration = (w14_manifest.get("calibration") or {}).get("decision") or {}
    w13_decision = w13_manifest.get("decision") or {}
    model_files = model_manifest.get("files") or {}
    artifacts = []
    for role, key in (("model_native", "ubj"), ("model_secondary", "json")):
        entry = model_files.get(key) or {}
        if entry.get("file"):
            artifacts.append(
                {
                    "role": role,
                    "path": f"reports/W15/model/{entry['file']}",
                    "declared_sha256": entry.get("sha256"),
                }
            )

    documents = {
        "W08": w08_manifest,
        "W11": w11_manifest,
        "W11_fold": fold_manifest,
        "W12": w12_manifest,
        "W13": w13_manifest,
        "W14": w14_manifest,
        "W15": w15_manifest,
        "W15_model": model_manifest,
    }
    opened_flags, scan_evidence = _scan_holdout_flags(documents)
    holdout_opened = bool(opened_flags)
    frozen_at, opened_at = _lock_timestamps(
        (w15_manifest, w14_manifest, w13_manifest, w11_manifest)
    )
    test_used_flags = [
        w11_split.get("test_partition_used"),
        (w14_manifest.get("population") or {}).get("test_partition_used"),
        (w15_manifest.get("population") or {}).get("test_partition_used"),
    ]
    if any(flag is True for flag in test_used_flags):
        test_partition_used: bool | None = True
    elif all(flag is False for flag in test_used_flags):
        test_partition_used = False
    else:
        test_partition_used = None

    return {
        "schema": EVIDENCE_SCHEMA,
        "header": {
            "holdout_access": HOLDOUT_ACCESS,
            "holdout_opened": holdout_opened,
            "evaluation_status": EVALUATION_STATUS,
            "prior_access_status": (
                "RECORDED_OPENING" if holdout_opened else "NO_RECORDED_OPENING"
            ),
            "prior_opening_records": opened_flags,
            "prior_access_evidence": scan_evidence,
        },
        "dataset": {
            "physical_dataset_id": None,
            "provenance": w11_manifest.get("provenance"),
            "evidence_class": w11_manifest.get("provenance"),
            "source_sha256": [],
            "hardware_config_id": w08_run.get("hardware_config_id"),
            "hardware_config_status": w08_run.get("hardware_config_status"),
            "run_identity_status": w08_run.get("run_id_status"),
            "calibration_status": w08_run.get("calibration_status"),
            "time_domain": w08_run.get("time_domain"),
            "clock_sync": w08_run.get("clock_sync_status"),
            "sample_quality_status": _completeness_status(w08_run),
            "physical_run_validity": (
                "VALID" if w08_run.get("eligibility") == "ELIGIBLE" else "NOT_VALIDATED"
            ),
            "run_source_hashes": {},
        },
        "split": {
            "dataset_id": w11_split.get("dataset_id")
            or w11_manifest.get("dataset_id"),
            "provenance": w11_manifest.get("provenance"),
            "test_partition_used": w11_split.get("test_partition_used"),
            "test_runs": list(w11_split.get("test_runs") or []),
            "train_runs": list(w11_split.get("train_runs") or []),
            "validation_runs": list(w11_split.get("validation_runs") or []),
            "pair_lineage": list(w11_split.get("pair_lineage") or []),
            "fold_test_runs": list(fold_manifest.get("test_runs") or []),
            "grouping_key": fold_manifest.get("grouping_key"),
            "locked_test_frozen_at": frozen_at,
            "locked_test_opened_at": opened_at,
            "observed_locked_test_runs": list(
                (w15_manifest.get("population") or {}).get("locked_test_runs") or []
            ),
            "membership_by_layer": _membership_by_layer(
                w11_split, fold_manifest, w13_manifest, w14_manifest, w15_manifest
            ),
        },
        "registration": {
            "test_runs": sorted(str(run) for run in registration.get("test_runs") or []),
            "test_pairs": sorted(str(pair) for pair in registration.get("test_pairs") or []),
            "model_artifact_sha256": registration.get("model_artifact_sha256"),
            "model_config_sha256": registration.get("model_config_sha256"),
            "feature_schema_hash": registration.get("feature_schema_hash"),
            "ordered_feature_ids_sha256": registration.get("ordered_feature_ids_sha256"),
            "analysis_code_sha256": registration.get("analysis_code_sha256"),
        },
        "model": {
            "artifact_id": model_manifest.get("artifact_id"),
            "model_artifact_sha256": model_manifest.get("model_artifact_sha256"),
            "files": model_files,
            "model_config_version": model_manifest.get("model_config_version"),
            "model_config_hash": model_manifest.get("model_config_hash"),
            "feature_version": model_manifest.get("feature_version"),
            "feature_schema_hash": model_manifest.get("feature_schema_hash"),
            "ordered_feature_ids": list(
                model_manifest.get("ordered_feature_ids") or []
            ),
            "ordered_feature_ids_sha256": model_manifest.get(
                "ordered_feature_ids_sha256"
            ),
            "data_evidence_class": model_manifest.get("data_evidence_class"),
            "release_eligibility": model_manifest.get("release_eligibility"),
            "target_spec_version": model_manifest.get("target_spec_version"),
            "target_status": model_manifest.get("target_status"),
            "horizon_s": model_manifest.get("horizon_s"),
            "horizon_status": model_manifest.get("horizon_status"),
            "operating_threshold": model_manifest.get("operating_threshold"),
            "operating_threshold_status": model_manifest.get(
                "operating_threshold_status"
            ),
            # The source must come from a committed threshold-freeze record; it
            # is never inferred from the status string.
            "operating_threshold_record": dict(threshold_record),
            "warning_persistence_status": model_manifest.get(
                "warning_persistence_status"
            ),
            "warning_persistence_k": model_manifest.get("warning_persistence_k"),
            "calibration_status": model_manifest.get("calibration_status"),
            "score_semantics": model_manifest.get("score_semantics"),
            "training_dataset_id": model_manifest.get("training_dataset_id"),
        },
        "config": _config_evidence(config),
        "registry": _registry_evidence(registry),
        "gates": {
            "gate_b_observed_status": (
                w08_manifest.get("physical_gate") or {}
            ).get("observed_status"),
            "gate_b_reason_codes": list(
                (w08_manifest.get("physical_gate") or {}).get("reason_codes") or []
            ),
            "gate_g3_decision": (
                w12_manifest.get("scientific_verdicts") or {}
            ).get("GATE_G3"),
            "predictive_eligible_runs": (w13_manifest.get("reconciliation") or {}).get(
                "predictive_eligible_runs"
            ),
            "test_partition_used": test_partition_used,
        },
        "horizon_decision": {
            "freeze_status": w13_decision.get("freeze_status"),
            "primary_horizon_s": w13_decision.get("primary_horizon_s"),
        },
        "calibration": {
            "decision": w14_calibration.get("decision"),
            "probabilistic_claim": False,
            "fit_population": None,
            "locked_test_used": None,
        },
        "approvals": dict(approvals),
        "artifacts": artifacts,
        "source_paths": dict(source_paths),
        "inputs": dict(inputs),
        "evaluation_receipt": None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ColdGuard W16 locked-test pre-registration readiness preflight. "
            "Metadata-only and fail-closed; it never opens locked-test "
            "observations and never runs an evaluation."
        )
    )
    parser.add_argument("--config", default="xgb-v1-config.yaml")
    parser.add_argument(
        "--feature-registry", default="feature-registry-v1.yaml"
    )
    parser.add_argument(
        "--model-manifest", default="reports/W15/model/model-manifest-W15.json"
    )
    parser.add_argument("--w15-manifest", default="reports/W15/w15-manifest.json")
    parser.add_argument("--w14-manifest", default="reports/W14/w14-manifest.json")
    parser.add_argument("--w13-manifest", default="reports/W13/horizon-manifest-W13.json")
    parser.add_argument("--w12-manifest", default="reports/W12/w12-manifest.json")
    parser.add_argument(
        "--w11-manifest", default="reports/W11/benchmark-manifest-W11.json"
    )
    parser.add_argument(
        "--w11-fold-manifest", default="reports/W11/cv-fold-manifest.yaml"
    )
    parser.add_argument("--w08-manifest", default="reports/W08/gate-b-manifest-W08.json")
    parser.add_argument(
        "--approval-ledger", default="reports/W16/approval-ledger-W16.json"
    )
    parser.add_argument(
        "--threshold-freeze-record", default="reports/W16/threshold-freeze-W16.json"
    )
    parser.add_argument(
        "--prior-manifest", default="reports/W16/locked-test-manifest-W16.json"
    )
    parser.add_argument("--out", default="reports/W16")
    parser.add_argument("--repository-revision", default=None)
    args = parser.parse_args(argv)

    ml_root = Path(__file__).resolve().parents[1]
    revision = args.repository_revision or _git_revision(ml_root)

    config_path = _resolve(ml_root, args.config)
    registry_path = _resolve(ml_root, args.feature_registry)
    model_manifest_path = _resolve(ml_root, args.model_manifest)
    w15_path = _resolve(ml_root, args.w15_manifest)
    w14_path = _resolve(ml_root, args.w14_manifest)
    w13_path = _resolve(ml_root, args.w13_manifest)
    w12_path = _resolve(ml_root, args.w12_manifest)
    w11_path = _resolve(ml_root, args.w11_manifest)
    fold_path = _resolve(ml_root, args.w11_fold_manifest)
    w08_path = _resolve(ml_root, args.w08_manifest)
    approval_path = _resolve(ml_root, args.approval_ledger)
    threshold_record_path = _resolve(ml_root, args.threshold_freeze_record)
    prior_path = _resolve(ml_root, args.prior_manifest)
    out_dir = _resolve(ml_root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / MANIFEST_NAME

    config_payload = _load_yaml(config_path)
    registry_payload = _load_yaml(registry_path)

    model_manifest = _load_json(model_manifest_path)
    w15_manifest = _load_json(w15_path)
    w14_manifest = _load_json(w14_path)
    w13_manifest = _load_json(w13_path)
    w12_manifest = _load_json(w12_path)
    w11_manifest = _load_json(w11_path)
    fold_manifest = _load_yaml(fold_path)
    w08_manifest = _load_json(w08_path)
    approvals = _load_json(approval_path) if approval_path.is_file() else {"approvals": []}
    threshold_record = (
        _load_json(threshold_record_path) if threshold_record_path.is_file() else {}
    )

    input_paths = [
        config_path,
        registry_path,
        model_manifest_path,
        w15_path,
        w14_path,
        w13_path,
        w12_path,
        w11_path,
        fold_path,
        w08_path,
    ]
    if approval_path.is_file():
        input_paths.append(approval_path)
    if threshold_record_path.is_file():
        input_paths.append(threshold_record_path)
    inputs = {
        record["path"]: {"sha256": record["sha256"]}
        for record in sorted(
            (_input_record(ml_root, path) for path in input_paths),
            key=lambda item: item["path"],
        )
    }

    analysis_code = _analysis_code_sha256(ml_root)
    prior = _prior_registration(prior_path)
    w11_split = w11_manifest.get("split") or {}
    dataset_id = w11_split.get("dataset_id") or w11_manifest.get("dataset_id")
    if prior is None:
        registration = _derive_registration(
            w11_split, dataset_id, model_manifest, analysis_code
        )
    else:
        registration = dict(prior)

    source_paths = {
        "model_manifest": _relative_path(ml_root, model_manifest_path),
        "model_config": _relative_path(ml_root, config_path),
        "feature_registry": _relative_path(ml_root, registry_path),
        "horizon_manifest": _relative_path(ml_root, w13_path),
        "w15_manifest": _relative_path(ml_root, w15_path),
        "w14_manifest": _relative_path(ml_root, w14_path),
        "w12_manifest": _relative_path(ml_root, w12_path),
        "w11_manifest": _relative_path(ml_root, w11_path),
        "w11_fold_manifest": _relative_path(ml_root, fold_path),
        "w08_manifest": _relative_path(ml_root, w08_path),
    }

    evidence = build_evidence(
        registry=registry_payload,
        config=config_payload,
        model_manifest=model_manifest,
        w15_manifest=w15_manifest,
        w14_manifest=w14_manifest,
        w13_manifest=w13_manifest,
        w12_manifest=w12_manifest,
        w11_manifest=w11_manifest,
        fold_manifest=fold_manifest,
        w08_manifest=w08_manifest,
        approvals=approvals,
        registration=registration,
        threshold_record=threshold_record,
        inputs=inputs,
        source_paths=source_paths,
    )
    evidence["current_analysis_code_sha256"] = analysis_code

    report = evaluate_w16_readiness(evidence, artifact_root=ml_root)

    manifest = dict(report.manifest)
    manifest["analysis_code_sha256"] = analysis_code
    manifest["repository_revision"] = revision
    manifest["revision_semantics"] = REVISION_SEMANTICS
    manifest["inputs_scope"] = "METADATA_ONLY"
    manifest["inputs"] = inputs
    manifest_path.write_bytes(_json(manifest).encode("utf-8"))

    failed = [row for row in report.requirements if row.reason_code]
    print(
        "W16 preflight complete: "
        f"decision={report.decision}; "
        f"requirements={len(report.requirements)}; "
        f"refused={len(failed)}; "
        f"holdout_opened={manifest['holdout_opened']}; "
        f"evaluation_status={manifest['evaluation_status']}; "
        f"manifest={manifest_path}"
    )
    if report.refusal_reasons:
        print(
            "W16 refusal reasons: " + ", ".join(report.refusal_reasons),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (W16PreflightError, W16ReadinessError) as exc:
        print(f"W16 PREFLIGHT REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:  # fail closed on malformed metadata
        print(
            f"W16 PREFLIGHT REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr
        )
        raise SystemExit(2)
