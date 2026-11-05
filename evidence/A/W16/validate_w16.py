"""Verify the W16 evidence dossier.

    py evidence/A/W16/validate_w16.py

W16's honesty is narrow and absolute: **no physical freeze may be declared from
host evidence, and no whole-team gate may be called GREEN.** This validator
re-runs the framework's own ``assert_no_freeze`` against the committed artifact
and additionally checks:

* ``comparability-framework.json`` has ``frozen: false`` and a derived
  ``no_g4_claim: true``;
* the cross-era comparison is BLOCKED and its verdict cannot be flipped to
  COMPARABLE while the W16 snapshot is absent (a verdict change that disagrees
  with ``comparison_allowed`` fails, not just a hash change);
* every response-tolerance field is still NOT_MEASURED;
* the acceptance keeps its non-GREEN verdict and never claims G4 GREEN;
* **absence is not a match** - a MISSING_SIDE dimension is expected, since the
  committed baseline labels only T2 and its physical-output column is empty;
* every dossier file is pinned (unpinned files and committed bytecode fail even
  with re-pinned hashes), no text artifact carries a forbidden physical-acceptance
  phrase, and the top-level verdict never declares a physical freeze.

A dossier that ever sets a freeze or a team gate from host bytes fails here.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

DOSSIER = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DOSSIER.parents[2]
# Do not leave a bytecode cache in the pinned dossier while importing the tool.
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO_ROOT / "firmware" / "tools"))

import cg_w16_comparability as w16  # noqa: E402

HONEST_VERDICT = "W16 is **not** a GREEN week"
_GATE = re.compile(r"\bG[34]\b[^\n]{0,25}?\bGREEN\b", re.IGNORECASE)
_NEG = re.compile(r"\b(not|never|cannot|no|without|declines?|does not|refuses|out of scope|blocked)\b",
                  re.IGNORECASE)
FORBIDDEN_PHRASES = (
    "clean runs", "physical acceptance", "physically accepted",
    "compliance certified", "repeatability established", "physical freeze declared",
)
_DOOR_PROSE = re.compile(r"door[\s>_\-–—→]*critical[^\n]{0,40}?[:=]\s*-?\d", re.IGNORECASE)


def declares_gate_green(text: str) -> bool:
    for m in _GATE.finditer(text):
        window = text[max(0, m.start() - 40):m.start()]
        if not _NEG.search(window):
            return True
    return False


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _all_dossier_files(root: pathlib.Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and p.name != "SHA256SUMS.txt"}


def check_pin_completeness(pinned: set[str], root: pathlib.Path) -> list[str]:
    failures: list[str] = []
    expected = _all_dossier_files(root)
    for unpinned in sorted(expected - pinned):
        failures.append(f"{unpinned} is in the dossier but not pinned")
    for stale in sorted(pinned - expected):
        failures.append(f"{stale} is pinned but no longer present (deleted or cache)")
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix == ".pyc" or "__pycache__" in path.parts):
            failures.append(f"{path.relative_to(root).as_posix()}: committed bytecode cache")
    return failures


def _door_leaf_is_numeric(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        for key in ("value_s", "value"):
            if key in value and not isinstance(value[key], bool) \
                    and isinstance(value[key], (int, float)):
                return True
    return False


def _walk_for_door_claims(obj: object, where: str, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            label = f"{where}.{k}"
            if re.search(r"door.*critical", str(k), re.IGNORECASE) and _door_leaf_is_numeric(v):
                out.append(label)
            _walk_for_door_claims(v, label, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_for_door_claims(v, f"{where}[{i}]", out)


def check_comparability_honesty(frame: dict) -> list[str]:
    """Absence must block, and a verdict may not disagree with its own flags."""
    failures: list[str] = []
    if frame.get("frozen") is not False:
        failures.append("comparability-framework.json set a physical freeze")
    if frame.get("no_g4_claim") is not True:
        failures.append("comparability-framework.json lost its no-G4-claim flag")
    # A freeze declared in the verdict text, not just the boolean, is a hard fail.
    verdict = str(frame.get("verdict", ""))
    if re.search(r"frozen|physical freeze", verdict, re.IGNORECASE) and "NO_FREEZE" not in verdict:
        failures.append(f"verdict declares a freeze: {verdict!r}")
    comp = frame.get("cross_era_comparison", {})
    if frame.get("w16_snapshot_present") is False:
        if comp.get("comparison_allowed") is not False:
            failures.append("comparability allowed a cross-era comparison without a W16 snapshot")
        if comp.get("verdict") != "BLOCKED":
            failures.append("cross_era_comparison.verdict is not BLOCKED while the W16 "
                            "snapshot is absent")
    else:
        # A W16 snapshot was supplied: the verdict must agree with comparison_allowed.
        allowed = comp.get("comparison_allowed")
        state = comp.get("verdict")
        if allowed is False and state == "COMPARABLE":
            failures.append("cross_era_comparison.verdict says COMPARABLE but "
                            "comparison_allowed is false")
        if allowed is True and state != "COMPARABLE":
            failures.append("cross_era_comparison.verdict disagrees with comparison_allowed")
    # Absence is not a match: at least one side must be MISSING_SIDE here.
    states = {v.get("state") for v in comp.get("dimension_table", {}).values()}
    if frame.get("w16_snapshot_present") is False and not states & {"MISSING_SIDE", "MISMATCH"}:
        failures.append("cross-era dimension table reports no MISSING_SIDE/MISMATCH even "
                        "though the W16 side is absent")
    return failures


def main() -> int:
    failures: list[str] = []
    sums_path = DOSSIER / "SHA256SUMS.txt"
    if not sums_path.is_file():
        print("FAIL: SHA256SUMS.txt is missing")
        return 1
    pinned: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([0-9a-f]{64})  (.+)$", line.strip())
        if not m:
            if line.strip():
                failures.append(f"unparsable SHA256SUMS line: {line[:80]!r}")
            continue
        digest, rel = m.groups()
        pinned[rel] = digest
        target = DOSSIER / rel
        if not target.is_file():
            failures.append(f"missing evidence file: {rel}")
            continue
        if b"\r" in target.read_bytes():
            failures.append(f"{rel} is not LF-only")
        if sha256(target) != digest:
            failures.append(f"hash mismatch: {rel}")

    failures.extend(check_pin_completeness(set(pinned), DOSSIER))

    acceptance = (DOSSIER / "acceptance.md").read_text(encoding="utf-8")
    if HONEST_VERDICT not in acceptance:
        failures.append("acceptance.md no longer states W16 is not a GREEN week")
    if declares_gate_green(acceptance):
        failures.append("acceptance.md declares a whole-team G3/G4 GREEN")

    frame_path = DOSSIER / "comparability-framework.json"
    if frame_path.is_file():
        frame = json.loads(frame_path.read_text(encoding="utf-8"))
        failures.extend(check_comparability_honesty(frame))
        try:
            w16.assert_no_freeze(frame)
        except AssertionError as exc:
            failures.append(f"assert_no_freeze rejected the committed artifact: {exc}")
    else:
        failures.append("comparability-framework.json is missing")

    tol_path = DOSSIER / "response-tolerance-format.json"
    if tol_path.is_file():
        tol = json.loads(tol_path.read_text(encoding="utf-8"))
        for name, field in tol.get("fields", {}).items():
            if field.get("value") != "NOT_MEASURED":
                failures.append(f"tolerance {name} was filled from host evidence")
    else:
        failures.append("response-tolerance-format.json is missing")

    # Text-artifact scans: forbidden physical-acceptance phrases, door numbers.
    for path in sorted(DOSSIER.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(DOSSIER).as_posix()
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            hits: list[str] = []
            _walk_for_door_claims(data, rel, hits)
            for h in hits:
                failures.append(f"{rel}: a door-critical numeric value appeared "
                                f"without data ({h})")
        elif path.suffix in (".md", ".csv", ".txt"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for phrase in FORBIDDEN_PHRASES:
                if phrase in text.lower():
                    failures.append(f"{rel}: forbidden physical-acceptance phrase {phrase!r}")
            if _DOOR_PROSE.search(text):
                failures.append(f"{rel}: a numeric door->critical claim appeared in prose")

    if not failures:
        print(f"W16 DOSSIER: OK ({len(pinned)} pinned files, no freeze, honest verdict)")
        return 0
    print("W16 DOSSIER: FAIL")
    for f in failures:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
