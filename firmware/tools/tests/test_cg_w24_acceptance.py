"""Unit tests for ColdGuard Member A — W24 Final Acceptance Tool."""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cg_w24_final_freeze import (
    REQUIREMENT_EVIDENCE_SPEC,
    REQUIRED_INDEPENDENT_RUNS,
    STATUS_INSUFFICIENT,
    STATUS_SATISFIED,
    STATUS_INSUFFICIENT,
    STATUS_SATISFIED,
    SYSTEM_INTEGRATION_NOT_ASSERTABLE,
    VERDICT_DATA_INSUFFICIENT,
    VERDICT_PHYSICALLY_ACCEPTED,
    VERDICT_PHYSICAL_ACCEPTANCE_PENDING,
    collate_acceptance_census,
    evaluate_requirement_evidence,
    generate_acceptance_census,
    validate_final_configuration,
    verify_physical_evidence,
)


HW_CONF = "HW-CONF-2026-10-27-ASBUILT-V2"
ALL_WEEKS = list(range(1, 25))


def _record(root, rel, body, n, device="DEV-A", boot=None, source="RAW_DEVICE_CAPTURE",
            conf=HW_CONF, pin=True, cls="COOLING_SESSION"):
    """One evidence record for a capture that carries its own identity and is pinned.

    Genuine W01-W24 captures list boot_id / hardware_config_id columns and appear in
    their dossier's SHA256SUMS.txt, so the fixtures reproduce that shape instead of
    inventing a rule real evidence could not satisfy.
    """
    boot_id = boot if boot is not None else f"BOOT-{n}"
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        f"boot_id,device_id,hardware_config_id,note\r\n"
        f"{boot_id},{device},{conf},run {n} payload\r\n"
    ).encode() + body
    path.write_bytes(payload)
    if pin:
        sums = path.parent / "SHA256SUMS.txt"
        line = f"{hashlib.sha256(payload).hexdigest()}  {path.name}\r\n"
        with sums.open("a", encoding="utf-8", newline="") as fh:
            fh.write(line)
    return {
        "run_id": f"RUN-{n}",
        "device_id": device,
        "boot_id": boot_id,
        "source_type": source,
        "artifact_path": rel,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "hardware_config_id": conf,
        "evidence_class": cls,
    }


def _week_dossiers(root):
    """Every claimed week needs a dossier directory, not only a number."""
    from cg_w24_final_freeze import WEEK_DOSSIER_DIR_FALLBACK
    for rel in WEEK_DOSSIER_DIR_FALLBACK.values():
        (Path(root) / rel).mkdir(parents=True, exist_ok=True)


class TestW24FinalAcceptance(unittest.TestCase):

    def setUp(self):
        self.valid_config = {
            "hardware_config_id": "HW-CONF-2026-10-27-ASBUILT-V2",
            "evidence_class": "AS_BUILT_BENCH_AUDITED",
            "pin_map_v2": {
                "one_wire_gpio": 33,
                "bme280_sda_gpio": 21,
                "bme280_scl_gpio": 34,
                "door_reed_gpio": 35,
                "pzem_tx_gpio": 36,
                "pzem_rx_gpio": 37,
                "ibt2_rpwm_gpio": 5,
                "ibt2_r_en_gpio": 6,
                "ibt2_l_en_gpio": 10,
            },
            "sensor_roms": {
                "t1": "287088CA00000051",
                "t2": "28AEBF2200000006",
                "t3": "28CBE9CA00000072",
                "t4": "283BE5C9000000A9",
            },
            "sensor_positions": {
                "t1": "CHAMBER_CENTER",
                "t2": "TEC_HOT_SIDE",
                "t3": "CHAMBER_BOTTOM",
                "t4": "NEAR_DOOR",
            },
            "power_and_protection": {
                "fuse_type": "15A blade fuse",
                "fuse_slot_3_posture": "REMOVED (TEC isolated)",
                "pzem_shunt": "FL-2 0.5 50A/75mV",
            },
        }

    def test_validate_final_configuration_clean(self):
        res = validate_final_configuration(self.valid_config)
        self.assertTrue(res.valid)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.evidence_class, "AS_BUILT_BENCH_AUDITED")

    def test_validate_final_configuration_wrong_pin(self):
        bad_config = dict(self.valid_config)
        bad_pins = dict(self.valid_config["pin_map_v2"])
        bad_pins["one_wire_gpio"] = 4  # Wrong old pin
        bad_config["pin_map_v2"] = bad_pins
        res = validate_final_configuration(bad_config)
        self.assertFalse(res.valid)
        self.assertTrue(any("PIN_MISMATCH: one_wire_gpio" in e for e in res.errors))

    def test_validate_final_configuration_wrong_fuse(self):
        bad_config = dict(self.valid_config)
        bad_power = dict(self.valid_config["power_and_protection"])
        bad_power["fuse_type"] = "10A blade fuse"  # Wrong fuse rating
        bad_config["power_and_protection"] = bad_power
        res = validate_final_configuration(bad_config)
        self.assertFalse(res.valid)
        self.assertTrue(any("FUSE_MISMATCH" in e for e in res.errors))

    def test_validate_final_configuration_fuse_not_removed(self):
        bad_config = dict(self.valid_config)
        bad_power = dict(self.valid_config["power_and_protection"])
        bad_power["fuse_slot_3_posture"] = "INSTALLED_ENERGIZED"  # Safety violation
        bad_config["power_and_protection"] = bad_power
        res = validate_final_configuration(bad_config)
        self.assertFalse(res.valid)
        self.assertTrue(any("FUSE_POSTURE_VIOLATION" in e for e in res.errors))

    def test_collate_acceptance_census_with_open_gates(self):
        all_weeks = list(range(1, 25))
        gates = ["H-GATE-1", "H-GATE-2", "H-GATE-5"]
        census = collate_acceptance_census(
            weeks_delivered=all_weeks,
            physical_runs_count=1,
            hardware_status="FAIL_CLOSED_FROZEN",
            open_hardware_gates=gates,
        )
        self.assertEqual(census["delivered_week_count"], 24)
        self.assertTrue(census["all_weeks_accounted_for"])
        self.assertTrue(census["software_contract_ready"])
        # Physical acceptance MUST NOT be granted when open hardware gates exist!
        self.assertFalse(census["physical_acceptance_ready"])
        self.assertEqual(
            census["handover_verdict"],
            "READY_FOR_SOFTWARE_INTEGRATION_PHYSICAL_ACCEPTANCE_BLOCKED",
        )

    def test_collate_acceptance_census_missing_weeks(self):
        partial = list(range(1, 17))
        census = collate_acceptance_census(
            weeks_delivered=partial,
            physical_runs_count=1,
            hardware_status="FAIL_CLOSED_FROZEN",
            open_hardware_gates=[],
        )
        self.assertEqual(census["delivered_week_count"], 16)
        self.assertFalse(census["all_weeks_accounted_for"])
        self.assertFalse(census["software_contract_ready"])
        self.assertEqual(census["handover_verdict"], "INCOMPLETE")


class TestW24CensusIsNotClaimDriven(unittest.TestCase):
    """A caller must not be able to reach physical acceptance by typing numbers."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _week_dossiers(self.root)

    def census(self, **kw):
        base = dict(weeks_delivered=ALL_WEEKS, physical_runs_count=0,
                    hardware_status="FAIL_CLOSED_FROZEN", open_hardware_gates=[],
                    repo_root=self.root, expected_hardware_config_id=HW_CONF)
        base.update(kw)
        return collate_acceptance_census(**base)

    def test_counts_alone_cannot_grant_physical_acceptance(self):
        res = self.census(physical_runs_count=9999, physical_evidence=None)
        self.assertFalse(res["physical_acceptance_ready"])
        self.assertEqual(res["acceptance_verdict"], VERDICT_DATA_INSUFFICIENT)
        self.assertNotEqual(res["handover_verdict"], "FULLY_ACCEPTED")

    def test_absent_gate_register_is_unknown_not_zero_gates(self):
        res = collate_acceptance_census(
            weeks_delivered=ALL_WEEKS, physical_runs_count=5,
            hardware_status="FAIL_CLOSED_FROZEN",
        )
        self.assertFalse(res["gate_register_supplied"])
        self.assertEqual(res["acceptance_verdict"], VERDICT_DATA_INSUFFICIENT)

    def test_cited_artifact_that_does_not_exist_is_refused(self):
        good = [self._mk(f"evidence/A/W24/run{i}.csv", i) for i in range(2)]
        bad = dict(self._mk("evidence/A/W24/run9.csv", 9))
        bad["artifact_path"] = "evidence/A/RC/remaining-hardware-gates.md"
        res = self.census(physical_runs_count=3, physical_evidence=good + [bad])
        self.assertEqual(res["physical_runs_verified"], 2)
        self.assertTrue(any("EVIDENCE_ARTIFACT_MISSING" in r for r in res["evidence_refusals"]))
        self.assertFalse(res["physical_acceptance_ready"])

    def test_recorded_hash_that_does_not_match_bytes_is_refused(self):
        rec = self._mk("evidence/A/W24/run1.csv", 1)
        rec["sha256"] = "0" * 64
        res = self.census(physical_evidence=[rec])
        self.assertTrue(any("EVIDENCE_HASH_MISMATCH" in r for r in res["evidence_refusals"]))
        self.assertEqual(res["physical_runs_verified"], 0)

    def test_host_fixture_cannot_count_as_physical_run(self):
        rec = self._mk("evidence/A/W24/run1.csv", 1, source="HOST_SYNTHETIC_FIXTURE")
        res = self.census(physical_evidence=[rec])
        self.assertTrue(any("EVIDENCE_SOURCE_SYNTHETIC" in r for r in res["evidence_refusals"]))
        self.assertEqual(res["physical_runs_verified"], 0)

    def test_segments_of_one_boot_count_as_one_independent_run(self):
        recs = [self._mk(f"evidence/A/W24/seg{i}.csv", i, boot="BOOT-SAME")
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_runs_count=3, physical_evidence=recs)
        self.assertEqual(res["physical_runs_verified"], 1)
        self.assertTrue(any("EVIDENCE_RUN_NOT_INDEPENDENT" in r for r in res["evidence_refusals"]))
        self.assertFalse(res["physical_acceptance_ready"])

    def test_other_hardware_config_is_refused(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i, conf="HW-CONF-OLD-V1")
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_evidence=recs)
        self.assertTrue(any("EVIDENCE_HARDWARE_CONFIG_MISMATCH" in r for r in res["evidence_refusals"]))

    def test_incomplete_record_is_refused(self):
        rec = self._mk("evidence/A/W24/run1.csv", 1)
        del rec["device_id"]
        res = self.census(physical_evidence=[rec])
        self.assertTrue(any("EVIDENCE_FIELD_MISSING" in r for r in res["evidence_refusals"]))

    def test_positive_control_genuine_independent_runs_are_accepted(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        covered = {
            "A-W04-03": {"status": STATUS_SATISFIED},
            "A-W07-02": {"status": STATUS_SATISFIED},
        }
        res = self.census(physical_runs_count=REQUIRED_INDEPENDENT_RUNS,
                          physical_evidence=recs, requirement_status=covered)
        self.assertEqual(res["physical_runs_verified"], REQUIRED_INDEPENDENT_RUNS)
        self.assertTrue(res["physical_acceptance_ready"])
        self.assertEqual(res["acceptance_verdict"], VERDICT_PHYSICALLY_ACCEPTED)

    def test_runs_without_requirement_coverage_cannot_be_fully_accepted(self):
        """Counts plus a satisfied run tally is still not a claim about requirements."""
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_runs_count=REQUIRED_INDEPENDENT_RUNS, physical_evidence=recs)
        self.assertEqual(res["physical_runs_verified"], REQUIRED_INDEPENDENT_RUNS)
        self.assertFalse(res["physical_acceptance_ready"])
        self.assertEqual(res["acceptance_verdict"], VERDICT_DATA_INSUFFICIENT)
        self.assertNotEqual(res["handover_verdict"], "FULLY_ACCEPTED")

    def test_unsatisfied_requirement_blocks_full_acceptance(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        covered = {
            "A-W04-03": {"status": STATUS_SATISFIED},
            "A-W08-01": {"status": STATUS_INSUFFICIENT},
        }
        res = self.census(physical_evidence=recs, requirement_status=covered)
        self.assertFalse(res["physical_acceptance_ready"])

    def test_open_gates_with_verified_runs_stay_pending(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_evidence=recs, open_hardware_gates=["H-GATE-1"],
                          requirement_status={"A-W04-03": {"status": STATUS_SATISFIED}})
        self.assertFalse(res["physical_acceptance_ready"])
        self.assertEqual(res["acceptance_verdict"], VERDICT_PHYSICAL_ACCEPTANCE_PENDING)

    def test_member_a_never_asserts_system_integration(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_evidence=recs)
        self.assertIs(res["system_integration_verified"], False)
        self.assertEqual(res["system_integration_note"], SYSTEM_INTEGRATION_NOT_ASSERTABLE)

    def test_out_of_range_week_id_is_surfaced(self):
        res = self.census(weeks_delivered=ALL_WEEKS + [99])
        self.assertEqual(res["unexpected_week_ids"], [99])
        self.assertFalse(res["all_weeks_accounted_for"])

    def test_absent_gate_register_reports_unknown_not_zero(self):
        res = collate_acceptance_census(
            weeks_delivered=ALL_WEEKS, physical_runs_count=5,
            hardware_status="FAIL_CLOSED_FROZEN",
        )
        self.assertIsNone(res["open_hardware_gates_count"])
        self.assertEqual(res["open_hardware_gates"], [])

    def test_citing_an_arbitrary_repo_file_is_refused(self):
        """Pointing at any readable file is not a capture: it must be declared evidence."""
        (self.root / "README.md").write_text("not a capture\n", encoding="utf-8")
        rec = _record(self.root, "evidence/A/W24/run1.csv", b"payload\n", 1)
        rec["artifact_path"] = "README.md"
        rec["sha256"] = hashlib.sha256(
            (self.root / "README.md").read_bytes()).hexdigest()
        res = self.census(physical_evidence=[rec])
        self.assertTrue(any("EVIDENCE_ARTIFACT_UNTRUSTED" in r for r in res["evidence_refusals"]))
        self.assertFalse(res["physical_acceptance_ready"])

    def test_unpinned_artifact_is_refused(self):
        rec = _record(self.root, "evidence/A/W24/run1.csv", b"payload\n", 1, pin=False)
        res = self.census(physical_evidence=[rec])
        self.assertTrue(any("EVIDENCE_ARTIFACT_UNPINNED" in r for r in res["evidence_refusals"]))
        self.assertEqual(res["physical_runs_verified"], 0)

    def test_parent_traversal_path_is_refused(self):
        outside = self.root.parent / "outside-run.csv"
        try:
            outside.write_bytes(b"boot_id,BOOT-1\npayload\n")
            self.addCleanup(outside.unlink, missing_ok=True)
            rec = _record(self.root, "evidence/A/W24/run1.csv", b"payload\n", 1)
            rec["artifact_path"] = "../outside-run.csv"
            rec["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
            res = self.census(physical_evidence=[rec])
            self.assertTrue(any("EVIDENCE_ARTIFACT_UNTRUSTED" in r for r in res["evidence_refusals"]))
            self.assertFalse(res["physical_acceptance_ready"])
        except OSError:
            self.skipTest("cannot write beside the sandbox root on this platform")

    def test_absolute_path_is_refused(self):
        rec = _record(self.root, "evidence/A/W24/run1.csv", b"payload\n", 1)
        rec["artifact_path"] = str(self.root / "evidence/A/W24/run1.csv")
        res = self.census(physical_evidence=[rec])
        self.assertTrue(any("EVIDENCE_ARTIFACT_UNTRUSTED" in r for r in res["evidence_refusals"]))

    def test_identical_bytes_cited_as_three_runs_count_once(self):
        first = _record(self.root, "evidence/A/W24/run1.csv", b"payload\n", 1, boot="BOOT-1")
        copy = _record(self.root, "evidence/A/W24/copy.csv", b"payload\n", 1, boot="BOOT-1")
        res = self.census(physical_evidence=[first, copy])
        self.assertEqual(res["physical_runs_verified"], 1)
        self.assertTrue(any("EVIDENCE_RUN_NOT_INDEPENDENT" in r for r in res["evidence_refusals"]))

    def test_boot_id_not_present_in_the_bytes_is_refused(self):
        rec = _record(self.root, "evidence/A/W24/run1.csv", b"payload\n", 1)
        rec["boot_id"] = "BOOT-FABRICATED"
        res = self.census(physical_evidence=[rec])
        self.assertTrue(
            any("EVIDENCE_IDENTITY_NOT_IN_ARTIFACT" in r for r in res["evidence_refusals"]))

    def test_missing_expected_config_refuses_all_records(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i) for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_evidence=recs, expected_hardware_config_id=None)
        self.assertEqual(res["physical_runs_verified"], 0)
        self.assertTrue(any("PHYSICAL_EVIDENCE_ABSENT" in r for r in res["evidence_refusals"]))

    def test_unrecognised_hardware_posture_blocks_acceptance(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        res = self.census(physical_evidence=recs, hardware_status="ENERGIZED_LIVE_HAZARD_UNRESOLVED")
        self.assertFalse(res["hardware_posture_safe"])
        self.assertFalse(res["physical_acceptance_ready"])

    def test_week_claim_without_a_dossier_blocks_acceptance(self):
        recs = [self._mk(f"evidence/A/W24/run{i}.csv", i)
                for i in range(REQUIRED_INDEPENDENT_RUNS)]
        shutil.rmtree(self.root / "evidence/A/W07")
        res = self.census(physical_evidence=recs)
        self.assertEqual(res["weeks_without_dossier"], ["W07"])
        self.assertFalse(res["physical_acceptance_ready"])

    def test_system_integration_is_a_boolean_and_a_note(self):
        res = self.census(physical_runs_count=3)
        self.assertIs(res["system_integration_verified"], False)
        self.assertEqual(res["system_integration_note"], SYSTEM_INTEGRATION_NOT_ASSERTABLE)

    def _mk(self, rel, n, **kw):
        return _record(self.root, rel, f"run {n} payload\n".encode(), n, **kw)


class TestW24EvidenceClassesAndGeneratedCensus(unittest.TestCase):
    """A capture may only evidence the requirement its own class can prove."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _week_dossiers(self.root)

    def test_record_without_evidence_class_is_refused(self):
        rec = _record(self.root, "evidence/A/W24/run1.csv", b"x\n", 1)
        del rec["evidence_class"]
        res = collate_acceptance_census(
            weeks_delivered=ALL_WEEKS, physical_runs_count=1,
            hardware_status="FAIL_CLOSED_FROZEN", open_hardware_gates=[],
            physical_evidence=[rec], repo_root=self.root,
            expected_hardware_config_id=HW_CONF)
        self.assertTrue(any("EVIDENCE_FIELD_MISSING" in r for r in res["evidence_refusals"]))

    def test_unknown_evidence_class_is_refused(self):
        rec = _record(self.root, "evidence/A/W24/run1.csv", b"x\n", 1, cls="VIBRATION_TEST")
        res = collate_acceptance_census(
            weeks_delivered=ALL_WEEKS, physical_runs_count=1,
            hardware_status="FAIL_CLOSED_FROZEN", open_hardware_gates=[],
            physical_evidence=[rec], repo_root=self.root,
            expected_hardware_config_id=HW_CONF)
        self.assertTrue(any("EVIDENCE_CLASS_UNKNOWN" in r for r in res["evidence_refusals"]))

    def test_cold_boot_capture_does_not_satisfy_cooling_requirement(self):
        rec = _record(self.root, "evidence/A/W24/boot-1.csv", b"x\n", 1, cls="COLD_BOOT_IDENTITY")
        res = collate_acceptance_census(
            weeks_delivered=ALL_WEEKS, physical_runs_count=1,
            hardware_status="FAIL_CLOSED_FROZEN", open_hardware_gates=[],
            physical_evidence=[rec], repo_root=self.root,
            expected_hardware_config_id=HW_CONF)
        self.assertEqual(res["physical_runs_verified"], 1)
        status = evaluate_requirement_evidence(
            verify_physical_evidence([rec], self.root, HW_CONF), REQUIREMENT_EVIDENCE_SPEC)
        self.assertEqual(status["A-W04-03"]["status"], STATUS_INSUFFICIENT)
        self.assertEqual(status["A-W03-04"]["status"], STATUS_SATISFIED)
        self.assertEqual(status["A-W07-02"]["status"], STATUS_INSUFFICIENT)

    def test_three_cooling_runs_satisfy_the_repeatability_threshold_only_for_cooling(self):
        recs = [_record(self.root, f"evidence/A/W24/c{i}.csv", b"x\n", i, cls="COOLING_SESSION")
                for i in range(3)]
        ver = verify_physical_evidence(recs, self.root, HW_CONF)
        status = evaluate_requirement_evidence(ver, REQUIREMENT_EVIDENCE_SPEC)
        self.assertEqual(status["A-W04-03"]["status"], STATUS_SATISFIED)
        self.assertEqual(status["A-W07-02"]["required_independent_runs"], 3)
        self.assertEqual(status["A-W07-02"]["verified_independent_runs"], 0)

    def test_generated_census_is_deterministic(self):
        _record(self.root, "evidence/A/W04/tec-cooling-response-600s.csv", b"payload\n", 1)
        _record(self.root, "evidence/A/W04/boot-default-off.csv", b"payload\n", 2,
                cls="COLD_BOOT_IDENTITY")
        first = generate_acceptance_census(self.root)
        second = generate_acceptance_census(self.root)
        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(first.encode()).hexdigest(),
                         hashlib.sha256(second.encode()).hexdigest())
        payload = json.loads(first)
        self.assertNotIn("generated_at", payload)
        self.assertTrue(payload["generated_by"].endswith("generate_acceptance_census"))

    def test_generated_census_classifies_named_captures_without_caller_claims(self):
        _record(self.root, "evidence/A/W08/envelope-by-duty.csv", b"payload\n", 7,
                cls="ELECTRICAL_ENVELOPE_SAMPLE")
        payload = json.loads(generate_acceptance_census(self.root))
        self.assertEqual(payload["runs_by_class"].get("ELECTRICAL_ENVELOPE_SAMPLE"), 1)
        self.assertEqual(payload["requirement_status"]["A-W08-01"]["status"], STATUS_SATISFIED)

    def test_generated_census_reports_unspecified_requirements_instead_of_borrowing(self):
        payload = json.loads(generate_acceptance_census(self.root))
        for requirement in REQUIREMENT_EVIDENCE_SPEC:
            self.assertIn(requirement, payload["requirement_status"])
        self.assertEqual(payload["physical_runs_verified"], 0)

    def test_generated_census_never_claims_physical_acceptance_on_real_tree(self):
        real = Path(__file__).resolve().parents[3]
        payload = json.loads(generate_acceptance_census(real))
        self.assertFalse(payload["physical_acceptance_ready"])
        self.assertNotEqual(payload["handover_verdict"], "FULLY_ACCEPTED")


if __name__ == "__main__":
    unittest.main()
