# Pre-merge: main delivery plan (dependency-aware, owner-approved only)

## Upstream member integration sequence (the DAG-mandated order)

| # | PR | Head | Merge order rationale |
|---|---|---|---|
| 1 | A#94 `fix/a-contract-telemetry-remediation` | `ae23a36` | independent; base main; carries the schema raw fields later readers rely on |
| 2 | A#95 `fix/a-main-acceptance-integrity` | `815387d` | independent of #94; 44 files; W09 reproducibility + new S1/S2 capture acquisition; refreshes the SAME manifests the owner layer also touches (fold-on-merge) |
| 3 | C#69 `feat/c-w13-observability` | `361e732` | carries its full stack c-w05..c-w12 (8 commits); backend command/ACK services the owner layer integrates with |
| 4 | D#90 `feat/d-w13-aiw-readiness` | `da82109` | carries d-w04..d-w12 (9 commits); control matrix (clock gate) changes command-path semantics — merge BEFORE any consumer release |
| 5 | B#102 `feat/b-w13-horizon-engineering` | `824a5389` | carries b-w04..b-w12 (8 commits); ml-only tree — order vs C/D free; placed last to keep the ml/members merge lag zero |
| 6 | Owner integration PR | branch `integration/w01-w13-owner-20261110` + sandbox refinements | last; contains the adapters/tests/sidecars/docs |

Merge mechanics per PR (based on the actual DAG):
- Use **merge commits** (`--no-ff`) — the stacks' internal history stays
  reviewable commit-by-commit; authorship preserved.
- No rebase/cherry-pick of published member branches; no squash of stacked
  histories; PR base branches (b-w12/c-w12/d-w12) need no separate merge —
  their tip commits are contained inside the PR heads (verified ancestry).
- After EACH merge: run the affected suite (below) + `git diff --check`.

## Conflict strategy (pre-measured in the sandbox)

- Expected textual conflicts: NONE between member PRs (disjoint trees).
- The three A#95 manifests merge cleanly against main; the OWNER layer's
  sidecar additions under `evidence/` are additive files (no overlap).
- Fold order for any residual manifest touch: merge line-additions from
  both sides, re-run the dossier validators, re-verify hashes.

## Post-merge regression requirements (per merge)

1. After A#94: `firmware/tools/tests/test_cg_telemetry_schema3_raw.py`,
   `test_contract_artifact_consistency.py`; W06 validators.
2. After A#95: W01/W03/W06/W08/W09/W13 validators + the acceptance-check
   phase; W09 must be OK (20 pinned / 957 rows re-derived).
3. After C#69: backend full suite with services (≈404+).
4. After D#90: control suite (428); the owner d90/D#90 tests as PRIMARY.
5. After B#102: ml suite (≈832; 3 CLI-skip acceptable with the dataset env
   unset; 0 without).
6. After the owner PR: backend full suite (services) + all owner suites;
   the six-path matrix from `premerge-combined-tests.md`.

## Not blocking the software merge

- Missing network command→device latency measurement, USB time sync
  implementation, TEC bench session — REAL_TEC_CONTROL_READINESS gates,
  NOT SOFTWARE_MERGE_READINESS gates (owner decision §9).
- The F3 semantic split is APPROVED by the owner (recorded) — no open
  member decision blocks the software merge.
## Delivery modes (7B §3)

The three delivery modes, distinguished exactly:

1. **GitHub PR merge into its own base branch** (the member stacks): PR
   #69→#90→#102 each merge into its recorded base (`a2eb4fc`/`19b296d`/
   `34435bd` respectively) — GitHub-side, member-owned, then re-targeted to
   `main` by the members; the owner NEVER modifies these PRs' bases.
2. **Direct SHA merge simulation** (what Phase 7 did, sandbox-only):
   `git merge <sha>` inside the disposable clone reproduced each PR's exact
   tree for verification — it is EVIDENCE, never a delivery act.
3. **Owner-approved integration PR targeting main** (the delivery): ONE PR
   from `integration/w01-w13-owner-20261110` (rebased on the post-merge
   main) containing the 12 atomic commits; the owner approves it after the
   member merges + post-merge regressions.
