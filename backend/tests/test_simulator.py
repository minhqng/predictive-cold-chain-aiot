"""Synthetic device builder behavior (C-W02-02).

Defects detected: a simulator payload that fails the frozen wire
contracts, nondeterministic output for identical inputs (unrepeatable
proof runs), sequence/boot identity collisions, legacy dual-channel
fields leaking back, command publishing from the device path, or QoS /
retain policy drifting from Doc 02 section 7.
"""

import json

import pytest

from coldguard_backend.contracts import Telemetry
from coldguard_backend.simulator import (
    build_event,
    build_health,
    build_state,
    build_telemetry,
    qos_retain_for,
    run_simulation,
    topic_for,
)

BOOT = "boot-sim-test-001"
RUN = "CG-W02-TEST-001"


def test_telemetry_builder_satisfies_wire_contracts():
    payload = build_telemetry(boot_id=BOOT, seq=7, run_id=RUN)
    telemetry = Telemetry.model_validate(payload)
    assert telemetry.message_identity == ("coldguard-001", BOOT, 7)
    assert telemetry.run_id == RUN


def test_telemetry_builder_is_deterministic():
    first = build_telemetry(boot_id=BOOT, seq=42, run_id=RUN)
    second = build_telemetry(boot_id=BOOT, seq=42, run_id=RUN)
    assert first == second


def test_telemetry_builder_distinguishes_sequences():
    first = build_telemetry(boot_id=BOOT, seq=1, run_id=RUN)
    second = build_telemetry(boot_id=BOOT, seq=2, run_id=RUN)
    assert first != second
    assert Telemetry.model_validate(first).message_identity != Telemetry.model_validate(
        second
    ).message_identity


def test_telemetry_builder_marks_synthetic_provenance():
    payload = build_telemetry(boot_id=BOOT, seq=1, run_id=RUN)
    assert payload["synthetic"] is True


def test_telemetry_builder_has_no_legacy_fields():
    raw = json.dumps(build_telemetry(boot_id=BOOT, seq=1, run_id=RUN))
    for legacy in ("current_1", "current_2", "power_1", "power_2", "cmd_1", "cmd_2"):
        assert legacy not in raw


def test_topic_namespace_matches_canonical_contract():
    assert topic_for("coldguard-001", "telemetry") == "coldguard/coldguard-001/telemetry"
    assert topic_for("coldguard-001", "event") == "coldguard/coldguard-001/event"
    assert topic_for("coldguard-001", "state") == "coldguard/coldguard-001/state"
    assert topic_for("coldguard-001", "health") == "coldguard/coldguard-001/health"


def test_topic_for_rejects_unknown_family():
    with pytest.raises(ValueError, match="unknown device topic family"):
        topic_for("coldguard-001", "command")


def test_qos_retain_policy_matches_doc02():
    assert qos_retain_for("telemetry") == (1, False)
    assert qos_retain_for("event") == (1, False)
    assert qos_retain_for("state") == (1, True)
    assert qos_retain_for("health") == (1, True)


def test_qos_retain_for_rejects_command_publishing():
    # The device must never publish commands; no policy exists for it.
    with pytest.raises(ValueError, match="no publisher policy"):
        qos_retain_for("command")


def test_companion_builders_carry_run_provenance():
    event = build_event(boot_id=BOOT, seq=0, run_id=RUN)
    state = build_state(boot_id=BOOT, seq=1, run_id=RUN)
    health = build_health(boot_id=BOOT, seq=1)
    assert event["run_id"] == RUN and event["boot_id"] == BOOT
    assert state["run_id"] == RUN and state["boot_id"] == BOOT
    assert health["boot_id"] == BOOT and health["status"] == "ONLINE"


def test_run_simulation_rejects_empty_run_without_broker():
    with pytest.raises(ValueError, match="count must be"):
        run_simulation(
            host="localhost",
            port=1883,
            username="x",
            password="y",
            boot_id=BOOT,
            run_id=RUN,
            count=0,
        )
