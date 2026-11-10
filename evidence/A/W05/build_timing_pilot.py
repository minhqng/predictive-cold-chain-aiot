"""Regenerate the W05 evidence artifacts from committed inputs.

    py evidence/A/W05/build_timing_pilot.py [--check]

Two artifacts, both derived - never hand-written:

``timing-pilot.json`` / ``timing-pilot-jitter.csv``
    The A-W05-03 measurement, produced by ``firmware/tools/cg_timing_analysis.py``
    over ``evidence/A/W04/g1/40-g1-boot-60s.log`` - a capture that is already
    committed, hash-pinned in ``evidence/A/W04/SHA256SUMS.txt``, and contains 62
    real ``#CG TELEM`` frames spanning ~61 s of device uptime.

    This is a **pilot**, not the 30-minute W05 timing study. It is a W04 firmware
    stream, so it carries no ``seq``, no per-producer sequence and no quality
    vocabulary; the analyzer reports those as absent rather than as passing. The
    30-minute capture on the W05 image is listed in ``acceptance.md`` as
    NEED_USER_ACTION, because taking it requires an authorized flash and an
    energization-supervised bench session.

``schema-fixture.json``
    One telemetry frame rendered by the **real** C formatter
    (``firmware/main/cg_telemetry.c`` via ``firmware/tools/tests/cg_w05_harness.c``)
    and parsed back by ``firmware/tools/cg_telemetry_schema.py``. The fixture is
    therefore the firmware's own bytes, not an example typed to match a document.

``--check`` re-derives everything and compares to what is on disk, so a drifted
artifact is a failure rather than a silent difference.

Nothing here touches hardware.
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
MAIN = REPO / "firmware" / "main"
TESTS = TOOLS / "tests"

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TESTS))

import cg_timing_analysis as timing  # noqa: E402

SOURCE_CAPTURE = EVIDENCE.parent / "W04" / "g1" / "40-g1-boot-60s.log"
HARNESS = TESTS / "cg_w05_harness.c"
HARNESS_SOURCES = [
    MAIN / "cg_quality.c",
    MAIN / "cg_health.c",
    MAIN / "cg_snapshot.c",
    MAIN / "cg_telemetry.c",
    MAIN / "cg_tec_control.c",
    MAIN / "cg_tec_limits.c",
]

# The pilot is a W04 stream; the target cadence is the W05/W04 configuration
# value, and the tolerance is the analyzer default. Both are recorded in the
# artifact so a reader can re-run with different bounds and see the difference.
TARGET_PERIOD_MS = 1000
TOLERANCE_MS = 150


def _write_text(path: pathlib.Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def build_timing_files() -> dict[str, str]:
    """Return {filename: text} for the timing pilot artifacts."""
    report = timing.analyse(SOURCE_CAPTURE, TARGET_PERIOD_MS, TOLERANCE_MS)
    rows = report.pop("jitter_rows")

    header = ",".join(str(key) for key in rows[0].keys())
    lines = [header]
    for row in rows:
        lines.append(",".join("" if row[key] == "" else str(row[key]) for key in row))
    csv_text = "\n".join(lines) + "\n"

    provenance = {
        "artifact": "A-W05-03 telemetry cadence pilot",
        "generated_by": "evidence/A/W05/build_timing_pilot.py",
        "source_capture": str(SOURCE_CAPTURE.relative_to(REPO)).replace("\\", "/"),
        "capture_schema": 1,
        "capture_firmware_version": "cg-w04-0.1.0",
        "capture_note": (
            "A W04 bench capture already committed and hash-pinned in "
            "evidence/A/W04/SHA256SUMS.txt. It is NOT the W05 30-minute study, it is NOT "
            "a closed-loop H8 run, and it carries no seq, producer sequence or quality "
            "vocabulary because schema 1 did not define them."
        ),
        "target_period_ms": TARGET_PERIOD_MS,
        "tolerance_ms": TOLERANCE_MS,
    }
    json_text = json.dumps({"provenance": provenance, "report": report},
                           indent=2, sort_keys=True) + "\n"
    return {"timing-pilot.json": json_text, "timing-pilot-jitter.csv": csv_text}


def _find_vcvars() -> pathlib.Path | None:
    from test_cg_tec_state_machine import find_vcvars  # noqa: E402

    return find_vcvars()


def _build(exe: pathlib.Path, workdir: pathlib.Path) -> str:
    vcvars = _find_vcvars()
    if vcvars is not None:
        from test_cg_w05_harness import build_with_msvc  # noqa: E402

        build_with_msvc(vcvars, workdir)
        return "MSVC"
    from test_cg_tec_state_machine import find_gcc  # noqa: E402
    from test_cg_w05_harness import build_with_gcc  # noqa: E402

    cc = find_gcc()
    if cc is None:
        raise RuntimeError(
            "no host C compiler found; schema-fixture.json must be produced by the real "
            "formatter, so it is not regenerated here"
        )
    build_with_gcc(cc, workdir)
    return cc


def build_fixture_file() -> dict[str, str]:
    """Render one frame with the real firmware formatter and describe it."""
    import cg_telemetry_schema as schema  # noqa: E402

    with tempfile.TemporaryDirectory(prefix="cg-w05-fixture-") as tmp:
        workdir = pathlib.Path(tmp)
        compiler = _build(workdir / "cg_w05_harness", workdir)
        exe = workdir / "cg_w05_harness.exe"
        if not exe.exists():
            exe = workdir / "cg_w05_harness"
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)

    line = next((ln[len("FIXTURE_V2 "):] for ln in result.stdout.splitlines()
                if ln.startswith("FIXTURE_V2 ")), None)
    if line is None:
        raise RuntimeError(f"the harness printed no FIXTURE_V2 line:\n{result.stdout}")

    record = schema.parse_line(line)
    payload = {
        "artifact": (f"A-W05 telemetry fixture, schema {record.value('schema')}, "
                     "re-derived from the current emitter"),
        "generated_by": "evidence/A/W05/build_timing_pilot.py",
        "rendered_by": "firmware/main/cg_telemetry.c via firmware/tools/tests/cg_w05_harness.c",
        "compiler": compiler,
        "is_synthetic_frame": True,
        "is_physical_measurement": False,
        "note": (
            "These bytes came out of the delivered formatter for a synthetic fixture state. "
            "They are the wire contract and the parser test input; they are NOT an observation "
            "of the ColdGuard chamber and must not be used as training or acceptance data."
        ),
        "schema_version": record.value("schema"),
        "line_length_bytes": len(line.encode("utf-8")),
        "line_budget_bytes": int(
            (MAIN / "coldguard_config.h").read_text(encoding="utf-8").split(
                "#define CG_TELEMETRY_LINE_MAX "
            )[1].split("\n")[0]
        ),
        "raw_line": line,
        "fields": {key: record.raw_fields[key] for key in sorted(record.raw_fields)},
        "typed_fields": {key: record.fields[key] for key in sorted(record.fields)},
    }
    return {"schema-fixture.json": json.dumps(payload, indent=2, sort_keys=True) + "\n"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="compare regenerated artifacts against the files on disk")
    args = parser.parse_args(argv)

    if not SOURCE_CAPTURE.exists():
        print(f"missing committed source capture: {SOURCE_CAPTURE}", file=sys.stderr)
        return 2

    artifacts = build_timing_files()
    try:
        artifacts.update(build_fixture_file())
    except RuntimeError as exc:
        print(f"fixture: {exc}", file=sys.stderr)
        return 1

    if args.check:
        drifted = []
        for name, text in artifacts.items():
            path = EVIDENCE / name
            if not path.exists():
                drifted.append(f"{name}: missing")
            elif path.open(encoding="utf-8", newline="\n").read() != text:
                drifted.append(f"{name}: content differs from a fresh derivation")
        if drifted:
            print("W05 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W05 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
        return 0

    for name, text in artifacts.items():
        _write_text(EVIDENCE / name, text)
        print(f"wrote {name} ({len(text.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
