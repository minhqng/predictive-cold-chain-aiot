#!/usr/bin/env python3
"""W23 evidence-package verifier (B-W23-04).

Reads only the explicit allowlisted package manifest, recomputes accessible file
hashes, and fails closed on integrity violations. It never opens locked-test
outcomes or final physical A/B outcomes, and it never writes into the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "coldguard-w23-evidence-package-v1"
MANIFEST_NAME = "evidence-package-W23.json"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HASH_KINDS = {
    "FILE_CONTENT_SHA256",
    "ARTIFACT_MANIFEST_SHA256",
}
FORBIDDEN_DATA_PATTERNS = (
    re.compile(r"locked[-_]test[-_]observations", re.IGNORECASE),
    re.compile(r"pair[-_]outcomes?\.(csv|json|parquet)$", re.IGNORECASE),
    re.compile(r"campaign[-_]export", re.IGNORECASE),
    re.compile(r"holdout[-_]data", re.IGNORECASE),
)
REQUIRED_TOP_LEVEL = (
    "schema",
    "package_id",
    "package_version",
    "git_source_revision",
    "revision_semantics",
    "canonical_documents",
    "sources",
    "reports",
    "dependency_lock",
    "figure_availability",
    "clean_room",
    "demo_narrative",
    "scientific_limitation_ledger",
    "external_dependencies",
)
REQUIRED_SOURCE_FIELDS = (
    "source_id",
    "path",
    "sha256",
    "hash_kind",
    "availability",
    "required_for_package",
    "evidence_class",
    "content_role",
    "owner",
    "opens_locked_outcome",
)
AVAILABILITY = {
    "LOCAL",
    "DECLARED_ONLY",
    "SOURCE_UNAVAILABLE",
    "WITHHELD",
}


class ManifestError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be an object")
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_TOP_LEVEL if key not in manifest]
    if missing:
        raise ManifestError(f"missing top-level fields: {missing}")
    if manifest["schema"] != SCHEMA:
        raise ManifestError(f"unsupported schema: {manifest['schema']!r}")
    if not isinstance(manifest["reports"], dict) or not manifest["reports"]:
        raise ManifestError("reports must be a non-empty object")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, entry in enumerate(manifest["sources"]):
        if not isinstance(entry, dict):
            raise ManifestError(f"sources[{index}] must be an object")
        missing = [field for field in REQUIRED_SOURCE_FIELDS if field not in entry]
        if missing:
            raise ManifestError(f"sources[{index}] missing fields: {missing}")
        source_id = entry["source_id"]
        if not isinstance(source_id, str) or not source_id:
            raise ManifestError(f"sources[{index}].source_id must be a non-empty string")
        if source_id in seen_ids:
            raise ManifestError(f"duplicate source_id: {source_id}")
        seen_ids.add(source_id)

        relative = entry["path"]
        if not isinstance(relative, str) or not relative:
            raise ManifestError(f"{source_id}.path must be a non-empty string")
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ManifestError(f"{source_id}.path must be repository-relative: {relative}")
        if relative in seen_paths:
            raise ManifestError(f"duplicate source path: {relative}")
        seen_paths.add(relative)

        if entry["hash_kind"] not in HASH_KINDS:
            raise ManifestError(f"{source_id}.hash_kind is not allowed: {entry['hash_kind']}")
        if entry["availability"] not in AVAILABILITY:
            raise ManifestError(
                f"{source_id}.availability is not allowed: {entry['availability']}"
            )
        if not isinstance(entry["required_for_package"], bool):
            raise ManifestError(f"{source_id}.required_for_package must be boolean")
        if not isinstance(entry["opens_locked_outcome"], bool):
            raise ManifestError(f"{source_id}.opens_locked_outcome must be boolean")
        if entry["opens_locked_outcome"]:
            raise ManifestError(f"{source_id} is declared to open a locked outcome")
        if any(pattern.search(relative) for pattern in FORBIDDEN_DATA_PATTERNS):
            raise ManifestError(f"{source_id} points at a forbidden outcome payload: {relative}")

        if entry["availability"] == "LOCAL":
            if not SHA256_RE.fullmatch(str(entry["sha256"])):
                raise ManifestError(f"{source_id}.sha256 must be 64 lowercase hex")
        elif entry["availability"] == "DECLARED_ONLY":
            if not SHA256_RE.fullmatch(str(entry["sha256"])):
                raise ManifestError(f"{source_id}.sha256 must be 64 lowercase hex")
        else:
            if entry["sha256"] is not None:
                raise ManifestError(
                    f"{source_id}.sha256 must be null when availability is "
                    f"{entry['availability']}"
                )

        if Path(relative).name == MANIFEST_NAME:
            raise ManifestError(f"{source_id} points at the manifest itself (self-hash)")


def verify_entry(entry: dict[str, Any], root: Path) -> dict[str, Any]:
    result = {
        "source_id": entry["source_id"],
        "path": entry["path"],
        "availability": entry["availability"],
        "required_for_package": entry["required_for_package"],
        "declared_sha256": entry["sha256"],
        "observed_sha256": None,
        "status": "UNKNOWN",
        "reason": None,
    }
    if entry["availability"] == "SOURCE_UNAVAILABLE":
        result["status"] = "SOURCE_UNAVAILABLE"
        result["reason"] = "source is not present in this checkout"
        return result
    if entry["availability"] == "WITHHELD":
        result["status"] = "WITHHELD"
        result["reason"] = "scientific gate withholds this artifact"
        return result
    if entry["availability"] == "DECLARED_ONLY":
        result["status"] = "DECLARED_HASH_NOT_RECOMPUTED"
        result["reason"] = "only a declaration is available"
        return result

    absolute = (root / entry["path"]).resolve()
    if not absolute.is_file():
        result["status"] = "MISSING"
        result["reason"] = f"file not found: {absolute}"
        return result
    observed = sha256_file(absolute)
    result["observed_sha256"] = observed
    if observed == entry["sha256"]:
        result["status"] = "VERIFIED"
    else:
        result["status"] = "MISMATCH"
        result["reason"] = "content hash does not match the declaration"
    return result


def verify_package(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    entries = [verify_entry(entry, root) for entry in manifest["sources"]]
    entries.sort(key=lambda item: item["source_id"])

    violations: list[str] = []
    for entry in entries:
        if entry["status"] in {"MISSING", "MISMATCH"}:
            violations.append(f"{entry['status']}: {entry['source_id']} ({entry['path']})")
        elif entry["status"] == "UNKNOWN" and entry["required_for_package"]:
            violations.append(f"UNVERIFIED_REQUIRED: {entry['source_id']}")

    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1

    report_results: list[dict[str, Any]] = []
    for name, expected in sorted(manifest["reports"].items()):
        relative = f"ml/reports/W23/{name}"
        absolute = (root / relative).resolve()
        if not absolute.is_file():
            report_results.append(
                {"report": name, "path": relative, "status": "MISSING", "observed_sha256": None}
            )
            violations.append(f"MISSING_REPORT: {relative}")
            continue
        observed = sha256_file(absolute)
        status = "VERIFIED" if observed == expected else "MISMATCH"
        report_results.append(
            {"report": name, "path": relative, "status": status, "observed_sha256": observed}
        )
        if status != "VERIFIED":
            violations.append(f"REPORT_HASH_MISMATCH: {relative}")

    lock = manifest["dependency_lock"]
    lock_path = (root / lock["path"]).resolve()
    if not lock_path.is_file():
        violations.append(f"DEPENDENCY_LOCK_MISSING: {lock['path']}")
        lock_status = "MISSING"
    else:
        lock_status = "VERIFIED" if sha256_file(lock_path) == lock["sha256"] else "MISMATCH"
        if lock_status != "VERIFIED":
            violations.append(f"DEPENDENCY_LOCK_MISMATCH: {lock['path']}")

    clean_room = manifest["clean_room"]
    if clean_room.get("independent_team_member_replay") not in {"PENDING", "VERIFIED"}:
        violations.append("CLEAN_ROOM_INDEPENDENT_STATUS_INVALID")
    if clean_room.get("final_physical_analysis") != "NOT_AUTHORIZED":
        violations.append("CLEAN_ROOM_PHYSICAL_ANALYSIS_NOT_REFUSED")

    return {
        "schema": "coldguard-w23-audit-result-v1",
        "package_id": manifest["package_id"],
        "package_version": manifest["package_version"],
        "git_source_revision": manifest["git_source_revision"],
        "revision_semantics": manifest["revision_semantics"],
        "entries": entries,
        "reports": report_results,
        "dependency_lock": {
            "path": lock["path"],
            "declared_sha256": lock["sha256"],
            "status": lock_status,
        },
        "summary": {
            "checked": len(entries),
            "violations": len(violations),
            "status_counts": dict(sorted(counts.items())),
        },
        "violations": sorted(violations),
        "integrity_ok": not violations,
        "scientific_status": manifest.get("scientific_status"),
    }


def render_summary(result: dict[str, Any]) -> str:
    lines = [
        "# W23 evidence-package audit",
        "",
        f"- package: `{result['package_id']}` version `{result['package_version']}`",
        f"- source revision: `{result['git_source_revision']}` "
        f"({result['revision_semantics']})",
        f"- integrity: **{'PASS' if result['integrity_ok'] else 'FAIL'}**",
        f"- checked sources: {result['summary']['checked']}",
        f"- violations: {result['summary']['violations']}",
        "",
        "## Status counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in result["summary"]["status_counts"].items():
        lines.append(f"| `{status}` | {count} |")
    lines.extend(["", "## Violations", ""])
    if result["violations"]:
        lines.extend(f"- {item}" for item in result["violations"])
    else:
        lines.append("None.")
    lines.extend(["", "## Sources", "", "| Source | Status | Path |", "|---|---|---|"])
    for entry in result["entries"]:
        lines.append(
            f"| `{entry['source_id']}` | `{entry['status']}` | `{entry['path']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(result: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    (out_dir / "audit-result.json").write_text(payload, encoding="utf-8")
    (out_dir / "audit-summary.md").write_text(render_summary(result), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the W23 evidence-package manifest (read-only)."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("reports/W23") / MANIFEST_NAME,
        help="explicit allowlisted evidence-package manifest",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root used to resolve manifest paths",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="optional directory for deterministic audit-result.json and audit-summary.md",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest_path = args.manifest if args.manifest.is_absolute() else Path.cwd() / args.manifest
    try:
        manifest = load_manifest(manifest_path)
        result = verify_package(manifest, args.root)
    except ManifestError as exc:
        print(f"W23 AUDIT FAILED: {exc}", file=sys.stderr)
        return 2
    if args.out is not None:
        write_outputs(result, args.out)
    print(
        json.dumps(
            {
                "package_id": result["package_id"],
                "integrity_ok": result["integrity_ok"],
                "violations": result["violations"],
                "status_counts": result["summary"]["status_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["integrity_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
