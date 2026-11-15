"""Tests for the W13 plant-timing package (A-W13-01 .. A-W13-04).

Covers the three behaviours the requirement makes load-bearing:

* the command->electrical **onset = first sample at/above the threshold** rule
  (a stale pre-run frame is annotated only when the record carries the evidence,
  and a legitimately-current first sample is never shifted a poll late);
* a **known-answer** time-constant fit on synthetic exponential data;
* the door->critical ask **refusing** to emit a number when no door-open event
  exists, plus the whole report on the committed capture.
"""

from __future__ import annotations

import math
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
REPO = TOOLS.parent.parent
sys.path.insert(0, str(TOOLS))

import cg_w13_timing as w13  # noqa: E402

COOLING = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
H6 = REPO / "evidence" / "A" / "W04" / "h6" / "first-tec-trace.csv"


class CommandToElectricalTests(unittest.TestCase):
    def _write_trace(self, d: pathlib.Path, name: str = "trace.csv",
                     samples=None) -> pathlib.Path:
        header = "host_utc,host_uptime_s,record_type,event_label,state,duty_permille," \
                 "vbus_v,current_a,power_w,elapsed_ms,boot_id"
        lines = [header]
        lines.append("2026-01-01T00:00:05Z,5.000,EVENT_CMD,START,RUNNING_10_PERCENT,100,,,,")
        lines.append("2026-01-01T00:00:05Z,5.000,EVENT_ON,ON,,100,,,,")
        for up, cur, elapsed, boot in (samples or []):
            lines.append(f"2026-01-01T00:00:05Z,{up},SAMPLE,,RUNNING_10_PERCENT,100,11.7,"
                         f"{cur},,{elapsed},{boot}")
        p = d / name
        p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        return p

    def test_preramp_sample_annotated_but_onset_is_threshold_crossing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = self._write_trace(pathlib.Path(td), samples=[
                ("5.500", "0.000", "2", "bA"),      # pre-ramp register read (sub-poll)
                ("6.000", "1.000", "1000", "bA"),   # true onset
                ("7.000", "1.000", "2000", "bA"),
            ])
            res = w13.command_to_electrical_delay(p)
            self.assertEqual(res["status"], "MEASURED")
            # Onset is the first sample at/above threshold (6.0), never shifted late.
            self.assertEqual(res["electrical_onset_device_uptime_s"], 6.0)
            self.assertEqual(res["delay_s"], 1.0)
            # The pre-ramp frame is annotated as stale, but only because the record
            # carries sub-poll elapsed_ms evidence.
            self.assertEqual(res["prerun_samples_annotated"][0]["host_uptime_s"], 5.5)

    def test_valid_first_sample_is_not_shifted_a_poll_late(self) -> None:
        # A capture whose FIRST post-command sample legitimately carries current must
        # report the true delay, not one poll period late. The reverted (buggy) rule
        # dropped samples_after[0] unconditionally and would report 1.5 s for a true 0.5 s.
        with tempfile.TemporaryDirectory() as td:
            p = self._write_trace(pathlib.Path(td), samples=[
                ("5.500", "1.000", "1500", "bA"),
                ("6.500", "1.000", "2500", "bA"),
            ])
            res = w13.command_to_electrical_delay(p)
            self.assertEqual(res["electrical_onset_device_uptime_s"], 5.5)
            self.assertEqual(res["delay_s"], 0.5)

    def test_clock_semantics_are_stated_in_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = self._write_trace(pathlib.Path(td), samples=[
                ("5.500", "0.000", "2", "bA"), ("6.000", "1.000", "1000", "bA")])
            res = w13.command_to_electrical_delay(p)
            rule = res["latency_exclusion_rule"]
            self.assertIn("DEVICE LOG UPTIME", rule)
            # Cites the committed pre-ramp source, not a non-existent analysis doc.
            self.assertIn("41-h6-run-analysis.md:28", rule)
            self.assertNotIn("H8_CURRENT_PATH_AND_SHUTDOWN_ANALYSIS", rule)
            self.assertEqual(res["poll_quantization_s"], 1.0)
            self.assertIn("0.156", res["excluded_transport"])

    def test_interval_never_crosses_a_boot_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = self._write_trace(pathlib.Path(td), samples=[
                ("5.500", "0.000", "2", "bA"), ("6.000", "1.000", "1000", "bB")])
            res = w13.command_to_electrical_delay(p)
            self.assertEqual(res["status"], "BOOT_DISCONTINUITY")
            self.assertIsNone(res["delay_s"])

    def test_probe_identification_trace_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = self._write_trace(pathlib.Path(td), name="probe-identification_trace.csv",
                                  samples=[("5.500", "1.000", "1500", "bA")])
            res = w13.command_to_electrical_delay(p)
            self.assertEqual(res["status"], "EXCLUDED_PROBE_IDENTIFICATION")

    def test_no_current_after_command_is_not_computable_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = self._write_trace(pathlib.Path(td), samples=[
                ("6.000", "0.0", "1500", "bA"), ("7.000", "0.0", "2500", "bA")])
            res = w13.command_to_electrical_delay(p)
            self.assertEqual(res["status"], "NO_POST_COMMAND_CURRENT")
            self.assertIsNone(res["delay_s"])

    @unittest.skipUnless(H6.is_file(), "H6 trace not present")
    def test_committed_h6_trace_yields_the_documented_delay(self) -> None:
        res = w13.command_to_electrical_delay(H6)
        self.assertEqual(res["status"], "MEASURED")
        # START accept at 5.235; the 0 A pre-ramp sample does not set onset; the first
        # sample at/above threshold is 0.970 A at 6.329 - the documented 1.094 s.
        self.assertAlmostEqual(res["delay_s"], 1.094, places=3)


class TimeConstantKnownAnswerTests(unittest.TestCase):
    def test_cooling_exponential_recovers_tau(self) -> None:
        # y = 30 - 20*(1 - exp(-t/50))  -> asymptote 10, swing -20, tau = 50 s.
        tau = 50.0
        t = [i * 1.0 for i in range(0, 200)]
        y = [30 - 20 * (1 - math.exp(-tt / tau)) for tt in t]
        res = w13.estimate_time_constant(t, y, direction="decrease")
        self.assertEqual(res["status"], "MEASURED")
        # The 63.2% target is reached at exactly t = tau; 1 s sampling tolerance.
        self.assertAlmostEqual(res["tau_s"], tau, delta=1.5)

    def test_warming_exponential_recovers_tau(self) -> None:
        tau = 40.0
        t = [i * 0.5 for i in range(0, 400)]
        y = [10 + 15 * (1 - math.exp(-tt / tau)) for tt in t]
        res = w13.estimate_time_constant(t, y, direction="auto")
        self.assertEqual(res["direction"], "increase")
        self.assertAlmostEqual(res["tau_s"], tau, delta=1.0)

    def test_short_window_tau_is_biased_and_flags_its_limitation(self) -> None:
        # Honest property: the 63.2%-of-observed-swing rule uses the observed
        # endpoints as the swing, so a window that has not reached steady state
        # yields a biased (low) estimate. It never silently claims a clean fit:
        # the limitation is always attached.
        tau = 500.0
        t = [i for i in range(0, 50)]
        y = [30 - 20 * (1 - math.exp(-tt / tau)) for tt in t]
        res = w13.estimate_time_constant(t, y, direction="decrease")
        self.assertEqual(res["status"], "MEASURED")
        self.assertIn("limitation", res)
        self.assertLess(res["tau_s"], tau)   # biased low, as documented

    def test_flat_signal_reports_no_swing(self) -> None:
        res = w13.estimate_time_constant([0, 1, 2], [10.0, 10.0, 10.0])
        self.assertEqual(res["status"], "NO_SWING")


class DoorCriticalRefusalTests(unittest.TestCase):
    def _rows(self, door_values):
        return [{
            "seq": str(i), "device_ms": str(i * 1000), "pwm_applied_permille": "999",
            "t1_c": "10", "t3_c": "10", "t4_c": "10", "stop_reason": "NONE",
            "door_open": v, "door_polarity": "UNCONFIRMED",
        } for i, v in enumerate(door_values)]

    def test_no_door_open_returns_not_computable_and_emits_no_number(self) -> None:
        res = w13.door_to_critical(self._rows(["0"] * 20))
        self.assertEqual(res["status"], "NOT_COMPUTABLE")
        self.assertIsNone(res["value_s"])
        self.assertFalse(res["number_emitted"])

    def test_unknown_door_open_is_still_not_computable(self) -> None:
        res = w13.door_to_critical(self._rows(["UNKNOWN"] * 20))
        self.assertEqual(res["status"], "NOT_COMPUTABLE")
        self.assertFalse(res["number_emitted"])

    def test_summary_never_publishes_a_door_number(self) -> None:
        # The committed capture has no door-open event, so the report must not
        # carry any door->critical value at all.
        if not COOLING.is_file():
            self.skipTest("cooling capture absent")
        rows = w13.load_csv(COOLING)
        res = w13.door_to_critical(rows)
        self.assertIsNone(res["value_s"])


class ThermalResponseTests(unittest.TestCase):
    def test_thermal_representation_excludes_hot_side(self) -> None:
        # One frame per minute; the three chamber probes fall 1.0 C/frame while
        # the hot side (t2) is pinned cold at 0. If t2 were folded into the
        # representation the crossing time would change; the trio-only baseline
        # makes the expected delay exact: baseline over first 5 frames =
        # mean(30,29,28,27,26)=28.0, 1 C target = 27.0 crossed at the frame 3 min in.
        rows = [{
            "seq": str(i), "device_ms": str(i * 60000), "pwm_applied_permille": "999",
            "t1_c": str(30 - 1.0 * i), "t3_c": str(30 - 1.0 * i),
            "t4_c": str(30 - 1.0 * i), "t2_c": "0",   # hot side pinned cold
            "stop_reason": "NONE",
        } for i in range(20)]
        res = w13.command_to_thermal_delay(rows, delta_c=1.0)
        self.assertEqual(res["status"], "MEASURED")
        self.assertAlmostEqual(res["delay_min"], 3.0, places=2)
        self.assertNotIn("t2", w13.CHAMBER_AIR_SLOTS)

    @unittest.skipUnless(COOLING.is_file(), "cooling capture not present")
    def test_committed_capture_reproduces_the_documented_1c_time(self) -> None:
        rows = w13.load_csv(COOLING)
        res = w13.command_to_thermal_delay(rows)
        self.assertEqual(res["status"], "MEASURED")
        self.assertAlmostEqual(res["delay_min"], 0.85, places=2)
        # all 957 committed frames carry a valid token, so nothing is excluded
        self.assertEqual(res["excluded_nonvalid_frames"], 0)
        cool = w13.cooling_time_constant_proxy(rows)
        self.assertEqual(cool["status"], "MEASURED")
        # The whole-window slope is the W13 tool's OWN computed figure (-0.8548 C/min);
        # it is no longer re-anchored to a W07 file that is not on this branch.
        self.assertAlmostEqual(cool["whole_window_slope_c_per_min"], -0.8548, places=3)

    def test_nonvalid_probe_token_is_excluded_from_the_trio_mean(self) -> None:
        # docs/01 section 20.1: a mean may only be taken over the valid state. A frame
        # whose chamber probe carries a non-valid token is dropped, not averaged.
        self.assertIsNone(w13._trio_mean({"t1_c": "10", "t1_status": "OK",
                                          "t3_c": "10", "t3_status": "OK",
                                          "t4_c": "30", "t4_status": "FAIL"}))
        self.assertAlmostEqual(w13._trio_mean({"t1_c": "10", "t1_status": "OK",
                                               "t3_c": "11", "t3_status": "OK",
                                               "t4_c": "12", "t4_status": "OK"}), 11.0)

    def test_probe_identification_cooling_capture_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "probe-identification_cooling.csv"
            p.write_text(
                "session,pwm_applied_permille,device_ms,t1_c,t3_c,t4_c\n"
                "probe-identification touch session,999,0,30,30,30\n",
                encoding="utf-8", newline="\n")
            report = w13.build_report([], p)
            self.assertEqual(report["command_to_thermal"]["status"],
                             "EXCLUDED_PROBE_IDENTIFICATION")
            self.assertEqual(report["door_to_critical"]["number_emitted"], False)


class DataGapRegisterTests(unittest.TestCase):
    def test_register_names_the_hard_gaps(self) -> None:
        ids = set()
        report = w13.build_report([H6] if H6.is_file() else [], COOLING if COOLING.is_file() else None)
        for gap in report["data_gap_register"]:
            ids.add(gap["id"])
        self.assertIn("GAP-DOOR-CRITICAL", ids)
        self.assertIn("GAP-NETWORK-COMMAND-LATENCY", ids)


if __name__ == "__main__":
    unittest.main()
