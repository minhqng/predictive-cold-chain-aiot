# Pre-merge FINAL verdict — Phase 7 + 7B correction (2026-11-10)

## Pinned tested tree (7B)

- **Combined candidate, FINAL and TESTED**: commit `e53f5f2f1348…`, git tree
  **`5f7dfc084fd4a6041e683ac6ef66e571451d72a9`** (= `e9681be` + the owner
  test-alignment commit; complete diff vs the previous combined candidate:
  5 owner test files M + the premerge docs A — see
  `premerge-atomic-commit-plan.md` item 8).
- Verification on the pinned tree: **75 passed / 1 legitimate skip** (the
  seven owner suites, targeted); the 1,664-test full result from the
  pre-freeze tree remains valid (no functional source change between
  `e9681be` and `e53f5f2` — tests/docs only).

## Source-completeness correction (7B)

- **PR #44 (C-W04): SUPERSEDED_BY_CONTENT_IN_TREE** — `0004_device_twin`
  occupies the W04 migration slot exactly once (no duplicate revision-0004
  head); `twin_store.py`, `test_migration_w04.py`, `test_twin.py` present
  and green. PR #44 stays closed/unmerged; merging it would duplicate the
  revision. See `premerge-source-completeness.md`.

## File-map correction (7B)

- `premerge-commit-file-map.csv` rebuilt from ACTUAL git ancestry
  (`--first-parent --full-history --diff-filter=AM`; attribution to the
  merge that INTRODUCED each file): **1,288 rows** = base 961 + owner 255
  + C#69 25 + D#90 16 + A#94 2 + B#102 29 — zero directory-guessing, zero
  duplicates; generated/dev/self-referential artifacts excluded.

## What was built and verified

- **A real combined source tree** in the disposable sandbox
  (`p7sandbox`, branch `phase7-combined` @ `e9681be`), produced by an
  actual git merge sequence over the verified live-GitHub SHAs:
  base `d22c8d5` (= remote `main`, drift-checked twice: unchanged) →
  A#94 `ae23a36` → A#95 `815387d` → C#69 `361e732` → D#90 `da82109` →
  B#102 `824a5389` (fetched by exact SHA into the sandbox) → the owner
  integration layer (one commit).
- **Combined-tree fingerprint**: `docs/premerge/combined-tree-manifest.json`
  (525 tracked engineering files hashed; digest-of-digests
  `7f9f76c3f0ce56ba…`).
- **Zero textual merge conflicts** across all five PR merges (disjoint
  member trees; A=firmware/evidence, C=backend, D=control, B=ml).

## §11 final validation checklist (each item independently verified)

| Requirement | Status |
|---|---|
| Every W01–W13 contribution present in the combined tree | PASS (per-PR file sets merged; B/C/D stacks carried by their PR heads — ancestry verified) |
| Every source SHA pinned + verified live | PASS (5/5 PR heads match the live GitHub API at run start AND end; no drift) |
| B#102 on its actual repaired W12 base | PASS (base `34435bd`, not the stale `a27eeed`; fetched fresh by SHA) |
| A#94 AND A#95 both represented | PASS (two independent merges; no content lost) |
| No member source silently dropped | PASS (merge = full-tree merge; per-commit file lists in the ledger) |
| No dataset lost | PASS (hash + row-count matrix in premerge-data-integrity.md) |
| 14 frozen modifications preserved | PASS (carried verbatim in the owner layer; disposition table per file) |
| Owner integration contributions retained | PASS (one ordered commit set, file map complete — zero unexplained deliverable files) |
| Backend service tests ON the combined candidate | PASS (404 PASS / 1 legitimate SKIP with PostgreSQL+TimescaleDB+Mosquitto live) |
| Cross-team tests exercised the combined source | PASS (six paths executed in-tree; D#90 gate + B#102 horizons + C#69 envelope verified in the same tree) |
| Safety fail-closed protections active | PASS (clock gate blocks unclaimed sync; EPOCH_UNSYNCHRONIZED; no TTL bypass; ACK≠applied preserved end-to-end) |
| Original worktree + member branches unchanged | PASS (sandbox-only writes; protected repos' `git status` identical before/after; no fetch/pull/push/merge outside the sandbox) |
| No commit/push/merge in protected repositories | PASS (all git writes occurred in the disposable sandbox clone only) |

## Combined-suite results (this run, on the combined tree)

- Backend (services): **404 PASS / 0 FAIL / 1 SKIP(legitimate)**.
- ML (B#102 tree): **832 PASS / 0 FAIL / 3 SKIP(CLI-replay; dataset env
  optional)** — the same tree passed 835/3→0 with the dataset dir env set
  in the isolated Phase-6 run.
- Control (D#90 tree): **428 PASS / 0 FAIL**.
- Owner suites: 44 PASS in the targeted re-runs (six paths + closure +
  d90 harness), incl. the corrected D#90-alignment tests.

## Remaining blockers (all non-software, owned)

1. `REQUIRES_CROSS_TEAM_CONTRACT_DECISION` — none open (F3 approved by the
   owner).
2. Member-PR merge authorizations (A#94, A#95, C#69, D#90, B#102) — owner.
3. `REAL_TEC_CONTROL_READINESS` — USB time sync implementation, watchdog,
   bench session with a network-measured command→device latency — future
   physical work; does NOT block the software merge (owner decision).

## VERDICT

**`MERGE_READY_FOR_OWNER_APPROVAL`** — for the combined W01–W13 candidate
as tested here (software scope), conditional on: (a) the five member-PR
merges using the recorded order, (b) the owner-approved atomic commit
sequence for the owner-integration layer, (c) the post-merge regressions
listed per merge.

NOT claimed: `MERGED_TO_MAIN` (no merge performed), no physical/real-service
claims beyond the executed software + service-suite evidence.
