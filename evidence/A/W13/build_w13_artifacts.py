"""Regenerate the W13 evidence artifacts from the committed captures.

    py evidence/A/W13/build_w13_artifacts.py [--check]

Every artifact is produced by running ``firmware/tools/cg_w13_timing.py`` on the
committed H6 console trace and the committed W04 cooling capture; nothing is
typed by hand and the volatile timestamp is stripped so ``--check`` is byte-exact.

Artifacts (docs/05A section 22 deliverables):

``plant-timing-report.json``  the full timing report (A-W13-01/02/03/04).
``response-delay.csv``        per-run command->electrical + command->thermal delays.
``door-critical.csv``         A-W13-03, honestly a NOT_COMPUTABLE row, never a number.
``data-gap-register.csv``     the named gaps that block any timing claim.

Honesty asserted at the end: no door->critical number appears anywhere, and the
report never marks a physical verification.
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

import cg_w13_timing as w13  # noqa: E402


def build_artifacts() -> dict[str, str]:
    traces, cooling = w13.default_paths()
    if not traces:
        raise RuntimeError("no committed console trace present")
    report = dict(w13.build_report(traces, cooling))
    report.pop("generated_utc", None)

    d2c = report["door_to_critical"]
    if d2c.get("number_emitted") or d2c.get("value_s") is not None:
        raise RuntimeError("door->critical produced a number without data")
    if report.get("physical_verified"):
        raise RuntimeError("W13 report claimed physical_verified from host evidence")

    artifacts: dict[str, str] = {
        "plant-timing-report.json": json.dumps(report, indent=2, sort_keys=True) + "\n",
    }

    # response-delay.csv - every row carries the configuration/era tag so it can
    # never be merged across images/boots in breach of the W12 dataset-validity rule.
    trace_tag = "trace-file (no boot_id/image column; boot continuity unverified)"
    cooling_tag = "unknown"
    if cooling and cooling.is_file():
        crows = w13.load_csv(cooling)
        boots = w13._distinct_boot_ids(crows)
        session = (crows[0].get("session") or "") if crows else ""
        img = "image=01cedce3" if "01cedce3" in session else "image=unpinned"
        boot = "boot=" + (boots[0] if len(boots) == 1 else "multi/none")
        cooling_tag = f"{img}|{boot}"

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["capture", "record", "value", "unit", "config_era_tag", "note"])
    for run in report["command_to_electrical"]["per_run"]:
        writer.writerow([run.get("capture"), "command_to_electrical_delay",
                         run.get("delay_s", ""), "s", trace_tag, run.get("status", "")])
    ctt = report.get("command_to_thermal", {})
    writer.writerow(["(cooling capture)", "command_to_thermal_delay_min",
                     ctt.get("delay_min", ""), "min", cooling_tag, ctt.get("status", "")])
    for key, label in (("cooling_tau", "cooling_tau_proxy"), ("recovery_tau", "recovery_tau_proxy")):
        res = report.get(key, {})
        writer.writerow(["(cooling capture)", label, res.get("tau_s", ""), "s",
                         cooling_tag, res.get("status", "")])
    artifacts["response-delay.csv"] = buf.getvalue()

    # door-critical.csv (never a number)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["requirement", "status", "value_s", "number_emitted", "reason"])
    writer.writerow([d2c["requirement"], d2c["status"], "", "false", d2c["reason"]])
    artifacts["door-critical.csv"] = buf.getvalue()

    # data-gap-register.csv
    buf = io.StringIO()
    rows = report["data_gap_register"]
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    artifacts["data-gap-register.csv"] = buf.getvalue()

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
            elif path.read_text(encoding="utf-8", newline="\n") != text:
                drifted.append(f"{name}: differs")
        if drifted:
            print("W13 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W13 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
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
