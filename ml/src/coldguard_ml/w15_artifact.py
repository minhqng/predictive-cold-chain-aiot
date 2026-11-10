"""W15 stable native XGBoost artifact with fail-closed feature-schema binding.

B-W15-04 requires a stable native model (``model.ubj`` / ``model.json``), an
exact ordered-feature contract, SHA-256 provenance, fresh-process reload parity
and explicit evidence classification.  A hash proves byte identity only; it
never proves scientific validity.

The artifact produced by this module is permanently classified as
``SYNTHETIC_SOFTWARE_CONTROL_ONLY`` / ``NON_DEPLOYABLE_CANDIDATE``.  It is not a
physical release model and it is not a W16 locked-test candidate.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import xgboost
from xgboost import XGBClassifier

from .feature_registry import FeatureRegistry
from .xgb_benchmark import BenchmarkConfig, LabeledSample, feature_matrix

W15_ARTIFACT_SCHEMA = "coldguard-w15-model-artifact-v1"
ARTIFACT_ID = "coldguard-w15-synthetic-xgb-candidate-v1"
SYNTHETIC_EVIDENCE_CLASS = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
NON_DEPLOYABLE = "NON_DEPLOYABLE_CANDIDATE"
RISK_SCORE_ONLY = "RISK_SCORE_ONLY"
ENGINEERING_REFERENCE_HORIZON = "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN"
ILLUSTRATIVE_THRESHOLD = "ILLUSTRATIVE_NOT_FROZEN"
PERSISTENCE_NOT_FROZEN = "NOT_FROZEN"
PROBE_TOLERANCE = 1e-12
PRIMARY_FORMAT = "ubj"
MODEL_FILE = "model.ubj"
JSON_MODEL_FILE = "model.json"

REQUIRED_MANIFEST_FIELDS = (
    "model_artifact_sha256",
    "model_format",
    "model_library_version",
    "training_dataset_id",
    "data_evidence_class",
    "feature_schema_hash",
    "ordered_feature_ids",
    "target_spec_version",
    "horizon_status",
    "model_config_hash",
    "calibration_status",
    "operating_threshold_status",
    "warning_persistence_status",
    "training_code_revision",
    "validation_evidence",
    "release_eligibility",
    "score_semantics",
    "files",
)


class ArtifactError(ValueError):
    """The artifact or its manifest violates the declared contract."""


_CANONICAL_REQUIRED_METADATA_FIELDS = (
    "model_artifact_sha256",
    "model_format",
    "model_library_version",
    "training_dataset_id",
    "data_evidence_class",
    "feature_schema_hash",
    "ordered_feature_ids",
    "target_spec_version",
    "horizon_status",
    "model_config_hash",
    "calibration_status",
    "operating_threshold_status",
    "warning_persistence_status",
    "training_code_revision",
    "validation_evidence",
    "release_eligibility",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ordered_feature_ids_sha256(feature_ids: Sequence[str]) -> str:
    return _sha256_bytes(json.dumps(list(feature_ids)).encode("utf-8"))


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def native_model_bytes(model: XGBClassifier) -> bytes:
    with tempfile.TemporaryDirectory(prefix="coldguard-w15-bytes-") as tmp:
        path = Path(tmp) / MODEL_FILE
        model.save_model(str(path))
        return path.read_bytes()


def compute_model_inspection(
    model: XGBClassifier, feature_ids: Sequence[str]
) -> dict[str, Any]:
    """Native split usage per feature; diagnostic only, never causal importance."""
    booster = model.get_booster()
    frame = booster.trees_to_dataframe()
    if "Feature" not in frame.columns:
        raise ArtifactError("booster frame has no Feature column")
    splits = frame[
        frame["Feature"].notna() & (frame["Feature"] != "Leaf")
    ]
    names = booster.feature_names
    counts = splits["Feature"].value_counts().to_dict()
    gains = splits.groupby("Feature")["Gain"].sum().to_dict()
    rows = []
    for index, feature_id in enumerate(feature_ids):
        key = names[index] if names else f"f{index}"
        rows.append(
            {
                "feature_id": feature_id,
                "feature_index": index,
                "split_count": int(counts.get(key, 0)),
                "total_gain": float(gains.get(key, 0.0) or 0.0),
            }
        )
    used = [row for row in rows if row["split_count"] > 0]
    dominant = max(rows, key=lambda row: row["split_count"], default=None)
    dominant_thresholds: list[float] = []
    if dominant is not None and dominant["split_count"] > 0:
        key = names[dominant["feature_index"]] if names else (
            f"f{dominant['feature_index']}"
        )
        dominant_thresholds = sorted(
            {
                float(value)
                for value in splits.loc[splits["Feature"] == key, "Split"].tolist()
                if value is not None
            }
        )
    return {
        "tree_count": int(frame["Tree"].nunique()) if "Tree" in frame.columns else None,
        "total_split_count": int(len(splits)),
        "feature_count": len(feature_ids),
        "used_feature_count": len(used),
        "unused_feature_count": len(rows) - len(used),
        "used_feature_ids": [row["feature_id"] for row in used],
        "unused_feature_ids": [
            row["feature_id"] for row in rows if row["split_count"] == 0
        ],
        "dominant_feature": dominant,
        "dominant_feature_split_thresholds": dominant_thresholds,
        "features": rows,
        "diagnostic_only": True,
        "interpretation_note": (
            "split usage is a native model diagnostic, not causal feature importance "
            "and not evidence of physical predictive value"
        ),
    }


def fit_final_candidate(
    samples: Sequence[LabeledSample],
    config: BenchmarkConfig,
    feature_ids: Sequence[str],
) -> XGBClassifier:
    """Fit the declared UNWEIGHTED candidate on the development population only."""
    if not samples:
        raise ArtifactError("cannot fit a model on an empty development population")
    if {sample.partition for sample in samples} - {"train", "validation"}:
        raise ArtifactError("artifact fitting received a non-development sample")
    positive = sum(1 for sample in samples if sample.y == 1)
    negative = len(samples) - positive
    if positive == 0 or negative == 0:
        raise ArtifactError("both classes are required to fit the candidate")
    X, y = feature_matrix(samples, feature_ids)
    params = dict(config.model_params)
    params["scale_pos_weight"] = 1.0
    params["random_state"] = config.model_params["random_state"]
    params["n_jobs"] = 1
    params["verbosity"] = 0
    model = XGBClassifier(**params)
    model.fit(X, y)
    if int(model.get_booster().num_features()) != len(feature_ids):
        raise ArtifactError("fitted model feature width does not match the contract")
    return model


def save_native_models(
    model: XGBClassifier,
    directory: str | Path,
    *,
    probe_matrix: np.ndarray,
) -> dict[str, Any]:
    """Write both native formats, hash the bytes and verify reload parity."""
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    paths = {"ubj": base / MODEL_FILE, "json": base / JSON_MODEL_FILE}
    for path in paths.values():
        model.save_model(str(path))
    restored = XGBClassifier()
    restored.load_model(str(paths[PRIMARY_FORMAT]))
    original = np.asarray(model.predict_proba(probe_matrix)[:, 1], dtype=float)
    reloaded = np.asarray(restored.predict_proba(probe_matrix)[:, 1], dtype=float)
    max_abs_diff = float(np.max(np.abs(original - reloaded))) if original.size else 0.0
    if not np.allclose(original, reloaded, rtol=0.0, atol=PROBE_TOLERANCE):
        raise ArtifactError(
            f"reload predictions moved by {max_abs_diff} > {PROBE_TOLERANCE}"
        )
    return {
        "files": {
            name: {
                "file": path.name,
                "sha256": _sha256_bytes(path.read_bytes()),
                "bytes": path.stat().st_size,
            }
            for name, path in paths.items()
        },
        "reload_parity": True,
        "probe_tolerance_abs": PROBE_TOLERANCE,
        "probe_max_abs_diff": max_abs_diff,
        "probe_rows": int(probe_matrix.shape[0]),
    }


def verify_fresh_process_parity(
    *,
    model_path: str | Path,
    probe_matrix: np.ndarray,
    expected_scores: np.ndarray,
    tolerance: float = PROBE_TOLERANCE,
) -> dict[str, Any]:
    """Reload the artifact in a fresh interpreter and compare probe predictions."""
    code = (
        "import json, sys\n"
        "import numpy as np\n"
        "from xgboost import XGBClassifier\n"
        "payload = json.loads(open(sys.argv[1], encoding='utf-8').read())\n"
        "model = XGBClassifier()\n"
        "model.load_model(sys.argv[2])\n"
        "X = np.asarray(payload['rows'], dtype=float)\n"
        "scores = np.asarray(model.predict_proba(X)[:, 1], dtype=float)\n"
        "import xgboost\n"
        "json.dump({'scores': scores.tolist(), 'xgboost': xgboost.__version__, "
        "'features': int(model.get_booster().num_features())}, "
        "open(sys.argv[3], 'w', encoding='utf-8'))\n"
    )
    with tempfile.TemporaryDirectory(prefix="coldguard-w15-fresh-") as tmp:
        payload_path = Path(tmp) / "probe.json"
        out_path = Path(tmp) / "scores.json"
        payload_path.write_text(
            json.dumps({"rows": np.asarray(probe_matrix, dtype=float).tolist()}),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(payload_path),
                str(model_path),
                str(out_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise ArtifactError(
                "fresh-process reload failed: " + completed.stderr.strip()[-800:]
            )
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    scores = np.asarray(payload["scores"], dtype=float)
    expected = np.asarray(expected_scores, dtype=float)
    if scores.shape != expected.shape:
        raise ArtifactError("fresh-process prediction width changed")
    max_abs_diff = float(np.max(np.abs(scores - expected))) if expected.size else 0.0
    if max_abs_diff > tolerance:
        raise ArtifactError(
            f"fresh-process predictions moved by {max_abs_diff} > {tolerance}"
        )
    if int(payload["features"]) != int(probe_matrix.shape[1]):
        raise ArtifactError("fresh-process model feature width changed")
    return {
        "fresh_process_reload_parity": True,
        "max_abs_diff": max_abs_diff,
        "tolerance_abs": tolerance,
        "fresh_process_xgboost": payload["xgboost"],
        "model_features": int(payload["features"]),
    }


def build_model_manifest(
    *,
    files: Mapping[str, Any],
    registry: FeatureRegistry,
    config: BenchmarkConfig,
    ordered_feature_ids: Sequence[str],
    training_dataset_id: str,
    training_population: Mapping[str, Any],
    validation_evidence: Mapping[str, Any],
    training_code_revision: str,
    probe_parity: Mapping[str, Any],
    deterministic_in_process: bool,
    model_inspection: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = {
        "schema": W15_ARTIFACT_SCHEMA,
        "artifact_id": ARTIFACT_ID,
        "model_artifact_sha256": files["files"][PRIMARY_FORMAT]["sha256"],
        "model_format": PRIMARY_FORMAT,
        "model_secondary_format": "json",
        "model_library": "xgboost",
        "model_library_version": xgboost.__version__,
        "model_family": "XGBoost",
        "training_dataset_id": training_dataset_id,
        "data_evidence_class": SYNTHETIC_EVIDENCE_CLASS,
        "feature_schema_hash": registry.schema_sha256,
        "feature_version": "CG-FEAT-1.0",
        "ordered_feature_ids": list(ordered_feature_ids),
        "ordered_feature_ids_sha256": _ordered_feature_ids_sha256(
            ordered_feature_ids
        ),
        "target_spec_version": config.label.spec_version,
        "target_status": "DEVELOPMENT_CANDIDATE_NOT_FROZEN",
        "horizon_s": config.label.horizon_s,
        "horizon_status": ENGINEERING_REFERENCE_HORIZON,
        "model_config_hash": config.config_sha256,
        "model_config_version": config.config_version,
        "calibration_status": RISK_SCORE_ONLY,
        "model_config_calibration_status": config.calibration_status,
        "score_semantics": "risk_score",
        "operating_threshold": config.risk_threshold,
        "operating_threshold_status": ILLUSTRATIVE_THRESHOLD,
        "warning_persistence_status": PERSISTENCE_NOT_FROZEN,
        "training_code_revision": training_code_revision,
        "training_code_revision_semantics": "GENERATION_BASE_NOT_DELIVERY_COMMIT",
        "training_population": dict(training_population),
        "validation_evidence": dict(validation_evidence),
        "model_inspection": dict(model_inspection),
        "guarded_interface_required": True,
        "raw_native_load_prohibited": True,
        "canonical_required_metadata_fields": list(
            _CANONICAL_REQUIRED_METADATA_FIELDS
        ),
        "release_eligibility": NON_DEPLOYABLE,
        "intended_use": [
            "offline software-control experiments on the W11 synthetic fixture",
            "risk_score semantics only",
            "future shadow-inference candidate only after all release gates",
        ],
        "prohibited_use": [
            "physical Controller B actuation",
            "calibrated-probability or percentage-risk wording",
            "public reliability or early-warning superiority claims",
            "final A/B comparison",
            "deployment or registration in C's backend",
        ],
        "limitations": [
            "trained on a deterministic synthetic fixture; not physical evidence",
            "eight development groups only; 4 correlated grouped folds are not 4 physical experiments",
            "primary horizon and critical target are not frozen",
            "no real calibration population; output is a risk score only",
            "electrical block is run-invariant in the synthetic fixture",
            "operating threshold and warning persistence are not frozen",
        ],
        "probe_parity": dict(probe_parity),
        "model_bytes_deterministic_in_process": bool(deterministic_in_process),
        "files": {name: dict(payload) for name, payload in files["files"].items()},
    }
    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    if missing:
        raise ArtifactError(f"artifact manifest is missing required fields: {missing}")
    return manifest


def _validate_manifest_contract(manifest: Mapping[str, Any]) -> None:
    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    if missing:
        raise ArtifactError(f"artifact manifest is missing required fields: {missing}")
    if manifest["schema"] != W15_ARTIFACT_SCHEMA:
        raise ArtifactError("artifact manifest schema mismatch")
    if manifest["data_evidence_class"] != SYNTHETIC_EVIDENCE_CLASS:
        raise ArtifactError(
            "artifact evidence class is not SYNTHETIC_SOFTWARE_CONTROL_ONLY"
        )
    if manifest["release_eligibility"] != NON_DEPLOYABLE:
        raise ArtifactError("synthetic artifact must remain NON_DEPLOYABLE_CANDIDATE")
    if manifest["score_semantics"] != "risk_score":
        raise ArtifactError("artifact must declare risk_score, never probability")
    if manifest["horizon_status"] != ENGINEERING_REFERENCE_HORIZON:
        raise ArtifactError("artifact must not record an unfrozen horizon as final")
    if manifest["calibration_status"] != RISK_SCORE_ONLY:
        raise ArtifactError("artifact must remain RISK_SCORE_ONLY")
    if manifest["operating_threshold_status"] != ILLUSTRATIVE_THRESHOLD:
        raise ArtifactError("operating threshold is not frozen in W15")
    if manifest["warning_persistence_status"] != PERSISTENCE_NOT_FROZEN:
        raise ArtifactError("warning persistence is not frozen in W15")
    if not manifest["ordered_feature_ids"]:
        raise ArtifactError("ordered feature contract is empty")
    if len(set(manifest["ordered_feature_ids"])) != len(
        manifest["ordered_feature_ids"]
    ):
        raise ArtifactError("ordered feature contract contains duplicates")
    expected_order_sha = _ordered_feature_ids_sha256(
        manifest["ordered_feature_ids"]
    )
    if manifest.get("ordered_feature_ids_sha256") != expected_order_sha:
        raise ArtifactError("ordered feature contract hash mismatch")
    for field in (
        "model_artifact_sha256",
        "feature_schema_hash",
        "model_config_hash",
    ):
        if not _HEX64.fullmatch(str(manifest[field])):
            raise ArtifactError(f"provenance field {field!r} is not a SHA-256 hex digest")
    primary_file = manifest["files"].get(manifest["model_format"])
    if not primary_file or manifest["model_artifact_sha256"] != primary_file.get(
        "sha256"
    ):
        raise ArtifactError(
            "model_artifact_sha256 does not match the primary artifact file"
        )
    if not str(manifest["training_code_revision"]).strip():
        raise ArtifactError("training code revision is missing")
    if manifest.get("guarded_interface_required") is not True:
        raise ArtifactError("the guarded inference interface is not required")
    if manifest["model_library_version"] != xgboost.__version__:
        raise ArtifactError(
            "runtime library version mismatch: "
            f"{manifest['model_library_version']} != {xgboost.__version__}"
        )
    if not isinstance(manifest["validation_evidence"], Mapping) or not manifest[
        "validation_evidence"
    ]:
        raise ArtifactError("validation evidence is missing")
    if not manifest["training_dataset_id"]:
        raise ArtifactError("training dataset identity is missing")


@dataclass(frozen=True)
class GuardedModel:
    _model: XGBClassifier
    ordered_feature_ids: tuple[str, ...]
    manifest: Mapping[str, Any]

    @property
    def raw_model_for_diagnostics_only(self) -> XGBClassifier:
        """Raw booster access bypasses schema checks; not an approved inference path."""
        return self._model

    def predict_risk(
        self, columns: Mapping[str, Sequence[float]]
    ) -> np.ndarray:
        """Predict risk scores only when the exact ordered columns are supplied."""
        if tuple(columns.keys()) != self.ordered_feature_ids:
            raise ArtifactError(
                "feature contract mismatch: expected exactly "
                f"{list(self.ordered_feature_ids)} in that order, got "
                f"{list(columns.keys())}"
            )
        lengths = {len(values) for values in columns.values()}
        if len(lengths) > 1:
            raise ArtifactError("feature columns have inconsistent lengths")
        matrix = np.column_stack(
            [np.asarray(columns[feature_id], dtype=float) for feature_id in self.ordered_feature_ids]
        )
        return np.asarray(self._model.predict_proba(matrix)[:, 1], dtype=float)


def load_guarded_artifact(
    *,
    manifest_path: str | Path,
    model_path: str | Path,
    expected_feature_ids: Sequence[str],
    expected_library_version: str | None = None,
    expected_feature_schema_hash: str | None = None,
    expected_model_config_hash: str | None = None,
) -> GuardedModel:
    """Load the artifact only when every declared binding still holds."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping):
        raise ArtifactError("artifact manifest root is not an object")
    _validate_manifest_contract(manifest)
    if expected_library_version is not None:
        if manifest["model_library_version"] != expected_library_version:
            raise ArtifactError(
                f"library version mismatch: {manifest['model_library_version']} != "
                f"{expected_library_version}"
            )
    if expected_feature_schema_hash is not None:
        if manifest["feature_schema_hash"] != expected_feature_schema_hash:
            raise ArtifactError("feature schema hash mismatch")
    if expected_model_config_hash is not None:
        if manifest["model_config_hash"] != expected_model_config_hash:
            raise ArtifactError("model configuration hash mismatch")
    if tuple(manifest["ordered_feature_ids"]) != tuple(expected_feature_ids):
        raise ArtifactError("ordered feature contract mismatch")
    model_path = Path(model_path)
    if not model_path.exists():
        raise ArtifactError(f"model file is missing: {model_path}")
    expected_format = model_path.suffix.lstrip(".")
    file_entry = manifest["files"].get(expected_format)
    if not file_entry or file_entry.get("file") != model_path.name:
        raise ArtifactError("model file is not bound by the manifest")
    actual_sha = _sha256_bytes(model_path.read_bytes())
    if actual_sha != file_entry["sha256"]:
        raise ArtifactError("model byte hash does not match the manifest")
    try:
        model = XGBClassifier()
        model.load_model(str(model_path))
    except Exception as exc:  # xgboost raises its own error type
        raise ArtifactError(f"model bytes cannot be loaded: {exc}") from exc
    if int(model.get_booster().num_features()) != len(manifest["ordered_feature_ids"]):
        raise ArtifactError("model width does not match the ordered feature contract")
    return GuardedModel(
        _model=model,
        ordered_feature_ids=tuple(manifest["ordered_feature_ids"]),
        manifest=manifest,
    )
