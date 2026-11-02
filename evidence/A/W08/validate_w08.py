"""Verify the W08 evidence dossier.

    py evidence/A/W08/validate_w08.py

Checks, in order:

1. every file listed in ``SHA256SUMS.txt`` exists and hashes to the pinned value,
   and the sums file is LF-only;
2. no flash image (``*.bin``) and no copy of a local-bench original was committed
   into the dossier - only the declared statistics may be;
3. **no artifact carries a physical claim**: the token ``PHYSICALLY_VERIFIED`` may
   appear only inside a sentence that denies it, and never in a CSV field;
4. the honest verdicts are still there - Gate A NOT CLOSED, A-W08-02
   ``NO_FREEZE``/``BLOCKED_HARDWARE``, ``continuous_rating_claimed: false`` in
   every thermal row, and the 55 degC ceiling still labelled provisional;
5. the numeric spine is re-derived from the committed capture, not trusted: the
   600 s CSV's driven-frame count, its peak/median current, the byte-identical
   holdover frame at ``device_ms=826894`` (7.15 A) and the empty status columns
   must still reproduce, and the committed-vs-declared cross-check of the raw
   stream against the committed CSV must still agree;
6. the unqualified-status fact is still published, not hidden: the committed
   H8-C source must be flagged ``electrical_status_recorded=false`` and the
   energy column must still have no status token anywhere.

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

FORBIDDEN = "PHYSICALLY_VERIFIED"
# A line may MENTION a physical word only to deny it. These are the denial
# markers the dossier's own sentences use; a line without one is a claim.
NEGATIONS = ("not", "never", "no ", "without", "refus", "unreach", "forbid",
             "false", "none", "non-", "instead of", "rather than")

GENERATED = (
    "operating-envelope-v1.yaml", "envelope-by-duty.csv", "holdover-frames.csv",
    "duty-zero-current-frames.csv", "electrical-status-coverage.csv",
    "source-summary.csv", "thermal-sustainability.csv", "fuse-selection.md",
    "safe-local-physical-inputs.csv", "gate-a-artifact-index.csv",
    "gate-a-operator-queue.csv", "Gate-A-report.md",
)
DECLARED_INPUT = "local-bench-observations.json"

HONEST_PHRASES = (
    "Gate A: **NOT CLOSED**",
    "PHYSICAL MEASUREMENT TAKEN BY THIS DOSSIER: **NONE**",
    "A-W08-02",
    "BLOCKED_HARDWARE",
)

# Operator correction 2026-11-02: the recorded "1.75" is the copper CORE DIAMETER
# in mm, so the cross-section is a derived reading, never a re-asked fact and never
# a nominal 2.5 mm2 claim. Kept here as a literal so the validator fails if the
# unit error returns to the published notes.
CONDUCTOR_DERIVED_AREA_MM2 = "2.405"

# docs/01 22.4/23.4 name the safety class a commanded-OFF-with-current frame maps
# to. A host tool may not decide that classification, so the token has to stay in
# the published Gate-A and acceptance rows instead of being smoothed away.
ANOMALY_TOKEN = "CONTROL_ELECTRICAL_ANOMALY"
DUTY_ZERO_DECAY_SEQUENCE = "7.15 -> 0.56 -> 0.02 -> 0.0"
DUTY_ZERO_ZERO_AT_DEVICE_MS = "829894"

# The committed-capture spine. Each value is re-derived from
# evidence/A/W04/tec-cooling-response-600s.csv on every run; if the capture or
# the analysis changes, this validator says so instead of trusting the artifact.
SPINE = {
    "frames": 957,
    "driven_frames_in_source": 600,
    "driven_frames_used": 599,
    "current_max_a": 9.99,
    "current_median_a": 7.16,
    "mean_current_excluding_holdovers_a": 7.2367,
    "mean_current_including_holdovers_a": 7.2247,
    "off_steady_max_current_a": 0.02,
    "holdover_seq": "827",
    "holdover_device_ms": 826894.0,
    "holdover_current_a": 7.15,
    "holdover_power_w": 84.2,
    "hot_side_max_c": 39.938,
    "power_consistency_max_abs_delta_w": 0.099,
}


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _expected_pinned_names() -> set[str]:
    """Every dossier file is pinned except the pin file itself and Python caches.

    Pinning both directions catches a stray file either way: an added file with no
    pin, and a pin pointing at a cache or a deleted file.
    """
    return {path.relative_to(DOSSIER).as_posix() for path in DOSSIER.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS.txt"
            and "__pycache__" not in path.parts and path.suffix != ".pyc"}


def check_pins(failures: list[str]) -> dict[str, str]:
    sums_path = DOSSIER / "SHA256SUMS.txt"
    pinned: dict[str, str] = {}
    if not sums_path.is_file():
        failures.append("SHA256SUMS.txt is missing")
        return pinned
    raw = sums_path.read_bytes()
    if b"\r\n" in raw:
        failures.append("SHA256SUMS.txt is not LF-only")
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
        pinned[rel] = digest
        target = DOSSIER / rel
        if not target.is_file():
            failures.append(f"missing evidence file: {rel}")
            continue
        actual = sha256(target)
        if actual != digest:
            failures.append(f"hash mismatch: {rel} (want {digest[:12]}… got "
                            f"{actual[:12]}…)")
    for name in GENERATED + (DECLARED_INPUT, "README.md", "acceptance.md",
                             "build_w08_artifacts.py", "validate_w08.py"):
        if name not in pinned:
            failures.append(f"{name} is not hash-pinned")
    expected = _expected_pinned_names()
    for unpinned in sorted(expected - set(pinned)):
        failures.append(f"{unpinned} is in the dossier but not hash-pinned")
    for stale in sorted(set(pinned) - expected):
        failures.append(f"{stale} is pinned but should not be (cache or deleted file)")
    return pinned


def check_no_physical_claim(failures: list[str]) -> None:
    for path in sorted(DOSSIER.rglob("*")):
        if not path.is_file() or path.suffix not in (".md", ".csv", ".yaml", ".json"):
            continue
        rel = path.relative_to(DOSSIER).as_posix()
        text = read(path)
        if path.suffix == ".csv" and FORBIDDEN in text:
            failures.append(f"{rel}: the {FORBIDDEN} token appears in a CSV field")
        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN in line and not any(n in line.lower() for n in NEGATIONS):
                failures.append(f"{rel}:{number} asserts {FORBIDDEN}: "
                                f"{line.strip()[:120]}")
        for pattern, why in (
            (re.compile(r"meets\s+(the\s+)?safety\?\W*(case|requirement)", re.I),
             "a safety-case claim"),
            (re.compile(r"\bcertified\b", re.I), "a certification claim"),
            (re.compile(r"\bcompliant\b", re.I), "a compliance claim"),
            (re.compile(r"continuous rating (of|is)\s*[0-9]"), "a continuous rating"),
            (re.compile(r"approved for (energiz|operat|deployment)", re.I),
             "an operational approval"),
        ):
            for number, line in enumerate(text.splitlines(), start=1):
                match = pattern.search(line)
                if match and not any(n in line.lower() for n in NEGATIONS):
                    failures.append(f"{rel}:{number}: {why} appeared "
                                    f"({match.group(0)!r}) in {line.strip()[:100]!r}")


def check_no_absolute_paths(failures: list[str]) -> None:
    """No pinned artifact may carry a developer absolute locator.

    An artifact that names a drive-qualified or home-directory path only reproduces
    and only reads on the machine that wrote it, so every locator here is
    repository-relative or ``<local-bench>/``-relative. This check is what turns
    that rule into something a reviewer can rely on instead of eyeballing.
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
            failures.append(f"acceptance.md lost the honest statement {phrase!r}")
    if re.search(r"Gate A (PASS|GREEN|CLOSED|COMPLETE)\b", acceptance):
        failures.append("acceptance.md declares Gate A PASS/GREEN/CLOSED/COMPLETE")

    fuse = read(DOSSIER / "fuse-selection.md")
    if "NO_FREEZE" not in fuse:
        failures.append("fuse-selection.md no longer returns NO_FREEZE")
    if "1.75" not in fuse or "2 x 2.5 mm2" not in fuse.replace("×", "x"):
        failures.append("fuse-selection.md lost the conductor deviation record")
    # The corrected conductor record: 1.75 is a core DIAMETER, so the area is a
    # derived ~2.405 mm2 under a stated solid-round assumption. Requiring all three
    # parts is what stops the old "1.75 mm2" unit error coming back, and stops the
    # narrowed gap being read as nominal 2.5 mm2 compliance.
    for token in (CONDUCTOR_DERIVED_AREA_MM2, "core diameter", "unit error",
                  "round solid", "UNVERIFIED"):
        if token not in fuse:
            failures.append(
                f"fuse-selection.md lost the corrected conductor record {token!r}")
    if re.search(r"1\.75\s*mm2", fuse.replace("²", "")):
        failures.append("fuse-selection.md states 1.75 mm2 again: 1.75 is the core "
                        "diameter in mm, not the cross-section")
    # A compliance claim is only allowed inside a sentence that denies it - the
    # same convention the dossier uses for PHYSICALLY_VERIFIED.
    for line in fuse.splitlines():
        if re.search(r"(nominal|canonical) 2\.5\s*mm2 compliance", line) and not any(
                marker in line.lower() for marker in NEGATIONS):
            failures.append("fuse-selection.md asserts 2.5 mm2 compliance instead of "
                            f"denying it: {line[:80]!r}")
            break
    if "BLOCKED_HARDWARE" not in fuse:
        failures.append("fuse-selection.md lost its status label")
    # The fuse value is operator-reported only, and a catalogue entry says nothing
    # about the installed body: keep both statements in the published note.
    for token in ("operator-reported", "catalogue", "legible"):
        if token not in fuse:
            failures.append(f"fuse-selection.md lost the fuse-evidence limit {token!r}")

    yaml_text = read(DOSSIER / "operating-envelope-v1.yaml")
    for token in ("do_not_extrapolate", "off_register_latency_rule",
                  "electrical_status_recorded", "reproducible_from_git: false",
                  "trust: LOCAL_BENCH", "status_label: REAL_DATA_ANALYZED"):
        if token not in yaml_text:
            failures.append(f"operating-envelope-v1.yaml lost {token!r}")
    if "no continuous rating" not in yaml_text.lower():
        failures.append("operating-envelope-v1.yaml no longer refuses a continuous rating")

    report = read(DOSSIER / "Gate-A-report.md")
    if "GATE A NOT CLOSED" not in report:
        failures.append("Gate-A-report.md no longer reports GATE A NOT CLOSED")
    if "exists_in_this_checkout" not in report and "In this checkout" not in report:
        failures.append("Gate-A-report.md lost the H0-H7 index resolution column")

    # Finding 1: the safety candidate and the recorded decay must stay published,
    # and the pass-criteria rows must not pre-decide them.
    for name, text in (("Gate-A-report.md", report), ("acceptance.md", acceptance)):
        if ANOMALY_TOKEN not in text:
            failures.append(f"{name} lost the {ANOMALY_TOKEN} candidate class "
                            "(docs/01 22.4/23.4) for the duty-0-with-current frame")
        if re.search(r"no unresolved high-current anomaly\D{0,30}\bMET\b", text,
                     re.IGNORECASE):
            failures.append(f"{name} asserts the high-current-anomaly criterion as "
                            "MET, which pre-decides a safety classification a host "
                            "tool cannot make")
    for name, text in (("Gate-A-report.md", report), ("acceptance.md", acceptance)):
        if DUTY_ZERO_DECAY_SEQUENCE not in text.replace("→", "->"):
            failures.append(f"{name} no longer records the duty-0 current decay "
                            f"{DUTY_ZERO_DECAY_SEQUENCE}")
        if DUTY_ZERO_ZERO_AT_DEVICE_MS not in text:
            failures.append(f"{name} lost the device_ms at which the PZEM-reported "
                            "current reaches zero")


def check_thermal_rows(failures: list[str]) -> list[dict[str, str]]:
    path = DOSSIER / "thermal-sustainability.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    if not rows:
        failures.append("thermal-sustainability.csv is empty")
        return rows
    for row in rows:
        if row["continuous_rating_claimed"] != "false":
            failures.append(f"thermal row {row['session']} claims a continuous rating")
        if row["limit_status"] != envelope_hot_side_limit_status():
            failures.append(f"thermal row {row['session']} no longer labels the "
                            "55 C ceiling provisional")
        if row["as_built_role"] != "TEC_HOT_SIDE":
            failures.append(f"thermal row {row['session']} is not the hot-side channel")
        if float(row["max_c"]) >= 55.0:
            failures.append(f"thermal row {row['session']} reports a hot-side value at "
                            "or above the provisional ceiling; re-read the verdict")
    if not any(row["session"] == "W04-H8C-box-600s"
               and row["reproducible_from_git"] == "true" for row in rows):
        failures.append("the committed 600 s hot-side row is missing")
    if not any(row["trust"] == "LOCAL_BENCH" for row in rows):
        failures.append("the declared local-bench endurance rows are missing")
    return rows


def envelope_hot_side_limit_status() -> str:
    import cg_w08_hot_side
    return cg_w08_hot_side.HOT_SIDE_LIMIT_STATUS


def check_spine(failures: list[str]) -> None:
    """Re-derive the committed numbers; the artifacts must match reality."""
    frames = envelope.classify(
        envelope.read_h8_csv(REPO_ROOT / envelope.H8_CSV, "W04-H8C-box-600s"))
    drive = envelope.drive_stats(frames)
    off = envelope.off_stats(frames)
    power = envelope.power_consistency(frames)
    thermal = envelope.thermal_response(frames)
    checks = {
        "frames": (len(frames), SPINE["frames"]),
        "driven_frames_in_source": (drive["driven_frames_in_source"],
                                    SPINE["driven_frames_in_source"]),
        "driven_frames_used": (drive["frames_used"], SPINE["driven_frames_used"]),
        "current_max_a": (drive["current_a"]["max"], SPINE["current_max_a"]),
        "current_median_a": (drive["current_a"]["median"], SPINE["current_median_a"]),
        "mean_current_excl": (drive["mean_current_a_excluding_holdovers"],
                              SPINE["mean_current_excluding_holdovers_a"]),
        "mean_current_incl": (drive["mean_current_a_inclusive_of_holdovers"],
                              SPINE["mean_current_including_holdovers_a"]),
        "off_steady_max_a": (off["steady_max_current_a"],
                             SPINE["off_steady_max_current_a"]),
        "hot_side_max_c": (thermal["t2"]["max_c"], SPINE["hot_side_max_c"]),
        "power_max_abs_delta_w": (power["max_abs_delta_w"],
                                  SPINE["power_consistency_max_abs_delta_w"]),
    }
    for name, (got, expected) in checks.items():
        if got != expected:
            failures.append(f"committed-capture spine changed on {name}: "
                            f"got {got}, pinned {expected}")
    holdovers = envelope.duty_zero_with_current(frames)
    if len(holdovers) != 2:
        failures.append(f"expected exactly 2 duty-0 frames above the steady floor in "
                        f"the committed capture, got {len(holdovers)}")
    target = next((row for row in holdovers if row["seq"] == SPINE["holdover_seq"]),
                  None)
    if target is None:
        failures.append("the 826894 holdover frame is no longer listed individually")
    else:
        if (target["clock_ms"], target["current_a"], target["power_w"]) != (
                SPINE["holdover_device_ms"], SPINE["holdover_current_a"],
                SPINE["holdover_power_w"]):
            failures.append("the 826894 holdover frame changed value")
        if target["classification"] != envelope.OFF_HOLD:
            failures.append("the 826894 frame is no longer classified as the "
                            "documented register holdover")
    empty_status = sum(1 for f in frames
                       if not f.status.get("voltage") or not f.status.get("current"))
    if empty_status != len(frames):
        failures.append("the committed CSV's electrical status cells are no longer "
                        "empty in every row - the unqualified-status finding changed")

    # And the artifacts must carry the same spine.
    summary_rows = {row["source"]: row for row in csv.DictReader(
        (DOSSIER / "source-summary.csv").open(encoding="utf-8", newline=""))}
    committed = summary_rows.get("W04-H8C-box-600s")
    if committed is None:
        failures.append("source-summary.csv lost the committed 600 s source")
    else:
        if committed["current_max_a"] != "9.99":
            failures.append("source-summary.csv no longer reports the 9.99 A peak")
        if committed["electrical_status_recorded"] != "false":
            failures.append("source-summary.csv promoted the committed capture's "
                            "electrical values to qualified")
        if committed["off_steady_max_current_a"] != "0.02":
            failures.append("source-summary.csv lost the 0.02 A steady OFF envelope")
    zero_rows = list(csv.DictReader(
        (DOSSIER / "duty-zero-current-frames.csv").open(encoding="utf-8", newline="")))
    if not any(row["seq"] == SPINE["holdover_seq"] and row["current_a"] == "7.15"
               and row["classification"] == envelope.OFF_HOLD for row in zero_rows):
        failures.append("duty-zero-current-frames.csv lost the 826894/7.15 A frame")


def bench_root() -> pathlib.Path:
    """The bench tree to byte-check against, never a hard-coded developer path."""
    return pathlib.Path(os.environ.get("CG_W08_BENCH_ROOT",
                                       str(envelope.DEFAULT_BENCH_ROOT)))


def check_declaration(failures: list[str]) -> int:
    path = DOSSIER / DECLARED_INPUT
    if not path.is_file():
        failures.append(f"{DECLARED_INPUT} is missing")
        return 0
    declaration = json.loads(read(path))
    provenance = declaration.get("provenance", {})
    for key, value in (("reproducible_from_git", False),
                       ("committed_in_git", False),
                       ("originals_copied_into_repository", False),
                       ("trust_class", "LOCAL_BENCH")):
        if provenance.get(key) != value:
            # name the file, not the parsed dict: a provenance regression has to
            # be reported, not raise AttributeError out of the validator.
            failures.append(f"{DECLARED_INPUT} provenance.{key} is not {value!r}")
    sessions = declaration.get("sessions", {})
    if len(sessions) != 18:
        failures.append(f"{DECLARED_INPUT} declares {len(sessions)} sessions, "
                        "expected 18 (12 H7 stages + 6 H8 sessions)")
    root = bench_root()
    skipped = 0
    for label, bundle in sorted(sessions.items()):
        locator = str(bundle["path"])
        if locator.startswith(envelope.LOCAL_BENCH_MARKER):
            # A <local-bench> locator is resolved against this checkout's sibling
            # bench tree, exactly as the generator wrote it; a machine without
            # that tree skips the byte check, a machine with it must agree.
            declared = root / locator[len(envelope.LOCAL_BENCH_MARKER):]
        else:
            failures.append(f"{label}: the declared locator {locator!r} is not a "
                            f"{envelope.LOCAL_BENCH_MARKER} locator")
            continue
        if not declared.is_file():
            skipped += 1  # expected on a machine without the local bench tree
            continue  # the NOT RUN note makes the skip visible instead of silent
        if sha256(declared) != bundle["sha256"]:
            failures.append(f"{label}: the local source file changed since the "
                            "declaration was derived")
    cross = sessions.get("W04-H8C-box-600s-raw")
    if cross is None:
        failures.append("the raw 600 s session is not declared, so the cross-check "
                        "against the committed CSV cannot run")
        return skipped
    frames = envelope.classify(
        envelope.read_h8_csv(REPO_ROOT / envelope.H8_CSV, "W04-H8C-box-600s"))
    git_drive = envelope.drive_stats(frames)
    declared_drive = cross["source_summary"]["drive"]
    for key in ("current_a", "voltage_v", "power_w"):
        if git_drive[key] != declared_drive[key]:
            failures.append(f"the declared raw stream and the committed CSV disagree "
                            f"on {key}: {declared_drive[key]} vs {git_drive[key]}")
    git_thermal = envelope.thermal_response(frames)
    if git_thermal["t2"] != cross["source_summary"]["thermal"]["t2"]:
        failures.append("the declared raw stream and the committed CSV disagree on the "
                        "hot-side trajectory")
    return skipped


def check_no_stray_originals(failures: list[str]) -> None:
    for path in DOSSIER.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(DOSSIER).as_posix()
        if path.suffix == ".bin":
            failures.append(f"flash image committed into the dossier: {rel}")
        if path.suffix in (".jsonl",) and rel != DECLARED_INPUT:
            failures.append(f"a local-bench original was copied into the dossier: {rel}")
        if rel.startswith("h7/") or rel.startswith("h8/"):
            failures.append(f"a local-bench original was copied into the dossier: {rel}")
    unlisted = sorted(
        rel for rel in (p.relative_to(DOSSIER).as_posix() for p in DOSSIER.rglob("*")
                        if p.is_file())
        if rel not in {"SHA256SUMS.txt"} and not rel.endswith(".pyc")
        and "__pycache__" not in rel)
    return unlisted


LOCAL_BENCH_NOTE = "local-bench original byte-checks: NOT RUN (bench tree absent)"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    failures: list[str] = []
    pinned = check_pins(failures)
    stray = check_no_stray_originals(failures)
    for rel in stray:
        if rel not in pinned:
            failures.append(f"{rel} exists but is not hash-pinned")
    check_no_physical_claim(failures)
    check_no_absolute_paths(failures)
    check_honest_verdicts(failures)
    check_thermal_rows(failures)
    check_spine(failures)
    bench_skips = check_declaration(failures)

    if bench_skips:
        print(LOCAL_BENCH_NOTE)
    if failures:
        print("W08 DOSSIER: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    checked_note = (f"{bench_skips} byte-checks NOT RUN" if bench_skips
                    else "local-bench originals byte-checked")
    print(f"W08 DOSSIER: OK ({len(pinned)} pinned files, spine re-derived from the "
          f"committed capture, no physical claim present; {checked_note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
