"""Offline evidence and process-exit regressions for the Leader TEC runner."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts import leader_tec200_run as runner

DEVICE = "coldguard-001"
BOOT = "abcd0123"
COMMAND = "00000000-0000-4000-8000-000000000123"
STAMP = datetime(2026, 11, 13, 9, tzinfo=timezone.utc)
RUNTIME_ENV = {
    "DATABASE_URL": "postgresql+psycopg://localhost/coldguard_test",
    "MQTT_HOST": "localhost",
    "MQTT_PORT": "1883",
    "MQTT_INGEST_PASSWORD": "fixture-ingest",
    "MQTT_COMMAND_PASSWORD": "fixture-command",
}


@pytest.mark.parametrize("missing", [None, *RUNTIME_ENV])
def test_runtime_config_requires_process_environment(monkeypatch, missing):
    for name, value in RUNTIME_ENV.items():
        monkeypatch.setenv(name, value)
    if missing:
        monkeypatch.delenv(missing)
        with pytest.raises(runner.UnprovenTrial, match=f"CONFIGURATION_MISSING_{missing}"):
            runner.runtime_config()
        return
    assert runner.runtime_config() == (
        "postgresql://localhost/coldguard_test", "localhost", 1883,
        {"backend-ingest": "fixture-ingest", "backend-command": "fixture-command"},
    )


@pytest.mark.parametrize("port", ["not-a-port", "0", "65536"])
def test_runtime_config_rejects_invalid_mqtt_port(monkeypatch, port):
    for name, value in RUNTIME_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MQTT_PORT", port)
    with pytest.raises(runner.UnprovenTrial, match="MQTT_PORT_INVALID"):
        runner.runtime_config()


def test_runtime_config_refuses_plain_mqtt_to_nonlocal_broker(monkeypatch):
    for name, value in RUNTIME_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MQTT_HOST", "broker.example.invalid")
    with pytest.raises(runner.UnprovenTrial, match="MQTT_HOST_REQUIRES_LOOPBACK"):
        runner.runtime_config()


def frame(second, *, cooling="OFF", current=0, device=DEVICE, boot=BOOT, **overrides):
    seq, uptime = second + 1, 100_000 + second * 1000
    at = STAMP + timedelta(seconds=second)
    duty = 0.2 if cooling == "ON" else 0.0
    fields = {
        "device_id": device, "boot_id": boot, "seq": seq, "uptime_ms": uptime,
        "current_a": "nan" if current is None else current, "current_status": "OK",
        "t_hot_side_c": 24, "t_hot_side_status": "OK", "thermal_age_ms": 50,
        "t_hot_side_src": "T2", "raw_t2_status": "OK",
        "power_age_ms": 0, "power_seq": seq, "output_stage": "ENABLED",
        "fault_code": "0x00000000", "fault_reason": "DURATION_REACHED" if second >= 33 else "NONE",
        "door_open": 0, "door_status": "OK", "cooling_applied_source": "FIRMWARE_OUTPUT_STATE",
        "cooling_applied": cooling, "pwm_duty": int(duty * 1000),
        "tec_state": "COOLING" if cooling == "ON" else "OFF",
        "cooling_evidence": ("MEASURED_APPLIED_AND_DRAWING" if current and cooling == "ON"
                             else "MEASURED_IDLE_AND_ZERO"),
    } | overrides
    return {
        "id": seq, "device_id": device, "boot_id": boot, "seq": seq,
        "ingest_status": "RECEIVED_VALID", "backend_received_at": at,
        "raw_json": {
            "device_id": device, "boot_id": boot, "seq": seq, "uptime_ms": uptime, "replay": False,
            "serial_source": {
                "frame": "#CG TELEM " + " ".join(f"{key}={value}" for key, value in fields.items()),
                "gateway_received_at": at.isoformat(),
            },
            "quality": {"thermal": "VALID", "electrical": "VALID"},
            "door": {"state": "CLOSED"}, "electrical": {"current_a": current},
            "thermal": {"t2": fields["t_hot_side_c"]},
            "actuation": {"cooling": cooling, "duty": duty},
        },
    }


def ack_record(**overrides):
    return {
        "command_id": COMMAND, "topic_device_id": DEVICE, "payload_device_id": DEVICE,
        "boot_id": BOOT, "validity": "VALID", "device_status": "ACCEPTED",
        "backend_received_at": STAMP + timedelta(seconds=1.1),
        "expires_at": STAMP + timedelta(seconds=15), "uptime_ms": 101_100,
        "time_sync_state": "SYNCHRONIZED", "expiry_evaluable": True,
        "reapplied": False, "output_stage": "ENABLED", "fault_code": "0x00000000",
        "applied_cooling": "OFF", "applied_duty": 0.0,
        "raw_payload": json.dumps({"desired": {"cooling": "ON", "duty": 0.2}}),
    } | overrides


def console(event, **overrides):
    arm = event == "ARM"
    return {
        "kind": "tec_console_result", "event": event,
        "device_id": DEVICE, "boot_id": BOOT, "command_id": COMMAND,
        "gateway_session_id": "fixture-session", "ack_uptime_ms": 101_100,
        "preceding_telemetry_uptime_ms": 101_000 if arm else 102_000,
        "result": "ARMED" if arm else "OK", "state": "ARMED" if arm else "COOLING",
        "duty_permille": "0" if arm else "200",
        "remaining_ms": "0" if arm else "30020",
        "ack_observed_at": (STAMP + timedelta(seconds=1.05)).isoformat(),
        "observed_at": (STAMP + timedelta(seconds=1.2 if arm else 2.2)).isoformat(),
    } | overrides


class TrialFixture:
    def __init__(self):
        self.time = 0.1
        self.rows = [frame(second, cooling="ON", current=2) if 3 <= second <= 32
                     else frame(second) for second in range(55)]
        self.ack = ack_record()
        self.events = [(1.2, console("ARM")), (2.2, console("START"))]
        self.logs = []
        self.sent = []
        self.outcome = "puback"
        self.abort = False
        self.stop_error = False

    def now(self):
        return STAMP + timedelta(seconds=self.time)

    def frames(self, after):
        eligible = [r for r in self.rows if r["backend_received_at"] <= self.now()]
        return eligible[-1:] if after is None else [r for r in eligible if r["id"] > after]

    def receive(self):
        if self.abort:
            raise KeyboardInterrupt
        ready = [event for when, event in self.events if when <= self.time]
        self.events = [(when, event) for when, event in self.events if when > self.time]
        return ready

    def submit(self):
        self.sent.append("ON")
        return {"outcome": self.outcome}

    def stop(self):
        self.sent.append("OFF")
        if self.stop_error:
            raise OSError
        return {"outcome": "puback"}

    def run(self):
        code = runner.run_trial(
            DEVICE, BOOT, COMMAND, frames=self.frames,
            ack=lambda: self.ack if self.time >= 1.1 else None,
            receive=self.receive, submit=self.submit, stop=self.stop,
            log=lambda event, detail: self.logs.append((event, detail)),
            now=self.now, clock=lambda: self.time, pause=lambda seconds: self.advance(seconds),
        )
        assert self.logs[-1][0] == "TRIAL_RESULT"
        return code, self.logs[-1][1]["result"]

    def advance(self, seconds):
        self.time += seconds


def test_positive_ordered_evidence_and_final_off_exit_zero():
    trial = TrialFixture()
    assert trial.run() == (0, "TRIAL_PASS")
    assert trial.sent == ["ON", "OFF"]
    assert trial.logs[-1][1]["final_off_confirmed"] is True


@pytest.mark.parametrize(("field", "value", "result"), [
    ("device", "coldguard-other", "WRONG_DEVICE"),
    ("boot", "abcd4567", "BOOT_ID_CHANGED"),
    ("current", None, "ELECTRICAL_INVALID"),
    ("current_status", "INVALID", "ELECTRICAL_INVALID"),
    ("power_age_ms", 3000, "ELECTRICAL_STALE"),
    ("t_hot_side_c", "nan", "THERMAL_INVALID"),
    ("t_hot_side_c", "", "THERMAL_MISSING"),
    ("t_hot_side_status", "STALE", "THERMAL_INVALID"),
    ("thermal_age_ms", 3000, "THERMAL_STALE"),
    ("t_hot_side_src", "T1", "THERMAL_SOURCE_MISMATCH"),
    ("t_hot_side_c", 40, "SAFETY_LIMIT"),
])
def test_precheck_refuses_before_dispatch(field, value, result):
    trial = TrialFixture()
    trial.rows[0] = frame(0, **{field: value})
    assert trial.run() == (1, result)
    assert trial.sent == []


@pytest.mark.parametrize(("change", "result"), [
    ({"command_id": "wrong"}, "ACK_IDENTITY_MISMATCH"),
    ({"boot_id": "abcd4567"}, "ACK_IDENTITY_MISMATCH"),
    ({"payload_device_id": "wrong"}, "ACK_IDENTITY_MISMATCH"),
    ({"backend_received_at": STAMP - timedelta(seconds=1)}, "ACK_STALE"),
    ({"uptime_ms": 99_000}, "ACK_STALE"),
    ({"device_status": "SAFETY_BLOCKED"}, "ACK_REJECTED"),
])
def test_bad_ack_cannot_authorize_evidence(change, result):
    trial = TrialFixture()
    trial.ack = ack_record(**change)
    assert trial.run() == (1, result)
    assert trial.sent == ["ON", "OFF"]


@pytest.mark.parametrize(("case", "result"), [
    ("delivery", "COMMAND_DELIVERY_UNCONFIRMED"),
    ("no-ack", "ACK_MISSING"),
    ("no-arm", "ARM_RESULT_MISSING"),
    ("no-start", "START_RESULT_MISSING"),
    ("arm-refused", "ARM_REJECTED"),
    ("start-refused", "START_REJECTED"),
    ("wrong-session", "START_WITHOUT_ARM"),
    ("wrong-start-anchor", "APPLIED_WITHOUT_START_RESULT"),
    ("no-applied", "APPLIED_TRANSITION_MISSING"),
    ("late-applied", "APPLIED_TRANSITION_LATE"),
    ("no-electrical", "PZEM_CONTRADICTS_APPLIED"),
    ("current-lost", "PZEM_CONTRADICTS_APPLIED"),
    ("no-off", "FINAL_OFF_MISSING"),
    ("no-post-stop-off", "FINAL_OFF_MISSING"),
    ("restart-during-stop", "UNEXPECTED_OUTPUT_AFTER_TRIAL"),
    ("restart-before-zero-current", "UNEXPECTED_RESTART"),
    ("early-stop", "RUN_ENDED_EARLY"),
    ("boot-change", "BOOT_ID_CHANGED"),
    ("abort", "SUPERVISOR_ABORT"),
    ("invalid-current-during-run", "ELECTRICAL_INVALID"),
    ("gap", "TELEMETRY_ORDER_INVALID"),
])
def test_incomplete_trial_exits_nonzero(case, result):
    trial = TrialFixture()
    if case == "delivery":
        trial.outcome = "timeout"
    elif case == "no-ack":
        trial.ack = None
        trial.rows = [frame(n) for n in range(55)]
    elif case == "no-arm":
        trial.events = []
        trial.rows = [frame(n) for n in range(55)]
    elif case == "no-start":
        trial.events = trial.events[:1]
        trial.rows = [frame(n) for n in range(55)]
    elif case == "arm-refused":
        trial.events[0] = (1.2, console("ARM", result="REFUSED", state="OFF"))
    elif case == "start-refused":
        trial.events[1] = (2.2, console("START", result="SENSOR", state="ARMED"))
    elif case == "wrong-session":
        trial.events[1] = (2.2, console("START", gateway_session_id="other-session"))
    elif case == "wrong-start-anchor":
        trial.events[1] = (2.2, console("START", preceding_telemetry_uptime_ms=102_500))
    elif case == "no-applied":
        trial.rows = [frame(n) for n in range(55)]
    elif case == "late-applied":
        trial.rows[3:32] = [frame(n) for n in range(3, 32)]
    elif case == "no-electrical":
        trial.rows[3:33] = [frame(n, cooling="ON") for n in range(3, 33)]
    elif case == "current-lost":
        trial.rows[5] = frame(5, cooling="ON", cooling_evidence="MEASURED_CONTRADICTS_APPLIED")
    elif case == "no-off":
        trial.rows[33:] = [frame(n, cooling="OFF", current=0.1) for n in range(33, 55)]
    elif case == "no-post-stop-off":
        trial.rows = trial.rows[:34]
    elif case == "restart-during-stop":
        trial.rows[34] = frame(34, cooling="ON", current=2)
    elif case == "restart-before-zero-current":
        trial.rows[33] = frame(33, current=0.1)
        trial.rows[34] = frame(34, cooling="ON", current=2)
    elif case == "early-stop":
        trial.rows[4] = frame(4, fault_reason="DURATION_REACHED")
    elif case == "boot-change":
        trial.rows[3] = frame(3, boot="abcd4321")
    elif case == "abort":
        trial.abort = True
    elif case == "invalid-current-during-run":
        trial.rows[4] = frame(4, cooling="ON", current=None)
    elif case == "gap":
        del trial.rows[4]
    assert trial.run() == (1, result)
    assert trial.sent == ["ON", "OFF"]


def test_duplicate_identical_frame_does_not_extend_freshness():
    trial = TrialFixture()
    replay = deepcopy(trial.rows[2])
    replay["id"] += 1
    replay["backend_received_at"] += timedelta(milliseconds=100)
    for row in trial.rows[3:]:
        row["id"] += 1
    trial.rows.insert(3, replay)
    assert trial.run() == (0, "TRIAL_PASS")


def test_cli_without_approval_cannot_open_live_resources(monkeypatch):
    monkeypatch.setattr(runner, "runtime_config", lambda: pytest.fail("live path reached"))
    with pytest.raises(SystemExit) as err:
        runner.main(["--device-id", DEVICE, "--expected-boot", BOOT, "--command-id", COMMAND])
    assert err.value.code == 2
