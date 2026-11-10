"""Structured logs, bounded metrics and backend-clock command evidence."""

import json
import logging
from time import monotonic

import pytest
from fastapi.testclient import TestClient

from coldguard_backend import ingest
from coldguard_backend.command_publisher import CommandPublisher, PublishResult
from coldguard_backend.command_service import create_command_intent
from coldguard_backend.main import app, get_db_engine
from coldguard_backend.observability import BUCKETS_MS, RuntimeMetrics, record_event, runtime_metrics
from tests.command_testkit import cleanup_commands, make_ack, make_command
from tests.test_command_store import _record_ack


def test_bounded_histogram_counts_and_snapshot_are_consistent():
    metrics = RuntimeMetrics()
    for duration, reason in ((1, "accepted"), (1.1, "accepted"), (5001, "failed")):
        metrics.record("ingest", reason, duration)
    state = metrics.snapshot()
    assert state["scope"] == "process"
    assert state["counters"] == {"ingest.accepted": 2, "ingest.failed": 1}
    assert state["duration_histograms_ms"]["ingest"] == {
        "upper_bounds_ms": BUCKETS_MS,
        "bucket_counts": [1, 1, *([0] * 8), 1],
        "count": 3,
    }
    state["duration_histograms_ms"]["ingest"]["bucket_counts"][0] = 200
    assert metrics.snapshot()["duration_histograms_ms"]["ingest"]["bucket_counts"][0] == 1


def test_structured_log_retains_allowed_identifiers_and_omits_payload(caplog):
    logger = logging.getLogger("coldguard-test")
    with caplog.at_level(logging.INFO, logger=logger.name):
        record_event(
            logger, "fixture_event", "accepted", monotonic(), level=logging.INFO,
            device_id="d", run_id="r", boot_id="b", seq=3, command_id="c",
            prediction_id="p", event_id="e", payload="never-log-this", password="secret-fixture",
        )
    entry = json.loads(caplog.records[-1].getMessage())
    assert entry == {
        "event": "fixture_event", "reason": "accepted", "duration_ms": entry["duration_ms"],
        "device_id": "d", "run_id": "r", "boot_id": "b", "seq": 3,
        "command_id": "c", "prediction_id": "p", "event_id": "e",
    }
    assert "never-log-this" not in caplog.text
    assert "secret-fixture" not in caplog.text


def test_raw_persistence_failure_is_counted_without_printing_exception(monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise RuntimeError("secret-fixture-from-db-error")

    monkeypatch.setattr(ingest, "store_raw", fail)
    metric = "telemetry_ingest.raw_persistence_failed"
    count = runtime_metrics.snapshot()["counters"].get(metric, 0)
    with pytest.raises(RuntimeError, match="secret-fixture-from-db-error"):
        ingest.ingest_message(None, topic="coldguard/d/telemetry", payload=b"secret payload")
    assert runtime_metrics.snapshot()["counters"][metric] == count + 1
    assert "raw_persistence_failed" in caplog.text
    assert "secret-fixture-from-db-error" not in caplog.text
    assert "secret payload" not in caplog.text


def test_command_timing_preserves_early_ack_and_unknown_physical_times(db_engine):
    cleanup_commands(db_engine)
    app.dependency_overrides[get_db_engine] = lambda: db_engine
    client = TestClient(app)
    command_id = "timing-proof"
    retry_metric = "command_retry.puback"
    initial = runtime_metrics.snapshot()["counters"].get(retry_metric, 0)
    try:
        assert client.get(f"/api/commands/{command_id}/timing").status_code == 404
        create_command_intent(db_engine, make_command(
            command_id, run_id="timing-run", prediction_id="timing-prediction",
        ))
        path = f"/api/commands/{command_id}/timing"
        before = client.get(path).json()
        assert before["created_at"] is not None
        assert before["device_ack_received_at"] is None
        assert before["broker_puback_recorded_at"] is None
        first = CommandPublisher(db_engine, lambda *_: PublishResult("UNKNOWN"))
        assert first.publish(command_id)["outcome"] == "unknown"

        def second_send(*_):
            assert _record_ack(db_engine, make_ack(command_id))["outcome"] == "applied"
            return PublishResult("PUBACK")

        assert CommandPublisher(db_engine, second_send).publish(command_id)["outcome"] == "puback"
        response = client.get(path)
        assert response.status_code == 200
        timing = response.json()
        assert timing["run_id"] == "timing-run"
        assert timing["prediction_id"] == "timing-prediction"
        assert timing["device_ack_preceded_puback_record"]
        assert timing["created_to_puback_ms"] >= timing["created_to_device_ack_ms"] >= 0
        assert timing["electrical_verified_at"] is None
        assert timing["thermal_verified_at"] is None
        assert timing["physical_timing_reason"] == "NO_TRUSTED_PHYSICAL_EVIDENCE"
        metrics = client.get("/api/metrics").json()
        assert metrics["counters"][retry_metric] == initial + 1
        assert metrics["duration_histograms_ms"]["command_publish"]["count"] >= 2
    finally:
        app.dependency_overrides.pop(get_db_engine, None)
        cleanup_commands(db_engine)
