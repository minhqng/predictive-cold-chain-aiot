"""Negative tests for the W04 static checker.

A checker that cannot fail is not a check. These tests feed ``run_checks``
mutated source text (in memory, no file is touched) and require it to fail
on each violation:

* output stage flipped on in the delivered configuration;
* a shipped limit marked RESOLVED without evidence;
* the telemetry wall-clock provenance removed;
* the adapter's enable refusal removed;
* the start ordering broken.

The real sources are also checked once and must pass.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import cg_check_firmware_w04 as checker_module  # noqa: E402

CONFIG = "firmware/main/coldguard_config.h"
LIMITS = "firmware/main/cg_tec_limits.c"
TELEMETRY = "firmware/main/cg_telemetry.c"
HW = "firmware/main/cg_tec_hw.c"
DOC = "docs/06-tec-commissioning-safety-and-limits.md"
DOC_PRODUCTION_STATUS = "PRODUCTION TEC OUTPUT STAGE COMPILED OUT AND NOT AUTHORIZED"
DOC_H6_STATUS = "H6 BENCH ENERGIZATION EXECUTED UNDER OPERATOR SUPERVISION"
CONTROL = "firmware/main/cg_tec_control.c"
COMMISSION = "firmware/main/cg_commission.c"


class W04CheckerTests(unittest.TestCase):
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

    def test_output_stage_flip_is_caught(self) -> None:
        checker = self.run_with(CONFIG, "#define CG_TEC_OUTPUT_STAGE_ENABLED 0",
                                "#define CG_TEC_OUTPUT_STAGE_ENABLED 1")
        self.assertTrue(checker.failures)

    def test_resolved_limit_without_evidence_is_caught(self) -> None:
        checker = self.run_with(LIMITS, ".state = CG_LIMIT_UNRESOLVED,",
                                ".state = CG_LIMIT_RESOLVED,")
        self.assertTrue(checker.failures)

    def test_fabricated_timestamp_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, 'timestamp_utc=UNAVAILABLE ',
                                'timestamp_utc=2026-01-01T00:00:00Z ')
        self.assertTrue(checker.failures)

    def test_adapter_enable_refusal_removal_is_caught(self) -> None:
        checker = self.run_with(HW, "if (ren || len) {", "if (false) {")
        self.assertTrue(checker.failures)

    def test_truncated_telemetry_path_is_caught(self) -> None:
        checker = self.run_with(TELEMETRY, "if (overflow) {", "if (false) {")
        self.assertTrue(checker.failures)

    def test_shrunk_telemetry_budget_is_caught(self) -> None:
        # The budget value moves when a longer frame is commissioned, so read the
        # shipped value instead of hard-coding an anchor that rots with it.
        config_text = (checker_module.REPO_ROOT / CONFIG).read_text(encoding="utf-8")
        current = checker_module.define_value(config_text, "CG_TELEMETRY_LINE_MAX")
        self.assertIsNotNone(current, f"{CONFIG} declares no CG_TELEMETRY_LINE_MAX")
        checker = self.run_with(CONFIG, f"#define CG_TELEMETRY_LINE_MAX {current}",
                                "#define CG_TELEMETRY_LINE_MAX 256")
        self.assertIn("telemetry line budget covers the worst-case frame with headroom",
                      checker.failures)

    def test_docs06_status_line_removal_is_caught(self) -> None:
        checker = self.run_with(DOC, DOC_PRODUCTION_STATUS, "STATUS LINE REMOVED")
        self.assertIn(
            "docs/06 states the production output stage is still unauthorized",
            checker.failures,
        )

    def test_network_token_rejects_real_entry_points(self) -> None:
        for violation in (
            '#include "lwip/netdb.h"',
            "mbedtls_ssl_setup(&ssl);",
            'esp_netif_init();',
            'int s = socket(AF_INET, SOCK_STREAM, 0);',
            'gethostbyname("coldguard.local");',
            "esp_wifi_start();",
            'MQTTClient_publish(msg);',
            "struct esp_transport *t = esp_transport_init();",
        ):
            self.assertIsNotNone(checker_module.NETWORK_TOKEN.search(violation),
                                 f"network entry point not caught: {violation}")

    def test_network_token_keeps_bench_vocabulary(self) -> None:
        for clean in (
            "cg_rs485_send_frame(frame, len);",
            "if (xQueueSend(s_queue, &command, 0) != pdTRUE) {",
            "uart_write_bytes(CG_RS485_UART_PORT, buf, n);",
            "esp_timer_start_once(guard_timer, seconds * 1000000);",
            "cg_tec_control_tick(ctl, &inputs, &snapshot);",
        ):
            self.assertIsNone(checker_module.NETWORK_TOKEN.search(clean),
                              f"non-network code rejected: {clean}")

    def test_docs06_energization_disclosure_removal_is_caught(self) -> None:
        checker = self.run_with(DOC, DOC_H6_STATUS, "STATUS LINE REMOVED")
        self.assertIn(
            "docs/06 discloses the supervised H6 energization instead of claiming "
            "no power test has ever run",
            checker.failures,
        )

    def test_start_order_break_is_caught(self) -> None:
        checker = self.run_with(
            CONTROL,
            "if (!ctl->ops.set_fan(true)) {",
            "if (!ctl->ops.set_cooling_duty(duty_permille)) {",
        )
        self.assertTrue(checker.failures)

    def test_wdt_subscription_missing_from_task_is_caught(self) -> None:
        checker = self.run_with(COMMISSION,
                                "if (esp_task_wdt_add(NULL) != ESP_OK) {",
                                "if (false) {")
        self.assertIn(
            "the commissioning task subscribes to the task watchdog from its own context and resets it",
            checker.failures,
        )

    def test_wdt_subscription_from_start_context_is_caught(self) -> None:
        checker = self.run_with(
            COMMISSION,
            "    (void)xTaskCreate(commission_task",
            "    (void)esp_task_wdt_add(NULL);\n    (void)xTaskCreate(commission_task",
        )
        self.assertIn(
            "cg_commission_start does not subscribe its caller (main) task to the task watchdog",
            checker.failures,
        )


if __name__ == "__main__":
    unittest.main()
