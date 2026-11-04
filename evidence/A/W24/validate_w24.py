"""Validator for ColdGuard Member A — W24 Dossier.

A-W24-04 proof pairing: the census must be checked against the repository, not
against a number inside itself. The previous version asserted
`weeks_accounted_for == 24`, which only re-read the claim it was meant to verify.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

DIR = pathlib.Path(__file__).resolve().parent
REPO = DIR.parents[2]
SUMS_FILE = DIR / "SHA256SUMS.txt"
CENSUS_FILE = DIR / "acceptance-census.json"

# Where each week's Member A dossier is expected to live, relative to repo root.
# W23 delivers the release-candidate package under evidence/A/RC/, not under W23/.
WEEK_DOSSIER_DIR = {w: f"evidence/A/W{w:02d}" for w in range(1, 25)}
WEEK_DOSSIER_DIR[23] = "evidence/A/RC"

# Keys emitted by firmware/tools/cg_w24_final_freeze.collate_acceptance_census().
TOOL_CENSUS_KEYS = {
    "expected_week_count",
    "delivered_week_count",
    "all_weeks_accounted_for",
    "physical_runs_verified",
    "software_contract_ready",
    "acceptance_verdict",
    "handover_verdict",
}


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_pins(fails: list[str]) -> None:
    if not SUMS_FILE.is_file():
        fails.append("SHA256SUMS.txt missing")
        return
    pinned: set[str] = set()
    for line in SUMS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        expected_hash, rel_path = line.split(None, 1)
        rel_path = rel_path.strip().replace("\\", "/")
        pinned.add(rel_path)
        target = DIR / rel_path
        if not target.is_file():
            fails.append(f"pinned file missing: {rel_path}")
            continue
        actual = sha256_file(target)
        if actual != expected_hash:
            fails.append(f"hash mismatch for {rel_path} (got {actual}, expected {expected_hash})")
    # Only the pin file itself cannot carry its own digest; every other dossier file
    # must be pinned or it cannot be audited.
    for present in sorted(p.name for p in DIR.iterdir() if p.is_file()):
        if present not in pinned and present != SUMS_FILE.name:
            fails.append(f"unpinned dossier file: {present} is not covered by SHA256SUMS.txt")


def check_references(census: dict, fails: list[str]) -> None:
    for key, value in census.items():
        if not key.endswith("_reference") or not isinstance(value, str):
            continue
        if not (REPO / value).is_file():
            fails.append(
                f"unresolved reference: {key} points at {value!r}, which is absent from this tree"
            )


def check_weeks(census: dict, fails: list[str], warns: list[str]) -> None:
    claimed = census.get("delivered_week_count")
    if not isinstance(claimed, int):
        fails.append("census has no integer delivered_week_count")
        return
    supported = []
    unsupported = []
    for week, rel in sorted(WEEK_DOSSIER_DIR.items()):
        if (REPO / rel).is_dir():
            supported.append(week)
        else:
            unsupported.append(week)
    if claimed > len(supported):
        fails.append(
            f"weeks_accounted_for claims {claimed} but only {len(supported)} week dossiers exist "
            f"in this tree; absent: "
            + ",".join(f"W{w:02d}" for w in unsupported)
            + " (delivered on sibling branches that are not ancestors of this one)"
        )
    if not census.get("open_hardware_gates_count"):
        return
    # The generated census reports readiness as booleans plus a verdict, not a free-text
    # status string, so the agreement check has to read those.
    if census.get("physical_acceptance_ready"):
        fails.append(
            f"physical_acceptance_ready is true while "
            f"{census['open_hardware_gates_count']} hardware gates are open"
        )
    verdict = str(census.get("acceptance_verdict", ""))
    if verdict == "PHYSICALLY_ACCEPTED" or "FULLY_ACCEPTED" in str(census.get("handover_verdict", "")):
        fails.append(
            f"acceptance_verdict={verdict!r} / handover={census.get('handover_verdict')!r} "
            f"while {census['open_hardware_gates_count']} hardware gates are open"
        )
    # The gate list must come from a register that is actually delivered, otherwise the
    # count is an assertion about hardware state with no source.
    register = WEEK_DOSSIER_DIR[23] + "/remaining-hardware-gates.md"
    if not (REPO / register).is_file():
        fails.append(f"gate register {register} is absent, so the open-gate count is unsourced")
    else:
        listed = set(re.findall(r"H-GATE-[0-9]+",
                                (REPO / register).read_text(encoding="utf-8", errors="replace")))
        reported = set(census.get("open_hardware_gates", []))
        if reported and reported != listed:
            fails.append(
                f"census gates {sorted(reported)} do not match the delivered register "
                f"{sorted(listed)}"
            )
    warns.append(
        "open hardware gates remain: "
        f"{census['open_hardware_gates_count']} recorded, physical acceptance cannot be claimed"
    )


def check_generated_census(census: dict, fails: list, repo: pathlib.Path) -> None:
    """The committed census must be byte-reproducible from the delivered generator.

    Comparing the file against a freshly generated one removes the whole class of
    hand-authored acceptance claims: a stale, edited or invented census simply stops
    matching its own source of truth.
    """
    tools = repo / "firmware" / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    try:
        from cg_w24_final_freeze import generate_acceptance_census
    except Exception as exc:  # noqa: BLE001
        fails.append(f"census generator is not importable, cannot verify provenance: {exc}")
        return
    expected = generate_acceptance_census(repo).encode("utf-8")
    if CENSUS_FILE.read_bytes() != expected:
        fails.append(
            "acceptance-census.json is not reproducible from "
            "cg_w24_final_freeze.generate_acceptance_census(); the committed census and the "
            "delivered repository disagree"
        )


def main() -> int:
    fails: list[str] = []
    warns: list[str] = []

    if not CENSUS_FILE.is_file():
        print("FAIL: acceptance-census.json missing")
        return 1
    census = json.loads(CENSUS_FILE.read_text(encoding="utf-8"))

    check_pins(fails)
    check_references(census, fails)
    check_weeks(census, fails, warns)

    # A census that does not come from the tool carries no evidence binding, so it
    # cannot be trusted as proof of anything. Warn-only let a hand-authored file pass.
    check_generated_census(census, fails, REPO)
    claimed = str(census.get("acceptance_verdict", "")) + str(census.get("handover_verdict", ""))
    if "ACCEPT" in claimed.upper() and "BLOCK" not in claimed.upper():
        if not census.get("physical_evidence"):
            fails.append(
                f"census asserts {claimed!r} without any physical_evidence records to re-verify"
            )
        else:
            sys.path.insert(0, str(REPO / "firmware" / "tools"))
            from cg_w24_final_freeze import verify_physical_evidence
            again = verify_physical_evidence(
                census["physical_evidence"], REPO,
                census.get("expected_hardware_config_id"),
            )
            if again.independent_run_count < census.get("physical_runs_verified", 0):
                fails.append(
                    f"census claims {census['physical_runs_verified']} verified runs but "
                    f"re-verification finds {again.independent_run_count}"
                )

    for message in fails:
        print(f"FAIL: {message}")
    for message in warns:
        print(f"WARN: {message}")

    if fails:
        print(f"W24 DOSSIER: REJECTED ({len(fails)} failed check(s))")
        return 1
    print("W24 DOSSIER: OK (pins verify, references resolve, week claims are supported "
          "by dossiers present in this tree)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
