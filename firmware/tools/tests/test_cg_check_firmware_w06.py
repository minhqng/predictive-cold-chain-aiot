"""Negative tests for the W06 static checker.

Each case mutates one source in memory and requires ``run_checks`` to fail with
the message that names the regression. The set is chosen around the promises this
slice makes: that a command is never treated as fresh without a synchronized
clock, that a replay never applies twice, that the command layer cannot actuate,
and that the idempotency memory cannot survive a reset.

One case is a must-not-fire control, so the suite also proves the checker is not
merely always failing.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_check_firmware_w06 as checker_module  # noqa: E402

CONFIG = "firmware/main/coldguard_config.h"
COMMAND = "firmware/main/cg_command.c"
COMMISSION = "firmware/main/cg_commission.c"
PARSER = "firmware/main/cg_tec_command.c"
TELEMETRY = "firmware/main/cg_telemetry.c"


class W06CheckerTests(unittest.TestCase):
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

    # 3. freshness ---------------------------------------------------------

    def test_receive_time_ttl_substitute_is_caught(self) -> None:
        checker = self.run_with(
            COMMAND,
            "if (ctx->time_sync != CG_TIME_SYNC_SYNCHRONIZED) {",
            "if (false) {",
        )
        self.assertTrue(any("fail-closed guard precedes the expiry comparison" in failure
                            for failure in checker.failures))

    def test_assuming_fresh_when_unsync_is_caught(self) -> None:
        checker = self.run_with(COMMAND, "EPOCH_UNSYNCHRONIZED", "FRESH_ASSUMED")
        self.assertTrue(any("an unverifiable absolute expiry blocks the command" in failure
                            for failure in checker.failures))

    def test_absent_expiry_treated_as_unbounded_is_caught(self) -> None:
        checker = self.run_with(COMMAND, 'ack->reason = "MISSING_EXPIRY";',
                                'ack->reason = "NO_EXPIRY_REQUESTED";\n        return;')
        self.assertTrue(any("an absent expiry is refused before any clock reasoning" in failure
                            for failure in checker.failures))

    def test_pre_identity_rejection_that_remembers_is_caught(self) -> None:
        """A foreign or malformed record must not take the canonical result with it."""
        checker = self.run_with(
            COMMAND,
            'ack->reason = "DEVICE_ID_MISMATCH";\n        return;',
            'ack->reason = "DEVICE_ID_MISMATCH";\n'
            '        if (store != NULL) {\n            store_put(store, ack);\n        }\n'
            '        return;',
        )
        self.assertTrue(any("schema and device-identity rejections are not stored" in failure
                            for failure in checker.failures))

    def test_missing_local_source_gate_is_caught(self) -> None:
        checker = self.run_with(
            COMMAND,
            "if (command->source == CG_CMD_SOURCE_LOCAL_CONSOLE) {",
            "if (false) {",
        )
        self.assertTrue(any("a source gate precedes the ACCEPTED assignment" in failure
                            for failure in checker.failures))

    def test_fabricated_now_ms_is_caught(self) -> None:
        checker = self.run_with(COMMISSION, "ctx->now_ms = 0U;",
                                "ctx->now_ms = ctx->uptime_ms;")
        self.assertTrue(any("no issuer-clock now is fabricated" in failure
                            for failure in checker.failures))

    def test_sync_claim_flip_is_caught(self) -> None:
        checker = self.run_with(COMMISSION,
                                "ctx->time_sync = CG_TIME_SYNC_UNSYNCHRONIZED;",
                                "ctx->time_sync = CG_TIME_SYNC_SYNCHRONIZED;")
        self.assertTrue(any("declares the clock unsynchronized" in failure
                            for failure in checker.failures))

    # 4. idempotency -------------------------------------------------------

    def test_replay_redecision_is_caught(self) -> None:
        """Moving the duplicate check after the freshness block lets a replay be
        judged against a world that has moved on."""
        checker = self.run_with(
            COMMAND,
            "    if (store != NULL) {\n        const cg_cmd_record_t *seen =",
            "    if (false) {\n        const cg_cmd_record_t *seen =",
        )
        self.assertTrue(any("a known command_id is answered from the store before" in failure
                            for failure in checker.failures))

    def test_duplicate_reapplication_is_caught(self) -> None:
        checker = self.run_with(COMMAND, "ack->reapplied = false;", "ack->reapplied = true;")
        self.assertTrue(any("a duplicate explicitly does not apply a second time" in failure
                            for failure in checker.failures))

    # 5. volatility --------------------------------------------------------

    def test_persisted_command_store_is_caught(self) -> None:
        checker = self.run_with(COMMISSION, "cg_cmd_store_init(&s_cmd_store);",
                                "cg_cmd_store_init(&s_cmd_store);\n    nvs_open(\"coldguard\", "
                                "NVS_READWRITE, NULL);")
        self.assertTrue(any("the store is a boot-scoped static" in failure or
                            "persists nothing" in failure or "writes no NVS" in failure
                            for failure in checker.failures))

    # 2. no actuation path --------------------------------------------------

    def test_command_layer_actuation_is_caught(self) -> None:
        checker = self.run_with(COMMAND, "const char *cg_cmd_cooling_name(cg_cmd_cooling_t",
                                "void cg_tec_start(void);\n\n"
                                "const char *cg_cmd_cooling_name(cg_cmd_cooling_t")
        self.assertTrue(any("must not call" in failure for failure in checker.failures))

    def test_bridge_calling_start_is_caught(self) -> None:
        checker = self.run_with(COMMISSION, "            record_command_state(&ack);",
                                "            cg_tec_start(&s_ctl, in, 1000U, 250U);\n"
                                "            record_command_state(&ack);")
        self.assertTrue(any("the console START verb remains the only controller start" in failure
                            or "without touching the output" in failure
                            for failure in checker.failures))

    def test_output_stage_flip_is_caught(self) -> None:
        checker = self.run_with(CONFIG, "#define CG_TEC_OUTPUT_STAGE_ENABLED 0",
                                "#define CG_TEC_OUTPUT_STAGE_ENABLED 1")
        self.assertTrue(checker.failures)

    # 6/7. ACK --------------------------------------------------------------

    def test_truncating_ack_is_caught(self) -> None:
        checker = self.run_with(COMMAND, "    if (overflow) {\n        buf[0] = '\\0';",
                                "    if (false) {\n        buf[0] = '\\0';")
        self.assertTrue(any("never truncated" in failure for failure in checker.failures))

    def test_applied_state_from_request_is_caught(self) -> None:
        checker = self.run_with(
            COMMAND,
            "ctx->applied_cooling_on ? CG_CMD_COOLING_ON : CG_CMD_COOLING_OFF",
            "command->cooling == CG_CMD_COOLING_ON ? CG_CMD_COOLING_ON : CG_CMD_COOLING_OFF",
        )
        self.assertTrue(any("applied state is copied from the device context" in failure
                            for failure in checker.failures))

    def test_missing_ack_field_is_caught(self) -> None:
        checker = self.run_with(COMMAND, "reapplied=%d expiry_evaluable=%d",
                                "reapplied=%d")
        self.assertTrue(any("ACK line carries" in failure for failure in checker.failures))

    def test_ack_claiming_thermal_verification_is_caught(self) -> None:
        """An ACK is protocol evidence. A status that reads as physical
        verification has no place in the closed vocabulary."""
        checker = self.run_with(COMMAND, 'case CG_CMD_ACK_OUT_OF_RANGE:\n            return "OUT_OF_RANGE";',
                                'case CG_CMD_ACK_OUT_OF_RANGE:\n            return "OUT_OF_RANGE";\n'
                                '        case 99:\n            return "VERIFIED";')
        self.assertTrue(any("closed set plus UNKNOWN" in failure or "physical outcome" in failure
                            for failure in checker.failures))

    # 8. host parity --------------------------------------------------------

    def test_schema_drift_is_caught(self) -> None:
        checker = self.run_with(CONFIG, "#define CG_TELEMETRY_SCHEMA_VERSION 3",
                                "#define CG_TELEMETRY_SCHEMA_VERSION 4")
        self.assertTrue(any("agree on the current serial schema" in failure
                            for failure in checker.failures))

    def test_history_erasure_is_caught(self) -> None:
        """A parser that stops accepting schema 1 orphans the committed W04
        captures."""
        import cg_telemetry_schema as schema

        original = schema.SUPPORTED_SCHEMAS
        schema.SUPPORTED_SCHEMAS = (3,)
        try:
            checker = checker_module.run_checks()
        finally:
            schema.SUPPORTED_SCHEMAS = original
        self.assertTrue(any("must stay parseable" in failure for failure in checker.failures))

    def test_no_command_coerced_to_zero_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, "command_id=NONE desired_cooling=NONE"
                                            " desired_duty_permille=nan",
                                "command_id=NONE desired_cooling=NONE desired_duty_permille=0")
        self.assertTrue(any("an unrequested duty is nan" in failure
                            for failure in checker.failures))

    # 9. console regression guard -------------------------------------------

    def test_verb_assignment_regression_is_caught(self) -> None:
        """The uninitialized-verb defect W06's harness caught in the delivered
        W04 parser must not come back."""
        checker = self.run_with(PARSER, "    *verb = start;\n    *space = '\\0';",
                                "    *space = '\\0';")
        self.assertTrue(any("split_line assigns the verb on BOTH paths" in failure
                            for failure in checker.failures))

    def test_cmdtest_duty_bound_removed_is_caught(self) -> None:
        checker = self.run_with(PARSER, "duty > 1000UL", "duty > 100000UL")
        self.assertTrue(any("refuses a duty outside permille" in failure
                            for failure in checker.failures))

    # must-not-fire control --------------------------------------------------

    def test_commented_out_call_does_not_fire(self) -> None:
        checker = self.run_with(COMMAND, "#include <stdio.h>",
                                "#include <stdio.h>\n/* cg_tec_start(); */")
        self.assertEqual(checker.failures, [])


if __name__ == "__main__":
    unittest.main()
