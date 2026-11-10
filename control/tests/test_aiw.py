from dataclasses import replace

import pytest

from coldguard_control.aiw import AIWInput, AIWStatus, TimingEvidence, assess_aiw


def _inputs() -> AIWInput:
    return AIWInput(
        run_id="synthetic-run", hardware_config_id="synthetic-hw",
        policy_version="synthetic-policy",
        warning_at=TimingEvidence(10.0, "B synthetic fixture", True),
        critical_at=TimingEvidence(100.0, "A synthetic fixture", True),
        physical_response_delay=TimingEvidence(50.0, "A synthetic fixture", True),
        system_latency=TimingEvidence(5.0, "C synthetic fixture", True),
        warning_clock_domain="run-uptime",
        critical_clock_domain="run-uptime",
        warning_run_id="synthetic-run", critical_run_id="synthetic-run",
        response_hardware_config_id="synthetic-hw",
    )


def test_positive_aiw_is_only_a_candidate():
    result = assess_aiw(_inputs())
    assert result.status is AIWStatus.POSITIVE_CANDIDATE
    assert result.value_s == 35.0
    assert result.physical_enablement is False


def test_negative_aiw_is_not_hidden():
    inputs = replace(
        _inputs(), physical_response_delay=TimingEvidence(95.0, "A test", True)
    )
    result = assess_aiw(inputs)
    assert result.status is AIWStatus.NON_POSITIVE
    assert result.value_s == -10.0


def test_missing_or_unqualified_input_is_unknown():
    inputs = replace(
        _inputs(), system_latency=TimingEvidence(None, "C pending", False)
    )
    result = assess_aiw(inputs)
    assert result.status is AIWStatus.UNKNOWN
    assert result.value_s is None
    assert result.missing == ("system_latency",)


def test_clock_domains_must_match():
    result = assess_aiw(replace(_inputs(), critical_clock_domain="utc"))
    assert result.status is AIWStatus.UNKNOWN
    assert "common_warning_critical_clock" in result.missing


def test_run_and_hardware_provenance_must_match():
    mismatched = replace(
        _inputs(), warning_run_id="another-run",
        response_hardware_config_id="another-hw",
    )
    result = assess_aiw(mismatched)
    assert result.status is AIWStatus.UNKNOWN
    assert "common_run_id" in result.missing
    assert "common_hardware_config" in result.missing


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_invalid_timing_is_rejected(value):
    with pytest.raises(ValueError, match="finite"):
        TimingEvidence(value, "bad", True)


def test_negative_latency_is_rejected():
    with pytest.raises(ValueError, match="negative"):
        replace(_inputs(), system_latency=TimingEvidence(-1.0, "bad", True))


def test_arithmetic_overflow_is_unknown():
    inputs = replace(
        _inputs(),
        warning_at=TimingEvidence(-1e308, "B test", True),
        critical_at=TimingEvidence(1e308, "A test", True),
    )
    result = assess_aiw(inputs)
    assert result.status is AIWStatus.UNKNOWN
    assert result.missing == ("finite_aiw",)
