"""Tests for the W09/W10 check runners (A-W09-01 delivery surface).

The runner is how a published PASS is reproduced, so it is testable in its own
right. The rule it has to satisfy is narrow and was previously broken: a slice's
runner may only discover test files that exist in this repository. An earlier
revision of `run_all_checks_w09.py` discovered `test_cg_w11*`, a suite belonging
to a different slice; a pristine checkout of the published revision therefore
failed the very command the W09 dossier publishes, while a working tree holding
another worker's untracked files showed a clean pass. The PASS was borrowed from
bytes nobody had committed.

These tests keep that from coming back, without needing git.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import run_all_checks_w09  # noqa: E402
import run_all_checks_w10  # noqa: E402

PATTERN_RE = re.compile(r'"(test_[A-Za-z0-9_*]+)"')
RUNNERS = {
    "run_all_checks_w09": run_all_checks_w09,
    "run_all_checks_w10": run_all_checks_w10,
}
# Slices whose tooling this branch actually delivers. Anything else belongs to
# another worker and may not be depended on for a verdict published here.
OWNED_PREFIXES = ("test_cg_w09", "test_cg_w10")
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
        source = pathlib.Path(run_all_checks_w09.__file__).read_text(encoding="utf-8") + \
            pathlib.Path(run_all_checks_w10.__file__).read_text(encoding="utf-8")
        for foreign in FOREIGN_PREFIXES:
            self.assertNotIn(f'"{foreign}', source, f"a runner discovers {foreign!r}")

    def test_w09_runner_still_covers_the_w09_and_w10_suites(self):
        # Removing a foreign dependency must not quietly drop the real coverage.
        selected = set(run_all_checks_w09.select_test_files("test_cg_w09*"))
        self.assertIn("test_cg_w09_validity.py", selected)
        self.assertIn("test_cg_w09_export.py", selected)
        self.assertIn("test_cg_w09_capture_parser.py", selected)
        w10 = set(run_all_checks_w09.select_test_files("test_cg_w10*"))
        self.assertIn("test_cg_w10_door.py", w10)
        self.assertIn("test_cg_w10_pairing.py", w10)

    def test_slice_suites_are_non_empty_for_both_runners(self):
        for name, module in RUNNERS.items():
            for prefix in OWNED_PREFIXES:
                with self.subTest(runner=name, prefix=prefix):
                    self.assertTrue(module.select_test_files(f"{prefix}*"))


if __name__ == "__main__":
    unittest.main()
