"""Verify the W06 evidence dossier.

    py evidence/A/W06/validate_w06.py

Checks, in order:

1. every file listed in ``SHA256SUMS.txt`` exists and hashes to the pinned value;
2. no flash image (``*.bin``) was committed into the dossier;
3. ``acceptance.md`` still states the honest verdict and does not claim W06 is
   GREEN/PASS/COMPLETE;
4. every generated artifact is labelled host-derived and **not** a physical
   measurement, and no fixture ACK reports an applied cooling state - a dossier
   that ever shows one has been generated against a tree that can actuate, which
   is not what this slice delivers;
5. the traces are honest about what they did not reach: the committed-capture
   trace must report no command lines, and the host demo must not claim
   ``THERMAL_VERIFIED`` for any command;
6. the logs contain the verdicts the requirement names: a duplicate, an expired
   command, and a reset that does not remember;
7. the pins cover the README, acceptance, both test records, the handoff and the
   build evidence.

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

HONEST_VERDICT = "W06 is **not** a GREEN week"
FORBIDDEN_VERDICTS = re.compile(r"\bW06 (PASS|GREEN|COMPLETE|CLOSED)\b")


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

    acceptance = (DOSSIER / "acceptance.md").read_text(encoding="utf-8")
    if HONEST_VERDICT not in acceptance:
        failures.append("acceptance.md no longer states that W06 is not a GREEN week")
    if FORBIDDEN_VERDICTS.search(acceptance):
        failures.append("acceptance.md claims W06 PASS/GREEN/COMPLETE/CLOSED")
    for required_phrase in (
        "Command received by a device: **NO**",
        "Actuation: **NO**",
    ):
        if required_phrase not in acceptance:
            failures.append(f"acceptance.md lost the scope statement {required_phrase!r}")

    fixture_path = DOSSIER / "ack-fixture.json"
    if not fixture_path.is_file():
        failures.append("ack-fixture.json is missing")
    else:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        provenance = fixture.get("provenance", {})
        if provenance.get("is_physical_measurement") is not False:
            failures.append("ack-fixture.json no longer declares itself a non-measurement")
        if provenance.get("is_host_scenario") is not True:
            failures.append("ack-fixture.json no longer declares itself a host scenario")
        for label, entry in fixture.get("fixtures", {}).items():
            fields = entry.get("fields", {})
            if fields.get("applied_cooling") == "ON":
                failures.append(
                    f"fixture {label!r} reports an applied cooling state; this slice must not be "
                    "able to produce one"
                )
            if fields.get("schema") != "1":
                failures.append(f"fixture {label!r} is not a docs/02 command-envelope schema")
        expected = {
            "shipped-unsynchronized": ("SAFETY_BLOCKED", "EPOCH_UNSYNCHRONIZED"),
            "synchronized-accepted": ("ACCEPTED", "NONE"),
            "synchronized-expired": ("EXPIRED", "EXPIRED"),
            "wrong-device": ("REJECTED", "DEVICE_ID_MISMATCH"),
            "duplicate-replay": ("DUPLICATE_CANONICAL", None),
        }
        for label, (status, reason) in expected.items():
            entry = fixture.get("fixtures", {}).get(label)
            if entry is None:
                failures.append(f"fixture {label!r} is missing")
                continue
            got = entry["fields"]
            if got.get("status") != status:
                failures.append(f"fixture {label!r} status is {got.get('status')!r}, not {status!r}")
            if reason is not None and got.get("reason") != reason:
                failures.append(f"fixture {label!r} reason is {got.get('reason')!r}, not {reason!r}")

    for name, must_contain in (
        ("duplicate-command-log.jsonl", ("ACCEPTED", "DUPLICATE_CANONICAL")),
        ("expired-command-log.jsonl", ("EXPIRED",)),
        ("reset-command-log.jsonl", ("ACCEPTED", "OUT_OF_RANGE")),
    ):
        path = DOSSIER / name
        if not path.is_file():
            failures.append(f"{name} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        for token in must_contain:
            if token not in text:
                failures.append(f"{name} no longer contains the verdict {token!r}")
        if '"is_physical_measurement": false' not in text:
            failures.append(f"{name} lost its host-scenario labelling")
        if name == "duplicate-command-log.jsonl" and '"reapplied": "1"' in text:
            failures.append("duplicate-command-log.jsonl shows a replay that applied again")
        # A command log that does not name the command is not evidence about a
        # command: the id is what makes "the same command_id twice" checkable.
        for row_line in [ln for ln in text.splitlines() if ln.strip()]:
            row = json.loads(row_line)
            if "command_id" not in row or "boot_id" not in row:
                failures.append(f"{name} has a row without command_id/boot_id")
            if "status" not in row:
                failures.append(f"{name} has a row without a status verdict")

    acceptance_text = acceptance
    if "A-W06-05" in acceptance_text and "**BLOCKED" not in acceptance_text:
        failures.append("acceptance.md no longer marks A-W06-05 as blocked on C/D and hardware")

    demo = DOSSIER / "trace-host-demo.json"
    if demo.is_file():
        report = json.loads(demo.read_text(encoding="utf-8"))
        reached = report.get("summary", {}).get("reached", {})
        # Nothing in this slice may reach applied evidence. A non-zero count here
        # means either the trace tool started promoting stages again or the demo
        # capture grew frames that were never produced.
        if reached.get("APPLIED_STATE", 0) != 0:
            failures.append("the host demo reports applied-state evidence it cannot have")
        if reached.get("ELECTRICAL_VERIFIED", 0) != 0:
            failures.append("the host demo reports electrical verification it cannot have")
        if report.get("provenance", {}).get("is_physical_measurement") is not False:
            failures.append("trace-host-demo.json no longer declares itself a non-measurement")
        for command in report.get("commands", []):
            if "THERMAL_VERIFIED" in command.get("stages", []):
                failures.append(
                    f"host demo claims thermal verification for {command['command_id']}"
                )
    else:
        failures.append("trace-host-demo.json is missing")

    real = DOSSIER / "trace-committed-w04-capture.json"
    if real.is_file():
        report = json.loads(real.read_text(encoding="utf-8"))
        summary = report.get("summary", {})
        if summary.get("verdict") != "NO_COMMAND_LINES_PRESENT":
            failures.append("the committed-capture trace no longer reports an honest empty result")
        if summary.get("commands_observed") != 0:
            failures.append("the committed-capture trace invented commands")
    else:
        failures.append("trace-committed-w04-capture.json is missing")

    for required in (
        "README.md", "command-parser-tests.md", "physical-command-trace.md",
        "acceptance.md", "handoff-w06.md", "build_contract_artifacts.py",
        "ack-fixture.json", "demo-command-capture.log",
        "duplicate-command-log.jsonl", "expired-command-log.jsonl",
        "reset-command-log.jsonl", "trace-host-demo.json",
        "trace-committed-w04-capture.json",
        "build/20-idf-py-build.log", "build/21-artifact-hashes.txt",
        "build/22-source-hashes.txt",
    ):
        if required not in pinned:
            failures.append(f"{required} is not hash-pinned")

    if not failures:
        print(f"W06 DOSSIER: OK ({len(pinned)} pinned files, honest verdict intact)")
        return 0

    print("W06 DOSSIER: FAIL")
    for failure in failures:
        print(f"  - {failure}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
