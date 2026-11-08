"""Registry coverage against the canonical playbook."""

from __future__ import annotations

import pathlib
import re
import unittest

from .helpers import TOOLS

from member_a_app.model import SafetyClass
from member_a_app.requirements import DEFINITIONS, EXPECTED_IDS, by_week, get, validate

REPO_ROOT = TOOLS.parent
DOC = REPO_ROOT / "docs" / "05A-member-a-embedded-thermal.md"


class RegistryCoverageTests(unittest.TestCase):
    def test_validate_has_no_errors(self) -> None:
        self.assertEqual(validate(), [])

    def test_exactly_114_definitions(self) -> None:
        self.assertEqual(len(DEFINITIONS), 114)
        self.assertEqual(len({item.test_id for item in DEFINITIONS}), 114)

    def test_ids_match_canonical_document(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        canonical = set(re.findall(r"\bA-W\d{2}-\d{2}\b", text))
        registry = {item.test_id for item in DEFINITIONS}
        self.assertEqual(len(canonical), 114)
        self.assertEqual(registry, canonical)
        self.assertEqual(set(EXPECTED_IDS), canonical)

    def test_week_matches_id(self) -> None:
        for definition in DEFINITIONS:
            self.assertEqual(definition.week, int(definition.test_id[3:5]),
                             definition.test_id)
        for week in range(1, 25):
            self.assertTrue(by_week(week), f"week {week} has no requirements")

    def test_every_definition_has_executable_contract(self) -> None:
        for definition in DEFINITIONS:
            with self.subTest(test_id=definition.test_id):
                self.assertTrue(definition.title)
                self.assertGreaterEqual(len(definition.criterion), 20)
                self.assertTrue(definition.checks)
                self.assertTrue(definition.evidence)
                self.assertIsNotNone(get(definition.test_id))

    def test_powered_handlers_can_block_or_gate(self) -> None:
        allowed = {
            "actuation_trace", "run_series", "recharacterization", "polarity",
            "fuse_final", "team_evidence", "decision", "composite", "hil_smoke",
            "s4_method", "s4_refusal", "soak", "reset_series", "degraded_sensor",
            "degraded_pzem", "derived", "unsupported",
        }
        for definition in DEFINITIONS:
            if definition.safety is SafetyClass.POWERED_GUIDED:
                self.assertIn(definition.handler, allowed, definition.test_id)

    def test_no_definition_is_pass_only(self) -> None:
        for definition in DEFINITIONS:
            self.assertGreaterEqual(len(definition.checks), 1, definition.test_id)

    def test_known_genuinely_unsupported_tests_are_explained(self) -> None:
        unsupported = [item for item in DEFINITIONS if item.handler == "unsupported"]
        self.assertTrue(unsupported)
        for definition in unsupported:
            self.assertIn("UNAVAILABLE", definition.params.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
