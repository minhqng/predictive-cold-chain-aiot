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


def _status_clause(status: str) -> str:
    """Say what the recorded status is, rather than asserting today's emptiness forever."""
    if status == "":
        return "`current_status` is an **empty cell, not OK**"
    return f"`current_status` is `{status}` - a recorded value this dossier must report as-is"


def _electrical_status_summary(rows: list[dict[str, str]]) -> str:
    """Describe the electrical status fields as this capture actually records them.

    Hardcoding "empty in all rows" was a snapshot of today's defect presented as
    provenance: a future capture with recorded statuses would regenerate a report that
    stated the opposite of what its own rows contain, and the prose check would still
    pass because it looked for that sentence.
    """
    parts: list[str] = []
    for key in ("current_status", "voltage_status"):
        empty = sum(1 for row in rows if not (row.get(key) or "").strip())
        parts.append(f"{key} empty in {empty}/{len(rows)} rows")
    for column in ("power_w", "energy_wh"):
        if not any(f"{column}_status" in row for row in rows):
            parts.append(f"{column} has no status column")
    return "; ".join(parts)


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
        "electrical_status_columns": _electrical_status_summary(rows),
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


# What makes the frame anomalous is its measurements not moving while its command
# did, so the two field groups are compared and reported separately on purpose.
MEASURED_FIELDS = ("voltage_v", "voltage_status", "current_a", "current_status",
                   "power_w", "energy_wh",
                   "t1_c", "t1_status", "t2_c", "t2_status",
                   "t3_c", "t3_status", "t4_c", "t4_status")
COMMAND_FIELDS = ("state", "pwm_req_permille", "pwm_applied_permille")


def _suspect_frame() -> dict[str, object] | None:
    """The zero-duty nonzero-current frame, quoted rather than summarised away.

    Returns None when the capture has no such frame: `SUSPECT_DEVICE_MS` names a specific
    recorded sample, and a generator that asserts on it would abort the whole dossier for a
    future capture that no longer contains it.
    """
    rows = rep.read_rows(H8_CAPTURE)
    for row in rows:
        if row.get("device_ms") != str(SUSPECT_DEVICE_MS):
            continue
        neighbours = [r for r in rows
                      if r["device_ms"] in {str(SUSPECT_DEVICE_MS - 2000),
                                            str(SUSPECT_DEVICE_MS - 1000)}]
        # The frames AFTER the suspect one decide how it should be read. Quoting the
        # frame alone made it look like current persisted at zero duty; it does not, and
        # the record has to show the decay rather than leave the reader to assume it.
        off_tail: list[dict[str, object]] = []
        for r in rows:
            if int(r.get("device_ms", "-1")) <= SUSPECT_DEVICE_MS:
                continue
            if rep.number(r, "pwm_applied_permille") != 0.0:
                break
            off_tail.append({"device_ms": int(r["device_ms"]),
                             "current_a": r.get("current_a", ""),
                             "power_w": r.get("power_w", ""),
                             "voltage_v": r.get("voltage_v", "")})
            if len(off_tail) >= 5:
                break
        sequence = [row.get("current_a", "")] + [s["current_a"] for s in off_tail]
        zero_at = next((s["device_ms"] for s in off_tail if s["current_a"] in ("0.0", "0")),
                       None)
        differing = sorted({k for n in neighbours for k in MEASURED_FIELDS
                            if n.get(k) != row.get(k)})
        identical = [n for n in neighbours
                     if all(n.get(k) == row.get(k) for k in MEASURED_FIELDS)]
        agreement = (f"all {len(MEASURED_FIELDS)} measured fields match "
                     f"{len(identical)} of the {len(neighbours)} preceding frames"
                     if not differing else
                     f"measured fields differ from the preceding frames on {differing}")
        return {
            "device_ms": SUSPECT_DEVICE_MS,
            "fields": {k: row.get(k, "") for k in MEASURED_FIELDS + COMMAND_FIELDS},
            "measured_fields_compared": list(MEASURED_FIELDS),
            "preceding_frames_identical_on_all_measured_fields": len(identical),
            "differing_measured_fields": differing,
            "command_and_state_fields": {
                k: {"preceding": [n.get(k, "") for n in neighbours],
                    "suspect": row.get(k, "")} for k in COMMAND_FIELDS},
            "operator_confirmed_zero_duty_current_sequence_a": sequence,
            "frames_after_suspect": off_tail,
            "current_returns_to_zero_at_device_ms": zero_at,
            "measurement_vs_verification": (
                "PZEM-reported values only. No independent instrument read this branch, so "
                "the decay describes what the meter showed, not proof that the branch carried "
                "no current - the two must not be conflated"),
            "canonical_candidate": ("docs/01 22.4 'Commanded OFF + unexpected current' names "
                                    "CONTROL_ELECTRICAL_ANOMALY, high severity, and 23.4 lists "
                                    "'current while state should be OFF' as its example"),
            "competing_explanation": ("register/transition lag on the PZEM side. Two committed "
                                      "observations support it: evidence/A/W04/README.md records "
                                      "the first PZEM sample after START still returning pre-run "
                                      "registers, and after this frame the applied duty stays 0 "
                                      "while the reading falls "
                                      f"{' -> '.join(str(s) for s in sequence)} A, reaching "
                                      f"{'0 at device_ms ' + str(zero_at) if zero_at else 'no zero reading in the captured tail'}"
                                      ". That is a decaying tail, not sustained energization - "
                                      "but it is a meter trace, not a verified zero-current "
                                      "measurement, so it weakens the anomaly reading without "
                                      "closing it"),
            "reading": (f"applied duty `{row.get('pwm_applied_permille', '')}` and requested "
                        f"duty `{row.get('pwm_req_permille', '')}` in state "
                        f"`{row.get('state', '')}`, yet the row carries "
                        f"`{row.get('current_a', '')} A` and `{row.get('power_w', '')} W`; "
                        f"{_status_clause(row.get('current_status', ''))} and {agreement}, "
                        f"so the readings did not move when "
                        f"the duty did. Naming this CONTROL_ELECTRICAL_ANOMALY is a safety "
                        f"classification and not a host tool's call, so it is recorded as the "
                        f"canonical candidate for the next supervised session; the frame stays "
                        f"inside the recovery segment's published peak, where the report names "
                        f"it instead of averaging it away"),
        }
    return None


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
        rep.overlay_rows([analyses[name] for name in (PRIMARY, *COMPARATORS)]))
    files["repeatability-overlay.csv"] = buffer.getvalue()

    for phase, filename in PHASE_FILE.items():
        entries = _registry(analyses[PRIMARY], phase)
        files[filename] = "".join(json.dumps(entry, sort_keys=True) + "\n"
                                  for entry in entries)

    files["reset-criterion-evaluation.json"] = json.dumps(_criterion_evidence(),
                                                          indent=2,
                                                          sort_keys=True) + "\n"
    files["repeatability-report.md"] = _report(analyses, _suspect_frame())
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


def _slope_relationship_sentence(phases: dict[str, dict[str, object]]) -> str:
    """Say what the two slope columns measured, derived from the numbers themselves.

    This paragraph used to read "the trailing-window slope is positive during cooling on
    purpose" as a hardcoded literal, while the table printed three lines above it said
    -0.070104 - so the dossier's own prose contradicted its own evidence, and the example
    it was meant to give of slope discipline was the thing that was wrong. No sign or
    magnitude may be asserted here that the run did not produce.
    """
    run = phases.get("cooling", {}).get("runs", [{}])[0]
    trailing = run.get("slope_c_per_min")
    whole = run.get("whole_phase_slope_c_per_min")
    if trailing is None or whole is None:
        return ("One of the two slope definitions is uncomputed for the only cooling "
                "segment, so they are published without comparison.")
    if abs(trailing) < abs(whole):
        comparison = "shallower than"
    elif abs(trailing) > abs(whole):
        comparison = "steeper than"
    else:
        comparison = "the same size as"
    return (
        f"The two slope columns answer different questions and are not two estimates of "
        f"one. In the only cooling segment the trailing window measures {trailing} C/min, "
        f"which is {comparison} the whole phase at {whole} C/min, so it reports recent "
        f"motion rather than the response. Neither value is \"the cooling slope\": the "
        f"phase answer is `whole_phase_slope_c_per_min`, and the comparison is computed "
        f"(`trailing_differs_from_whole_phase`) rather than asserted, so a future run in "
        f"which the two agree will say so.")


def _report(analyses: dict[str, dict[str, object]], suspect: dict[str, object]) -> str:
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
    lines += ["", _slope_relationship_sentence(phases), "", "### Electrical figures", ""]
    cooling = phases["cooling"]["runs"][0]
    recovery = phases.get("recovery", {}).get("runs", [{}])[0]
    suspect_block = ([
        f"Suspect frame (`device_ms={SUSPECT_DEVICE_MS}`): {suspect['reading']}.",
        "",
        f"- canonical candidate: {suspect['canonical_candidate']}",
        f"- competing explanation: {suspect['competing_explanation']}",
        f"- comparison actually performed: `{len(suspect['measured_fields_compared'])}` "
        f"measured fields, "
        f"`{suspect['preceding_frames_identical_on_all_measured_fields']}` of "
        f"`{len(suspect['command_and_state_fields']['state']['preceding'])}` preceding "
        f"frames identical on all of them, differing on "
        f"`{suspect['differing_measured_fields'] or 'none'}`",
        "",
    ] if suspect else [
        "No frame in this capture carries a non-zero current with applied duty 0, so there "
        "is no suspect frame to quote. A future capture that has one must name it rather "
        "than let it raise the segment peak silently.",
        "",
    ])
    lines += [
        f"- driven block: mean current `{cooling['mean_current_a']} A`, peak "
        f"`{cooling['peak_current_a']} A`, mean power `{cooling['mean_power_w']} W`, "
        f"energy delta `{cooling['energy_wh']} Wh`",
        f"- recovery segment: peak current `{recovery.get('peak_current_a')} A` — "
        f"**that peak is the single suspect frame below**, not evidence of current "
        f"after the bridge opened",
        f"- electrical qualification: {cooling['electrical_status_note']} "
        f"(`electrical_rows_unqualified: {cooling['electrical_rows_unqualified']}`, "
        f"`electrical_status_recorded: "
        f"{str(cooling['electrical_status_recorded']).lower()}`), so values that nothing "
        f"checked are never presented as status-checked",
        "",
        *suspect_block,
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
