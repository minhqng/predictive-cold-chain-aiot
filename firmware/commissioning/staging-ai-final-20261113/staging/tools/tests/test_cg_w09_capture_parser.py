"""Tests for cg_w09_capture_parser.py (A-W09-02).

The parser is the layer that decides what a frame is allowed to mean later, so
these tests are about fidelity: nothing may be invented, nothing may be silently
defaulted, and the three real encodings must land in one vocabulary without the
telemetry contract being forked.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_telemetry_schema as schema  # noqa: E402
import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_fixtures as fx  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
W04_CSV = REPO_ROOT / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


def _provenance(**overrides) -> cp.SourceProvenance:
    defaults = dict(
        source_kind="h8s_fixture",
        source_path="tests/test_cg_w09_capture_parser.py",
        source_sha256=None,
        line_index=1,
        is_physical_measurement=False,
        run_label=fx.FIXTURE_RUN_LABEL_PREFIX + "UNIT",
    )
    defaults.update(overrides)
    return cp.SourceProvenance(**defaults)


class H8sLineParsing(unittest.TestCase):
    def test_parses_a_real_shaped_line(self):
        frame = cp.parse_h8s_line(fx.h8s_line(seq=7), _provenance())
        self.assertEqual(frame.seq, 7)
        self.assertEqual(frame.values["schema"], 3)
        self.assertEqual(frame.values["state"], "OFF")
        self.assertAlmostEqual(frame.values["t1"], 25.0)
        self.assertEqual(frame.values["t2_role"], "HOT_SIDE")

    def test_timestamp_utc_is_never_a_value(self):
        frame = cp.parse_h8s_line(fx.h8s_line(), _provenance())
        self.assertIsNone(frame.values["timestamp_utc"])
        self.assertEqual(frame.values["timestamp_utc_status"], "UNAVAILABLE")

    def test_line_with_a_device_wall_clock_is_rejected(self):
        line = fx.h8s_line().replace(
            "timestamp_utc=UNAVAILABLE", "timestamp_utc=2026-11-02T00:00:00Z"
        )
        with self.assertRaises(schema.TelemetryError):
            cp.parse_h8s_line(line, _provenance())

    def test_wrong_utc_source_token_is_rejected(self):
        line = fx.h8s_line().replace(
            "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK", "timestamp_utc_source=HOST_ASSIGNED"
        )
        with self.assertRaises(schema.TelemetryError):
            cp.parse_h8s_line(line, _provenance())

    def test_missing_required_field_is_rejected_not_repaired(self):
        line = fx.h8s_line().replace("door_raw=0 ", "")
        with self.assertRaises(schema.TelemetryError) as ctx:
            cp.parse_h8s_line(line, _provenance())
        self.assertIn("door_raw", str(ctx.exception))

    def test_duplicate_field_is_rejected(self):
        line = fx.h8s_line() + " seq=99"
        with self.assertRaises(schema.TelemetryError):
            cp.parse_h8s_line(line, _provenance())

    def test_truncated_line_is_rejected(self):
        with self.assertRaises(schema.TelemetryError):
            cp.parse_h8s_line(fx.h8s_line()[:120], _provenance())

    def test_bad_snapshot_token_is_rejected(self):
        with self.assertRaises(schema.TelemetryError):
            cp.parse_h8s_line(fx.h8s_line(snapshot="MAYBE"), _provenance())

    def test_door_open_token_vocabulary_is_closed(self):
        for token in ("2", "true", ""):
            line = fx.h8s_line().replace("door_open=0", f"door_open={token}")
            with self.assertRaises(schema.TelemetryError):
                cp.parse_h8s_line(line, _provenance())

    def test_unknown_extra_token_is_retained(self):
        line = fx.h8s_line() + " some_future_field=HELLO"
        frame = cp.parse_h8s_line(line, _provenance())
        self.assertEqual(frame.values["some_future_field"], "HELLO")

    def test_raw_line_is_kept_for_traceability(self):
        line = fx.h8s_line(seq=3)
        frame = cp.parse_h8s_line(line, _provenance())
        self.assertIn("seq=3", frame.raw)


class SamplesJsonlUsesTheRawField(unittest.TestCase):
    def test_json_projection_without_raw_is_refused(self):
        # door_raw / door_status / door_cycles exist only in the raw line, so a
        # parser that read the JSON projection would lose the door evidence.
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as workdir:
            path = pathlib.Path(workdir) / "samples.jsonl"
            path.write_text(
                json.dumps({"seq": 1, "door_open": "UNKNOWN", "boot_id": "x"}) + "\n",
                encoding="utf-8",
            )
            frames, report = cp.read_h8s_jsonl(path, "UNIT_JSONL")
            self.assertEqual(frames, [])
            self.assertIn("no '#CG H8S' raw line", report["rejected"][0]["reason"])

    def test_roundtrip_fixture_jsonl(self):
        import json
        import tempfile

        lines = [fx.h8s_line(seq=s) for s in range(1, 6)]
        with tempfile.TemporaryDirectory() as workdir:
            path = pathlib.Path(workdir) / "samples.jsonl"
            path.write_text(
                "".join(json.dumps({"raw": line}) + "\n" for line in lines), encoding="utf-8"
            )
            frames, report = cp.read_h8s_jsonl(path, "UNIT_JSONL")
            self.assertEqual(len(frames), 5)
            self.assertEqual(report["rejected"], [])
            self.assertEqual(len(report["source_sha256"]), 64)


class TranscriptHostTime(unittest.TestCase):
    def test_host_prefix_is_kept_separate_from_device_time(self):
        provenance = _provenance()
        line = "2026-11-01T09:10:24Z " + fx.h8s_line(seq=2)
        frame = cp.parse_frame_line(line, provenance)
        self.assertEqual(frame.values["host_capture_time_utc"], "2026-11-01T09:10:24Z")
        self.assertIsNone(frame.values["timestamp_utc"])
        self.assertEqual(
            frame.values["host_capture_time_semantics"],
            "HOST_CLOCK_ADDED_AT_CAPTURE_NOT_DEVICE_TIME",
        )

    def test_malformed_host_time_is_rejected(self):
        with self.assertRaises(schema.TelemetryError):
            cp.parse_frame_line("not-a-date #CG H8S schema=3", _provenance())

    def test_strip_leaves_a_bare_device_line_alone(self):
        host_time, device = cp.strip_host_capture_time(fx.h8s_line())
        self.assertIsNone(host_time)
        self.assertTrue(device.startswith("#CG H8S"))

    def test_timestamp_on_a_non_device_line_is_not_a_capture_time(self):
        host_time, device = cp.strip_host_capture_time("2026-11-01T09:10:24Z some boot noise")
        self.assertIsNone(host_time)
        self.assertTrue(device.startswith("2026-11"))


class TelemDelegation(unittest.TestCase):
    def test_telem_line_goes_through_the_schema_module(self):
        self.assertTrue((W04_CSV.exists()))
        captured = REPO_ROOT / "evidence" / "A" / "W04" / "g1" / "41-g1-reset.log"
        if not captured.is_file():
            self.skipTest("committed W04 g1 capture not present")
        frames, report = cp.read_transcript(captured, "G1_RESET", is_physical_measurement=True)
        self.assertGreater(report["records"], 0)
        self.assertEqual(report["rejected"], [])
        self.assertTrue(all(f.values["schema"] in (1, 2, 3) for f in frames))

    def test_the_parser_does_not_reimplement_the_telem_contract(self):
        # A schema-2 line the shipped contract rejects must also be rejected here:
        # if this module had its own field list it would start accepting lines the
        # firmware never emitted.
        provenance = _provenance()
        with self.assertRaises(schema.TelemetryError):
            cp.parse_frame_line("#CG TELEM schema=2 seq=1", provenance)


class CsvNormalization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, cls.report = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")

    def test_reads_the_committed_capture_completely(self):
        self.assertEqual(self.report["records"], 957)
        self.assertEqual(self.report["rejected"], [])
        self.assertEqual(len(self.frames), 957)

    def test_source_is_hash_pinned(self):
        self.assertEqual(len(self.report["source_sha256"]), 64)
        self.assertEqual(self.frames[0].provenance.source_sha256, self.report["source_sha256"])

    def test_column_aliases_are_applied(self):
        first = self.frames[0]
        self.assertIn("voltage_v_status", first.values)
        self.assertIn("air_c", first.values)
        self.assertIsNotNone(first.values.get("t1"))

    def test_empty_status_cells_stay_none_not_ok(self):
        # The committed CSV has voltage_status/current_status empty in every row.
        # Coercing that to OK is how an unqualified number becomes a measurement.
        for frame in self.frames[:20]:
            self.assertIsNone(frame.values["voltage_v_status"])
            self.assertIsNone(frame.values["current_a_status"])

    def test_door_status_and_power_status_absent_from_the_csv_encoding(self):
        frame = self.frames[100]
        self.assertFalse(frame.has("door_status"))
        self.assertFalse(frame.has("power_status"))

    def test_dedup_key_records_the_absent_device_id(self):
        self.assertEqual(self.frames[0].dedup_key[0], "SOURCE_DOES_NOT_CARRY_DEVICE_ID")
        self.assertEqual(self.frames[0].dedup_key[1], "56044b74")
        self.assertEqual(self.frames[0].dedup_key[2], 1)

    def test_the_csv_is_a_physical_source_by_default(self):
        self.assertTrue(self.frames[0].provenance.is_physical_measurement)

    def test_run_label_is_carried_on_every_frame(self):
        self.assertEqual({f.provenance.run_label for f in self.frames}, {"H8C_BOX_COOLING_600S"})


class MaskDecoding(unittest.TestCase):
    def test_bits_name_the_failed_source(self):
        self.assertEqual(cp.mask_names(0x80), ["DOOR"])
        # 0x780 is bits 7-10: the direct-magnet boot could not read the door nor
        # the PZEM at all, and the mask says exactly that.
        self.assertEqual(cp.mask_names(0x780), ["DOOR", "PZEM_V", "PZEM_I", "PZEM_P"])
        self.assertEqual(cp.mask_names(0x1), ["T1"])
        self.assertEqual(cp.mask_names(0xF), ["T1", "T2", "T3", "SPARE"])
        self.assertEqual(cp.mask_names(0), [])
        self.assertEqual(cp.mask_names(None), [])

    def test_group_by_run_splits_on_boot_and_run_id(self):
        frames = [
            cp.parse_h8s_line(fx.h8s_line(seq=1, boot_id="a", run_id="r0"), _provenance()),
            cp.parse_h8s_line(fx.h8s_line(seq=2, boot_id="a", run_id="r0"), _provenance()),
            cp.parse_h8s_line(fx.h8s_line(seq=1, boot_id="b", run_id="r1"), _provenance()),
        ]
        groups = cp.group_by_run(frames)
        self.assertEqual(len(groups), 2)
        self.assertEqual([len(v) for v in groups.values()], [2, 1])

    def test_boot_identity_reads_rom_roles(self):
        lines = [
            "#CG LOG v=2 fw=cg-w04-0.1.0 hw=CG-HW-001 device=coldguard-001 pin_map=2 grammar=2",
            "#CG ROM role=T1 rom=287088CA00000051 present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING",
            "#CG H8S something",
        ]
        identity = cp.read_boot_identity(lines)
        self.assertEqual(identity["firmware_version"], "cg-w04-0.1.0")
        self.assertEqual(identity["hardware_config_id"], "CG-HW-001")
        self.assertEqual(identity["device_id"], "coldguard-001")
        self.assertEqual(identity["roms"]["T1"]["rom"], "287088CA00000051")


    def test_the_wire_spelling_of_the_bme_pressure_qualifier_gets_one_shared_name(self):
        """`pressure_status` on the line is `bme_pressure_status` in the derived table.

        The validity layer watches `pressure_hpa_status`. Without this alias an H8S
        frame reads as carrying no pressure qualifier at all, so the environment
        domain is judged on a field nobody wrote - the exact way a check stops
        happening without anything failing (docs/01 19.4).
        """
        frame = cp.parse_h8s_line(fx.h8s_line(seq=1), _provenance())
        self.assertEqual(frame.values["pressure_status"], "OK")
        self.assertEqual(frame.values["pressure_hpa_status"], "OK")

    def test_the_alias_never_overwrites_a_qualifier_the_source_already_spelled(self):
        """The alias fires only when the shared name is missing.

        A source that already carries `pressure_hpa_status` keeps its own value;
        overwriting it with the wire token would replace a stated reading with a
        borrowed one.
        """
        line = fx.h8s_line(seq=2).replace("pressure_status=OK", "pressure_hpa_status=STALE")
        frame = cp.parse_h8s_line(line, _provenance())
        self.assertEqual(frame.values["pressure_hpa_status"], "STALE")
        self.assertNotIn("pressure_status", frame.values)


if __name__ == "__main__":
    unittest.main()
