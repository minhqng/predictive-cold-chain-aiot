"""W14 dossier validator: byte pins plus the honesty of every verdict.

Regenerating a report can only prove it reproduces; it cannot prove it still tells the
truth. This validator re-reads the captures themselves and re-checks the four claims
this week could most easily get wrong:

* a chamber-air statistic that averages the TEC hot-side surface (`t2_c`) - the flag
  must agree with the term list on every published row, not just in prose;
* one session's sample dispersion described as a distribution;
* a disturbance response for a door that was never opened, with the tally re-derived
  from the CSV rather than quoted;
* a pairing tolerance presented as agreed, adopted, final, or simply valued.

It also re-derives the sensor-position QA facts from the capture (role column tokens,
which channel rose while the bridge was driven) and re-computes every published variant
metric, so a doc that drifted from the data fails on the number, not on the sentence.

Two classes of check, kept apart deliberately: `ALWAYS_REQUIRED`-style checks are
DURABLE and hold however the physical study develops, while the single-session language
is a PHASE SNAPSHOT - MUST EVOLVE: it is only true while the dossier holds one thermal
session, so the validator requires it now and forbids it later.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

DOSSIER = pathlib.Path(__file__).resolve().parent
REPO = DOSSIER.parents[2]
sys.path.insert(0, str(REPO / "firmware" / "tools"))

import cg_thermal_repeatability as rep  # noqa: E402
import cg_w14_pairing as pair  # noqa: E402
import cg_w14_spatial as sp  # noqa: E402
import cg_w14_sensor_qa as qa  # noqa: E402

FAILURES: list[str] = []
H8_ID = "evidence/A/W04/tec-cooling-response-600s.csv"
H8_CAPTURE = REPO / H8_ID

# Durable: these hold however the physical study develops.
ALWAYS_REQUIRED = ("SINGLE_SESSION_OBSERVATION", "NOT_COMPUTABLE", "includes_hot_side",
                   "conditioning_fingerprint", "within_session", "PROBE_IDENTIFICATION",
                   "NEEDS_A_NEW_CAPTURE", "NEEDS_PHYSICAL_EVIDENCE", "TEAM_DEPENDENCY")
GENERATED_SUFFIXES = {".md", ".json", ".csv", ".jsonl"}
DATA_ARTIFACTS = ("spatial-statistics.json", "ablation-support.json",
                  "ablation-support.csv", "sensor-position-qa.json", "pairing-input.json")
ABSENT_DOOR_TOKENS = ("1", "OPEN", "TRUE")


def require(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def load(name: str) -> dict[str, object]:
    return json.loads((DOSSIER / name).read_text(encoding="utf-8"))


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


def check_provenance_paths() -> None:
    """No committed artifact may name a capture by a developer's absolute path."""
    offenders = re.compile(r"[A-Za-z]:[\\/]|/home/|/Users/|\\Users\\")
    for path in sorted(DOSSIER.rglob("*")):
        if not path.is_file() or path.suffix not in GENERATED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if offenders.search(line):
                FAILURES.append(f"{path.name} embeds an absolute capture path: "
                                f"{line.strip()[:100]!r}")


def check_no_false_claims() -> None:
    """The claims this week must not assert are checked in every generated artifact."""
    for path in sorted(DOSSIER.iterdir()):
        if not path.is_file() or path.suffix not in GENERATED_SUFFIXES:
            continue
        try:
            qa.assert_no_false_claim(path.name, path.read_text(encoding="utf-8"))
        except rep.AnalysisError as error:
            FAILURES.append(str(error))


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

    csv_text = (DOSSIER / "ablation-support.csv").read_text(encoding="utf-8")
    header = csv_text.splitlines()[0].split(",")
    rows = [line.split(",") for line in csv_text.splitlines()[1:]]
    require(len(rows) > 100, f"ablation-support.csv has only {len(rows)} data rows")
    for row in rows:
        record = dict(zip(header, row))
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


def check_variant_recompute() -> None:
    """Every published variant metric, recomputed from the capture, not trusted."""
    matrix = load("ablation-support.json")
    rows = rep.read_rows(H8_CAPTURE)
    phases = rep.split_phases(rows)
    for entry in matrix["captures"]:
        if entry["capture"] != H8_ID:
            FAILURES.append(f"ablation names {entry['capture']}, not the committed capture")
            continue
        for name, published in entry["variants"].items():
            for phase, metrics in published.items():
                if not metrics.get("usable"):
                    continue
                want = sp.variant_phase_metrics(phases[phase], phase, name)
                for key in ("samples", "delta_c", "min_c", "max_c",
                            "whole_phase_slope_c_per_min", "partial_term_rows",
                            "includes_hot_side", "is_chamber_air"):
                    require(want[key] == metrics[key],
                            f"ablation {name}/{phase} publishes {key}={metrics[key]}, the "
                            f"capture says {want[key]}")


def check_spatial_recompute() -> None:
    """Independent arithmetic on the raw rows for the headline gradient figures."""
    spatial = load("spatial-statistics.json")
    rows = rep.read_rows(H8_CAPTURE)
    driven = [row for row in rep.split_phases(rows)["cooling"]
              if all(rep.reading(row, term)[1] in ("ok", "unqualified")
                     for term in sp.AIR_TERMS)]
    naive = {}
    for index, a in enumerate(sp.AIR_TERMS):
        for b in sp.AIR_TERMS[index + 1:]:
            values = [round(float(row[a]) - float(row[b]), 4) for row in driven]
            naive[f"{a}-vs-{b}"] = round(max(abs(v) for v in values), 4)
    block = spatial["captures"][0]["phases"]["cooling"]["air_gradient"]
    published = {label.split(" (")[0]: pair["max_abs_c"]
                 for label, pair in block["pairs"].items()}
    for key, want in naive.items():
        require(published.get(key) == want,
                f"spatial air gradient {key} publishes {published.get(key)}, the rows "
                f"say {want}")
    require(block["tallies"]["usable_pairs"] == len(driven),
            f"spatial air gradient claims {block['tallies']['usable_pairs']} pairs, the "
            f"rows hold {len(driven)}")
    hot_max = max(abs(float(row["t2_c"]) - float(row[term]))
                  for row in driven for term in sp.AIR_TERMS)
    require(block["max_pairwise_difference_c"] < hot_max,
            "the air-only maximum is not smaller than the surface separation, so the "
            "two are not the blocks they claim to be")


def check_disturbance_honesty() -> None:
    """Re-read the door column; the response status has to follow the data."""
    rows = rep.read_rows(H8_CAPTURE)
    tally: dict[str, int] = {}
    for row in rows:
        token = (row.get("door_open") or "MISSING").strip() or "MISSING"
        tally[token] = tally.get(token, 0) + 1
    open_rows = sum(count for token, count in tally.items() if token in ABSENT_DOOR_TOKENS)
    spatial = load("spatial-statistics.json")
    block = spatial["disturbance_specific_response"]
    for entry in block["per_capture"]:
        require(entry["evidence"]["door_open_token_tally"] == tally,
                f"the disturbance block publishes tally "
                f"{entry['evidence']['door_open_token_tally']}, the CSV says {tally}")
    if open_rows == 0:
        require(block["status"] == "NOT_COMPUTABLE",
                "no door-open row exists in the capture, so a computed disturbance "
                "response is fabricated")
        require(spatial["verdict"]["disturbance_response_computed"] is False,
                "the verdict says a disturbance response was computed with no event")
        for entry in block["per_capture"]:
            require("invent" in entry["reason"] or "never OPEN" in entry["reason"],
                    "NOT_COMPUTABLE must say why in the artifact, not only in prose")
            require(bool(entry["what_would_make_it_computable"]),
                    "NOT_COMPUTABLE must name the measurement that would change it")
    else:
        require(block["status"] != "NOT_COMPUTABLE",
                "a door-open event is recorded but the report still says NOT_COMPUTABLE")


def check_session_labels() -> None:
    """One session stays one session, now and after the physical study succeeds."""
    rows = rep.read_rows(H8_CAPTURE)
    boots = sorted({row.get("boot_id", "") for row in rows})
    spatial = load("spatial-statistics.json")
    for entry in spatial["captures"]:
        require(entry["boot_ids"] == boots,
                f"spatial lists boot_ids {entry['boot_ids']}, the capture holds {boots}")
        require(entry["independent_sessions"] == len(boots),
                f"{entry['capture']} reports {entry['independent_sessions']} sessions "
                f"from {len(boots)} boot_id values")
    require(spatial["verdict"]["independent_sessions"] == len(boots),
            "the spatial verdict's session count does not match the captures")
    text = (DOSSIER / "spatial-statistics.json").read_text(encoding="utf-8")
    ablation_text = (DOSSIER / "ablation-support.json").read_text(encoding="utf-8")
    if len(boots) == 1:
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
                "multiple boots filed")
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
    rows = rep.read_rows(H8_CAPTURE)
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
    driven = rep.split_phases(rows)["cooling"]
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
    rows = rep.read_rows(H8_CAPTURE)
    unqualified = sum(1 for row in rows if rep.reading(row, "current_a")[1] == "unqualified")
    boots = {row.get("boot_id", "") for row in rows}
    open_rows = sum(1 for row in rows
                    if (row.get("door_open") or "").strip() in ABSENT_DOOR_TOKENS)
    joined = " ".join(payload["why_no_number"])
    for token in (f"independent thermal sessions on disk: {len(boots)}",
                  f"{open_rows} of {len(rows)} rows",
                  f"no recorded status in this capture: {unqualified}"):
        require(token in joined,
                f"pairing-input.json no longer states the re-derived limit {token!r}")
    sensitivity = payload["what_the_real_data_supports"]["drop_one_feature_sensitivity"]
    require(sensitivity["status"] == "MEASURED_ON_ONE_SESSION",
            "the drop-one table must be labelled as one session's measurement")
    require(sensitivity["reference_delta_c"] == -8.7083,
            f"the ablation reference moved from W07's published -8.7083 to "
            f"{sensitivity['reference_delta_c']}")
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


def check_handwritten_claims() -> None:
    """The prose a person wrote must quote numbers the tools actually produced."""
    spatial = load("spatial-statistics.json")
    payload = load("pairing-input.json")
    cooling = spatial["captures"][0]["phases"]["cooling"]
    sensitivity = payload["what_the_real_data_supports"]["drop_one_feature_sensitivity"]
    headline = {
        "1.126": ("README.md", "acceptance.md"),
        "18.938": ("README.md", "acceptance.md"),
        "-8.7083": ("README.md", "acceptance.md"),
        "0.5833": ("README.md", "acceptance.md"),
        "6.1456": ("acceptance.md",),
        "NOT_COMPUTABLE": ("README.md", "acceptance.md"),
        "TEAM_DEPENDENCY": ("README.md", "acceptance.md"),
        "NOT_VERIFIABLE_FROM_ARCHIVED_DATA": ("README.md", "acceptance.md"),
    }
    texts = {name: (DOSSIER / name).read_text(encoding="utf-8")
             for name in ("README.md", "acceptance.md")}
    for token, files in headline.items():
        for name in files:
            require(token in texts[name],
                    f"{name} no longer quotes {token!r}, a number the tools produced")
    require(str(cooling["air_gradient"]["max_pairwise_difference_c"]) in texts["README.md"],
            "README.md's headline air gradient is not the generated value")
    require(str(sensitivity["air_only_max_abs_deviation_c"]) in texts["acceptance.md"],
            "acceptance.md's ablation figure is not the generated value")


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
    check_hot_side_containment()
    check_variant_recompute()
    check_spatial_recompute()
    check_disturbance_honesty()
    check_session_labels()
    check_qa_artifact()
    check_pairing_artifact()
    check_identification_excluded()
    check_handwritten_claims()
    check_status_vocabulary()

    if FAILURES:
        print("W14 DOSSIER: FAIL")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("W14 DOSSIER: OK (pins verify, no chamber-air mean carries the hot side, one "
          "session is still one session, the disturbance is still NOT_COMPUTABLE, and no "
          "tolerance was invented)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
