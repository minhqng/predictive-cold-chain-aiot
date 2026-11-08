"""Test execution engine and the context handed to each protocol.

The engine owns prerequisite gating, result classification and persistence.
A handler only gathers measurements and asserts named checks; it cannot
write PASS for a simulated session or for a test that executed no check.
"""

from __future__ import annotations

import dataclasses
import math
import queue
import time
from typing import Any, Callable, Iterable, Sequence

from . import analysis, protocol
from .device import DeviceLink
from .evidence import SessionStore
from .model import (
    CheckResult,
    OperatorInterface,
    Outcome,
    SafetyClass,
    TestBlocked,
    TestDefinition,
    TestMode,
    TestResult,
    now_iso,
)


class AutoOperator:
    """Scripted operator for headless tests and unattended logic checks."""

    def __init__(self, answers: dict[str, list[Any]] | None = None):
        self.answers = {key: list(values) for key, values in (answers or {}).items()}
        self.log: list[str] = []
        self._cancelled = False

    def _pop(self, kind: str, default: Any) -> Any:
        values = self.answers.get(kind)
        if not values:
            return default
        return values.pop(0)

    def info(self, title: str, message: str) -> None:
        self.log.append(f"INFO {title}: {message}")

    def confirm(self, title: str, message: str) -> bool:
        return bool(self._pop("confirm", True))

    def choose(self, title: str, message: str, options: list[str]) -> str | None:
        value = self._pop("choose", options[0] if options else None)
        return value if value in options else None

    def text(self, title: str, message: str, multiline: bool = False) -> str | None:
        return self._pop("text", "auto")

    def number(self, title: str, message: str, unit: str = "",
               minimum: float | None = None,
               maximum: float | None = None) -> float | None:
        value = self._pop("number", minimum if minimum is not None else 0.0)
        return float(value) if value is not None else None

    def file(self, title: str, kinds: list[tuple[str, str]] | None = None) -> str | None:
        return self._pop("file", None)

    def progress(self, message: str, fraction: float | None = None) -> None:
        self.log.append(f"PROGRESS {message} {fraction if fraction is not None else ''}".strip())

    def cancelled(self) -> bool:
        return self._cancelled


class TestContext:
    def __init__(self, definition: TestDefinition, store: SessionStore,
                 device: DeviceLink | None, operator: OperatorInterface,
                 config: dict[str, Any] | None = None):
        self.definition = definition
        self.store = store
        self.device = device
        self.operator = operator
        self.config = dict(config or {})
        self.checks: list[CheckResult] = []
        self.measurements: dict[str, Any] = {}
        self.evidence: list[dict[str, Any]] = []
        self.notes: str = ""
        self.repetitions: list[dict[str, Any]] = []
        self.source = self._default_source()
        self.started_at = now_iso()
        self._cancelled = False
        self._measurement_record: dict[str, Any] | None = None

    def _default_source(self) -> str:
        if self.definition.mode is TestMode.DOCUMENTARY:
            return "DOCUMENTARY"
        if self.definition.mode is TestMode.TEAM_DEPENDENCY:
            return "TEAM_EVIDENCE"
        if self.device is not None and self.device.is_simulated:
            return "SIMULATED"
        return "HARDWARE"

    @property
    def is_simulated(self) -> bool:
        return self.device is None or self.device.is_simulated

    def check(self, name: str, passed: bool, detail: str = "", failure_reason: str = "") -> bool:
        self.checks.append(CheckResult(name=name, passed=bool(passed), detail=detail,
                                       failure_reason=failure_reason))
        return bool(passed)

    def check_closed(self, name: str, value: float | None, minimum: float | None = None,
                     maximum: float | None = None, detail: str = "") -> bool:
        if value is None:
            return self.check(name, False, detail=detail, failure_reason="MEASUREMENT_MISSING")
        if minimum is not None and value < minimum:
            return self.check(name, False, detail=f"{value} < {minimum} {detail}",
                              failure_reason=f"{name}_BELOW_MINIMUM")
        if maximum is not None and value > maximum:
            return self.check(name, False, detail=f"{value} > {maximum} {detail}",
                              failure_reason=f"{name}_ABOVE_MAXIMUM")
        return self.check(name, True, detail=detail or f"{value}")

    def block(self, reason: str) -> None:
        raise TestBlocked(reason)

    def progress(self, message: str, fraction: float | None = None) -> None:
        self.operator.progress(f"{self.definition.test_id}: {message}", fraction)

    def ask_confirm(self, message: str) -> bool:
        return self.operator.confirm(self.definition.test_id, message)

    def ask_choice(self, message: str, options: list[str]) -> str:
        value = self.operator.choose(self.definition.test_id, message, options)
        if value is None:
            raise TestBlocked("OPERATOR_CANCELLED")
        return value

    def ask_text(self, message: str, multiline: bool = False) -> str:
        value = self.operator.text(self.definition.test_id, message, multiline)
        if value is None:
            raise TestBlocked("OPERATOR_CANCELLED")
        return value

    def ask_number(self, message: str, unit: str = "", minimum: float | None = None,
                   maximum: float | None = None) -> float:
        value = self.operator.number(self.definition.test_id, message, unit, minimum, maximum)
        if value is None:
            raise TestBlocked("OPERATOR_CANCELLED")
        return value

    def ask_file(self, message: str, kinds: list[tuple[str, str]] | None = None) -> str | None:
        return self.operator.file(self.definition.test_id, kinds)

    def attach(self, path: str | None) -> dict[str, Any] | None:
        if not path:
            return None
        record = self.store.attach(self.definition.test_id, path)
        self.evidence.append(record)
        return record

    def imported_files(self) -> list[dict[str, Any]]:
        return self.store.imported_for(self.definition.test_id)

    def imported_first(self, suffix: str | None = None) -> dict[str, Any] | None:
        for record in self.imported_files():
            stored = str(record.get("stored", ""))
            if suffix is None or stored.lower().endswith(suffix.lower()):
                return record
        return None

    def imported_path(self, record: dict[str, Any]) -> str:
        return str(self.store.root / record["stored"])

    def require_attachment(self, message: str, minimum: int = 1,
                           kinds: list[tuple[str, str]] | None = None) -> int:
        imported = self.imported_files()
        for record in imported:
            if record not in self.evidence:
                self.evidence.append(record)
        attached = len(imported)
        maximum = max(1, minimum)
        for index in range(attached, maximum):
            path = self.ask_file(f"{message} (evidence {index + 1}/{maximum})", kinds)
            if path is None:
                break
            if self.attach(path) is not None:
                attached += 1
        self.check("evidence_attached", attached >= minimum,
                   detail=f"{attached}/{minimum} files (imported={len(imported)})",
                   failure_reason="REQUIRED_EVIDENCE_MISSING")
        return attached

    def require_live_device(self) -> DeviceLink:
        if self.device is None or not self.device.snapshot.connected:
            self.block("NO_DEVICE_CONNECTED")
        assert self.device is not None
        return self.device

    def latest_frame(self) -> protocol.TelemetryFrame:
        device = self.require_live_device()
        frame = device.latest_frame()
        if frame is None:
            self.block("NO_TELEMETRY_YET")
        return frame

    def capture(self, duration_s: float, min_frames: int = 1,
                stop_predicate: Callable[[Sequence[protocol.TelemetryFrame]], bool] | None = None,
                label: str = "") -> list[protocol.TelemetryFrame]:
        device = self.require_live_device()
        requested = float(duration_s)
        if not math.isfinite(requested) or requested <= 0.0:
            raise TestBlocked(f"CAPTURE_DURATION_INVALID requested={requested}")
        # A real capture is bounded here, not left to a caller's duration
        # value. A-W05-03 requires 1800 s; 1900 s leaves setup margin while
        # still refusing unbounded/absurd windows.
        hard_limit = float(self.config.get("max_capture_s", 1900.0))
        if requested > hard_limit:
            raise TestBlocked(
                f"CAPTURE_DURATION_EXCEEDS_LIMIT requested={requested:.0f}s "
                f"max={hard_limit:.0f}s")
        scale = 1.0
        cursor = device.frame_cursor()
        if device.is_simulated and self.config.get("fast_simulation", True):
            scale = 0.0
            cursor = 0
        duration = requested * scale
        frames: list[protocol.TelemetryFrame] = []
        started = time.monotonic()
        while True:
            new_frames, cursor = device.frames_since(cursor)
            frames.extend(new_frames)
            if stop_predicate is not None and stop_predicate(frames):
                break
            elapsed = time.monotonic() - started
            if elapsed >= duration:
                break
            if self.operator.cancelled():
                raise TestBlocked("OPERATOR_CANCELLED")
            self.progress(f"{label or 'capturing'}: {elapsed:.0f}/{duration:.0f}s "
                          f"frames={len(frames)}", elapsed / duration if duration else 1.0)
            time.sleep(min(0.25, max(0.02, duration - elapsed)))
        new_frames, cursor = device.frames_since(cursor)
        frames.extend(new_frames)
        if len(frames) < min_frames:
            raise TestBlocked(f"INSUFFICIENT_TELEMETRY frames={len(frames)} required={min_frames}")
        return frames

    def wait_for_frame(self, predicate: Callable[[protocol.TelemetryFrame], bool],
                       timeout_s: float) -> protocol.TelemetryFrame:
        device = self.require_live_device()
        if device.is_simulated and self.config.get("fast_simulation", True):
            frame = device.latest_frame()
            if frame is not None and predicate(frame):
                return frame
            self.block("SIMULATED_FRAME_NOT_PRESENT")
        frame = device.wait_for_frame(predicate, timeout_s)
        if frame is None:
            self.block(f"TELEMETRY_TIMEOUT {timeout_s:.0f}s")
        return frame

    def wait_for_event(self, predicate: Callable[[protocol.ParsedLine], bool],
                       timeout_s: float, cursor: int | None = None) -> protocol.ParsedLine:
        device = self.require_live_device()
        event = device.wait_for_event(predicate, timeout_s, cursor)
        if event is None:
            self.block(f"DEVICE_EVENT_TIMEOUT {timeout_s:.0f}s")
        return event

    def send(self, command: bytes, description: str = "") -> None:
        device = self.require_live_device()
        device.send(command, description)

    def result_of(self, test_id: str) -> TestResult | None:
        return self.store.result(test_id)

    def require_result(self, test_id: str) -> TestResult:
        result = self.store.result(test_id)
        if result is None:
            self.block(f"PREREQUISITE_NOT_RUN {test_id}")
        if result.outcome is not Outcome.PASS:
            self.block(f"PREREQUISITE_{result.outcome.value} {test_id}: {result.failure_reason}")
        return result

    def save_measurements(self) -> None:
        if not self.measurements:
            return
        payload = {
            "test_id": self.definition.test_id,
            "captured_at": now_iso(),
            "measurements": self.measurements,
            "repetitions": self.repetitions,
            "source": self.source,
        }
        if self._measurement_record is None:
            self._measurement_record = self.store.save_measurements(
                self.definition.test_id, payload)
            self.evidence.append(self._measurement_record)
        else:
            self.store.update_measurements(self._measurement_record, payload)


PROFILE_INDEPENDENT_HANDLERS = frozenset({
    "documentary", "numeric", "bom_csv", "photo_inventory", "token_scan",
    "max3485", "fuse", "fuse_final", "decision", "team_evidence", "composite",
    "evidence_audit", "handover", "evidence_gap_list", "rerun_evidence",
    "invalidation_log", "protocol_freeze", "rehearsal", "campaign_manifest",
    "pzem_reference", "dataset_support", "derived", "polarity", "unsupported",
})


class TestRunner:
    def __init__(self, store: SessionStore, device: DeviceLink | None,
                 operator: OperatorInterface, definitions: Iterable[TestDefinition],
                 config: dict[str, Any] | None = None):
        self.store = store
        self.device = device
        self.operator = operator
        self.definitions = {item.test_id: item for item in definitions}
        self.config = dict(config or {})
        if store.config("critical_tmin_c") is not None:
            self.config.setdefault("critical_tmin_c", store.config("critical_tmin_c"))
        if store.config("critical_tmax_c") is not None:
            self.config.setdefault("critical_tmax_c", store.config("critical_tmax_c"))

    def run(self, test_id: str, force: bool = False) -> TestResult:
        definition = self.definitions.get(test_id)
        if definition is None:
            raise KeyError(f"unknown canonical test id {test_id}")
        previous = self.store.result(test_id)
        if previous is not None and previous.outcome is Outcome.PASS and not force:
            return previous

        blocked = self._prerequisite_block(definition)
        if blocked is not None:
            return self._record_incomplete(definition, blocked)

        context = TestContext(definition, self.store, self.device, self.operator, self.config)
        outcome = Outcome.PASS
        failure_reason = ""
        try:
            from . import evaluators
            handler = evaluators.HANDLERS.get(definition.handler)
            if handler is None:
                raise RuntimeError(f"no handler named {definition.handler}")
            handler(context)
        except TestBlocked as exc:
            outcome = Outcome.INCOMPLETE
            failure_reason = exc.reason
        except Exception as exc:  # an application defect must be visible, not green
            outcome = Outcome.FAIL
            failure_reason = f"HANDLER_ERROR: {type(exc).__name__}: {exc}"

        if outcome is Outcome.PASS:
            failed = [item for item in context.checks if item.passed is False]
            if failed:
                outcome = Outcome.FAIL
                failure_reason = failed[0].failure_reason or failed[0].name
            elif not context.checks:
                outcome = Outcome.FAIL
                failure_reason = "NO_CHECKS_EXECUTED"
        if outcome is Outcome.PASS and self._is_simulated(context):
            outcome = Outcome.INCOMPLETE
            failure_reason = "SIMULATED_SESSION: physical acceptance requires real hardware"

        result = TestResult(
            test_id=test_id,
            outcome=outcome,
            started_at=context.started_at,
            ended_at=now_iso(),
            checks=context.checks,
            measurements=context.measurements,
            evidence=context.evidence,
            failure_reason=failure_reason,
            notes=context.notes,
            operator=self.store.operator,
            device_identity=self._identity(),
            repetitions=context.repetitions,
            source=context.source,
        )
        self.store.record_result(result)
        self.operator.progress(f"{test_id} {outcome.value}"
                               + (f": {failure_reason}" if failure_reason else ""), 1.0)
        return result

    def _is_simulated(self, context: TestContext) -> bool:
        if context.source in {"DOCUMENTARY", "OPERATOR_MEASUREMENT",
                              "TEAM_EVIDENCE", "DERIVED"}:
            return False
        return context.device is None or context.device.is_simulated

    def _identity(self) -> dict[str, Any]:
        if self.device is None:
            return {}
        return self.device.snapshot.identity()

    def _prerequisite_block(self, definition: TestDefinition) -> str | None:
        for prerequisite in definition.prerequisites:
            result = self.store.result(prerequisite)
            if result is None:
                return f"PREREQUISITE_NOT_RUN {prerequisite}"
            if result.outcome is not Outcome.PASS:
                return f"PREREQUISITE_{result.outcome.value} {prerequisite}: {result.failure_reason}"
        if self.device is not None and definition.handler not in PROFILE_INDEPENDENT_HANDLERS:
            frame = self.device.latest_frame()
            if frame is not None and frame.is_h8:
                return ("H8_BENCH_IMAGE: canonical W06 telemetry/command fields are absent; "
                        "use the H8 read-only/bench profile; this canonical requirement is "
                        "INCOMPLETE, not PASS")
        return None

    def _record_incomplete(self, definition: TestDefinition, reason: str) -> TestResult:
        result = TestResult(
            test_id=definition.test_id,
            outcome=Outcome.INCOMPLETE,
            started_at=now_iso(),
            ended_at=now_iso(),
            failure_reason=reason,
            operator=self.store.operator,
            device_identity=self._identity(),
            source="SIMULATED" if self.device is not None and self.device.is_simulated else "HARDWARE",
        )
        self.store.record_result(result)
        return result

    def run_group(self, week: int, force: bool = False) -> list[TestResult]:
        return [self.run(item.test_id, force=force)
                for item in sorted(self.definitions.values(), key=lambda value: value.test_id)
                if item.week == week]

    def run_all(self, eligible_only: bool = True, force: bool = False) -> list[TestResult]:
        out: list[TestResult] = []
        for definition in sorted(self.definitions.values(), key=lambda value: value.test_id):
            previous = self.store.result(definition.test_id)
            if previous is not None and previous.outcome is Outcome.PASS and not force:
                continue
            if eligible_only and self._prerequisite_block(definition) is not None:
                out.append(self._record_incomplete(definition,
                                                   self._prerequisite_block(definition) or ""))
                continue
            out.append(self.run(definition.test_id, force=force))
        return out
