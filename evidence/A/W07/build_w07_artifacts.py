"""Generate every W07 artifact from the delivered analysis tools and real captures.

Run with ``--check`` to verify the committed files still reproduce byte-for-byte.

Nothing here is typed by hand: the numbers come from
``firmware/tools/cg_thermal_repeatability.py`` and
``firmware/tools/cg_reset_criterion.py`` reading captures that are already
committed. The generator also refuses to write a report that claims repeatability
was established, or that marks any run physically verified, because with the runs
this repository holds it cannot.

Phase registries are kept separate - `warmup-runs.jsonl` holds passive baseline
segments only, `cooling-step-runs.jsonl` driven blocks only, and
`recovery-runs.jsonl` post-action segments - because a recovery rebound is not a
warm-up run and the counts feed a requirement that asks for repetitions of each.
"""

from __future__ import annotations

import csv
import io
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "firmware" / "tools"))

import cg_reset_criterion as criterion  # noqa: E402
import cg_thermal_repeatability as rep  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
H8_CAPTURE = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
CRITERION = HERE / "reset-criterion-v0.yaml"

MIN_RUNS = 3
PRIMARY = "tmean_airroles_v0"
COMPARATORS = ("tmean_chamber3_v0", "tmean_t2excluded_v0", "tmean_all4_v0")
PHASE_FILE = {"baseline": "warmup-runs.jsonl", "cooling": "cooling-step-runs.jsonl",
              "recovery": "recovery-runs.jsonl"}
PHASE_LABEL = {"baseline": "passive warm-up segment",
               "cooling": "cooling step",
               "recovery": "post-action recovery segment"}
# One frame in the recovery segment carries current while applied duty is 0 and is
# byte-identical to the two preceding driven frames. It is named, not averaged in.
SUSPECT_DEVICE_MS = 826894


def _provenance(path: pathlib.Path) -> dict[str, object]:
    rows = rep.read_rows(path)
    first = rows[0]
    return {
        "capture": path.relative_to(REPO).as_posix(),
        "session": first.get("session", "UNRECORDED"),
        "boot_id": first.get("boot_id", "UNRECORDED"),
        "rows": len(rows),
        "device_ms_first": first.get("device_ms"),
        "device_ms_last": rows[-1].get("device_ms"),
        "limits_policy": first.get("limits_policy", "UNRECORDED"),
        "fan_field": first.get("fan", "UNRECORDED"),
        "door_field_values": sorted({(row.get("door_open") or "MISSING") or "MISSING"
                                     for row in rows}),
        "electrical_status_columns": "current_status/voltage_status empty in all rows",
    }


def _registry(report: dict[str, object], phase: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for run in report["runs"]:
        metrics = run["phases"].get(phase)
        if not metrics or not metrics.get("usable"):
            continue
        entry: dict[str, object] = {
            "phase": phase,
            "label": PHASE_LABEL[phase],
            "independent_session": False,
            "note": ("this segment shares its boot_id with the other phases of the same "
                     "capture, so it is not an independent repetition"),
        }
        entry.update({k: v for k, v in metrics.items() if k != "phase"})
        entry["provenance"] = _provenance(rep.capture_path(str(run["capture"])))
        entries.append(entry)
    return entries


def _suspect_frame() -> dict[str, object]:
    """The zero-duty nonzero-current frame, quoted rather than summarised away."""
    rows = rep.read_rows(H8_CAPTURE)
    for row in rows:
        if row.get("device_ms") == str(SUSPECT_DEVICE_MS):
            keys = ("device_ms", "stage", "state", "pwm_req_permille",
                    "pwm_applied_permille", "current_a", "current_status", "power_w",
                    "energy_wh", "t1_c", "t2_c", "t3_c", "t4_c")
            neighbours = [r for r in rows
                          if r["device_ms"] in {str(SUSPECT_DEVICE_MS - 2000),
                                                str(SUSPECT_DEVICE_MS - 1000)}]
            identical = [n for n in neighbours
                         if all(n.get(k) == row.get(k) for k in
                                ("current_a", "power_w", "energy_wh", "t1_c", "t2_c"))]
            return {
                "device_ms": SUSPECT_DEVICE_MS,
                "fields": {k: row.get(k, "") for k in keys},
                "preceding_frames_byte_identical_on_electrical_and_thermal":
                    len(identical),
                "current_status_value": repr(row.get("current_status", "")),
                "reading": ("state=COOLDOWN with applied duty 0 yet current 7.15 A; "
                            "current_status is an empty cell, not OK, and the electrical "
                            "and thermal fields repeat the two preceding driven frames "
                            "exactly - consistent with documented PZEM register holdover, "
                            "so it is recorded as an observation to confirm on the next "
                            "supervised session and excluded from no statistic silently"),
            }
    raise AssertionError(f"suspect frame device_ms={SUSPECT_DEVICE_MS} not found")


def build() -> dict[str, str]:
    if not H8_CAPTURE.is_file():
        raise SystemExit(f"missing required capture: {H8_CAPTURE}")

    analyses = {name: rep.analyze([H8_CAPTURE], name, MIN_RUNS)
                for name in (PRIMARY, *COMPARATORS)}

    files: dict[str, str] = {}
    for name, report in analyses.items():
        files[f"repeatability-{name}.json"] = (
            json.dumps(report, indent=2, sort_keys=True) + "\n")

    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(
        rep.overlay_rows([analyses[PRIMARY], analyses["tmean_chamber3_v0"],
                          analyses["tmean_t2excluded_v0"]]))
    files["repeatability-overlay.csv"] = buffer.getvalue()

    for phase, filename in PHASE_FILE.items():
        entries = _registry(analyses[PRIMARY], phase)
        files[filename] = "".join(json.dumps(entry, sort_keys=True) + "\n"
                                  for entry in entries)

    files["reset-criterion-evaluation.json"] = json.dumps(_criterion_evidence(),
                                                          indent=2,
                                                          sort_keys=True) + "\n"
    files["repeatability-report.md"] = _report(analyses)
    for name, text in files.items():
        _guard(name, text)
    return files


def _criterion_evidence() -> dict[str, object]:
    """Run the shipped candidate against real rows, and against a labelled injection."""
    criteria = criterion.load_criteria(CRITERION)
    definition = criterion.parameter(criteria, "tmean_definition")[0]
    rows = rep.split_phases(rep.read_rows(H8_CAPTURE))
    driven = next(row for row in rows["cooling"]
                  if (rep.number(row, "pwm_applied_permille") or 0.0) > 0.0)
    observed = criterion.state_from_capture_row(driven, definition)
    shipped = criterion.evaluate(criteria, observed)

    injected = criterion.load_criteria(CRITERION)
    for entry in injected["parameters"]:
        if entry["name"] == "tmean_band_c":
            entry["value"], entry["status"] = "31.5", "PROPOSED"
        if entry["name"] == "gradient_bound_c_per_min":
            entry["value"], entry["status"] = "0.50", "PROPOSED"
    state = dict(observed, slope_c_per_min=0.0)
    return {
        "criteria_file": criterion.CRITERION_SCHEMA,
        "criterion_status": criteria["status"],
        "observed_state": observed,
        "shipped_candidate": shipped,
        "with_test_injected_numbers": {
            "note": ("31.5 C and 0.50 C/min were injected to prove the evaluator can "
                     "reach READY; they are not project thresholds, no document may "
                     "quote them as such, and the shipped file keeps both gates "
                     "UNRESOLVED"),
            "injection": {"tmean_band_c": "31.5", "gradient_bound_c_per_min": "0.50"},
            "result": criterion.evaluate(injected, state),
        },
        "hot_side_representation_refused": criterion.evaluate(
            criteria, dict(observed, representation="tmean_chamber3_v0")),
        "suspect_frame": _suspect_frame(),
    }


def _stat_row(block: dict[str, object], outcome: str) -> str:
    stats = block["statistics"][outcome]
    if stats["status"] != "OK":
        return (f"| {outcome} | 0 | - | - | - | - | - | no run of this phase produced "
                f"this outcome |")
    return (f"| {outcome} | {stats['n']} | {stats['mean']} | {stats['sd_sample']} | "
            f"{stats['cv_pct']} | {stats['min']} | {stats['max']} | "
            f"{stats.get('cv_note', '')} |")


def _report(analyses: dict[str, dict[str, object]]) -> str:
    primary = analyses[PRIMARY]
    phases = primary["phases"]
    lines = [
        "# W07 repeatability report",
        "",
        "Generated by `evidence/A/W07/build_w07_artifacts.py` from committed captures. "
        "Every number reproduces with the commands in `README.md`; nothing was measured "
        "for this report.",
        "",
        f"Primary representation: `{PRIMARY}` = mean of the as-built chamber-air probes "
        "(T1 centre, T3 bottom, T4 near door), per the operator-frozen geometry in "
        "`probe-identification-v0.md`. `includes_hot_side: false`.",
        "",
        "## Verdict",
        "",
        "**NOT ESTABLISHED — insufficient independent runs.** The analysis exists; the "
        "captures do not.",
        "",
        f"- cooling-step runs: `{primary['verdict']['cooling_step_runs']}`",
        f"- passive warm-up runs: `{primary['verdict']['passive_warmup_runs']}`",
        f"- plant variation reportable: `{primary['verdict']['plant_variation_reportable']}`",
        f"- undetermined rows (no usable applied duty): "
        f"`{primary['verdict']['undetermined_rows_total']}`",
        f"- A-W07-02/03 require {MIN_RUNS} valid runs of each kind",
        "",
        "## What the one available run shows",
        "",
        f"Every value below is `{PRIMARY}`. Slope columns name their own definition: "
        f"`{primary['slope_definition']}` for trailing motion and "
        f"`{primary['whole_phase_slope_definition']}` for the phase as a whole.",
        "",
        "| phase | samples / rows read | skipped | partial-term | duration min | "
        "delta C | trailing slope C/min | whole-phase slope C/min | 1 C at min |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for phase in ("baseline", "cooling", "recovery"):
        block = phases.get(phase)
        if not block:
            lines.append(f"| {phase} | - | - | - | - | - | - | - | no usable segment |")
            continue
        run = block["runs"][0]
        lines.append(
            f"| {PHASE_LABEL[phase]} | {run['samples']} / {run['rows_read']} | "
            f"{run['skipped_rows']} | {run['partial_term_rows']} | "
            f"{run['duration_min']} | {run['delta_c']} | {run['slope_c_per_min']} | "
            f"{run['whole_phase_slope_c_per_min']} | {run['minutes_to_1c']} |")
    lines += [
        "",
        "The trailing-window slope is positive during cooling on purpose: the chamber",
        "mean bottoms out and starts rebounding inside the driven block, so the last",
        "120 samples measure recent motion, not the response. Both numbers are",
        "published under their own definitions and neither is called \"the cooling",
        "slope\".",
        "",
        "### Electrical figures",
        "",
    ]
    cooling = phases["cooling"]["runs"][0]
    recovery = phases.get("recovery", {}).get("runs", [{}])[0]
    lines += [
        f"- driven block: mean current `{cooling['mean_current_a']} A`, peak "
        f"`{cooling['peak_current_a']} A`, mean power `{cooling['mean_power_w']} W`, "
        f"energy delta `{cooling['energy_wh']} Wh`",
        f"- recovery segment: peak current `{recovery.get('peak_current_a')} A` — "
        f"**that peak is the single suspect frame below**, not evidence of current "
        f"after the bridge opened",
        f"- `current_status`/`voltage_status` are empty in all "
        f"{cooling['rows_read']} rows read (`electrical_status_recorded: "
        f"{str(cooling['electrical_status_recorded']).lower()}`), so these are values "
        f"with no recorded validity and are never presented as status-checked",
        "",
        f"Suspect frame (`device_ms={SUSPECT_DEVICE_MS}`): state `COOLDOWN`, "
        f"requested and applied duty `0`, current `7.15 A`, power `84.2 W`, "
        f"`current_status` an **empty cell, not OK**, and its electrical and thermal "
        f"fields byte-identical to the two preceding driven frames. Read as documented "
        f"PZEM register holdover, recorded as an observation for the next supervised "
        f"session, and not interpreted as current flowing with the bridge off.",
        "",
        "## The representation question, measured",
        "",
        "Same single run, four definitions:",
        "",
        "| representation | terms | roles | includes hot side | delta C | "
        "whole-phase slope C/min | 1 C at min |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in (PRIMARY, *COMPARATORS):
        block = analyses[name]["phases"].get("cooling")
        if not block:
            continue
        run = block["runs"][0]
        lines.append(f"| `{name}` | {', '.join(analyses[name]['representation_terms'])} | "
                     f"{', '.join(analyses[name]['representation_roles'])} | "
                     f"{analyses[name]['includes_hot_side']} | {run['delta_c']} | "
                     f"{run['whole_phase_slope_c_per_min']} | {run['minutes_to_1c']} |")
    air = analyses[PRIMARY]["phases"]["cooling"]["runs"][0]["delta_c"]
    canon = analyses["tmean_chamber3_v0"]["phases"]["cooling"]["runs"][0]["delta_c"]
    lines += [
        "",
        f"The docs/01 §20.1 literal mean(T1,T2,T3) measures `{canon}` C where the",
        f"as-built chamber-air mean measures `{air}` C — a factor of",
        f"{abs(air) / abs(canon):.2f}. T2 is on the hot side, rises while the air",
        "probes fall, and averaging it into an air temperature flattens the response",
        "the chamber actually produced.",
        "",
        "This is stated as measured disagreement between named definitions. The",
        "physical geometry is operator-final and is not reopened here; the logical",
        "T1/T2/T3 naming in docs/01 remains a project decision, and no silent",
        "firmware remap is proposed.",
        "",
        "## Statistics",
        "",
        "Sample (n-1) spread. With n=1 the spread columns are empty by construction:",
        "one run has no dispersion, and inventing a variance would be the exact thing",
        "this week must not do. Outcomes no run produced are listed as NO_SAMPLES",
        "rather than dropped from the table.",
        "",
        "| phase | outcome | n | mean | sd (sample) | CV % | min | max | note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for phase, block in sorted(phases.items()):
        for outcome in rep.OUTCOMES:
            lines.append(f"| {phase} " + _stat_row(block, outcome))
    lines += [
        "",
        "## Reproduce",
        "",
        "```bash",
        "py firmware/tools/run_all_checks_w07.py",
        "py evidence/A/W07/build_w07_artifacts.py --check",
        f"py firmware/tools/cg_thermal_repeatability.py {H8_CAPTURE.relative_to(REPO).as_posix()} --representation {PRIMARY}",
        "```",
        "",
    ]
    return "\n".join(lines)


def _guard(name: str, text: str) -> None:
    """No generated artifact may claim more than host analysis of old captures."""
    lowered = text.lower()
    for token in ("physically verified", "repeatability established", "physical pass",
                  "verdict=pass", "bench pass"):
        if token in lowered:
            raise SystemExit(f"refusing to write {name}: it would claim {token!r}")
    if "independent_session" in lowered and '"independent_session": true' in lowered:
        raise SystemExit(f"refusing to write {name}: one boot_id is not independent")


def check_or_write(files: dict[str, str], write: bool) -> int:
    failures = []
    for name, text in sorted(files.items()):
        path = HERE / name
        if write:
            path.write_bytes(text.encode("utf-8"))
            print(f"wrote {name} ({len(text.encode('utf-8'))} bytes)")
        elif not path.is_file():
            failures.append(f"missing {name}")
        elif path.read_bytes() != text.encode("utf-8"):
            failures.append(f"differs: {name}")
    if failures:
        print("W07 ARTIFACTS: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    if not write:
        print(f"W07 ARTIFACTS OK ({len(files)} files reproduce from the tools and "
              f"captures)")
    return 0


if __name__ == "__main__":
    sys.exit(check_or_write(build(), "--check" not in sys.argv))
