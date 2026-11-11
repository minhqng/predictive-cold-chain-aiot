"""Tests for clock-quality-aware timing and transmission latency metrics (C-W05-05)."""

from datetime import datetime, timedelta, timezone

from coldguard_backend.timing import (
    DEFAULT_MAX_PLAUSIBLE_LATENCY_MS,
    TimingMetrics,
    compute_timing_metrics,
)


def test_synchronized_timing_calculates_latency():
    now = datetime.now(timezone.utc)
    captured = now - timedelta(milliseconds=125)
    metrics = compute_timing_metrics(now, captured, clock_sync_verified=True)

    assert metrics.status == "SYNCHRONIZED"
    assert metrics.latency_ms is not None
    assert abs(metrics.latency_ms - 125.0) < 0.01
    assert metrics.captured_at == captured
    assert metrics.backend_received_at == now
    assert "synchronized" in metrics.reason.lower()


def test_unverified_clock_yields_null_latency():
    """Fail-closed: timezone-aware captured_at without verified clock must yield null latency."""
    now = datetime.now(timezone.utc)
    captured = now - timedelta(milliseconds=125)
    # Default clock_sync_verified is False
    metrics = compute_timing_metrics(now, captured)

    assert metrics.status == "UNVERIFIED_CLOCK"
    assert metrics.latency_ms is None
    assert metrics.captured_at == captured
    assert metrics.backend_received_at == now
    assert "not been verified" in metrics.reason.lower()


def test_clockless_null_captured_at_yields_null_latency():
    now = datetime.now(timezone.utc)
    metrics = compute_timing_metrics(now, None)

    assert metrics.status == "UNAVAILABLE"
    assert metrics.latency_ms is None
    assert metrics.captured_at is None
    assert metrics.backend_received_at == now
    assert "no wall clock" in metrics.reason


def test_clockless_serial_source_yields_null_latency():
    now = datetime.now(timezone.utc)
    serial_source = {
        "schema_version": 2,
        "clock_quality": "UNAVAILABLE",
        "gateway_received_at": now.isoformat(),
        "frame": "#CG TELEM ...",
    }
    # Even if an erroneous captured_at was passed, serial_source forces UNAVAILABLE
    metrics = compute_timing_metrics(
        now, now - timedelta(seconds=1), serial_source=serial_source
    )

    assert metrics.status == "UNAVAILABLE"
    assert metrics.latency_ms is None
    assert "no wall clock" in metrics.reason


def test_clock_quality_unavailable_yields_null_latency():
    now = datetime.now(timezone.utc)
    metrics = compute_timing_metrics(
        now, now - timedelta(seconds=1), clock_quality="UNAVAILABLE"
    )

    assert metrics.status == "UNAVAILABLE"
    assert metrics.latency_ms is None


def test_future_timestamp_negative_latency():
    now = datetime.now(timezone.utc)
    future = now + timedelta(seconds=5)
    metrics = compute_timing_metrics(now, future, clock_sync_verified=True)

    assert metrics.status == "NEGATIVE_LATENCY"
    assert metrics.latency_ms is None
    assert "future" in metrics.reason.lower()


def test_replay_yields_null_latency():
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=30)
    metrics = compute_timing_metrics(now, past, is_replay=True)

    assert metrics.status == "REPLAY"
    assert metrics.latency_ms is None
    assert "replayed" in metrics.reason.lower()


def test_replay_with_valid_timestamp_takes_precedence_over_sync():
    now = datetime.now(timezone.utc)
    past = now - timedelta(milliseconds=50)
    metrics = compute_timing_metrics(
        now, past, is_replay=True, clock_sync_verified=True
    )

    assert metrics.status == "REPLAY"
    assert metrics.latency_ms is None
    assert "replayed" in metrics.reason.lower()


def test_excessive_skew_yields_null_latency():
    now = datetime.now(timezone.utc)
    far_past = now - timedelta(days=2)
    metrics = compute_timing_metrics(now, far_past, clock_sync_verified=True)

    assert metrics.status == "EXCESSIVE_SKEW"
    assert metrics.latency_ms is None
    assert "exceeds" in metrics.reason.lower()


def test_missing_timezone_yields_untrusted_clock():
    now = datetime.now(timezone.utc)
    naive_captured = datetime(2026, 11, 7, 12, 0, 0)
    metrics = compute_timing_metrics(now, naive_captured)

    assert metrics.status == "UNTRUSTED_CLOCK"
    assert metrics.latency_ms is None
    assert "timezone" in metrics.reason.lower()


def test_naive_backend_received_at_yields_untrusted_clock():
    naive_now = datetime(2026, 11, 7, 12, 0, 1)
    captured = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
    metrics = compute_timing_metrics(naive_now, captured)

    assert metrics.status == "UNTRUSTED_CLOCK"
    assert metrics.latency_ms is None


def test_timing_metrics_to_dict():
    now = datetime.now(timezone.utc)
    metrics = compute_timing_metrics(
        now, now - timedelta(milliseconds=50), clock_sync_verified=True
    )
    d = metrics.to_dict()

    assert d["status"] == "SYNCHRONIZED"
    assert d["latency_ms"] == 50.0
    assert d["backend_received_at"] == now.isoformat()
    assert d["captured_at"] is not None

