"""Verify the W09 evidence dossier.

    py evidence/A/W09/validate_w09.py

Checks, in order:

1. every file listed in ``SHA256SUMS.txt`` exists and hashes to the pinned value,
   and every file the manifest promises is actually pinned;
2. no artifact carries an absolute developer path - the dossier must resolve from
   the repository root alone;
3. every derived artifact reproduces byte-for-byte from the delivered tooling;
4. the numbers the dossier publishes are recomputed here from the real source
   capture rather than trusted: the row total comes from the committed CSV, and
   the invalidation counts come from running the validity layer again;
5. the honesty of the verdicts, which is the part a hash cannot protect:
   the unqualified electrical domain is still reported unqualified, an absent
   qualifier column still blocks the domains that need it, every reason code that
   fires is declared as checked, no run is certified, no invented run id is
   published to Member B, the probe-identification session class is still
   permanently excluded, the missing physical sessions are still stated as
   missing, and no fixture is labelled as a measurement;
6. the per-row contract, checked against the companion CSV itself: the declared
   column set equals the delivered header, every demanded field is either a
   column or a stated NOT AVAILABLE, no cell is blank, and every quality column
   stays inside the closed vocabulary;
7. the closed status vocabulary is used and nothing claims
   ``PHYSICALLY_VERIFIED`` for a session that did not happen;
8. the two classes of README claim are kept apart: the durable **MUST-KEEP**
   rules are demanded in every revision, while the **PHASE SNAPSHOT** figures
   describe the one real thermal session the repository holds today and are
   demanded only while that is still true. The single-session wording is
   *refused* as soon as ``run-registry.json`` lists a second real thermal
   capture, so this honesty check cannot fail the day the physical study
   succeeds (the split the reviewed W07 report validator already applies).

Exit code 0 only when every check passes. Nothing here touches hardware.
"""

from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import re
import sys
import unittest

DOSSIER = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DOSSIER.parents[2]
TOOLS = REPO_ROOT / "firmware" / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(DOSSIER))

import build_w09_artifacts as builder  # noqa: E402
import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_export as run_export  # noqa: E402
import cg_w09_run_protocol as protocol  # noqa: E402
import cg_w09_validity as validity  # noqa: E402

STATUS_VOCABULARY = {
    "IMPLEMENTED", "HOST_VERIFIED", "REAL_DATA_ANALYZED", "PHYSICALLY_VERIFIED",
    "NEED_USER_ACTION", "TEAM_DEPENDENCY", "BLOCKED_HARDWARE",
}
ABSOLUTE_PATH = re.compile(r"(?:^|[\s\"'`(])[A-Za-z]:[\\/]{1,2}[^\s\"'`]*|[\\s\"'`(]/(?:home|Users)/")
FORBIDDEN_OVERSTATEMENT = re.compile(
    r"\bW09 (PASS|GREEN|COMPLETE|CLOSED)\b|\bfour valid S1 runs (were )?collected\b",
    re.IGNORECASE,
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(name: str) -> dict:
    return json.loads((DOSSIER / name).read_text(encoding="utf-8"))


def _check_row_contract(failures: list[str], export: dict) -> None:
    """The per-row claim is checked on the published rows, not on a header claim.

    This exists because the dossier once published "26 columns per row" and named
    ``quality_by_domain``, ``invalidation_reasons`` and ``dedup_key`` while the
    companion CSV carried 24 columns without those names, and because the export
    declared a 50-column set that the file did not deliver. A row-level claim that
    nobody compares against the row-level file is not evidence.
    """
    frames_block = export["frames"]
    if not isinstance(frames_block, dict):
        failures.append("the published export inlines frame rows; the companion contract "
                        "is only checkable against the file it declares")
        return
    declared = list(frames_block.get("columns_per_row") or [])
    companion = str(frames_block.get("companion_file") or "")
    if declared != list(run_export.ROW_CSV_COLUMNS):
        failures.append(
            "the export declares a per-row column set that is not the tool's row contract: "
            f"{sorted(set(declared) ^ set(run_export.ROW_CSV_COLUMNS))}"
        )
    path = DOSSIER / companion
    if not companion or not path.is_file():
        failures.append(f"the companion file {companion!r} the export names is not on disk")
        return
    with path.open(encoding="utf-8", newline="") as handle:
        delivered = [name for name in csv.DictReader(handle).fieldnames or []]
    if delivered != declared:
        failures.append(
            f"{companion} delivers {len(delivered)} columns but the export declares "
            f"{len(declared)}; unseen in the file: {sorted(set(declared) - set(delivered))}, "
            f"undeclared in the file: {sorted(set(delivered) - set(declared))}"
        )
        return
    contract = frames_block.get("row_contract") or {}
    not_available = contract.get("not_available_per_row") or {}
    if contract.get("companion_csv_columns") != delivered:
        failures.append("the published row contract does not describe the delivered header")
    # A demanded field is either a column of the file or a stated gap. Nothing in
    # between, because "in between" is what let three named columns go missing.
    for name in run_export.ROW_CONTRACT_DELIVERED:
        if name not in delivered and name not in not_available:
            failures.append(
                f"the row contract demands {name!r} but the companion neither delivers it "
                "nor states why it cannot"
            )
    for name, reason in not_available.items():
        if not str(reason).startswith("NOT AVAILABLE"):
            failures.append(f"the row contract excuses {name!r} without a NOT AVAILABLE reason")
    for name in sorted(set(run_export.ROW_CONTRACT_NOT_AVAILABLE) - set(not_available)):
        failures.append(
            f"the tool states {name!r} as unavailable per row and the dossier no longer "
            "publishes that statement"
        )

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != int(frames_block.get("rows") or -1):
        failures.append(
            f"{companion} has {len(rows)} data rows but the export declares "
            f"{frames_block.get('rows')}"
        )
    # Every cell answers: a value, or the literal NOT_AVAILABLE / NONE the renderer
    # writes when there is none. A blank is the silent absence this file may not
    # publish, and it is what a reader would otherwise have to interpret.
    for name in delivered:
        blanks = sum(1 for row in rows if not (row.get(name) or "").strip())
        if blanks:
            failures.append(
                f"{companion}: {blanks}/{len(rows)} rows leave {name!r} blank; the contract "
                "requires a value or an explicit NOT_AVAILABLE"
            )
    for name in delivered:
        if name != "quality" and not name.endswith("_quality"):
            continue
        outside = sorted({row[name] for row in rows} - set(validity.KNOWN_QUALITIES))
        if outside:
            failures.append(
                f"{companion}: {name} carries {outside} outside the closed quality vocabulary "
                "(docs/01 §19.4)"
            )




# --- durable claims vs phase snapshots -----------------------------------------
#
# Two classes of README claim, deliberately separated - the split the reviewed W07
# report validator applies with ``ALWAYS_REQUIRED``.
#
#   MUST_KEEP_CLAIMS   rules and provenance facts that hold however the physical
#                      study develops, so they are demanded in every revision.
#   the snapshot block  figures measured over the one real thermal session in the
#                      repository today. They are demanded only while that session
#                      is all there is, and the single-session wording is refused
#                      as soon as a second real thermal capture is filed. Pinning
#                      H8-only numbers forever would make this honesty check fail
#                      the day the physical study succeeds, which is the opposite
#                      of what an honesty check is for.
MUST_KEEP_CLAIMS = (
    "MUST-KEEP",
    "PHASE SNAPSHOT",
    "MUST EVOLVE",
    "TEC_HOT_SIDE",
    "never averaged into chamber air",
    "documented, not resolved",
    "never assumed satisfied",
    "docs/01 §19.4",
    "docs/01 §20.5",
    "rows_thermally_usable_for_statistics",
    "rows_usable_for_baseline",
    "blocked_run_ids",
    "PROBE_IDENTIFICATION",
    "host tests are not physical verification",
    "usable_for_a_health_claim: false",
)

# The wording that is true only while one real thermal session exists. It is a
# claim about the study phase, not about the tooling, so it is required today and
# forbidden the moment the registry says otherwise.
SNAPSHOT_EXCLUSIVITY_CLAIM = "only real thermal capture"


def normalized_prose(text):
    """Whitespace-collapsed prose with the typographic minus replaced.

    Bullets wrap across lines and figures are bolded, so a claim is matched on the
    collapsed, emphasis-stripped text; the README writes gradients with U+2212 while
    the artifacts hold ASCII ``-``.
    """
    return " ".join(text.replace("−", "-").replace("**", "").split())


def _real_thermal_sessions(registry):
    """Real committed captures this dossier screens for a thermal scenario.

    Counted from ``run-registry.json`` rather than from the README's own words, so
    the snapshot branch tracks the data: filing a second real thermal capture moves
    the dossier out of the branch with no edit to this validator.
    """
    return sum(
        1 for capture in registry.get("captures", [])
        if capture.get("is_physical_measurement") and capture.get("scenario_screen")
    )


def _w09_host_test_count():
    """Count the W09 host tests the README quotes instead of trusting the prose."""
    suite = unittest.TestLoader().discover(
        start_dir=str(TOOLS / "tests"), pattern="test_cg_w09*.py",
        top_level_dir=str(TOOLS / "tests"),
    )

    def size(node):
        if isinstance(node, unittest.TestSuite):
            return sum(size(child) for child in node)
        return 1

    return size(suite)


def _snapshot_figures(summary, ranges, export, registry):
    """The figures the README must state, taken from the artifacts, not from prose.

    Matching them here is what stops a re-derivation from leaving the human summary
    behind: every number below is recomputed by this run and has to appear.
    """
    figures = [
        f"{summary['rows_total']:,} data rows parsed",
        f"{summary['rows_thermally_usable_for_statistics']:,} rows are clean",
        f"usable_fraction {summary['usable_fraction']}",
        f"{len(summary['reason_codes_checked'])} reason codes declared",
    ]
    for phase, count in sorted(export["experiment_phase"]["counts"].items()):
        figures.append(f"`{phase}` {count:,}")
    for code, count in sorted(summary["reason_counts"].items()):
        figures.append(f"`{code}` {count:,}")
    cadence = ranges["cadence"]
    figures += [
        f"{cadence['n_intervals']:,} intervals",
        f"mean {cadence['mean_interval_ms']} ms",
        f"min {cadence['min_interval_ms']}, max {cadence['max_interval_ms']}",
    ]
    for block in ranges["gradient"].values():
        figures.append(str(block["least_squares_gradient_c_per_s"]))
        figures.append(str(block["endpoint_gradient_c_per_s"]))
        figures.append(f"window {block['window']['duration_s']:g} s")
    for capture in registry["captures"]:
        if capture.get("scenario_screen") and capture.get("size_bytes"):
            figures.append(f"{capture['size_bytes']:,} bytes")
            figures.append(capture["sha256"])
    return figures


def _check_claim_classes(failures, readme, registry, summary, ranges, export):
    """Enforce the MUST-KEEP / PHASE SNAPSHOT split written into README section 4."""
    norm = normalized_prose(readme)
    for token in MUST_KEEP_CLAIMS:
        if token not in norm:
            failures.append(f"README.md dropped the durable MUST-KEEP claim {token!r}")

    tests = _w09_host_test_count()
    if f"{tests:,} W09 host tests" not in norm:
        failures.append(
            f"README.md does not state the {tests} W09 host tests this checkout actually "
            "collects; a quoted test count is a claim, not a style choice"
        )

    sessions = _real_thermal_sessions(registry)
    if sessions <= 1:
        if SNAPSHOT_EXCLUSIVITY_CLAIM not in norm:
            failures.append(
                "with a single real thermal session the README must say so plainly; the "
                "snapshot figures are meaningless without their scope"
            )
        for figure in _snapshot_figures(summary, ranges, export, registry):
            if figure not in norm:
                failures.append(
                    f"README.md no longer states the re-derived snapshot figure {figure!r}"
                )
    else:
        if SNAPSHOT_EXCLUSIVITY_CLAIM in norm:
            failures.append(
                f"README.md still says {SNAPSHOT_EXCLUSIVITY_CLAIM!r} with {sessions} real "
                "thermal sessions registered: a PHASE SNAPSHOT claim kept past its phase is "
                "an overstatement, not evidence"
            )


def main() -> int:
    failures: list[str] = []

    sums_path = DOSSIER / "SHA256SUMS.txt"
    if not sums_path.is_file():
        print("FAIL: SHA256SUMS.txt is missing")
        return 1

    pinned: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([0-9a-f]{64})  (.+)$", line.strip())
        if not match:
            failures.append(f"SHA256SUMS.txt: unparsable line {line!r}")
            continue
        pinned[match.group(2)] = match.group(1)

    for name, digest in sorted(pinned.items()):
        path = DOSSIER / name
        if not path.is_file():
            failures.append(f"{name} is pinned but missing")
        elif sha256(path) != digest:
            failures.append(f"{name} does not hash to the pinned value")

    for name in builder.PINNED_FILES:
        if name not in pinned:
            failures.append(f"{name} is not hash-pinned")

    # --- pin-list hygiene ------------------------------------------------------
    #
    # The manifest is the dossier's contract, so it is checked in both directions:
    # nothing may sit in the folder unpinned, and nothing may be pinned that does
    # not belong there. A __pycache__/.pyc entry hashes differently on every
    # machine, so a pin list that swallowed one makes the verdict unreproducible
    # for everybody else; a CR byte is the same failure in another form, because
    # .gitattributes normalises text to LF on checkout and a CRLF file therefore
    # hashes one way here and another way in the reviewer's tree.
    on_disk = {
        found.relative_to(DOSSIER).as_posix()
        for found in DOSSIER.rglob("*")
        if found.is_file() and found.name != "SHA256SUMS.txt"
        and "__pycache__" not in found.parts and not found.name.endswith(".pyc")
    }
    for stray in sorted(on_disk - set(pinned)):
        failures.append(f"{stray} is in the dossier but not hash-pinned")
    for cache in sorted(name for name in pinned
                        if "__pycache__" in name or name.endswith(".pyc")):
        failures.append(f"{cache} is pinned; a compiled cache file hashes per machine")
    for name in sorted(pinned):
        path = DOSSIER / name
        if path.is_file() and b"\r" in path.read_bytes():
            failures.append(f"{name} carries CR bytes and would re-hash on checkout")
    if b"\r" in sums_path.read_bytes():
        failures.append("SHA256SUMS.txt carries CR bytes and would re-hash on checkout")

    text_files = [
        name for name in pinned
        if name.endswith((".md", ".json", ".py", ".csv", ".txt"))
    ]
    for name in text_files:
        body = (DOSSIER / name).read_text(encoding="utf-8")
        hit = ABSOLUTE_PATH.search(body)
        if hit:
            failures.append(f"{name} carries a non-repository-relative path: {hit.group(0)!r}")
        if name.endswith(".md") and FORBIDDEN_OVERSTATEMENT.search(body):
            failures.append(f"{name} overstates the week as finished")

    expected = builder.build_artifacts()
    for name, text in expected.items():
        path = DOSSIER / name
        if not path.is_file():
            failures.append(f"{name} is not a derived artifact on disk")
        elif path.open(encoding="utf-8", newline="\n").read() != text:
            failures.append(f"{name} does not reproduce from the delivered tooling")

    export = read_json(f"exports/{builder.EXPORT_RUN_ID}.json")
    index = read_json("s1-run-index.json")
    summary = read_json("invalidation-summary.json")
    registry = read_json("run-registry.json")
    ranges = read_json("healthy-ranges.json")

    if export["device_id"] != "NOT_CARRIED_BY_THIS_ENCODING":
        failures.append("the export no longer states that device_id is not carried")
    if export["timestamp_semantics"]["timestamp_utc_status"] != "UNAVAILABLE":
        failures.append("the export claims a device wall clock it does not have")
    if export["run_id_status"] != run_export.RUN_ID_AMBIGUOUS:
        failures.append("the export no longer reports its run_id as unresolved")
    if export["run_id"] is not None:
        failures.append("the export published a run_id the source does not carry")
    for joined in ("MULTIPLE_RUN_IDS", "MULTIPLE_BOOT_IDS"):
        if joined in json.dumps(index) or joined in json.dumps(export):
            failures.append(f"an invented joined identifier ({joined}) is published to Member B")
    if index["valid_s1_run_ids_for_member_b"]:
        failures.append("the index hands B a run id whose source identity is unresolved")
    if not index["blocked_run_ids"]:
        failures.append("the index no longer states why the candidate is blocked")

    source = REPO_ROOT / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = [r for r in reader if r and any(cell.strip() for cell in r)]
    if summary["rows_total"] != len(rows):
        failures.append(
            f"invalidation-summary rows_total={summary['rows_total']} but the committed capture "
            f"has {len(rows)} data rows"
        )
    frames, _ = cp.read_csv_capture(builder.W04_CSV, builder.RUN_LABEL)
    recomputed = validity.summarize(validity.evaluate_frames(frames))
    for key in ("rows_total", "rows_usable_for_baseline", "quality_counts",
                "quality_counts_by_domain", "reason_counts"):
        if summary[key] != recomputed[key]:
            failures.append(f"invalidation-summary {key} is not what the validity layer returns")
    run_ids_in_source = {str(f.run_id) for f in frames if f.run_id}
    if run_ids_in_source != set(export["run_ids"]):
        failures.append("the run_id segments the export names are not the ones the source carries")
    if len(run_ids_in_source) > 1 and len(index["runs"]) > 1:
        failures.append("one boot_id's segments were registered as independent runs")

    if summary["quality_counts_by_domain"]["electrical"]["VALID"] != 0:
        failures.append(
            "the electrical domain was promoted to VALID, but every electrical column in the "
            "committed capture is reported without a producer status"
        )
    _check_row_contract(failures, export)
    # Absence must still mean absence: a qualifier the encoding does not carry may
    # not be read as a satisfied one, and may not leave a row scenario-usable.
    if (summary["rows_usable_for_baseline"]
            > summary.get("rows_thermally_usable_for_statistics", -1)):
        failures.append("the scenario-usable count exceeds the thermally-usable count it depends on")
    domain_of_status = {
        status_field: domain
        for domain, fields in validity.STATUS_FIELDS_BY_DOMAIN.items()
        for status_field in fields
    }
    checked_absences = 0
    row_verdicts = validity.evaluate_frames(frames)
    for frame, verdict in zip(frames, row_verdicts):
        for status_field, domain in domain_of_status.items():
            if frame.has(status_field):
                continue
            checked_absences += 1
            code = f"{status_field.upper()}_ABSENT"
            if code not in verdict.reason_codes:
                failures.append(f"row {frame.seq} lacks {status_field} and reports no {code}")
            if verdict.quality_by_domain[domain] not in validity.BLOCKING_SEVERITIES:
                failures.append(
                    f"row {frame.seq}: {status_field} absent but {domain} was not blocked"
                )
            for scenario in ("S1_NORMAL_BASELINE", "S2_DOOR_DISTURBANCE"):
                needed = validity.SCENARIO_REQUIRED_DOMAINS[scenario]
                if domain in needed and scenario in verdict.usable_for:
                    failures.append(
                        f"row {frame.seq} is {scenario}-usable while {status_field} is absent"
                    )
    if checked_absences == 0:
        failures.append(
            "no absent-qualifier check ran against the committed capture; the dossier's "
            "fail-closed claim would be untested"
        )
    emitted = {code for verdict in row_verdicts for code in verdict.reason_codes}
    undeclared = sorted(emitted - set(summary["reason_codes_checked"]))
    if undeclared:
        failures.append(f"reason codes fire without being declared as checked: {undeclared}")
    if ranges["electrical_active_range"]["usable_for_a_health_claim"] is not False:
        failures.append("healthy-ranges.json now offers unqualified electrical values as health evidence")
    if not str(ranges["electrical_active_range"]["qualification"]).startswith("UNQUALIFIED"):
        failures.append("healthy-ranges.json no longer labels the electrical range unqualified")
    if ranges["electrical_domain_counts"]["VALID"] != 0:
        failures.append("healthy-ranges.json claims a VALID electrical domain the source cannot support")
    for entry in index["runs"]:
        if entry["is_physical_measurement"] is not True:
            failures.append("a non-physical run appears in the run index")
    for capture in registry["captures"]:
        if capture["eligibility"] == "HOST_FIXTURE_NOT_A_RUN" and capture["is_physical_measurement"]:
            failures.append(f"{capture['capture_id']}: a host fixture is labelled a measurement")
        if "fixture" in capture["kind"] and capture["is_physical_measurement"]:
            failures.append(f"{capture['capture_id']}: fixture kind carried as physical data")
    if registry["s1_runs_certified_valid"] != 0:
        failures.append("the registry certifies S1 runs that were never collected")

    excluded = [p for p in registry["external_positions"]
                if p.get("session_class") == "PROBE_IDENTIFICATION"]
    if not excluded:
        failures.append(
            "the 2026-11-02 probe-identification session is no longer excluded by the registry"
        )
    if "PROBE_IDENTIFICATION" not in validity.EXCLUDED_SESSION_CLASSES:
        failures.append("the validity layer no longer excludes the probe-identification class")
    # Untracked bytes cannot anchor a published claim - the rule the registry
    # states for the H8 frames, applied to the untracked door driver too.
    uncitable = [p for p in registry["external_positions"]
                 if p.get("eligibility") == validity.UNCITABLE_UNTRACKED_SOURCE]
    if not uncitable:
        failures.append(
            "the contact-inversion claim is published without its citation status; its only "
            "code-level source is tracked on no ref"
        )
    for position in uncitable:
        if not position.get("claim_kept") or not position.get("action_required"):
            failures.append(
                f"{position.get('capture_id')}: an uncitable source must keep its claim and "
                "name what would make it citable"
            )
    for name in ("README.md", "acceptance.md", "run-registry.json"):
        body = (DOSSIER / name).read_text(encoding="utf-8")
        if "h8_door.c" in body and validity.UNCITABLE_UNTRACKED_SOURCE not in body:
            failures.append(f"{name} cites an untracked source as proof without its label")

    doc = protocol.document()
    for gate in protocol.GATES:
        if not gate.doc_anchor or "docs/" not in gate.doc_anchor:
            failures.append(f"gate {gate.gate_id} has no canonical doc anchor")
    if doc["gate_counts"].get("BEFORE_RUN", 0) == 0 or doc["gate_counts"].get("AFTER_RUN", 0) == 0:
        failures.append("the checklist lost one half of the A-W09-01 requirement")
    observed = {g.firmware_observability for g in protocol.GATES}
    if not observed <= {proto_val for proto_val in (
        protocol.OBSERVABLE, protocol.PARTIAL, protocol.HOST_ONLY
    )}:
        failures.append("a gate uses an observability value outside the closed vocabulary")

    for label, where in (
        (export["status_label"], "export"),
        *( (entry["status_label"], f"index run {entry['device_run_label']}")
           for entry in index["runs"] ),
        *( (capture["status_label"], f"registry {capture['capture_id']}")
           for capture in registry["captures"] ),
    ):
        if label not in STATUS_VOCABULARY:
            failures.append(f"{where}: status label {label!r} is outside the vocabulary")
    readme = (DOSSIER / "README.md").read_text(encoding="utf-8")
    acceptance = (DOSSIER / "acceptance.md").read_text(encoding="utf-8")
    # PROBE_IDENTIFICATION is a durable claim; "REAL DATA NOT AVAILABLE" is a
    # snapshot of the study phase, so it is tied to the measured certified-run count
    # instead of being pinned forever - see _check_claim_classes.
    if "PROBE_IDENTIFICATION" not in readme + acceptance:
        failures.append("the dossier no longer states PROBE_IDENTIFICATION")
    if registry["s1_runs_certified_valid"] == 0:
        if "REAL DATA NOT AVAILABLE" not in readme + acceptance:
            failures.append(
                "no S1 run is certified, so the dossier must still state REAL DATA NOT AVAILABLE"
            )
    elif "REAL DATA NOT AVAILABLE" in readme + acceptance:
        failures.append(
            f"{registry['s1_runs_certified_valid']} S1 runs are certified but the "
            "dossier still declares the real data missing"
        )
    _check_claim_classes(failures, readme, registry, summary, ranges, export)

    if not failures:
        print(
            f"W09 DOSSIER: OK ({len(pinned)} pinned files, "
            f"{summary['rows_total']} rows re-derived from the committed capture, "
            "honest verdicts intact)"
        )
        return 0

    print("W09 DOSSIER: FAIL")
    for failure in failures:
        print(f"  - {failure}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
