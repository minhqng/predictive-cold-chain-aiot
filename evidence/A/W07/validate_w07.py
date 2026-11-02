"""W07 dossier validator: byte pins plus the honesty of every verdict.

A regenerated report can drift into a claim the data does not support, so this
validator checks the words and the numbers, not only the hashes. It fails if W07
evidence calls anything physically verified, calls the geometry complete, lets a
number injected for a test reach the reset criterion as if it were a threshold,
files a recovery rebound as a warm-up run, or averages the suspect zero-duty
current frame into a segment peak without naming it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "firmware" / "tools"))

import cg_reset_criterion as criterion  # noqa: E402
import cg_thermal_repeatability as rep  # noqa: E402

DOSSIER = pathlib.Path(__file__).resolve().parent
FAILURES: list[str] = []

PHASE_OF_FILE = {
    "warmup-runs.jsonl": "baseline",
    "cooling-step-runs.jsonl": "cooling",
    "recovery-runs.jsonl": "recovery",
}
FORBIDDEN = ("physically verified", "repeatability established", "physical pass",
             "bench pass")
# Data artifacts only. `.py` is left out because this file's own absolute-path
# pattern would match itself; a hardcoded path in a generator still surfaces
# here, because the artifact it writes is what gets published.
GENERATED_SUFFIXES = {".md", ".json", ".jsonl", ".yaml", ".csv"}


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
        raw = path.read_bytes()
        if "\r" in raw.decode("utf-8", errors="replace"):
            FAILURES.append(f"{name} carries CR bytes and would break on checkout")
        got = hashlib.sha256(raw).hexdigest()
        if got != want:
            FAILURES.append(f"hash mismatch: {name} (want {want[:12]}\u2026 got "
                            f"{got[:12]}\u2026)")


def check_report() -> str:
    report = (DOSSIER / "repeatability-report.md").read_text(encoding="utf-8")
    for token in ("NOT ESTABLISHED", "INSUFFICIENT_RUNS", "tmean_airroles_v0",
                  "tmean_chamber3_v0", "includes_hot_side", "-8.7083", "-2.5627",
                  "3.40", "whole_phase_least_squares_v0", "NO_SAMPLES",
                  "sample (n-1)", "undetermined rows"):
        require(token in report or token.lower() in report.lower(),
                f"repeatability-report.md lost {token!r}")
    require("empty cell, not OK" in report,
            "the suspect zero-duty current frame must be named, not averaged into a peak")
    for token in FORBIDDEN:
        require(token not in report.lower(), f"report claims {token!r}")
    return report


def check_geometry() -> None:
    geometry = (DOSSIER / "geometry-v1.md").read_text(encoding="utf-8")
    for token in ("CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR",
                  "TEC_HOT_SIDE", "probe-identification-v0.md",
                  "287088CA00000051", "28AEBF2200000006", "28CBE9CA00000072",
                  "283BE5C9000000A9"):
        require(token in geometry, f"geometry-v1.md lost {token!r}")
    require("NOT FROZEN" in geometry,
            "geometry-v1.md must still state what is not frozen")
    require("configuration photo" in geometry or "photo" in geometry.lower(),
            "geometry-v1.md must name the missing photo deliverable")
    require("no freeze" in geometry.lower() or "not frozen by this record" in geometry.lower(),
            "the 1.75 mm2 conductor must not be listed as frozen evidence")


def check_identification() -> None:
    record = (DOSSIER / "probe-identification-v0.md").read_text(encoding="utf-8")
    require("PROBE_IDENTIFICATION" in record,
            "the identification record must carry its own label")
    require("233" in record and "119" in record,
            "the record must carry the measured frame counts, not an approximation")
    for name in ("baseline.log", "touch_1.log", "settle_1.log", "touch_2.log",
                 "live_check.log", "decay_check.log"):
        require((DOSSIER / "probe-identification" / name).is_file(),
                f"identification capture {name} is missing")
    excluded = [str(rep.number(row, "pwm_applied_permille"))
                for name in sorted((DOSSIER / "probe-identification").iterdir())
                for row in _lines(name)
                if rep.number(row, "pwm_applied_permille") not in (None, 0.0)]
    require(not excluded,
            f"a PROBE_IDENTIFICATION capture shows non-zero applied duty: {excluded[:3]}")


def _lines(path: pathlib.Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "#CG H8S" not in line:
            continue
        fields: dict[str, str] = {}
        for token in line.split():
            if "=" in token:
                key, _, value = token.partition("=")
                fields[key] = value
        out.append(fields)
    return out


def check_registries() -> None:
    for name, phase in PHASE_OF_FILE.items():
        path = DOSSIER / name
        if not path.is_file():
            FAILURES.append(f"missing registry {name}")
            continue
        entries = [json.loads(line) for line in
                   path.read_text(encoding="utf-8").splitlines() if line.strip()]
        require(all(entry["phase"] == phase for entry in entries),
                f"{name} holds phases other than {phase}")
        require(all(entry["independent_session"] is False for entry in entries),
                f"{name} registers a segment as an independent run")
        require(all(entry["provenance"]["boot_id"] for entry in entries),
                f"{name} has an entry without the capture it came from")
        require(all(entry["current_rows_unqualified"] == entry["rows_read"]
                    and entry["electrical_status_recorded"] is False
                    for entry in entries),
                f"{name} presents unqualified electrical values as status-checked")
    cooling = [json.loads(line) for line in
               (DOSSIER / "cooling-step-runs.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    require(len(cooling) == 1,
            f"exactly one real cooling run is committed, got {len(cooling)}")


def check_criterion() -> None:
    criteria = criterion.load_criteria(DOSSIER / "reset-criterion-v0.yaml")
    open_numbers = [entry["name"] for entry in criteria["parameters"]
                    if entry["status"] == "UNRESOLVED"]
    require(open_numbers == ["tmean_band_c", "gradient_bound_c_per_min"],
            f"reset criterion must leave exactly the measured gates open, got {open_numbers}")
    definition = criterion.parameter(criteria, "tmean_definition")[0]
    require(definition == "tmean_airroles_v0",
            f"the criterion names {definition!r}, which is not the as-built air mean")
    require(not rep.includes_hot_side(definition),
            f"the criterion's representation {definition!r} averages the hot-side probe")

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
    require(evaluation["hot_side_representation_refused"]["verdict"] == "NOT_READY",
            "a hot-side-contaminated mean must be refused, not judged")
    suspect = evaluation["suspect_frame"]["fields"]
    require(suspect["pwm_applied_permille"] == "0" and suspect["current_a"] == "7.15"
            and suspect["current_status"] == "",
            "the suspect frame must be quoted as recorded: duty 0, current 7.15, empty status")


def check_overlay() -> None:
    overlay = (DOSSIER / "repeatability-overlay.csv").read_text(encoding="utf-8")
    header = overlay.splitlines()[0]
    for column in ("phase_elapsed_min", "boot_elapsed_min", "representation",
                   "includes_hot_side"):
        require(column in header, f"overlay lost the {column!r} column")
    representations = {line.split(",")[2] for line in overlay.splitlines()[1:]}
    require(len(representations) >= 3,
            f"the overlay must carry every analysed definition, got {representations}")


def check_provenance_paths() -> None:
    """No committed artifact may name a capture by a developer's absolute path.

    These files are hash-pinned: an absolute path makes one real capture hash
    differently on every machine, which turns 'reproduces byte-for-byte' into a
    claim only the author's laptop can test.
    """
    offenders = re.compile(r"^\s*[A-Za-z]:[\\/]|C:[\\/]|/home/|/Users/")
    for path in sorted(DOSSIER.rglob("*")):
        if not path.is_file() or path.suffix not in GENERATED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [line.strip()[:100] for line in text.splitlines() if offenders.search(line)]
        for hit in hits:
            FAILURES.append(f"{path.name} embeds an absolute capture path: {hit!r}")


def main() -> int:
    check_pins()
    check_report()
    check_geometry()
    check_identification()
    check_registries()
    check_criterion()
    check_overlay()
    check_provenance_paths()

    if FAILURES:
        print("W07 DOSSIER: FAIL")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("W07 DOSSIER: OK (pins verify, verdicts still honest, one run still one run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
