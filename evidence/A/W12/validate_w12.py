"""Verify the W12 evidence dossier.

    py evidence/A/W12/validate_w12.py

Checks, in order:

1. every file listed in ``SHA256SUMS.txt`` exists and hashes to the pinned value,
   **and** every dossier file is pinned (an unpinned file, an unpinned ``__pycache__``
   or committed bytecode fails here even if the pin of the remaining files is
   re-generated to match a mutation);
2. no flash image (``*.bin``) was committed into the dossier;
3. ``acceptance.md`` keeps its honest, non-GREEN verdict;
4. honesty re-asserts (the point of this validator):
   * nothing in the dossier is labelled PHYSICALLY_VERIFIED and the report's
     ``physical_verified`` flag is False;
   * the gate G3 input does NOT declare a whole-team G3 GREEN;
   * the PZEM audit fails a *claim* of electrical qualification that has no
     evidence behind it - it never fails qualification itself, because the
     OPERATOR_ACTION_QUEUE asks a future capture to supply exactly that;
   * duty-0-with-current frames are listed individually (never a folded-in mean);
   * no door->critical number appears anywhere - in prose or in the real nested
     JSON shape (``"door_to_critical": {"value_s": 123.4}``) - because W13 owns
     that ask and it is NOT COMPUTABLE;
   * no forbidden physical-acceptance phrase ("clean runs", "physical acceptance",
     "compliance certified", ...) appears in any text artifact.

Exit code 0 only when every check passes. Nothing here touches hardware.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

DOSSIER = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DOSSIER.parents[2]

HONEST_VERDICT = "W12 is **not** a GREEN week"
# A gate-GREEN *claim* fails the dossier; a disclaimer that the slice does NOT
# declare GREEN must be allowed to say so in plain words. The scan finds each
# "G3/G4 ... GREEN" occurrence and fails only when no negation governs it.
_GATE = re.compile(r"\bG[34]\b[^\n]{0,25}?\bGREEN\b", re.IGNORECASE)
_NEG = re.compile(r"\b(not|never|cannot|no|without|declines?|does not|refuses|out of scope|blocked)\b",
                  re.IGNORECASE)
# Physical-acceptance claims that this host slice must never make, in any form,
# anywhere in the dossier text. Honest disclaimers do not use these strings.
FORBIDDEN_PHRASES = (
    "clean runs", "physical acceptance", "physically accepted",
    "compliance certified", "repeatability established", "physical freeze declared",
)
# A numeric door->critical claim in prose: "door->critical = 90 s" etc.
_DOOR_PROSE = re.compile(r"door[\s>_\-–—→]*critical[^\n]{0,40}?[:=]\s*-?\d", re.IGNORECASE)
_QUALIFICATION_CLAIMS = ("QUALIFIED", "PARTIALLY_QUALIFIED")


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
    """Every file under the dossier except the pin file itself (caches included)."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and p.name != "SHA256SUMS.txt"}


def check_pin_completeness(pinned: set[str], root: pathlib.Path) -> list[str]:
    """An unpinned file or a committed bytecode cache fails, even with re-pinned hashes."""
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


def check_pzem_qualification_claim(audit: dict) -> list[str]:
    """Fail a QUALIFIED *claim* that carries no evidence, never qualification itself.

    The old check failed whenever ``electrical_qualification`` left UNQUALIFIED -
    which asserted today's missing-qualification defect as an invariant and turned
    the chain red on the exact qualified capture this slice's action queue requests.

    Two gaps close here. ``PARTIALLY_QUALIFIED`` did not start with ``QUALIFIED`` so it
    escaped the prefix test entirely, and the evidence demanded was a *non-empty* cell,
    which INVALID, STALE or TIMEOUT tokens satisfy. A claim must now be backed by frames
    carrying the producer's own validating status (cg_pzem_status_name: OK), and any
    qualification string outside the published vocabulary fails rather than passing quietly.
    """
    failures: list[str] = []
    for cap in audit.get("captures", []):
        pz = cap.get("pzem_audit", {})
        if pz.get("duty0_with_current_frames", {}).get("listed_individually_never_averaged") is False:
            failures.append(f"{cap.get('capture')}: duty-0 current frames were averaged")
        qual = str(pz.get("electrical_qualification") or "")
        if qual in _QUALIFICATION_CLAIMS:
            evidence = pz.get("qualified_frame_evidence") or {}
            if not evidence.get("frames_with_valid_status"):
                failures.append(f"{cap.get('capture')}: claims {qual!r} electrical "
                                "qualification with no frame carrying a validating status "
                                "token - non-empty is not enough, INVALID and TIMEOUT are "
                                "both non-empty")
        elif qual not in ("UNQUALIFIED", ""):
            failures.append(f"{cap.get('capture')}: electrical_qualification {qual!r} is "
                            "outside the published qualification vocabulary")
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

    stray_bin = sorted(p.name for p in DOSSIER.rglob("*.bin"))
    if stray_bin:
        failures.append("flash images committed: " + ", ".join(stray_bin))

    acceptance = (DOSSIER / "acceptance.md").read_text(encoding="utf-8")
    if HONEST_VERDICT not in acceptance:
        failures.append("acceptance.md no longer states W12 is not a GREEN week")
    if declares_gate_green(acceptance):
        failures.append("acceptance.md declares a whole-team G3/G4 GREEN")

    audit_path = DOSSIER / "drift-audit.json"
    if not audit_path.is_file():
        failures.append("drift-audit.json is missing")
    else:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("physical_verified") is not False:
            failures.append("drift-audit.json no longer declares physical_verified=false")
        if audit.get("touches_hardware") is not False:
            failures.append("drift-audit.json claims it touched hardware")
        for cap in audit.get("captures", []):
            if cap.get("is_probe_identification") and cap.get("sensor_consistency", {}).get(
                    "slot_offsets"):
                failures.append(f"{cap['capture']}: probe-id capture produced drift stats")
        failures.extend(check_pzem_qualification_claim(audit))

    g3_path = DOSSIER / "gate-g3-input.json"
    if g3_path.is_file():
        g3 = json.loads(g3_path.read_text(encoding="utf-8"))
        if str(g3.get("a_side_status", "")).upper() in ("GREEN", "PHYSICALLY_VERIFIED",
                                                         "TEAM_GATE_G3_GREEN"):
            failures.append("gate-g3-input.json claimed a whole-team/physical status")
        if not str(g3.get("does_not_declare", "")).startswith("G3"):
            failures.append("gate-g3-input.json no longer states it does not declare G3")
    else:
        failures.append("gate-g3-input.json is missing")

    # Cross-tree door-number guard: W13 owns door->critical, but a stray numeric
    # door value anywhere under W12 - in prose or the real nested JSON shape - is a
    # hard failure. The old single-line regex missed {"door_to_critical":
    # {"value_s": 123.4}}; this walker matches the actual structure.
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
        print(f"W12 DOSSIER: OK ({len(pinned)} pinned files, honest verdict intact)")
        return 0
    print("W12 DOSSIER: FAIL")
    for f in failures:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
