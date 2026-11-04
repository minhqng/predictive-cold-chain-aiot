"""Execution-readiness gate classification tests."""

from __future__ import annotations

import pathlib
import tempfile
import unittest
from types import SimpleNamespace

from member_a_app import protocol, readiness
from member_a_app.model import Outcome
from member_a_app.requirements import get


def result(outcome: Outcome, reason: str = "") -> SimpleNamespace:
    return SimpleNamespace(outcome=outcome, failure_reason=reason)


class ReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.results = {
            "A-W02-04": result(Outcome.PASS),
            "A-W02-02": result(Outcome.PASS),
            "A-W04-03": result(Outcome.PASS),
            "A-W07-01": result(Outcome.PASS),
            "A-W02-05": result(Outcome.PASS),
            "A-W03-05": result(Outcome.INCOMPLETE, "H8_BENCH_IMAGE"),
            "A-W06-02": result(Outcome.INCOMPLETE, "NETWORK_COMMAND_TRANSPORT_UNAVAILABLE"),
            "A-W01-01": result(Outcome.FAIL, "UNAPPROVED_SUBSTITUTION"),
            "A-W05-01": result(Outcome.INCOMPLETE, "PZEM_POWER_SUPPLY_OFF"),
        }

    def item(self, test_id: str, snapshot: readiness.CapabilitySnapshot):
        rows = readiness.evaluate([get(test_id)], self.results, snapshot)
        return rows[0]

    def test_ready_telemetry_and_already_passed(self) -> None:
        snap = readiness.CapabilitySnapshot(connected=True, firmware_kind="CANONICAL")
        self.assertEqual(self.item("A-W02-04", snap).state, readiness.READY_NOW)
        self.assertEqual(self.item("A-W02-05", snap).state, readiness.READY_NOW)

    def test_actuation_is_firmware_blocked_before_psu(self) -> None:
        snap = readiness.CapabilitySnapshot(
            connected=True, firmware_kind="CANONICAL", output_stage="DISABLED",
            command_transport=False, psu_present=False,
            limits={"on_time_max_ms": 190000.0})
        item = self.item("A-W04-05", snap)
        self.assertEqual(item.state, readiness.NEEDS_FIRMWARE_CAPABILITY)
        self.assertTrue(any(reason.startswith("COMMAND_TRANSPORT") for reason in item.reasons))
        self.assertTrue(any(reason.startswith("OUTPUT_STAGE") for reason in item.reasons))

    def test_600s_actuation_detected_against_190s_profile(self) -> None:
        snap = readiness.CapabilitySnapshot(
            connected=True, firmware_kind="CANONICAL", output_stage="ENABLED",
            command_transport=True, psu_present=True,
            limits={"on_time_max_ms": 190000.0})
        item = self.item("A-W08-03", snap)
        self.assertEqual(item.state, readiness.NEEDS_FIRMWARE_CAPABILITY)
        self.assertTrue(any("DURATION_EXCEEDS_FIRMWARE_LIMIT" in reason
                            for reason in item.reasons))

    def test_warmup_needs_operator_door_and_not_psu(self) -> None:
        snap = readiness.CapabilitySnapshot(
            connected=True, firmware_kind="CANONICAL", output_stage="ENABLED",
            command_transport=True, psu_present=False, door_known=False)
        item = self.item("A-W07-02", snap)
        self.assertEqual(item.state, readiness.NEEDS_OPERATOR)
        self.assertIn("DOOR_ATTESTATION_REQUIRED", item.reasons)
        self.assertNotIn("PSU_OFF_OR_PZEM_UNAVAILABLE", item.reasons)

    def test_external_team_and_hardware_noncompliance(self) -> None:
        snap = readiness.CapabilitySnapshot(connected=True, firmware_kind="CANONICAL")
        self.assertEqual(self.item("A-W06-02", snap).state,
                         readiness.NEEDS_EXTERNAL_TEAM_INPUT)
        self.assertEqual(self.item("A-W01-01", snap).state,
                         readiness.HARDWARE_NONCOMPLIANT)

    def test_bme_absent_is_firmware_capability(self) -> None:
        snap = readiness.CapabilitySnapshot(
            connected=True, firmware_kind="CANONICAL", output_stage="ENABLED",
            command_transport=True, psu_present=True, door_known=True,
            bme_present=False)
        for test_id in ("A-W05-04", "A-W05-05"):
            item = self.item(test_id, snap)
            self.assertEqual(item.state, readiness.NEEDS_FIRMWARE_CAPABILITY)
            self.assertIn("BME_PRODUCER_ABSENT", item.reasons)

    def test_psu_and_prerequisite_states(self) -> None:
        snap = readiness.CapabilitySnapshot(
            connected=True, firmware_kind="CANONICAL", output_stage="ENABLED",
            command_transport=True, psu_present=False)
        self.assertEqual(self.item("A-W05-01", snap).state, readiness.NEEDS_PSU)
        self.assertEqual(self.item("A-W05-03", snap).state, readiness.NEEDS_PSU)
        self.assertEqual(self.item("A-W08-05", snap).state,
                         readiness.NEEDS_EXISTING_PREREQUISITE)

    def test_live_snapshot_waits_for_first_pzem_poll(self) -> None:
        import threading
        import time
        from member_a_app.device import FakeDeviceLink
        from member_a_app.tests.helpers import telem_line

        link = FakeDeviceLink(None)
        link.feed_line(telem_line(seq=1, uptime_ms=1000, voltage=0.0,
                                  current=0.0))
        def later() -> None:
            time.sleep(0.3)
            link.feed_line(telem_line(seq=2, uptime_ms=2000, voltage=11.95,
                                      current=0.0))
        threading.Thread(target=later, daemon=True).start()
        snapshot = readiness.build_snapshot(link, probe_commands=False, wait_s=0.1)
        self.assertTrue(snapshot.psu_present)
        self.assertAlmostEqual(snapshot.frame.voltage_v, 11.95)

    def test_chamber_offset_drift_ignores_common_mode_and_hot_side(self) -> None:
        from member_a_app import analysis

        baseline = {"T1": {"mean_c": 30.0}, "T3": {"mean_c": 29.8},
                    "SPARE": {"mean_c": 30.2}, "T2": {"mean_c": 40.0}}
        current = {"T1": {"mean_c": 30.4}, "T3": {"mean_c": 30.2},
                   "SPARE": {"mean_c": 30.6}, "T2": {"mean_c": 40.2}}
        offset, common = analysis.offset_drift(baseline, current)
        self.assertAlmostEqual(common, 0.4, places=6)
        self.assertAlmostEqual(offset, 0.0, places=6)
        shifted = {"T1": {"mean_c": 31.0}, "T3": {"mean_c": 30.2},
                   "SPARE": {"mean_c": 30.6}}
        offset, _ = analysis.offset_drift(baseline, shifted)
        self.assertGreater(offset, 0.3)

    def test_limits_are_parsed_from_boot_events(self) -> None:
        events = [protocol.parse_line(
            "#CG TEC_LIMIT name=on_time_max_ms state=RESOLVED value=190000.0000 "
            "unit=ms source=BENCH_190S")]
        self.assertEqual(readiness._limits_from_events(events)["on_time_max_ms"],
                         190000.0)

    def test_report_files_are_written(self) -> None:
        snap = readiness.CapabilitySnapshot(connected=True, firmware_kind="CANONICAL")
        with tempfile.TemporaryDirectory() as tmp:
            paths = readiness.write_report(
                [get("A-W02-04"), get("A-W06-02")], self.results, snap,
                pathlib.Path(tmp))
            self.assertTrue(paths["json"].is_file())
            self.assertTrue(paths["markdown"].is_file())
            self.assertIn("READY_NOW", paths["markdown"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
