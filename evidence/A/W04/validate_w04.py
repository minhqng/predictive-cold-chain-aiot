"""Verify the W04 evidence dossier.

    py evidence/A/W04/validate_w04.py

Checks, in order:

1. every file listed in ``SHA256SUMS.txt`` exists and hashes to the pinned
   value, so a committed serial capture cannot be silently rewritten;
2. no flash image (``*.bin``) sneaked into the dossier, which is the rule
   ``ARTIFACT-MANIFEST.md`` states for this week;
3. ``acceptance.md`` still carries the honest W04 verdict instead of a PASS;
4. every local-only artifact named in the manifest is reported PRESENT or
   ABSENT. Absent is the expected state on a clean checkout: those bytes live
   in Member A's bench worktree, and the validator must not fail because of it.

Exit code 0 only when 1-3 pass. Nothing here touches hardware.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys

DOSSIER = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DOSSIER.parents[2]


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

    pinned = 0
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([0-9a-f]{64})  (.+)$", line.strip())
        if not match:
            if line.strip():
                failures.append(f"unparsable SHA256SUMS line: {line[:80]!r}")
            continue
        digest, rel = match.groups()
        target = DOSSIER / rel
        pinned += 1
        if not target.is_file():
            failures.append(f"missing evidence file: {rel}")
            continue
        actual = sha256(target)
        if actual != digest:
            failures.append(f"hash mismatch: {rel} (want {digest[:12]}… got {actual[:12]}…)")

    stray_bin = sorted(p.relative_to(DOSSIER).as_posix() for p in DOSSIER.rglob("*.bin"))
    if stray_bin:
        failures.append("flash images committed against the manifest rule: "
                        + ", ".join(stray_bin))

    acceptance = (DOSSIER / "acceptance.md").read_text(encoding="utf-8")
    if "W04 PARTIAL" not in acceptance:
        failures.append("acceptance.md no longer states the W04 PARTIAL verdict")
    if re.search(r"\bW04 (PASS|GREEN|COMPLETE)\b", acceptance):
        failures.append("acceptance.md claims W04 PASS/GREEN/COMPLETE")

    manifest = (DOSSIER / "ARTIFACT-MANIFEST.md").read_text(encoding="utf-8")
    local_only = re.findall(r"^\| `[0-9a-f]{64}` \| [^|]+ \| `?([^`|\s]+)`? \|",
                            manifest, flags=re.MULTILINE)
    present = absent = 0
    for rel in local_only:
        if (REPO_ROOT / rel).is_file():
            present += 1
        else:
            absent += 1

    print(f"pinned evidence files verified : {pinned}")
    for failure in failures:
        print(f"FAIL: {failure}")
    print(f"local-only manifest entries    : {present} present, {absent} absent "
          f"(absent = kept in Member A's bench worktree)")
    if failures:
        print(f"VALIDATE_W04: {len(failures)} FAILED")
        return 1
    print("VALIDATE_W04: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
