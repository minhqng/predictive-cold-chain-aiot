"""The W09 dossier must keep durable claims and phase snapshots apart, in both directions.

`evidence/A/W09/README.md` splits its claims into a **MUST-KEEP** class (rules and
provenance facts that hold however the physical study develops) and a **PHASE
SNAPSHOT** class (figures measured over the one real thermal session the repository
holds today: 957 rows, boot_id `56044b74` carrying two `run_id` segments, from
`evidence/A/W04/tec-cooling-response-600s.csv`).

The point of the split is that an honesty check must not become a lock. A validator
that pinned the H8-only numbers forever would fail the day the operator files a
second real session - so it would be punishing the success it exists to record. A
validator that only ever checked prose would stay green while the prose rotted. This
file exercises both halves of `validate_w09._check_claim_classes`, including the
branch the committed data cannot reach on its own, by re-running the check against a
registry that already lists a second real thermal capture.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))

DOSSIER = REPO_ROOT / "evidence" / "A" / "W09"
EXPORT_NAME = "exports/CG-S1-H8C-600S.json"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_w09_under_test", DOSSIER / "validate_w09.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _published(name: str) -> dict:
    return json.loads((DOSSIER / name).read_text(encoding="utf-8"))


def _second_real_thermal_session(registry: dict) -> dict:
    """The same registry with a second real capture screened for a thermal scenario."""
    out = copy.deepcopy(registry)
    base = next(c for c in out["captures"] if c.get("scenario_screen"))
    clone = copy.deepcopy(base)
    clone["capture_id"] = "SYNTHETIC-SECOND-SESSION"
    clone["path"] = "evidence/A/W09/tests/second-session.csv"
    out["captures"].append(clone)
    return out


class ClaimClassSplitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = _load_validator()
        cls.readme = (DOSSIER / "README.md").read_text(encoding="utf-8")
        cls.registry = _published("run-registry.json")
        cls.summary = _published("invalidation-summary.json")
        cls.ranges = _published("healthy-ranges.json")
        cls.export = _published(EXPORT_NAME)

    def _mutilated(self, *removals):
        """The published README with a claim removed, matched on the collapsed text.

        The validator collapses whitespace before matching, and the README wraps its
        bullets, so a claim is cut from the collapsed form - cutting the raw file
        would silently leave the wrapped occurrence in place and test nothing.
        """
        text = self.validator.normalized_prose(self.readme)
        for removal in removals:
            self.assertIn(removal, text, removal)
            text = text.replace(removal, "withheld for the test")
        return text

    def _failures(self, readme=None, registry=None):
        failures: list[str] = []
        self.validator._check_claim_classes(
            failures,
            readme if readme is not None else self.readme,
            registry if registry is not None else self.registry,
            self.summary, self.ranges, self.export,
        )
        return failures

    def test_the_published_dossier_satisfies_both_classes_today(self):
        self.assertEqual(self._failures(), [])

    def test_the_snapshot_branch_follows_the_registry_not_the_prose(self):
        self.assertEqual(self.validator._real_thermal_sessions(self.registry), 1)
        self.assertEqual(
            self.validator._real_thermal_sessions(_second_real_thermal_session(self.registry)), 2
        )

    def test_durable_claims_are_demanded_whatever_the_session_count(self):
        for registry in (self.registry, _second_real_thermal_session(self.registry)):
            for token in self.validator.MUST_KEEP_CLAIMS:
                with self.subTest(token=token):
                    reported = self._failures(
                        readme=self._mutilated(token), registry=registry
                    )
                    self.assertTrue(
                        any(token in message for message in reported),
                        f"removing the durable claim {token!r} was not reported: {reported}",
                    )

    def test_snapshot_figures_are_demanded_only_while_one_session_exists(self):
        figures = self.validator._snapshot_figures(
            self.summary, self.ranges, self.export, self.registry
        )
        self.assertGreaterEqual(len(figures), 20)
        for figure in figures:
            with self.subTest(figure=figure):
                self.assertIn(figure, self.validator.normalized_prose(self.readme))

    def test_the_single_session_wording_is_required_at_one_and_forbidden_above_it(self):
        claim = self.validator.SNAPSHOT_EXCLUSIVITY_CLAIM
        self.assertIn(claim, self.validator.normalized_prose(self.readme))

        def relevant(messages):
            return [m for m in messages if "thermal session" in m or "thermal capture" in m]

        missing = self._failures(readme=self._mutilated(claim))
        self.assertEqual(len(relevant(missing)), 1, missing)
        self.assertIn("single real thermal session", relevant(missing)[0])

        refused = self._failures(registry=_second_real_thermal_session(self.registry))
        self.assertEqual(len(relevant(refused)), 1, refused)
        self.assertIn(claim, relevant(refused)[0])
        self.assertIn("overstatement", relevant(refused)[0])

    def test_a_stale_snapshot_figure_fails_today_but_not_after_the_phase_ends(self):
        figures = self.validator._snapshot_figures(
            self.summary, self.ranges, self.export, self.registry
        )
        stale = self._mutilated(figures[0])
        self.assertTrue(
            any("snapshot figure" in m for m in self._failures(readme=stale)),
            "a stale snapshot figure must be named while the phase still holds",
        )
        after = self._failures(
            readme=stale, registry=_second_real_thermal_session(self.registry)
        )
        self.assertFalse(any("snapshot figure" in m for m in after), after)


if __name__ == "__main__":
    unittest.main()
