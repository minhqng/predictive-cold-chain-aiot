"""Core result, definition and operator abstractions.

This module has no serial, GUI or filesystem dependency so the test
protocols and the runner can be exercised headlessly.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import enum
from typing import Any, Protocol


class Outcome(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCOMPLETE = "INCOMPLETE"
    NOT_RUN = "NOT_RUN"

    @property
    def rank(self) -> int:
        return {Outcome.PASS: 3, Outcome.FAIL: 2, Outcome.INCOMPLETE: 1, Outcome.NOT_RUN: 0}[self]


class TestMode(str, enum.Enum):
    AUTOMATED = "AUTOMATED"
    GUIDED = "GUIDED"
    DOCUMENTARY = "DOCUMENTARY"
    TEAM_DEPENDENCY = "TEAM_DEPENDENCY"


class SafetyClass(str, enum.Enum):
    NO_POWER = "NO_POWER"
    READ_ONLY = "READ_ONLY"
    POWERED_GUIDED = "POWERED_GUIDED"


@dataclasses.dataclass
class CheckResult:
    name: str
    passed: bool | None
    detail: str = ""
    failure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class TestResult:
    test_id: str
    outcome: Outcome
    started_at: str
    ended_at: str
    checks: list[CheckResult] = dataclasses.field(default_factory=list)
    measurements: dict[str, Any] = dataclasses.field(default_factory=dict)
    evidence: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    failure_reason: str = ""
    notes: str = ""
    operator: str = ""
    device_identity: dict[str, Any] = dataclasses.field(default_factory=dict)
    repetitions: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    source: str = "HARDWARE"

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["outcome"] = self.outcome.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TestResult":
        data = dict(payload)
        data["outcome"] = Outcome(data.get("outcome", "NOT_RUN"))
        data["checks"] = [CheckResult(**item) for item in data.get("checks", [])]
        return cls(**data)


@dataclasses.dataclass(frozen=True)
class TestDefinition:
    test_id: str
    week: int
    title: str
    criterion: str
    mode: TestMode
    safety: SafetyClass
    handler: str
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    prerequisites: tuple[str, ...] = ()
    hardware_prereqs: tuple[str, ...] = ()
    firmware_prereqs: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    duration_s: float | None = None
    repetitions: int = 1
    canonical_source: str = "docs/05A-member-a-embedded-thermal.md"

    @property
    def id(self) -> str:
        return self.test_id


class TestBlocked(Exception):
    """Raised when a prerequisite, hardware state or safety gate is unmet.

    The runner converts this to INCOMPLETE, never to PASS or FAIL, so an
    unexecuted requirement cannot disappear into a green number.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class OperatorInterface(Protocol):
    def info(self, title: str, message: str) -> None: ...

    def confirm(self, title: str, message: str) -> bool: ...

    def choose(self, title: str, message: str, options: list[str]) -> str | None: ...

    def text(self, title: str, message: str, multiline: bool = False) -> str | None: ...

    def number(self, title: str, message: str, unit: str = "", minimum: float | None = None,
               maximum: float | None = None) -> float | None: ...

    def file(self, title: str, kinds: list[tuple[str, str]] | None = None) -> str | None: ...

    def progress(self, message: str, fraction: float | None = None) -> None: ...

    def cancelled(self) -> bool: ...


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")
