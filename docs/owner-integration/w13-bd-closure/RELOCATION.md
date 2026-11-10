# W13 B→D closure sidecar relocation (Phase 4, 2026-11-10)

The two owner sidecars were placed under `evidence/A/W13/` during Phase 2B,
which broke Member A's dossier pin-completeness rule (`validate_w13.py`
requires every dossier file to be pinned in the dossier's own
`SHA256SUMS.txt`; Phase 4 is forbidden from editing that pinned manifest).

Owner-owned resolution: relocation outside Member A's dossier, byte-identical
and hash-verified.

| File | sha256 |
|---|---|
| `bd-dependency-closure-20261110.json` | 698ef8c8e44df572c96ad2b5ad7006e11a657779b6ba5d5ca9c363e3280e5ee9 |
| `bd-dependency-closure-20261110.SHA256SUMS.txt` | 5fcba2812d89d4ca2a90d50d0ecf0e8be723608a3c139a3dd2220195998e2109 |

Verification performed:

- pre-move backup copies compared byte-hash-equal (scratchpad, outside repo);
- post-move hashes identical to the pre-move hashes (relocated files are the
  same bytes; nothing regenerated);
- `validate_w13.py` now reports `W13 DOSSIER: OK (19 pinned files, no door
  number, honest verdict)` with exit 0;
- the single code reference (`backend/tests/test_bd_dependency_closure.py`
  `CLOSURE_SIDECAR`) was updated to this location.

The 14 Phase-1 tracked modifications and every member file remain untouched;
no git history, staging or commits were created.
