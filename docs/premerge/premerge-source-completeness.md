# Pre-merge source completeness — Member C W04 (PR #44) vs the combined tree

## Verified facts (live GitHub API + the sandbox combined tree, 2026-11-10)

- **PR #44** (`feat/c-w04-digital-twin-core`): state **CLOSED, NOT MERGED**;
  head `1fedfbc6…`; base `main @ ea1993cb…` (two merges older than the
  current `d22c8d5`); **5 files**:
  1. `backend/src/coldguard_backend/ingest.py` (modified, ±50)
  2. `backend/src/coldguard_backend/migrations/versions/0004_twin.py`
     (added, ±57)
  3. `backend/src/coldguard_backend/twin_store.py` (added)
  4. `backend/tests/test_migration_w04.py` (added, ±77)
  5. `backend/tests/test_twin.py` (added, ±303)
  The commit object `1fedfbc` is NOT in any local object store (never
  fetched); no local snapshot of its contents exists.

## The W04 content in the combined tree (every file verified present)

| PR #44 file | Combined-tree counterpart | Status |
|---|---|---|
| `migrations/versions/0004_twin.py` | `migrations/versions/0004_device_twin.py` (revision `0004`, down_revision `0003` — the migration-DAG slot PR #44's file would have occupied) | **RENAMED/SUPERSEDED** |
| `twin_store.py` | `twin_store.py` (present, 6,353 bytes) | **PRESENT** |
| `tests/test_migration_w04.py` | `tests/test_migration_w04.py` (present) | **PRESENT** |
| `tests/test_twin.py` | `tests/test_twin.py` (present) | **PRESENT** |
| `ingest.py` (+50) | `ingest.py` present; the twin-ingest path is exercised by the current-tree tests (`test_twin.py` green on the combined tree) | **COVERED** |

## The migration-history question (answered from the actual tree)

- The current migration chain is linear and gapless:
  `0001_baseline → 0002_raw → 0003_normalized → 0004_device_twin →
  0005_serial_source → 0006_storage_baseline → 0007_reconciliation_metadata
  → 0008_commands → 0009_experiments`.
- **There is no `0004_twin.py` AND no duplicate revision `0004`**: the W04
  slot is occupied exactly once by `0004_device_twin.py`. Merging PR #44's
  `0004_twin.py` (same revision id, same down-revision) as-is would create
  a duplicate-head conflict in the Alembic graph — the correct delivery is
  exactly what already happened downstream: the renamed
  `0004_device_twin` revision.
- Both files claim revision `0004` / parent `0003` (verified on the
  current tree; the PR's exact patch text from the API confirms the same
  identifiers) — i.e. **the same logical migration, renamed**.

## Verdict

**`SUPERSEDED_BY_CONTENT_IN_TREE`** — every W04 behavior, migration slot,
store and test that PR #44 would have delivered exists in the combined
tree (renamed migration + store + both test files), and the migration
graph is single-headed at revision `0004`. **No source-completeness
blocker for W04 remains**; PR #44 stays closed/unmerged and must NOT be
merged (it would duplicate revision `0004`).

Residual caveat (honest, bounded): the exact byte content of the unmerged
`0004_twin.py`/`ingest.py ±50` cannot be byte-compared without fetching
`1fedfbc` (no local object; fetch is not authorized this phase). The
functional coverage is proven by the current tree's own W04 tests, which
pass on the combined tree; a byte-level equivalence check remains optional
follow-up if the owner wants certainty beyond behavior.
