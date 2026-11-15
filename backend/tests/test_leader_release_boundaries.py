"""Verify the release-only boot reconciliation and shadow runner boundaries."""
import json

from scripts import leader_door_orchestrator as shadow
from scripts.leader_boot_reconcile import promote_twin
from tests.test_twin import _ingest, _payload, _twin, device_id  # noqa: F401


def test_reconcile_matches_observed_device_and_boot(db_engine, device_id):
    engine = db_engine
    _ingest(engine, _payload(device_id, 1, boot_id="12345678"))
    _ingest(engine, _payload(device_id, 1, boot_id="87654321"))
    live = {"fresh": True, "device": device_id, "telemetry": {"boot_id": "aaaaaaaa"}}
    assert promote_twin(engine, device_id, live)["verdict"] == "BOOT_NOT_INGESTED"
    live["telemetry"]["boot_id"] = "87654321"
    assert promote_twin(engine, device_id, {**live, "fresh": False})["verdict"] == "FRESH_DEVICE_BOOT_REQUIRED"
    assert promote_twin(engine, device_id, {**live, "device": "other"})["verdict"] == "FRESH_DEVICE_BOOT_REQUIRED"
    assert _twin(engine, device_id)["last_boot_id"] == "12345678"
    assert promote_twin(engine, device_id, live)["verdict"] == "PROMOTED"
    assert _twin(engine, device_id)["last_boot_id"] == "87654321"


def test_shadow_proposes_cooling_without_dispatch(monkeypatch, tmp_path):
    event_path = tmp_path / "door-events.jsonl"
    monkeypatch.setattr(shadow, "EVENTS", event_path)
    monkeypatch.setattr(shadow, "SETPOINT_FILE", tmp_path / "no-setpoint.json")
    live = {
        "device": shadow.DEVICE, "fresh": True, "frame_age_s": 1,
        "clock": {"state": "ANCHORED"},
        "door": {"state": "CLOSED", "attested_this_boot": True},
        "telemetry": {
            "boot_id": "12345678", "seq": 99, "t1_c": 26, "t3_c": 26, "t4_c": 26,
            "quality": {"overall": "VALID", "electrical": "VALID"},
            "actuation": {"cooling": "OFF", "duty": 0},
        },
    }
    calls = []

    def read(url):
        calls.append(url)
        return live if url.endswith("/live") else None

    def stop_after_tick(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(shadow, "_get", read)
    monkeypatch.setattr(shadow.time, "sleep", stop_after_tick)
    try:
        shadow.main()
    except KeyboardInterrupt:
        pass
    record = json.loads(event_path.read_text(encoding="utf-8"))
    assert record["source"] == "SHADOW_DECISION"
    assert record["policy_state"] == "CRITICAL_PROTECTION"
    assert record["proposed"] == "ISSUE_ON"
    assert record["applied_cooling"] == "OFF"
    assert record["device_id"] == shadow.DEVICE and record["boot_id"] == "12345678"
    assert len(calls) == 2 and "dispatch" not in record


def test_shadow_consumes_operator_setpoint_as_target(monkeypatch, tmp_path):
    event_path = tmp_path / "door-events.jsonl"
    setpoint_path = tmp_path / "setpoint-desired.json"
    setpoint_path.write_text(json.dumps({"setpoint_c": 20.0, "source": "OPERATOR"}),
                             encoding="utf-8")
    monkeypatch.setattr(shadow, "EVENTS", event_path)
    monkeypatch.setattr(shadow, "SETPOINT_FILE", setpoint_path)
    live = {
        "device": shadow.DEVICE, "fresh": True, "frame_age_s": 1,
        "clock": {"state": "ANCHORED"},
        "door": {"state": "CLOSED", "attested_this_boot": True},
        "telemetry": {
            "boot_id": "12345678", "seq": 99, "t1_c": 26, "t3_c": 26, "t4_c": 26,
            "quality": {"overall": "VALID", "electrical": "VALID"},
            "actuation": {"cooling": "OFF", "duty": 0},
        },
    }

    def read(url):
        return live if url.endswith("/live") else None

    def stop_after_tick(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(shadow, "_get", read)
    monkeypatch.setattr(shadow.time, "sleep", stop_after_tick)
    try:
        shadow.main()
    except KeyboardInterrupt:
        pass
    record = json.loads(event_path.read_text(encoding="utf-8"))
    assert record["source"] == "SHADOW_DECISION"
    # The operator setpoint became the Member D policy target (desired state),
    # and the shadow runner still dispatches nothing.
    assert record["target_c"] == 20.0
    assert record["applied_cooling"] == "OFF"
    assert "dispatch" not in record
