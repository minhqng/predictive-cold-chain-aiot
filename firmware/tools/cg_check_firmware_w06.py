"""Static contract checks for the ColdGuard W06 command/ACK firmware.

Like the W04 and W05 checkers this certifies only what is provable from the
sources. It does not compile the firmware and does not touch hardware.

Checks:

1.  Fail-closed posture - the command layer did not enable the output stage, did
    not introduce a requested duty, and did not relax the actuator authorization.
2.  No actuation path - nothing on the command path can drive the branch; the
    controller's own START verb remains the single call site it was in W04.
3.  Freshness - with an unsynchronized clock the validator blocks instead of
    assuming freshness, and no receive-time TTL is substituted for the canonical
    absolute expiry anywhere in the layer.
4.  Idempotency ordering - a known command_id is answered before expiry, range
    and safety are re-decided, so a replay cannot reach a different verdict.
5.  Volatile memory - the idempotency store is RAM, never NVS, so a reset cannot
    resurrect a command identity or a desire.
6.  ACK vocabulary and payload - the closed status set, the docs/02 §32.3 payload
    fields, and a truncation-refusing formatter.
7.  Applied state - reported from the device, never derived from the request.
8.  Host parity - the serial schema is 3, schemas 1 and 2 still parse, and every
    W06 field the parser requires is emitted by the formatter.
9.  Console regression guard - the verb-assignment defect W06's harness caught
    stays fixed, and arity rules did not loosen.
10. Scope guard - no network entry point, grammar version unchanged, new source in
    the build.

Exit codes: 0 = every check passed, 1 = at least one failed, 2 = usage/IO.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cg_check_firmware_w04 as w04  # noqa: E402
from cg_check_firmware_w04 import (  # noqa: E402
    Checker,
    define_value,
    extract_function_body,
    strip_comments,
)
import cg_serial  # noqa: E402
import cg_telemetry_schema as telemetry_schema  # noqa: E402

ACCEPT_STATUSES = (
    "ACCEPTED",
    "REJECTED",
    "DUPLICATE_CANONICAL",
    "EXPIRED",
    "SAFETY_BLOCKED",
    "INVALID_STATE",
    "OUT_OF_RANGE",
)


def run_checks() -> Checker:
    checker = Checker()

    config = checker.read("firmware/main/coldguard_config.h")
    command_c = strip_comments(checker.read("firmware/main/cg_command.c"))
    command_h = checker.read("firmware/main/cg_command.h")
    telemetry_c = strip_comments(checker.read("firmware/main/cg_telemetry.c"))
    telemetry_h = checker.read("firmware/main/cg_telemetry.h")
    commission_c = strip_comments(checker.read("firmware/main/cg_commission.c"))
    parser_c = strip_comments(checker.read("firmware/main/cg_tec_command.c"))
    parser_h = checker.read("firmware/main/cg_tec_command.h")
    control_c = strip_comments(checker.read("firmware/main/cg_tec_control.c"))
    log_h = checker.read("firmware/main/cg_log.h")
    cmake = checker.read("firmware/main/CMakeLists.txt")

    validate_body = extract_function_body(command_c, r"void cg_command_validate\([^)]*\)")
    checker.check(validate_body is not None, "cg_command_validate was located")
    body = validate_body or ""

    # 1. Fail-closed posture ----------------------------------------------
    checker.check(define_value(config, "CG_TEC_OUTPUT_STAGE_ENABLED") == "0",
                  "W06 did not enable the TEC output stage")
    checker.check(define_value(config, "CG_TEC_REQUEST_DUTY_PERMILLE") == "0",
                  "W06 did not introduce a requested duty")
    checker.check(define_value(config, "CG_ACTUATOR_ENABLE_ALLOWED") == "0",
                  "W06 did not relax the actuator authorization gate")

    # 2. No actuation path --------------------------------------------------
    for forbidden in ("cg_tec_start", "cg_tec_arm", "set_enables", "set_cooling_duty",
                      "cg_actuator_", "gpio_set_level", "ledc_set_duty"):
        checker.check(forbidden not in command_c,
                      f"the command layer must not call {forbidden}: it acknowledges, it does "
                      f"not actuate")
    checker.check(commission_c.count("cg_tec_start(&s_ctl") == 1,
                  "the console START verb remains the only controller start call site")
    cmdtest_case = body_span(commission_c, "case CG_TEC_CMD_CMDTEST:")
    checker.check(cmdtest_case != "" and "cg_tec_start" not in cmdtest_case
                  and "set_enables" not in cmdtest_case,
                  "the CMDTEST bridge validates and acknowledges without touching the output")

    # 3. Freshness: fail closed, never a substitute ------------------------
    checker.check("ctx->time_sync = CG_TIME_SYNC_UNSYNCHRONIZED;" in commission_c,
                  "the shipped context declares the clock unsynchronized; firmware has no wall "
                  "clock and must not pretend otherwise")
    checker.check('ctx->now_ms = 0U;' in commission_c,
                  "no issuer-clock now is fabricated for the shipped context")
    unsync_guard = "if (ctx->time_sync != CG_TIME_SYNC_SYNCHRONIZED) {"
    checker.check(unsync_guard in body,
                  "the unsynchronized-clock guard is live: without it a command would be "
                  "treated as fresh because nothing disproved it")
    checker.check('ack->reason = "EPOCH_UNSYNCHRONIZED";' in body
                  and "ack->expiry_evaluable = false" in body,
                  "an unverifiable absolute expiry blocks the command and says it is unevaluable")
    compare = body.find("ctx->now_ms > command->expires_at_ms")
    unsync = body.find(unsync_guard)
    checker.check(unsync != -1 and compare != -1 and unsync < compare,
                  "the fail-closed guard precedes the expiry comparison; a command is never "
                  "judged fresh by default")
    checker.check("MISSING_EXPIRY" in body and "unbounded" not in body,
                  "an absent expiry is refused, not treated as never expiring")
    checker.check("MISSING_CREATED_AT" in body,
                  "a command without an issue time is refused rather than assumed recent")
    # The freshness rule must not be reinterpreted anywhere in the command layer.
    # CG_TEC_ARM_TTL_MS is a different, pre-existing thing: the local ARM
    # authorization window. It is scoped out rather than silenced.
    command_h_text = command_h
    for substitute in ("received_ms + ", "uptime_ms + command->", "ttl_ms", "TTL_MS"):
        checker.check(substitute not in command_c and substitute not in command_h_text,
                      f"the command layer contains no receive-time freshness substitute "
                      f"({substitute!r}) that could stand in for created_at/expires_at")
    checker.check("CG_TEC_ARM_TTL_MS" not in cmdtest_case,
                  "the ARM authorization window is not reused as command expiry")

    # 4. Idempotency ordering ----------------------------------------------
    dup_branch = ("if (store != NULL) {\n        const cg_cmd_record_t *seen = "
                  "store_find(store, command->command_id);")
    checker.check(dup_branch in body,
                  "the duplicate lookup is live: an id already answered must be found in the "
                  "store, not re-decided against a world that has moved on")
    dup = body.find(dup_branch)
    checker.check(dup != -1 and unsync != -1 and dup < unsync,
                  "a known command_id is answered from the store before freshness, range or "
                  "safety are re-decided, so a replay cannot reach a new verdict")
    checker.check("ack->status = CG_CMD_ACK_DUPLICATE_CANONICAL;" in body,
                  "the duplicate status is assigned, not just named")
    checker.check("ack->reapplied = false;" in body,
                  "a duplicate explicitly does not apply a second time")
    checker.check("canonical_status" in command_h and "seen->status" in body,
                  "the duplicate returns the ORIGINAL verdict, not a re-evaluation")
    checker.check("store->hits++" in body and "store->evicted++" in
                  (extract_function_body(command_c, r"static void store_put\([^)]*\)") or ""),
                  "duplicate hits and retention evictions are counted, so the memory bound is "
                  "observable instead of assumed")

    # 5. Volatile memory ----------------------------------------------------
    checker.check("nvs" not in command_c.lower(),
                  "the command layer writes no NVS: command identity must not survive a reset")
    checker.check("nvs" not in commission_c.lower(),
                  "the commissioning file persists nothing either: the store lives and dies with "
                  "the boot")
    checker.check("nvs" not in cmdtest_case.lower(),
                  "the CMDTEST bridge persists nothing")
    checker.check(re.search(r"CG_CMD_STORE_CAPACITY\s+\d+", command_h) is not None,
                  "the retention size is an explicit named bound")
    checker.check("cg_cmd_store_t s_cmd_store;" in commission_c
                  and "cg_cmd_store_init(&s_cmd_store);" in commission_c,
                  "the store is a boot-scoped static initialised at start, so a reset clears it")

    # 6. ACK vocabulary and payload ----------------------------------------
    for status in ACCEPT_STATUSES:
        checker.check(f'case CG_CMD_ACK_{status}' in command_c
                      or f'"{status}"' in command_c,
                      f"the ACK status {status} is named exactly as docs/02 2168-2177 spells it")
    status_body = extract_function_body(command_c,
                                        r"const char \*cg_cmd_ack_status_name\([^)]*\)") or ""
    emitted = set(re.findall(r'return "([A-Z_]+)";', status_body))
    checker.check(emitted == set(ACCEPT_STATUSES) | {"UNKNOWN"},
                  f"the ACK status names are exactly the closed set plus UNKNOWN, found "
                  f"sorted={sorted(emitted)}: a status like VERIFIED would read as physical "
                  f"verification of an action that was never verified")
    checker.check('return "UNKNOWN";' in status_body and "default:" in status_body,
                  "an out-of-range status is named UNKNOWN instead of defaulting to a verdict")
    checker.check("parse_u64_checked" in command_c
                  and "(UINT64_MAX - digit) / 10ULL" in command_c,
                  "numeric fields are parsed with an overflow check: a digit-count bound alone "
                  "still lets 20 digits wrap, which could turn a far-future expiry in-range")
    checker.check("if (!parse_u64_checked(value, &wide) || wide > 4294967295ULL)" in command_c,
                  "an out-of-range duty is refused rather than narrowed into range by the cast")
    checker.check("char line[CG_COMMAND_ACK_LINE_MAX];" in commission_c
                  and re.search(r"CG_COMMAND_ACK_LINE_MAX\s+\d+", config) is not None,
                  "the ACK buffer is a named budget the measured worst case is tested against, "
                  "not an inline guess: a refused ACK deletes the audit record")
    checker.check('"VERIFIED"' not in command_c and '"COOLED"' not in command_c,
                  "the command layer never claims a physical outcome (docs/02 2216-2224)")
    for key in ("command_id=%s", "status=%s reason=%s", "desired_cooling=%s",
                "applied_cooling=%s", "reapplied=%d", "expiry_evaluable=%d",
                "time_sync_state=%s", "device_mode=%s", "ack_seq=%lu", "boot_id=%s",
                "uptime_ms=%llu", "output_stage=%s", "allowed_duty_max_permille=%lu"):
        checker.check(key in command_c, f"the ACK line carries {key}")
    ack_format = extract_function_body(command_c, r"int cg_command_ack_format\([^)]*\)")
    checker.check(ack_format is not None
                  and "if (overflow) {\n        buf[0] = '\\0';" in ack_format,
                  "an ACK that would not fit is refused whole by the overflow branch, never "
                  "truncated")
    checker.check("schema=1 event=ACK" in command_c and "schema=3" not in command_c,
                  "the ACK states the docs/02 command envelope version, not the serial schema")
    checker.check('ack->command_id[0] == \'\\0\'' in (ack_format or ""),
                  "an ACK naming no command is refused: it would be evidence about nothing")

    # 7. Applied state ------------------------------------------------------
    checker.check("ctx->applied_cooling_on ? CG_CMD_COOLING_ON : CG_CMD_COOLING_OFF" in command_c,
                  "applied state is copied from the device context, not derived from the request")
    checker.check("ctx->applied_duty_permille" in command_c,
                  "the ACK carries the duty the device is actually driving")
    ack_start_body = extract_function_body(command_c, r"static void ack_start\([^)]*\)") or ""
    checker.check("ctx->applied_cooling_on ? CG_CMD_COOLING_ON : CG_CMD_COOLING_OFF"
                  in ack_start_body and "ack->applied_duty_permille = ctx->applied_duty_permille;"
                  in ack_start_body,
                  "ack_start fills the applied pair from the context only")
    checker.check(ack_start_body.count("command->duty_permille") == 1
                  and "ack->desired_duty_permille = command->duty_permille;" in ack_start_body,
                  "the request's duty is read exactly once, into the desired field")
    checker.check("if (ack->status == CG_CMD_ACK_ACCEPTED)" in commission_c,
                  "the desired state advances only for an accepted command")

    # 8. Host parity --------------------------------------------------------
    checker.check(define_value(config, "CG_TELEMETRY_SCHEMA_VERSION")
                  == str(telemetry_schema.SCHEMA_VERSION),
                  "firmware and host agree on the current serial schema version")
    checker.check(telemetry_schema.SCHEMA_VERSION == 3,
                  "the serial schema is 3 while the docs/02 command envelope stays 1")
    checker.check(1 in telemetry_schema.SUPPORTED_SCHEMAS
                  and 2 in telemetry_schema.SUPPORTED_SCHEMAS,
                  "the committed W04 (schema 1) and W05 (schema 2) captures must stay parseable")
    for field in telemetry_schema.W06_REQUIRED_FIELDS:
        checker.check(f"{field}=" in telemetry_c, f"telemetry emits the W06 field {field}")
    checker.check("W06_REQUIRED_FIELDS" in dir(telemetry_schema),
                  "the host parser declares the W06 required set, so a schema-3 line is checked")
    checker.check('"NONE"' in telemetry_c and "command_id=NONE" in telemetry_c,
                  "no-command-received is named NONE, not coerced into an ACK status or a zero")
    checker.check("desired_duty_permille=nan" in telemetry_c,
                  "an unrequested duty is nan, not 0: 0 would read as an explicit request to "
                  "stay off")

    # 9. Console regression guard ------------------------------------------
    split_body = extract_function_body(parser_c, r"static bool split_line\([^)]*\)")
    checker.check(split_body is not None and split_body.count("*verb = start;") == 2,
                  "split_line assigns the verb on BOTH paths: leaving the two-token path "
                  "unassigned makes ARM/START/RUN/PHASE compare uninitialized stack memory")
    checker.check("CG_TEC_CMD_CMDTEST" in parser_h and "CMDTEST" in parser_c,
                  "the local bridge verb exists in the grammar")
    checker.check("out->flag = equals_ci(fields[1], \"ON\")" in parser_c,
                  "the bridge records cooling as an explicit flag, not by overloading a number")
    checker.check("duty > 1000UL" in parser_c,
                  "the console refuses a duty outside permille before the validator sees it")

    # 10. Scope guard -------------------------------------------------------
    checker.check(cg_serial.GRAMMAR_VERSION == 2,
                  "serial grammar stays 2: W06 adds a line kind, it does not change existing kinds")
    checker.check('#define CG_LOG_CMDACK "CMDACK"' in config,
                  "the ACK line kind is a configuration token, not a literal in one call site")
    checker.check("CG_LOG_CMDACK" in config and "#CG CMDACK" in log_h,
                  "the log grammar header documents the new line kind")
    for source in ("firmware/main/cg_command.c", "firmware/main/cg_telemetry.c",
                   "firmware/main/cg_tec_command.c", "firmware/main/cg_commission.c"):
        text = strip_comments(checker.read(source))
        checker.check(w04.NETWORK_TOKEN.search(text) is None,
                      f"{source} opens no network entry point")
    checker.check('"cg_command.c"' in cmake, "cg_command.c is in the build")

    return checker


def body_span(text: str, marker: str) -> str:
    start = text.find(marker)
    if start == -1:
        return ""
    end = text.find("case CG_TEC_CMD_", start + len(marker))
    return text[start:end if end != -1 else len(text)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Static contract checks for the W06 command/ACK firmware sources."
    )
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    args = parser.parse_args(argv)

    try:
        checker = run_checks()
    except OSError as exc:
        print(f"cannot read firmware sources: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        for note in checker.notes:
            print(note)

    if checker.failures:
        print()
        print("W06 STATIC FIRMWARE CHECK: FAIL")
        for failure in checker.failures:
            print(f"  - {failure}")
        return 1

    print()
    print(f"W06 STATIC FIRMWARE CHECK: PASS ({len(checker.notes)} checks)")
    print("Reminder: this does NOT compile the firmware and does not touch hardware.")
    print("The executable behaviour proof is firmware/tools/tests/cg_w06_harness.c.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
