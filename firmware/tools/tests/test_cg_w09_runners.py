"""Tests for the W09 check runner (A-W09-01 delivery surface).

The runner is how a published PASS is reproduced, so it is testable in its own
right. The rule it has to satisfy is narrow and was previously broken: a slice's
runner may only discover test files that exist in this repository. An earlier
revision of `run_all_checks_w09.py` discovered `test_cg_w11*`, a suite belonging
to a different slice; a pristine checkout of the published revision therefore
failed the very command the W09 dossier publishes, while a working tree holding
another worker's untracked files showed a clean pass. The PASS was borrowed from
bytes nobody had committed.

The same rule now decides which runner modules this file may import. On the W09
branch `run_all_checks_w10.py` is not tracked, so importing it unconditionally
would make the W09 suite fail to load for a reason that belongs to the next week.
The W10 runner is therefore loaded only when this checkout actually carries it -
which is the case on the W10 branch stacked here, where the same assertions run
over both weeks instead of silently vanishing.

These tests keep that from coming back, without needing git.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import run_all_checks_w09  # noqa: E402

PATTERN_RE = re.compile(r'"(test_[A-Za-z0-9_*]+)"')


def _load_runner(name: str):
    """Load a sibling runner module only if this branch tracks it."""
    path = TOOLS / f"{name}.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_all_checks_w10 = _load_runner("run_all_checks_w10")

RUNNERS = {"run_all_checks_w09": run_all_checks_w09}
if run_all_checks_w10 is not None:
    RUNNERS["run_all_checks_w10"] = run_all_checks_w10

# Slices whose tooling this checkout actually delivers. Anything else belongs to
# another worker and may not be depended on for a verdict published here.
OWNED_PREFIXES = tuple(
    prefix for prefix, path in (
        ("test_cg_w09", TOOLS / "tests" / "cg_w09_fixtures.py"),
        ("test_cg_w10", TOOLS / "cg_w10_door.py"),
    ) if path.is_file()
)
FOREIGN_PREFIXES = ("test_cg_w11", "test_cg_s4", "test_cg_s3")


def _patterns(module) -> list[str]:
    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    return sorted(set(PATTERN_RE.findall(source)))


class RunnerTestSelectionResolves(unittest.TestCase):
    def test_every_discovery_pattern_resolves_to_a_test_file(self):
        for name, module in RUNNERS.items():
            for pattern in _patterns(module):
                with self.subTest(runner=name, pattern=pattern):
                    selected = module.select_test_files(pattern)
                    self.assertTrue(
                        selected,
                        f"{name} selects {pattern!r} but no such test file exists; a runner "
                        "must not depend on uncommitted work",
                    )

    def test_selection_resolves_inside_the_tests_directory_only(self):
        for name, module in RUNNERS.items():
            for pattern in _patterns(module):
                for filename in module.select_test_files(pattern):
                    self.assertTrue(
                        (module.TOOLS / "tests" / filename).is_file(),
                        f"{name}: {filename} is not a file under firmware/tools/tests",
                    )

    def test_w09_and_w10_runners_do_not_discover_another_slices_tests(self):
        source = "".join(
            pathlib.Path(module.__file__).read_text(encoding="utf-8")
            for module in RUNNERS.values()
        )
        for foreign in FOREIGN_PREFIXES:
            self.assertNotIn(f'"{foreign}', source, f"a runner discovers {foreign!r}")

    def test_w09_runner_still_covers_the_w09_suite(self):
        # Removing a foreign dependency must not quietly drop the real coverage.
        selected = set(run_all_checks_w09.select_test_files("test_cg_w09*"))
        self.assertIn("test_cg_w09_validity.py", selected)
        self.assertIn("test_cg_w09_export.py", selected)
        self.assertIn("test_cg_w09_capture_parser.py", selected)
        self.assertIn("test_cg_w09_noise.py", selected)
        self.assertIn("test_cg_w09_runners.py", selected)

    def test_w10_suites_are_covered_where_the_w10_tools_exist(self):
        """The W10 suites are covered by the W10 runner, not by a borrowed gate."""
        if run_all_checks_w10 is None:
            self.skipTest("this branch does not track run_all_checks_w10.py; the W10 suites "
                          "belong to the slice stacked on this branch")
        w10 = set(run_all_checks_w10.select_test_files("test_cg_w10*"))
        self.assertIn("test_cg_w10_door.py", w10)
        self.assertIn("test_cg_w10_pairing.py", w10)
        self.assertTrue(set(run_all_checks_w10.select_test_files("test_cg_w09*")))

    def test_slice_suites_are_non_empty_for_both_runners(self):
        for name, module in RUNNERS.items():
            for prefix in OWNED_PREFIXES:
                with self.subTest(runner=name, prefix=prefix):
                    self.assertTrue(module.select_test_files(f"{prefix}*"))


if __name__ == "__main__":
    unittest.main()
