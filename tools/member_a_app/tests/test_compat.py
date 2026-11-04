"""Image compatibility classification."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from .helpers import boot_lines, h8_boot_lines, h8s_line, telem_line

from member_a_app import compat
from member_a_app.device import DeviceLink, FakeDeviceLink
from member_a_app.evidence import SessionStore


class CompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SessionStore(pathlib.Path(self.temp.name) / "session", operator="tester")
        self.device = FakeDeviceLink(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_h8_profile_is_read_only_for_canonical_tests(self) -> None:
        for line in h8_boot_lines():
            self.device.feed_line(line)
        self.device.feed_line(h8s_line())
        result = compat.classify(self.device.snapshot)
        self.assertEqual(result.kind, "H8_BENCH")
        self.assertTrue(result.telemetry)
        self.assertFalse(result.canonical_telemetry)
        self.assertFalse(result.canonical_console_commands)
        self.assertTrue(result.h8_console_commands)
        self.assertTrue(result.h8_host_ack_required)
        self.assertTrue(result.h8_stage_f_probe)
        self.assertTrue(result.h8_stage_f_approved)
        self.assertIn(("H8 Stage F probe", "APPROVED"), result.capability_rows())
        self.assertEqual(result.output_stage, "H8_STAGE_ENGINE")
        self.assertTrue(result.supervised)
        self.assertTrue(result.off_current_approved)
        self.assertEqual(result.firmware_version, "h8-bench")
        self.assertEqual(result.device_id, "H8_BENCH")

    def test_h8_stage_f_unapproved_and_unreported_are_distinct(self) -> None:
        for line in h8_boot_lines()[:3]:
            self.device.feed_line(line)
        self.device.feed_line(h8s_line())
        unreported = compat.classify(self.device.snapshot)
        self.assertIsNone(unreported.h8_stage_f_approved)
        self.assertIn(("H8 Stage F probe", "IMPLEMENTED_APPROVAL_UNREPORTED"),
                      unreported.capability_rows())

        self.device.feed_line(
            "#CG TEC_LIMITS test_mode=BENCH_ENDURANCE stage_f_guard=0 "
            "endurance_stages=0")
        unapproved = compat.classify(self.device.snapshot)
        self.assertFalse(unapproved.h8_stage_f_approved)
        self.assertIn(("H8 Stage F probe", "IMPLEMENTED_APPROVAL_UNAPPROVED"),
                      unapproved.capability_rows())

    def test_canonical_profile_reports_disabled_stage_and_no_accepted_path(self) -> None:
        for line in boot_lines():
            self.device.feed_line(line)
        self.device.feed_line(telem_line(output_stage="DISABLED"))
        result = compat.classify(self.device.snapshot)
        self.assertEqual(result.kind, "CANONICAL_W06")
        self.assertTrue(result.canonical_telemetry)
        self.assertTrue(result.canonical_console_commands)
        self.assertFalse(result.accepted_canonical_commands)
        self.assertFalse(result.h8_console_commands)
        self.assertEqual(result.output_stage, "DISABLED")

    def test_unknown_profile(self) -> None:
        result = compat.classify(DeviceLink(None).snapshot)
        self.assertEqual(result.kind, "UNKNOWN")
        self.assertFalse(result.telemetry)

    def test_static_matrix_names_both_grammars(self) -> None:
        text = "\n".join(compat.static_matrix())
        self.assertIn("H8_BENCH", text)
        self.assertIn("CANONICAL_W06", text)
        self.assertIn("Stage F", text)


if __name__ == "__main__":
    unittest.main()
