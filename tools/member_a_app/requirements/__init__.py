"""Registry of all 114 canonical Member A requirements."""

from __future__ import annotations

from ..model import TestDefinition
from . import w01_w06, w07_w12, w13_w18, w19_w24

EXPECTED_IDS: tuple[str, ...] = tuple(
    f"A-W{week:02d}-{index:02d}"
    for week, count in (
        (1, 5), (2, 7), (3, 7), (4, 7), (5, 5), (6, 6),
        (7, 5), (8, 5), (9, 4), (10, 5), (11, 4), (12, 5),
        (13, 4), (14, 4), (15, 4), (16, 4), (17, 4), (18, 5),
        (19, 4), (20, 4), (21, 4), (22, 3), (23, 5), (24, 4),
    )
    for index in range(1, count + 1)
)

DEFINITIONS: tuple[TestDefinition, ...] = tuple(
    w01_w06.DEFINITIONS + w07_w12.DEFINITIONS + w13_w18.DEFINITIONS
    + w19_w24.DEFINITIONS
)

_BY_ID = {definition.test_id: definition for definition in DEFINITIONS}


def get(test_id: str) -> TestDefinition | None:
    return _BY_ID.get(test_id)


def by_week(week: int) -> list[TestDefinition]:
    return [definition for definition in DEFINITIONS if definition.week == week]


def validate() -> list[str]:
    from .. import evaluators

    errors: list[str] = []
    ids = [definition.test_id for definition in DEFINITIONS]
    if len(ids) != 114:
        errors.append(f"expected 114 definitions, found {len(ids)}")
    if len(set(ids)) != len(ids):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        errors.append(f"duplicate ids: {duplicates}")
    missing = sorted(set(EXPECTED_IDS) - set(ids))
    extra = sorted(set(ids) - set(EXPECTED_IDS))
    if missing:
        errors.append(f"missing canonical ids: {missing}")
    if extra:
        errors.append(f"non-canonical ids: {extra}")
    for definition in DEFINITIONS:
        if not definition.title.strip():
            errors.append(f"{definition.test_id}: empty title")
        if len(definition.criterion.strip()) < 20:
            errors.append(f"{definition.test_id}: criterion too short")
        if definition.handler not in evaluators.HANDLERS:
            errors.append(f"{definition.test_id}: unknown handler {definition.handler!r}")
        if not definition.checks:
            errors.append(f"{definition.test_id}: no checks declared")
        if not definition.evidence:
            errors.append(f"{definition.test_id}: no evidence declared")
        if definition.handler == "unsupported" and not definition.params.get("reason"):
            errors.append(f"{definition.test_id}: unsupported handler without a reason")
    return errors
