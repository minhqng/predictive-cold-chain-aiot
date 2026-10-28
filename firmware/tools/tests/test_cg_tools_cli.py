"""End-to-end tests for the ColdGuard W02 host tools.

Every fixture here is synthetic and is written to a temporary directory.
These tests prove the operator-facing commands work on a real log file,
including their exit codes, without needing hardware or a COM port.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_capture  # noqa: E402
import cg_serial  # noqa: E402

ROM_T1 = "287088CA00000051"
ROM_T2 = "28AEBF2200000006"
ROM_T3 = "28CBE9CA00000072"
ROM_SPARE = "283BE5C9000000A9"
PENDING = "ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING"


def boot_block(index: int) -> str:
    lines = [f"#CG BOOT boot_id=boot{index:04d} boot_count={index}"]
    for role, rom in (("T1", ROM_T1), ("T2", ROM_T2), ("T3", ROM_T3), ("SPARE", ROM_SPARE)):
        lines.append(f"#CG ROM role={role} rom={rom} present=1 status={PENDING}")
    lines.append("#CG ROMS required_present=3/3 known=4 known_present=4")
    return "\n".join(lines) + "\n"


def sensor_log(samples: int = 600, period_ms: int = 1000) -> str:
    text = "#CG LOG v=1 fw=cg-w02-0.1.0 hw=CG-HW-001 pin_map=1 grammar=1\n"
    text += "#CG SAFETY actuator=OFF pwm=5 en=6\n"
    text += boot_block(0)
    text += "#CG DOOR_POLARITY state=UNVERIFIED raw_open_level=0\n"
    for index in range(samples):
        t1 = 29.8125 + (index % 3) * 0.0625
        t2 = 30.1875 + (index % 2) * 0.0625
        t3 = 29.5625
        text += (
            f"#CG SAMPLE uptime_ms={index * period_ms} seq={index + 1} "
            f"T1={t1:.4f} T2={t2:.4f} T3={t3:.4f} SPARE=nan t1=1 t2=1 t3=1 "
            f"thermal=VALID door_raw=1 door=UNVERIFIED\n"
        )
    return text


def door_log(cycles: int = 24, debounce_ms: int = 50, poll_ms: int = 5) -> str:
    """Build a log from the documented debounce model.

    Each cycle injects a short bounce burst (three raw flips inside the
    debounce window) and then a stable level, so the log contains real
    bounce evidence that the debounce window is supposed to absorb.
    """

    text = "#CG LOG v=1 fw=cg-w02-0.1.0 hw=CG-HW-001 pin_map=1 grammar=1\n"
    text += boot_block(0)
    text += "#CG DOOR_POLARITY state=UNVERIFIED raw_open_level=0\n"

    now_us = 1_000_000
    committed = 1
    transitions = 0
    raw_edges = 0
    for _ in range(cycles):
        for _ in range(2):  # one open + one close per cycle
            target = 0 if committed == 1 else 1
            # A short bounce burst: the level reaches the target, jumps
            # back once, and returns - all inside the debounce window.
            for level in (target, committed, target):
                raw_edges += 1
                text += f"#CG DOOR_EDGE uptime_us={now_us} raw={level}\n"
                now_us += poll_ms * 1000
            # The final edge starts the stability window.
            raw_edges += 1
            text += f"#CG DOOR_EDGE uptime_us={now_us} raw={target}\n"
            now_us += poll_ms * 1000
            now_us += debounce_ms * 1000
            committed = target
            transitions += 1
            text += (
                f"#CG DOOR_STATE uptime_ms={now_us // 1000} raw={committed} state=UNVERIFIED "
                f"transitions={transitions} cycles={transitions // 2} "
                f"discarded={raw_edges - transitions}\n"
            )
            now_us += 1_200_000  # operator holds the door for ~1.2 s
    return text


class CliRunner:
    def __init__(self, workdir: pathlib.Path) -> None:
        self.workdir = workdir

    def write(self, name: str, text: str) -> pathlib.Path:
        path = self.workdir / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def run(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOLS / script), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )


class VerifyRebootsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runner = CliRunner(pathlib.Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_five_stable_boots_pass(self) -> None:
        log = self.runner.write("stable.log", "".join(boot_block(index) for index in range(1, 6)))
        result = self.runner.run("cg_verify_reboots.py", str(log))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("IDENTITY_STABLE", result.stdout)
        self.assertIn("REBOOT IDENTITY: PASS", result.stdout)

    def test_four_boots_do_not_pass(self) -> None:
        log = self.runner.write("short.log", "".join(boot_block(index) for index in range(1, 5)))
        result = self.runner.run("cg_verify_reboots.py", str(log))
        self.assertEqual(result.returncode, 1)
        self.assertIn("INSUFFICIENT_BOOTS", result.stdout)

    def test_json_report_is_written(self) -> None:
        log = self.runner.write("stable.log", "".join(boot_block(index) for index in range(1, 6)))
        json_path = pathlib.Path(self.tmp.name) / "report.json"
        result = self.runner.run("cg_verify_reboots.py", str(log), "--json", str(json_path))
        self.assertEqual(result.returncode, 0)
        self.assertIn("IDENTITY_STABLE", json_path.read_text(encoding="utf-8"))

    def test_duplicated_boot_blocks_are_rejected(self) -> None:
        log = self.runner.write("dup.log", boot_block(1) * 5)
        result = self.runner.run("cg_verify_reboots.py", str(log))
        self.assertEqual(result.returncode, 1)
        self.assertIn("BOOT_METADATA_INVALID", result.stdout)
        self.assertIn("BOOT_ID_DUPLICATED", result.stdout)

    def test_zero_boot_count_is_rejected(self) -> None:
        text = "".join(boot_block(index) for index in range(1, 6)).replace("boot_count=3", "boot_count=0")
        log = self.runner.write("zero.log", text)
        result = self.runner.run("cg_verify_reboots.py", str(log))
        self.assertEqual(result.returncode, 1)
        self.assertIn("BOOT_METADATA_INVALID", result.stdout)
        self.assertIn("BOOT_COUNT_ZERO", result.stdout)


class SensorCsvCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runner = CliRunner(pathlib.Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sixty_samples_declared_below_minimum(self) -> None:
        log = self.runner.write("short.log", sensor_log(samples=60))
        csv_path = pathlib.Path(self.tmp.name) / "sensor-consistency.csv"
        result = self.runner.run("cg_build_sensor_csv.py", str(log), "--out", str(csv_path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("WINDOW NOT USABLE", result.stdout)

    def test_six_hundred_samples_builds_csv(self) -> None:
        log = self.runner.write("long.log", sensor_log(samples=600))
        csv_path = pathlib.Path(self.tmp.name) / "sensor-consistency.csv"
        result = self.runner.run("cg_build_sensor_csv.py", str(log), "--out", str(csv_path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WINDOW USABLE", result.stdout)

        text = csv_path.read_text(encoding="utf-8")
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "uptime_ms,seq,t1_c,t2_c,t3_c,t1_valid,t2_valid,t3_valid,thermal")
        self.assertEqual(len(lines), 601)
        self.assertIn("599.0 s", result.stdout)  # 600 samples at 1 Hz
        self.assertNotIn("nan", text.lower())

    def test_invalid_probe_becomes_empty_cell(self) -> None:
        text = sensor_log(samples=5).replace("T2=30.1875", "T2=nan").replace("t2=1", "t2=0")
        log = self.runner.write("degraded.log", text)
        csv_path = pathlib.Path(self.tmp.name) / "out.csv"
        result = self.runner.run("cg_build_sensor_csv.py", str(log), "--out", str(csv_path), "--min-samples", "1")
        self.assertEqual(result.returncode, 1)  # invalid readings present in the window
        rows = csv_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[1].split(",")[3], "")  # empty, never 0
        self.assertEqual(rows[1].split(",")[6], "0")


class DoorCsvCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runner = CliRunner(pathlib.Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_twenty_four_cycles_without_polarity_does_not_claim_semantics(self) -> None:
        log = self.runner.write("door.log", door_log(cycles=24))
        csv_path = pathlib.Path(self.tmp.name) / "door-test.csv"
        result = self.runner.run("cg_build_door_csv.py", str(log), "--out", str(csv_path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("NOT PROVEN (semantic polarity UNVERIFIED)", result.stdout)
        text = csv_path.read_text(encoding="utf-8")
        self.assertIn("UNVERIFIED", text)
        self.assertNotIn("OPEN", text)
        self.assertNotIn("CLOSED", text)

    def test_twenty_four_cycles_with_declared_polarity_passes(self) -> None:
        log = self.runner.write("door.log", door_log(cycles=24))
        csv_path = pathlib.Path(self.tmp.name) / "door-test.csv"
        result = self.runner.run(
            "cg_build_door_csv.py", str(log), "--out", str(csv_path), "--open-level", "0"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CYCLES PROVEN (24 >= 20)", result.stdout)
        self.assertIn("bounce observed       : True", result.stdout)

        rows = csv_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(rows[0], "uptime_ms,raw,state,transitions,cycles,discarded_edges")
        self.assertEqual(len(rows), 49)  # 48 committed transitions
        for row in rows[1:]:
            fields = row.split(",")
            self.assertIn(fields[2], ("OPEN", "CLOSED"))
            int(fields[3])
            int(fields[4])
            int(fields[5])

    def test_nineteen_cycles_fail_the_requirement(self) -> None:
        log = self.runner.write("door.log", door_log(cycles=19))
        csv_path = pathlib.Path(self.tmp.name) / "door-test.csv"
        result = self.runner.run(
            "cg_build_door_csv.py", str(log), "--out", str(csv_path), "--open-level", "1"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("NOT PROVEN (19 cycles < 20)", result.stdout)

    def test_empty_log_is_a_usage_failure(self) -> None:
        log = self.runner.write("empty.log", "#CG LOG v=1\n")
        csv_path = pathlib.Path(self.tmp.name) / "door-test.csv"
        result = self.runner.run("cg_build_door_csv.py", str(log), "--out", str(csv_path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing to build", result.stderr)

    def test_multi_boot_capture_is_refused_without_boot_selector(self) -> None:
        log = self.runner.write("multi.log", door_log(cycles=24) + door_log(cycles=24))
        csv_path = pathlib.Path(self.tmp.name) / "door-test.csv"
        result = self.runner.run("cg_build_door_csv.py", str(log), "--out", str(csv_path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("multiple boots", result.stderr)

    def test_boot_selector_restores_multi_boot_analysis(self) -> None:
        log = self.runner.write("multi.log", door_log(cycles=24) + door_log(cycles=24))
        csv_path = pathlib.Path(self.tmp.name) / "door-test.csv"
        result = self.runner.run(
            "cg_build_door_csv.py",
            str(log),
            "--out",
            str(csv_path),
            "--open-level",
            "0",
            "--boot",
            "1",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CYCLES PROVEN (24 >= 20)", result.stdout)
        rows = csv_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(rows), 49)  # only boot1's 48 committed transitions


class CaptureTests(unittest.TestCase):
    def test_replay_wraps_the_stream_with_metadata(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            out_path = pathlib.Path(tmp.name) / "capture.log"
            with out_path.open("w", encoding="utf-8", newline="\n") as out:
                count = cg_capture.replay(boot_block(1).splitlines(keepends=True), out, "COM9", 115200, 30)
            self.assertEqual(count, len(boot_block(1).splitlines()))

            parsed = cg_serial.read_log(str(out_path))
            self.assertEqual(parsed.captures[0]["port"], "COM9")
            self.assertEqual(parsed.captures[0]["baud"], "115200")
            self.assertEqual(parsed.captures[-1]["lines"], str(count))
            self.assertEqual(len(parsed.boots), 1)
        finally:
            tmp.cleanup()

    def test_capture_cli_from_file_end_to_end(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            workdir = pathlib.Path(tmp.name)
            source = workdir / "device.log"
            source.write_text(
                "".join(boot_block(index) for index in range(1, 6)), encoding="utf-8", newline="\n"
            )
            out_path = workdir / "capture.log"
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "cg_capture.py"),
                    "--from-file",
                    str(source),
                    "--out",
                    str(out_path),
                    "--port",
                    "COM7",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            verify = subprocess.run(
                [sys.executable, str(TOOLS / "cg_verify_reboots.py"), str(out_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(verify.returncode, 0)
            self.assertIn("IDENTITY_STABLE", verify.stdout)
            self.assertIn("COM7", out_path.read_text(encoding="utf-8"))
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
