"""Regenerate the W16 evidence artifacts by running the framework on real data.

    py evidence/A/W16/build_w16_artifacts.py [--check]

The framework itself is produced by ``firmware/tools/cg_w16_comparability.py`` on
the committed W04/H8-C baseline capture, with the W16-era side deliberately
empty (the W16 re-measurement is a physical action this host slice cannot
perform). ``--check`` compares against the files on disk; the volatile timestamp
is stripped so the comparison is byte-exact.

Artifacts:

``comparability-framework.json``  dimensions, baseline signature, cross-era verdict,
                                  configuration-drift detection, the freeze guard's
                                  own verdict.
``response-tolerance-format.json`` A-W16-03 analysis format (placeholders only).
``final-freeze-evidence-schema.json`` A-W16-04 evidence schema.
``w16-rerun-requirements.csv``       A-W16-01 required re-runs with status.

Honesty asserted at build time (via the tool's ``assert_no_freeze`` and a
re-check here): ``frozen`` is False, no team gate is claimed, and every tolerance
value is NOT_MEASURED. If a future run tried to write a freeze from host evidence
the build would fail, not silently pass.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import pathlib
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[2]
TOOLS = REPO / "firmware" / "tools"
sys.path.insert(0, str(TOOLS))

import cg_w16_comparability as w16  # noqa: E402


def build_artifacts() -> dict[str, str]:
    paths = w16.default_captures()
    if not paths:
        raise RuntimeError("no committed baseline capture present")
    report = dict(w16.build_report(paths))  # build_report already ran assert_no_freeze
    report.pop("generated_utc", None)

    # Re-assert the honesty properties the W16 slice owes (independent of the tool).
    if report["frozen"]:
        raise RuntimeError("W16 report set a physical freeze from host evidence")
    if report["cross_era_comparison"]["comparison_allowed"]:
        raise RuntimeError("W16 allowed a cross-era comparison without a W16 snapshot")
    for field in report["response_tolerance_format"]["fields"].values():
        if field["value"] != "NOT_MEASURED":
            raise RuntimeError("a W16 tolerance was filled from host evidence")

    artifacts: dict[str, str] = {
        "comparability-framework.json": json.dumps(report, indent=2, sort_keys=True) + "\n",
        "response-tolerance-format.json": json.dumps(
            report["response_tolerance_format"], indent=2, sort_keys=True) + "\n",
        "final-freeze-evidence-schema.json": json.dumps(
            report["final_freeze_evidence_schema"], indent=2, sort_keys=True) + "\n",
    }

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["item", "ask", "status", "host_can_compute", "why"])
    for r in report["a_w16_01_rerun_requirements"]:
        writer.writerow([r["item"], r["ask"], r["status"], r["host_can_compute"], r["why"]])
    artifacts["w16-rerun-requirements.csv"] = buf.getvalue()

    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
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
                drifted.append(f"{name}: differs")
        if drifted:
            print("W16 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W16 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
        return 0
    for name, text in artifacts.items():
        (EVIDENCE / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name} ({len(text.encode('utf-8'))} bytes)")
    return 0


def write_pins() -> int:
    """Pin every dossier file except the pin file itself, LF-only, sorted by name.

    Pins nobody can regenerate are not evidence: an undocumented pin step silently
    leaves a new dossier file unpinned, which is how a pinned hash stops meaning anything.
    """
    lines = []
    for path in sorted(p for p in EVIDENCE.rglob("*")
                       if p.is_file() and p.name != "SHA256SUMS.txt"
                       and "__pycache__" not in p.parts and p.suffix != ".pyc"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(EVIDENCE).as_posix()}" + "\n")
    (EVIDENCE / "SHA256SUMS.txt").write_bytes("".join(lines).encode("utf-8"))
    print(f"wrote SHA256SUMS.txt ({len(lines)} files pinned)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--pins" in sys.argv:
        sys.exit(write_pins())
    sys.exit(main())
