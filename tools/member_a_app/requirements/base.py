"""Small constructor used by the four week modules."""

from __future__ import annotations

from typing import Any

from ..model import SafetyClass, TestDefinition, TestMode


def T(test_id: str, week: int, title: str, criterion: str,
      mode: TestMode, safety: SafetyClass, handler: str, *,
      params: dict[str, Any] | None = None,
      prereq: tuple[str, ...] = (),
      hw: tuple[str, ...] = (),
      fw: tuple[str, ...] = (),
      actions: tuple[str, ...] = (),
      checks: tuple[str, ...] = (),
      evidence: tuple[str, ...] = (),
      duration: float | None = None,
      reps: int = 1) -> TestDefinition:
    return TestDefinition(
        test_id=test_id, week=week, title=title, criterion=criterion,
        mode=mode, safety=safety, handler=handler, params=dict(params or {}),
        prerequisites=prereq, hardware_prereqs=hw, firmware_prereqs=fw,
        actions=actions, checks=checks, evidence=evidence,
        duration_s=duration, repetitions=reps,
    )


AUTOMATED = TestMode.AUTOMATED
GUIDED = TestMode.GUIDED
DOCUMENTARY = TestMode.DOCUMENTARY
TEAM = TestMode.TEAM_DEPENDENCY

NO_POWER = SafetyClass.NO_POWER
READ_ONLY = SafetyClass.READ_ONLY
POWERED = SafetyClass.POWERED_GUIDED

CANONICAL_FW = ("canonical W05/W06 firmware with #CG TELEM schema 3 and the console grammar",)
BENCH = ("assembled CG-HW-001 bench with 12 V PSU, fused TEC branch, PZEM and IBT-2",)
