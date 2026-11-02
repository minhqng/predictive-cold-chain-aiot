"""W07 dossier validator: byte pins plus the honesty of every verdict.

A regenerated report can drift into a claim the data does not support, so this
validator checks the words and the numbers, not only the hashes. It fails if W07
evidence calls anything physically verified, calls the geometry frozen, or lets a
number injected in a test reach the reset criterion as if it were a threshold.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "firmware" / "tools"))

import cg_reset_criterion as criterion  # noqa: E402

DOSSIER = pathlib.Path(__file__).resolve().parent
FAILURES: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def check_pins() -> None:
    sums = DOSSIER / "SHA256SUMS.txt"
    if not sums.is_file():
        FAILURES.append("SHA256SUMS.txt is missing")
        return
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            FAILURES.append(f"unparsable pin line: {line[:80]!r}")
            continue
        want, name = parts
        path = DOSSIER / name
        if not path.is_file():
            FAILURES.append(f"pinned file missing: {name}")
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want:
            FAILURES.append(f"hash mismatch: {name} (want {want[:12]}\u2026 got {got[:12]}\u2026)")


def main() -> int:
    check_pins()

    report = (DOSSIER / "repeatability-report.md").read_text(encoding="utf-8")
    for token in ("NOT ESTABLISHED", "INSUFFICIENT_RUNS", "tmean_chamber3_v0",
                  "tmean_t2excluded_v0", "-2.5627", "-8.6875", "sample"):
        require(token in report, f"repeatability-report.md lost {token!r}")
    for forbidden in ("physically verified", "repeatability established", "physical pass"):
        require(forbidden not in report.lower(),
                f"repeatability-report.md claims {forbidden!r}")

    geometry = (DOSSIER / "geometry-v1.md").read_text(encoding="utf-8")
    require("NOT FROZEN" in geometry, "geometry-v1.md must state what is not frozen")
    require("configuration photo" in geometry,
            "geometry-v1.md must name the missing photo deliverable")

    criteria = criterion.load_criteria(DOSSIER / "reset-criterion-v0.yaml")
    open_numbers = [entry["name"] for entry in criteria["parameters"]
                    if entry["status"] == "UNRESOLVED"]
    require(open_numbers == ["tmean_band_c", "gradient_bound_c_per_min"],
            f"reset criterion must leave exactly the measured gates open, got {open_numbers}")

    evaluation = json.loads((DOSSIER / "reset-criterion-evaluation.json").read_text(
        encoding="utf-8"))
    require(evaluation["shipped_candidate"]["verdict"] == "UNKNOWN",
            "the shipped candidate must answer UNKNOWN while its gates are unresolved")
    require("UNKNOWN is not READY" in evaluation["shipped_candidate"]["why"],
            "the evaluation must say that UNKNOWN is not READY")
    injection = evaluation["with_test_injected_numbers"]
    require("not project thresholds" in injection["note"],
            "injected numbers must be labelled as not thresholds")
    require(injection["result"]["verdict"] == "READY",
            "the injection exists to prove READY is reachable once values are set")

    cooling = [json.loads(line) for line in
               (DOSSIER / "cooling-step-runs.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    warmup = [json.loads(line) for line in
              (DOSSIER / "warmup-runs.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()]
    require(len(cooling) == 1, f"exactly one real cooling run is committed, got {len(cooling)}")
    require(all(entry["independent_session"] is False for entry in cooling + warmup),
            "no segment from the one boot_id may be registered as an independent run")
    require(all("provenance" in entry and entry["provenance"]["boot_id"] for entry in
                cooling + warmup),
            "every registry entry must carry the capture it came from")

    overlay = (DOSSIER / "repeatability-overlay.csv").read_text(encoding="utf-8")
    require(overlay.startswith("run,phase,sample_index,elapsed_min,tmean_c,representation"),
            "the overlay lost its header")
    require("\r" not in overlay, "the overlay must be LF-only or its pin breaks")

    if FAILURES:
        print("W07 DOSSIER: FAIL")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("W07 DOSSIER: OK (pins verify, verdicts still honest, one run still one run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
