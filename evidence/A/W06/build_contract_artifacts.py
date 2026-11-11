"""Regenerate the W06 evidence artifacts from the delivered firmware sources.

    py evidence/A/W06/build_contract_artifacts.py [--check]

Everything here is produced by compiling and running the real
``firmware/main/cg_command.c`` (and its telemetry neighbour) through
``firmware/tools/tests/cg_w06_harness.c``. The harness emits its fixtures only
after all 36 scenarios have passed, so an artifact cannot be generated from a
tree that fails its own tests. Nothing is typed into these files by hand.

Artifacts:

``ack-fixture.json``
    Five labelled ``#CG CMDACK`` lines - the shipped unsynchronized case, a
    synchronized acceptance, an expired command, a wrong-device command, and a
    replay - each with the field map parsed back out of the emitted bytes.

``duplicate-command-log.jsonl`` / ``expired-command-log.jsonl`` /
``reset-command-log.jsonl``
    The three command logs docs/05A §15 names as deliverables, built from the
    scenario traces the validator produced. They are **host** logs: a device
    capture of the same events requires an issuer, which today does not exist
    because this firmware has no transport.

Two honesty rules are asserted at the end, not assumed:

* every fixture record is labelled ``is_physical_measurement: false`` and
  ``is_host_scenario: true``;
* no fixture may report an applied cooling state, because the output stage is
  compiled out - if one ever did, the generator was run against a tree that can
  actuate, and that is a safety claim this slice does not make.

Requires a host C compiler; it fails loudly rather than writing a hand-made
substitute.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[2]
TOOLS = REPO / "firmware" / "tools"
TESTS = TOOLS / "tests"
MAIN = REPO / "firmware" / "main"

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TESTS))

import cg_telemetry_schema as telemetry_schema  # noqa: E402  (unused guard below)

HARNESS = TESTS / "cg_w06_harness.c"
SOURCES = [
    MAIN / "cg_command.c",
    MAIN / "cg_quality.c",
    MAIN / "cg_health.c",
    MAIN / "cg_snapshot.c",
    MAIN / "cg_telemetry.c",
    MAIN / "cg_tec_control.c",
    MAIN / "cg_tec_limits.c",
    MAIN / "cg_tec_command.c",
]

SCENARIOS = {
    "shipped-unsynchronized": "the board as shipped: no wall clock, so expiry is unverifiable",
    "synchronized-accepted": "harness-injected synchronized clock and resolved limits",
    "synchronized-expired": "harness-injected clock past the command's expiry",
    "wrong-device": "command addressed to another device id",
    "duplicate-replay": "the same command_id submitted twice",
}


def run_harness() -> str:
    from test_cg_tec_state_machine import find_gcc, find_vcvars
    from test_cg_w05_harness import build_with_gcc, build_with_msvc

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="cg-w06-artifacts-"))
    vcvars = find_vcvars()
    if vcvars is not None:
        exe = build_with_msvc(vcvars, workdir, HARNESS, SOURCES, "cg_w06_harness.exe")
    else:
        cc = find_gcc()
        if cc is None:
            raise RuntimeError(
                "no host C compiler found; W06 artifacts must come from the real validator and "
                "formatter, so they are not hand-written here"
            )
        exe = build_with_gcc(cc, workdir, HARNESS, SOURCES, "cg_w06_harness")
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"harness failed:\n{result.stdout}\n{result.stderr}")
    if "ALL SCENARIOS PASS" not in result.stdout:
        raise RuntimeError("harness did not report a full pass before emitting artifacts")
    return result.stdout


def parse_kv(text: str, skip: int = 2) -> dict[str, str]:
    """`skip` exists because the "#CG CMDACK" line carries two non-keyword tokens
    before its fields, while a scenario event line is all key=value."""
    out: dict[str, str] = {}
    for token in text.split(" ")[skip:]:
        if "=" in token:
            key, value = token.split("=", 1)
            out[key] = value
    return out


def build_artifacts() -> dict[str, str]:
    output = run_harness()
    provenance = {
        "generated_by": "evidence/A/W06/build_contract_artifacts.py",
        "produced_by": "firmware/main/cg_command.c + cg_telemetry.c through "
                       "firmware/tools/tests/cg_w06_harness.c",
        "is_host_scenario": True,
        "is_physical_measurement": False,
        "warning": (
            "Synthetic commands against an injected validation context. Not a bench capture, "
            "not a backend round trip, and not evidence that any branch was ever energized."
        ),
    }

    fixtures: dict[str, object] = {}
    logs: dict[str, list[dict[str, str]]] = {
        "duplicate": [], "expired": [], "reset": []
    }
    current = None

    for line in output.splitlines():
        if line.startswith("FIXTURE_ACK "):
            remainder = line[len("FIXTURE_ACK "):]
            label_token, _, body = remainder.partition(" ")
            if not label_token.startswith("scenario="):
                raise RuntimeError(f"fixture line without a scenario label: {line[:60]!r}")
            label = label_token[len("scenario="):]
            if label not in SCENARIOS:
                raise RuntimeError(f"unexpected fixture scenario {label!r}")
            fields = parse_kv(body)
            if fields.get("applied_cooling") == "ON":
                raise RuntimeError(
                    f"{label}: the harness reported applied cooling ON; this slice must not be "
                    "able to produce that state"
                )
            fixtures[label] = {
                "description": SCENARIOS[label],
                "raw_line": body,
                "fields": fields,
            }
        elif line.startswith("SCENARIO_BEGIN "):
            current = line[len("SCENARIO_BEGIN "):].strip()
            if current not in logs:
                raise RuntimeError(f"unknown scenario {current!r}")
        elif line.startswith("SCENARIO_EVENT "):
            if current is None:
                raise RuntimeError("scenario event outside a scenario")
            logs[current].append(parse_kv(line[len("SCENARIO_EVENT "):], skip=0))
        elif line.startswith("SCENARIO_END "):
            current = None

    if len(fixtures) != len(SCENARIOS):
        raise RuntimeError(f"expected {len(SCENARIOS)} fixture ACKs, got {len(fixtures)}")
    for name, entries in logs.items():
        if not entries:
            raise RuntimeError(f"scenario log {name!r} is empty")

    artifacts: dict[str, str] = {
        "ack-fixture.json": json.dumps(
            {"provenance": provenance, "fixtures": fixtures}, indent=2, sort_keys=True) + "\n"
    }
    for name, entries in logs.items():
        rows = [json.dumps({"provenance": provenance, **entry}, sort_keys=True)
                for entry in entries]
        artifacts[f"{name}-command-log.jsonl"] = "\n".join(rows) + "\n"

    # A-W06-05, two views of the same rule set. The demo capture is the emitted
    # ACK lines plus the W05 fixture telemetry line, so the trace tool is
    # exercised on real formatter bytes; the committed capture is a W04 log in
    # which no command line exists at all. Both reports are generated, and the
    # honest one is the second: an empty trace is the correct answer for a
    # firmware that has no transport and has never been actuated.
    schema_fixture = EVIDENCE.parent / "W05" / "schema-fixture.json"
    if schema_fixture.is_file():
        telem_line = json.loads(schema_fixture.read_text(encoding="utf-8"))["raw_line"]
        lines = [fixtures[label]["raw_line"] for label in SCENARIOS] + [telem_line]
        artifacts["demo-command-capture.log"] = (
            "# Host-generated demonstration capture for cg_command_trace.py.\n"
            "# Every line below was emitted by the delivered firmware sources through\n"
            "# firmware/tools/tests/cg_w06_harness.c and the W05 harness. This is NOT a\n"
            "# bench capture, and no line here records a physical actuation.\n"
            + "\n".join(lines) + "\n"
        )
        artifacts.update(build_trace_artifacts(artifacts["demo-command-capture.log"]))
    return artifacts


def build_trace_artifacts(demo_capture_text: str) -> dict[str, str]:
    import cg_command_trace

    with tempfile.TemporaryDirectory(prefix="cg-w06-trace-") as tmp:
        work = pathlib.Path(tmp)
        demo = work / "demo.log"
        demo.write_text(demo_capture_text, encoding="utf-8", newline="\n")
        demo_lines = demo.read_text(encoding="utf-8").splitlines()
        demo_commands = cg_command_trace.parse_capture(demo_lines)
        demo_rows = cg_command_trace.evaluate(demo_commands)
        out = {
            "trace-host-demo.json": json.dumps(
                {
                    "provenance": {
                        "capture": "evidence/A/W06/demo-command-capture.log",
                        "kind": "host-generated",
                        "is_physical_measurement": False,
                        "note": ("Exercises the promotion rules on emitted bytes. It shows what "
                                 "the trace tool refuses to claim, not what a device did."),
                    },
                    "summary": cg_command_trace.summarize(demo_commands, demo_rows),
                    "commands": demo_rows,
                }, indent=2, sort_keys=True) + "\n"
        }

        real = EVIDENCE.parent / "W04" / "g1" / "40-g1-boot-60s.log"
        if real.is_file():
            real_lines = real.read_text(encoding="utf-8", errors="replace").splitlines()
            real_commands = cg_command_trace.parse_capture(real_lines)
            real_rows = cg_command_trace.evaluate(real_commands)
            out["trace-committed-w04-capture.json"] = json.dumps(
                {
                    "provenance": {
                        "capture": "evidence/A/W04/g1/40-g1-boot-60s.log",
                        "kind": "committed device capture",
                        "note": ("A real device capture, taken before W06, so it contains no "
                                 "command lines. The correct trace report for it is empty: no "
                                 "lifecycle stage may be claimed from bytes that never carried "
                                 "a command."),
                    },
                    "summary": cg_command_trace.summarize(real_commands, real_rows),
                    "commands": real_rows,
                }, indent=2, sort_keys=True) + "\n"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="regenerate and compare against the files on disk")
    args = parser.parse_args(argv)

    try:
        artifacts = build_artifacts()
    except (RuntimeError, AssertionError) as exc:
        print(f"ARTIFACT_BUILD_FAILED: {exc}", file=sys.stderr)
        return 1

    if args.check:
        drifted = []
        for name, text in artifacts.items():
            path = EVIDENCE / name
            if not path.is_file():
                drifted.append(f"{name}: missing")
            elif path.open(encoding="utf-8", newline="\n").read() != text:
                drifted.append(f"{name}: differs from a fresh derivation")
        if drifted:
            print("W06 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W06 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
        return 0

    for name, text in artifacts.items():
        (EVIDENCE / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name} ({len(text.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
