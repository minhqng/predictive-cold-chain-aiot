"""Load approved frozen XGBoost bytes and persist inference before returning evidence."""

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.engine import Engine

from coldguard_backend.experiment_store import Identifier
from coldguard_backend.prediction_store import Digest, PredictionDraft, current_prediction, record_prediction


class InferenceUnavailable(ValueError):
    """The artifact, runtime or input cannot produce approved evidence."""


class FrozenModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    model_version: Identifier
    feature_version: Identifier
    artifact_sha256: Digest
    feature_schema_sha256: Digest
    feature_names: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=1000)]
    horizon_s: Annotated[int, Field(gt=0, le=86400)]

    @model_validator(mode="after")
    def _unique_features(self):
        if len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature names must be unique")
        return self


ScoreFunction = Callable[[list[float]], float]
ModelLoader = Callable[[bytes, tuple[str, ...]], ScoreFunction]


def _load_xgboost(artifact: bytes, names: tuple[str, ...]) -> ScoreFunction:
    try:
        import xgboost as xgb
    except ImportError as exc:
        raise InferenceUnavailable("XGBoost runtime unavailable") from exc
    try:
        booster = xgb.Booster()
        booster.load_model(bytearray(artifact))
        if booster.num_features() != len(names) or (
            booster.feature_names is not None and tuple(booster.feature_names) != names
        ):
            raise InferenceUnavailable("model feature schema mismatch")
    except xgb.core.XGBoostError as exc:
        raise InferenceUnavailable("frozen XGBoost model could not be loaded") from exc

    def score(values: list[float]) -> float:
        output = booster.predict(xgb.DMatrix([values], feature_names=list(names)), validate_features=True)
        if output.shape != (1,):
            raise InferenceUnavailable("model did not return one risk score")
        return float(output[0])

    return score


def _verified_bytes(path: Path, expected_sha256: str) -> bytes:
    limit = 128 * 1024 * 1024
    try:
        with path.open("rb") as artifact:
            payload = artifact.read(limit + 1)
    except OSError as exc:
        raise InferenceUnavailable("frozen artifact unavailable") from exc
    if not payload or len(payload) > limit or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise InferenceUnavailable("frozen artifact checksum mismatch")
    return payload


@dataclass(frozen=True)
class FrozenModel:
    spec: FrozenModelSpec
    _score: ScoreFunction

    def score(self, features: Mapping[str, float]) -> float:
        if tuple(features) != self.spec.feature_names or any(
            type(value) not in (float, int) or not math.isfinite(value) for value in features.values()
        ):
            raise InferenceUnavailable("feature order or values are invalid")
        try:
            risk = self._score(list(features.values()))
        except InferenceUnavailable:
            raise
        except Exception as exc:
            raise InferenceUnavailable("frozen model inference failed") from exc
        if type(risk) not in (int, float) or not math.isfinite(risk) or not 0 <= risk <= 1:
            raise InferenceUnavailable("model risk score is invalid")
        return risk


def load_frozen_model(
    artifact_path: Path, feature_path: Path, *, manifest: FrozenModelSpec,
    approved: FrozenModelSpec, loader: ModelLoader = _load_xgboost,
) -> FrozenModel:
    if manifest != approved:
        raise InferenceUnavailable("model version or feature contract is not approved")
    _verified_bytes(feature_path, approved.feature_schema_sha256)
    model_bytes = _verified_bytes(artifact_path, approved.artifact_sha256)
    return FrozenModel(approved, loader(model_bytes, approved.feature_names))


def infer_and_record(
    engine: Engine, model: FrozenModel, *, prediction_id: str, device_id: str,
    run_id: str | None, features: Mapping[str, float], input_ids: list[int],
    input_window_start: datetime, input_window_end: datetime, created_at: datetime,
    max_input_age_sec: int,
) -> dict:
    risk = model.score(features)
    draft = PredictionDraft(
        prediction_id=prediction_id, device_id=device_id, run_id=run_id,
        model_version=model.spec.model_version, model_sha256=model.spec.artifact_sha256,
        feature_version=model.spec.feature_version, feature_schema_sha256=model.spec.feature_schema_sha256,
        horizon_sec=model.spec.horizon_s, max_input_age_sec=max_input_age_sec,
        created_at=created_at, input_window_start=input_window_start,
        input_window_end=input_window_end, input_telemetry_ids=input_ids, risk_score=risk,
    )
    with engine.begin() as connection:
        saved = record_prediction(connection, draft)
        current = current_prediction(connection, device_id, None)
        is_current = current["status"] == "FRESH" and current["prediction"]["prediction_id"] == prediction_id
    return {
        "prediction_id": saved["prediction_id"],
        "status": "FRESH" if is_current else "HISTORICAL",
        "risk_score": saved["risk_score"] if is_current else None,
    }
