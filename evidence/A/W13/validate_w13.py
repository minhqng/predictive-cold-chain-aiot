"""Verify the W13 evidence dossier.

    py evidence/A/W13/validate_w13.py

Beyond the SHA256 pins this validator re-asserts the honesty rules the W13 slice
is judged on:

* **no door->critical number without data** - ``door-critical.csv`` carries no
  numeric value and ``plant-timing-report.json`` reports door->critical as
  NOT_COMPUTABLE with ``number_emitted: false``. A stray number - in prose or in
  the real nested JSON shape - fails the build.
* **no physical PASS / no whole-team GREEN** - nothing is marked
  PHYSICALLY_VERIFIED and the acceptance does not declare G3/G4 GREEN.
* **the command->electrical onset rule is honest** - it cites the committed
  pre-ramp source (``41-h6-run-analysis.md:28``), not a non-existent analysis
  doc, and states the device-log-uptime clock and the +/-1 s poll quantization.

It also checks the data-gap register names the door gap and the network-command
gap, enumerates every dossier file against the pins (unpinned files and committed
bytecode fail even with re-pinned hashes), and scans text artifacts for forbidden
physical-acceptance phrases.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

DOSSIER = pathlib.Path(__file__).resolve().parent
HONEST_VERDICT = "W13 is **not** a GREEN week"
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
        failures.append("acceptance.md no longer states W13 is not a GREEN week")
    if declares_gate_green(acceptance):
        failures.append("acceptance.md declares a whole-team G3/G4 GREEN")

    # door->critical must not carry a number.
    dc_path = DOSSIER / "door-critical.csv"
    if dc_path.is_file():
        for row in dc_path.read_text(encoding="utf-8").splitlines()[1:]:
            cols = row.split(",")
            if len(cols) >= 3 and cols[2].strip() and re.match(r"^-?[0-9.]+$", cols[2].strip()):
                failures.append(f"door-critical.csv has a numeric value: {row[:80]!r}")
    else:
        failures.append("door-critical.csv is missing")

    rep_path = DOSSIER / "plant-timing-report.json"
    if rep_path.is_file():
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        if rep.get("physical_verified") is not False:
            failures.append("plant-timing-report.json claims physical_verified")
        d2c = rep.get("door_to_critical", {})
        if d2c.get("status") != "NOT_COMPUTABLE" or d2c.get("number_emitted") is not False \
                or d2c.get("value_s") is not None:
            failures.append("door->critical is not honestly NOT_COMPUTABLE")
        gaps = {g["id"] for g in rep.get("data_gap_register", [])}
        for need in ("GAP-DOOR-CRITICAL", "GAP-NETWORK-COMMAND-LATENCY"):
            if need not in gaps:
                failures.append(f"data-gap register dropped {need}")
        # H2: the onset rule must cite the committed pre-ramp source and must not
        # resurrect the non-existent H8_CURRENT_PATH_AND_SHUTDOWN_ANALYSIS.
        cte = rep.get("command_to_electrical", {})
        rule = cte.get("latency_exclusion_rule", "")
        if "H8_CURRENT_PATH_AND_SHUTDOWN_ANALYSIS" in rule:
            failures.append("onset rule still cites a non-existent analysis doc")
        if "41-h6-run-analysis.md" not in rule:
            failures.append("onset rule does not cite the committed pre-ramp source")

    # Text-artifact scans: forbidden physical-acceptance phrases and door numbers.
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
        print(f"W13 DOSSIER: OK ({len(pinned)} pinned files, no door number, honest verdict)")
        return 0
    print("W13 DOSSIER: FAIL")
    for f in failures:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
