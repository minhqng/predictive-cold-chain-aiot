"""Tests for cg_w09_export.py and cg_w09_run_protocol.py (A-W09-01/-02/-04).

The export is the artifact Member B trains on, so the tests are about the export
refusing to be wrong: a missing required field fails the build, a host fixture
cannot become a run, a PROBE_IDENTIFICATION capture cannot enter an S1 export,
TEC_HOT_SIDE cannot be averaged into chamber air, and the run protocol cannot
claim a firmware can observe something it cannot.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_export as ex  # noqa: E402
import cg_w09_fixtures as fx  # noqa: E402
import cg_w09_run_protocol as proto  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
W04_CSV = REPO_ROOT / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"


def _source(path: pathlib.Path, physical: bool = True) -> ex.RunSource:
    return ex.RunSource(
        path=path.as_posix(),
        sha256=cp.sha256_file(path),
        source_kind="csv_capture",
        is_physical_measurement=physical,
        run_label="H8C_BOX_COOLING_600S",
        repo_tracked=True,
    )


class RunProtocolShape(unittest.TestCase):
    def test_every_gate_names_a_doc_anchor(self):
        for gate in proto.GATES:
            self.assertTrue(gate.doc_anchor, gate.gate_id)
            self.assertIn("docs/", gate.doc_anchor)

    def test_gate_ids_are_unique(self):
        ids = [gate.gate_id for gate in proto.GATES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_observability_vocabulary_is_closed(self):
        allowed = {proto.OBSERVABLE, proto.PARTIAL, proto.HOST_ONLY}
        for gate in proto.GATES:
            self.assertIn(gate.firmware_observability, allowed, gate.gate_id)

    def test_both_checklist_halves_of_the_requirement_exist(self):
        doc = proto.document()
        self.assertIn(proto.PHASE_BEFORE, doc["gate_counts"])
        self.assertIn(proto.PHASE_AFTER, doc["gate_counts"])

    def test_every_named_item_of_a_w09_01_has_a_gate(self):
        # docs/05A §18 A-W09-01 lists eight items; a checklist that drops one is
        # worse than no checklist, because it reads as complete.
        documented = [
            "hardware config", "sensor identity", "PZEM range", "initial state", "door",
            "storage online", "end reason", "manual intervention", "anomaly",
            "validity candidate",
        ]
        text = " | ".join(gate.requirement for gate in proto.GATES).lower()
        for item in documented:
            self.assertIn(item.lower(), text, f"A-W09-01 item {item!r} has no gate")

    def test_host_only_gates_are_not_marked_firmware_observable(self):
        # storage and probe position are the two a frame cannot vouch for; a
        # previous revision let a checklist imply otherwise.
        for gate_id in ("GATE-STORAGE-ONLINE", "GATE-SENSOR-POSITION", "GATE-PROVENANCE-PIN"):
            self.assertEqual(proto.gate_by_id(gate_id).firmware_observability, proto.HOST_ONLY)

    def test_door_gate_is_partial_because_polarity_is_not_position(self):
        gate = proto.gate_by_id("GATE-DOOR-STATE")
        self.assertEqual(gate.firmware_observability, proto.PARTIAL)
        self.assertIn("stuck-high", gate.note)

    def test_supervised_authorization_gap_is_recorded(self):
        gate = proto.gate_by_id("GATE-OUTPUT-GATE")
        self.assertIn("supervised_authorized=0", gate.note)

    def test_rendered_markdown_carries_every_gate(self):
        doc = proto.document()
        text = proto.render_markdown(doc)
        for gate in proto.GATES:
            self.assertIn(gate.gate_id, text)

    def test_scenario_gates_are_scoped(self):
        self.assertEqual(proto.gate_by_id("GATE-S2-DISTURBANCE-CONTROL").scenario_scope,
                         ("S2_DOOR_DISTURBANCE",))


class ExportCompleteness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, cls.report = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.export = ex.build_run_export(
            cls.frames,
            run_label="H8C_BOX_COOLING_600S",
            scenario_candidate="S1_NORMAL_BASELINE",
            status_label="REAL_DATA_ANALYZED",
            sources=[_source(W04_CSV)],
            generated_at_utc="2026-11-02T00:00:00Z",
        )

    def test_every_required_field_is_present(self):
        for name in ex.REQUIRED_EXPORT_FIELDS:
            self.assertIn(name, self.export, f"required export field {name} is missing")

    def test_a_missing_required_field_fails_the_build(self):
        broken = dict(self.export)
        for name in ("hardware_config_id", "firmware_version", "provenance"):
            candidate = dict(broken)
            candidate.pop(name)
            with self.assertRaises(ex.ExportError) as ctx:
                ex._assert_complete(candidate)
            self.assertIn(name, str(ctx.exception))

    def test_sensors_carry_rom_and_physical_position(self):
        for sensor in self.export["sensors"]:
            for name in ex.REQUIRED_SENSOR_FIELDS:
                self.assertIn(name, sensor, f"{sensor.get('raw_slot')} missing {name}")
            self.assertEqual(len(sensor["rom"]), 16)
            self.assertTrue(sensor["physical_position"])

    def test_roms_match_the_frozen_as_built_record(self):
        by_slot = {s["raw_slot"]: s for s in self.export["sensors"]}
        self.assertEqual(by_slot["t1"]["rom"], "287088CA00000051")
        self.assertEqual(by_slot["t2"]["rom"], "28AEBF2200000006")
        self.assertEqual(by_slot["t3"]["rom"], "28CBE9CA00000072")
        self.assertEqual(by_slot["t4"]["rom"], "283BE5C9000000A9")
        self.assertEqual(by_slot["t2"]["physical_position"], "TEC_HOT_SIDE")
        self.assertFalse(by_slot["t2"]["in_chamber_air_mean"])
        self.assertTrue(by_slot["t1"]["in_chamber_air_mean"])

    def test_rom_source_is_stated_as_by_source(self):
        for sensor in self.export["sensors"]:
            self.assertIn("BY_SOURCE", sensor["rom_source"])
            self.assertFalse(sensor["rom_readback_verified"])

    def test_a_rom_contradiction_is_fatal(self):
        frames = fx.physical_frames(2)
        source = ex.RunSource(
            path="virtual", sha256="0" * 64, source_kind="h8s_jsonl",
            is_physical_measurement=True, run_label="SOMETHING",
        )
        with self.assertRaises(ex.ExportError):
            ex.build_run_export(
                frames, run_label="SOMETHING", scenario_candidate="S1_NORMAL_BASELINE",
                status_label="HOST_VERIFIED", sources=[source],
                boot_identity={"roms": {"T1": {"rom": "0000000000000000", "present": "1"}}},
            )

    def test_required_identity_fields_are_named_in_the_contract(self):
        # A run export Member B cannot join on is worthless; the required field
        # list is the contract, so it must name the identity fields and their
        # semantics, not just the values.
        for name in ("run_id", "run_id_status", "boot_id", "boot_id_status",
                     "hardware_config_id", "firmware_version", "sensors",
                     "timestamp_semantics", "uptime_semantics", "provenance"):
            self.assertIn(name, ex.REQUIRED_EXPORT_FIELDS)

    def test_a_run_export_missing_id_status_is_fatal(self):
        broken = dict(self.export)
        broken.pop("run_id_status")
        with self.assertRaises(ex.ExportError):
            ex._assert_complete(broken)

    def test_no_source_is_fatal(self):
        with self.assertRaises(ex.ExportError):
            ex.build_run_export(
                self.frames, run_label="X", scenario_candidate="S1_NORMAL_BASELINE",
                status_label="REAL_DATA_ANALYZED", sources=[],
            )

    def test_unpinned_source_is_fatal(self):
        with self.assertRaises(ex.ExportError):
            ex.build_run_export(
                self.frames, run_label="X", scenario_candidate="S1_NORMAL_BASELINE",
                status_label="REAL_DATA_ANALYZED",
                sources=[_source(W04_CSV).__class__(
                    path=W04_CSV.as_posix(), sha256=None, source_kind="csv_capture",
                    is_physical_measurement=True, run_label="H8C_BOX_COOLING_600S",
                )],
            )

    def test_empty_frames_are_refused(self):
        with self.assertRaises(ex.ExportError):
            ex.build_run_export(
                [], run_label="X", scenario_candidate="S1_NORMAL_BASELINE",
                status_label="HOST_VERIFIED", sources=[_source(W04_CSV)],
            )


class ExportProvenanceAndTime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, cls.report = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.export = ex.build_run_export(
            cls.frames, run_label="H8C_BOX_COOLING_600S",
            scenario_candidate="S1_NORMAL_BASELINE", status_label="REAL_DATA_ANALYZED",
            sources=[_source(W04_CSV)], generated_at_utc="2026-11-02T00:00:00Z",
        )

    def test_source_sha256_is_pinned(self):
        sources = self.export["provenance"]["sources"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["sha256"], self.report["source_sha256"])
        self.assertEqual(len(sources[0]["sha256"]), 64)

    def test_identity_fields_are_the_real_values(self):
        self.assertEqual(self.export["boot_id"], "56044b74")
        self.assertEqual(self.export["hardware_config_id"], "CG-HW-001")
        self.assertEqual(self.export["run_ids"], ["run-00000000", "run-00000001"])

    def test_ambiguous_source_run_ids_are_named_but_never_joined(self):
        # The committed capture carries two run_id segments inside one boot_id.
        # Inventing "run-00000000+run-00000001" would give Member B a key that
        # exists in no source, and registering the segments as two runs would
        # overstate the campaign. Both are refused: run_id stays null and the
        # state is said out loud.
        self.assertIsNone(self.export["run_id"])
        self.assertEqual(
            self.export["run_id_status"], ex.RUN_ID_AMBIGUOUS
        )
        self.assertEqual(self.export["boot_id_status"], ex.BOOT_ID_SINGLE)

    def test_single_source_run_id_is_published_as_is(self):
        export = ex.build_run_export(
            fx.physical_frames(3), run_label="SOME_REAL_RUN",
            scenario_candidate="S1_NORMAL_BASELINE", status_label="REAL_DATA_ANALYZED",
            sources=[_source(W04_CSV)], generated_at_utc="2026-11-02T00:00:00Z",
        )
        self.assertEqual(export["run_id"], "run-00000000")
        self.assertEqual(export["run_id_status"], ex.RUN_ID_SINGLE)

    def test_a_run_id_spanning_boot_ids_is_not_a_run(self):
        # Segments of one boot are not independent runs, and one run id spread
        # over two boot_ids is not one run either: opening the port changed the
        # boot, so the identity is unresolved and nothing is published.
        frames = fx.physical_frames(2) + fx.physical_frames(2, boot_id="otherboot")
        export = ex.build_run_export(
            frames, run_label="SOME_REAL_RUN",
            scenario_candidate="S1_NORMAL_BASELINE", status_label="REAL_DATA_ANALYZED",
            sources=[_source(W04_CSV)], generated_at_utc="2026-11-02T00:00:00Z",
        )
        self.assertIsNone(export["boot_id"])
        self.assertEqual(export["boot_id_status"], ex.BOOT_ID_AMBIGUOUS)
        index = ex.build_run_index([export], generated_at_utc="2026-11-02T00:00:00Z")
        self.assertEqual(index["valid_s1_run_ids_for_member_b"], [])
        self.assertEqual(len(index["blocked_run_ids"]), 1)

    def test_timestamp_semantics(self):
        semantics = self.export["timestamp_semantics"]
        self.assertIsNone(semantics["device_timestamp_utc"])
        self.assertEqual(semantics["timestamp_utc_status"], "UNAVAILABLE")
        self.assertEqual(semantics["timestamp_utc_source"], "DEVICE_HAS_NO_WALL_CLOCK")
        self.assertEqual(semantics["measurement_time_axis"], "DEVICE_UPTIME_MS")

    def test_host_time_is_labelled_as_host_time(self):
        label = self.export["timestamp_semantics"]["host_capture_time"]
        self.assertIn("NEVER_IN_PLACE_OF_IT", label)
        self.assertNotIn("REPLACES", label)

    def test_every_frame_row_keeps_the_device_time_unavailable(self):
        for row in self.export["frames"][:50]:
            self.assertIsNone(row["timestamp_utc"])
            self.assertEqual(row["timestamp_utc_status"], "UNAVAILABLE")

    def test_uptime_join_rule_is_stated(self):
        self.assertEqual(
            self.export["uptime_semantics"]["cross_join_rule"],
            "join on (device_id, boot_id, seq); never on device_ms alone",
        )

    def test_cadence_is_measured_from_the_frames(self):
        measured = self.export["cadence"]["measured"]
        self.assertEqual(measured["n_intervals"], 956)
        self.assertAlmostEqual(measured["median_interval_ms"], 1000.0)
        self.assertEqual(measured["nonpositive_intervals"], 0)


class FixtureAndExcludedClassRefusal(unittest.TestCase):
    def test_a_host_fixture_cannot_be_exported_as_a_run(self):
        frames = fx.fixture_frames(4)
        source = ex.RunSource(
            path="tests/cg_w09_fixtures.py", sha256="0" * 64, source_kind="h8s_fixture",
            is_physical_measurement=False, run_label=fx.FIXTURE_RUN_LABEL_PREFIX + "UNIT",
        )
        with self.assertRaises(ex.ExportError) as ctx:
            ex.build_run_export(
                frames, run_label="FIXTURE_UNIT", scenario_candidate="S1_NORMAL_BASELINE",
                status_label="HOST_VERIFIED", sources=[source],
            )
        self.assertIn("is_physical_measurement=false", str(ctx.exception))

    def test_a_probe_identification_capture_cannot_be_exported(self):
        frames = fx.physical_frames(3, run_label="PROBE_IDENTIFICATION_TOUCH_2")
        source = ex.RunSource(
            path="evidence/A/W07/probe-identification/touch_2.log", sha256="0" * 64,
            source_kind="h8s_jsonl", is_physical_measurement=True,
            run_label="PROBE_IDENTIFICATION_TOUCH_2",
        )
        with self.assertRaises(ex.ExportError) as ctx:
            ex.build_run_export(
                frames, run_label="PROBE_IDENTIFICATION_TOUCH_2",
                scenario_candidate="S1_NORMAL_BASELINE", status_label="REAL_DATA_ANALYZED",
                sources=[source],
            )
        self.assertIn("excluded session class", str(ctx.exception))


class ChamberMeanIsNotContaminated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.export = ex.build_run_export(
            frames, run_label="H8C_BOX_COOLING_600S",
            scenario_candidate="S1_NORMAL_BASELINE", status_label="REAL_DATA_ANALYZED",
            sources=[_source(W04_CSV)], generated_at_utc="2026-11-02T00:00:00Z",
        )
        cls.states = cls.export["derived_thermal_states"]["states"]

    def test_chamber_mean_excludes_the_hot_side(self):
        self.assertNotIn("t2", self.states["chamber_air_mean"]["slots"])
        self.assertIn("t2", self.states["chamber_air_mean"]["excluded"])

    def test_the_literal_docs01_mean_is_reported_but_not_usable(self):
        literal = self.states["docs01_20_1_literal_tmean"]
        self.assertFalse(literal["use_for_physics"])
        self.assertEqual(literal["quality_label"], "CONTAMINATED_ON_THIS_RIG")
        self.assertIn("open project issue", literal["contamination_reason"])

    def test_the_literal_mean_is_warmer_than_chamber_air(self):
        # On this geometry the §20.1 mean sits above the true chamber-air state,
        # which is the whole reason the discrepancy is recorded rather than
        # quietly redefined here.
        self.assertGreater(
            literal := self.states["docs01_20_1_literal_tmean"]["mean_c"],
            self.states["chamber_air_mean"]["mean_c"],
        )
        self.assertGreater(literal, self.states["chamber_air_mean"]["mean_c"])

    def test_hot_side_is_reported_alone(self):
        hot = self.states["tec_hot_side"]
        self.assertTrue(hot["never_in_chamber_mean"])
        self.assertGreater(hot["mean_c"], self.states["chamber_air_mean"]["mean_c"])

    def test_geometry_version_and_position_source_are_stated(self):
        self.assertEqual(
            self.export["derived_thermal_states"]["geometry_version"], ex.FROZEN_GEOMETRY_VERSION
        )
        self.assertIn("2026-11-02", self.export["derived_thermal_states"]["position_source"])

    def test_gradient_is_reported_per_chamber_slot(self):
        gradient = self.export["derived_thermal_states"]["gradient_c_per_s"]
        self.assertIn("t1", gradient)
        self.assertNotIn("t2", gradient)

    def test_every_gradient_states_its_estimator_and_its_window(self):
        """docs/01 §20.5: a slope without a named fit and window is ambiguous.

        One number per slot was the defect: the published figure was an endpoint
        difference, a least-squares fit over the identical rows was about 3x from
        it, and nothing said which was which.
        """
        gradient = self.export["derived_thermal_states"]["gradient_c_per_s"]
        for slot, entry in gradient.items():
            with self.subTest(slot=slot):
                self.assertIsNotNone(entry["least_squares_gradient_c_per_s"])
                self.assertIsNotNone(entry["endpoint_gradient_c_per_s"])
                self.assertIn("ordinary least squares", entry["least_squares_estimator"])
                self.assertIn("(last - first)", entry["endpoint_estimator"])
                self.assertEqual(entry["window"]["doc_anchor"], "docs/01 §20.5")
                self.assertIn("raw single-probe value",
                              entry["window"]["temperature_representation"])
                self.assertGreater(entry["window"]["duration_s"], 0)
                self.assertGreater(entry["n"], 2)

    def test_the_two_estimators_are_published_apart_not_merged(self):
        # They answer different questions on a series that cools and then recovers,
        # so the dossier may not print one of them as "the" gradient.
        gradient = self.export["derived_thermal_states"]["gradient_c_per_s"]["t1"]
        self.assertIn("estimator_spread_c_per_s", gradient)
        self.assertGreater(gradient["estimator_spread_c_per_s"], 0.0)
        self.assertIn("different estimators", gradient["reading"])

    def test_the_endpoint_estimator_is_what_it_says_it_is(self):
        # The label is a claim about arithmetic, so check the arithmetic: on an
        # evenly spaced series the endpoint figure equals (last - first) / span.
        entry = self.export["derived_thermal_states"]["gradient_c_per_s"]["t1"]
        window = entry["window"]
        span_s = (window["last_device_ms"] - window["first_device_ms"]) / 1000.0
        states = self.export["derived_thermal_states"]["states"]["t1_chamber_center"]
        self.assertAlmostEqual(
            entry["endpoint_gradient_c_per_s"],
            round((states["last_c"] - states["first_c"]) / span_s, 7),
            places=6,
        )


class RowContractIsDelivered(unittest.TestCase):
    """A per-row claim is only evidence if the rows carry it and the file says so.

    The dossier once claimed 26 columns per row naming fields that did not exist,
    while the export declared a 50-column set over a 24-column file. These tests
    bind the claim, the declaration and the delivery to one source.
    """

    @classmethod
    def setUpClass(cls):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.export = ex.build_run_export(
            frames, run_label="H8C_BOX_COOLING_600S",
            scenario_candidate="S1_NORMAL_BASELINE", status_label="REAL_DATA_ANALYZED",
            sources=[_source(W04_CSV)], generated_at_utc="2026-11-02T00:00:00Z",
        )

    def test_the_declared_header_is_the_rendered_header(self):
        rendered = ex.render_companion_csv(self.export["frames"]).splitlines()[0]
        self.assertEqual(rendered.split(","), list(ex.ROW_CSV_COLUMNS))

    def test_every_contract_field_lands_in_a_column_or_a_stated_gap(self):
        stated = set(ex.ROW_CSV_COLUMNS) | set(ex.ROW_CONTRACT_NOT_AVAILABLE)
        unsaid = sorted(set(ex.ROW_CONTRACT_DELIVERED) - stated)
        self.assertEqual(unsaid, [], "a contracted row field is neither delivered nor explained")

    def test_the_identity_rom_and_provenance_fields_are_on_every_row(self):
        # docs/05A §18's row criterion, checked per row rather than per file. The
        # quality state is one dict in the row and one column per domain in the
        # companion, so both forms are asserted here.
        required = [
            "run_id", "boot_id", "hardware_config_id", "firmware_version", "device_ms",
            "timestamp_utc_status", "source_line_index", "dedup_key", "experiment_phase",
            "quality", "quality_by_domain", "invalidation_reasons",
        ] + [
            f"{slot}{suffix}"
            for slot in ("t1", "t2", "t3", "t4")
            for suffix in ("", "_rom", "_physical_position", "_status")
        ]
        for row in self.export["frames"]:
            for name in required:
                self.assertIn(name, row, f"row {row['seq']} lacks {name}")
            self.assertEqual(set(row["quality_by_domain"]), set(
                ("producer", "thermal", "environment", "electrical", "door", "sequence",
                 "provenance")))
        header = ex.render_companion_csv(self.export["frames"]).splitlines()[0].split(",")
        for domain in ("producer", "thermal", "environment", "electrical", "door", "sequence",
                       "provenance"):
            self.assertIn(f"{domain}_quality", header)

    def test_a_field_no_encoding_carries_is_stated_per_field(self):
        for name, reason in ex.ROW_CONTRACT_NOT_AVAILABLE.items():
            with self.subTest(field=name):
                self.assertTrue(reason.startswith("NOT AVAILABLE"), name)
                self.assertGreater(len(reason), 40, f"{name} is excused without a reason")

    def test_an_unavailable_cell_says_so_instead_of_being_blank(self):
        line = ex.render_companion_csv(self.export["frames"]).splitlines()[1].split(",")
        header = list(ex.ROW_CSV_COLUMNS)
        cells = dict(zip(header, line))
        self.assertEqual(cells["timestamp_utc"], ex.NOT_AVAILABLE_CELL)
        self.assertNotEqual(cells["timestamp_utc"], "")

    def test_rendering_refuses_a_row_that_cannot_answer_a_declared_column(self):
        row = dict(self.export["frames"][0])
        del row["hardware_config_id"]
        with self.assertRaises(ex.ExportError):
            ex.render_companion_csv([row])

    def test_rendering_refuses_a_row_whose_quality_map_lost_a_domain(self):
        row = dict(self.export["frames"][0])
        domains = dict(row["quality_by_domain"])
        domains.pop("door")
        row["quality_by_domain"] = domains
        with self.assertRaises(ex.ExportError):
            ex.render_companion_csv([row])

    def test_a_row_missing_a_contracted_field_fails_the_export(self):
        export = dict(self.export)
        export["frames"] = [dict(row) for row in self.export["frames"]]
        del export["frames"][0]["dedup_key"]
        with self.assertRaises(ex.ExportError):
            ex._assert_complete(export)

    def test_an_export_that_inlines_no_rows_cannot_claim_a_row_contract(self):
        export = dict(self.export)
        export["frames"] = {"rows": 957, "companion_file": "elsewhere.csv"}
        with self.assertRaises(ex.ExportError):
            ex._assert_complete(export)

    def test_the_published_contract_block_describes_the_published_columns(self):
        block = self.export["row_contract"]
        self.assertEqual(block["companion_csv_columns"], list(ex.ROW_CSV_COLUMNS))
        for group, names in block["delivered_per_row"].items():
            for name in names:
                self.assertIn(name, ex.ROW_CSV_COLUMNS, f"{group} names {name}, not a column")

    def test_the_contract_block_is_a_required_export_field(self):
        self.assertIn("row_contract", ex.REQUIRED_EXPORT_FIELDS)
        self.assertIn("row_contract", self.export)


class RunIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        cls.frames_used = frames
        cls.export = ex.build_run_export(
            frames, run_label="H8C_BOX_COOLING_600S",
            scenario_candidate="S1_NORMAL_BASELINE", status_label="REAL_DATA_ANALYZED",
            sources=[_source(W04_CSV)], generated_at_utc="2026-11-02T00:00:00Z",
        )
        cls.index = ex.build_run_index([cls.export], generated_at_utc="2026-11-02T00:00:00Z")

    def test_index_declares_the_dedup_key(self):
        self.assertEqual(self.index["dedup_key"], ["device_id", "boot_id", "seq"])

    def test_index_carries_the_pinned_hash_per_run(self):
        # Property: every source the index names is hash-pinned, however many
        # sources a future run is assembled from.
        entry = self.index["runs"][0]
        self.assertTrue(entry["source_paths"])
        for path in entry["source_paths"]:
            self.assertIn(path, entry["source_sha256"])
            self.assertRegex(entry["source_sha256"][path], r"^[0-9a-f]{64}$")

    def test_index_usability_is_measured_and_internally_consistent(self):
        # Property, not a count: the published fraction is the published counts,
        # and neither is allowed to exceed the rows that exist.
        entry = self.index["runs"][0]
        self.assertEqual(entry["frames_total"], len(self.frames_used))
        self.assertLessEqual(entry["frames_usable_for_baseline"], entry["frames_total"])
        self.assertLessEqual(
            entry["frames_thermally_usable_for_statistics"], entry["frames_total"]
        )
        self.assertAlmostEqual(
            entry["usable_fraction"],
            round(entry["frames_usable_for_baseline"] / entry["frames_total"], 6),
            places=6,
        )
        for counts in entry["quality_counts_by_domain"].values():
            self.assertEqual(sum(counts.values()), entry["frames_total"])

    def test_phase_snapshot_the_indexed_run_is_thermal_but_not_s1_usable(self):
        """PHASE SNAPSHOT - MUST EVOLVE when the capture carries its qualifiers.

        957 rows, 940 thermally usable, 0 usable for the S1 scenario: the last
        figure is a statement about today's derived CSV (no door/environment/power
        qualifier column), not about the rules. The day a capture carries those
        columns this fails, and the right response is to retire the snapshot and
        re-derive the dossier, never to move the assertion.
        """
        entry = self.index["runs"][0]
        self.assertEqual(entry["frames_total"], 957)
        self.assertEqual(entry["frames_thermally_usable_for_statistics"], 940)
        self.assertEqual(entry["frames_usable_for_baseline"], 0)
        self.assertEqual(entry["usable_fraction"], 0.0)

    def test_ambiguous_run_id_is_blocked_not_handed_to_b(self):
        # Property: a capture whose source run_id segments are unresolved yields
        # no joinable id for Member B, whatever its row counts turn out to be.
        self.assertEqual(
            self.export["run_id_status"], ex.RUN_ID_AMBIGUOUS
        )
        self.assertEqual(self.index["valid_s1_run_ids_for_member_b"], [])
        blocked = [
            b for b in self.index["blocked_run_ids"]
            if b["boot_id"] == self.export["boot_id"]
        ]
        self.assertEqual(len(blocked), 1)
        self.assertIn("run_id_status", blocked[0]["reasons"][0])

    def test_a_run_with_no_ambiguity_and_a_majority_is_handed_to_b(self):
        # The other side of the same rule, so the empty list above cannot be
        # earned by a check that simply never passes.
        clean = ex.build_run_export(
            fx.physical_frames(4), run_label="SOME_REAL_RUN",
            scenario_candidate="S1_NORMAL_BASELINE", status_label="REAL_DATA_ANALYZED",
            sources=[_source(W04_CSV)], generated_at_utc="2026-11-02T00:00:00Z",
        )
        index = ex.build_run_index([clean], generated_at_utc="2026-11-02T00:00:00Z")
        self.assertEqual(index["valid_s1_run_ids_for_member_b"], [clean["run_id"]])
        weak = dict(clean)
        weak["invalidation"] = dict(clean["invalidation"])
        weak["invalidation"]["summary"] = dict(clean["invalidation"]["summary"])
        weak["invalidation"]["summary"]["usable_fraction"] = 0.05
        index = ex.build_run_index([weak], generated_at_utc="2026-11-02T00:00:00Z")
        self.assertEqual(index["valid_s1_run_ids_for_member_b"], [])

    def test_index_quality_counts_by_domain_survive(self):
        entry = self.index["runs"][0]
        self.assertEqual(entry["quality_counts_by_domain"]["thermal"]["VALID"],
                         entry["frames_total"])
        self.assertEqual(entry["quality_counts_by_domain"]["electrical"]["VALID"], 0)


class PhaseClassification(unittest.TestCase):
    def test_phases_split_the_committed_capture_correctly(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        counts = ex._phase_counts(frames)
        self.assertEqual(counts[ex.PHASE_PRE_FIRST_SNAPSHOT], 17)
        self.assertEqual(counts[ex.PHASE_ACTIVE_COOLING], 600)
        self.assertEqual(counts[ex.PHASE_COOLDOWN], 5)
        self.assertEqual(counts[ex.PHASE_OFF_IDLE], 335)
        self.assertEqual(sum(counts.values()), 957)

    def test_export_frames_carry_their_phase(self):
        frames, _ = cp.read_csv_capture(W04_CSV, "H8C_BOX_COOLING_600S")
        export = ex.build_run_export(
            frames, run_label="H8C_BOX_COOLING_600S",
            scenario_candidate="S1_NORMAL_BASELINE", status_label="REAL_DATA_ANALYZED",
            sources=[_source(W04_CSV)],
        )
        self.assertEqual(export["frames"][0]["experiment_phase"], ex.PHASE_PRE_FIRST_SNAPSHOT)
        self.assertEqual(export["frames"][400]["experiment_phase"], ex.PHASE_ACTIVE_COOLING)


if __name__ == "__main__":
    unittest.main()
