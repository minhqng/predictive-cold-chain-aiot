"""Tests that the W14 dossier validator really fails when a claim stops being honest.

A validator that only checks hashes proves reproduction, not truth, and a validator
whose honesty checks cannot be tripped is decoration. Each case here builds a miniature
repository in a temp directory - the tools, the real capture, the dossier - confirms the
untouched copy passes, then plants exactly one false claim, re-pins the bytes so the
hash check cannot be what failed, and requires a non-zero exit naming the defect.

The planted claims are the four this week could actually ship by accident: a
non-movement verification, an invented pairing tolerance, a hot-side-contaminated
chamber-air mean, and one session labelled a distribution. Two extras cover the
disturbance response and an absolute developer path in a pinned artifact.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
DOSSIER = REPO / "evidence" / "A" / "W14"
TOOLS = REPO / "firmware" / "tools"
H8 = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
TOOL_FILES = ("cg_thermal_repeatability.py", "cg_w14_spatial.py", "cg_w14_sensor_qa.py",
              "cg_w14_pairing.py")


def build_copy(root: pathlib.Path) -> pathlib.Path:
    """A working mini-repo: the dossier, its tools, and the capture it reads."""
    (root / "firmware" / "tools").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "A" / "W04").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "A" / "W14").mkdir(parents=True, exist_ok=True)
    for name in TOOL_FILES:
        shutil.copy2(TOOLS / name, root / "firmware" / "tools" / name)
    shutil.copy2(H8, root / "evidence" / "A" / "W04" / H8.name)
    for path in DOSSIER.iterdir():
        if path.is_file() and path.suffix != ".pyc":
            shutil.copy2(path, root / "evidence" / "A" / "W14" / path.name)
    return root / "evidence" / "A" / "W14"


def validate(dossier: pathlib.Path) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(dossier / "validate_w14.py")],
                            cwd=str(dossier), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def repin(dossier: pathlib.Path) -> None:
    """Re-pin after an edit, so the failure under test is the honesty check."""
    result = subprocess.run([sys.executable, str(dossier / "build_w14_artifacts.py"),
                             "--pins"], cwd=str(dossier), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr


def edit_json(dossier: pathlib.Path, name: str, mutate) -> None:
    path = dossier / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class DossierValidatorFails(unittest.TestCase):
    """One planted defect per case, everything else left as delivered."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name) / "repo"
        self.root.mkdir(parents=True)
        self.dossier = build_copy(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_untouched_copy_passes_first(self):
        """Without this control, every failure below could be a broken sandbox."""
        code, output = validate(self.dossier)
        self.assertEqual(code, 0, output)

    def test_planted_no_movement_claim_fails(self):
        path = self.dossier / "sensor-position-qa.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text + "\nThe slots were re-checked against the freeze record: "
                        "no movement verified since 2026-11-02.\n", encoding="utf-8")
        repin(self.dossier)
        code, output = validate(self.dossier)
        self.assertEqual(code, 1, output)
        self.assertIn("no movement verified", output)

    def test_planted_tolerance_fails(self):
        edit_json(self.dossier, "pairing-input.json",
                  lambda p: p.update(tolerance_value=0.4))
        repin(self.dossier)
        code, output = validate(self.dossier)
        self.assertEqual(code, 1, output)
        self.assertIn("tolerance", output)

    def test_planted_agreement_claim_fails(self):
        edit_json(self.dossier, "pairing-input.json",
                  lambda p: p.update(agreed_with_member_b=True))
        repin(self.dossier)
        code, output = validate(self.dossier)
        self.assertEqual(code, 1, output)
        self.assertIn("agreement", output)

    def test_hot_side_contaminated_chamber_air_mean_fails(self):
        def mutate(payload):
            block = payload["captures"][0]["variants"]["tmean_chamber3_v0"]["cooling"]
            block["is_chamber_air"] = True
            block["feature_terms"] = ["t1_c", "t3_c", "t4_c"]
            block["feature_roles"] = ["CHAMBER_CENTER", "CHAMBER_BOTTOM",
                                      "CHAMBER_NEAR_DOOR"]
            block["delta_c"] = -8.7083
        edit_json(self.dossier, "ablation-support.json", mutate)
        repin(self.dossier)
        code, output = validate(self.dossier)
        self.assertEqual(code, 1, output)
        self.assertIn("hot", output)

    def test_one_session_labelled_a_distribution_fails(self):
        def mutate(payload):
            payload["verdict"]["single_session_observation"] = False
            payload["verdict"]["distribution_computed"] = True
            payload["gradient_distribution"]["status"] = "DISTRIBUTION_COMPUTED"
        edit_json(self.dossier, "spatial-statistics.json", mutate)
        repin(self.dossier)
        code, output = validate(self.dossier)
        self.assertEqual(code, 1, output)
        self.assertIn("distribution", output)

    def test_fabricated_disturbance_response_fails(self):
        def mutate(payload):
            payload["disturbance_specific_response"]["status"] = \
                "COMPUTED_FROM_RECORDED_EVENTS"
            payload["disturbance_specific_response"]["per_capture"][0]["status"] = \
                "COMPUTED_FROM_RECORDED_EVENTS"
            payload["verdict"]["disturbance_response_computed"] = True
        edit_json(self.dossier, "spatial-statistics.json", mutate)
        repin(self.dossier)
        code, output = validate(self.dossier)
        self.assertEqual(code, 1, output)
        self.assertIn("door-open", output)

    def test_absolute_developer_path_fails(self):
        path = self.dossier / "spatial-report.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text + "\nSource capture: C:\\\\Users\\\\bench\\\\capture.csv\n",
                        encoding="utf-8")
        repin(self.dossier)
        code, output = validate(self.dossier)
        self.assertEqual(code, 1, output)
        self.assertIn("absolute capture path", output)

    def test_bytes_change_without_repinning_fails_the_pins(self):
        path = self.dossier / "ablation-support.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nedited after pinning\n",
                        encoding="utf-8")
        code, output = validate(self.dossier)
        self.assertEqual(code, 1, output)
        self.assertIn("hash mismatch", output)


class BuilderRefusesFalseClaims(unittest.TestCase):
    """The generator's own guard, so a bad sentence never reaches a file."""

    def test_generator_exits_non_zero_on_an_asserted_false_claim(self):
        sys.path.insert(0, str(TOOLS))
        import cg_thermal_repeatability as rep  # noqa: E402
        import cg_w14_sensor_qa as qa  # noqa: E402

        for text in ("Sensor positions were re-checked: no movement verified.",
                     "The initial matching tolerance agreed with Member B is 0.5 C.",
                     "Run-to-run gradient distribution computed from the sessions."):
            with self.assertRaises(rep.AnalysisError, msg=text):
                qa.assert_no_false_claim("scratch.md", text)

    def test_quoted_and_negated_forms_are_allowed(self):
        sys.path.insert(0, str(TOOLS))
        import cg_w14_sensor_qa as qa  # noqa: E402

        qa.assert_no_false_claim(
            "scratch.md", "The phrase `\"no movement verified\"` is never asserted here.")
        qa.assert_no_false_claim(
            "scratch.md", "- physically verified: `False` (host analysis only)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
