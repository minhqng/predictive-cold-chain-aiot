"""Statistical analysis and role authority."""

from __future__ import annotations

import pathlib
import sys
import unittest

from .helpers import telem_line

from member_a_app import analysis, protocol

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def frame(**kwargs: object) -> protocol.TelemetryFrame:
    parsed = protocol.parse_line(telem_line(**kwargs))
    assert parsed.frame is not None
    return parsed.frame


def series(count: int, **kwargs: object) -> list[protocol.TelemetryFrame]:
    out = []
    for index in range(count):
        values = dict(kwargs)
        values["seq"] = index + 1
        values["uptime_ms"] = 1_000_000 + index * 1000
        for key, value in list(values.items()):
            if isinstance(value, (list, tuple)):
                values[key] = value[min(index, len(value) - 1)]
        out.append(frame(**values))
    return out


class RoleAuthorityTests(unittest.TestCase):
    def test_chamber_air_excludes_hot_side(self) -> None:
        item = frame(t1=25.0, t2=40.0, t3=24.0, spare=26.0)
        self.assertEqual(analysis.chamber_temps(item), [25.0, 24.0, 26.0])
        self.assertAlmostEqual(analysis.tmean(item), 25.0)
        self.assertAlmostEqual(analysis.gradient(item), 2.0)
        self.assertEqual(analysis.hot_side(item), 40.0)

    def test_frozen_roles_match_repository_authority(self) -> None:
        tools = REPO_ROOT / "firmware" / "tools"
        if not (tools / "cg_probe_roles.py").is_file():
            self.skipTest("repository role authority is not present")
        sys.path.insert(0, str(tools))
        try:
            import cg_probe_roles  # type: ignore
        finally:
            sys.path.pop(0)
        self.assertEqual(cg_probe_roles.ROM_POSITION_BY_ROM,
                         {rom: {"T1": "CHAMBER_CENTER", "T2": "TEC_HOT_SIDE",
                                "T3": "CHAMBER_BOTTOM", "SPARE": "CHAMBER_NEAR_DOOR"}[role]
                          for role, rom in analysis.FROZEN_ROM_BY_ROLE.items()})
        self.assertEqual(set(cg_probe_roles.CHAMBER_AIR_SERIAL_ROLES),
                         {"T1", "T3", "SPARE"})
        self.assertEqual(cg_probe_roles.HOT_SIDE_SERIAL_ROLE, "T2")


class TimingAndElectricalTests(unittest.TestCase):
    def test_timing_metrics(self) -> None:
        frames = series(4)
        metrics = analysis.timing_metrics(frames)
        self.assertEqual(metrics["frames"], 4)
        self.assertAlmostEqual(metrics["interval_mean_s"], 1.0)
        self.assertEqual(metrics["seq_regressions"], 0)

    def test_electrical_metrics_power_consistency(self) -> None:
        frames = series(3, voltage=12.0, current=5.0)
        metrics = analysis.electrical_metrics(frames)
        self.assertTrue(metrics["valid_rate"] > 0.99)
        self.assertAlmostEqual(metrics["current_mean_a"], 5.0)
        self.assertAlmostEqual(metrics["power_mean_w"], 60.0)
        self.assertLess(metrics["power_consistency_max_rel_error"], 0.01)

    def test_acquisition_metrics(self) -> None:
        frames = series(5)
        metrics = analysis.acquisition_metrics(frames)
        self.assertEqual(metrics["seq_regressions"], 0)
        self.assertEqual(metrics["probes_valid_min"], 4)


class DoorAndStepTests(unittest.TestCase):
    def test_door_metrics(self) -> None:
        frames = series(6, door=[0, 0, 1, 1, 0, 0])
        metrics = analysis.door_metrics(frames)
        self.assertEqual(metrics["transitions"], 2)
        self.assertEqual(metrics["cycles"], 1)
        self.assertAlmostEqual(metrics["open_durations_s"][0], 2.0)

    def test_s2_metrics(self) -> None:
        frames = []
        for index in range(10):
            t1 = 20.0 + max(0, index - 3) * 0.5
            frames.append(frame(seq=index + 1, uptime_ms=1_000_000 + index * 1000,
                                t1=t1, t3=t1, spare=t1, door=1 if 4 <= index < 7 else 0))
        metrics = analysis.s2_metrics(frames)
        self.assertTrue(metrics["valid"])
        self.assertAlmostEqual(metrics["baseline_mean_c"], 20.0)
        self.assertGreater(metrics["peak_mean_c"], metrics["baseline_mean_c"])

    def test_door_to_critical(self) -> None:
        frames = []
        for index in range(10):
            t1 = 20.0 + max(0, index - 2) * 0.5
            frames.append(frame(seq=index + 1, uptime_ms=1_000_000 + index * 1000,
                                t1=t1, t3=t1, spare=t1, door=1 if index >= 3 else 0))
        value = analysis.door_to_critical(frames, 21.0)
        self.assertIsNotNone(value)
        self.assertGreater(value or 0, 0)

    def test_cooling_step_metrics(self) -> None:
        frames = []
        for index in range(20):
            cooling = "ON" if index >= 5 else "OFF"
            current = 5.0 if index >= 5 else 0.0
            t1 = 25.0 - max(0, index - 6) * 0.3
            frames.append(frame(seq=index + 1, uptime_ms=1_000_000 + index * 1000,
                                t1=t1, t3=t1, spare=t1, current=current, cooling=cooling,
                                state="COOLING" if cooling == "ON" else "OFF"))
        metrics = analysis.cooling_step_metrics(frames)
        self.assertEqual(metrics["cooling_frames"], 15)
        self.assertAlmostEqual(metrics["current_mean_a"], 5.0)
        self.assertGreater(metrics["chamber_drop_c"] or 0, 1.0)


if __name__ == "__main__":
    unittest.main()
