# Leader Delivery Frozen-File Review — 14 Tracked Modifications

These 14 files are modified tracked entries in the protected owner worktree
(`C:\Users\dlbac\Downloads\coldguard-repo\_owner-w01-w13`, branch
`integration/w01-w13-owner-20261110`, baseline `d22c8d5b`). They are user data and
previously authorized owner work. This Phase 8 review records, per file, the exact
current hash, whether the same path is affected by any member PR, whether the change
is user evidence that must remain, whether the logic is owner-owned, and the final
safe delivery disposition. No file is modified by Phase 8.

## Exact path-by-path inventory

| # | Path | Current SHA256 (16) | Member-PR collision? | Nature | Disposition |
|---|---|---|---|---|---|
| 1 | `docs/00-project-scope-architecture.md` | `bc581295a0f3f31e` | no (no member PR touches it) | canonical doc owner review | `CANONICAL_DOC_REVIEW` |
| 2 | `evidence/A/W01/README.md` | `d3a8458a5f45c4bd` | no | owner evidence update | `PRESERVE_AS_ORIGINAL_EVIDENCE` |
| 3 | `evidence/A/W01/acceptance.md` | `30c6e0037d9fb189` | no | owner evidence update | `PRESERVE_AS_ORIGINAL_EVIDENCE` |
| 4 | `evidence/A/W01/bom-audit.csv` | `932be9cf9dc643c0` | no | owner evidence update | `PRESERVE_AS_ORIGINAL_EVIDENCE` |
| 5 | `evidence/A/W01/freeze-deviation-review.md` | `e8087dbd09308894` | no | owner evidence update | `PRESERVE_AS_ORIGINAL_EVIDENCE` |
| 6 | `evidence/A/W01/validate_w01.py` | `33f6cf5793aed8f3` | A#94 also touches validators in `tools/member_a_app/…` (different file: `validators/…`); path itself untouched | owner-owned validator extension kept | `SOURCE_CHANGE_REQUIRES_DECISION` (owner-only; member-facing copy is upstream `validate_w01.py` already integrated) |
| 7 | `evidence/A/W03/acceptance.md` | `679b8b125c62145c` | no | owner evidence update | `PRESERVE_AS_ORIGINAL_EVIDENCE` |
| 8 | `evidence/A/W03/hardware-deviation-and-safety.md` | `8af58321d170b065` | no | owner evidence update | `PRESERVE_AS_ORIGINAL_EVIDENCE` |
| 9 | `evidence/A/W03/rs485-pin-and-compatibility.md` | `f7f1fcd4e89cd5ba` | no | owner evidence update | `PRESERVE_AS_ORIGINAL_EVIDENCE` |
| 10 | `evidence/A/W08/SHA256SUMS.txt` | `4769cec5f0438405` | A#95 (acceptance-integrity refresh) | manifest pins refresh | `UPSTREAM_ALREADY_FIXED` (A#95 lands its own pins through the member merge; owner copy retained as historical evidence) |
| 11 | `evidence/A/W09/SHA256SUMS.txt` | `36b00be45b84b143` | A#95 | manifest pins refresh | `UPSTREAM_ALREADY_FIXED` |
| 12 | `evidence/A/W13/SHA256SUMS.txt` | `7f093ad6eeba43f8` | A#95 | manifest pins refresh | `UPSTREAM_ALREADY_FIXED` |
| 13 | `tools/member_a_app/evaluators_extra.py` | `b6e50d58b782e2c0` | no | owner additive evaluator | `MIGRATE_TO_OWNER_ADDITIVE_FILE` |
| 14 | `tools/member_a_app/requirements/w01_w06.py` | `3fcf30c4aa9b0898` | no | owner additive requirement | `MIGRATE_TO_OWNER_ADDITIVE_FILE` |

## Notes on the three A manifest overlaps

`evidence/A/W08|W09|W13/SHA256SUMS.txt` overlap with A#95 (acceptance-integrity
refresh). Disposition is `UPSTREAM_ALREADY_FIXED`: the member PR brings its own
correct evidence pins into the tree through the merge, and the owner-modified copies
are preserved in the owner worktree as historical evidence. No manifest entry is
silently overwritten — the final tree keeps the member-PR version, and the owner's
pre-refresh versions stay recorded here (hash column above) for provenance.

## Delivery packaging

All 14 files are delivered inside the owner integration layer commit
(`e9681be chore(integration): add owner cross-team integration layer`), never inside
member-only commits. If a member PR later produces its own refresh of the same file,
the Leader must re-run this review and reconcile; nothing is silently overwritten.
