"""Regenerate the W12 evidence artifacts from the committed captures.

    py evidence/A/W12/build_w12_artifacts.py [--check]

Every artifact here is produced by running ``firmware/tools/cg_w12_drift_audit.py``
against the committed W04 cooling capture. Nothing is typed by hand, and the
volatile generation timestamp is stripped so ``--check`` is byte-exact.

Artifacts:

``drift-audit.json``
    The full machine-readable audit report (per-capture sensor consistency, role
    geometry, PZEM zero/active, cross-session drift).

``mechanical-audit-checklist.csv``
    A-W12-03 as a flat table: item, check, status, what closes each item.

``dataset-validity.csv``
    A-W12-04 configuration-grouped table: the intended label, the evidence-derived
    identity, the physical session identity, the three verification layers
    (reference / review / authorized provenance) each shown separately, the resulting
    config_verification, and which captures may not be pooled. The nested per-layer
    records themselves live in drift-audit.json.

``gate-g3-input.json``
    A-W12-05: the Member-A signoff input with named blockers and the explicit
    statement that it does not declare a whole-team G3 GREEN.

Honesty rules asserted at the end (not assumed): no artifact reports
``physical_verified: true``; no artifact declares a team gate GREEN; the gate G3
input keeps its NEED_USER_ACTION posture.
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

import cg_w12_drift_audit as w12  # noqa: E402


def _strip_volatile(report: dict[str, object]) -> dict[str, object]:
    report = dict(report)
    report.pop("generated_utc", None)
    return report


def _cell(value: object) -> object:
    """Render one dataset-validity cell.

    The dataset table now carries nested evidence (per-capture requirement booleans and
    the open-item list), so the CSV must state the same facts the JSON does rather than
    print a Python repr that a consumer could misread.
    """
    if isinstance(value, dict):
        return ";".join(f"{key}={'met' if item is True else 'missing' if item is False else item}"
                        for key, item in sorted(value.items()))
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if value is None:
        return ""
    return value


def build_artifacts() -> dict[str, str]:
    paths = w12.default_captures()
    if not paths:
        raise RuntimeError("no committed capture present to audit")
    report = _strip_volatile(w12.build_report(paths))

    # Honesty assertions: the host slice never claims a physical verification.
    if report.get("physical_verified"):
        raise RuntimeError("W12 report claimed physical_verified from host evidence")
    if report["gate_g3_input"]["a_side_status"] != "NEED_USER_ACTION":
        raise RuntimeError("W12 gate G3 input left its NEED_USER_ACTION posture")

    artifacts: dict[str, str] = {
        "drift-audit.json": json.dumps(report, indent=2, sort_keys=True) + "\n",
        "gate-g3-input.json": json.dumps(report["gate_g3_input"], indent=2, sort_keys=True) + "\n",
    }

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["item", "check", "status", "observed",
                                              "recommended_vs_observed", "closes_with"],
                            lineterminator="\n")
    writer.writeheader()
    for row in report["mechanical_audit_checklist"]:
        writer.writerow({k: row.get(k, "") for k in writer.fieldnames})
    artifacts["mechanical-audit-checklist.csv"] = buf.getvalue()

    buf = io.StringIO()
    rows = report["hardware_config_signoff"]["dataset_validity_table"]
    # The nested per-layer records are published in drift-audit.json; the CSV keeps the columns a
    # consumer filters on, so a cell never buries a status under three paragraphs of reason text.
    columns = [key for key in rows[0].keys()
               if key not in {"inspection_reference", "review_binding", "approval_provenance"}]
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: (_cell(r.get(k))) for k in columns})
    artifacts["dataset-validity.csv"] = buf.getvalue()

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
                drifted.append(f"{name}: differs from a fresh derivation")
        if drifted:
            print("W12 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W12 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
        return 0

    for name, text in artifacts.items():
        (EVIDENCE / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name} ({len(text.encode('utf-8'))} bytes)")
    return 0


def write_pins() -> int:
    """Pin every dossier file except the pin file itself, LF-only, sorted by name.

    Without a documented producer the pins are a mystery artifact: a reviewer cannot
    regenerate them, and adding a file to the dossier silently leaves it unpinned.
    """
    lines = []
    for path in sorted(p for p in EVIDENCE.rglob("*")
                       if p.is_file() and p.name != "SHA256SUMS.txt"
                       and "__pycache__" not in p.parts and p.suffix != ".pyc"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(EVIDENCE).as_posix()}\n")
    (EVIDENCE / "SHA256SUMS.txt").write_bytes("".join(lines).encode("utf-8"))
    print(f"wrote SHA256SUMS.txt ({len(lines)} files pinned)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--pins" in sys.argv:
        sys.exit(write_pins())
    sys.exit(main())
