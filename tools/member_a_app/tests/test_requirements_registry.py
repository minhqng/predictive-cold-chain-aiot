"""Tests for the canonical Member A requirement registry.

The registry publishes the 114 canonical TestDefinitions (criteria, modes,
safety classes, checks and evidence) against the shared acceptance core
(model.py). It is the source of truth the evaluators consume.

The full ``requirements.validate()`` handler cross-check imports the evaluator
module, which is published in the next infrastructure PR in the chain; these
tests therefore assert the registry's structure and canonical identity directly
without importing evaluators.
"""

from __future__ import annotations

import unittest

from member_a_app import requirements as registry
from member_a_app.model import SafetyClass, TestDefinition, TestMode


class TestRegistryIdentity(unittest.TestCase):
    def test_exactly_114_unique_canonical_definitions(self):
        ids = [d.test_id for d in registry.DEFINITIONS]
        self.assertEqual(len(ids), 114)
        self.assertEqual(len(set(ids)), 114, "duplicate requirement ids")
        self.assertEqual(set(ids), set(registry.EXPECTED_IDS))
        self.assertEqual(sorted(set(registry.EXPECTED_IDS) - set(ids)), [])
        self.assertEqual(sorted(set(ids) - set(registry.EXPECTED_IDS)), [])

    def test_every_definition_is_a_test_definition(self):
        for d in registry.DEFINITIONS:
            self.assertIsInstance(d, TestDefinition)
            self.assertIsInstance(d.mode, TestMode)
            self.assertIsInstance(d.safety, SafetyClass)

    def test_get_and_by_week(self):
        self.assertIsNone(registry.get("A-W99-99"))
        w23 = [d.test_id for d in registry.by_week(23)]
        self.assertEqual(w23, [f"A-W23-{i:02d}" for i in range(1, 6)])
        self.assertEqual(registry.get("A-W23-03").week, 23)


class TestRegistryStructure(unittest.TestCase):
    def test_structural_invariants(self):
        for d in registry.DEFINITIONS:
            self.assertTrue(d.title.strip(), f"{d.test_id}: empty title")
            self.assertGreaterEqual(len(d.criterion.strip()), 20,
                                    f"{d.test_id}: criterion too short")
            self.assertTrue(d.handler.strip(), f"{d.test_id}: empty handler")
            self.assertTrue(d.checks, f"{d.test_id}: no checks declared")
            self.assertTrue(d.evidence, f"{d.test_id}: no evidence declared")

    def test_unsupported_handlers_carry_a_reason(self):
        for d in registry.DEFINITIONS:
            if d.handler == "unsupported":
                self.assertTrue(d.params.get("reason"),
                                f"{d.test_id}: unsupported without reason")


class TestPublishedAcceptanceDefinitions(unittest.TestCase):
    """Spot-check definitions backing already-published Member A acceptances."""

    def test_w04_polarity(self):
        d = registry.get("A-W04-06")
        self.assertEqual(d.handler, "polarity")
        self.assertEqual(d.safety, SafetyClass.POWERED_GUIDED)

    def test_w21_degraded_sensor_and_pzem(self):
        self.assertEqual(registry.get("A-W21-01").handler, "soak")
        self.assertEqual(registry.get("A-W21-02").handler, "degraded_sensor")
        self.assertEqual(registry.get("A-W21-03").handler, "degraded_pzem")
        self.assertEqual(registry.get("A-W21-04").handler, "safe_local")

    def test_w12_and_w23_documentary(self):
        self.assertEqual(registry.get("A-W12-03").handler, "documentary")
        self.assertEqual(registry.get("A-W23-02").handler, "documentary")
        self.assertEqual(registry.get("A-W12-03").safety, SafetyClass.NO_POWER)

    def test_w23_03_labeling_has_no_waiver(self):
        d = registry.get("A-W23-03")
        self.assertEqual(d.handler, "documentary")
        items = d.params.get("items", [])
        self.assertEqual(len(items), 6, "six canonical branch labels")
        # unknown_ok must be falsy: an operator-accepted deviation cannot waive
        # the applied-label criterion (no waiver clause exists).
        self.assertFalse(bool(d.params.get("unknown_ok", False)))


if __name__ == "__main__":
    unittest.main()