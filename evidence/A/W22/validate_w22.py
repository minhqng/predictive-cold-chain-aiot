"""Validator for ColdGuard Member A — W22 Dossier."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

DIR = pathlib.Path(__file__).resolve().parent
REPO = DIR.parents[2]
SUMS_FILE = DIR / "SHA256SUMS.txt"


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if not SUMS_FILE.is_file():
        print("FAIL: SHA256SUMS.txt missing")
        return 1

    lines = SUMS_FILE.read_text(encoding="utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        expected_hash, rel_path = line.split(None, 1)
        target_file = DIR / rel_path
        if not target_file.is_file():
            print(f"FAIL: Missing file {rel_path}")
            return 1
        actual_hash = sha256_file(target_file)
        if actual_hash != expected_hash:
            print(f"FAIL: Hash mismatch for {rel_path} (got {actual_hash}, expected {expected_hash})")
            return 1

    log_path = DIR / "approved-rerun-log.json"
    data = json.loads(log_path.read_text(encoding="utf-8"))
    if len(data.get("approved_reruns", [])) != 0:
        print("FAIL: Dishonest rerun count claimed")
        return 1

    print("W22 DOSSIER: OK (pins verify, rerun governance intact, zero fabricated reruns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
