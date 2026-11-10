"""B-W06-01 … B-W06-04 adversarial and integration tests.

Software fixtures are explicitly synthetic. The real A W09 export, the C
fixture and A's host-generated command log are consumed read-only.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from coldguard_ml import (
    EvaluationContractError,
    LatencyComponent,
    compute_aiw,
    load_capture,
)
from coldguard_ml.real_data_qa import channel_summary_csv
from coldguard_ml.timing_alignment import (
    CLOCK_DEVICE_BOOT_UPTIME,
    CLOCK_DEVICE_EVENT_UTC,
    CLOCK_SYNC_EVIDENCED,
    CLOCK_SYNC_SYNTHETIC_EXACT,
    CLOCK_SYNC_UNVERIFIED,
    DEFAULT_ELECTRICAL_POLICY,
    DEFAULT_THERMAL_POLICY,
    EVENT_APPLIED_STATE,
    EVENT_COMMAND_CREATED_OR_PUBLISHED,
    EVENT_DEVICE_ACK,
    EVENT_DOOR_TRANSITION,
    EVENT_TELEMETRY_SAMPLE,
    ORDERED_IN_DOMAIN,
    ORDER_AMBIGUOUS,
    ORDER_MIXED_BOOT,
    ORDER_MIXED_DEVICE,
    PROVENANCE_PHYSICAL_MEASURED,
    PROVENANCE_SYNTHETIC_FIXTURE,
    PROVENANCE_UNVERIFIED,
    RESPONSE_CENSORED,
    RESPONSE_DUPLICATE_CANONICAL_NOT_APPLICATION,
    RESPONSE_NOT_APPLICABLE_ACK_NOT_ACCEPTED,
    RESPONSE_NOT_ESTIMABLE_CLOCK,
    RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR,
    RESPONSE_NOT_ESTIMABLE_QUALITY,
    RESPONSE_NOT_OBSERVED,
    RESPONSE_OBSERVED_DIAGNOSTIC_ONLY,
    RESPONSE_VERIFIED_MEASURED_RESPONSE,
    ResponsePolicy,
    TimelineEvent,
    ack_to_applied,
    analyze_response,
    audit_timeline,
    command_to_ack,
    command_to_response,
    deduplicate_events,
    event_timeline_csv,
    events_from_capture,
    load_a_command_events,
    load_event_fixture,
    order_timeline,
    partial_order,
    response_summary_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "ml"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "W06"
REAL_A_EXPORT = REPO_ROOT / "evidence/A/W09/exports/CG-S1-H8C-600S.json"
REAL_A_INDEX = REPO_ROOT / "evidence/A/W09/s1-run-index.json"
DEMO_LOG = REPO_ROOT / "evidence/A/W06/demo-command-capture.log"
C_FIXTURE = REPO_ROOT / "backend/fixtures/telemetry_v0.json"
CLI = ML_ROOT / "scripts" / "event-alignment-W06.py"


def _fixture(name):
    return FIXTURES / name


def _events(name):
    return load_event_fixture(_fixture(name))


def _canonical(name):
    return deduplicate_events(_events(name)).canonical_events


def _by_type(events, event_type):
    return [event for event in events if event.event_type == event_type]


def _real_capture():
    return load_capture(REAL_A_EXPORT, a_run_index=REAL_A_INDEX)


def _real_events():
    return events_from_capture(_real_capture())


def _run_cli(arguments, cwd=ML_ROOT):
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _cli_module():
    spec = importlib.util.spec_from_file_location("w06_cli_under_test", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event(
    event_id,
    event_type,
    uptime=1000,
    *,
    seq=None,
    device="dev-1",
    boot="boot-1",
    command_id=None,
    ack_seq=None,
    fields=None,
    clock=CLOCK_DEVICE_BOOT_UPTIME,
    sync=CLOCK_SYNC_SYNTHETIC_EXACT,
    event_time_utc=None,
    backend_received_at=None,
    uncertainty=None,
    source_record_index=None,
):
    return TimelineEvent(
        event_id=event_id,
        event_type=event_type,
        provenance=PROVENANCE_SYNTHETIC_FIXTURE,
        source_path="fixture",
        source_sha256="f" * 64,
        source_namespace="coldguard.w06-event-fixture/v1",
        source_record_index=source_record_index,
        device_id=device,
        boot_id=boot,
        run_id="run-1",
        command_id=command_id,
        ack_seq=ack_seq,
        seq=seq,
        device_uptime_ms=uptime,
        event_time_utc=event_time_utc,
        backend_received_at=backend_received_at,
        clock_domain=clock,
        clock_sync=sync,
        normalized_fields=tuple(sorted((fields or {}).items())),
        uncertainty_s=uncertainty,
    )


def _physical_event(
    event_id,
    event_type,
    uptime,
    *,
    device="dev-1",
    boot="boot-1",
    command_id=None,
    source="physical-source",
    sha="a" * 64,
    fields=None,
    uncertainty=1.0,
    provenance=PROVENANCE_PHYSICAL_MEASURED,
):
    return TimelineEvent(
        event_id=event_id,
        event_type=event_type,
        provenance=provenance,
        source_path=source,
        source_sha256=sha,
        source_namespace="probe/physical-shape",
        device_id=device,
        boot_id=boot,
        run_id="run-1",
        command_id=command_id,
        device_uptime_ms=uptime,
        clock_domain=CLOCK_DEVICE_BOOT_UPTIME,
        clock_sync=CLOCK_SYNC_SYNTHETIC_EXACT,
        normalized_fields=tuple(sorted((fields or {}).items())),
        measurement_quality="VALID",
        uncertainty_s=uncertainty,
    )


def _physical_command_chain(
    *,
    anchor_device="dev-1",
    anchor_boot="boot-1",
    sample_device="dev-1",
    sample_boot="boot-1",
    sample_source="physical-source",
    sample_sha="a" * 64,
):
    command = _physical_event(
        "cmd-identity",
        EVENT_COMMAND_CREATED_OR_PUBLISHED,
        2000,
        device=anchor_device,
        boot=anchor_boot,
        command_id="CMD-ID",
        source="physical-source",
        sha="a" * 64,
    )
    applied = _physical_event(
        "applied-identity",
        EVENT_APPLIED_STATE,
        2100,
        device=anchor_device,
        boot=anchor_boot,
        command_id="CMD-ID",
        source="physical-source",
        sha="a" * 64,
        fields={"applied_to": "ON", "quality.thermal": "VALID"},
    )
    samples = [
        _physical_event(
            f"sample-{index}",
            EVENT_TELEMETRY_SAMPLE,
            uptime,
            device=sample_device,
            boot=sample_boot,
            source=sample_source,
            sha=sample_sha,
            fields={
                "chamber_air_mean_c": f"{value:.6f}",
                "quality.thermal": "VALID",
            },
        )
        for index, (uptime, value) in enumerate(
            [
                (1000, 25.0),
                (1500, 25.0),
                (1900, 25.0),
                (2200, 20.0),
                (2400, 20.0),
                (2600, 20.0),
            ]
        )
    ]
    return command, applied, samples


def _baseline_events():
    return [
        _event(
            "t0",
            EVENT_TELEMETRY_SAMPLE,
            1000,
            seq=1000,
            fields={"cooling_current_a": "0.000000", "chamber_air_mean_c": "25.0",
                    "quality.electrical": "VALID", "quality.thermal": "VALID"},
        ),
        _event(
            "t1",
            EVENT_TELEMETRY_SAMPLE,
            1500,
            seq=1001,
            fields={"cooling_current_a": "0.000000", "chamber_air_mean_c": "25.0",
                    "quality.electrical": "VALID", "quality.thermal": "VALID"},
        ),
    ]


# ---------------------------------------------------------------------------
# B-W06-01 event alignment
# ---------------------------------------------------------------------------


def test_same_boot_same_clock_orders_lifecycle_events():
    events = _canonical("qualified-response.json")
    ordered = order_timeline(events)
    assert ordered.status == ORDERED_IN_DOMAIN
    ids = [event.event_id for event in ordered.events]
    assert ids.index("cmd-publish") < ids.index("ack-1") < ids.index("applied-1")
    assert ordered.clock_domain == CLOCK_DEVICE_BOOT_UPTIME
    assert ordered.device_id == "cg-sim-qualified"
    assert ordered.boot_id == "sim-boot-qualified"


def test_two_boots_with_equal_uptime_are_not_joined():
    events = _canonical("two-boots-equal-uptime.json")
    ordered = order_timeline(events)
    assert ordered.status == ORDER_MIXED_BOOT
    assert "CROSS_BOOT_JOIN_REFUSED" in ordered.reason_codes
    assert len(events) == 2


def test_missing_clock_sync_blocks_absolute_latency():
    command = _event(
        "cmd",
        EVENT_COMMAND_CREATED_OR_PUBLISHED,
        clock=CLOCK_DEVICE_EVENT_UTC,
        sync=CLOCK_SYNC_UNVERIFIED,
        event_time_utc="2026-01-01T00:00:00Z",
        command_id="CMD-UTC",
        fields={"desired_cooling": "ON"},
    )
    ack = _event(
        "ack",
        EVENT_DEVICE_ACK,
        clock=CLOCK_DEVICE_EVENT_UTC,
        sync=CLOCK_SYNC_UNVERIFIED,
        event_time_utc="2026-01-01T00:00:01Z",
        command_id="CMD-UTC",
        ack_seq=1,
        fields={"status": "ACCEPTED"},
    )
    result = command_to_ack([command], [ack])[0]
    assert result.state == RESPONSE_NOT_ESTIMABLE_CLOCK
    assert result.latency_s is None
    assert "UNVERIFIED_CLOCK_SYNC" in result.reason_codes


def test_host_capture_time_is_never_promoted_to_device_event_time():
    events = _real_events()
    samples = _by_type(events, EVENT_TELEMETRY_SAMPLE)
    assert samples
    assert all(event.event_time_utc is None for event in samples)
    assert all(event.clock_domain == CLOCK_DEVICE_BOOT_UPTIME for event in samples)
    assert all(event.field_origin == "NORMALIZED_ONLY" for event in samples)
    assert all(event.field("host_capture_time_utc") is None for event in samples)


def test_out_of_order_reception_reports_conflict_but_keeps_device_order():
    first = _event(
        "first",
        EVENT_TELEMETRY_SAMPLE,
        1000,
        seq=1,
        clock=CLOCK_DEVICE_EVENT_UTC,
        event_time_utc="2026-01-01T00:00:01Z",
        backend_received_at="2026-01-01T00:00:02Z",
    )
    second = _event(
        "second",
        EVENT_TELEMETRY_SAMPLE,
        2000,
        seq=2,
        clock=CLOCK_DEVICE_EVENT_UTC,
        event_time_utc="2026-01-01T00:00:02Z",
        backend_received_at="2026-01-01T00:00:01Z",
    )
    audit = audit_timeline([first, second])
    assert audit.domains[0].capture_receive_conflicts == 1
    ordered = order_timeline([first, second])
    assert ordered.status == ORDERED_IN_DOMAIN
    assert [event.event_id for event in ordered.events] == ["first", "second"]


def test_time_reversal_is_ambiguous_and_not_silently_reordered():
    first = _event(
        "first", EVENT_TELEMETRY_SAMPLE, 2000, seq=1, source_record_index=1
    )
    second = _event(
        "second", EVENT_TELEMETRY_SAMPLE, 1000, seq=2, source_record_index=2
    )
    ordered = order_timeline([first, second])
    assert ordered.status == ORDER_AMBIGUOUS
    assert "TIME_REVERSAL" in ordered.reason_codes
    assert [event.event_id for event in ordered.events] == ["first", "second"]


def test_time_reversal_retains_unindexed_events():
    first = _event(
        "first", EVENT_TELEMETRY_SAMPLE, 2000, seq=1, source_record_index=1
    )
    second = _event(
        "second", EVENT_TELEMETRY_SAMPLE, 1000, seq=2, source_record_index=2
    )
    unindexed = _event("third", EVENT_TELEMETRY_SAMPLE, 1500, seq=3)
    ordered = order_timeline([first, second, unindexed])
    assert ordered.status == ORDER_AMBIGUOUS
    assert {event.event_id for event in ordered.events} == {
        "first",
        "second",
        "third",
    }
    assert len(ordered.events) == 3


def test_missing_identity_event_is_retained_without_invented_keys():
    event = _event(
        "anonymous",
        EVENT_TELEMETRY_SAMPLE,
        1000,
        device=None,
        boot=None,
        seq=None,
    )
    dedup = deduplicate_events([event])
    assert dedup.canonical_events == ()
    assert len(dedup.missing_identity_events) == 1
    assert "MISSING_IDENTITY" in dedup.reason_codes


def test_real_a_unresolved_run_identity_is_retained():
    samples = _by_type(_real_events(), EVENT_TELEMETRY_SAMPLE)
    assert samples
    assert all("RUN_ID_UNRESOLVED" in event.reason_codes for event in samples)
    assert all(event.identity_status == "PARTIAL" for event in samples)
    assert {event.run_id for event in samples} == {"run-00000000", "run-00000001"}


def test_ack_adapter_rejects_non_command_schema(tmp_path):
    log = tmp_path / "bad-ack.log"
    log.write_text(
        "#CG CMDACK schema=3 event=ACK command_id=x\n", encoding="utf-8"
    )
    with pytest.raises(Exception) as exc:
        load_a_command_events(log, provenance="HOST_GENERATED_SYNTHETIC")
    assert "ACK_SCHEMA_NOT_COMMAND_ENVELOPE" in str(exc.value)


def test_ack_adapter_ignores_serial_telemetry_lines():
    load = load_a_command_events(
        DEMO_LOG, provenance="HOST_GENERATED_SYNTHETIC"
    )
    assert len(load.events) == 5
    assert all(event.event_type == EVENT_DEVICE_ACK for event in load.events)
    assert load.ignored_telemetry_lines == 1
    assert all(
        event.source_namespace == "coldguard.command-ack-serial/v1"
        for event in load.events
    )


def test_declared_boot_identity_does_not_clean_mixed_boot_events():
    events = [
        _event("first", EVENT_TELEMETRY_SAMPLE, 1000, device="dev-1", boot="boot-1"),
        _event("second", EVENT_TELEMETRY_SAMPLE, 2000, device="dev-1", boot="boot-2"),
    ]
    ordered = order_timeline(events, boot_id="boot-1")
    assert ordered.status == ORDER_MIXED_BOOT
    assert "CROSS_BOOT_JOIN_REFUSED" in ordered.reason_codes
    assert ordered.boot_id is None
    assert [event.event_id for event in ordered.events] == ["first", "second"]


def test_declared_device_identity_does_not_clean_mixed_device_events():
    events = [
        _event("first", EVENT_TELEMETRY_SAMPLE, 1000, device="dev-1", boot="boot-1"),
        _event("second", EVENT_TELEMETRY_SAMPLE, 2000, device="dev-2", boot="boot-1"),
    ]
    ordered = order_timeline(events, device_id="dev-1")
    assert ordered.status == ORDER_MIXED_DEVICE
    assert "MIXED_DEVICE_IDENTITIES" in ordered.reason_codes
    assert ordered.device_id is None
    assert [event.event_id for event in ordered.events] == ["first", "second"]


def test_declared_identity_without_event_evidence_is_not_alignable():
    events = [
        _event("first", EVENT_TELEMETRY_SAMPLE, 1000, device=None, boot=None),
        _event("second", EVENT_TELEMETRY_SAMPLE, 2000, device=None, boot=None),
    ]
    ordered = order_timeline(events, device_id="dev-1", boot_id="boot-1")
    assert ordered.status != ORDERED_IN_DOMAIN
    assert "DECLARED_DEVICE_ID_NOT_EVIDENCED" in ordered.reason_codes
    assert ordered.device_id is None
    assert ordered.boot_id is None


def test_declared_identity_matching_events_orders_normally():
    events = [
        _event("first", EVENT_TELEMETRY_SAMPLE, 1000, device="dev-1", boot="boot-1"),
        _event("second", EVENT_TELEMETRY_SAMPLE, 2000, device="dev-1", boot="boot-1"),
    ]
    ordered = order_timeline(events, device_id="dev-1", boot_id="boot-1")
    assert ordered.status == ORDERED_IN_DOMAIN
    assert ordered.device_id == "dev-1"
    assert ordered.boot_id == "boot-1"


def test_declared_device_conflicting_with_events_is_rejected():
    events = [
        _event("first", EVENT_TELEMETRY_SAMPLE, 1000, device="dev-1", boot="boot-1"),
    ]
    ordered = order_timeline(events, device_id="dev-2")
    assert ordered.status == "NOT_ALIGNABLE"
    assert "DECLARED_DEVICE_ID_CONFLICTS_WITH_EVENTS" in ordered.reason_codes
    assert ordered.device_id is None
    assert [event.event_id for event in ordered.events] == ["first"]


def test_declared_boot_without_event_evidence_is_rejected():
    events = [
        _event("first", EVENT_TELEMETRY_SAMPLE, 1000, device="dev-1", boot=None),
        _event("second", EVENT_TELEMETRY_SAMPLE, 2000, device="dev-1", boot=None),
    ]
    ordered = order_timeline(events, boot_id="boot-1")
    assert ordered.status != ORDERED_IN_DOMAIN
    assert "DECLARED_BOOT_ID_NOT_EVIDENCED" in ordered.reason_codes
    assert ordered.boot_id is None


def test_partial_order_claims_protocol_stage_not_latency():
    events = _canonical("qualified-response.json")
    relations = partial_order(events)
    assert relations
    assert all(not relation.latency_claim for relation in relations)
    assert any(
        "COMMAND_CREATED_OR_PUBLISHED_BEFORE_DEVICE_ACK" in relation.relation
        for relation in relations
    )
    assert any(
        "DEVICE_ACK_BEFORE_APPLIED_STATE" in relation.relation
        for relation in relations
    )


def test_partial_order_does_not_cross_boots():
    first = _event(
        "ack-a",
        EVENT_DEVICE_ACK,
        1000,
        boot="boot-a",
        command_id="CMD-X",
        ack_seq=1,
        fields={"status": "ACCEPTED"},
    )
    second = _event(
        "ack-b",
        EVENT_DEVICE_ACK,
        1000,
        boot="boot-b",
        command_id="CMD-X",
        ack_seq=2,
        fields={"status": "DUPLICATE_CANONICAL"},
    )
    assert partial_order([first, second]) == ()


# ---------------------------------------------------------------------------
# B-W06-02 clock and sequence diagnostics
# ---------------------------------------------------------------------------


def test_real_a_diagnostics_preserve_w05_facts():
    events = _real_events()
    canonical = deduplicate_events(events).canonical_events
    audit = audit_timeline(canonical)
    assert len(audit.domains) == 1
    domain = audit.domains[0]
    assert domain.clock_domain == CLOCK_DEVICE_BOOT_UPTIME
    assert domain.event_count == len(canonical)
    assert domain.median_interval_s == pytest.approx(1.0)
    assert domain.p95_interval_s == pytest.approx(1.0)
    assert domain.timestamp_reversals == 0
    assert domain.sequence_gaps == 0
    assert domain.sequence_duplicates == 0
    assert domain.uptime_resets == 0
    assert domain.monotonic is True
    assert "MISSING_CAPTURE_TIME" in domain.reason_codes
    assert "MISSING_RECEIVE_TIME" in domain.reason_codes
    assert len(_by_type(canonical, EVENT_TELEMETRY_SAMPLE)) == 957
    assert len(_by_type(canonical, EVENT_DOOR_TRANSITION)) == 0
    assert len(_by_type(canonical, EVENT_COMMAND_CREATED_OR_PUBLISHED)) == 0
    assert len(_by_type(canonical, EVENT_DEVICE_ACK)) == 0


def test_sequence_gap_and_duplicate_are_reported():
    events = [
        _event("a", EVENT_TELEMETRY_SAMPLE, 1000, seq=1),
        _event("b", EVENT_TELEMETRY_SAMPLE, 2000, seq=2),
        _event("c", EVENT_TELEMETRY_SAMPLE, 3000, seq=4),
        _event("d", EVENT_TELEMETRY_SAMPLE, 4000, seq=4),
    ]
    audit = audit_timeline(events)
    domain = audit.domains[0]
    assert domain.sequence_gaps == 1
    assert domain.sequence_duplicates == 1


def test_uptime_reset_and_timestamp_reversal_are_reported():
    events = [
        _event("a", EVENT_TELEMETRY_SAMPLE, 1000, seq=1, source_record_index=1),
        _event("b", EVENT_TELEMETRY_SAMPLE, 2000, seq=2, source_record_index=2),
        _event("c", EVENT_TELEMETRY_SAMPLE, 1500, seq=3, source_record_index=3),
    ]
    audit = audit_timeline(events)
    domain = audit.domains[0]
    assert domain.uptime_resets == 1
    assert domain.timestamp_reversals == 1
    assert domain.monotonic is False
    assert "TIME_REVERSAL" in domain.reason_codes


def test_missing_capture_and_receive_fields_are_counted():
    event = _event("a", EVENT_TELEMETRY_SAMPLE, 1000, seq=1)
    audit = audit_timeline([event])
    domain = audit.domains[0]
    assert domain.missing_capture_times == 1
    assert domain.missing_receive_times == 1
    assert domain.capture_receive_conflicts == 0


# ---------------------------------------------------------------------------
# B-W06-03 response helpers
# ---------------------------------------------------------------------------


def test_qualified_synthetic_electrical_response_is_numeric_but_diagnostic():
    events = _canonical("qualified-response.json")
    anchor = _by_type(events, EVENT_APPLIED_STATE)[0]
    samples = _by_type(events, EVENT_TELEMETRY_SAMPLE)
    result = analyze_response(
        "APPLIED_TO_ELECTRICAL", anchor, samples, DEFAULT_ELECTRICAL_POLICY
    )
    assert result.state == RESPONSE_OBSERVED_DIAGNOSTIC_ONLY
    assert result.evidence_class == "SYNTHETIC_UNIT_TEST"
    assert result.latency_s == pytest.approx(0.2)
    assert result.uncertainty_s == pytest.approx(0.05)


def test_qualified_synthetic_thermal_response_is_numeric_but_diagnostic():
    events = _canonical("qualified-response.json")
    anchor = _by_type(events, EVENT_APPLIED_STATE)[0]
    samples = _by_type(events, EVENT_TELEMETRY_SAMPLE)
    result = analyze_response(
        "APPLIED_TO_THERMAL", anchor, samples, DEFAULT_THERMAL_POLICY
    )
    assert result.state == RESPONSE_OBSERVED_DIAGNOSTIC_ONLY
    assert result.latency_s == pytest.approx(0.3)


def test_command_to_response_requires_an_applied_chain_link():
    events = _canonical("qualified-response.json")
    commands = _by_type(events, EVENT_COMMAND_CREATED_OR_PUBLISHED)
    samples = _by_type(events, EVENT_TELEMETRY_SAMPLE)
    results = command_to_response(
        commands,
        [],
        samples,
        DEFAULT_ELECTRICAL_POLICY,
        relationship="COMMAND_TO_ELECTRICAL",
    )
    assert results[0].state == RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR
    assert "NO_APPLIED_STATE_EVIDENCE" in results[0].reason_codes
    assert results[0].latency_s is None


def test_accepted_ack_without_applied_evidence_is_not_a_response():
    load = load_a_command_events(
        DEMO_LOG, provenance="HOST_GENERATED_SYNTHETIC"
    )
    results = {
        result.command_id: result
        for result in ack_to_applied(load.events, [])
    }
    accepted = next(
        result
        for command_id, result in results.items()
        if command_id.endswith("000b")
    )
    assert accepted.state == RESPONSE_NOT_OBSERVED
    assert accepted.latency_s is None
    assert "NO_APPLIED_STATE_EVIDENCE_AFTER_ACCEPTED_ACK" in accepted.reason_codes


def test_unqualified_electrical_quality_never_certifies():
    events = _canonical("unqualified-electrical.json")
    anchor = _by_type(events, EVENT_APPLIED_STATE)[0]
    samples = _by_type(events, EVENT_TELEMETRY_SAMPLE)
    result = analyze_response(
        "APPLIED_TO_ELECTRICAL", anchor, samples, DEFAULT_ELECTRICAL_POLICY
    )
    assert result.state == RESPONSE_NOT_ESTIMABLE_QUALITY
    assert result.latency_s is None


def test_real_a_electrical_quality_is_unknown_and_never_certifies():
    capture = _real_capture()
    canonical = deduplicate_events(events_from_capture(capture)).canonical_events
    anchor = _by_type(canonical, EVENT_APPLIED_STATE)[0]
    samples = _by_type(canonical, EVENT_TELEMETRY_SAMPLE)
    result = analyze_response(
        "APPLIED_TO_ELECTRICAL", anchor, samples, DEFAULT_ELECTRICAL_POLICY
    )
    assert result.state == RESPONSE_NOT_ESTIMABLE_QUALITY
    assert result.latency_s is None
    assert "BASELINE_QUALITY_NOT_VALID" in result.reason_codes


def test_real_a_thermal_diagnostic_is_not_reported_as_a_numeric_delay():
    capture = _real_capture()
    canonical = deduplicate_events(events_from_capture(capture)).canonical_events
    anchor = _by_type(canonical, EVENT_APPLIED_STATE)[0]
    samples = _by_type(canonical, EVENT_TELEMETRY_SAMPLE)
    result = analyze_response(
        "APPLIED_TO_THERMAL", anchor, samples, DEFAULT_THERMAL_POLICY
    )
    assert result.state == RESPONSE_OBSERVED_DIAGNOSTIC_ONLY
    assert result.latency_s is None
    assert "ANCHOR_QUALITY_NOT_VALID_DIAGNOSTIC_ONLY" in result.reason_codes


def test_response_with_missing_sample_device_identity_is_not_estimable():
    command, applied, samples = _physical_command_chain(sample_device=None)
    result = command_to_response(
        [command], [applied], samples, DEFAULT_THERMAL_POLICY,
        relationship="COMMAND_TO_THERMAL",
    )[0]
    assert result.state != RESPONSE_VERIFIED_MEASURED_RESPONSE
    assert result.latency_s is None
    assert "STREAM_IDENTITY_NOT_ESTIMABLE" in result.reason_codes


def test_response_with_missing_sample_boot_identity_is_not_estimable():
    command, applied, samples = _physical_command_chain(sample_boot=None)
    result = command_to_response(
        [command], [applied], samples, DEFAULT_THERMAL_POLICY,
        relationship="COMMAND_TO_THERMAL",
    )[0]
    assert result.state != RESPONSE_VERIFIED_MEASURED_RESPONSE
    assert result.latency_s is None
    assert "STREAM_IDENTITY_NOT_ESTIMABLE" in result.reason_codes


def test_response_from_unrelated_source_is_not_attributed_across_identity():
    command, applied, samples = _physical_command_chain(
        sample_device=None,
        sample_boot=None,
        sample_source="unrelated-source",
        sample_sha="u" * 64,
    )
    result = command_to_response(
        [command], [applied], samples, DEFAULT_THERMAL_POLICY,
        relationship="COMMAND_TO_THERMAL",
    )[0]
    assert result.state != RESPONSE_VERIFIED_MEASURED_RESPONSE
    assert result.latency_s is None
    assert "STREAM_IDENTITY_NOT_ESTIMABLE" in result.reason_codes


def test_proven_device_conflict_rejects_response_association():
    command, applied, samples = _physical_command_chain(sample_device="dev-2")
    result = command_to_response(
        [command], [applied], samples, DEFAULT_THERMAL_POLICY,
        relationship="COMMAND_TO_THERMAL",
    )[0]
    assert result.state != RESPONSE_VERIFIED_MEASURED_RESPONSE
    assert result.latency_s is None


def test_same_source_missing_device_identity_is_diagnostic_not_verified():
    command, applied, samples = _physical_command_chain(
        anchor_device=None, sample_device=None
    )
    result = command_to_response(
        [command], [applied], samples, DEFAULT_THERMAL_POLICY,
        relationship="COMMAND_TO_THERMAL",
    )[0]
    assert result.state == RESPONSE_OBSERVED_DIAGNOSTIC_ONLY
    assert result.latency_s == pytest.approx(0.2)
    assert "INCOMPLETE_EVENT_IDENTITY_DIAGNOSTIC_ONLY" in result.reason_codes


def test_ack_to_applied_missing_device_identity_is_diagnostic_not_verified():
    ack = _physical_event(
        "ack-identity",
        EVENT_DEVICE_ACK,
        1000,
        device=None,
        command_id="CMD-ID",
        fields={"status": "ACCEPTED"},
    )
    applied = _physical_event(
        "applied-identity",
        EVENT_APPLIED_STATE,
        1300,
        device=None,
        command_id="CMD-ID",
        fields={"applied_to": "ON"},
    )
    result = ack_to_applied([ack], [applied])[0]
    assert result.state == RESPONSE_OBSERVED_DIAGNOSTIC_ONLY
    assert result.latency_s == pytest.approx(0.3)
    assert "INCOMPLETE_EVENT_IDENTITY_DIAGNOSTIC_ONLY" in result.reason_codes


def test_ack_to_applied_asymmetric_identity_is_not_estimable():
    ack = _physical_event(
        "ack-identity",
        EVENT_DEVICE_ACK,
        1000,
        command_id="CMD-ID",
        fields={"status": "ACCEPTED"},
    )
    applied = _physical_event(
        "applied-identity",
        EVENT_APPLIED_STATE,
        1300,
        device=None,
        command_id="CMD-ID",
        fields={"applied_to": "ON"},
    )
    result = ack_to_applied([ack], [applied])[0]
    assert result.state == RESPONSE_NOT_ESTIMABLE_CLOCK
    assert result.latency_s is None
    assert "MIXED_CLOCK_DOMAIN_OR_STREAM" in result.reason_codes


def test_both_events_missing_boot_identity_are_not_a_stream():
    command, applied, samples = _physical_command_chain(
        anchor_boot=None, sample_boot=None
    )
    result = command_to_response(
        [command], [applied], samples, DEFAULT_THERMAL_POLICY,
        relationship="COMMAND_TO_THERMAL",
    )[0]
    assert result.state == RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR
    assert result.latency_s is None
    assert "NO_APPLIED_STATE_EVIDENCE" in result.reason_codes


def test_anchor_missing_device_with_full_sample_identity_is_not_estimable():
    command, applied, samples = _physical_command_chain(anchor_device=None)
    result = command_to_response(
        [command], [applied], samples, DEFAULT_THERMAL_POLICY,
        relationship="COMMAND_TO_THERMAL",
    )[0]
    assert result.state != RESPONSE_VERIFIED_MEASURED_RESPONSE
    assert result.latency_s is None
    assert "STREAM_IDENTITY_NOT_ESTIMABLE" in result.reason_codes


def test_unverified_provenance_command_to_ack_has_no_numeric_latency():
    command = _physical_event(
        "cmd-unverified",
        EVENT_COMMAND_CREATED_OR_PUBLISHED,
        1000,
        command_id="CMD-UNVERIFIED",
    )
    ack = _physical_event(
        "ack-unverified",
        EVENT_DEVICE_ACK,
        1300,
        command_id="CMD-UNVERIFIED",
        fields={"status": "ACCEPTED"},
        provenance=PROVENANCE_UNVERIFIED,
    )
    result = command_to_ack([command], [ack])[0]
    assert result.state == RESPONSE_OBSERVED_DIAGNOSTIC_ONLY
    assert result.latency_s is None
    assert "UNVERIFIED_PROVENANCE_DIAGNOSTIC_ONLY" in result.reason_codes


def test_tec_hot_side_is_never_a_chamber_air_response_channel():
    with pytest.raises(Exception):
        ResponsePolicy(
            name="bad",
            channel="t2_c",
            physical_role="CHAMBER_AIR",
            quality_key="thermal",
            expected_direction="DOWN",
            min_change=0.25,
        )
    with pytest.raises(Exception):
        ResponsePolicy(
            name="bad",
            channel="chamber_air_mean_c",
            physical_role="TEC_HOT_SIDE",
            quality_key="thermal",
            expected_direction="DOWN",
            min_change=0.25,
        )


def test_missing_response_is_not_zero_and_censoring_is_explicit():
    events = _canonical("no-response.json")
    anchor = _by_type(events, EVENT_APPLIED_STATE)[0]
    samples = _by_type(events, EVENT_TELEMETRY_SAMPLE)
    short = analyze_response(
        "APPLIED_TO_ELECTRICAL",
        anchor,
        samples,
        ResponsePolicy(
            name="short-window",
            channel="cooling_current_a",
            physical_role="COOLING_BRANCH_ELECTRICAL",
            quality_key="electrical",
            expected_direction="UP",
            min_change=0.05,
            baseline_window_s=10.0,
            max_window_s=1.0,
            sustained_observations=3,
            max_gap_s=5.0,
            max_uncertainty_s=10.0,
        ),
    )
    assert short.state == RESPONSE_NOT_OBSERVED
    assert short.latency_s is None
    censored = analyze_response(
        "APPLIED_TO_ELECTRICAL", anchor, samples, DEFAULT_ELECTRICAL_POLICY
    )
    assert censored.state == RESPONSE_CENSORED
    assert censored.latency_s is None


def test_threshold_boundary_is_inclusive_and_configurable():
    anchor = _event(
        "anchor",
        EVENT_APPLIED_STATE,
        2000,
        fields={
            "applied_to": "ON",
            "quality.electrical": "VALID",
            "quality.thermal": "VALID",
        },
    )
    samples = [
        _event("b0", EVENT_TELEMETRY_SAMPLE, 1000, seq=1,
               fields={"cooling_current_a": "0.000000",
                       "quality.electrical": "VALID"},
               uncertainty=0.0),
        _event("b1", EVENT_TELEMETRY_SAMPLE, 1500, seq=2,
               fields={"cooling_current_a": "0.000000",
                       "quality.electrical": "VALID"},
               uncertainty=0.0),
        _event("p0", EVENT_TELEMETRY_SAMPLE, 2500, seq=3,
               fields={"cooling_current_a": "0.500000",
                       "quality.electrical": "VALID"},
               uncertainty=0.0),
        _event("p1", EVENT_TELEMETRY_SAMPLE, 3000, seq=4,
               fields={"cooling_current_a": "0.500000",
                       "quality.electrical": "VALID"},
               uncertainty=0.0),
        _event("p2", EVENT_TELEMETRY_SAMPLE, 3500, seq=5,
               fields={"cooling_current_a": "0.500000",
                       "quality.electrical": "VALID"},
               uncertainty=0.0),
        _event("p3", EVENT_TELEMETRY_SAMPLE, 4000, seq=6,
               fields={"cooling_current_a": "0.500000",
                       "quality.electrical": "VALID"},
               uncertainty=0.0),
    ]
    policy = ResponsePolicy(
        name="boundary",
        channel="cooling_current_a",
        physical_role="COOLING_BRANCH_ELECTRICAL",
        quality_key="electrical",
        expected_direction="UP",
        min_change=0.5,
        baseline_window_s=2.0,
        max_window_s=2.0,
        sustained_observations=3,
        max_gap_s=5.0,
        max_uncertainty_s=10.0,
    )
    result = analyze_response("APPLIED_TO_ELECTRICAL", anchor, samples, policy)
    assert result.state == RESPONSE_OBSERVED_DIAGNOSTIC_ONLY
    assert result.latency_s == pytest.approx(0.5)


def test_missing_uncertainty_does_not_report_a_numeric_delay():
    anchor = _event(
        "anchor",
        EVENT_APPLIED_STATE,
        2000,
        fields={
            "applied_to": "ON",
            "quality.electrical": "VALID",
            "quality.thermal": "VALID",
        },
    )
    samples = [
        _event("b0", EVENT_TELEMETRY_SAMPLE, 1000, seq=1,
               fields={"cooling_current_a": "0.0",
                       "quality.electrical": "VALID"}),
        _event("b1", EVENT_TELEMETRY_SAMPLE, 1500, seq=2,
               fields={"cooling_current_a": "0.0",
                       "quality.electrical": "VALID"}),
        _event("p0", EVENT_TELEMETRY_SAMPLE, 2500, seq=3,
               fields={"cooling_current_a": "0.5",
                       "quality.electrical": "VALID"}),
        _event("p1", EVENT_TELEMETRY_SAMPLE, 3000, seq=4,
               fields={"cooling_current_a": "0.5",
                       "quality.electrical": "VALID"}),
        _event("p2", EVENT_TELEMETRY_SAMPLE, 3500, seq=5,
               fields={"cooling_current_a": "0.5",
                       "quality.electrical": "VALID"}),
    ]
    result = analyze_response(
        "APPLIED_TO_ELECTRICAL",
        anchor,
        samples,
        ResponsePolicy(
            name="no-uncertainty",
            channel="cooling_current_a",
            physical_role="COOLING_BRANCH_ELECTRICAL",
            quality_key="electrical",
            expected_direction="UP",
            min_change=0.05,
            baseline_window_s=10.0,
            max_window_s=10.0,
            sustained_observations=3,
            max_gap_s=5.0,
            max_uncertainty_s=10.0,
        ),
    )
    assert result.state == "NOT_ESTIMABLE_UNCERTAINTY"
    assert result.latency_s is None
    assert "UNCERTAINTY_NOT_CARRIED" in result.reason_codes


def test_uncertainty_above_the_bound_does_not_report_a_delay():
    events = _canonical("qualified-response.json")
    anchor = _by_type(events, EVENT_APPLIED_STATE)[0]
    anchor = TimelineEvent(**{**anchor.__dict__, "uncertainty_s": 100.0})
    samples = _by_type(events, EVENT_TELEMETRY_SAMPLE)
    policy = ResponsePolicy(
        name="bounded",
        channel="cooling_current_a",
        physical_role="COOLING_BRANCH_ELECTRICAL",
        quality_key="electrical",
        expected_direction="UP",
        min_change=0.05,
        baseline_window_s=10.0,
        max_window_s=60.0,
        sustained_observations=3,
        max_gap_s=5.0,
        max_uncertainty_s=10.0,
    )
    result = analyze_response("APPLIED_TO_ELECTRICAL", anchor, samples, policy)
    assert result.state == "NOT_ESTIMABLE_UNCERTAINTY"
    assert result.latency_s is None


def test_mixed_clock_command_to_ack_never_yields_absolute_latency():
    events = _canonical("mixed-clock.json")
    commands = _by_type(events, EVENT_COMMAND_CREATED_OR_PUBLISHED)
    acks = _by_type(events, EVENT_DEVICE_ACK)
    result = command_to_ack(commands, acks)[0]
    assert result.state == RESPONSE_NOT_ESTIMABLE_CLOCK
    assert result.latency_s is None


def test_command_to_ack_requires_a_publication_anchor():
    load = load_a_command_events(
        DEMO_LOG, provenance="HOST_GENERATED_SYNTHETIC"
    )
    results = command_to_ack([], load.events)
    assert results
    assert all(result.state == RESPONSE_NOT_ESTIMABLE_MISSING_ANCHOR for result in results)
    assert all(
        "ACK_RELATIVE_LATENCY_IS_NOT_COMMAND_PUBLICATION_LATENCY"
        in result.reason_codes
        for result in results
    )


def test_ack_to_applied_requires_synchronized_utc_clock():
    ack = _event(
        "ack",
        EVENT_DEVICE_ACK,
        clock=CLOCK_DEVICE_EVENT_UTC,
        sync=CLOCK_SYNC_UNVERIFIED,
        event_time_utc="2026-01-01T00:00:00Z",
        command_id="CMD-UTC",
        ack_seq=1,
        fields={"status": "ACCEPTED"},
    )
    applied = _event(
        "applied",
        EVENT_APPLIED_STATE,
        clock=CLOCK_DEVICE_EVENT_UTC,
        sync=CLOCK_SYNC_UNVERIFIED,
        event_time_utc="2026-01-01T00:00:01Z",
        command_id="CMD-UTC",
        fields={"applied_to": "ON"},
    )
    result = ack_to_applied([ack], [applied])[0]
    assert result.state == RESPONSE_NOT_ESTIMABLE_CLOCK
    assert result.latency_s is None
    assert "UNVERIFIED_CLOCK_SYNC" in result.reason_codes


def test_response_samples_with_unverified_utc_clock_are_not_estimable():
    anchor = _event(
        "anchor",
        EVENT_APPLIED_STATE,
        clock=CLOCK_DEVICE_EVENT_UTC,
        sync=CLOCK_SYNC_EVIDENCED,
        event_time_utc="2026-01-01T00:00:00Z",
        fields={
            "applied_to": "ON",
            "quality.electrical": "VALID",
            "quality.thermal": "VALID",
        },
    )
    samples = [
        _event(
            f"sample-{index}",
            EVENT_TELEMETRY_SAMPLE,
            clock=CLOCK_DEVICE_EVENT_UTC,
            sync=CLOCK_SYNC_UNVERIFIED,
            event_time_utc=f"2026-01-01T00:00:0{index}Z",
            seq=index,
            fields={"cooling_current_a": "0.0",
                    "quality.electrical": "VALID"},
        )
        for index in range(1, 4)
    ]
    result = analyze_response(
        "APPLIED_TO_ELECTRICAL", anchor, samples, DEFAULT_ELECTRICAL_POLICY
    )
    assert result.state == RESPONSE_NOT_ESTIMABLE_CLOCK
    assert result.latency_s is None
    assert "SAMPLE_CLOCK_SYNC_UNVERIFIED" in result.reason_codes


def test_w04_aiw_overlap_remains_rejected():
    system = [
        LatencyComponent(
            name="system",
            owner="B",
            start_s=0.0,
            end_s=2.0,
            clock_domain="DEVICE_BOOT_UPTIME",
            measurement_method="test",
            uncertainty_s=0.0,
        )
    ]
    physical = [
        LatencyComponent(
            name="physical",
            owner="A",
            start_s=1.0,
            end_s=3.0,
            clock_domain="DEVICE_BOOT_UPTIME",
            measurement_method="test",
            uncertainty_s=0.0,
        )
    ]
    with pytest.raises(EvaluationContractError):
        compute_aiw(
            t_critical_s=10.0,
            t_warning_s=0.0,
            system_components=system,
            physical_components=physical,
            reference_clock_domain="DEVICE_BOOT_UPTIME",
        )


# ---------------------------------------------------------------------------
# B-W06-04 duplicate and idempotency handling
# ---------------------------------------------------------------------------


def test_exact_duplicate_collapses_with_multiplicity():
    dedup = deduplicate_events(_events("exact-duplicate.json"))
    assert len(dedup.canonical_events) == 1
    assert dedup.canonical_events[0].delivery_count == 2
    assert dedup.duplicate_deliveries == 1
    assert "IDENTICAL_DUPLICATE_DELIVERY" in dedup.reason_codes


def test_contradictory_duplicate_identity_keeps_both_payloads():
    dedup = deduplicate_events(_events("contradictory-identity.json"))
    assert dedup.canonical_events == ()
    assert len(dedup.contradictory_events) == 4
    assert "CONTRADICTORY_IDENTITY" in dedup.reason_codes


def test_contradictory_ack_deliveries_keep_distinct_event_ids(tmp_path):
    fields = (
        "#CG CMDACK schema=1 event=ACK command_id=CMD-X command_id_form=UUID "
        "source=NETWORK device_id=dev-1 boot_id=boot-1 uptime_ms=1000 "
        "ack_seq=7 status={status} reason={reason} desired_cooling=ON "
        "desired_duty_permille=500 applied_cooling=OFF "
        "applied_duty_permille=0 reapplied=0 expiry_evaluable=1 "
        "time_sync_state=SYNCHRONIZED device_mode=OFF"
    )
    log = tmp_path / "conflict.log"
    log.write_text(
        fields.format(status="ACCEPTED", reason="NONE")
        + "\n"
        + fields.format(status="REJECTED", reason="DEVICE_ID_MISMATCH")
        + "\n",
        encoding="utf-8",
    )
    load = load_a_command_events(log, provenance="HOST_GENERATED_SYNTHETIC")
    dedup = deduplicate_events(load.events)
    assert len(dedup.canonical_events) == 0
    assert len(dedup.contradictory_events) == 2
    assert dedup.contradictory_identity_count == 1
    assert len({event.event_id for event in dedup.contradictory_events}) == 2


def test_duplicate_canonical_is_not_an_independent_application():
    load = load_a_command_events(
        DEMO_LOG, provenance="HOST_GENERATED_SYNTHETIC"
    )
    dedup = deduplicate_events(load.events)
    assert dedup.duplicate_canonical_acks == 1
    duplicate_id = next(
        result.command_id
        for result in ack_to_applied(load.events, [])
        if result.state == RESPONSE_DUPLICATE_CANONICAL_NOT_APPLICATION
    )
    result = next(
        result
        for result in ack_to_applied(load.events, [])
        if result.command_id == duplicate_id
    )
    assert result.independent_application is False


def test_non_accepted_acks_are_not_applications():
    load = load_a_command_events(
        DEMO_LOG, provenance="HOST_GENERATED_SYNTHETIC"
    )
    states = {result.command_id: result.state for result in ack_to_applied(load.events, [])}
    assert states["00000000-0000-4000-8000-00000000000c"] == (
        RESPONSE_NOT_APPLICABLE_ACK_NOT_ACCEPTED
    )
    assert states["00000000-0000-4000-8000-00000000000d"] == (
        RESPONSE_NOT_APPLICABLE_ACK_NOT_ACCEPTED
    )


def test_new_command_with_same_action_remains_separate():
    first = _event(
        "ack-a",
        EVENT_DEVICE_ACK,
        1000,
        command_id="CMD-A",
        ack_seq=1,
        fields={"status": "ACCEPTED", "desired_cooling": "ON",
                "desired_duty_permille": "500"},
    )
    second = _event(
        "ack-b",
        EVENT_DEVICE_ACK,
        1100,
        command_id="CMD-B",
        ack_seq=2,
        fields={"status": "ACCEPTED", "desired_cooling": "ON",
                "desired_duty_permille": "500"},
    )
    dedup = deduplicate_events([first, second])
    assert len(dedup.canonical_events) == 2
    assert dedup.new_commands_same_action == 1


def test_reboot_is_not_a_duplicate_proof():
    first = _event(
        "ack-a",
        EVENT_DEVICE_ACK,
        1000,
        boot="boot-a",
        command_id="CMD-X",
        ack_seq=1,
        fields={"status": "ACCEPTED"},
    )
    second = _event(
        "ack-b",
        EVENT_DEVICE_ACK,
        1000,
        boot="boot-b",
        command_id="CMD-X",
        ack_seq=1,
        fields={"status": "ACCEPTED"},
    )
    dedup = deduplicate_events([first, second])
    assert len(dedup.canonical_events) == 2
    assert dedup.reboot_identity_resets == 1
    assert "REBOOT_RESETS_IDENTITY" in dedup.reason_codes


def test_no_command_identity_creates_no_invented_lifecycle():
    events = _real_events()
    assert command_to_ack([], []) == ()
    assert ack_to_applied([], []) == ()
    assert partial_order(events) == ()


def _response_set(events):
    commands = _by_type(events, EVENT_COMMAND_CREATED_OR_PUBLISHED)
    acks = _by_type(events, EVENT_DEVICE_ACK)
    applied = _by_type(events, EVENT_APPLIED_STATE)
    samples = _by_type(events, EVENT_TELEMETRY_SAMPLE)
    responses = list(command_to_ack(commands, acks))
    responses.extend(ack_to_applied(acks, applied))
    for anchor in applied:
        responses.append(
            analyze_response(
                "APPLIED_TO_ELECTRICAL",
                anchor,
                samples,
                DEFAULT_ELECTRICAL_POLICY,
            )
        )
        responses.append(
            analyze_response(
                "APPLIED_TO_THERMAL",
                anchor,
                samples,
                DEFAULT_THERMAL_POLICY,
            )
        )
    return response_summary_csv(tuple(sorted(responses, key=lambda item: (
        item.relationship,
        item.command_id or "",
        item.anchor_event_id or "",
        item.state,
    ))))


def test_reversed_input_order_yields_identical_canonical_report():
    forward = deduplicate_events(_events("qualified-response.json"))
    reversed_ = deduplicate_events(list(reversed(_events("qualified-response.json"))))
    assert event_timeline_csv(forward.canonical_events) == event_timeline_csv(
        reversed_.canonical_events
    )
    assert _response_set(forward.canonical_events) == _response_set(
        reversed_.canonical_events
    )


# ---------------------------------------------------------------------------
# CLI integration and scientific separation
# ---------------------------------------------------------------------------


def test_cli_real_a_c_and_demo_artifacts_are_honest(tmp_path):
    out = tmp_path / "w06"
    result = _run_cli(
        [
            "--source", str(REAL_A_EXPORT),
            "--a-run-index", str(REAL_A_INDEX),
            "--source", str(C_FIXTURE),
            "--a-command-log", str(DEMO_LOG),
            "--a-command-provenance", "HOST_GENERATED_SYNTHETIC",
            "--out", str(out),
            "--repository-revision", "test-revision",
        ]
    )
    assert result.returncode == 0, result.stderr
    for name in (
        "event-timeline-W06.csv",
        "response-summary-W06.csv",
        "timing-audit-W06.md",
        "timing-manifest-W06.json",
    ):
        assert (out / name).is_file(), name
    manifest = json.loads(
        (out / "timing-manifest-W06.json").read_text(encoding="utf-8")
    )
    assert manifest["separation"] == {
        "w06_software_verification": "PASS",
        "real_command_lifecycle_evidence": "ABSENT",
        "physical_data_eligibility": "NOT_READY",
        "real_aiw": "NOT_ESTIMABLE",
    }
    counts = manifest["counts"]
    assert counts["telemetry_events"] == 958
    assert counts["command_events"] == 0
    assert counts["ack_events"] == 5
    assert counts["door_transitions"] == 0
    assert counts["real_measured_response_delays"] == 0
    timeline_rows = list(
        csv.DictReader(
            io.StringIO(
                (out / "event-timeline-W06.csv").read_text(encoding="utf-8")
            )
        )
    )
    response_rows = list(
        csv.DictReader(
            io.StringIO(
                (out / "response-summary-W06.csv").read_text(encoding="utf-8")
            )
        )
    )
    assert len(timeline_rows) == len(manifest["timeline_events"])
    assert len(response_rows) == len(manifest["responses"])
    report = (out / "timing-audit-W06.md").read_text(encoding="utf-8")
    assert "REAL COMMAND-LIFECYCLE EVIDENCE | ABSENT" in report
    assert "PHYSICAL DATA ELIGIBILITY | NOT_READY" in report
    assert "REAL AIW | NOT_ESTIMABLE" in report
    assert "D:\\" not in report
    assert "/home/" not in report


def test_event_timeline_csv_carries_event_fields(tmp_path):
    out = tmp_path / "fields"
    result = _run_cli(
        [
            "--source", str(REAL_A_EXPORT),
            "--a-run-index", str(REAL_A_INDEX),
            "--out", str(out),
            "--repository-revision", "test-revision",
        ]
    )
    assert result.returncode == 0, result.stderr
    rows = list(
        csv.DictReader(
            io.StringIO(
                (out / "event-timeline-W06.csv").read_text(encoding="utf-8")
            )
        )
    )
    applied = [row for row in rows if row["event_type"] == "APPLIED_STATE"]
    assert applied
    applied_fields = json.loads(applied[0]["normalized_fields"])
    assert "applied_from" in applied_fields
    assert "applied_to" in applied_fields
    telemetry = [row for row in rows if row["event_type"] == "TELEMETRY_SAMPLE"]
    assert any(
        "chamber_air_mean_c" in json.loads(row["normalized_fields"])
        for row in telemetry
    )


def test_cli_is_deterministic(tmp_path):
    out = tmp_path / "w06"
    args = [
        "--source", str(REAL_A_EXPORT),
        "--a-run-index", str(REAL_A_INDEX),
        "--a-command-log", str(DEMO_LOG),
        "--a-command-provenance", "HOST_GENERATED_SYNTHETIC",
        "--out", str(out),
        "--repository-revision", "test-revision",
    ]
    assert _run_cli(args).returncode == 0
    first = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in out.iterdir()
    }
    assert _run_cli(args).returncode == 0
    second = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in out.iterdir()
    }
    assert first == second


def test_cli_synthetic_positive_control(tmp_path):
    out = tmp_path / "fixture"
    result = _run_cli(
        [
            "--event-fixture", str(_fixture("qualified-response.json")),
            "--out", str(out),
            "--repository-revision", "test-revision",
        ]
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (out / "timing-manifest-W06.json").read_text(encoding="utf-8")
    )
    assert manifest["counts"]["synthetic_example_delays"] == 6
    assert manifest["counts"]["real_measured_response_delays"] == 0
    assert manifest["separation"]["real_command_lifecycle_evidence"] == "ABSENT"
    assert manifest["separation"]["physical_data_eligibility"] == "NOT_VERIFIED"
    report = (out / "response-summary-W06.csv").read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(report)))
    assert all(row["state"] == "OBSERVED_DIAGNOSTIC_ONLY" for row in rows)
    latencies = {
        row["relationship"]: float(row["latency_s"])
        for row in rows
        if row["latency_s"] not in ("", "NOT_ESTIMABLE")
    }
    assert latencies["COMMAND_TO_ACK"] == pytest.approx(0.2)
    assert latencies["ACK_TO_APPLIED_STATE"] == pytest.approx(0.3)
    assert latencies["COMMAND_TO_ELECTRICAL"] == pytest.approx(0.7)
    assert latencies["COMMAND_TO_THERMAL"] == pytest.approx(0.8)
    assert latencies["APPLIED_TO_ELECTRICAL"] == pytest.approx(0.2)
    assert latencies["APPLIED_TO_THERMAL"] == pytest.approx(0.3)


def test_cli_mixed_clock_fixture_is_not_estimable(tmp_path):
    out = tmp_path / "mixed"
    result = _run_cli(
        [
            "--event-fixture", str(_fixture("mixed-clock.json")),
            "--out", str(out),
            "--repository-revision", "test-revision",
        ]
    )
    assert result.returncode == 0, result.stderr
    summary = (out / "response-summary-W06.csv").read_text(encoding="utf-8")
    assert "NOT_ESTIMABLE_CLOCK" in summary


def test_cli_contradictory_identity_is_reported(tmp_path):
    out = tmp_path / "conflict"
    result = _run_cli(
        [
            "--event-fixture", str(_fixture("contradictory-identity.json")),
            "--out", str(out),
            "--repository-revision", "test-revision",
        ]
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (out / "timing-manifest-W06.json").read_text(encoding="utf-8")
    )
    assert manifest["counts"]["contradictory_identities"] == 2
    assert manifest["counts"]["contradictory_events"] == 4
    assert "CONTRADICTORY_IDENTITY" in manifest["dedup"]["reason_codes"]


def test_cli_refuses_a_bad_command_log(tmp_path):
    bad = tmp_path / "bad.log"
    bad.write_text("#CG CMDACK schema=1 event=ACK\n", encoding="utf-8")
    result = _run_cli(["--a-command-log", str(bad), "--out", str(tmp_path / "out")])
    assert result.returncode == 2
    assert "REFUSED" in result.stderr


def test_cli_c_fixture_has_no_command_linkage(tmp_path):
    out = tmp_path / "c"
    result = _run_cli(
        [
            "--source", str(C_FIXTURE),
            "--out", str(out),
            "--repository-revision", "test-revision",
        ]
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (out / "timing-manifest-W06.json").read_text(encoding="utf-8")
    )
    assert manifest["counts"]["telemetry_events"] == 1
    assert manifest["counts"]["command_events"] == 0
    assert manifest["counts"]["ack_events"] == 0
    assert manifest["sources"][0]["provenance"] == "SYNTHETIC"


def test_w05_qa_outputs_remain_valid_on_w06_branch():
    capture = _real_capture()
    from coldguard_ml import analyze_capture, summarize_qa_suite

    analyses = [analyze_capture(capture)]
    suite = summarize_qa_suite(analyses)
    assert suite.predictive_dataset_readiness == "NOT_READY"
    assert suite.eligible_s1_runs == 0
    assert "physical_admission_status" in channel_summary_csv(analyses)
