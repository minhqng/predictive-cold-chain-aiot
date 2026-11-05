"""Verify the W15 evidence dossier.

    py evidence/A/W15/validate_w15.py

Checks, in order:

1. every file listed in ``SHA256SUMS.txt`` exists, hashes to the pinned value,
   and the sums file is LF-only;
2. no flash image and no local-bench original (``*.jsonl``) was copied into the
   dossier - only declared statistics may be;
3. **no artifact carries a physical claim**: ``PHYSICALLY_VERIFIED`` may appear
   only inside a denial, and no artifact may claim a certified calibration, a
   reference meter, or a PWM **GO**;
4. the honest verdicts are still present - A-W15-04 ``NOT_DECIDED``, every
   decision parameter and every firmware limit still ``UNRESOLVED``, A-W15-03
   reporting plausibility instead of calibration;
5. the quality spine is **re-derived from the committed captures** rather than
   trusted: the 957-frame comparison count, zero frames beyond the V x I
   tolerance, the worst 0.099 W delta, the 14 Wh counter against the 14.219 Wh
   integral, the 7 invalid polls of the W03 capture, the 62 valueless frames of
   the production build, and the 19-of-23 usable-run tally must all still hold in
   the generated artifacts;
6. the shared declaration's SHA-256 recorded in ``w15-input-provenance.json``
   still matches ``evidence/A/W08/local-bench-observations.json`` when it exists
   on disk.

Exit code 0 only when every check passes. Nothing here touches hardware.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import pathlib
import re
import sys

DOSSIER = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DOSSIER.parents[2]
sys.path.insert(0, str(REPO_ROOT / "firmware" / "tools"))

import cg_w08_envelope as envelope  # noqa: E402
import cg_w15_pzem_quality as quality  # noqa: E402

FORBIDDEN = "PHYSICALLY_VERIFIED"
NEGATIONS = ("not", "never", "no ", "without", "refus", "unreach", "forbid",
             "false", "none", "non-", "instead of", "rather than")
DECLARATION = REPO_ROOT / "evidence" / "A" / "W08" / "local-bench-observations.json"

GENERATED = (
    "pzem-quality.json", "w15-input-provenance.json", "pzem-quality-report.md",
    "electrical-frame-quality.csv", "a3-feature-provenance.csv", "A3-run-index.csv",
    "pwm-go-no-go.md", "pwm-criteria.csv", "pwm-preconditions.csv",
    "pwm-limits-unresolved.csv", "w15-operator-queue.csv",
)

HONEST_PHRASES = (
    "A-W15-04 decision: **NOT_DECIDED**",
    "calibration **NOT certified**",
    "no trusted independent meter",
)

SPINE = {
    "committed_frames_compared": 957,
    "mismatch_frames": 0,
    "worst_committed_delta_w": 0.099,
    "counter_delta_wh": 14.0,
    "integral_wh": 14.219,
    "w03_invalid_polls": 7,
    "w03_rows": 601,
    "g1_valueless_frames": 62,
    "io_error_frames_declared": 16,
    "usable_runs": 19,
    "index_rows": 23,
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _expected_pinned_names() -> set[str]:
    """Every dossier file is pinned except the pin file itself and Python caches.

    Pinning both directions is what catches a stray file in either form: an added
    file with no pin, and a pin pointing at a cache or a deleted file.
    """
    return {path.relative_to(DOSSIER).as_posix() for path in DOSSIER.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS.txt"
            and "__pycache__" not in path.parts and path.suffix != ".pyc"}


def check_pins(failures: list[str]) -> set[str]:
    sums_path = DOSSIER / "SHA256SUMS.txt"
    if not sums_path.is_file():
        failures.append("SHA256SUMS.txt is missing")
        return set()
    raw = sums_path.read_bytes()
    if b"\r\n" in raw:
        failures.append("SHA256SUMS.txt is not LF-only")
    pinned = set()
    for line in raw.decode("utf-8").splitlines():
        match = re.match(r"^([0-9a-f]{64})  (.+)$", line.strip())
        if not match:
            if line.strip():
                failures.append(f"unparsable SHA256SUMS line: {line[:80]!r}")
            continue
        digest, rel = match.groups()
        if "__pycache__" in rel or rel.endswith(".pyc"):
            failures.append(f"{rel} is pinned but is a Python cache: only dossier "
                            "artifacts may be hash-pinned")
            continue
        pinned.add(rel)
        target = DOSSIER / rel
        if not target.is_file():
            failures.append(f"missing evidence file: {rel}")
            continue
        actual = sha256(target)
        if actual != digest:
            failures.append(f"hash mismatch: {rel} (want {digest[:12]}… got "
                            f"{actual[:12]}…)")
    for name in GENERATED + ("README.md", "acceptance.md", "build_w15_artifacts.py",
                             "validate_w15.py"):
        if name not in pinned:
            failures.append(f"{name} is not hash-pinned")
    expected = _expected_pinned_names()
    for unpinned in sorted(expected - pinned):
        failures.append(f"{unpinned} is in the dossier but not hash-pinned")
    for stale in sorted(pinned - expected):
        failures.append(f"{stale} is pinned but should not be (cache or deleted file)")
    return pinned


def check_no_physical_claim(failures: list[str]) -> None:
    for path in sorted(DOSSIER.rglob("*")):
        if not path.is_file() or path.suffix not in (".md", ".csv", ".json"):
            continue
        rel = path.relative_to(DOSSIER).as_posix()
        text = read(path)
        if path.suffix != ".md" and FORBIDDEN in text:
            failures.append(f"{rel}: the {FORBIDDEN} token appears outside prose")
        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN in line and not any(n in line.lower() for n in NEGATIONS):
                failures.append(f"{rel}:{number} asserts {FORBIDDEN}: "
                                f"{line.strip()[:120]}")
        for pattern, why in (
            (re.compile(r"calibration certifi", re.I), "a calibration certification"),
            (re.compile(r"decision:\s*\*{0,2}GO\b", re.I), "a PWM GO decision"),
            (re.compile(r"\bcompliant\b", re.I), "a compliance claim"),
            (re.compile(r"reference meter available", re.I), "a reference-meter claim"),
        ):
            for number, line in enumerate(text.splitlines(), start=1):
                match = pattern.search(line)
                if match and not any(n in line.lower() for n in NEGATIONS):
                    failures.append(f"{rel}:{number}: {why} appeared "
                                    f"({match.group(0)!r})")


def check_no_absolute_paths(failures: list[str]) -> None:
    """No pinned artifact may carry a developer absolute locator.

    A drive-qualified or home-directory path makes the artifact readable only on
    the machine that wrote it, so every locator in this dossier is
    repository-relative or ``<local-bench>/``-relative and this check fires the
    moment that rule is broken.
    """
    for path in sorted(DOSSIER.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.name == "SHA256SUMS.txt" or path.suffix == ".pyc":
            continue
        rel = path.relative_to(DOSSIER).as_posix()
        for number, line in enumerate(read(path).splitlines(), start=1):
            hits = envelope.absolute_path_hits(line)
            if hits:
                failures.append(
                    f"{rel}:{number} carries an absolute developer path ({hits[0]!r}); "
                    f"pinned artifacts use repository-relative or "
                    f"{envelope.LOCAL_BENCH_MARKER} locators")


def check_honest_verdicts(failures: list[str]) -> None:
    acceptance = read(DOSSIER / "acceptance.md")
    for phrase in HONEST_PHRASES:
        if phrase not in acceptance:
            failures.append(f"acceptance.md lost {phrase!r}")
    if re.search(r"A-W15-0[1-4]\s*\|[^|]*\|\s*(VERIFIED|PASS|GREEN|DONE)\b", acceptance):
        failures.append("acceptance.md marked a W15 requirement PASS/VERIFIED")

    criteria = list(csv.DictReader(
        (DOSSIER / "pwm-criteria.csv").open(encoding="utf-8", newline="")))
    if len(criteria) != 6:
        failures.append(f"pwm-criteria.csv has {len(criteria)} rows, expected 6")
    if any(row["state"] != "UNRESOLVED" for row in criteria):
        failures.append("a PWM criterion is no longer UNRESOLVED - the method would "
                        "be deciding on an invented threshold")

    limits = list(csv.DictReader(
        (DOSSIER / "pwm-limits-unresolved.csv").open(encoding="utf-8", newline="")))
    if len(limits) != 6 or any(row["state"] != "UNRESOLVED" for row in limits):
        failures.append("the delivered six-limit table is no longer reported fully "
                        "UNRESOLVED")

    preconditions = list(csv.DictReader(
        (DOSSIER / "pwm-preconditions.csv").open(encoding="utf-8", newline="")))
    if len(preconditions) != 9:
        failures.append(f"pwm-preconditions.csv has {len(preconditions)} rows, "
                        "expected 9")
    if not any("FAIL" in row["current_state"] for row in preconditions):
        failures.append("no safety precondition is recorded as failing; on this tree "
                        "several must be")

    go = read(DOSSIER / "pwm-go-no-go.md")
    if "NOT_DECIDED" not in go:
        failures.append("pwm-go-no-go.md no longer reports NOT_DECIDED")

    payload = json.loads(read(DOSSIER / "pzem-quality.json"))
    reference = payload["reference_check"]
    if reference["trusted_independent_meter_available"] is not False:
        failures.append("the dossier claims a trusted independent meter exists")
    if reference["certified_calibration"] is not False:
        failures.append("the dossier claims a certified calibration")
    if payload["pwm_decision"]["decision"] != "NOT_DECIDED":
        failures.append("pzem-quality.json carries a PWM decision this slice cannot make")


def check_spine(failures: list[str]) -> None:
    """Re-derive the committed quality facts; the artifacts must still match."""
    frames = envelope.classify(
        envelope.read_h8_csv(REPO_ROOT / envelope.H8_CSV, "W04-H8C-box-600s"))
    power = envelope.power_consistency(frames)
    energy = envelope.energy_consistency(frames)
    if power["frames_compared"] != SPINE["committed_frames_compared"]:
        failures.append(f"committed frames compared is {power['frames_compared']}")
    if power["frames_beyond_tolerance_count"] != SPINE["mismatch_frames"]:
        failures.append("V x I mismatches appeared in the committed capture")
    if power["max_abs_delta_w"] != SPINE["worst_committed_delta_w"]:
        failures.append(f"worst V x I delta changed to {power['max_abs_delta_w']}")
    if energy["counter_delta_wh"] != SPINE["counter_delta_wh"]:
        failures.append("the energy counter delta changed")
    if energy["trapezoidal_integral_of_power_wh"] != SPINE["integral_wh"]:
        failures.append("the trapezoidal integral of power changed")

    w03 = list(csv.DictReader(
        (REPO_ROOT / envelope.W03_OFF_2026_10_20).open(encoding="utf-8", newline="")))
    invalid = sum(1 for row in w03 if (row.get("quality") or "") == "INVALID")
    if len(w03) != SPINE["w03_rows"] or invalid != SPINE["w03_invalid_polls"]:
        failures.append(f"W03 OFF capture now has {len(w03)} rows and {invalid} "
                        "INVALID polls")

    g1 = envelope.read_g1_csv(REPO_ROOT / envelope.G1_TELEMETRY,
                                      "W04-G1-production-failclosed")
    valueless = sum(1 for f in g1 if f.current_a is None)
    if valueless != SPINE["g1_valueless_frames"] or valueless != len(g1):
        failures.append("the production fail-closed build no longer publishes zero "
                        "electrical values in every frame")

    rows = list(csv.DictReader(
        (DOSSIER / "electrical-frame-quality.csv").open(encoding="utf-8", newline="")))
    if len(rows) != SPINE["index_rows"]:
        failures.append(f"electrical-frame-quality.csv has {len(rows)} rows, expected "
                        f"{SPINE['index_rows']}")
    def io_count(row: dict[str, str]) -> int:
        # A malformed row has to report a failure, not crash the validator: a
        # mutated artifact must produce a verdict, not a traceback.
        raw = (row.get("io_error_frames") or "").strip()
        if not raw.isdigit():
            failures.append(f"electrical-frame-quality.csv row {row.get('source')!r} "
                            f"carries a non-numeric io_error_frames {raw!r}")
            return 0
        return int(raw)

    io_total = sum(io_count(row) for row in rows)
    if io_total != SPINE["io_error_frames_declared"]:
        failures.append(f"IO_ERROR frames total {io_total}, pinned "
                        f"{SPINE['io_error_frames_declared']}")
    unqualified = sorted(row["source"] for row in rows
                         if row["electrical_status_recorded"] == "false")
    if "W04-H8C-box-600s" not in unqualified:
        failures.append("the committed 600 s capture is no longer flagged as "
                        "unqualified electrical data")
    if "W04-H8C-box-600s-raw" in unqualified:
        failures.append("the raw 600 s stream lost its validity tokens - the reader "
                        "regressed")

    index = list(csv.DictReader(
        (DOSSIER / "A3-run-index.csv").open(encoding="utf-8", newline="")))
    usable = [row for row in index if row["usable_for_electrical_ablation"] == "yes"]
    if len(index) != SPINE["index_rows"] or len(usable) != SPINE["usable_runs"]:
        failures.append(f"A3-run-index.csv reports {len(usable)} usable runs of "
                        f"{len(index)}, expected {SPINE['usable_runs']}/{SPINE['index_rows']}")
    committed_usable = [row for row in usable if row["trust"] == "COMMITTED"]
    if [row["session"] for row in committed_usable] != ["W04-H8C-box-600s"]:
        failures.append("the committed-and-usable run set changed: "
                        f"{[row['session'] for row in committed_usable]}")

    provenance = list(csv.DictReader(
        (DOSSIER / "a3-feature-provenance.csv").open(encoding="utf-8", newline="")))
    energy_row = next((row for row in provenance
                       if row["feature"] == "accumulated_energy_wh"), None)
    if energy_row is None or "NONE PUBLISHED" not in energy_row["validity_condition"]:
        failures.append("a3-feature-provenance.csv no longer records that energy has "
                        "no validity token")


def check_declaration_pin(failures: list[str]) -> None:
    payload = json.loads(read(DOSSIER / "w15-input-provenance.json"))
    if payload.get("local_bench_reproducible_from_git") is not False:
        failures.append("w15-input-provenance.json no longer flags the local-bench "
                        "half as unreproducible")
    if DECLARATION.is_file():
        if sha256(DECLARATION) != payload.get("declared_input_sha256"):
            failures.append("the shared W08 declaration changed since W15 was built")
    if payload.get("declared_input") != "evidence/A/W08/local-bench-observations.json":
        failures.append("w15-input-provenance.json points at the wrong declared input")


def check_no_stray_originals(failures: list[str], pinned: set[str]) -> None:
    for path in DOSSIER.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(DOSSIER).as_posix()
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        if path.suffix == ".bin":
            failures.append(f"flash image committed into the dossier: {rel}")
        if path.suffix == ".jsonl":
            failures.append(f"a local-bench original was copied into the dossier: {rel}")
        if rel != "SHA256SUMS.txt" and rel not in pinned:
            failures.append(f"{rel} exists but is not hash-pinned")


LOCAL_BENCH_NOTE = "local-bench original byte-checks: NOT RUN (bench tree absent)"
ANOMALY_TOKEN = "CONTROL_ELECTRICAL_ANOMALY"
# The duty-0 decay the operator confirmed on 2026-11-02, re-derived from the
# committed capture: applied duty stays 0 while the PZEM-reported current falls and
# reaches zero at device_ms=829894.
DUTY_ZERO_DECAY_SEQUENCE_A = [7.15, 0.56, 0.02, 0.0]
DUTY_ZERO_DECAY_MARKDOWN = "7.15 -> 0.56 -> 0.02 -> 0.0"
ZERO_AT_DEVICE_MS = 829894.0


def bench_root() -> pathlib.Path:
    """The bench tree to byte-check against, never a hard-coded developer path."""
    return pathlib.Path(os.environ.get("CG_W08_BENCH_ROOT",
                                       str(envelope.DEFAULT_BENCH_ROOT)))


def check_bench_originals(failures: list[str]) -> int:
    """Re-hash every declared local-bench original against the bench tree.

    The W15 rows for the H7 ladder and the H8 sessions are declared statistics
    whose originals live in Member A's local W04 tree. When that tree is absent the
    per-original SHA-256 checks cannot run - and that must be said out loud instead
    of bundled into the OK line. Returns the number of originals that could not be
    byte-checked.
    """
    if not DECLARATION.is_file():
        return 0
    root = bench_root()
    declaration = json.loads(read(DECLARATION))
    skipped = 0
    for label, bundle in sorted(declaration.get("sessions", {}).items()):
        locator = str(bundle.get("path", ""))
        if not locator.startswith(envelope.LOCAL_BENCH_MARKER):
            failures.append(f"{label}: the declared locator {locator!r} is not a "
                            f"{envelope.LOCAL_BENCH_MARKER} locator")
            continue
        declared = root / locator[len(envelope.LOCAL_BENCH_MARKER):]
        if not declared.is_file():
            skipped += 1
            continue
        if sha256(declared) != bundle.get("sha256"):
            failures.append(f"{label}: the local-bench original changed since the "
                            "declaration was derived")
    return skipped


def check_anomaly_candidate(failures: list[str]) -> None:
    """The duty-0-with-current frame must keep naming its canonical safety class.

    docs/01 22.4/23.4 name CONTROL_ELECTRICAL_ANOMALY (high severity) as the
    candidate that maps the frame to the lockout class. W15 deliberately leaves it
    open against the register-holdover reading, so the token has to stay in the
    published evidence; requiring it here is what stops it silently disappearing.
    """
    report = read(DOSSIER / "pzem-quality-report.md")
    if ANOMALY_TOKEN not in report:
        failures.append(f"pzem-quality-report.md lost the {ANOMALY_TOKEN} candidate "
                        "class (docs/01 22.4/23.4) for the duty-0-with-current frame")
    payload = json.loads(read(DOSSIER / "pzem-quality.json"))
    note = str(payload.get("audit", {}).get("on_off_consistency", {}).get("note", ""))
    if ANOMALY_TOKEN not in note:
        failures.append(f"pzem-quality.json on_off_consistency note no longer names "
                        f"{ANOMALY_TOKEN} as the competing safety candidate")

    # Operator correction 2026-11-02: the whole recorded decay must stay published,
    # with the zero point named, so the holdover reading is evidence on the table and
    # not an unverified assertion. The sequence is re-derived from the committed
    # capture, so a mutation that drops it fails here.
    consistency = payload.get("audit", {}).get("on_off_consistency", {})
    suspect = [a for a in consistency.get("anomalies", [])
               if a.get("kind") == "APPLIED_OFF_CURRENT_ABOVE_FLOOR"
               and a.get("source") == "W04-H8C-box-600s"
               and a.get("clock_ms") == 826894.0]
    if not suspect:
        failures.append("pzem-quality.json lost the 826894 applied-OFF anomaly")
    else:
        frame = suspect[0]
        if frame.get("zero_duty_current_sequence_a") != DUTY_ZERO_DECAY_SEQUENCE_A:
            failures.append(
                "pzem-quality.json no longer carries the recorded duty-0 decay "
                f"{DUTY_ZERO_DECAY_SEQUENCE_A} for the 826894 frame")
        if frame.get("current_returns_to_zero_at_device_ms") != ZERO_AT_DEVICE_MS:
            failures.append("pzem-quality.json lost the device_ms at which the "
                            "PZEM-reported current reaches zero")
        if not frame.get("trace_provenance"):
            failures.append("pzem-quality.json no longer labels the decay as a "
                            "PZEM-reported trace")
    if DUTY_ZERO_DECAY_MARKDOWN not in report:
        failures.append("pzem-quality-report.md lost the recorded duty-0 decay sequence")
    if f"{int(ZERO_AT_DEVICE_MS)}" not in report:
        failures.append("pzem-quality-report.md lost the zero-current device_ms")
    if "no independent instrument" not in report:
        failures.append("pzem-quality-report.md no longer separates the measured value "
                        "from a verified physical current")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    failures: list[str] = []
    pinned = check_pins(failures)
    check_no_physical_claim(failures)
    check_no_absolute_paths(failures)
    check_honest_verdicts(failures)
    check_anomaly_candidate(failures)
    check_spine(failures)
    check_declaration_pin(failures)
    check_no_stray_originals(failures, pinned)
    bench_skips = check_bench_originals(failures)

    if bench_skips:
        print(LOCAL_BENCH_NOTE)
    if failures:
        print("W15 DOSSIER: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    checked_note = (f"{bench_skips} byte-checks NOT RUN" if bench_skips
                    else "local-bench originals byte-checked")
    print(f"W15 DOSSIER: OK ({len(pinned)} pinned files, quality spine re-derived, "
          f"PWM decision still NOT_DECIDED; {checked_note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
