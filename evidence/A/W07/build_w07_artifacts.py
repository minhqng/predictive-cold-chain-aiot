"""Generate every W07 artifact from the delivered analysis tools and real captures.

Run with ``--check`` to verify the committed files still reproduce byte-for-byte.

Nothing here is typed by hand: the numbers come from
``firmware/tools/cg_thermal_repeatability.py`` and
``firmware/tools/cg_reset_criterion.py`` reading captures that are already
committed. The generator also refuses to write a report that claims repeatability
was established, or that marks any run physically verified, because with the runs
this repository holds it cannot.
"""

from __future__ import annotations

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
PHASE_LABEL = {
    "baseline": "passive warm-up segment",
    "cooling": "cooling step",
    "recovery": "post-action recovery",
}


def _provenance(path: pathlib.Path) -> dict[str, object]:
    rows = rep.read_rows(path)
    first = rows[0]
    return {
        "capture": str(path.relative_to(REPO).as_posix()),
        "session": first.get("session", "UNRECORDED"),
        "boot_id": first.get("boot_id", "UNRECORDED"),
        "rows": len(rows),
        "device_ms_first": first.get("device_ms"),
        "device_ms_last": rows[-1].get("device_ms"),
        "limits_policy": first.get("limits_policy", "UNRECORDED"),
        "physical_output_field": first.get("physical_output", ""),
        "fan_field": first.get("fan", "UNRECORDED"),
    }


def _registry(report: dict[str, object], phase: str) -> list[dict[str, object]]:
    """One line per usable run segment of one phase, with its own provenance."""
    entries: list[dict[str, object]] = []
    for run in report["runs"]:
        metrics = run["phases"].get(phase)
        if not metrics or not metrics.get("usable"):
            continue
        entry = {"phase": phase, "label": PHASE_LABEL[phase],
                 "representation": report["representation"],
                 "independent_session": False,
                 "note": ("this segment comes from the same boot_id as the cooling step, "
                          "so it is not an independent repetition")}
        entry.update({key: value for key, value in metrics.items() if key != "phase"})
        entry["provenance"] = _provenance(pathlib.Path(run["capture"]))
        entries.append(entry)
    return entries


def build() -> dict[str, str]:
    if not H8_CAPTURE.is_file():
        raise SystemExit(f"missing required capture: {H8_CAPTURE}")

    files: dict[str, str] = {}
    analyses = {}
    for representation in ("tmean_chamber3_v0", "tmean_t2excluded_v0"):
        analyses[representation] = rep.analyze([H8_CAPTURE], representation, MIN_RUNS)

    for representation, report in analyses.items():
        slug = representation.replace("_v0", "")
        files[f"repeatability-{slug}.json"] = json.dumps(report, indent=2,
                                                         sort_keys=True) + "\n"

    import csv as csv_module
    import io

    buffer = io.StringIO()
    csv_module.writer(buffer, lineterminator="\n").writerows(
        rep.overlay_rows(analyses["tmean_chamber3_v0"]))
    files["repeatability-overlay.csv"] = buffer.getvalue()

    chamber3 = analyses["tmean_chamber3_v0"]
    files["cooling-step-runs.jsonl"] = "".join(
        json.dumps(entry, sort_keys=True) + "\n" for entry in _registry(chamber3, "cooling"))
    files["warmup-runs.jsonl"] = "".join(
        json.dumps(entry, sort_keys=True) + "\n"
        for entry in _registry(chamber3, "baseline") + _registry(chamber3, "recovery"))

    files["reset-criterion-evaluation.json"] = json.dumps(_criterion_evidence(),
                                                           indent=2, sort_keys=True) + "\n"
    files["repeatability-report.md"] = _report(chamber3, analyses)

    for name, text in files.items():
        _guard(name, text)
    return files


def _criterion_evidence() -> dict[str, object]:
    """Run the shipped candidate against real rows, and against a labelled injection."""
    criteria = criterion.load_criteria(CRITERION)
    rows = rep.split_phases(rep.read_rows(H8_CAPTURE))
    driven = next(row for row in rows["cooling"]
                  if (rep._number(row, "pwm_applied_permille") or 0.0) > 0.0)
    observed = criterion.state_from_capture_row(driven)
    shipped = criterion.evaluate(criteria, observed)

    injected = criterion.load_criteria(CRITERION)
    for entry in injected["parameters"]:
        if entry["name"] == "tmean_band_c":
            entry["value"], entry["status"] = "31.0", "TEST_INJECTION_NOT_FROZEN"
        if entry["name"] == "gradient_bound_c_per_min":
            entry["value"], entry["status"] = "0.5", "TEST_INJECTION_NOT_FROZEN"
    state = dict(observed, slope_c_per_min=0.0)
    return {
        "criteria_file": criterion.CRITERION_SCHEMA,
        "observed_state": observed,
        "shipped_candidate": shipped,
        "with_test_injected_numbers": {
            "note": ("the two values above were injected to prove the evaluator can answer "
                     "READY; they are not project thresholds and no document may quote them "
                     "as such"),
            "injection": {"tmean_band_c": "31.0", "gradient_bound_c_per_min": "0.5"},
            "result": criterion.evaluate(injected, state),
        },
    }


def _report(chamber3: dict[str, object], analyses: dict[str, dict[str, object]]) -> str:
    phases = chamber3["phases"]
    lines = [
        "# W07 repeatability report",
        "",
        f"Generated by `evidence/A/W07/{pathlib.Path(__file__).name}` from committed "
        "captures; every number below is reproducible with the reproduce command in "
        "`README.md`.",
        "",
        "## Verdict",
        "",
        "**NOT ESTABLISHED — insufficient independent runs.** The analysis exists, the "
        "captures do not.",
        "",
        f"- cooling-step runs: `{chamber3['verdict']['cooling_step_runs']}`",
        f"- passive warm-up runs: `{chamber3['verdict']['passive_warmup_runs']}`",
        f"- plant variation reportable: `{chamber3['verdict']['plant_variation_reportable']}`",
        f"- A-W07-02/03 require {MIN_RUNS} valid runs of each kind",
        "",
        "## What the one available run shows",
        "",
    ]
    for phase in ("baseline", "cooling", "recovery"):
        block = phases.get(phase)
        if not block:
            lines.append(f"- **{phase}**: no usable segment in the committed captures.")
            continue
        run = block["runs"][0]
        lines.append(
            f"- **{PHASE_LABEL[phase]}**: {run['samples']} samples over "
            f"{run['duration_min']} min, {run['representation']} moved "
            f"{run['delta_c']} C, whole-phase slope {run['whole_phase_slope_c_per_min']} "
            f"C/min, peak current {run['peak_current_a']} A, "
            f"full-term samples {run['full_term_samples']}/{run['samples']}, "
            f"n={block['verdict']['runs']} run.")
    lines += [
        "",
        "## The measurement question the run exposes",
        "",
        "The same committed run gives two different answers depending on which mean is",
        "called `Tmean`:",
        "",
    ]
    for representation, report in analyses.items():
        block = report["phases"].get("cooling")
        if block:
            run = block["runs"][0]
            lines.append(f"- `{representation}`: delta {run['delta_c']} C, "
                         f"whole-phase slope {run['whole_phase_slope_c_per_min']} C/min, "
                         f"1 C reached in {run['minutes_to_1c']} min.")
    lines += [
        "",
        "The capture labels the T2 probe `HOT_SIDE` while docs/01 freezes T1/T2/T3 as",
        "chamber-air probes, and during cooling T2 rises as T1/T3/T4 fall. That is the",
        "open contract decision, stated as measured disagreement between two named",
        "definitions. It is not resolved here, and no number in this report may be",
        "quoted as *the* cooling response until it is.",
        "",
        "## Statistics",
        "",
        "| phase | outcome | n | mean | sd (sample) | CV % | min | max |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for phase, block in sorted(phases.items()):
        for outcome, stats in sorted(block["statistics"].items()):
            if stats["status"] != "OK":
                continue
            lines.append(f"| {phase} | {outcome} | {stats['n']} | {stats['mean']} | "
                         f"{stats['sd_sample']} | {stats['cv_pct']} | {stats['min']} | "
                         f"{stats['max']} |")
    lines += [
        "",
        "With n=1 the spread columns are empty by construction, and that is the honest "
        "output: a single run has no dispersion. `reset-criterion-v0.yaml` keeps its two "
        "numeric gates `UNRESOLVED` for the same reason.",
        "",
    ]
    return "\n".join(lines)


def _guard(name: str, text: str) -> None:
    """No generated artifact may claim more than a host analysis of old captures."""
    lowered = text.lower()
    for token in ("physically verified", "repeatability established", "physical pass",
                  "verdict=pass", "bench pass"):
        if token in lowered:
            raise SystemExit(f"refusing to write {name}: it would claim {token!r}")
    if "independent_session" in lowered and '"independent_session": true' in lowered:
        raise SystemExit(f"refusing to write {name}: one boot_id cannot be independent")


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
        print(f"W07 ARTIFACTS OK ({len(files)} files reproduce from the tools and captures)")
    return 0


if __name__ == "__main__":
    write = "--check" not in sys.argv
    sys.exit(check_or_write(build(), write))
