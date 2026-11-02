"""Regenerate the W08 evidence artifacts from recorded captures.

    py evidence/A/W08/build_w08_artifacts.py            # write the artifacts
    py evidence/A/W08/build_w08_artifacts.py --check    # compare, write nothing
    py evidence/A/W08/build_w08_artifacts.py --write-declaration [--bench-root DIR]
    py evidence/A/W08/build_w08_artifacts.py --check --verify-bench

Two input classes, kept apart on purpose:

``git`` sources are re-read from this repository on every run, so
``--check`` reproduces the byte content of every artifact on a clean checkout.
That set is the 957-row H8-C 600 s CSV, the H6 conservative trace, the two W03
OFF envelopes and the production G1 telemetry CSV.

``local-bench`` sources (the H7 20-100 % ladder, the H8 A-E endurance sessions
and the raw ``samples.jsonl`` the committed CSV was derived from) live only in
Member A's local W04 tree. They are **read there, never copied**, and their
derived statistics are carried into the artifacts through
``local-bench-observations.json``: a declared input with per-file SHA-256, frame
counts and the exact command that produced it, each value flagged
``reproducible_from_git: false``. ``--write-declaration`` regenerates that file
from the bench tree; ``--verify-bench`` re-derives it and fails on any drift.

Every artifact is generated. Nothing in this dossier is typed by hand, and
nothing in it may claim a physical verification: the honesty rules are asserted
after generation and the writer refuses to emit a file that breaks them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[2]
TOOLS = REPO / "firmware" / "tools"
sys.path.insert(0, str(TOOLS))

import cg_w08_envelope as envelope          # noqa: E402
import cg_w08_gate_a as gate_a              # noqa: E402
import cg_w08_hot_side as hot_side          # noqa: E402
import cg_w15_pzem_quality as quality       # noqa: E402

DECLARATION = EVIDENCE / "local-bench-observations.json"
LOCAL_SESSION_LABELS = tuple(label for _r, label, _g in envelope.H7_LADDER) + \
    tuple(label for _r, label, _g in envelope.H8_SESSIONS)

FORBIDDEN_TOKEN = "PHYSICALLY_VERIFIED"
NEGATIONS = ("not", "never", "no ", "refus", "unreach", "forbid", "without")

CROSS_CHECK_SESSION = "W04-H8C-box-600s-raw"
CROSS_CHECK_GIT_SESSION = "W04-H8C-box-600s"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# the local-bench declaration (declared input, hash-pinned)
# --------------------------------------------------------------------------

def session_bundle(frames: list[envelope.Frame], label: str, path: pathlib.Path,
                   rel: str, regime: str) -> dict[str, object]:
    """The declared statistics for one local session, computed by the same code
    that computes the committed ones - not transcribed.

    ``path`` is the real on-disk file (only read, hashed and sized); what lands
    in the pinned declaration is the ``<local-bench>/``-relative ``rel`` locator,
    because a developer absolute path would make this artifact unreviewable on
    any other machine.
    """
    coverage = envelope.status_coverage(frames)[label]
    duties = sorted({f.duty_applied for f in frames
                     if f.classification == envelope.DRIVEN})
    duty_rows = [
        {"duty_permille": duty,
         "stats": envelope.drive_stats([f for f in frames if f.duty_applied == duty])}
        for duty in duties
    ]
    hot_row = hot_side.analyse_session(
        frames, session=label, trust="LOCAL_BENCH",
        reproducible_from_git=False, regime=regime)
    a3_row = quality.a3_run_row(REPO, None, frames, label)
    a3_row["file"] = envelope.LOCAL_BENCH_MARKER + rel
    return {
        "label": label,
        "path": envelope.LOCAL_BENCH_MARKER + rel,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "frames": len(frames),
        "regime": regime,
        "source_summary": {
            "trust": "LOCAL_BENCH",
            "regime": regime,
            "frames": len(frames),
            "duty_applied_permille": duties[0] if duties else None,
            "drive": envelope.drive_stats(frames),
            "off": envelope.off_stats(frames),
            "thermal": envelope.thermal_response(frames),
            "power_consistency": envelope.power_consistency(frames),
            "energy_consistency": envelope.energy_consistency(frames),
            "status_coverage": coverage,
            "state_counts": envelope.frame_label_counts(frames, "state"),
            "stop_reason_counts": envelope.frame_label_counts(frames, "stop_reason"),
            "fault_bits_counts": envelope.frame_label_counts(frames, "fault_bits"),
            "snapshot_counts": envelope.frame_label_counts(frames, "snapshot"),
        },
        "duty_rows": duty_rows,
        "status_coverage": coverage,
        "holdover_frames": envelope.holdover_rows(frames),
        "duty_zero_with_current_frames": envelope.duty_zero_with_current(frames),
        "hot_side": hot_row.as_row() if hot_row else None,
        "w15_quality": quality.audit_source(
            frames, label, "LOCAL_BENCH", envelope.LOCAL_BENCH_MARKER + rel),
        "w15_a3_run": a3_row,
    }


def write_declaration(bench_root: pathlib.Path) -> dict[str, object]:
    if not bench_root.is_dir():
        raise RuntimeError(f"bench root not found: {bench_root}")
    sources = envelope.load_sources(REPO, bench_root)
    sessions: dict[str, object] = {}
    for rel, label, regime in list(envelope.H7_LADDER) + list(envelope.H8_SESSIONS):
        path = bench_root / rel
        if label not in sources or not path.is_file():
            raise RuntimeError(f"declared session {label} missing at {path}")
        sessions[label] = session_bundle(sources[label], label, path, rel, regime)
    declaration = {
        "schema": "cg-w08-local-bench-observations-1",
        "provenance": {
            "generated_by": "py evidence/A/W08/build_w08_artifacts.py "
                            "--write-declaration",
            "derived_by_modules": [
                "firmware/tools/cg_w08_envelope.py",
                "firmware/tools/cg_w08_hot_side.py",
            ],
            "bench_root_locator": (
                "<local-bench>/ = the tail below, resolved against the operator's "
                "--bench-root at derivation time; the pinned artifact deliberately "
                "carries no developer absolute path"
            ),
            "bench_root_tail": pathlib.PurePosixPath(
                *bench_root.parts[-4:]).as_posix(),
            "bench_root_is_local_only": True,
            "trust_class": "LOCAL_BENCH",
            "reproducible_from_git": False,
            "committed_in_git": False,
            "originals_copied_into_repository": False,
            "note": (
                "These captures live only in Member A's local W04 tree. This file "
                "declares what the same analysis code computed from them, with each "
                "source file's SHA-256 recorded at derivation time, so a reviewer can "
                "verify the bytes without the originals being copied or committed. "
                "Every number taken from here is flagged reproducible_from_git: false."
            ),
            "cross_check": (
                f"{CROSS_CHECK_SESSION} is the raw stream of {CROSS_CHECK_GIT_SESSION}, "
                "whose derived CSV IS committed; validate_w08.py asserts the two agree "
                "on the electrical and thermal statistics, which is what makes this "
                "declaration checkable rather than asserted."
            ),
        },
        "sessions": sessions,
    }
    return declaration


def load_declaration() -> dict[str, object]:
    if not DECLARATION.is_file():
        raise RuntimeError(
            f"{DECLARATION.name} is missing; regenerate it with --write-declaration")
    return json.loads(DECLARATION.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# merge: git envelope + declared local sessions
# --------------------------------------------------------------------------

def merge_declared(base: dict[str, object], declaration: dict[str, object]
                   ) -> dict[str, object]:
    """Fold the declared sessions into the git-derived envelope, flagged."""
    for label, bundle in sorted(declaration["sessions"].items()):
        summary = dict(bundle["source_summary"])
        summary["reproducible_from_git"] = False
        summary["declared_in"] = DECLARATION.name
        base["sources"][label] = summary
        for entry in bundle["duty_rows"]:
            stats = dict(entry["stats"])
            base["by_duty_permille"].setdefault(str(entry["duty_permille"]), []).append({
                "source": label,
                "trust": "LOCAL_BENCH",
                "regime": bundle["regime"],
                **stats,
            })
        base["status_coverage"][label] = bundle["status_coverage"]
        base["holdover_frames"].extend(bundle["holdover_frames"])
        base["duty_zero_with_current_frames"].extend(
            bundle["duty_zero_with_current_frames"])
    for key in base["by_duty_permille"]:
        base["by_duty_permille"][key].sort(key=lambda entry: entry["source"])
    base["local_bench_sources_present"] = False
    base["local_bench_declared_from"] = DECLARATION.name
    return base


def declared_hot_side_rows(declaration: dict[str, object]) -> list[hot_side.HotSideRow]:
    rows: list[hot_side.HotSideRow] = []
    for bundle in declaration["sessions"].values():
        payload = bundle.get("hot_side")
        if not payload:
            continue
        fields = dict(payload)
        fields["trust"] = "LOCAL_BENCH"
        fields["reproducible_from_git"] = False
        rows.append(hot_side.HotSideRow(**{
            key: fields[key] for key in hot_side.HotSideRow.__dataclass_fields__}))
    return rows


def build_artifact_map(repo_root: pathlib.Path) -> dict[str, str]:
    declaration = load_declaration()
    base = envelope.build_envelope(repo_root, None)
    merged = merge_declared(base, declaration)

    committed_currents = hot_side.observed_currents(repo_root, None)
    declared_currents = [
        {
            "session": label,
            "trust": "LOCAL_BENCH",
            "series_path_regime": bundle["regime"],
            "duty_permille": bundle["source_summary"]["duty_applied_permille"],
            "driven_frames": bundle["source_summary"]["drive"]["frames_used"],
            "current_median_a":
                bundle["source_summary"]["drive"]["current_a"].get("median"),
            "current_p95_a": bundle["source_summary"]["drive"]["current_a"].get("p95"),
            "current_max_a": bundle["source_summary"]["drive"]["current_a"].get("max"),
            "power_max_w": bundle["source_summary"]["drive"]["power_w"].get("max"),
            "electrical_status_recorded":
                bundle["source_summary"]["status_coverage"]["electrical_status_recorded"],
        }
        for label, bundle in sorted(declaration["sessions"].items())
        if bundle["source_summary"]["drive"]["frames_used"]
    ]
    fuse = hot_side.fuse_evaluation(committed_currents + declared_currents)

    git_rows = hot_side.analyse_all(repo_root, None)
    rows = git_rows + declared_hot_side_rows(declaration)
    rows.sort(key=lambda row: row.session)

    package = gate_a.build_package(repo_root, None, merged,
                                   {"fuse_evaluation": fuse})

    artifacts = {
        "operating-envelope-v1.yaml": envelope.render_yaml(merged),
        "envelope-by-duty.csv": envelope.render_duty_csv(merged),
        "holdover-frames.csv": envelope.render_holdover_csv(merged),
        "duty-zero-current-frames.csv": envelope.render_duty_zero_current_csv(merged),
        "electrical-status-coverage.csv": envelope.render_status_coverage_csv(merged),
        "source-summary.csv": envelope.render_source_summary_csv(merged),
        "thermal-sustainability.csv": hot_side.render_thermal_csv(rows),
        "fuse-selection.md": hot_side.render_fuse_md(fuse),
        "safe-local-physical-inputs.csv": gate_a.render_safe_local_csv(package),
        "gate-a-artifact-index.csv": gate_a.render_index_csv(package),
        "gate-a-operator-queue.csv": gate_a.render_queue_csv(package),
        "Gate-A-report.md": gate_a.render_gate_a_report(package),
    }
    return artifacts


def honesty_check(artifacts: dict[str, str]) -> list[str]:
    """Refuse to write an artifact that promotes itself into a physical claim."""
    failures: list[str] = []
    for name, text in sorted(artifacts.items()):
        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_TOKEN in line and not any(n in line.lower()
                                                   for n in NEGATIONS):
                failures.append(
                    f"{name}:{number} asserts {FORBIDDEN_TOKEN} without a negation: "
                    f"{line.strip()[:120]}")
        if name.endswith(".csv") and FORBIDDEN_TOKEN in text:
            failures.append(f"{name}: a CSV must never carry the {FORBIDDEN_TOKEN} "
                            "token at all")
        for number, line in enumerate(text.splitlines(), start=1):
            hits = envelope.absolute_path_hits(line)
            if hits:
                failures.append(
                    f"{name}:{number} would pin an absolute developer path "
                    f"({hits[0]!r}); emit a repository-relative or "
                    f"{envelope.LOCAL_BENCH_MARKER} locator instead")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="regenerate in memory and compare with the files")
    parser.add_argument("--write-declaration", action="store_true",
                        help="derive local-bench-observations.json from the bench tree")
    parser.add_argument("--verify-bench", action="store_true",
                        help="with --check, also re-derive the declaration and compare")
    parser.add_argument("--bench-root", type=pathlib.Path,
                        default=envelope.DEFAULT_BENCH_ROOT)
    args = parser.parse_args(argv)

    if args.write_declaration:
        declaration = write_declaration(args.bench_root)
        DECLARATION.write_text(json.dumps(declaration, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8", newline="\n")
        print(f"wrote {DECLARATION.name} "
              f"({len(declaration['sessions'])} declared local sessions)")
        return 0

    if args.verify_bench:
        fresh = write_declaration(args.bench_root)
        committed = load_declaration()
        drifted = [
            label for label, bundle in fresh["sessions"].items()
            if json.dumps(bundle, sort_keys=True)
            != json.dumps(committed["sessions"].get(label), sort_keys=True)
        ]
        if drifted:
            print("DECLARATION DRIFTED for: " + ", ".join(sorted(drifted)))
            return 1
        print(f"declaration matches a fresh derivation "
              f"({len(fresh['sessions'])} sessions)")

    artifacts = build_artifact_map(REPO)
    failures = honesty_check(artifacts)
    if failures:
        print("ARTIFACT_BUILD_FAILED: an artifact asserts a physical claim")
        for line in failures:
            print(f"  - {line}")
        return 1

    if args.check:
        drifted = []
        for name, text in sorted(artifacts.items()):
            path = EVIDENCE / name
            if not path.is_file():
                drifted.append(f"{name}: missing")
            elif path.read_text(encoding="utf-8", newline="\n") != text:
                drifted.append(f"{name}: differs from a fresh derivation")
        if drifted:
            print("W08 ARTIFACT CHECK: DRIFTED")
            for line in drifted:
                print(f"  - {line}")
            return 1
        print(f"W08 ARTIFACT CHECK: {len(artifacts)} artifacts reproduce exactly")
        return 0

    for name, text in sorted(artifacts.items()):
        (EVIDENCE / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name} ({len(text.encode('utf-8'))} bytes)")
    print("Reminder: every artifact here is derived from recorded captures. None of "
          "them is a physical verification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Sentinel: CONTINUE-AT-END-OF-BUILDER
