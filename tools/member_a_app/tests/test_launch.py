"""Application launch checks: registry mode and a real Tk smoke launch."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

from .helpers import TOOLS

APP = TOOLS / "member_a_app" / "app.py"
REPO = TOOLS.parent


class LaunchTests(unittest.TestCase):
    def test_check_mode_reports_114(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(APP), "--check"],
            cwd=str(REPO), capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("definitions=114 errors=0", completed.stdout)

    def test_gui_smoke_launch(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(APP), "--smoke"],
            cwd=str(REPO), capture_output=True, text=True, timeout=60)
        if completed.returncode != 0:
            combined = (completed.stdout + completed.stderr).lower()
            if "no display" in combined or "tclerror" in combined or "couldn't connect" in combined:
                self.skipTest("no desktop display available for a Tk launch")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("SMOKE_OK", completed.stdout)


if __name__ == "__main__":
    unittest.main()
