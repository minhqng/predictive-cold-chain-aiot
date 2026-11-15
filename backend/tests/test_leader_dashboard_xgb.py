"""Dashboard XGBoost endpoint contract tests (blocked/stale pass-through).

These use the real `xgb_view` API payload function with the inference call
monkeypatched: no fake score is asserted as a green result.
"""

import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE / "backend"))

from integration import leader_dashboard_server as server  # noqa: E402


def test_blocked_missing_features_are_surfaced(monkeypatch):
    blocked = {
        "mode": "DEMO_ONLY_SHADOW", "score_status": "BLOCKED_FEATURES_INCOMPLETE",
        "score": None, "missing_features": ["time_since_open"],
        "feature_count": 27, "feature_total": 28,
    }
    monkeypatch.setattr(server, "live_prediction", lambda *a, **k: blocked)
    assert server.xgb_view() == blocked


def test_stale_state_is_surfaced(monkeypatch):
    stale = {
        "mode": "DEMO_ONLY_SHADOW", "score_status": "STALE_NO_SCORE",
        "score": None, "fresh": False, "frame_age_s": 42.0,
        "missing_features": [], "feature_count": 28, "feature_total": 28,
    }
    monkeypatch.setattr(server, "live_prediction", lambda *a, **k: stale)
    out = server.xgb_view()
    assert out["score_status"] == "STALE_NO_SCORE"
    assert out["score"] is None


def test_database_blocked_is_surfaced(monkeypatch):
    blocked = {
        "mode": "DEMO_ONLY_SHADOW", "score_status": "BLOCKED_DATABASE_UNAVAILABLE",
        "score": None, "source": "REAL_SERIAL",
    }
    monkeypatch.setattr(server, "live_prediction", lambda *a, **k: blocked)
    out = server.xgb_view()
    assert out["score_status"] == "BLOCKED_DATABASE_UNAVAILABLE"
    assert out["score"] is None


def test_inference_exception_becomes_blocked_not_green(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("database gone")
    monkeypatch.setattr(server, "live_prediction", boom)
    out = server.xgb_view()
    assert out["score_status"] == "BLOCKED_ENDPOINT_ERROR"
    assert out["score"] is None


def test_inference_unavailable_becomes_model_blocked(monkeypatch):
    class InferenceUnavailable(RuntimeError):
        pass

    def boom(*_args, **_kwargs):
        raise InferenceUnavailable("artifact missing")
    monkeypatch.setattr(server, "live_prediction", boom)
    out = server.xgb_view()
    assert out["score_status"] == "BLOCKED_MODEL_UNAVAILABLE"
    assert out["score"] is None


def _reset_cache(monkeypatch):
    monkeypatch.setattr(server, "_xgb_cache_payload", None)
    monkeypatch.setattr(server, "_xgb_cache_anchor", None)
    monkeypatch.setattr(server, "_xgb_cache_computed_at", None)


def test_cached_view_serves_without_recompute(monkeypatch):
    calls = {"n": 0}
    payload = {
        "mode": "DEMO_ONLY_SHADOW", "demo_only": True,
        "score_status": "OK_EXPERIMENTAL_DEMO",
        "forecast_status": "OK_EXPERIMENTAL_DEMO",
        "predicted_temperature_c": 23.0, "score": None,
        "anchor_utc": server._now().isoformat(), "frame_age_s": 0.5, "fresh": True,
    }

    def fake(*_a, **_k):
        calls["n"] += 1
        return payload

    monkeypatch.setattr(server, "live_prediction", fake)
    _reset_cache(monkeypatch)
    server._refresh_xgb_cache()
    assert calls["n"] == 1
    for _ in range(5):
        out = server.xgb_view_cached()
        assert out["forecast_status"] == "OK_EXPERIMENTAL_DEMO"
        assert out["predicted_temperature_c"] == 23.0
    # The hot GET path must not re-run the multi-second inference.
    assert calls["n"] == 1


def test_cached_view_reages_and_fails_closed(monkeypatch):
    anchor_time = server._now()
    payload = {
        "score_status": "OK_EXPERIMENTAL_DEMO",
        "forecast_status": "OK_EXPERIMENTAL_DEMO",
        "predicted_temperature_c": 23.0,
        "anchor_utc": anchor_time.isoformat(), "frame_age_s": 0.0, "fresh": True,
    }
    clock = {"t": anchor_time}
    monkeypatch.setattr(server, "_now", lambda: clock["t"])
    monkeypatch.setattr(server, "live_prediction", lambda *a, **k: payload)
    _reset_cache(monkeypatch)
    server._refresh_xgb_cache()

    fresh = server.xgb_view_cached()
    assert fresh["forecast_status"] == "OK_EXPERIMENTAL_DEMO"
    assert fresh["frame_age_s"] <= 1.0

    # A stalled refresh must age the forecast out, not keep it falsely fresh.
    clock["t"] = anchor_time + server.timedelta(seconds=20)
    stale = server.xgb_view_cached()
    assert stale["frame_age_s"] >= 20.0
    assert stale["forecast_status"] == "STALE_NO_FORECAST"
    assert stale["fresh"] is False


def test_cached_view_warming_is_blocked(monkeypatch):
    _reset_cache(monkeypatch)
    out = server.xgb_view_cached()
    assert out["score_status"] == "BLOCKED_FORECAST_WARMING"
    assert out["predicted_temperature_c"] is None
