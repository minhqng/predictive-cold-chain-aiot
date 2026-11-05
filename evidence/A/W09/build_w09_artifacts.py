"""Regenerate the W09 evidence artifacts from the delivered tooling.

    py evidence/A/W09/build_w09_artifacts.py [--check]

Every artifact here is derived by running the W09 tools over bytes that are
already in the repository. Nothing is typed in by hand, and the builder refuses
to write when a derived claim contradicts its source:

``run-protocol-v1.json`` / ``run-protocol-v1.md``
    The machine-readable and human forms of ``cg_w09_run_protocol`` - every gate,
    its doc anchor, and whether firmware can observe it.

``run-registry.json``
    The real baseline run registry: every capture in the repo, each classified
    by what it can and cannot enter. It exists so "we have four S1 runs" can never
    be asserted by counting files that are not runs.

``exports/CG-S1-H8C-600S.json``
    The per-run export of the only committed thermal capture, with frame rows,
    per-field quality, invalidation reasons, provenance and source SHA-256s.

``s1-run-index.json``
    The run index Member B joins against - valid S1 IDs plus measured usability.

``invalidation-summary.json``
    Reason and domain counts over the real capture, including the reasons that
    occurred zero times, so 'checked and found none' is distinguishable from
    'did not check'.

``healthy-ranges.json``
    A-W09-04's healthy response reference: electrical active/OFF ranges, thermal
    baseline and gradient, each labelled with the qualification it actually has.

``handoff-fields.md``
    A-W09 handoff to Member C: the run-manifest edge fields, from the export
    schema rather than from prose.

A pinned build stamp keeps the derivation byte-reproducible; the artifact records
that the stamp is a build constant and not a device time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[2]
TOOLS = REPO / "firmware" / "tools"

sys.path.insert(0, str(TOOLS))

import cg_w09_capture_parser as cp  # noqa: E402
import cg_w09_export as run_export  # noqa: E402
import cg_w09_noise as noise  # noqa: E402  (A-W09-04 gradient needs the measured noise)
import cg_w09_run_protocol as protocol  # noqa: E402
import cg_w09_validity as validity  # noqa: E402

BUILD_STAMP = "2026-11-02T00:00:00Z"  # pinned so --check is byte-reproducible
BUILD_STAMP_MEANING = "HOST_BUILD_CONSTANT_NOT_A_DEVICE_TIME"

W04_CSV = REPO / "evidence" / "A" / "W04" / "tec-cooling-response-600s.csv"
RUN_LABEL = "H8C_BOX_COOLING_600S"
EXPORT_RUN_ID = "CG-S1-H8C-600S"

# Every real capture in the repository, with the classification the W09 tools
# reach for it. These are not run IDs until they are eligible; the registry's
# job is to say which ones are.
REGISTRY_CANDIDATES = [
    {
        "capture_id": "W04-TEC-COOLING-600S",
        "path": "evidence/A/W04/tec-cooling-response-600s.csv",
        "kind": "csv_capture",
        "encoding": "derived 1 Hz table of the H8 box-cooling stage run",
        "session": "H8 box-cooling 600 s, stage H8-C, 2026-11-01, image 01cedce3...",
        "boot_id": "56044b74",
        "scenario_screen": "S1_NORMAL_BASELINE",
        "eligibility": "S1_BASELINE_CANDIDATE",
        "status_label": "REAL_DATA_ANALYZED",
        "is_physical_measurement": True,
        "notes": [
            "the only committed capture with a thermal response and an energized stage",
            "candidate, not certified: one run cannot show between-run repeatability",
            "electrical columns carry no producer status, so its energy claims are not usable",
        ],
    },
    {
        "capture_id": "W04-G1-BOOT-60S",
        "path": "evidence/A/W04/g1/42-telemetry.csv",
        "kind": "telem_schema1",
        "encoding": "schema-1 #CG TELEM derived table",
        "session": "G1 boot/reset observability check",
        "boot_id": "cb8775eb",
        "scenario_screen": None,
        "eligibility": "NOT_A_THERMAL_RUN",
        "status_label": "REAL_DATA_ANALYZED",
        "is_physical_measurement": True,
        "notes": [
            "a real capture of a real boot, but no stage ran and the probe roles were "
            "NOT_ASSIGNED, so it carries no thermal response to baseline",
        ],
    },
    {
        "capture_id": "W05-TIMING-PILOT",
        "path": "evidence/A/W05/timing-pilot-jitter.csv",
        "kind": "derived_timing_table",
        "encoding": "host timing-pilot jitter table over real schema-2 frames",
        "session": "W05 cadence/jitter pilot",
        "boot_id": None,
        "scenario_screen": None,
        "eligibility": "NOT_A_THERMAL_RUN",
        "status_label": "REAL_DATA_ANALYZED",
        "is_physical_measurement": True,
        "notes": ["cadence evidence only; it describes arrival timing, not plant state"],
    },
    {
        "capture_id": "W05-SCHEMA-FIXTURE",
        "path": "evidence/A/W05/schema-fixture.json",
        "kind": "schema_fixture",
        "encoding": "schema-2 fixture",
        "session": "W05 schema fixture",
        "boot_id": None,
        "scenario_screen": None,
        "eligibility": "HOST_FIXTURE_NOT_A_RUN",
        "status_label": "HOST_VERIFIED",
        "is_physical_measurement": False,
        "notes": ["proves the parser contract; can never populate a dataset"],
    },
    {
        "capture_id": "W06-DEMO-COMMAND-CAPTURE",
        "path": "evidence/A/W06/demo-command-capture.log",
        "kind": "host_command_fixture",
        "encoding": "C-harness command/ACK capture",
        "session": "W06 host harness",
        "boot_id": None,
        "scenario_screen": None,
        "eligibility": "HOST_FIXTURE_NOT_A_RUN",
        "status_label": "HOST_VERIFIED",
        "is_physical_measurement": False,
        "notes": ["host-generated C-harness fixture, not physical data"],
    },
    {
        "capture_id": "W06-ACK-FIXTURE",
        "path": "evidence/A/W06/ack-fixture.json",
        "kind": "host_command_fixture",
        "encoding": "labelled #CG CMDACK fixture set",
        "session": "W06 host harness",
        "boot_id": None,
        "scenario_screen": None,
        "eligibility": "HOST_FIXTURE_NOT_A_RUN",
        "status_label": "HOST_VERIFIED",
        "is_physical_measurement": False,
        "notes": ["five labelled ACK lines; protocol evidence only (docs/02 §32.2)"],
    },
]

# Captures that exist outside this branch and are therefore not citable here.
EXTERNAL_POSITIONS = [
    {
        "capture_id": "W07-PROBE-IDENTIFICATION",
        "location": "worktree A-W07-plant-repeatability/evidence/A/W07/probe-identification/",
        "session_class": "PROBE_IDENTIFICATION",
        "eligibility": "PERMANENTLY_EXCLUDED",
        "reason": "every frame was taken with a hand on a probe; docs/05A §18 A-W09-03 makes a "
                  "manual touch a physical invalidation, so these frames may never enter "
                  "S1/S2/S4 or any thermal-response statistic",
        "enforced_by": "cg_w09_validity.EXCLUDED_SESSION_CLASSES, tested in "
                       "test_cg_w09_validity.py (the W10 door tests of the stacked slice re-test "
                       "the same refusal from the consumer side)",
    },
    {
        "capture_id": "H8-PHASE4E-RAW-FRAMES",
        "location": "worktree A-W04-tec-commissioning/evidence/A/W04/h8/",
        "session_class": "H8_BENCH_RAW",
        "eligibility": "NOT_CITABLE_UNTRACKED",
        "reason": "the H8 monitor frames, including the raw #CG H8S lines behind the committed "
                  "CSV and the post-mount door window, are present on the bench host but are not "
                  "git-tracked on any branch; untracked bytes cannot anchor a published claim",
        "action_required": "the W04 owner must commit them; W09 parsing and door tooling are "
                           "already verified against their format",
    },
    {
        "capture_id": "H8-DOOR-DRIVER-SOURCE",
        "location": "worktree A-W04-tec-commissioning/firmware/h8-bench/main/",
        "session_class": "H8_BENCH_DRIVER_SOURCE",
        "eligibility": validity.UNCITABLE_UNTRACKED_SOURCE,
        "reason": "firmware/h8-bench/main/h8_door.c and the bench console driver are quoted by "
                  "the W10 door analysis as the code-level reason a frame cannot name its own "
                  "door state, but no git ref in this repository carries those files; the same "
                  "rule that excludes the untracked H8 frames applies to untracked source",
        "claim_kept": "the contact polarity inverts every reading between the two settings, so "
                      "door state needs a per-boot external attestation",
        "claim_rests_on": "docs/01 §8.1/§8.2 plus the complementary mapping table that "
                          "the W10 door slice stacked on this branch publishes as "
                          "cg_w10_door.MAPPING_BY_POLARITY",
        "action_required": "the H8 bench owner must commit the driver source; until then the "
                           "mechanism is stated with its citation status, not with a quotation",
    },
]


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(payload) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_registry(frames, export) -> dict:
    """The real baseline run registry.

    Eligibility is stated per capture, with the reason, and the counts are
    measured from the validity layer rather than asserted.
    """
    entries = []
    for candidate in REGISTRY_CANDIDATES:
        path = REPO / candidate["path"]
        entry = dict(candidate)
        entry["exists_in_repository"] = path.is_file()
        entry["sha256"] = sha256_file(path) if path.is_file() else None
        entry["size_bytes"] = path.stat().st_size if path.is_file() else None
        entries.append(entry)
    summary = export["invalidation"]["summary"]
    return {
        "registry_version": "w09-run-registry-v1",
        "generated_at_utc": BUILD_STAMP,
        "build_stamp_meaning": BUILD_STAMP_MEANING,
        "captures": entries,
        "external_positions": EXTERNAL_POSITIONS,
        "s1_baseline_target": "~4 valid S1 runs (docs/05A §18 A-W09-02)",
        "s1_candidates_available": sum(
            1 for e in entries if e["eligibility"] == "S1_BASELINE_CANDIDATE"
        ),
        "s1_runs_certified_valid": 0,
        "why_not_certified": [
            "certifying a baseline needs between-run repeatability, and one capture cannot show it",
            "the capture's electrical columns are unqualified, so its energy baseline is unusable",
            "the door was never in a machine-readable CLOSED state for the first 17 frames",
            "the derived table carries no door_status, air_c_status, rh_pct_status or "
            "power_w_status column at all, so the door and environment domains cannot be "
            "qualified and no row of it is usable for the S1 scenario",
        ],
        "measured_usability_of_the_candidate": {
            "frames_total": summary["rows_total"],
            "frames_usable_for_baseline": summary["rows_usable_for_baseline"],
            "frames_thermally_usable_for_statistics":
                summary["rows_thermally_usable_for_statistics"],
            "usable_fraction": summary["usable_fraction"],
            "quality_counts_by_domain": summary["quality_counts_by_domain"],
            "the_two_counts_are_not_the_same_claim": (
                "rows_thermally_usable counts rows clean enough for a mixed-probe thermal "
                "statistic; rows_usable_for_baseline counts rows the S1 scenario can use, which "
                "additionally needs the door and environment domains qualified"
            ),
        },
        "policy": [
            "an invalid attempt is recorded, never deleted (docs/05A §18 A-W09-03)",
            "a capture is not a run until the registry says it is eligible",
            "a host fixture can never appear as a run in this registry",
        ],
    }


def healthy_ranges(frames) -> dict:
    """A-W09-04: the healthy response reference, per lane, honestly labelled."""
    validities = validity.evaluate_frames(frames)
    thermal_ok = {
        i for i, v in enumerate(validities)
        if v.quality_by_domain["thermal"] not in validity.BLOCKING_SEVERITIES
        and v.quality_by_domain["producer"] not in validity.BLOCKING_SEVERITIES
    }
    active = [
        f for i, f in enumerate(frames)
        if i in thermal_ok and isinstance(f.values.get("pwm_applied_permille"), int)
        and f.values["pwm_applied_permille"] > 0
    ]
    off = [
        f for i, f in enumerate(frames)
        if i in thermal_ok and f.values.get("state") == "OFF"
        and f.values.get("pwm_applied_permille") == 0
    ]
    cooldown = [f for f in frames if f.values.get("state") == "COOLDOWN"]

    def series(rows, field):
        return [r.values.get(field) for r in rows if isinstance(r.values.get(field), (int, float))]

    def span(rows, field):
        values = series(rows, field)
        if not values:
            return None
        return {
            "n": len(values), "min": round(min(values), 4), "max": round(max(values), 4),
            "mean": round(statistics.fmean(values), 4),
        }

    profile = None
    thermal_baseline = {}
    for slot in run_export.CHAMBER_AIR_SLOTS:
        values = [
            f.values.get(slot) for i, f in enumerate(frames)
            if i in thermal_ok and isinstance(f.values.get(slot), (int, float))
        ]
        position = run_export.FROZEN_SENSOR_GEOMETRY[slot]["position"]
        thermal_baseline[f"{slot}_{position.lower()}"] = {
            "n": len(values),
            "start_c": round(values[0], 3) if values else None,
            "end_c": round(values[-1], 3) if values else None,
            "min_c": round(min(values), 3) if values else None,
            "max_c": round(max(values), 3) if values else None,
            "total_change_c": round(values[-1] - values[0], 3) if values else None,
        }
    electrical_qualification = validity.summarize(validities)["quality_counts_by_domain"]["electrical"]
    return {
        "requirement": "docs/05A §18 A-W09-04 (healthy response reference)",
        "status_label": "REAL_DATA_ANALYZED",
        "source": {"path": W04_CSV.relative_to(REPO).as_posix(), "sha256": sha256_file(W04_CSV)},
        "electrical_active_range": {
            "frames": len(active),
            "current_a": span(active, "current_a"),
            "voltage_v": span(active, "voltage_v"),
            "power_w": span(active, "power_w"),
            "pwm_applied_permille": span(active, "pwm_applied_permille"),
            "qualification": "UNQUALIFIED - current_status/voltage_status are empty in all 957 "
                             "rows and no power_status column exists",
            "usable_for_a_health_claim": False,
        },
        "electrical_off_range": {
            "frames": len(off),
            "current_a": span(off, "current_a"),
            "voltage_v": span(off, "voltage_v"),
            "qualification": "UNQUALIFIED, same reason",
            "usable_for_a_health_claim": False,
        },
        "cooldown_frames": len(cooldown),
        "thermal_baseline": thermal_baseline,
        "thermal_hot_side": {
            "n": len(series(frames, "t2")),
            "min_c": min(series(frames, "t2")), "max_c": max(series(frames, "t2")),
            "physical_position": "TEC_HOT_SIDE",
            "never_in_chamber_mean": True,
        },
        "per_probe_noise": None,
        "gradient": run_export.gradient(frames, thermal_ok),
        "cadence": run_export.measured_cadence(frames),
        "electrical_domain_counts": electrical_qualification,
        "honesty": [
            "the electrical ranges below are numbers read out of real frames",
            "they are not qualified measurements, so D and B must not cite them as health evidence",
            "thermal figures are computed only over rows the validity layer accepted for thermal use",
        ],
    }


def build_handoff_fields(export) -> str:
    lines = [
        "# Run-manifest edge fields (A-W09 handoff to Member C)",
        "",
        f"Derived from the export schema in `firmware/tools/cg_w09_export.py` "
        f"({run_export.EXPORT_VERSION}) and the example export "
        f"`exports/{EXPORT_RUN_ID}.json`. Status: **IMPLEMENTED / "
        "HOST_VERIFIED**.",
        "",
        "These are the fields a run manifest must carry for the backend to join a capture without "
        "guessing. Every one is present in the shipped export; none is inferred.",
        "",
        "| field | value in the example export | notes |",
        "|---|---|---|",
        f"| `run_id` | `{export['run_id']}` (`run_id_status={export['run_id_status']}`) | the "
        "source carries several run_id segments inside one boot_id; they are listed in `run_ids` "
        "and never merged into a joined id, so this run is not publishable for a B join |",
        f"| `run_ids` | `{export['run_ids']}` | the segments as the device stated them |",
        f"| `boot_id` | `{export['boot_id']}` (`boot_id_status={export['boot_id_status']}`) | "
        "per boot; opening the port changes it |",
        f"| `device_id` | `{export['device_id']}` | not carried by the H8S/CSV encodings |",
        f"| `hardware_config_id` | `{export['hardware_config_id']}` | from the `#CG LOG` boot line |",
        f"| `firmware_version` | `{export['firmware_version']}` | from the `#CG LOG` boot line |",
        f"| `schema_version` | `{export['schema_version']}` | wire schema of the source line |",
        "| `timestamp_utc` | `null` + `timestamp_utc_status=UNAVAILABLE` | device has no wall clock |",
        "| `host_capture_time_utc` | separate field, host-labelled | only where the transcript prefixed it |",
        "| `dedup_key` | `(device_id, boot_id, seq)` | docs/02 §4.2/§4.3 |",
        "",
        "## Sensor identity C receives",
        "",
        "| raw slot | ROM | ROM source | physical position | in chamber mean |",
        "|---|---|---|---|---|",
    ]
    for sensor in export["sensors"]:
        lines.append(
            f"| `{sensor['raw_slot']}` | `{sensor['rom']}` | `{sensor['rom_source']}` | "
            f"{sensor['physical_position']} | {'yes' if sensor['in_chamber_air_mean'] else '**no**'} |"
        )
    lines += [
        "",
        "ROMs are stated **by source** from the firmware ROM map and the per-boot `#CG ROM` lines; "
        "no readback was performed, and the export says so in `rom_readback_verified: false`.",
        "",
        "## Experiment phases",
        "",
    ]
    for phase, count in sorted(export["experiment_phase"]["counts"].items()):
        lines.append(f"* `{phase}` - {count} frame(s)")
    lines += [
        "",
        "## Invalidation C must propagate",
        "",
        f"Of {export['invalidation']['summary']['rows_total']} frames, "
        f"{export['invalidation']['summary']['rows_usable_for_baseline']} are usable for the "
        "S1 scenario and "
        f"{export['invalidation']['summary']['rows_thermally_usable_for_statistics']} are clean "
        "enough for a mixed-probe thermal statistic. The two are different claims: the scenario "
        "additionally requires the door and environment domains to be qualified, and this derived "
        "table carries no qualifier column for them, so those domains are reported UNKNOWN rather "
        "than assumed good. Reasons are per frame in `frames[].invalidation_reasons` and counted "
        "in `invalidation.summary.reason_counts`. No frame is deleted.",
        "",
    ]
    return "\n".join(lines)


def row_validity_csv(export) -> str:
    """Per-row verdicts and contract fields as a CSV beside the metadata export.

    The full 957-row inline block would weigh megabytes inside a JSON file a human
    has to scroll, so the rows ship as their own file - but the file delivers the
    **whole** per-row contract, rendered by the tool that declares it. An earlier
    revision of this function wrote 24 hand-picked columns while the export
    declared 50 and the dossier claimed 26, which is how a completeness claim came
    to name columns that did not exist.
    """
    return run_export.render_companion_csv(export["frames"])


def externalise_frames(export: dict, companion: str) -> dict:
    """Point the export at its companion CSV instead of inlining 957 rows.

    The declared column set is the set the companion renders, taken from the same
    constant, and the row contract states per field how it is delivered or why it
    is not. `validate_w09.py` compares the published header against this, so the
    declaration cannot drift from the delivery again.
    """
    rows = export["frames"]
    rendered_header = run_export.render_companion_csv(rows).splitlines()[0].split(",")
    if rendered_header != list(run_export.ROW_CSV_COLUMNS):
        raise run_export.ExportError(
            "the rendered companion header is not the declared row contract; refusing to "
            "publish a declaration of columns the file does not carry"
        )
    out = dict(export)
    out["frames"] = {
        "rows": len(rows),
        "companion_file": companion,
        "columns_per_row": list(run_export.ROW_CSV_COLUMNS),
        "row_contract": run_export.row_contract_block(),
        "reason": "kept out of the metadata file so the dossier stays reviewable; every field "
                  "the row contract demands is a column of this file, and the fields no "
                  "encoding can carry per row are stated there rather than left out",
    }
    return out


def build_artifacts() -> dict[str, str]:
    frames, report = cp.read_csv_capture(W04_CSV, RUN_LABEL)
    if report["rejected"]:
        raise RuntimeError(f"the committed capture no longer parses cleanly: {report['rejected']}")
    boot_identity = cp.read_boot_identity(
        (REPO / "evidence" / "A" / "W04" / "g1" / "40-g1-boot-60s.log").read_text(
            encoding="utf-8", errors="replace").splitlines()
    )
    source = run_export.RunSource(
        path=(W04_CSV.relative_to(REPO)).as_posix(),
        sha256=report["source_sha256"],
        source_kind="csv_capture",
        is_physical_measurement=True,
        run_label=RUN_LABEL,
        repo_tracked=True,
        note="derived 1 Hz table of the H8 box-cooling stage run",
    )
    export = run_export.build_run_export(
        frames,
        run_label=RUN_LABEL,
        scenario_candidate="S1_NORMAL_BASELINE",
        status_label="REAL_DATA_ANALYZED",
        boot_identity=boot_identity,
        sources=[source],
        generated_at_utc=BUILD_STAMP,
        extra_notes=[
            f"build stamp {BUILD_STAMP} is {BUILD_STAMP_MEANING}",
            "single-run candidate: between-run repeatability is not demonstrated by one capture",
        ],
    )
    rows_csv = row_validity_csv(export)
    companion = f"exports/{EXPORT_RUN_ID}.row-validity.csv"
    metadata_export = externalise_frames(export, companion)
    validities = validity.evaluate_frames(frames)
    registry = build_registry(frames, export)
    ranges = healthy_ranges(frames)
    ranges["per_probe_noise"] = noise.probe_noise_profile(frames)
    index = run_export.build_run_index(
        [metadata_export],
        generated_at_utc=BUILD_STAMP,
        notes=[
            "valid S1 IDs are a handoff to Member B (docs/05A §18 Handoff)",
            "a candidate is not a certified run; see run-registry.json for the gap",
            f"the artifact name '{EXPORT_RUN_ID}' is a host label for this export file, "
            "not a device run_id: the source run_id segments are ambiguous and are listed "
            "in blocked_run_ids instead of being published to B",
        ],
    )
    protocol_doc = protocol.document()
    return {
        "run-protocol-v1.json": _text(protocol_doc),
        "run-protocol-v1.md": protocol.render_markdown(protocol_doc),
        "run-registry.json": _text(registry),
        f"exports/{EXPORT_RUN_ID}.json": _text(metadata_export),
        companion: rows_csv,
        "s1-run-index.json": _text(index),
        "invalidation-summary.json": _text(validity.summarize(validities)),
        "healthy-ranges.json": _text(ranges),
        "handoff-fields.md": build_handoff_fields(metadata_export),
    }


# The files this dossier pins. A name here that is missing on disk is a validator
# failure, which is the point: the pin list is the manifest, not a listing of
# whatever happens to be in the directory.
PINNED_FILES = (
    "README.md",
    "acceptance.md",
    "build_w09_artifacts.py",
    "handoff-fields.md",
    "healthy-ranges.json",
    "invalidation-summary.json",
    "run-protocol-v1.json",
    "run-protocol-v1.md",
    "run-registry.json",
    "s1-run-index.json",
    f"exports/{EXPORT_RUN_ID}.json",
    f"exports/{EXPORT_RUN_ID}.row-validity.csv",
    "validate_w09.py",
)


def write_sums() -> int:
    missing = [name for name in PINNED_FILES if not (EVIDENCE / name).is_file()]
    if missing:
        print("W09 SUMS: REFUSED, missing " + ", ".join(missing))
        return 1
    lines = [f"{sha256_file(EVIDENCE / name)}  {name}" for name in sorted(PINNED_FILES)]
    (EVIDENCE / "SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote SHA256SUMS.txt ({len(lines)} files)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="regenerate and compare against the files on disk")
    parser.add_argument("--sums", action="store_true",
                        help="rewrite SHA256SUMS.txt for the files this dossier pins")
    args = parser.parse_args(argv)

    if args.sums:
        return write_sums()

    artifacts = build_artifacts()
    if args.check:
        drifted = []
        for name, text in artifacts.items():
            path = EVIDENCE / name
            if not path.is_file():
                drifted.append(f"{name}: missing")
            elif path.read_text(encoding="utf-8", newline="\n") != text:
                drifted.append(f"{name}: differs from a fresh derivation")
        if drifted:
            print("W09 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W09 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
        return 0

    for name, text in artifacts.items():
        path = EVIDENCE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name} ({len(text.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
