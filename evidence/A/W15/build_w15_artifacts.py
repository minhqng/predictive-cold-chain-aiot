"""Regenerate the W15 evidence artifacts from recorded captures.

    py evidence/A/W15/build_w15_artifacts.py            # write the artifacts
    py evidence/A/W15/build_w15_artifacts.py --check     # compare, write nothing

Inputs follow the W08 rule exactly, so a clean checkout reproduces every byte:

* the **committed** captures (the 957-row H8-C CSV, the H6 trace, the two W03 OFF
  envelopes, the production G1 CSV) are re-read from git on every run;
* the **local-bench** sessions (H7 ladder, H8 A-E, the raw 600 s stream) come
  from ``evidence/A/W08/local-bench-observations.json``, the shared declared
  input whose per-file SHA-256 was recorded when it was derived. Their own
  SHA-256 is written into ``w15-input-provenance.json`` so a reviewer can tell
  which half of a number is reproducible here and which half is declared.

Artifacts (all generated, none typed):

``pzem-quality-report.md`` / ``electrical-frame-quality.csv`` / ``pzem-quality.json``
    A-W15-01: missing/invalid responses, cadence and freshness, transport
    classes, ON/OFF separation and the holdover patterns, power consistency.
``A3-run-index.csv``
    A-W15-02: which runs carry command + applied + V/I/P + thermal response.
``a3-feature-provenance.csv``
    A-W15-02: feature -> PZEM register -> validity condition -> whether authentic
    data exists to compute it at all.
``pwm-go-no-go.md`` + ``pwm-*.csv``
    A-W15-04: the METHODOLOGY with every threshold recorded as UNRESOLVED. The
    decision is NOT_DECIDED and the generator refuses to emit GO.
``w15-operator-queue.csv``
    the W15 half of the consolidated operator queue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[2]
TOOLS = REPO / "firmware" / "tools"
sys.path.insert(0, str(TOOLS))

import cg_w08_envelope as envelope          # noqa: E402
import cg_w15_pzem_quality as quality       # noqa: E402
import cg_w15_pwm_gonogo as pwm             # noqa: E402

DECLARATION = REPO / "evidence" / "A" / "W08" / "local-bench-observations.json"

FORBIDDEN_TOKEN = "PHYSICALLY_VERIFIED"
NEGATIONS = ("not", "never", "no ", "without", "refus", "unreach", "forbid",
             "false", "none", "non-", "instead of", "rather than")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merged_audit() -> dict[str, object]:
    """Git-derived audit rows plus the declared local-bench rows."""
    report = quality.audit(REPO, None)
    declaration = json.loads(DECLARATION.read_text(encoding="utf-8"))
    for label, bundle in sorted(declaration["sessions"].items()):
        row = dict(bundle["w15_quality"])
        row["declared_in"] = DECLARATION.name
        row["reproducible_from_git"] = False
        report["sources"].append(row)
    report["sources"].sort(key=lambda row: row["source"])
    report["summary"] = quality.summarize(report["sources"])
    report["declaration_sha256"] = sha256(DECLARATION)
    return report


def merged_run_index() -> list[dict[str, object]]:
    declaration = json.loads(DECLARATION.read_text(encoding="utf-8"))
    rows = quality.a3_run_index(REPO, None, None)
    for label, bundle in sorted(declaration["sessions"].items()):
        row = dict(bundle["w15_a3_run"])
        row["declared_in"] = DECLARATION.name
        rows.append(row)
    rows.sort(key=lambda row: row["session"])
    return rows


def build_artifact_map() -> dict[str, str]:
    report = merged_audit()
    provenance = quality.a3_provenance(report)
    runs = merged_run_index()
    reference = quality.reference_check(report)
    thresholds = pwm.evaluate_thresholds()
    decision = pwm.decide(thresholds)

    payload = {
        "schema": "cg-w15-1",
        "status_label": "REAL_DATA_ANALYZED",
        "provenance": {
            "committed_inputs": [
                "evidence/A/W04/tec-cooling-response-600s.csv",
                "evidence/A/W04/h6/first-tec-trace.csv",
                "evidence/A/W04/g1/42-telemetry.csv",
                "evidence/A/W03/hardware-2026-10-27/raw/test-132b-off-envelope.csv",
                "evidence/A/W03/hardware-2026-10-20/raw/pzem-off.csv",
            ],
            "declared_input": DECLARATION.relative_to(REPO).as_posix(),
            "declared_input_sha256": report["declaration_sha256"],
            "local_bench_reproducible_from_git": False,
            "note": (
                "the local-bench rows in this payload are declared statistics from "
                "Member A's local W04 tree; the originals were read there and never "
                "copied into this repository"
            ),
        },
        "audit": report,
        "a3_provenance": [row.as_row() for row in provenance],
        "a3_run_index": runs,
        "reference_check": reference,
        "pwm_decision": decision,
    }
    artifacts = {
        "pzem-quality.json": json.dumps(payload, indent=2, sort_keys=True) + "\n",
        "w15-input-provenance.json": json.dumps(
            payload["provenance"], indent=2, sort_keys=True) + "\n",
        "pzem-quality-report.md": quality.render_pzem_quality_report(
            report, provenance, reference),
        "electrical-frame-quality.csv": quality.render_quality_csv(report),
        "a3-feature-provenance.csv": quality.render_provenance_csv(provenance),
        "A3-run-index.csv": quality.render_run_index_csv(runs),
        "pwm-go-no-go.md": pwm.render_pwm_md(decision),
        "pwm-criteria.csv": pwm.render_criteria_csv(),
        "pwm-preconditions.csv": pwm.render_preconditions_csv(),
        "pwm-limits-unresolved.csv": pwm.render_limits_csv(),
        "w15-operator-queue.csv": pwm.render_queue_csv(),
    }
    return artifacts


def honesty_check(artifacts: dict[str, str]) -> list[str]:
    failures: list[str] = []
    for name, text in sorted(artifacts.items()):
        if name.endswith(".md"):
            for number, line in enumerate(text.splitlines(), start=1):
                if FORBIDDEN_TOKEN in line and not any(
                        n in line.lower() for n in NEGATIONS):
                    failures.append(f"{name}:{number} asserts {FORBIDDEN_TOKEN}: "
                                    f"{line.strip()[:120]}")
        else:
            if FORBIDDEN_TOKEN in text:
                failures.append(f"{name}: carries the {FORBIDDEN_TOKEN} token")
    go = artifacts["pwm-go-no-go.md"]
    if "decision: **NOT_DECIDED**" not in go and "decision**: **NOT_DECIDED**" not in go:
        failures.append("pwm-go-no-go.md no longer reports NOT_DECIDED")
    if "UNRESOLVED" not in artifacts["pwm-limits-unresolved.csv"]:
        failures.append("pwm-limits-unresolved.csv lost an UNRESOLVED entry")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not DECLARATION.is_file():
        print(f"ARTIFACT_BUILD_FAILED: {DECLARATION} is missing; run "
              "evidence/A/W08/build_w08_artifacts.py --write-declaration first")
        return 1

    artifacts = build_artifact_map()
    failures = honesty_check(artifacts)
    if failures:
        print("ARTIFACT_BUILD_FAILED: a W15 artifact asserts something it cannot")
        for line in failures:
            print(f"  - {line}")
        return 1

    if args.check:
        drifted = []
        for name, text in sorted(artifacts.items()):
            path = EVIDENCE / name
            if not path.is_file():
                drifted.append(f"{name}: missing")
            elif path.read_text(encoding="utf-8", newline="\n") != text:
                drifted.append(f"{name}: differs from a fresh derivation")
        if drifted:
            print("W15 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W15 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
        return 0

    for name, text in sorted(artifacts.items()):
        (EVIDENCE / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name} ({len(text.encode('utf-8'))} bytes)")
    print("Reminder: the PWM decision stays NOT_DECIDED; this dossier measures "
          "nothing and certifies no calibration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
