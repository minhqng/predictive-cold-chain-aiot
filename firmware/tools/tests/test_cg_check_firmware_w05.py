"""Negative tests for the W05 static checker.

A checker that cannot fail is not a check. Each case below mutates one source
in memory (no file is touched) and requires ``cg_check_firmware_w05.run_checks``
to fail with the message that names the regression. The mutations are the ways
this slice could quietly stop meaning what it claims:

* inventing a calibration identifier when no bundle was measured;
* letting a command replay or reset the per-boot frame counter;
* dropping the door timestamp or the energy register from the snapshot again;
* defaulting an unobserved source to a definite verdict;
* counting good probes where the contract counts failed ones;
* deriving the applied cooling state from the requested duty;
* initialising the liveness registry after the producers start;
* emitting a field the host schema does not declare, or removing one it needs.

The real sources are also checked once and must pass.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_check_firmware_w05 as checker_module  # noqa: E402

CONFIG = "firmware/main/coldguard_config.h"
QUALITY = "firmware/main/cg_quality.c"
QUALITY_C = QUALITY
HEALTH = "firmware/main/cg_health.c"
SNAPSHOT = "firmware/main/cg_snapshot.c"
SNAPSHOT_H = "firmware/main/cg_snapshot.h"
TELEMETRY = "firmware/main/cg_telemetry.c"
COMMISSION = "firmware/main/cg_commission.c"
APP_MAIN = "firmware/main/app_main.c"
POWER = "firmware/main/cg_power.c"
DS18B20 = "firmware/main/cg_ds18b20.c"
CONTROL = "firmware/main/cg_tec_control.c"
CONTROL_H = "firmware/main/cg_tec_control.h"


class W05CheckerTests(unittest.TestCase):
    def run_with(self, relative: str, old: str, new: str):
        original_read = checker_module.Checker.read
        test_case = self

        def fake_read(instance, requested: str) -> str:
            text = original_read(instance, requested)
            if requested == relative:
                test_case.assertIn(old, text, f"mutation anchor missing in {relative}")
                return text.replace(old, new, 1)
            return text

        checker_module.Checker.read = fake_read
        try:
            return checker_module.run_checks()
        finally:
            checker_module.Checker.read = original_read

    def test_real_tree_passes(self) -> None:
        checker = checker_module.run_checks()
        self.assertEqual(checker.failures, [])

    # 1. identity --------------------------------------------------------

    def test_invented_calibration_id_is_caught(self) -> None:
        checker = self.run_with(CONFIG, '#define CG_CALIBRATION_ID "UNRECORDED"',
                                '#define CG_CALIBRATION_ID "CG-CAL-001"')
        self.assertIn("calibration_id is the UNRECORDED token", " ".join(checker.failures))

    def test_command_resetting_seq_is_caught(self) -> None:
        checker = self.run_with(
            COMMISSION,
            "case CG_TEC_CMD_STATUS:",
            "case CG_TEC_CMD_STATUS:\n            s_telem_seq = 0;",
        )
        self.assertIn("no console command resets or replays the frame counter",
                      " ".join(checker.failures))

    def test_removing_device_id_from_the_line_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, '"run_id=%s device_id=%s boot_id=%s boot_count=%lu seq=%lu "',
                                '"run_id=%s boot_id=%s boot_count=%lu seq=%lu "')
        self.assertTrue(checker.failures)

    # 2. coherence -------------------------------------------------------

    def test_dropping_door_observation_time_is_caught(self) -> None:
        checker = self.run_with(SNAPSHOT, "s_snap.door_obs_ms = obs_ms;",
                                "/* door time dropped */")
        self.assertIn("the door publication records an observation time (W04 recorded none)",
                      " ".join(checker.failures))

    def test_dropping_energy_from_the_snapshot_is_caught(self) -> None:
        checker = self.run_with(SNAPSHOT, "s_snap.energy_wh = energy_wh;",
                                "/* energy dropped */")
        self.assertIn("the decoded PZEM energy register reaches the snapshot (W04 logged it only)",
                      " ".join(checker.failures))

    def test_removing_an_age_field_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, '" thermal_age_ms=%llu power_age_ms=%llu door_age_ms=%llu"',
                                '" power_age_ms=%llu door_age_ms=%llu"')
        self.assertIn("telemetry reports thermal_age_ms", " ".join(checker.failures))

    def test_wrapping_age_instead_of_saturating_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, "return UINT64_MAX;", "return 0U;")
        self.assertIn("an age is saturated, never wrapped", " ".join(checker.failures))

    def test_snapshot_init_back_to_invalid_is_caught(self) -> None:
        checker = self.run_with(SNAPSHOT, "s_snap.thermal_quality = CG_QUALITY_UNKNOWN;",
                                "s_snap.thermal_quality = CG_QUALITY_INVALID;")
        self.assertIn("a snapshot before the first thermal publication is UNKNOWN, not INVALID",
                      " ".join(checker.failures))

    # 3. quality ---------------------------------------------------------

    def test_defaulting_unknown_quality_to_invalid_is_caught(self) -> None:
        checker = self.run_with(DS18B20, 'return "UNKNOWN";', 'return "INVALID";')
        self.assertIn("cg_quality_name maps an out-of-range thermal quality to UNKNOWN",
                      " ".join(checker.failures))

    def test_counting_good_probes_instead_of_failed_probes_is_caught(self) -> None:
        checker = self.run_with(QUALITY_C,
                               "const int failed = in->probes_expected - in->probes_ok;",
                               "const int failed = in->probes_ok;")
        self.assertTrue(checker.failures)

    def test_collapse_order_change_is_caught(self) -> None:
        checker = self.run_with(QUALITY_C,
                                "if (saw_invalid) {\n        return CG_Q_INVALID;\n    }",
                                "if (saw_invalid) {\n        return CG_Q_DEGRADED;\n    }")
        self.assertIn("collapse order is INVALID > UNKNOWN > DEGRADED > VALID",
                      " ".join(checker.failures))

    def test_dropping_a_quality_field_is_caught(self) -> None:
        checker = self.run_with(
            TELEMETRY,
            '" thermal_quality=%s environment_quality=%s door_quality=%s electrical_quality=%s"',
            '" environment_quality=%s door_quality=%s electrical_quality=%s"',
        )
        self.assertIn("telemetry emits thermal_quality", " ".join(checker.failures))

    # 4. liveness --------------------------------------------------------

    def test_registry_init_after_tasks_start_is_caught(self) -> None:
        checker = self.run_with(
            APP_MAIN,
            "cg_health_registry_init(periods);",
            "/* deferred to the first task iteration */",
        )
        self.assertIn("the registry is initialised before any producer task can start",
                      " ".join(checker.failures))

    def test_power_producer_not_beating_is_caught(self) -> None:
        checker = self.run_with(POWER, "cg_health_registry_beat(CG_PRODUCER_POWER, obs_ms);",
                                "/* heartbeat dropped */")
        self.assertIn("the PZEM task beats once per poll attempt", " ".join(checker.failures))

    def test_health_fallback_to_ok_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, "CG_TELEM_HEALTH_UNKNOWN", "CG_TELEM_STATUS_OK")
        self.assertTrue(checker.failures)

    def test_unlocked_registry_is_caught(self) -> None:
        checker = self.run_with(HEALTH, "CG_HEALTH_LOCK();\n    cg_health_eval(s_registry, now_ms, out);",
                                "cg_health_eval(s_registry, now_ms, out);")
        self.assertTrue(checker.failures)

    # 5. applied state ---------------------------------------------------

    def test_deriving_applied_state_from_duty_is_caught(self) -> None:
        checker = self.run_with(
            TELEMETRY,
            "applied = tec.outputs_energized ? CG_TELEM_APPLIED_ON : CG_TELEM_APPLIED_OFF;",
            "applied = tec.duty_permille > 0U ? CG_TELEM_APPLIED_ON : CG_TELEM_APPLIED_OFF;",
        )
        self.assertIn("cooling_applied comes from the output layer's own record",
                      " ".join(checker.failures))

    def test_stale_evidence_smoothed_to_idle_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, "return CG_TELEM_EVIDENCE_STALE;",
                                "return CG_TELEM_EVIDENCE_IDLE;")
        self.assertIn("a stale electrical reading is reported as unobserved",
                      " ".join(checker.failures))

    def test_status_losing_applied_state_is_caught(self) -> None:
        checker = self.run_with(CONTROL, "out->outputs_energized = ctl->outputs_energized;",
                                "/* not exposed */")
        self.assertIn("cg_tec_get_status copies the applied state",
                      " ".join(checker.failures))
        checker = self.run_with(CONTROL_H, "bool outputs_energized;", "/* removed */")
        self.assertIn("the controller status exposes what the outputs were left driving",
                      " ".join(checker.failures))

    # 6. scope guard -----------------------------------------------------

    def test_output_stage_flip_is_still_caught(self) -> None:
        checker = self.run_with(CONFIG, "#define CG_TEC_OUTPUT_STAGE_ENABLED 0",
                                "#define CG_TEC_OUTPUT_STAGE_ENABLED 1")
        self.assertIn("W05 did not enable the TEC output stage", " ".join(checker.failures))

    def test_new_duty_request_is_caught(self) -> None:
        checker = self.run_with(CONFIG, "#define CG_TEC_REQUEST_DUTY_PERMILLE 0",
                                "#define CG_TEC_REQUEST_DUTY_PERMILLE 100")
        self.assertIn("W05 did not introduce a requested duty", " ".join(checker.failures))

    def test_schema_drift_from_host_is_caught(self) -> None:
        checker = self.run_with(CONFIG, "#define CG_TELEMETRY_SCHEMA_VERSION 2",
                                "#define CG_TELEMETRY_SCHEMA_VERSION 3")
        self.assertIn("firmware and host agree on the current serial schema version",
                      " ".join(checker.failures))

    def test_network_import_is_caught(self) -> None:
        checker = self.run_with(HEALTH, "#include <stdio.h>", "#include <stdio.h>\n"
                                                              "/* esp_wifi_connect(); */")
        # A comment is stripped before the scan, so the checker must not fire on it.
        self.assertEqual(checker.failures, [])
        checker = self.run_with(HEALTH, "#include <stdio.h>",
                                "#include <stdio.h>\nvoid probe(void) { esp_wifi_connect(); }")
        self.assertTrue(checker.failures)

    # 7. guards added after the independent review found assertions that could
    #    not fail - each of these mutations leaves the old checks green.

    def test_unpublished_probe_counts_are_caught(self) -> None:
        """The defect that made every frame UNKNOWN: publish_thermal not copying
        the driver's measurement counts."""
        checker = self.run_with(SNAPSHOT, "s_snap.probes_ok = snap->measurement_ok;",
                                "/* copy dropped */")
        self.assertIn("the driver's probe counts are copied into the snapshot",
                      " ".join(checker.failures))

    def test_degraded_becoming_unreachable_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, "snap->thermal_quality != CG_QUALITY_INVALID",
                                "snap->thermal_valid")
        self.assertIn("so DEGRADED is reachable", " ".join(checker.failures))

    def test_hot_side_status_argument_swap_is_caught(self) -> None:
        """A chamber reading routed into the hot-side field with a real status
        token. The old check only required the literal somewhere in the file."""
        checker = self.run_with(
            TELEMETRY,
            "fmt_float(false, 0.0f, t_hot, sizeof(t_hot)), CG_TELEM_STATUS_NOT_ASSIGNED",
            "fmt_float(snap->t_valid[CG_ROLE_T2], snap->t_c[CG_ROLE_T2], t_hot, "
            "sizeof(t_hot)), t_inside_status",
        )
        self.assertIn("the hot-side field is hard-wired to a missing value with NOT_ASSIGNED",
                      " ".join(checker.failures))

    def test_rom_emit_deletion_is_caught(self) -> None:
        """Deleting the append must fail even though the rom_keys table still
        names t1_rom..spare_rom."""
        checker = self.run_with(TELEMETRY, '" %s=%s", rom_keys[role],', '" %s=%s", "",')
        self.assertIn("telemetry emits the ROM values from the frame",
                      " ".join(checker.failures))

    def test_rom_source_claim_removal_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, " role_status=%s rom_source=%s",
                                " role_status=%s")
        self.assertTrue(checker.failures)

    def test_unconditional_applied_state_clear_is_caught(self) -> None:
        checker = self.run_with(
            CONTROL,
            "if (ok) {\n        ctl->outputs_energized = false;\n        ctl->duty_permille = 0U;\n    }",
            "ctl->outputs_energized = false;\n    ctl->duty_permille = 0U;",
        )
        self.assertIn("claiming OFF while the branch is still being driven",
                      " ".join(checker.failures))

    def test_truncating_number_formatter_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY,
                                "if (written < 0 || (size_t)written >= cap) {",
                                "if (written < 0) {")
        self.assertIn("never a truncated prefix of a plausible number",
                      " ".join(checker.failures))

    def test_door_age_override_removal_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, "quality_in.door_age_over_limit = ",
                                "/* quality_in.door_age_over_limit = */ ")
        self.assertIn("the door quality gets the same independent age cross-check",
                      " ".join(checker.failures))


if __name__ == "__main__":
    unittest.main()
