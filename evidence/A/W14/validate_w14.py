"""W14 dossier validator: byte pins plus the honesty of every verdict.

Regenerating a report can only prove it reproduces; it cannot prove it still tells the
truth. This validator re-reads the captures themselves and re-checks the claims this
week could most easily get wrong:

* a chamber-air statistic that averages the TEC hot-side surface (`t2_c`) - the flag
  must agree with the term list on every published row, not just in prose;
* the A-W14-02 control itself: `conditioning_fingerprint` is re-computed from the
  committed capture, and every `ablation-support.csv` row has its `device_ms` to
  `feature_c`/`pwm`/`door`/`boot_id` attribution re-derived from the source row it
  names. A stamped label nobody checks is not a proof, so nothing here accepts the
  artifact's own word for it;
* one session's sample dispersion described as a distribution;
* a disturbance response for a door that was never opened, with the tally re-derived
  from the CSV rather than quoted;
* a pairing tolerance presented as agreed, adopted, final, or simply valued;
* a forbidden claim hidden in a JSON value, where the prose guard's line structure
  gives no purchase and only the structural guard reaches it.

It also re-derives the sensor-position QA facts from the capture (role column tokens,
which channel rose while the bridge was driven) and re-computes every published variant
metric, so a doc that drifted from the data fails on the number, not on the sentence.

Two classes of check, kept apart deliberately:

* `ALWAYS_REQUIRED` is DURABLE - it holds however the physical study develops.
* The single-session wording, this week's capture list and every count quoted from them
  are a PHASE SNAPSHOT - MUST EVOLVE: they are true only while the repository holds one
  thermal session, so the validator requires that language now and forbids it later. The
  capture set comes from `build_w14_artifacts.CAPTURES`, never from a hard-coded
  filename, so the next session joins the dossier without this file blaming the data
  for having grown.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import pathlib
import re
import sys

# Importing the builder must not drop a __pycache__ into a hash-pinned folder: a cache
# file is not a deliverable and check_pins fails the dossier if one is present.
sys.dont_write_bytecode = True

DOSSIER = pathlib.Path(__file__).resolve().parent
REPO = DOSSIER.parents[2]
for _entry in (str(REPO / "firmware" / "tools"), str(DOSSIER)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import build_w14_artifacts as gen  # noqa: E402
import cg_thermal_repeatability as rep  # noqa: E402
import cg_w14_pairing as pair  # noqa: E402
import cg_w14_spatial as sp  # noqa: E402
import cg_w14_sensor_qa as qa  # noqa: E402

FAILURES: list[str] = []

# DURABLE vocabulary: these labels hold however the physical study develops, and the
# artifacts must keep carrying them.
ALWAYS_REQUIRED = ("SINGLE_SESSION_OBSERVATION", "NOT_COMPUTABLE", "includes_hot_side",
                   "conditioning_fingerprint", "one_fingerprint_per_capture",
                   "used_rows_conditioning_fingerprint", "within_session",
                   "PROBE_IDENTIFICATION", "NEEDS_A_NEW_CAPTURE",
                   "NEEDS_PHYSICAL_EVIDENCE", "TEAM_DEPENDENCY", "NOT_VERIFIABLE",
                   "device_ms")
GENERATED_SUFFIXES = {".md", ".json", ".csv", ".jsonl"}
# MEDIUM-4: the pinned .py files are part of the delivered dossier and are hashed by
# check_pins, so they are scanned too. A rule that stops at the file extension of the
# things that usually hold the leak is a rule with a hole in it.
PATH_SCAN_SUFFIXES = GENERATED_SUFFIXES | {".py"}
DATA_ARTIFACTS = ("spatial-statistics.json", "ablation-support.json",
                  "ablation-support.csv", "sensor-position-qa.json", "pairing-input.json")
ABSENT_DOOR_TOKENS = ("1", "OPEN", "TRUE")
PROVENANCE_SCANNED = tuple(sorted(gen.pinned_names()))
# The driven block every phase-level check reads first when an artifact names no capture.
PHASES = ("baseline", "cooling", "recovery")

# The capture set is the builder's data, so this file cannot pin itself to one filename.
CAPTURE_PATHS: dict[str, pathlib.Path] = {}
CAPTURE_ROWS: dict[str, list[dict[str, str]]] = {}
for _path in gen.CAPTURES:
    _cid = rep.capture_id(_path)
    CAPTURE_PATHS[_cid] = _path
    if not _path.is_file():
        FAILURES.append(f"the builder's capture {_cid} is not on disk")
    else:
        CAPTURE_ROWS[_cid] = rep.read_rows(_path)
CAPTURE_IDS = tuple(CAPTURE_PATHS)
PRIMARY_CAPTURE = CAPTURE_IDS[0] if CAPTURE_IDS else ""
BOOT_IDS = {cid: sorted({str(row.get("boot_id") or "") for row in rows})
            for cid, rows in CAPTURE_ROWS.items()}
SESSIONS = len({boot for boots in BOOT_IDS.values() for boot in boots})
FINGERPRINTS = {cid: sp.conditioning_fingerprint(rows) for cid, rows in CAPTURE_ROWS.items()}
PHASE_ROWS = {cid: rep.split_phases(rows) for cid, rows in CAPTURE_ROWS.items()}
CAPTURE_NAMES = {path.name: cid for cid, path in CAPTURE_PATHS.items()}

# Scanning the pinned .py files includes scanning this file, so the pattern is one raw
# literal written so that its own text is not a match for itself: it neither carries a
# drive-letter prefix nor spells a home directory in the slash-wrapped form it hunts.
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[/\\]|[/\\](?:home|Users)[/\\])")


def require(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def load(name: str) -> dict[str, object]:
    return json.loads((DOSSIER / name).read_text(encoding="utf-8"))


def rows_of(cid: str) -> list[dict[str, str]]:
    """The committed rows of a named capture, or a failure naming the unknown capture."""
    if cid in CAPTURE_ROWS:
        return CAPTURE_ROWS[cid]
    FAILURES.append(f"an artifact names capture {cid!r}, which is not in the W14 capture "
                    f"set {list(CAPTURE_IDS)}")
    return []


def full_term_rows(rows: list[dict[str, str]], terms: tuple[str, ...]
                   ) -> list[dict[str, str]]:
    """The rows a term-set statistic walks: every term usable in them."""
    kept = []
    for row in rows:
        value, usable, total = sp.mean_of_terms(row, terms)
        if value is not None and usable == total:
            kept.append(row)
    return kept


def _expected_pinned_names() -> set[str]:
    """The declared deliverable set, shared with the builder so the two cannot drift."""
    return set(gen.pinned_names())


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
            FAILURES.append(f"hash mismatch: {name} (want {want[:12]}… got "
                            f"{got[:12]}…)")
    expected = _expected_pinned_names()
    for unpinned in sorted(expected - pinned):
        FAILURES.append(f"{unpinned} is in the dossier but not pinned")
    for stale in sorted(pinned - expected):
        FAILURES.append(f"{stale} is pinned but is not a declared deliverable")
    present = gen.present_dossier_files()
    for name in present:
        if "__pycache__" in name.split("/") or name.lower().endswith(".pyc"):
            FAILURES.append(f"{name} is a Python cache committed inside the dossier: it "
                            "is not a deliverable and is not pin material - delete it")
    for name in sorted(set(present) - expected - {"SHA256SUMS.txt"}):
        FAILURES.append(f"{name} is present in the dossier and is not a declared "
                        "deliverable: nothing may be dropped into a pinned folder and "
                        "then re-pinned into legitimacy")


def check_provenance_paths() -> None:
    """No committed artifact may name a capture by a developer's absolute path."""
    for name in PROVENANCE_SCANNED:
        path = DOSSIER / name
        if not path.is_file() or path.suffix not in PATH_SCAN_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if ABSOLUTE_PATH.search(line):
                FAILURES.append(f"{path.name}:{number} embeds an absolute capture path: "
                                f"{line.strip()[:100]!r}")


def check_no_false_claims() -> None:
    """The claims this week must not assert are checked in every generated artifact.

    Two guards, because they catch different things: `assert_no_false_claim` reads prose
    line by line and lets a quoted or negated discussion through, and
    `guard_no_forbidden_claim` reads parsed JSON with no exemption at all. Running only
    the first over a .json file is what let a planted `"summary": "... no movement
    verified ..."` ship: every JSON value line is made of double quotes, so a guard that
    counts a double quote as evidence of quotation treats the whole file as quoted.
    """
    for path in sorted(DOSSIER.iterdir()):
        if not path.is_file() or path.suffix not in GENERATED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            qa.assert_no_false_claim(path.name, text)
        except rep.AnalysisError as error:
            FAILURES.append(str(error))
        if path.suffix == ".json":
            try:
                payload = json.loads(text)
            except ValueError as error:
                FAILURES.append(f"{path.name} is not parsable JSON: {error}")
                continue
            try:
                qa.guard_no_forbidden_claim(payload)
            except rep.AnalysisError as error:
                FAILURES.append(f"{path.name}: {error}")


def check_always_required() -> None:
    """DURABLE: the labels that must survive any further physical study."""
    machine_text = "".join((DOSSIER / name).read_text(encoding="utf-8")
                           for name in DATA_ARTIFACTS)
    for token in ALWAYS_REQUIRED:
        require(token in machine_text,
                f"the W14 artifacts no longer carry the durable label {token!r}")


def check_hot_side_containment() -> None:
    """T2 is a surface. No statistic labelled chamber air may include it."""
    matrix = load("ablation-support.json")
    for name, variant in sp.VARIANTS.items():
        if variant["is_chamber_air"]:
            require("t2_c" not in variant["terms"],
                    f"variant {name} is labelled chamber air but carries t2_c")
    for entry in matrix["captures"]:
        for name, phases in entry["variants"].items():
            variant = sp.VARIANTS[name]
            for phase, metrics in phases.items():
                for key in ("includes_hot_side", "is_chamber_air"):
                    require(key in metrics,
                            f"ablation {name}/{phase} lost the {key} label")
                if metrics["includes_hot_side"] and metrics["is_chamber_air"]:
                    FAILURES.append(
                        f"ablation {name}/{phase} calls a hot-side-contaminated mean "
                        "chamber air")
                if "t2_c" in metrics["feature_terms"]:
                    require(metrics["includes_hot_side"] is True,
                            f"ablation {name}/{phase} hides the hot side in its flag")
                    require(not metrics["is_chamber_air"],
                            f"ablation {name}/{phase} includes t2_c in a chamber-air set")
                if not metrics["includes_hot_side"]:
                    require(not sp.terms_include_hot_side(metrics["feature_terms"]),
                            f"ablation {name}/{phase} flag disagrees with its own terms")

    csv_rows = read_ablation_csv()
    if csv_rows is not None:
        _, records = csv_rows
        for record in records:
            terms = record["feature_terms"].split(";")
            want_hot = "1" if sp.terms_include_hot_side(terms) else "0"
            if record["includes_hot_side"] != want_hot:
                FAILURES.append(f"ablation row {record['variant']} flags hot side "
                                f"{record['includes_hot_side']}, its terms say {want_hot}")
                break
            if record["is_chamber_air"] == "1" and "t2_c" in terms:
                FAILURES.append(f"ablation row {record['variant']} is chamber air and "
                                "includes t2_c")
                break

    spatial = load("spatial-statistics.json")
    require(spatial["air_terms"] == list(sp.AIR_TERMS) and "t2_c" not in spatial["air_terms"],
            "spatial-statistics.json lost the air/hot-side split")
    for entry in spatial["captures"]:
        for phase, block in entry["phases"].items():
            if not isinstance(block, dict) or "air_gradient" not in block:
                continue
            require("t2_c" not in block["air_gradient"]["terms"],
                    f"spatial {phase} air gradient includes the hot-side probe")
            require(block["air_gradient"]["includes_hot_side"] is False,
                    f"spatial {phase} air gradient flags no hot side but should not "
                    "include one")


def read_ablation_csv() -> tuple[list[str], list[dict[str, str]]] | None:
    path = DOSSIER / "ablation-support.csv"
    if not path.is_file():
        FAILURES.append("ablation-support.csv is missing")
        return None
    text = path.read_text(encoding="utf-8")
    header = text.splitlines()[0].split(",")
    records = list(csv.DictReader(io.StringIO(text)))
    require(len(records) > 100, f"ablation-support.csv has only {len(records)} data rows")
    return header, records


def check_conditioning_provenance() -> None:
    """Re-derive the A-W14-02 control from the capture; trust no stamped label.

    The fingerprint is one hash per capture, so the published rows cannot disagree with
    each other and prove nothing by agreeing. What this checks instead is that every
    published fingerprint - the capture-wide one and the per-variant fingerprint of the
    rows each statistic actually walked - is what the committed rows hash to, and that
    `one_fingerprint_per_capture` matches the derived state rather than a literal.
    """
    matrix = load("ablation-support.json")
    top = matrix.get("physical_condition_control")
    require(isinstance(top, dict),
            "ablation-support.json lost physical_condition_control: the control claim "
            "has to be published as data, not as a sentence")
    derived_flags: list[bool] = []
    for entry in matrix["captures"]:
        cid = str(entry["capture"])
        rows = rows_of(cid)
        if not rows:
            continue
        want = FINGERPRINTS[cid]
        require(entry["conditioning_fingerprint"] == want,
                f"ablation capture {cid} publishes conditioning_fingerprint "
                f"{entry['conditioning_fingerprint']!r}, the committed rows hash to "
                f"{want!r} - a fingerprint the capture does not produce is a label, "
                "not a proof")
        require(entry.get("condition_columns") == list(sp.CONDITION_COLUMNS),
                f"ablation capture {cid} no longer states which columns the "
                "fingerprint hashes")
        control = entry.get("physical_condition_control")
        require(isinstance(control, dict),
                f"ablation capture {cid} has no per-capture physical_condition_control")

        phases = PHASE_ROWS[cid]
        stamped: set[str] = set()
        used_by_phase: dict[str, set[str]] = {}
        for name, per_phase in entry["variants"].items():
            terms = tuple(sp.VARIANTS[name]["terms"])
            for phase, metrics in per_phase.items():
                stamped.add(str(metrics.get("conditioning_fingerprint")))
                require(metrics.get("conditioning_fingerprint") == want,
                        f"ablation row {name}/{phase} of {cid} carries fingerprint "
                        f"{metrics.get('conditioning_fingerprint')!r}; its own capture's "
                        f"rows hash to {want!r}")
                used = full_term_rows(phases.get(phase, []), terms)
                want_used_fp = sp.conditioning_fingerprint(used)
                require(metrics.get("used_rows") == len(used),
                        f"ablation row {name}/{phase} of {cid} says it walked "
                        f"{metrics.get('used_rows')} rows; the phase holds {len(used)} "
                        "rows with every term usable")
                require(metrics.get("used_rows_conditioning_fingerprint") == want_used_fp,
                        f"ablation row {name}/{phase} of {cid} hashes its used condition "
                        f"rows to {metrics.get('used_rows_conditioning_fingerprint')!r}, "
                        f"the rows say {want_used_fp!r}")
                if metrics.get("usable"):
                    used_by_phase.setdefault(phase, set()).add(want_used_fp)
        disagreeing = sorted(p for p, fps in used_by_phase.items() if len(fps) != 1)
        derived_flag = stamped == {want} and not disagreeing
        derived_flags.append(derived_flag)
        require(derived_flag is True,
                f"the conditioning control does not hold for {cid}: the variants were "
                f"not computed over one set of physical rows "
                f"(stamped={sorted(stamped)}, capture={want!r}, disagreeing phases="
                f"{disagreeing}), so the ablation is not one run described several ways")
        if isinstance(control, dict):
            require(control.get("one_fingerprint_per_capture") is derived_flag,
                    f"{cid}: published one_fingerprint_per_capture="
                    f"{control.get('one_fingerprint_per_capture')!r} but the rows derive "
                    f"{derived_flag} - the flag is computed from the data, never written "
                    "as a literal")
            require(control.get("capture_fingerprint") == want,
                    f"{cid}: physical_condition_control names {want!r} as its capture "
                    f"fingerprint, it names {control.get('capture_fingerprint')!r}")
            require(control.get("phases_where_variants_disagree_on_used_rows")
                    == disagreeing,
                    f"{cid}: the published list of disagreeing phases is not what the "
                    "used-row fingerprints give")
    if isinstance(top, dict):
        require(top.get("one_fingerprint_per_capture") is all(derived_flags),
                "the dossier-wide one_fingerprint_per_capture does not match the value "
                "derived from the captures")


def check_ablation_row_attribution() -> None:
    """Every CSV row: which source row produced it, re-derived or failed.

    A long-format series is only joinable if each line really is that variant's mean of
    that device_ms's named terms under that boot, duty and door token. This recomputes
    the whole series from the captures, line by line, and compares.
    """
    read = read_ablation_csv()
    if read is None:
        return
    header, records = read
    for key in ("capture", "boot_id", "phase", "variant", "feature_terms", "device_ms",
                "pwm_applied_permille", "door_open", "feature_c", "term_count",
                "conditioning_fingerprint"):
        require(key in header, f"ablation-support.csv lost the {key} column")
    matrix = load("ablation-support.json")
    observed: dict[tuple[str, str], list[str]] = {}
    for number, record in enumerate(records, start=2):
        cid = CAPTURE_NAMES.get(str(record["capture"]))
        if cid is None:
            FAILURES.append(f"ablation-support.csv line {number} names capture "
                            f"{record['capture']!r}, which is not a file in the W14 "
                            "capture set")
            continue
        name = str(record["variant"])
        phase = str(record["phase"])
        if name not in sp.VARIANTS:
            FAILURES.append(f"ablation-support.csv line {number} names the unknown "
                            f"variant {name!r}")
            continue
        variant = sp.VARIANTS[name]
        if phase not in PHASE_ROWS[cid]:
            FAILURES.append(f"ablation-support.csv line {number} names phase {phase!r}, "
                            f"which {cid} does not have")
            continue
        terms = tuple(variant["terms"])
        require(record["feature_terms"].split(";") == list(terms),
                f"ablation-support.csv line {number} lists terms {record['feature_terms']}"
                f", variant {name} is {list(terms)}")
        source_rows = PHASE_ROWS[cid].get(phase)
        if source_rows is None:
            FAILURES.append(f"ablation-support.csv line {number} names phase {phase}, "
                            f"which {cid} does not have")
            continue
        device_ms = record["device_ms"]
        matches = [row for row in source_rows
                   if (row.get("device_ms") or "") == device_ms]
        if len(matches) != 1:
            FAILURES.append(f"ablation-support.csv line {number} attributes device_ms="
                            f"{device_ms} of {cid}/{phase} to {len(matches)} source rows "
                            "- a series row has to name exactly one")
            continue
        source = matches[0]
        for column in ("boot_id", "pwm_applied_permille", "door_open"):
            require(record[column] == (source.get(column) or ""),
                    f"ablation-support.csv line {number} publishes {column}="
                    f"{record[column]!r} for device_ms={device_ms}, the source row says "
                    f"{(source.get(column) or '')!r} - the row is not attributed to the "
                    "physical run it claims")
        value, usable, total = sp.mean_of_terms(source, terms)
        if value is None or usable != total:
            FAILURES.append(f"ablation-support.csv line {number} carries a feature value "
                            f"for device_ms={device_ms} whose terms are not all usable "
                            f"({usable}/{total})")
            continue
        try:
            published = float(record["feature_c"])
        except ValueError:
            FAILURES.append(f"ablation-support.csv line {number} has a non-numeric "
                            f"feature_c {record['feature_c']!r}")
            continue
        require(round(published, 4) == round(value, 4),
                f"ablation-support.csv line {number} publishes feature_c={record['feature_c']}"
                f" for {name} at device_ms={device_ms}; the named terms in that source "
                f"row mean {round(value, 4)}")
        require(record["term_count"] == str(total),
                f"ablation-support.csv line {number} term_count={record['term_count']} "
                f"against {total} named terms")
        require(record["conditioning_fingerprint"] == FINGERPRINTS[cid],
                f"ablation-support.csv line {number} stamps conditioning_fingerprint="
                f"{record['conditioning_fingerprint']!r} while the capture's condition "
                f"rows hash to {FINGERPRINTS[cid]!r}")
        observed.setdefault((name, phase), []).append(device_ms)

    expected_total = 0
    for entry in matrix["captures"]:
        cid = str(entry["capture"])
        if cid not in CAPTURE_ROWS:
            continue
        for name, per_phase in entry["variants"].items():
            terms = tuple(sp.VARIANTS[name]["terms"])
            for phase, metrics in per_phase.items():
                if not metrics.get("usable"):
                    continue
                want = [str(row.get("device_ms") or "")
                        for row in full_term_rows(PHASE_ROWS[cid].get(phase, []), terms)]
                expected_total += len(want)
                got = observed.get((name, phase), [])
                require(got == want,
                        f"the published series for {name}/{phase} of {cid} is not the "
                        f"capture's row sequence ({len(got)} rows published against "
                        f"{len(want)} in the capture)")
    require(len(records) == expected_total,
            f"ablation-support.csv holds {len(records)} rows; the captures support "
            f"{expected_total} (one per variant per full-term row per usable phase)")


def check_variant_recompute() -> None:
    """Every published variant metric, recomputed from the capture, not trusted."""
    matrix = load("ablation-support.json")
    for entry in matrix["captures"]:
        cid = str(entry["capture"])
        if cid not in CAPTURE_ROWS:
            FAILURES.append(f"ablation names {cid}, which is not in the W14 capture set "
                            f"{list(CAPTURE_IDS)}")
            continue
        phases = PHASE_ROWS[cid]
        for name, published in entry["variants"].items():
            for phase, metrics in published.items():
                if not metrics.get("usable"):
                    continue
                want = sp.variant_phase_metrics(phases[phase], phase, name)
                for key in ("samples", "delta_c", "min_c", "max_c",
                            "whole_phase_slope_c_per_min", "partial_term_rows",
                            "unqualified_rows", "includes_hot_side", "is_chamber_air"):
                    require(want[key] == metrics[key],
                            f"ablation {name}/{phase} publishes {key}={metrics[key]}, the "
                            f"capture says {want[key]}")


def check_spatial_recompute() -> None:
    """Independent arithmetic on the raw rows for the headline gradient figures."""
    spatial = load("spatial-statistics.json")
    for entry in spatial["captures"]:
        cid = str(entry["capture"])
        rows = rows_of(cid)
        if not rows:
            continue
        driven = [row for row in PHASE_ROWS[cid]["cooling"]
                  if all(rep.reading(row, term)[1] in ("ok", "unqualified")
                         for term in sp.AIR_TERMS)]
        naive: dict[str, float] = {}
        for index, a in enumerate(sp.AIR_TERMS):
            for b in sp.AIR_TERMS[index + 1:]:
                values = [round(float(row[a]) - float(row[b]), 4) for row in driven]
                if values:
                    naive[f"{a}-vs-{b}"] = round(max(abs(v) for v in values), 4)
        block = entry["phases"].get("cooling", {})
        if not isinstance(block, dict) or "air_gradient" not in block:
            continue
        block = block["air_gradient"]
        published = {label.split(" (")[0]: pair_block["max_abs_c"]
                     for label, pair_block in block["pairs"].items()}
        for key, want in naive.items():
            require(published.get(key) == want,
                    f"spatial air gradient {key} of {cid} publishes {published.get(key)}, "
                    f"the rows say {want}")
        require(block["tallies"]["usable_pairs"] == len(driven),
                f"spatial air gradient of {cid} claims "
                f"{block['tallies']['usable_pairs']} pairs, the rows hold {len(driven)}")
        require(block["tallies"].get("unqualified_rows") is not None,
                f"spatial air gradient of {cid} does not tally the gradient samples whose "
                "t*_status was never recorded")
        if driven:
            hot_max = max(abs(float(row["t2_c"]) - float(row[term]))
                          for row in driven for term in sp.AIR_TERMS)
            require(block["max_pairwise_difference_c"] < hot_max,
                    "the air-only maximum is not smaller than the surface separation, so "
                    "the two are not the blocks they claim to be")


def check_disturbance_honesty() -> None:
    """Re-read the door column; the response status has to follow the data."""
    spatial = load("spatial-statistics.json")
    block = spatial["disturbance_specific_response"]
    tally_by_capture: dict[str, dict[str, int]] = {}
    open_by_capture: dict[str, int] = {}
    for entry in spatial["captures"]:
        cid = str(entry["capture"])
        rows = rows_of(cid)
        tally: dict[str, int] = {}
        for row in rows:
            token = (row.get("door_open") or "MISSING").strip() or "MISSING"
            tally[token] = tally.get(token, 0) + 1
        tally_by_capture[cid] = tally
        open_by_capture[cid] = sum(count for token, count in tally.items()
                                  if token in ABSENT_DOOR_TOKENS)
    open_rows = sum(open_by_capture.values())
    published_entries = block["per_capture"]
    require(len(published_entries) == len(spatial["captures"]),
            "the disturbance block does not cover every capture in the report")
    for index, entry in enumerate(published_entries):
        cid = str(spatial["captures"][index]["capture"])
        if cid not in tally_by_capture:
            continue
        require(entry["evidence"]["door_open_token_tally"] == tally_by_capture[cid],
                f"the disturbance block for {cid} publishes tally "
                f"{entry['evidence']['door_open_token_tally']}, the CSV says "
                f"{tally_by_capture[cid]}")
    if open_rows == 0:
        require(block["status"] == "NOT_COMPUTABLE",
                "no door-open row exists in the capture, so a computed disturbance "
                "response is fabricated")
        require(spatial["verdict"]["disturbance_response_computed"] is False,
                "the verdict says a disturbance response was computed with no event")
        for entry in published_entries:
            require("invent" in entry["reason"] or "never OPEN" in entry["reason"],
                    "NOT_COMPUTABLE must say why in the artifact, not only in prose")
            require(bool(entry["what_would_make_it_computable"]),
                    "NOT_COMPUTABLE must name the measurement that would change it")
    else:
        require(block["status"] != "NOT_COMPUTABLE",
                "a door-open event is recorded but the report still says NOT_COMPUTABLE")


def check_session_labels() -> None:
    """One session stays one session, now and after the physical study succeeds."""
    spatial = load("spatial-statistics.json")
    for entry in spatial["captures"]:
        cid = str(entry["capture"])
        rows = rows_of(cid)
        if not rows:
            continue
        boots = BOOT_IDS[cid]
        require(entry["boot_ids"] == boots,
                f"spatial lists boot_ids {entry['boot_ids']} for {cid}, the capture holds "
                f"{boots}")
        require(entry["independent_sessions"] == len(boots),
                f"{cid} reports {entry['independent_sessions']} sessions from "
                f"{len(boots)} boot_id values")
    require(spatial["verdict"]["independent_sessions"] == SESSIONS,
            f"the spatial verdict's session count ({spatial['verdict']['independent_sessions']}) "
            f"does not match the {SESSIONS} boot_id values across the capture set")
    text = (DOSSIER / "spatial-statistics.json").read_text(encoding="utf-8")
    ablation_text = (DOSSIER / "ablation-support.json").read_text(encoding="utf-8")
    if SESSIONS == 1:
        # PHASE SNAPSHOT - MUST EVOLVE: required only while one session is on disk.
        for token, source in (("SINGLE_SESSION_OBSERVATION", text),
                              ("NOT_COMPUTABLE_AS_DISTRIBUTION", text),
                              ("distribution_computed\": false", text),
                              ("not_a_repeat_distribution", ablation_text)):
            require(token in source,
                    f"with one session the artifacts must still say {token!r}")
        require(spatial["verdict"]["single_session_observation"] is True,
                "one boot_id is reported as more than a single-session observation")
        require(spatial["verdict"]["distribution_computed"] is False,
                "one session is published as a computed distribution")
    else:
        require("SINGLE_SESSION_OBSERVATION" not in text,
                "the dossier still calls its figures single-session observations with "
                f"{SESSIONS} boots filed")
        require("not_a_repeat_distribution\": true" not in ablation_text,
                "the ablation verdict still refuses a repeat distribution it now has")


def check_qa_artifact() -> None:
    """The QA report must keep the verifiable and the unverifiable apart."""
    report = load("sensor-position-qa.json")
    for key in ("CURRENT_VERIFIABLE", "NEEDS_A_NEW_CAPTURE", "NEEDS_PHYSICAL_EVIDENCE"):
        require(key in report, f"sensor-position-qa.json lost the {key} block")
    require(report["verdict"]["movement_since_freeze"] == "NOT_VERIFIABLE_FROM_ARCHIVED_DATA",
            "the QA verdict may not call movement verifiable: archived frames carry no "
            "probe identity")
    cid = str(report["baseline_capture"]["capture"])
    rows = rows_of(cid)
    if not rows:
        return
    recomputed = qa.role_label_check(rows)
    published = report["baseline_capture"]["role_label_check"]
    require(published["state"] == recomputed["state"],
            f"QA publishes role state {published['state']!r}, the capture says "
            f"{recomputed['state']!r}")
    for column, block in published["per_column"].items():
        tokens = sorted({(row.get(column) or "COLUMN_ABSENT").strip() or "MISSING"
                         for row in rows})
        require(block["tokens"] == tokens,
                f"QA role column {column} lists {block['tokens']}, the capture holds {tokens}")
    driven = PHASE_ROWS[cid]["cooling"]
    rising = sorted(term for term in rep.AS_BUILT_ROLES
                    if float(driven[-1][term]) - float(driven[0][term]) > 0)
    signature = report["baseline_capture"]["behaviour_signature"]
    require(sorted(signature["rising_channel"]) == rising,
            f"QA says the rising channel is {signature['rising_channel']}, the rows say "
            f"{rising}")
    require(signature["consistent_with_hot_side_split"] is True,
            "the committed session does not actually show the hot-side/air split the "
            "frozen record describes")
    require(len(rising) == 1 and rising == ["t2_c"],
            "more than one channel rose while the bridge was driven: the geometry claim "
            "and the data disagree")
    for candidate in report["candidates"]:
        if candidate["same_capture_as_baseline"]:
            require("circular" in candidate.get("comparison_value", ""),
                    f"candidate {candidate['capture']} is the baseline itself and must "
                    "say the comparison is circular")
        require(candidate["role_label_check"]["state"] in ("MATCH", "MISMATCH", "COLUMN_ABSENT"),
                f"candidate {candidate['capture']} has an unparsable role state")
    require(len(report["NEEDS_A_NEW_CAPTURE"]["protocol"]) >= 3,
            "the QA method must ship the protocol a new capture has to meet")
    require(len(report["meaning_of_each_mismatch"]) >= 5,
            "every mismatch class must state what it would mean physically")
    for key, meaning in report["meaning_of_each_mismatch"].items():
        require(isinstance(meaning, str) and len(meaning) > 40,
                f"mismatch class {key} has no interpretable meaning")
    require(report["frozen_baseline"]["slot_to_position"] == dict(rep.AS_BUILT_ROLES),
            "the QA baseline drifted from the frozen role map")


def check_pairing_artifact() -> None:
    """Member A's input side stays an input: no value, no claimed agreement."""
    payload = load("pairing-input.json")
    try:
        pair.assert_no_invented_tolerance(payload)
    except rep.AnalysisError as error:
        FAILURES.append(f"pairing-input.json: {error}")
    require(payload["status"] == "TEAM_DEPENDENCY",
            f"pairing status is {payload['status']!r}; A-W14-04 is a joint decision")
    require(payload["tolerance_value"] is None and payload["tolerance_proposed"] is False,
            "pairing-input.json carries a tolerance; it is frozen with Member B")
    require(payload["verdict"]["physically_verified"] is False,
            "a host-side analysis may not be marked physically verified")
    primary = str(payload["captures"][0]["capture"])
    rows = rows_of(primary)
    unqualified = sum(1 for row in rows if rep.reading(row, "current_a")[1] == "unqualified")
    open_rows = sum(1 for row in rows
                    if (row.get("door_open") or "").strip() in ABSENT_DOOR_TOKENS)
    joined = " ".join(str(item) for item in payload["why_no_number"])
    for token in (f"independent thermal sessions on disk: {SESSIONS}",
                  f"{open_rows} of {len(rows)} rows",
                  f"no recorded status in this capture: {unqualified}"):
        require(token in joined,
                f"pairing-input.json no longer states the re-derived limit {token!r}")
    sensitivity = payload["what_the_real_data_supports"]["drop_one_feature_sensitivity"]
    require(sensitivity["status"] == "MEASURED_ON_ONE_SESSION",
            "the drop-one table must be labelled as one session's measurement")
    reference = sp.variant_phase_metrics(PHASE_ROWS[primary]["cooling"], "cooling",
                                         pair.AIR_VARIANT)
    require(sensitivity["reference_delta_c"] == reference["delta_c"],
            f"the drop-one reference ({sensitivity['reference_delta_c']}) is not the "
            f"capture's own {pair.AIR_VARIANT} cooling delta ({reference['delta_c']})")
    for entry in sensitivity["rows"]:
        require(entry["deviation_from_air3_delta_c"] ==
                round(entry["delta_c"] - sensitivity["reference_delta_c"], 4),
                f"drop-one deviation for {entry['variant']} does not match its own delta")
    air_worst = max(abs(float(entry["deviation_from_air3_delta_c"]))
                    for entry in sensitivity["rows"] if entry["is_chamber_air"])
    require(sensitivity["air_only_max_abs_deviation_c"] == round(air_worst, 4),
            "the air-only worst case is not the worst of the air rows")
    require(set(payload["join_keys_b_can_use"]) >= {"capture", "boot_id", "device_ms",
                                                    "conditioning_fingerprint", "variant",
                                                    "phase"},
            "the handoff lost a join key Member B needs")


IDENTIFICATION_CAPTURE_FILES = ("baseline.log", "decay_check.log", "live_check.log",
                                "settle_1.log", "touch_1.log", "touch_2.log")


def check_identification_excluded() -> None:
    """The touch session must not have crept into any W14 statistic."""
    for path in sorted(DOSSIER.iterdir()):
        if not path.is_file() or path.suffix not in GENERATED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name in IDENTIFICATION_CAPTURE_FILES:
            require(name not in text,
                    f"{path.name} cites the identification capture {name} as data; the "
                    "frozen record forbids reusing it for any thermal statistic")
        if "probe-identification" in text:
            require("PROBE_IDENTIFICATION" in text or "excluded" in text.lower()
                    or "refus" in text.lower() or "forbids" in text.lower(),
                    f"{path.name} names the identification record without stating its "
                    "exclusion")
    # DURABLE: the identification session is refused by what it is, not by its filename.
    boots = set(sp.IDENTIFICATION_BOOT_IDS)
    for cid, capture_boots in BOOT_IDS.items():
        require(not (boots & set(capture_boots)),
                f"{cid} carries the boot_id of the frozen PROBE_IDENTIFICATION session "
                "and must not be in the W14 capture set")


def _count_forms(count: int) -> tuple[str, ...]:
    """A corpus count as the prose may write it: 9570, "9 570", or with a thin space."""
    spaced = f"{count:,}".replace(",", " ")
    return (str(count), spaced, spaced.replace(" ", " "))


def check_handwritten_claims() -> None:
    """The prose a person wrote must quote numbers the tools actually produced.

    DURABLE: the docs quote the generated values, and the vocabulary labels stay in the
    sentences that refuse the claims. PHASE SNAPSHOT - MUST EVOLVE: *which* values those
    are. Not one figure below is a literal this file is allowed to know: each is read
    out of the artifact and capture that produced it, so when a second session lands and
    the headline moves, the docs are checked against the new number instead of failing
    for having been updated.
    """
    spatial = load("spatial-statistics.json")
    payload = load("pairing-input.json")
    primary = str(spatial["captures"][0]["capture"])
    cooling = spatial["captures"][0]["phases"]["cooling"]
    sensitivity = payload["what_the_real_data_supports"]["drop_one_feature_sensitivity"]
    matrix = load("ablation-support.json")
    hot_row = next((row for row in sensitivity["rows"]
                    if row["variant"] == pair.CANONICAL_LITERAL_VARIANT), None)
    texts = {name: (DOSSIER / name).read_text(encoding="utf-8")
             for name in ("README.md", "acceptance.md", "handoff.md")}
    quotes = {
        "air-to-air maximum": (str(cooling["air_gradient"]["max_pairwise_difference_c"]),
                               ("README.md", "acceptance.md", "handoff.md")),
        "air-versus-surface maximum": (
            str(cooling["phase_max_pairwise_difference_c"]),
            ("README.md", "acceptance.md", "handoff.md")),
        "reference delta": (str(sensitivity["reference_delta_c"]),
                            ("README.md", "acceptance.md")),
        "worst air deviation": (str(sensitivity["air_only_max_abs_deviation_c"]),
                               ("README.md", "acceptance.md")),
        "the hot side averaged into an air mean": (
            None if hot_row is None else str(abs(float(hot_row["deviation_from_air3_delta_c"]))),
            ("README.md", "acceptance.md", "handoff.md")),
        "the canonical literal's own delta": (
            None if hot_row is None else str(hot_row["delta_c"]), ("acceptance.md",)),
        "the conditioning fingerprint": (str(FINGERPRINTS[primary]), ("acceptance.md",)),
    }
    for label, (value, files) in quotes.items():
        if value is None:
            FAILURES.append(f"no {label} row exists in the generated artifacts, so the "
                            "docs that quote one are quoting nothing")
            continue
        for name in files:
            require(value in texts[name],
                    f"{name} no longer quotes {label} = {value!r}, the value the tools "
                    "produce for this capture set")
    for token, files in (("NOT_COMPUTABLE", ("README.md", "acceptance.md")),
                         ("TEAM_DEPENDENCY", ("README.md", "acceptance.md")),
                         ("NOT_VERIFIABLE_FROM_ARCHIVED_DATA", ("README.md", "acceptance.md")),
                         ("SINGLE_SESSION_OBSERVATION", ("README.md", "acceptance.md"))):
        for name in files:
            require(token in texts[name],
                    f"{name} no longer states {token!r}, the refusal the data forces")
    require(str(cooling["air_gradient"]["max_pairwise_difference_c"]) in texts["README.md"],
            "README.md's headline air gradient is not the generated value")
    require(str(sensitivity["air_only_max_abs_deviation_c"]) in texts["acceptance.md"],
            "acceptance.md's ablation figure is not the generated value")
    require("MUST EVOLVE" in texts["acceptance.md"],
            "acceptance.md no longer marks which claims are a PHASE SNAPSHOT that has "
            "to change as the physical study develops")


def check_generated_counts() -> None:
    """PHASE SNAPSHOT - MUST EVOLVE: the corpus counts quoted in prose are this set's.

    The row counts a reader trusts - the session's 957 rows, the 9 570 long-format rows
    - are derived here from the capture set and the published series. They are not
    literals: the second session makes them wrong, and a dossier that keeps stating the
    old count is a dossier describing a corpus it no longer has.
    """
    session_rows = sum(len(rows) for rows in CAPTURE_ROWS.values())
    csv_read = read_ablation_csv()
    long_rows = 0 if csv_read is None else len(csv_read[1])
    variant_count = len(matrix_variant_names())
    counts = {
        "README.md": ((session_rows, "the rows in the capture set"),
                      (long_rows, "the long-format series rows"),
                      (variant_count, "the ablation feature sets")),
        "handoff.md": ((long_rows, "the long-format series rows"),
                       (session_rows, "the rows in the capture set")),
        "acceptance.md": ((session_rows, "the rows in the capture set"),
                          (variant_count, "the ablation feature sets")),
    }
    for name, wanted in counts.items():
        text = (DOSSIER / name).read_text(encoding="utf-8")
        for count, what in wanted:
            if any(form in text for form in _count_forms(count)):
                continue
            FAILURES.append(f"{name} no longer states {what} as {count} (it writes "
                            f"{_count_forms(count)[0]!r} or its spaced form nowhere): a "
                            "count quoted from an older corpus describes data this "
                            "dossier does not hold")


def matrix_variant_names() -> list[str]:
    return list(load("ablation-support.json")["variants"])  # type: ignore[call-overload]


STATUS_VOCABULARY = {"IMPLEMENTED", "HOST_VERIFIED", "REAL_DATA_ANALYZED",
                    "PHYSICALLY_VERIFIED", "NEED_USER_ACTION", "TEAM_DEPENDENCY",
                    "BLOCKED_HARDWARE", "NOT_COMPUTABLE_AS_DISTRIBUTION"}


def check_status_vocabulary() -> None:
    """Only the sanctioned status words in the matrix, and nothing host-side physical.

    Scoped to the requirement-matrix rows and to underscored ALL-CAPS labels, because
    the risk worth catching is an invented *status*, not ordinary capitalised prose.
    A label the tools emit is allowed (it is machine-derived and re-checked elsewhere);
    a label no artifact produces can only have been written by hand.
    """
    text = (DOSSIER / "acceptance.md").read_text(encoding="utf-8")
    machine_text = "".join((DOSSIER / name).read_text(encoding="utf-8")
                           for name in DATA_ARTIFACTS + ("spatial-report.md",
                                                          "ablation-support.md",
                                                          "sensor-position-qa.md",
                                                          "member-b-handoff.md"))
    matrix = "\n".join(line for line in text.splitlines() if line.startswith("| **A-W14-"))
    require(len(matrix.splitlines()) == 4,
            "the acceptance matrix must carry exactly the four A-W14 rows to check "
            "statuses in it")
    for token in set(re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b", matrix)):
        require(token in STATUS_VOCABULARY or token in machine_text,
                f"acceptance.md's matrix uses the status-like label {token!r}, which no "
                "generated artifact produces")
    require("PHYSICALLY_VERIFIED" not in matrix,
            "nothing host-side may be called physically verified, least of all in the "
            "requirement matrix")
    for line in text.splitlines():
        if "PHYSICALLY_VERIFIED" in line:
            require("never" in line.lower() or "not" in line.lower(),
                    f"acceptance.md names PHYSICALLY_VERIFIED on line {line[:60]!r} "
                    "without stating that it is not earned here")


def main() -> int:
    check_pins()
    check_provenance_paths()
    check_no_false_claims()
    check_always_required()
    check_hot_side_containment()
    check_conditioning_provenance()
    check_ablation_row_attribution()
    check_variant_recompute()
    check_spatial_recompute()
    check_disturbance_honesty()
    check_session_labels()
    check_qa_artifact()
    check_pairing_artifact()
    check_identification_excluded()
    check_handwritten_claims()
    check_generated_counts()
    check_status_vocabulary()

    if FAILURES:
        print("W14 DOSSIER: FAIL")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print(f"W14 DOSSIER: OK (pins verify, every conditioning fingerprint and every "
          f"series row re-derives from the capture, no chamber-air mean carries the hot "
          f"side, {SESSIONS} session(s) labelled as what they are, the disturbance is "
          f"still NOT_COMPUTABLE, and no tolerance was invented)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
