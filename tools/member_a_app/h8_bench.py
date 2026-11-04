"""H8 bench readiness: read-only capture and a supervised Stage F probe.

This module is deliberately separate from the 114 canonical acceptance
registry. An H8 result is stored under bench-results/ and is never reported
as a canonical W06 PASS. The supervised probe uses only Stage F (30 s, 20 %)
and never the A-E endurance ladder. The H8 firmware's own gates and host ACK
watchdog remain in control; the app only supplies the operator actions.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any, Sequence

from . import analysis, protocol, protocol_h8
from .device import DeviceLink
from .evidence import SessionStore
from .model import OperatorInterface, now_iso

STAGE_F = "F"
STAGE_F_REPORT = "H8-CHECK"
STAGE_F_SECONDS = 30.0
STAGE_F_CURRENT_MAX_A = 2.5
STAGE_F_HOT_MAX_C = 45.0
DEFAULT_OFF_CURRENT_MAX_A = 0.20


class SilentOperator:
    """Safe headless operator: refuses every physical confirmation."""

    def info(self, title: str, message: str) -> None:
        print(f"[info] {title}: {message}")

    def confirm(self, title: str, message: str) -> bool:
        print(f"[refused] {title}: {message}")
        return False

    def choose(self, title: str, message: str, options: list[str]) -> str | None:
        return None

    def text(self, title: str, message: str, multiline: bool = False) -> str | None:
        return None

    def number(self, title: str, message: str, unit: str = "",
               minimum: float | None = None, maximum: float | None = None) -> float | None:
        return None

    def file(self, title: str, kinds: list[tuple[str, str]] | None = None) -> str | None:
        return None

    def progress(self, message: str, fraction: float | None = None) -> None:
        print(f"[progress] {message}")

    def cancelled(self) -> bool:
        return False


@dataclasses.dataclass
class BenchResult:
    kind: str
    outcome: str
    reason: str
    checks: list[dict[str, Any]]
    measurements: dict[str, Any]
    commands: list[dict[str, Any]]
    started_at: str
    ended_at: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _check(checks: list[dict[str, Any]], name: str, passed: bool,
           detail: str = "", failure_reason: str = "") -> bool:
    checks.append({"name": name, "passed": bool(passed), "detail": detail,
                   "failure_reason": "" if passed else (failure_reason or name)})
    return bool(passed)


def _outcome(checks: Sequence[dict[str, Any]]) -> str:
    return "PASS" if checks and all(item["passed"] for item in checks) else "FAIL"


def _capture(device: DeviceLink, seconds: float, min_frames: int = 5,
             stop_predicate=None, progress=None,
             label: str = "H8 capture") -> tuple[list[protocol.TelemetryFrame], str | None]:
    cursor = 0 if device.is_simulated else device.frame_cursor()
    frames: list[protocol.TelemetryFrame] = []
    started = time.monotonic()
    while True:
        new, cursor = device.frames_since(cursor)
        frames.extend(new)
        if stop_predicate is not None and stop_predicate(frames):
            reason = stop_predicate(frames)
            return frames, str(reason)
        elapsed = time.monotonic() - started
        if elapsed >= seconds:
            break
        if progress is not None:
            progress(f"{label}: {elapsed:.0f}/{seconds:.0f}s frames={len(frames)}",
                     elapsed / seconds if seconds else 1.0)
        time.sleep(min(0.25, max(0.02, seconds - elapsed)))
    new, cursor = device.frames_since(cursor)
    frames.extend(new)
    if len(frames) < min_frames:
        raise RuntimeError(f"INSUFFICIENT_H8_FRAMES frames={len(frames)} required={min_frames}")
    return frames, None


def _summary(frames: Sequence[protocol.TelemetryFrame]) -> dict[str, Any]:
    metrics = analysis.soak_metrics(frames)
    latest = frames[-1] if frames else None
    return {
        **metrics,
        "latest_state": latest.state if latest else None,
        "latest_stage": latest.test_phase if latest else None,
        "latest_pwm_applied": latest.pwm_applied if latest else None,
        "latest_pwm_readback": latest.pwm_readback if latest else None,
        "latest_current_a": latest.current_a if latest else None,
        "latest_hot_side_c": analysis.hot_side(latest) if latest else None,
        "latest_fault_bits": latest.fault_bits if latest else None,
        "latest_door_open": latest.door_open if latest else None,
    }


class H8Bench:
    def __init__(self, device: DeviceLink, store: SessionStore,
                 operator: OperatorInterface):
        self.device = device
        self.store = store
        self.operator = operator

    def _h8_frame(self) -> protocol.TelemetryFrame:
        frame = self.device.latest_frame()
        if frame is None:
            raise RuntimeError("NO_H8_TELEMETRY")
        if not frame.is_h8:
            raise RuntimeError("NOT_H8_IMAGE: this check requires #CG H8S telemetry")
        return frame

    def read_only(self, seconds: float = 60.0) -> dict[str, Any]:
        started = now_iso()
        checks: list[dict[str, Any]] = []
        commands: list[dict[str, Any]] = []
        self.device.set_h8_ack(False)
        try:
            deadline = time.monotonic() + 5.0
            while self.device.latest_frame() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            frame = self._h8_frame()
            _check(checks, "h8_telemetry_present", True, detail=frame.kind)
            frames, stop = _capture(self.device, seconds, min_frames=5,
                                    progress=self.operator.progress,
                                    label="H8 read-only")
            summary = _summary(frames)
            _check(checks, "frames_captured", summary["frames"] >= 5,
                   detail=str(summary["frames"]))
            _check(checks, "fault_field_present", summary.get("fault_bits_complete") is True,
                   failure_reason="H8_FAULT_FIELD_MISSING")
            _check(checks, "no_fault", summary.get("fault_bits_max") == 0,
                   failure_reason="FAULT_DURING_CAPTURE")
            payload = BenchResult(
                kind="h8-read-only",
                outcome=_outcome(checks),
                reason="" if _outcome(checks) == "PASS" else "READ_ONLY_CHECK_FAILED",
                checks=checks,
                measurements=summary,
                commands=commands,
                started_at=started,
                ended_at=now_iso(),
            ).to_dict()
            payload["source"] = "H8_BENCH"
            payload["device_identity"] = self.device.snapshot.identity()
            payload["firmware_kind"] = self.device.snapshot.firmware_kind
            self.store.record_bench_result("h8-read-only", payload)
            return payload
        except Exception as exc:
            payload = BenchResult(
                kind="h8-read-only", outcome="INCOMPLETE", reason=str(exc),
                checks=checks, measurements={}, commands=commands,
                started_at=started, ended_at=now_iso(),
            ).to_dict()
            payload["source"] = "H8_BENCH"
            payload["device_identity"] = self.device.snapshot.identity()
            self.store.record_bench_result("h8-read-only", payload)
            return payload

    def supervised_stage_f(self) -> dict[str, Any]:
        started = now_iso()
        checks: list[dict[str, Any]] = []
        commands: list[dict[str, Any]] = []
        measurements: dict[str, Any] = {}
        reason = ""

        def send(command: bytes, description: str) -> None:
            self.device.send(command, description)
            commands.append({"command": command.decode("ascii", errors="replace").strip(),
                             "description": description, "at": now_iso()})

        def wait_result(prefix: str, timeout: float, cursor: int) -> str | None:
            event = self.device.wait_for_h8_cmd(prefix, timeout, cursor)
            if event is None:
                return None
            result = str(event.kv.get("result", ""))
            commands.append({"result": result, "at": now_iso()})
            return result

        def command_and_result(command: bytes, description: str, prefix: str,
                               timeout: float = 5.0) -> str | None:
            cursor = self.device.event_cursor()
            send(command, description)
            return wait_result(prefix, timeout, cursor)

        self.device.set_h8_ack(False)
        started = False
        try:
            frame = self._h8_frame()
            snapshot = self.device.snapshot
            h8 = snapshot.h8
            test_mode = str(frame.kv.get("test_mode") or h8.get("test_mode") or "")
            supervised = str(frame.kv.get("supervised_bench") or h8.get("supervised_bench")
                             or h8.get("supervised") or "")
            off_approved = str(frame.kv.get("off_current_approved")
                               or h8.get("off_current_approved") or "")
            limits_approved = str(frame.kv.get("limits_operator_approved")
                                  or h8.get("limits_operator_approved") or "")
            limits_enforced = str(frame.kv.get("limits_enforced")
                                  or h8.get("limits_enforced") or "")
            off_limit = _float(frame.kv.get("off_current_limit_a"),
                               _float(h8.get("off_current_limit_a"),
                                      DEFAULT_OFF_CURRENT_MAX_A))
            measurements.update({
                "test_mode": test_mode,
                "supervised_bench": supervised,
                "off_current_approved": off_approved,
                "limits_operator_approved": limits_approved,
                "limits_enforced": limits_enforced,
                "off_current_limit_a": off_limit,
                "starting_state": frame.state,
                "starting_fault_bits": frame.fault_bits,
            })
            if test_mode != "BENCH_ENDURANCE":
                raise RuntimeError(f"H8_NOT_BENCH_ENDURANCE test_mode={test_mode}")
            if supervised not in {"1", "TRUE", "YES"}:
                raise RuntimeError("H8_SUPERVISED_BENCH_NOT_ENABLED")
            if off_approved not in {"1", "TRUE", "YES"}:
                raise RuntimeError("H8_OFF_CURRENT_GATE_NOT_APPROVED")
            if limits_approved not in {"1", "TRUE", "YES"}:
                raise RuntimeError("H8_LIMITS_NOT_APPROVED")
            if limits_enforced not in {"1", "TRUE", "YES"}:
                raise RuntimeError("H8_LIMITS_NOT_ENFORCED")
            if (frame.fault_bits or 0) != 0:
                raise RuntimeError(f"H8_FAULT_PRESENT 0x{frame.fault_bits:08X}")
            if frame.fault_bits is None:
                raise RuntimeError("H8_FAULT_FIELD_MISSING")
            if frame.state not in {"OFF", "COOLDOWN"}:
                raise RuntimeError(f"H8_NOT_OFF state={frame.state}")
            if frame.state == "COOLDOWN":
                self.operator.info("H8 bench", "Waiting for the H8 COOLDOWN to reach OFF.")
                if self.device.wait_for_h8_state("OFF", 90) is None:
                    raise RuntimeError("H8_COOLDOWN_DID_NOT_REACH_OFF")
                frame = self._h8_frame()
            if not frame.electrical_valid() or frame.current_a is None:
                raise RuntimeError("H8_OFF_CURRENT_UNVERIFIED: PZEM has no valid current")
            if frame.current_a > off_limit:
                raise RuntimeError(
                    f"H8_OFF_CURRENT_HIGH current={frame.current_a:.3f}A limit={off_limit:.3f}A")
            _check(checks, "prerequisites_met", True,
                   detail=f"mode={test_mode} off_current={frame.current_a:.3f}A")
            _check(checks, "off_current_within_limit", True,
                   detail=f"{frame.current_a:.3f} <= {off_limit:.3f} A")
            for prompt in (
                    "Fuse installed; TEC branch fused and no loose terminal",
                    "V1 fan is spinning and unobstructed",
                    "Chamber closed; operator present at the PSU and able to remove power",
                    "TEC branch is safe to energize for a 30 s, 20 % Stage F check"):
                if not self.operator.confirm("H8 Stage F precheck", prompt):
                    raise RuntimeError(f"PRECHECK_NOT_CONFIRMED: {prompt}")
            token = snapshot.auth_token
            if not token:
                token = (self.operator.text("H8 token",
                                            "Enter the H8 boot token (1-8 hex).") or "").strip()
            token = protocol_h8.token(token)
            near_low_text = self.operator.choose(
                "H8 door polarity",
                "With the door CLOSED, what is the MC-38 raw level?",
                ["NEAR_LOW (raw 0)", "NEAR_HIGH (raw 1)"])
            if near_low_text is None:
                raise RuntimeError("DOOR_POLARITY_NOT_CONFIRMED")
            near_low = near_low_text.startswith("NEAR_LOW")
            _check(checks, "operator_prechecks", True)

            result = command_and_result(protocol_h8.supervise(token),
                                        "SUPERVISE", "SUPERVISED_")
            if result != "SUPERVISED_AUTHORIZED":
                raise RuntimeError(f"H8_SUPERVISE_REFUSED result={result}")
            _check(checks, "supervise_authorized", True, detail=str(result))

            result = command_and_result(protocol_h8.stage(STAGE_F), "STAGE F", "STAGE_")
            if result != "STAGE_SELECTED":
                raise RuntimeError(f"H8_STAGE_F_REFUSED result={result}")
            _check(checks, "stage_f_selected", True, detail=str(result))

            result = command_and_result(protocol_h8.fan(token), "FAN confirm", "FAN_")
            if result != "FAN_CONFIRMED":
                raise RuntimeError(f"H8_FAN_REFUSED result={result}")
            _check(checks, "fan_confirmed", True, detail=str(result))

            result = command_and_result(protocol_h8.door(near_low, token),
                                        "DOOR polarity", "DOOR_POLARITY_")
            if result != "DOOR_POLARITY_CONFIRMED":
                raise RuntimeError(f"H8_DOOR_REFUSED result={result}")
            _check(checks, "door_polarity_confirmed", True, detail=str(result))

            self.device.set_h8_ack(True)
            ack_before = self.device.snapshot.h8_ack_count
            ack_cursor = self.device.event_cursor()
            latest = self.device.latest_frame()
            if latest is not None:
                ack = protocol_h8.ack_from_frame(latest)
                if ack is None:
                    raise RuntimeError("H8_ACK_FRAME_UNPARSEABLE")
                send(ack, "H8 host ACK (pre-START, latest frame)")
            ack_event = self.device.wait_for_h8_cmd("ACK_ACCEPTED", 3, ack_cursor)
            ack_result = str(ack_event.kv.get("result", "")) if ack_event is not None else None
            if ack_result != "ACK_ACCEPTED":
                raise RuntimeError(f"H8_ACK_NOT_ACCEPTED result={ack_result}")
            _check(checks, "ack_fresh", True, detail=str(ack_result))

            result = command_and_result(protocol_h8.arm(token), "ARM", "ARM")
            if result != "ARMED":
                raise RuntimeError(f"H8_ARM_REFUSED result={result}")
            _check(checks, "armed", True, detail=str(result))

            # Last gate before the only step that energizes the TEC. The
            # prechecks happen before SUPERVISE/ARM; this asks again for the
            # test-specific START so a queued flow cannot energize unattended.
            if not self.operator.confirm(
                    "H8 Stage F START",
                    "All prechecks, SUPERVISE, STAGE F, FAN, DOOR, ACK and ARM "
                    "are complete.\n\nConfirm the test-specific START: energize "
                    "the TEC at 20 % for 30 s now?"):
                try:
                    send(protocol_h8.stop(), "STOP after START not confirmed")
                except Exception:
                    pass
                raise RuntimeError("H8_STAGE_F_START_NOT_CONFIRMED")
            _check(checks, "start_confirmed", True,
                   detail="operator confirmed TEC energization at START")

            result = command_and_result(protocol_h8.start(), "START Stage F", "START_",
                                        timeout=8.0)
            if result not in {"START_OK", "START_OK_SUPERVISED"}:
                # A refusal is a readiness result, not a PASS and not a fault.
                raise H8StartRefused(f"H8_START_REFUSED result={result}")
            started = True
            _check(checks, "start_accepted", True, detail=str(result))

            def abnormal(captured: Sequence[protocol.TelemetryFrame]) -> str | None:
                for item in captured:
                    if (item.fault_bits or 0) != 0:
                        return f"FAULT_BITS=0x{item.fault_bits:08X}"
                    if item.state == "FAULT_LATCH":
                        return "FAULT_LATCH"
                    if item.current_a is not None and item.current_a > STAGE_F_CURRENT_MAX_A:
                        return f"OVERCURRENT={item.current_a:.2f}A"
                    hot = analysis.hot_side(item)
                    if hot is not None and hot > STAGE_F_HOT_MAX_C:
                        return f"HOT_SIDE={hot:.2f}C"
                return None

            frames, safety_reason = _capture(
                self.device, STAGE_F_SECONDS + 5, min_frames=5,
                stop_predicate=abnormal, progress=self.operator.progress,
                label="H8 Stage F")
            measurements.update(_summary(frames))
            measurements["safety_stop_reason"] = safety_reason
            measurements["ack_count"] = self.device.snapshot.h8_ack_count - ack_before
            self.device.set_h8_ack(False)
            if safety_reason:
                _check(checks, "no_safety_stop", False, detail=safety_reason,
                       failure_reason="H8_SAFETY_STOP")
                send(protocol_h8.estop(), "ESTOP after H8 safety stop")
            else:
                _check(checks, "no_safety_stop", True)

            if any(item.state == "COOLING" for item in frames):
                _check(checks, "cooling_observed", True)
            else:
                _check(checks, "cooling_observed", False,
                       failure_reason="H8_NEVER_REACHED_COOLING")
            currents = [item.current_a for item in frames
                        if item.electrical_valid() and item.current_a is not None]
            if currents:
                _check(checks, "current_observed", max(currents) > 0.05,
                       detail=f"max={max(currents):.3f}A",
                       failure_reason="H8_CURRENT_NOT_OBSERVED")
            else:
                _check(checks, "current_observed", False,
                       failure_reason="H8_CURRENT_UNVERIFIED")
            pwm_values = [item.pwm_applied for item in frames if item.pwm_applied is not None]
            if pwm_values:
                # 200 permille maps to 1638/8192 counts, which the firmware
                # itself accepts as one-count quantisation (199.95 permille).
                _check(checks, "pwm_stage_f", abs(max(pwm_values) - 200) <= 1,
                       detail=f"max={max(pwm_values)} (200 +/- 1)",
                       failure_reason="H8_PWM_NOT_200_PERMILLE")
            else:
                _check(checks, "pwm_stage_f", False,
                       failure_reason="H8_PWM_UNVERIFIED")
            _check(checks, "no_fault",
                   all(item.fault_bits is not None and item.fault_bits == 0 for item in frames),
                   failure_reason="H8_FAULT_DURING_STAGE_F")

            if not safety_reason:
                result = command_and_result(protocol_h8.stop(), "STOP", "STOP", timeout=8)
                if result != "STOP":
                    if result is not None:
                        send(protocol_h8.estop(), "ESTOP after STOP refusal")
                    _check(checks, "stop_acknowledged", False, detail=str(result),
                           failure_reason="H8_STOP_NOT_ACKNOWLEDGED")
                else:
                    _check(checks, "stop_acknowledged", True)
                started = False
                if self.device.wait_for_h8_state("OFF", 10) is None:
                    if self.device.wait_for_h8_state("COOLDOWN", 3) is None:
                        _check(checks, "returned_off", False,
                               failure_reason="H8_DID_NOT_RETURN_OFF")
                    else:
                        _check(checks, "returned_off", True, detail="COOLDOWN")
                else:
                    _check(checks, "returned_off", True, detail="OFF")
                final = self.device.latest_frame()
                if final is not None:
                    post_current = final.current_a
                    _check(checks, "post_off_current",
                           post_current is not None and post_current <= off_limit,
                           detail=str(post_current), failure_reason="H8_POST_OFF_CURRENT_HIGH")
                    _check(checks, "post_off_pwm",
                           final.pwm_applied == 0, detail=str(final.pwm_applied),
                           failure_reason="H8_PWM_NOT_ZERO_AFTER_STOP")
            outcome = _outcome(checks)
            payload = BenchResult(
                kind="h8-stage-f",
                outcome=outcome,
                reason="" if outcome == "PASS" else "H8_STAGE_F_CHECK_FAILED",
                checks=checks,
                measurements=measurements,
                commands=commands,
                started_at=started,
                ended_at=now_iso(),
            ).to_dict()
            payload["source"] = "H8_BENCH"
            payload["device_identity"] = self.device.snapshot.identity()
            payload["firmware_kind"] = self.device.snapshot.firmware_kind
            self.store.record_bench_result("h8-stage-f", payload)
            return payload
        except H8StartRefused as exc:
            self.device.set_h8_ack(False)
            try:
                send(protocol_h8.stop(), "STOP after START refusal (disarm)")
            except Exception:
                pass
            _check(checks, "start_accepted", False, detail=str(exc),
                   failure_reason="H8_STAGE_F_NOT_APPROVED_OR_GATE_BLOCKED")
            payload = BenchResult(
                kind="h8-stage-f", outcome="INCOMPLETE", reason=str(exc),
                checks=checks, measurements=measurements, commands=commands,
                started_at=started, ended_at=now_iso(),
            ).to_dict()
            payload["source"] = "H8_BENCH"
            payload["device_identity"] = self.device.snapshot.identity()
            self.store.record_bench_result("h8-stage-f", payload)
            return payload
        except Exception as exc:
            self.device.set_h8_ack(False)
            reason = str(exc)
            outcome = "INCOMPLETE"
            _check(checks, "bench_prerequisite", False, detail=reason,
                   failure_reason="H8_BENCH_PREREQUISITE")
            payload = BenchResult(
                kind="h8-stage-f", outcome=outcome, reason=reason,
                checks=checks, measurements=measurements, commands=commands,
                started_at=started, ended_at=now_iso(),
            ).to_dict()
            payload["source"] = "H8_BENCH"
            payload["device_identity"] = self.device.snapshot.identity()
            self.store.record_bench_result("h8-stage-f", payload)
            return payload
        finally:
            if started:
                try:
                    self.device.send(protocol_h8.stop(), "STOP in bench finally")
                except Exception:
                    pass
            self.device.set_h8_ack(False)


class H8StartRefused(RuntimeError):
    pass


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
