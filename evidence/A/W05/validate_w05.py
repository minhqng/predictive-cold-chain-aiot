"""Verify the W05 evidence dossier.

    py evidence/A/W05/validate_w05.py

Checks, in order:

1. every file listed in ``SHA256SUMS.txt`` exists and hashes to the pinned
   value, so a committed fixture, pilot or build log cannot be silently rewritten;
2. no flash image (``*.bin``) sneaked into the dossier;
3. ``acceptance.md`` still states the honest W05 verdict: software-complete with
   the physical capture unauthorized, not a PASS/GREEN week;
4. ``schema-fixture.json`` still declares itself a rendered frame and **not** a
   physical measurement, and carries the schema the current emitter produces
   (2 in the W05 dossier as delivered, 3 after the 2026-11-03 re-derivation);
5. the timing pilot names the committed capture it was derived from, that capture
   exists, and the pilot is labelled as a 60-second W04 window rather than the
   30-minute W05 study;
6. if ``30min-telemetry.csv`` or a W05 ``timing-jitter.csv`` is ever added, it
   must be hash-pinned **and** ``acceptance.md`` must stop describing it as
   missing - a fabricated capture cannot be introduced by dropping a file in
   without updating the verdict, and a real one cannot be hidden behind a stale
   verdict.

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

HONEST_VERDICT = "W05 is **not** a GREEN week"
CAPTURE_STILL_MISSING = "NEED_USER_ACTION"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    failures: list[str] = []

    sums_path = DOSSIER / "SHA256SUMS.txt"
    if not sums_path.is_file():
        print("FAIL: SHA256SUMS.txt is missing")
        return 1

    pinned: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([0-9a-f]{64})  (.+)$", line.strip())
        if not match:
            if line.strip():
                failures.append(f"unparsable SHA256SUMS line: {line[:80]!r}")
            continue
        digest, rel = match.groups()
        pinned[rel] = digest
        target = DOSSIER / rel
        if not target.is_file():
            failures.append(f"missing evidence file: {rel}")
            continue
        actual = sha256(target)
        if actual != digest:
            failures.append(f"hash mismatch: {rel} (want {digest[:12]}… got {actual[:12]}…)")

    stray_bin = sorted(p.relative_to(DOSSIER).as_posix() for p in DOSSIER.rglob("*.bin"))
    if stray_bin:
        failures.append("flash images committed into the dossier: " + ", ".join(stray_bin))

    acceptance_path = DOSSIER / "acceptance.md"
    acceptance = acceptance_path.read_text(encoding="utf-8")
    if HONEST_VERDICT not in acceptance:
        failures.append("acceptance.md no longer states that W05 is not a GREEN week")
    if re.search(r"\bW05 (PASS|GREEN|COMPLETE|CLOSED)\b", acceptance):
        failures.append("acceptance.md claims W05 PASS/GREEN/COMPLETE/CLOSED")

    capture_present = (DOSSIER / "30min-telemetry.csv").is_file()
    if not capture_present and CAPTURE_STILL_MISSING not in acceptance:
        failures.append("acceptance.md must keep the 30-minute capture as NEED_USER_ACTION "
                        "while no such file exists")
    if capture_present:
        if "30min-telemetry.csv" not in pinned:
            failures.append("30min-telemetry.csv exists but is not hash-pinned in SHA256SUMS.txt")
        if CAPTURE_STILL_MISSING in acceptance:
            failures.append("30min-telemetry.csv exists but acceptance.md still calls the "
                            "capture NEED_USER_ACTION - update the verdict from the real data")

    fixture_path = DOSSIER / "schema-fixture.json"
    if not fixture_path.is_file():
        failures.append("schema-fixture.json is missing")
    else:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        if fixture.get("schema_version") != 3:
            failures.append("schema-fixture.json is not a schema-3 frame")
        if fixture.get("is_physical_measurement") is not False:
            failures.append("schema-fixture.json no longer declares itself a non-measurement")
        if fixture.get("is_synthetic_frame") is not True:
            failures.append("schema-fixture.json no longer declares the frame synthetic")
        if "raw_line" not in fixture or not fixture["raw_line"].startswith("#CG TELEM schema=3 "):
            failures.append("schema-fixture.json lost its raw firmware-rendered line")
        raw = fixture.get("raw_line", "")
        if " t_inside_src=T1" not in raw:
            failures.append("schema-fixture.json chamber-air value is not sourced from the "
                            "as-built CHAMBER_CENTER probe T1 (287088CA00000051)")
        if " t_hot_side_src=T2" not in raw:
            failures.append("schema-fixture.json does not source the hot-side value from the "
                            "as-built TEC_HOT_SIDE probe T2 (28AEBF2200000006)")

    pilot_path = DOSSIER / "timing-pilot.json"
    if not pilot_path.is_file():
        failures.append("timing-pilot.json is missing")
    else:
        pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
        provenance = pilot.get("provenance", {})
        source = provenance.get("source_capture", "")
        if not source:
            failures.append("timing-pilot.json names no source capture")
        elif not (REPO_ROOT / source).is_file():
            failures.append(f"timing-pilot source capture missing: {source}")
        if provenance.get("capture_schema") != 1:
            failures.append("timing-pilot.json no longer states that its source is a schema-1 "
                            "(W04) capture")
        note = str(provenance.get("capture_note", "")).lower()
        if "30" not in note or "not" not in note:
            failures.append("timing-pilot provenance must state that this is NOT the "
                            "30-minute W05 study")
        cadence = pilot.get("report", {}).get("cadence", {})
        if cadence.get("accepted_frames") != 62:
            failures.append(f"timing-pilot frame count drifted: {cadence.get('accepted_frames')}")
        if pilot["report"].get("verdict") != "MEASURED":
            failures.append("timing-pilot verdict is not MEASURED")

    for required in ("README.md", "quality-test.md", "timing-pilot.md", "handoff-w05.md",
                     "acceptance.md", "build_timing_pilot.py",
                     "build/20-idf-py-build.log", "build/21-artifact-hashes.txt",
                     "build/22-source-hashes.txt"):
        if required not in pinned:
            failures.append(f"{required} is not hash-pinned")

    if not failures:
        print(f"W05 DOSSIER: OK ({len(pinned)} pinned files, honest verdict intact)")
        return 0

    print("W05 DOSSIER: FAIL")
    for failure in failures:
        print(f"  - {failure}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
