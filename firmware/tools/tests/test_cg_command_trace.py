"""Tests for cg_command_trace.py (A-W06-05).

The trace tool is the half of W06 that decides whether a command can be called
physically verified, so its tests are about what it refuses to promote, not about
how pretty the report is. The demo capture is read from the delivered dossier so
the assertions run on the same bytes the evidence ships.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_command_trace as trace  # noqa: E402

DOSSIER = pathlib.Path(__file__).resolve().parents[3] / "evidence" / "A" / "W06"
DEMO_CAPTURE = DOSSIER / "demo-command-capture.log"
W04_CAPTURE = pathlib.Path(__file__).resolve().parents[3] / "evidence" / "A" / "W04" / "g1" / "41-g1-reset.log"


def _telem_template() -> str:
    """The schema-3 telemetry line the harness emitted into the demo capture."""
    for line in DEMO_CAPTURE.read_text(encoding="utf-8").splitlines():
        if line.startswith(trace.telemetry_schema.PREFIX):
            return line
    raise AssertionError("the demo capture carries no telemetry line")


def _telem(uptime_ms: int, boot_id: str, cooling_applied: str = "OFF") -> str:
    line = _telem_template()
    line = re.sub(r"uptime_ms=\d+", f"uptime_ms={uptime_ms}", line)
    line = re.sub(r"boot_id=\S+", f"boot_id={boot_id}", line)
    line = re.sub(r"cooling_applied=\S+", f"cooling_applied={cooling_applied}", line)
    return line


def _ack(command_id: str, uptime_ms: int, boot_id: str, status: str = "ACCEPTED",
         reason: str = "NONE", reapplied: str = "0", applied: str = "OFF",
         desired: str = "ON") -> str:
    return (
        "#CG CMDACK schema=1 event=ACK "
        f"command_id={command_id} command_id_form=UUID source=NETWORK "
        f"boot_id={boot_id} boot_count=1 uptime_ms={uptime_ms} ack_seq=1 "
        f"status={status} reason={reason} desired_cooling={desired} "
        "desired_duty_permille=250 "
        f"applied_cooling={applied} applied_duty_permille=0 reapplied={reapplied} "
        "expiry_evaluable=1 time_sync_state=SYNCHRONIZED device_mode=COOLING "
        "fault_code=0x00000000 output_stage=ENABLED allowed_duty_max_permille=500"
    )


def _report(lines: list[str], per_frame: bool = False) -> dict:
    with tempfile.TemporaryDirectory() as workdir:
        capture = pathlib.Path(workdir) / "capture.log"
        out = pathlib.Path(workdir) / "report.json"
        capture.write_text("\n".join(lines) + "\n", encoding="utf-8")
        argv = [str(capture), "--json", str(out)] + (["--per-frame"] if per_frame else [])
        if trace.main(argv) != 0:
            raise AssertionError(f"the trace tool refused to report on {len(lines)} lines")
        return json.loads(out.read_text(encoding="utf-8"))


class TracePromotionTests(unittest.TestCase):
    def test_an_ack_alone_never_reaches_applied_state(self) -> None:
        """docs/02 32.2: an ACK is protocol evidence, not applied evidence."""
        report = _report([_ack("cmd-1", 1000, "abcd0123")])
        row = report["commands"][0]
        self.assertEqual(row["stages"], ["COMMAND_SEEN", "DEVICE_ACK"])
        self.assertEqual(row["blocked_at"], "APPLIED_STATE")
        self.assertEqual(report["summary"]["not_applied"], 1)
        self.assertEqual(report["summary"]["reached"]["ELECTRICAL_VERIFIED"], 0)
        self.assertEqual(report["summary"]["reached"]["THERMAL_VERIFIED"], 0)

    def test_a_replay_that_applied_twice_is_reported_as_a_defect(self) -> None:
        report = _report([
            _ack("cmd-1", 1000, "abcd0123"),
            _ack("cmd-1", 1005, "abcd0123", status="DUPLICATE_CANONICAL", reapplied="1"),
        ])
        row = report["commands"][0]
        self.assertTrue(any("reapplied=1" in note for note in row["notes"]), row["notes"])
        self.assertNotIn("APPLIED_STATE", row["stages"])

    def test_frames_from_another_boot_are_not_attributed(self) -> None:
        """A frame from a different boot_id is a different clock axis."""
        commands = trace.parse_capture([
            _ack("cmd-1", 1000, "abcd0123"),
            _telem(2000, "ef567890", cooling_applied="ON"),
        ])
        self.assertEqual(commands["cmd-1"]["frames_after"], [])

    def test_applied_state_needs_applied_evidence_not_a_desired_one(self) -> None:
        lines = [
            _ack("cmd-1", 1000, "abcd0123"),
            _telem(2000, "abcd0123", cooling_applied="OFF"),
            _telem(3000, "abcd0123", cooling_applied="OFF"),
            _telem(4000, "abcd0123", cooling_applied="OFF"),
        ]
        row = _report(lines)["commands"][0]
        self.assertEqual(row["blocked_at"], "APPLIED_STATE")


class TracePerFrameTests(unittest.TestCase):
    def test_frames_are_attributed_by_identity_not_by_row_order(self) -> None:
        """Rows come out sorted by command_id while parsing keeps arrival order.

        Positional pairing put the wrong frames on the wrong row whenever those
        two orders disagreed, which is exactly the case a real capture produces.
        """
        lines = [
            # Arrival order zz.. precedes aa..; sorted output order is the reverse.
            _ack("zz-command", 1000, "abcd0123"),
            _telem(1500, "abcd0123"),
            _telem(1600, "abcd0123"),
            _ack("aa-command", 5000, "abcd0123"),
            _telem(5500, "abcd0123"),
            _telem(5600, "abcd0123"),
            _telem(5700, "abcd0123"),
        ]
        report = _report(lines, per_frame=True)
        expected = {
            row["command_id"]: len(trace.parse_capture(lines)[row["command_id"]]["frames_after"])
            for row in report["commands"]
        }
        self.assertEqual([row["command_id"] for row in report["commands"]],
                         ["aa-command", "zz-command"])
        got = {row["command_id"]: len(row["frames_after"]) for row in report["commands"]}
        # zz acknowledged first, so it owns every later frame; aa started at 5000
        # and may only attribute the three after it. Positional pairing would have
        # swapped exactly these two counts.
        self.assertEqual(got, {"aa-command": 3, "zz-command": 5})
        self.assertEqual(got, expected)

    def test_per_frame_frames_all_follow_their_own_ack(self) -> None:
        lines = [
            _ack("cmd-1", 3000, "abcd0123"),
            _telem(1000, "abcd0123"),
            _telem(4000, "abcd0123"),
        ]
        report = _report(lines, per_frame=True)
        frames = report["commands"][0]["frames_after"]
        self.assertEqual(len(frames), 1)
        self.assertEqual(int(frames[0]["uptime_ms"]), 4000)


class TraceRealCaptureTests(unittest.TestCase):
    def test_a_capture_without_command_lines_reports_no_commands(self) -> None:
        """The committed W04 capture predates the command contract; the tool must
        say so instead of inventing a lifecycle."""
        if not W04_CAPTURE.is_file():
            self.skipTest(f"{W04_CAPTURE} is not present in this checkout")
        report = _report(W04_CAPTURE.read_text(encoding="utf-8", errors="replace").splitlines())
        self.assertEqual(report["summary"]["commands_observed"], 0)
        self.assertEqual(report["summary"]["verdict"], "NO_COMMAND_LINES_PRESENT")

    def test_the_shipped_demo_report_still_reproduces_from_the_delivered_capture(self) -> None:
        published = json.loads((DOSSIER / "trace-host-demo.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as workdir:
            out = pathlib.Path(workdir) / "report.json"
            self.assertEqual(
                trace.main([str(DEMO_CAPTURE), "--json", str(out), "--per-frame"]), 0)
            fresh = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(fresh["summary"], published["summary"])
        self.assertEqual([r["command_id"] for r in fresh["commands"]],
                         [r["command_id"] for r in published["commands"]])
        # The published demo never claims physical application.
        self.assertEqual(published["summary"]["reached"]["ELECTRICAL_VERIFIED"], 0)
        self.assertEqual(published["summary"]["reached"]["THERMAL_VERIFIED"], 0)


if __name__ == "__main__":
    unittest.main()
