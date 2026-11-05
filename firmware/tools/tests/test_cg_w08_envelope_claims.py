"""The published W08 numbers, proved against the bytes they came from.

`test_cg_w08_envelope.py` already pins the register-latency *rules*. This file
pins the *claims* the W08 dossier publishes, because those are the numbers a
reviewer will quote:

* the envelope boundaries of the committed 600 s capture (600 driven frames, 599
  used, 7.16 A median, 9.99 A peak, 7.2247/7.2367 A means, 0.02 A steady OFF
  ceiling);
* that the documented PZEM register-latency frame at ``device_ms=826894`` is
  named and excluded rather than averaged, and that its byte-identity claim holds
  on the fields this slice states (V/I/P/energy and T1/T2/T3 - not T4);
* V x I consistency and the energy-counter agreement;
* unqualified-status handling: the committed CSV's V/I/P carry no validity, while
  the wire line of the same session does (proved with a labelled synthetic
  fixture, never a copied original);
* and that no generated artifact can claim ``PHYSICALLY_VERIFIED`` - proved by
  injecting one into a temporary copy of the dossier and watching the validator
  fail.

Everything here is host analysis of recorded files. No test touches hardware, and
no test asserts a physical limit.
"""

from __future__ import annotations

import csv
import functools
import hashlib
import importlib.util
import io
import json
import contextlib
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
REPO = TOOLS.parents[1]
DOSSIER = REPO / "evidence" / "A" / "W08"

sys.path.insert(0, str(TOOLS))

import cg_w08_envelope as env  # noqa: E402

CSV_PATH = REPO / "evidence/A/W04/tec-cooling-response-600s.csv"

# One raw frame line of the bench image's #CG H8S schema=3 output, as the monitor
# recorded it, reduced to the tokens this test needs. It is a SYNTHETIC FIXTURE
# built in this test file - not a copied capture - and it exists only to prove
# that the reader recovers the validity tokens the committed CSV lost.
SYNTHETIC_WIRE_LINE = (
    "#CG H8S schema=3 seq=827 device_ms=826894 boot_id=56044b74 run_id=run-00000001 "
    "stage=H8-C state=COOLDOWN fault_bits=0x0 stop_reason=STAGE_DEADLINE snapshot=VALID "
    "pwm_req_permille=0 pwm_applied_permille=0 pwm_readback_permille=0 "
    "off_current_limit_a=0.200 off_verify=PASS limits_policy=APPROVED "
    "t1=20.875 t1_status=OK t1_age_ms=46 t1_role=UNASSIGNED "
    "t2=39.562 t2_status=OK t2_age_ms=46 t2_role=HOT_SIDE "
    "t3=21.625 t3_status=OK t3_age_ms=46 t3_role=UNASSIGNED "
    "t4=21.438 t4_status=OK t4_age_ms=46 t4_role=UNASSIGNED "
    "voltage_v=11.790 voltage_v_status=OK voltage_v_age_ms=666 "
    "current_a=7.150 current_a_status=OK current_a_age_ms=666 "
    "power_w=84.200 power_w_status=OK power_w_age_ms=666 energy_wh=122.000"
)


def monitor_record(raw_line: str) -> dict[str, object]:
    """Rebuild the monitor's parsed object from a wire line, as the monitor did.

    The reader takes values from the parsed object and validity/age tokens from
    the raw string; a fixture therefore has to carry both, exactly like the real
    ``samples.jsonl`` files. Synthetic: never a copied capture.
    """
    tokens = env._raw_tokens(raw_line)
    record: dict[str, object] = {
        "seq": tokens.get("seq"),
        "device_ms": tokens.get("device_ms"),
        "state": tokens.get("state"),
        "stage": tokens.get("stage"),
        "stop_reason": tokens.get("stop_reason"),
        "snapshot": tokens.get("snapshot"),
        "pwm_req": tokens.get("pwm_req_permille"),
        "pwm_applied": tokens.get("pwm_applied_permille"),
        "pwm_readback": tokens.get("pwm_readback_permille"),
        "voltage_v": tokens.get("voltage_v"),
        "current_a": tokens.get("current_a"),
        "power_w": tokens.get("power_w"),
        "energy_wh": tokens.get("energy_wh"),
        "raw": raw_line,
    }
    for channel in ("t1", "t2", "t3", "t4"):
        record[channel] = tokens.get(channel)
        record[f"{channel}_status"] = tokens.get(f"{channel}_status")
        record[f"{channel}_role"] = tokens.get(f"{channel}_role")
        record[f"{channel}_age_ms"] = tokens.get(f"{channel}_age_ms")
    return record


@functools.lru_cache(maxsize=1)
def committed_frames() -> list[env.Frame]:
    return env.classify(env.read_h8_csv(CSV_PATH, "W04-H8C-box-600s"))


@functools.lru_cache(maxsize=1)
def committed_envelope() -> dict[str, object]:
    return env.build_envelope(REPO, None, transport=False)


class EnvelopeBoundaries(unittest.TestCase):
    """The published ranges, recomputed from the CSV on every run."""

    def test_frame_and_stage_population(self) -> None:
        frames = committed_frames()
        self.assertEqual(len(frames), 957)
        self.assertEqual(sum(1 for f in frames if f.stage == "NONE"), 219)
        self.assertEqual(sum(1 for f in frames if f.stage == "H8-C"), 738)
        self.assertEqual(sum(1 for f in frames if f.driven), 600)
        self.assertEqual({f.duty_applied for f in frames if f.driven}, {999})
        self.assertEqual(sum(1 for f in frames if f.state == "COOLDOWN"), 5)
        self.assertEqual({f.fault_bits for f in frames}, {"0"})
        rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8", newline="")))
        self.assertEqual({row["boot_id"] for row in rows}, {"56044b74"})
        self.assertEqual({row["session"] for row in rows},
                         {"H8 box-cooling 600 s, stage H8-C, 2026-11-01, "
                          "image 01cedce3..."})
        self.assertEqual({row["physical_output"] for row in rows}, {""},
                         "physical_output is an empty column in every row")

    def test_current_boundaries_and_both_means_are_published(self) -> None:
        drive = env.drive_stats(committed_frames())
        self.assertEqual(drive["driven_frames_in_source"], 600)
        self.assertEqual(drive["frames_used"], 599)
        self.assertEqual(drive["frames_excluded"], 1)
        self.assertEqual(drive["excluded_classes"], [env.PRE_RUN_HOLD])
        self.assertEqual(drive["current_a"]["min"], 7.14)
        self.assertEqual(drive["current_a"]["median"], 7.16)
        self.assertEqual(drive["current_a"]["p95"], 7.64)
        self.assertEqual(drive["current_a"]["max"], 9.99)
        # The 0.1220 A difference is exactly the one excluded pre-run frame:
        # quoting either mean without naming the exclusion would be a silent edit.
        self.assertEqual(drive["mean_current_a_inclusive_of_holdovers"], 7.2247)
        self.assertEqual(drive["mean_current_a_excluding_holdovers"], 7.2367)
        self.assertAlmostEqual(
            (drive["mean_current_a_excluding_holdovers"] * 599) / 600,
            drive["mean_current_a_inclusive_of_holdovers"], delta=0.0002)

    def test_voltage_and_power_boundaries(self) -> None:
        drive = env.drive_stats(committed_frames())
        self.assertEqual(drive["voltage_v"]["min"], 11.76)
        self.assertEqual(drive["voltage_v"]["median"], 11.79)
        self.assertEqual(drive["voltage_v"]["max"], 11.81)
        self.assertEqual(drive["power_w"]["median"], 84.4)
        self.assertEqual(drive["power_w"]["mean"], 85.3015)
        self.assertEqual(drive["power_w"]["max"], 117.4)

    def test_off_envelope_is_the_meter_floor_not_the_holdover(self) -> None:
        off = env.off_stats(committed_frames())
        self.assertEqual(off["off_frames"], 357)
        self.assertEqual(off["steady_frames_used"], 355)
        self.assertEqual(off["excluded_register_frames"], 2)
        self.assertEqual(off["steady_max_current_a"], 0.02)
        self.assertEqual(off["excluded_max_current_a"], 7.15)
        self.assertEqual(off["steady_floor_a"], 0.05)
        self.assertLess(off["steady_max_current_a"], off["bench_off_current_limit_a"])

    def test_hot_side_is_reported_as_a_single_channel_never_averaged(self) -> None:
        thermal = env.thermal_response(committed_frames())
        self.assertEqual(thermal["t2"]["max_c"], 39.938)
        self.assertEqual(thermal["t2"]["as_built_role"], "TEC_HOT_SIDE")
        self.assertEqual(thermal["t2"]["device_reported_role"], ["HOT_SIDE"])
        self.assertTrue(thermal["t2"]["role_is_hot_side"])
        for channel in ("t1", "t3", "t4"):
            self.assertEqual(thermal[channel]["device_reported_role"], ["UNASSIGNED"])
            self.assertFalse(thermal[channel]["role_is_hot_side"])
            self.assertFalse(thermal[channel]["averaged_into_any_statistic"])
        # T2 warms while the chamber cools: any pooled "mean chamber temperature"
        # would hide that, so the two populations must stay apart.
        self.assertGreater(thermal["t2"]["max_c"], thermal["t2"]["first_c"])
        self.assertLess(thermal["t1"]["min_c"], thermal["t1"]["first_c"])


class LatencyExclusion(unittest.TestCase):
    def test_documented_holdover_frame_is_named_and_not_averaged(self) -> None:
        rows = [row for row in env.duty_zero_with_current(committed_frames())]
        self.assertEqual(len(rows), 2, "exactly two duty-0 frames sit above the floor")
        holdover = next(row for row in rows if row["seq"] == "827")
        self.assertEqual(holdover["clock_ms"], 826894.0)
        self.assertEqual(holdover["state"], "COOLDOWN")
        self.assertEqual(holdover["duty_applied_permille"], 0)
        self.assertEqual(holdover["current_a"], 7.15)
        self.assertEqual(holdover["power_w"], 84.2)
        self.assertEqual(holdover["energy_wh"], 122.0)
        self.assertEqual(holdover["classification"], env.OFF_HOLD)
        self.assertIn("byte-identical", holdover["note"])
        self.assertFalse(holdover["electrical_status_recorded"])
        # Now prove it is excluded, not averaged: the OFF ceiling is the meter
        # floor, and no mean contains 7.15.
        off = env.off_stats(committed_frames())
        self.assertLess(off["steady_max_current_a"], holdover["current_a"])
        drive = env.drive_stats(committed_frames())
        self.assertNotIn(env.OFF_HOLD, drive["excluded_classes"],
                         "a duty-0 frame must never be counted as a driven frame")

    def test_holdover_byte_identity_claim_is_field_specific(self) -> None:
        """Identical on every measured field; only BME and bookkeeping move."""
        rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8", newline="")))
        by_ms = {row["device_ms"]: row for row in rows}
        held = by_ms["826894"]
        for previous in ("825894", "824894"):
            for field in ("voltage_v", "current_a", "power_w", "energy_wh",
                          "t1_c", "t2_c", "t3_c", "t4_c",
                          "t1_status", "t2_status", "t3_status", "t4_status"):
                self.assertEqual(held[field], by_ms[previous][field],
                                 f"{field} differs from {previous}")
            # ...and the environment channels did keep moving, which is what
            # proves the frame is a register repeat rather than a whole-frame
            # duplicate of the previous row.
            for field in ("bme_air_c", "bme_rh_pct", "bme_pressure_hpa"):
                self.assertNotEqual(held[field], by_ms[previous][field],
                                    f"{field} should still be moving")

    def test_pre_run_frame_is_first_of_block_only(self) -> None:
        rows = [row for row in committed_frames()
                if row.classification == env.PRE_RUN_HOLD]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].clock_ms, 226894.0)
        self.assertEqual(rows[0].seq, "227")
        self.assertEqual(rows[0].current_a, 0.0)
        self.assertEqual(rows[0].duty_applied, 999)

    def test_lsb_off_holdover_is_still_caught(self) -> None:
        """The H8-B case: one LSB off the previous frame, still a register repeat."""
        driven = env.Frame(source="FIXTURE", seq="1", clock_ms=506894.0,
                           duty_applied=999, voltage_v=11.79, current_a=7.12,
                           power_w=83.9)
        off = env.Frame(source="FIXTURE", seq="2", clock_ms=507894.0,
                        duty_applied=0, voltage_v=11.79, current_a=7.13,
                        power_w=84.0)
        classified = env.classify([driven, off])
        self.assertEqual(classified[1].classification, env.OFF_HOLD)
        self.assertIn("first post-OFF poll", classified[1].notes[0])
        stats = env.off_stats(classified)
        self.assertEqual(stats["steady_frames_used"], 0)
        self.assertEqual(stats["excluded_register_frames"], 1)

    def test_residual_far_from_a_drive_edge_is_flagged_not_steady(self) -> None:
        driven = env.Frame(source="FIXTURE", seq="1", clock_ms=1000.0,
                           duty_applied=999, voltage_v=11.8, current_a=7.0,
                           power_w=82.0)
        far = env.Frame(source="FIXTURE", seq="2", clock_ms=60000.0,
                        duty_applied=0, voltage_v=11.8, current_a=6.9, power_w=81.0)
        classified = env.classify([driven, far])
        self.assertEqual(classified[1].classification, env.OFF_RESIDUAL)
        self.assertEqual(env.off_stats(classified)["steady_frames_used"], 0)
        self.assertEqual(
            env.off_stats(classified)["excluded_classes"], [env.OFF_RESIDUAL])


class ConsistencyChecks(unittest.TestCase):
    def test_v_times_i_agrees_within_register_quantisation(self) -> None:
        power = env.power_consistency(committed_frames())
        self.assertEqual(power["frames_compared"], 957)
        self.assertEqual(power["frames_beyond_tolerance_count"], 0)
        self.assertEqual(power["max_abs_delta_w"], 0.099)
        self.assertEqual(power["quantisation_tolerance_w"], 0.18)
        self.assertEqual(power["verdict"], "NO_MISMATCH_BEYOND_REGISTER_QUANTISATION")
        aggregate = power["aggregate_check"]
        self.assertEqual(aggregate["mean_reported_power_w"], 85.3015)
        self.assertEqual(aggregate["mean_voltage_times_mean_current_w"], 85.3565)
        self.assertLess(abs(aggregate["delta_percent"]), 0.5)

    def test_a_real_mismatch_would_be_reported(self) -> None:
        frames = [env.Frame(source="FIXTURE", seq="1", clock_ms=0.0, duty_applied=999,
                            voltage_v=12.0, current_a=7.0, power_w=200.0)]
        classified = env.classify(frames)
        power = env.power_consistency(classified)
        self.assertEqual(power["verdict"], "MISMATCH_PRESENT")
        self.assertEqual(power["frames_beyond_tolerance_count"], 1)

    def test_energy_counter_matches_the_integral_within_its_quantum(self) -> None:
        energy = env.energy_consistency(committed_frames())
        self.assertEqual(energy["frames"], 957)
        self.assertEqual(energy["span_s"], 955.99)
        self.assertEqual(energy["energy_wh_first"], 108.0)
        self.assertEqual(energy["energy_wh_last"], 122.0)
        self.assertEqual(energy["counter_delta_wh"], 14.0)
        self.assertEqual(energy["trapezoidal_integral_of_power_wh"], 14.219)
        self.assertLessEqual(abs(energy["counter_minus_integral_wh"]),
                             energy["counter_quantisation_wh"])
        self.assertTrue(energy["monotonic_non_decreasing"])
        self.assertEqual(energy["distinct_counter_values"], 15)
        self.assertEqual(energy["verdict"], "COUNTER_WITHIN_QUANTISATION")


class UnqualifiedStatus(unittest.TestCase):
    def test_committed_csv_publishes_no_electrical_validity(self) -> None:
        coverage = env.status_coverage(committed_frames())["W04-H8C-box-600s"]
        self.assertFalse(coverage["electrical_status_recorded"])
        self.assertEqual(coverage["qualification_level"], env.QUALIFICATION_NONE)
        for name in ("voltage", "current", "power"):
            column = coverage["columns"][name]
            self.assertEqual(column["frames_without_a_label"], 957)
            self.assertEqual(column["label_counts"], {"(empty)": 957})
        self.assertIn("voltage", coverage["unqualified_columns"])
        self.assertIn("current", coverage["unqualified_columns"])
        self.assertIn("power", coverage["unqualified_columns"])

    def test_the_csv_has_no_power_energy_or_door_status_columns(self) -> None:
        header = CSV_PATH.read_text(encoding="utf-8").splitlines()[0].split(",")
        self.assertIn("voltage_status", header)
        self.assertIn("current_status", header)
        for absent in ("power_status", "energy_status", "door_status", "fan_status"):
            self.assertNotIn(absent, header)
        # ...and the two thermal-adjacent environment columns have no companion.
        self.assertIn("bme_air_c", header)
        self.assertNotIn("bme_air_status", header)
        frames = committed_frames()
        self.assertTrue(all(f.status["power_status_column_exists"] == "false"
                            for f in frames))
        self.assertTrue(all(f.status["energy_status_column_exists"] == "false"
                            for f in frames))
        self.assertTrue(all(f.status["door_status_column_exists"] == "false"
                            for f in frames))

    def test_wire_line_carries_the_tokens_the_csv_lost(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cg-w08-wire-") as tmp:
            path = pathlib.Path(tmp) / "samples.jsonl"
            path.write_text(json.dumps(monitor_record(SYNTHETIC_WIRE_LINE)) + "\n",
                            encoding="utf-8")
            frames = env.classify(env.read_raw_jsonl(path, "SYNTHETIC-FIXTURE"))
        self.assertEqual(len(frames), 1)
        frame = frames[0]
        self.assertEqual(frame.current_a, 7.15)
        self.assertEqual(frame.status["current"], "OK")
        self.assertEqual(frame.status["voltage"], "OK")
        self.assertEqual(frame.status["power"], "OK")
        self.assertEqual(frame.ages_ms["current"], 666.0)
        # A lone duty-0 frame above the floor with no drive edge to explain it is
        # reported as an unexplained residual, never folded into the OFF envelope.
        self.assertEqual(frame.classification, env.OFF_RESIDUAL)
        coverage = env.status_coverage([frame])["SYNTHETIC-FIXTURE"]
        self.assertTrue(coverage["electrical_status_recorded"])
        self.assertEqual(coverage["qualification_level"], env.QUALIFICATION_FIELD)
        # The fixture also proves the energy token genuinely does not exist:
        self.assertEqual(coverage["columns"]["energy"]["frames_without_a_label"], 1)

    def test_io_error_is_absence_not_zero(self) -> None:
        line = SYNTHETIC_WIRE_LINE.replace(
            "pwm_applied_permille=0", "pwm_applied_permille=0").replace(
            "current_a=7.150 current_a_status=OK", "current_a= current_a_status=IO_ERROR"
        ).replace("current_a_age_ms=666", "current_a_age_ms=-1")
        with tempfile.TemporaryDirectory(prefix="cg-w08-io-") as tmp:
            path = pathlib.Path(tmp) / "samples.jsonl"
            path.write_text(json.dumps(monitor_record(line)) + "\n", encoding="utf-8")
            frame = env.classify(env.read_raw_jsonl(path, "SYNTHETIC-FIXTURE"))[0]
        self.assertIsNone(frame.current_a)
        self.assertEqual(frame.status["current"], "IO_ERROR")
        self.assertEqual(frame.classification, env.NO_ELECTRICAL)

    def test_g1_production_build_publishes_no_value_at_all(self) -> None:
        frames = env.read_g1_csv(REPO / env.G1_TELEMETRY, "W04-G1-production-failclosed")
        self.assertEqual(len(frames), 62)
        self.assertTrue(all(f.current_a is None for f in frames))
        coverage = env.status_coverage(frames)["W04-G1-production-failclosed"]
        self.assertFalse(coverage["electrical_status_recorded"])
        self.assertEqual(coverage["valueless_columns"],
                         ["voltage", "current", "power", "energy"])
        self.assertIn("INVALID", coverage["columns"]["current"]["label_counts"])

    def test_w03_off_captures_are_poll_level_qualified(self) -> None:
        frames = env.read_w03_off(REPO / env.W03_OFF_132B,
                                  "W03-132b-off-envelope")
        coverage = env.status_coverage(frames)["W03-132b-off-envelope"]
        self.assertEqual(coverage["qualification_level"], env.QUALIFICATION_POLL)
        self.assertTrue(coverage["electrical_status_recorded"])
        self.assertTrue(all(f.current_a == 0.0 for f in frames))
        self.assertEqual(env.off_stats(env.classify(frames))["steady_max_current_a"], 0.0)


class ArtifactHonesty(unittest.TestCase):
    def test_binary_photograph_does_not_create_text_path_failures(self) -> None:
        photograph = DOSSIER / "attachments" / "fuse-block-holder-20261105.png"
        self.assertTrue(photograph.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        module = self._load_validator()
        failures: list[str] = []
        module.check_no_absolute_paths(failures)
        self.assertEqual(failures, [])

    """No generated artifact may claim PHYSICALLY_VERIFIED - proved, not asserted."""

    def test_dossier_on_disk_is_clean_and_validates(self) -> None:
        module = self._load_validator()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = module.main()
        self.assertEqual(code, 0, buffer.getvalue())
        for name in ("operating-envelope-v1.yaml", "thermal-sustainability.csv",
                     "fuse-selection.md", "Gate-A-report.md",
                     "electrical-status-coverage.csv", "duty-zero-current-frames.csv"):
            text = (DOSSIER / name).read_text(encoding="utf-8")
            for line in text.splitlines():
                if env.FORBIDDEN_STATUS in line:
                    self.assertTrue(
                        any(n in line.lower() for n in ("not", "never", "no ")),
                        f"{name} asserts the physical label: {line[:80]!r}")

    def test_injected_physical_claim_makes_the_validator_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cg-w08-mutate-") as tmp:
            work = pathlib.Path(tmp) / "W08"
            shutil.copytree(DOSSIER, work)
            target = work / "electrical-status-coverage.csv"
            target.write_text(
                target.read_text(encoding="utf-8")
                + "W04-H8C-box-600s,957,none,voltage,957,957,{},true,PHYSICALLY_VERIFIED\n",
                encoding="utf-8", newline="\n")
            # Re-pin every hash so the only possible failure is the claim itself.
            sums = []
            for path in sorted(p for p in work.iterdir() if p.is_file()):
                if path.name == "SHA256SUMS.txt":
                    continue
                sums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                            f"{path.name}")
            (work / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n",
                                                 encoding="utf-8", newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            self.assertEqual(code, 1, buffer.getvalue())
            self.assertIn("PHYSICALLY_VERIFIED", buffer.getvalue())

    def test_missing_honest_verdict_makes_the_validator_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cg-w08-verdict-") as tmp:
            work = pathlib.Path(tmp) / "W08"
            shutil.copytree(DOSSIER, work)
            acceptance = work / "acceptance.md"
            text = acceptance.read_text(encoding="utf-8").replace(
                "Gate A: **NOT CLOSED**", "Gate A: **CLOSED**")
            acceptance.write_text(text, encoding="utf-8", newline="\n")
            sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
                    for p in sorted(work.iterdir())
                    if p.is_file() and p.name != "SHA256SUMS.txt"]
            (work / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n",
                                                 encoding="utf-8", newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            self.assertEqual(code, 1, buffer.getvalue())

    def _remutate(self, tmp: str, mutate, prefix: str) -> tuple[int, str]:
        """Copy the dossier, mutate one file, re-pin everything, run the validator."""
        with tempfile.TemporaryDirectory(prefix=prefix) as dirn:
            work = pathlib.Path(dirn) / "W08"
            shutil.copytree(DOSSIER, work)
            mutate(work)
            sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
                    for p in sorted(work.iterdir())
                    if p.is_file() and p.name != "SHA256SUMS.txt"]
            (work / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n",
                                                 encoding="utf-8", newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            return code, buffer.getvalue()

    def test_absolute_developer_path_makes_the_validator_fail(self) -> None:
        def mutate(work: pathlib.Path) -> None:
            readme = work / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8")
                + "\nThe capture lives at X:\\Users\\someone\\repo\\evidence\\A\\W04"
                  "\non this machine.\n",
                encoding="utf-8", newline="\n")

        code, output = self._remutate("abs", mutate, "cg-w08-abs-")
        self.assertEqual(code, 1, output)
        self.assertIn("absolute developer path", output)

    def test_a_relative_repository_path_does_not_trip_the_absolute_check(self) -> None:
        # The check keys on drive-qualified and home-directory locators only, so
        # the honest repository-relative paths and https URLs still validate.
        self.assertEqual(env.absolute_path_hits(env.H8_CSV), [])
        self.assertEqual(env.absolute_path_hits("see https://example.com/a/b"), [])

    def test_unpinned_artifact_makes_the_validator_fail(self) -> None:
        def mutate(work: pathlib.Path) -> None:
            (work / "electrical-status-coverage.csv").write_text(
                (work / "electrical-status-coverage.csv").read_text(
                    encoding="utf-8") + "# appended\n", encoding="utf-8", newline="\n")

        # The re-pin in _remutate is what this mutates away for one file: drop it.
        with tempfile.TemporaryDirectory(prefix="cg-w08-unpinned-") as dirn:
            work = pathlib.Path(dirn) / "W08"
            shutil.copytree(DOSSIER, work)
            mutate(work)
            lines = [line for line in (work / "SHA256SUMS.txt").read_text(
                encoding="utf-8").splitlines()
                if not line.endswith("electrical-status-coverage.csv")]
            (work / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n",
                                                 encoding="utf-8", newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            self.assertEqual(code, 1, buffer.getvalue())
            self.assertIn("not hash-pinned", buffer.getvalue())

    def test_pin_for_a_file_that_should_not_exist_makes_the_validator_fail(self) -> None:
        def mutate(work: pathlib.Path) -> None:
            (work / "raw-capture.bin").write_bytes(b"not a pinned artifact\n")

        with tempfile.TemporaryDirectory(prefix="cg-w08-straypin-") as dirn:
            work = pathlib.Path(dirn) / "W08"
            shutil.copytree(DOSSIER, work)
            mutate(work)
            sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
                    for p in sorted(work.iterdir())
                    if p.is_file() and p.name != "SHA256SUMS.txt"]
            (work / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n",
                                                 encoding="utf-8", newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            self.assertEqual(code, 1, buffer.getvalue())
            self.assertIn("flash image committed into the dossier", buffer.getvalue())

    def test_pinned_pycache_entry_makes_the_validator_fail(self) -> None:
        # F3: a __pycache__ byte must never pass as a pinned dossier artifact.
        # Copy the dossier, add an evil cache file and pin its correct hash - the
        # pin itself must be rejected, not silently verified.
        with tempfile.TemporaryDirectory(prefix="cg-w08-pyc-") as dirn:
            work = pathlib.Path(dirn) / "W08"
            shutil.copytree(DOSSIER, work)
            cache = work / "__pycache__"
            cache.mkdir(exist_ok=True)
            (cache / "evil.cpython-314.pyc").write_bytes(b"not evidence")
            lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  "
                     f"{p.relative_to(work).as_posix()}"
                     for p in sorted(work.rglob("*"))
                     if p.is_file() and p.name != "SHA256SUMS.txt"]
            (work / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n",
                                                 encoding="utf-8", newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            self.assertEqual(code, 1, buffer.getvalue())
            self.assertIn("Python cache", buffer.getvalue())

    def test_a_file_without_a_pin_makes_the_validator_fail(self) -> None:
        # F3 both-direction: pinning every dossier file means an added, unpinned
        # artifact is caught even though no GENERATED name was touched.
        with tempfile.TemporaryDirectory(prefix="cg-w08-added-") as dirn:
            work = pathlib.Path(dirn) / "W08"
            shutil.copytree(DOSSIER, work)
            (work / "extra-notes.md").write_text("unpinned\n", encoding="utf-8",
                                                 newline="\n")
            module = self._load_validator()
            module.DOSSIER = work
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = module.main()
            self.assertEqual(code, 1, buffer.getvalue())
            self.assertIn("not hash-pinned", buffer.getvalue())

    def test_empty_bench_root_reports_byte_checks_not_run(self) -> None:
        # F2: pointed at an empty scratch bench tree the 18 per-original SHA-256
        # checks cannot run, and the validator must print the NOT RUN note rather
        # than bundling the skip into the OK line.
        module = self._load_validator()
        with tempfile.TemporaryDirectory(prefix="cg-w08-emptybench-") as dirn:
            saved = os.environ.get("CG_W08_BENCH_ROOT")
            os.environ["CG_W08_BENCH_ROOT"] = dirn
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer):
                    code = module.main()
            finally:
                if saved is None:
                    os.environ.pop("CG_W08_BENCH_ROOT", None)
                else:
                    os.environ["CG_W08_BENCH_ROOT"] = saved
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("local-bench original byte-checks: NOT RUN", buffer.getvalue())

    @staticmethod
    def _load_validator():
        path = DOSSIER / "validate_w08.py"
        spec = importlib.util.spec_from_file_location("validate_w08_under_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


class EnvelopeShape(unittest.TestCase):
    def test_every_driven_frame_is_accounted_for(self) -> None:
        report = committed_envelope()
        for source, summary in report["sources"].items():
            drive = summary["drive"]
            self.assertEqual(drive["frames_used"] + drive["frames_excluded"],
                             drive["driven_frames_in_source"], source)

    def test_status_label_vocabulary_is_respected(self) -> None:
        report = committed_envelope()
        self.assertEqual(report["status_label"], "REAL_DATA_ANALYZED")
        self.assertNotIn(env.FORBIDDEN_STATUS, json.dumps(report))
        text = env.render_yaml(report)
        for line in text.splitlines():
            if "status:" in line and env.FORBIDDEN_STATUS in line:
                self.fail(f"the envelope yaml promotes a status: {line!r}")

    def test_guard_rejects_a_poisoned_report(self) -> None:
        report = dict(committed_envelope())
        report["status_label"] = env.FORBIDDEN_STATUS
        with self.assertRaises(ValueError):
            env.assert_no_physical_claim(report)

    def test_local_bench_rows_are_flagged_unreproducible(self) -> None:
        declaration = json.loads(
            (DOSSIER / "local-bench-observations.json").read_text(encoding="utf-8"))
        self.assertEqual(declaration["provenance"]["reproducible_from_git"], False)
        self.assertEqual(declaration["provenance"]["originals_copied_into_repository"],
                         False)
        self.assertEqual(len(declaration["sessions"]), 18)
        for label, bundle in declaration["sessions"].items():
            self.assertTrue(bundle["sha256"], label)
            self.assertGreater(bundle["frames"], 0, label)
        raw = declaration["sessions"]["W04-H8C-box-600s-raw"]["source_summary"]
        git = committed_envelope()["sources"]["W04-H8C-box-600s"]
        # The declared raw stream must reproduce the committed CSV exactly: that is
        # what makes the rest of the declaration checkable rather than asserted.
        for key in ("current_a", "voltage_v", "power_w"):
            self.assertEqual(raw["drive"][key], git["drive"][key], key)
        self.assertEqual(raw["thermal"]["t2"], git["thermal"]["t2"])


if __name__ == "__main__":
    unittest.main()
