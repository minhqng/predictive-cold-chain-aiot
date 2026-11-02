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
PROBE_CHANNELS = ("t1", "t2", "t3", "t4")
HANDS_OFF_WINDOWS = ("live_check", "baseline", "decay_check")


def require(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def _expected_pinned_names() -> set[str]:
    """Every dossier file is pinned except the pin file itself and Python caches."""
    return {path.relative_to(DOSSIER).as_posix() for path in DOSSIER.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS.txt"
            and "__pycache__" not in path.parts and path.suffix != ".pyc"}


def check_pins() -> None:
    sums = DOSSIER / "SHA256SUMS.txt"
    if not sums.is_file():
        FAILURES.append("SHA256SUMS.txt is missing")
        return
    pinned: set[str] = set()
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            FAILURES.append(f"unparsable pin line: {line[:80]!r}")
            continue
        want, name = parts
        pinned.add(name)
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
    expected = _expected_pinned_names()
    for unpinned in sorted(expected - pinned):
        FAILURES.append(f"{unpinned} is in the dossier but not pinned")
    for stale in sorted(pinned - expected):
        FAILURES.append(f"{stale} is pinned but should not be (cache or deleted file)")


# Durable: these hold however the physical study develops.
ALWAYS_REQUIRED = ("tmean_airroles_v0", "tmean_chamber3_v0", "includes_hot_side",
                   "whole_phase_least_squares_v0", "NO_SAMPLES", "sample (n-1)",
                   "undetermined rows")


def _registry_entries(name: str) -> list[dict[str, object]]:
    path = DOSSIER / name
    if not path.is_file():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _distinct_cooling_boots() -> int:
    return len({str(entry["provenance"]["boot_id"])
                for entry in _registry_entries("cooling-step-runs.jsonl")})


def check_report() -> str:
    """The report must keep saying what it means, at the strength the data supports.

    Two classes of token, deliberately separated. `ALWAYS_REQUIRED` is durable.
    `INSUFFICIENT_RUNS`, `NOT ESTABLISHED` and the single-run figures are a PHASE
    SNAPSHOT - MUST EVOLVE: they are only true while A-W07-02/03 have one session, so
    asserting them forever would make this validator fail the moment the physical study
    succeeds, which is the opposite of what an honesty check is for.
    """
    report = (DOSSIER / "repeatability-report.md").read_text(encoding="utf-8")
    for token in ALWAYS_REQUIRED:
        require(token in report or token.lower() in report.lower(),
                f"repeatability-report.md lost {token!r}")
    if _distinct_cooling_boots() <= 1:
        for token in ("NOT ESTABLISHED", "INSUFFICIENT_RUNS", "-8.7083", "-2.5627", "3.40"):
            require(token in report or token.lower() in report.lower(),
                    f"with one cooling session the report must still say {token!r}")
    else:
        require("INSUFFICIENT_RUNS" not in report,
                "the report still calls the runs insufficient with multiple sessions filed")
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


TOUCH_WINDOWS = ("touch_1.log", "settle_1.log", "touch_2.log")


def check_identification() -> None:
    """Re-count the captures. Matching a number in a sentence proves only the sentence.

    The record's counts used to be checked with `"233" in record`, which stayed green
    after three frames were deleted from a capture - the validator confirmed the prose
    while the prose had become false. Every figure below is recomputed from the bytes.
    """
    record = (DOSSIER / "probe-identification-v0.md").read_text(encoding="utf-8")
    require("PROBE_IDENTIFICATION" in record,
            "the identification record must carry its own label")
    frames = {path.name: _lines(path)
              for path in sorted((DOSSIER / "probe-identification").iterdir())}
    require(len(frames) == 6, f"expected 6 identification captures, found {sorted(frames)}")
    total = sum(len(rows) for rows in frames.values())
    touched = sum(len(frames.get(name, [])) for name in TOUCH_WINDOWS)
    require(str(total) in record, f"the record must state the recomputed total {total}")
    require(str(touched) in record,
            f"the record must state the recomputed touch-window count {touched}")
    for name, rows in frames.items():
        window = name.removesuffix(".log")
        require(f"`{window}`" in record, f"the record has no row for {window}")
        require(str(len(rows)) in record,
                f"the record does not state {window}'s recomputed {len(rows)} frames")
        off = [row.get("device_ms") for row in rows if row.get("state") != "OFF"]
        require(not off,
                f"{window} carries state != OFF at device_ms {off[:3]}")
        driven = [row.get("device_ms") for row in rows
                  if (rep.number(row, "pwm_applied_permille") or 0.0) != 0.0]
        require(not driven,
                f"a PROBE_IDENTIFICATION capture shows non-zero applied duty at "
                f"{driven[:3]}")
    boots: dict[str, str] = {}
    for name, rows in frames.items():
        ids = {row.get("boot_id") for row in rows if row.get("boot_id")}
        require(len(ids) == 1, f"{name} spans {sorted(ids)} boot_ids, expected one per window")
        if len(ids) == 1:
            boots[name] = ids.pop()
    for name, boot in sorted(boots.items()):
        window = name.removesuffix(".log")
        row_line = next((line for line in record.splitlines()
                         if line.startswith(f"| `{window}`")), "")
        require(boot in row_line,
                f"the record's `{window}` row must carry its own boot_id {boot}; a global "
                f"list lets a window be mis-paired and still pass")
    measured = set(boots.values())
    listed = set(re.findall(r"\b[0-9a-f]{8}\b", record))
    require(measured == listed,
            f"boot ids in the captures {sorted(measured)} and boot ids in the record "
            f"{sorted(listed)} are not the same set")


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
        entries = _registry_entries(name)
        require(all(entry["phase"] == phase for entry in entries),
                f"{name} holds phases other than {phase}")
        require(all(entry["independent_session"] is False for entry in entries),
                f"{name} registers a segment as an independent run")
        require(all(entry["provenance"]["boot_id"] for entry in entries),
                f"{name} has an entry without the capture it came from")
        # The durable property is the bookkeeping, not today's defect: unqualified
        # readings must be flagged as unqualified, and a qualified capture must not be
        # forced to look unqualified to keep this validator green.
        for entry in entries:
            # electrical_rows_unqualified sums four columns, so its ceiling is four
            # times the rows read, not the rows themselves.
            require(0 <= entry["electrical_rows_unqualified"] <= 4 * entry["rows_read"],
                    f"{name}: unqualified electrical count outside its own bounds")
            require(entry["electrical_status_recorded"] is
                    (entry["electrical_rows_unqualified"] == 0),
                    f"{name}: electrical_status_recorded contradicts its own counts")
            require(entry["current_rows_unqualified"]
                    + entry["voltage_rows_unqualified"]
                    + entry["power_rows_unqualified"]
                    + entry["energy_rows_unqualified"]
                    == entry["electrical_rows_unqualified"],
                    f"{name}: per-column unqualified counts do not sum to the total")
            if entry["electrical_rows_unqualified"]:
                require("unqualified" in str(entry.get("electrical_status_note", "")),
                        f"{name}: unqualified electrical values carry no warning")
    boots = _distinct_cooling_boots()
    require(boots >= 1, "no cooling step is registered at all")
    if boots <= 1:
        require(len(_registry_entries("cooling-step-runs.jsonl")) == boots,
                "segments of one boot are filed as separate cooling runs")


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
    # Status alone is not a requirement: a FROZEN gate whose value names no condition
    # (`door_required: OPEN`, `cooling_state_required_known: false`) passes nothing, and
    # the evaluator must not be the only place that notices.
    state_values = {entry["name"]: entry["value"] for entry in criteria["parameters"]}
    for name, wanted in (("door_required", "CLOSED"),
                         ("cooling_state_required_known", "true"),
                         ("sensor_quality_required", "VALID")):
        require(state_values.get(name, "").strip().lower() == wanted.lower(),
                f"{name} must require {wanted!r}, the file says {state_values.get(name)!r}")

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
    suspect = evaluation["suspect_frame"]
    capture = rep.capture_path("evidence/A/W04/tec-cooling-response-600s.csv")
    zero_duty_current = sorted({str(row.get("device_ms")) for row in rep.read_rows(capture)
                                if rep.number(row, "pwm_applied_permille") == 0.0
                                and (rep.number(row, "current_a") or 0.0) > 0.0})
    if suspect is None:
        require(not zero_duty_current,
                f"the capture carries applied-duty-0 frames with current "
                f"{zero_duty_current[:3]} but the report quotes none")
    else:
        require(str(suspect["device_ms"]) in zero_duty_current,
                f"the quoted suspect frame {suspect['device_ms']} is not a duty-0 "
                f"with-current frame in the capture")
        fields = suspect["fields"]
        require(fields["pwm_applied_permille"] == "0"
                and fields["current_a"] == "7.15"
                and fields["current_status"] == "",
                "the suspect frame must be quoted as recorded: duty 0, current 7.15, "
                "empty status")
        require(suspect["differing_measured_fields"] == [],
                f"the report claims the frame repeats its preceding measurements, which "
                f"disagree on {suspect['differing_measured_fields']}")
        require(suspect["preceding_frames_identical_on_all_measured_fields"] == 2,
                "both preceding frames must actually match the quoted frame")
        require("CONTROL_ELECTRICAL_ANOMALY" in suspect["canonical_candidate"],
                "a commanded-OFF-with-current frame is a canonical safety candidate and "
                "must not be filed away as a sensor quirk")


def check_overlay() -> None:
    overlay = (DOSSIER / "repeatability-overlay.csv").read_text(encoding="utf-8")
    header = overlay.splitlines()[0]
    for column in ("phase_elapsed_min", "boot_elapsed_min", "representation",
                   "includes_hot_side"):
        require(column in header, f"overlay lost the {column!r} column")
    rows = [line.split(",") for line in overlay.splitlines()[1:]]
    representations = {row[2] for row in rows}
    analysed = {path.stem.removeprefix("repeatability-")
                for path in DOSSIER.glob("repeatability-tmean_*.json")}
    require(representations == analysed,
            f"the overlay carries {sorted(representations)} but the dossier analysed "
            f"{sorted(analysed)}: the README's claim that every analysed definition is "
            f"overlaid has to be true, not approximately true")
    for row in rows:
        require(row[3] == ("1" if rep.includes_hot_side(row[2]) else "0"),
                f"overlay row flags hot side {row[3]} for {row[2]}, which says otherwise")


def check_provenance_paths() -> None:
    """No committed artifact may name a capture by a developer's absolute path.

    These files are hash-pinned: an absolute path makes one real capture hash
    differently on every machine, which turns 'reproduces byte-for-byte' into a
    claim only the author's laptop can test.
    """
    offenders = re.compile(r"[A-Za-z]:[\\/]|/home/|/Users/")
    for path in sorted(DOSSIER.rglob("*")):
        if not path.is_file() or path.suffix not in GENERATED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [line.strip()[:100] for line in text.splitlines() if offenders.search(line)]
        for hit in hits:
            FAILURES.append(f"{path.name} embeds an absolute capture path: {hit!r}")


def check_handwritten_claims() -> None:
    """The prose a person wrote must not drift from the artifact the tool produced.

    Two failures this guards against, both real in this dossier's history: a hardcoded
    sentence asserting the trailing cooling slope was positive while the generated table
    three lines away said -0.070104, and a forbidden claim appearing only in the
    hand-written summary rather than the report the FORBIDDEN scan used to read.
    """
    criteria = criterion.load_criteria(DOSSIER / "reset-criterion-v0.yaml")
    primary = criterion.parameter(criteria, "tmean_definition")[0]
    cooling = json.loads((DOSSIER / f"repeatability-{primary}.json")
                         .read_text(encoding="utf-8"))["runs"][0]["phases"]["cooling"]
    quoted = (str(cooling["slope_c_per_min"]), str(cooling["whole_phase_slope_c_per_min"]))
    for name in ("README.md", "acceptance.md"):
        text = (DOSSIER / name).read_text(encoding="utf-8")
        for token in FORBIDDEN:
            require(token not in text.lower(), f"{name} claims {token!r}")
        for value in quoted:
            require(value in text,
                    f"{name} must quote the generated slope {value}; it currently carries "
                    f"a number the tools did not produce")

    probe_record = (DOSSIER / "probe-identification-v0.md").read_text(encoding="utf-8")
    captures = sorted((DOSSIER / "probe-identification").iterdir())
    per_window = {path.name.removesuffix(".log"): {channel: _spread(path, channel)
                                                   for channel in PROBE_CHANNELS}
                  for path in captures}
    t2_max = max(scores["t2"] for scores in per_window.values())
    hands_off_max = max(max(scores.values()) for window, scores in per_window.items()
                        if window in HANDS_OFF_WINDOWS)
    require(f"{t2_max:.3f}" in probe_record,
            f"the record must state the recomputed hot-side spread {t2_max:.3f} C")
    require(f"{hands_off_max:.3f}" in probe_record,
            f"the record must state the recomputed worst hands-off spread "
            f"{hands_off_max:.3f} C, not a smaller number it did not measure")
    for window, scores in sorted(per_window.items()):
        worst = max(scores.values())
        require(f"{worst:.3f}" in probe_record,
                f"the record must state {window}'s recomputed max spread {worst:.3f} C")


def _spread(path: pathlib.Path, channel: str) -> float:
    """Within-window spread of one probe channel in a serial identification capture.

    Serial frames name the probe `t2`; the CSV names the same column `t2_c`. The record
    used to claim every channel stayed within 0.063 C while hands were off, which its own
    `decay_check` data contradicts, so each figure is recomputed per channel here.
    """
    values = [float(row[channel]) for row in _lines(path) if row.get(channel)]
    return 0.0 if len(values) < 2 else max(values) - min(values)


CHECKS = (check_pins, check_report, check_geometry, check_identification,
          check_registries, check_criterion, check_overlay,
          check_handwritten_claims, check_provenance_paths)


def main() -> int:
    for check in CHECKS:
        try:
            check()
        except Exception as error:
            # A deleted file or a renamed field used to abort the whole run with a
            # traceback, so the gate reported fewer failures than it had found and an
            # earlier check's verdict could be the last thing printed. Record it and go on.
            FAILURES.append(f"{check.__name__} raised {type(error).__name__}: {error}")

    if FAILURES:
        print("W07 DOSSIER: FAIL")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("W07 DOSSIER: OK (pins verify, verdicts still honest, one run still one run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
