"""Leader-owned live control runtime: fail-closed prediction freshness preflight.

Composes the delivered Member C dispatch machinery with a Leader preflight
that enforces Member D's prediction-freshness limit on the live path, using
the PC/gateway system UTC clock as the single trusted timebase (the ESP32
carries no wall clock; device uptime/seq semantics stay Member-owned).

Provenance of the limits (delivered compositions, not Leader inventions):
- prediction_max_age_s = 600.0  (backend/src/coldguard_backend/command_path_runner.py:451)
- command_max_future_skew_s = 300.0 (backend/src/coldguard_backend/command_path_runner.py:452)

The preflight mirrors Member D's `_prediction_healthy`
(control/src/coldguard_control/policy.py:304-311) semantics on the live
entrypoint and refuses BEFORE any member persistence or broker I/O:
a stale prediction can never mint, persist or dispatch a command.

Non-predictive scoped commands (controller_id != PREDICTIVE and no
prediction_id — e.g. manual SAFE/OFF) skip the prediction preflight because
no prediction contract applies to them; every other member fence (token,
device scope, expiry, appraisal) still runs inside the delivered code.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from coldguard_backend.prediction_store import current_prediction  # noqa: E402


PREDICTION_MAX_AGE_S = 600.0
COMMAND_MAX_FUTURE_SKEW_S = 300.0

DispatchFn = Callable[..., dict]


@dataclass(frozen=True)
class FreshnessVerdict:
    ok: bool
    reason_code: str
    detail: dict

    def as_result(self) -> dict:
        return {"outcome": "PREDICTION_FRESHNESS_REFUSED", "verdict": self.reason_code, "detail": self.detail}


class LeaderControlRuntime:
    """Live command entrypoint used by the demo pipeline."""

    def __init__(
        self, engine, member_dispatch: DispatchFn, *,
        prediction_max_age_s: float = PREDICTION_MAX_AGE_S,
        future_skew_s: float = COMMAND_MAX_FUTURE_SKEW_S,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._engine = engine
        self._member_dispatch = member_dispatch
        self._max_age_s = float(prediction_max_age_s)
        self._future_skew_s = float(future_skew_s)
        self._now = now_fn or (lambda: datetime.now(timezone.utc))

    @property
    def max_age_s(self) -> float:
        return self._max_age_s

    def preflight_prediction(
        self, *, device_id: str, prediction_id: str | None, now: datetime | None = None,
    ) -> FreshnessVerdict:
        now = now or self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        with self._engine.connect() as connection:
            projection = current_prediction(connection, device_id, None)
        prediction = projection.get("prediction")
        if not isinstance(prediction, dict):
            return FreshnessVerdict(False, "PREDICTION_MISSING", {"device_id": device_id})
        if projection.get("status") != "FRESH":  # member current_prediction: top-level "status"
            return FreshnessVerdict(False, "PREDICTION_STALE", {
                "device_id": device_id,
                "member_status": projection.get("status"),
                "fresh_until": str(prediction.get("fresh_until")),
            })
        try:
            created = datetime.fromisoformat(str(prediction["created_at"]))
        except (KeyError, TypeError, ValueError):
            return FreshnessVerdict(False, "PREDICTION_TIMESTAMP_INVALID", {"device_id": device_id})
        if created.tzinfo is None:
            return FreshnessVerdict(False, "PREDICTION_TIMESTAMP_INVALID", {"device_id": device_id})
        age_s = (now - created).total_seconds()
        if age_s < -self._future_skew_s:
            return FreshnessVerdict(False, "PREDICTION_FUTURE_DATED", {
                "created_at": created.isoformat(), "now": now.isoformat(), "age_s": age_s,
            })
        if age_s > self._max_age_s:
            return FreshnessVerdict(False, "PREDICTION_AGE_EXCEEDS_LIMIT", {
                "age_s": age_s, "max_age_s": self._max_age_s, "clock": "backend_utc",
            })
        if prediction_id and str(prediction.get("prediction_id")) != str(prediction_id):
            return FreshnessVerdict(False, "PREDICTION_ID_MISMATCH", {
                "command_prediction_id": prediction_id,
                "current_prediction_id": str(prediction.get("prediction_id")),
            })
        return FreshnessVerdict(True, "PREDICTION_FRESH", {
            "age_s": age_s,
            "max_age_s": self._max_age_s,
            "fresh_until": str(prediction.get("fresh_until")),
            "model_version": prediction.get("model_version"),
            "model_sha256": prediction.get("model_sha256"),
            "clock": "backend_utc",
        })

    def dispatch(self, command: Any, *, backend_token: str | None, approval_signature: str | None = None,
                 now: datetime | None = None) -> dict:
        """Preflight (predictive only) then the delivered member dispatch."""
        is_predictive = getattr(command, "controller_id", "") == "PREDICTIVE" or getattr(command, "prediction_id", None)
        if is_predictive:
            verdict = self.preflight_prediction(
                device_id=command.device_id, prediction_id=command.prediction_id, now=now,
            )
            if not verdict.ok:
                return verdict.as_result()
        return self._member_dispatch(command, backend_token=backend_token, approval_signature=approval_signature)
