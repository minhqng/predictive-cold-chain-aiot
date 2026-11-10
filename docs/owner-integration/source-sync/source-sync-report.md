# Source synchronization report — Phase 6 (owner-owned, additive)

Owner worktree `_owner-w01-w13` @ `integration/w01-w13-owner-20261110`, base
`d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85`. Remote `main` HEAD verified at
start AND re-checked at end of run: **`d22c8d5b1f...` — unchanged, exactly
the owner base. No source drift occurred during execution.**

## Live GitHub verification (read-only API, 2026-11-10)

- 50 open PRs; 28 merged (closed) PRs. The W01–W13 stacks:
  - B: `#43`(b-w04) → `#46/48/49/50/52/54/58/59`(b-w05..b-w12) → **#102**
    `feat/b-w13-horizon-engineering` @ `824a5389c29ade0e56ecef7ef21eb35c2a379a7b`,
    base = `feat/b-w12-benchmark-g3-review` @ `34435bdba8b4...` (**remote base
    is NOT the stale local `a27eeed` snapshot** — histories diverged, as the
    owner stated).
  - C: `#60`(c-w05) → … → `#68`(c-w12) → **#69**
    `feat/c-w13-observability` @ `361e73246a3a6746a39a7e2769dffdfb7b1ce486`,
    base = `feat/c-w12-platform-baseline` @ `a2eb4fc63307`.
  - D: `#81`(d-w04) → … → `#89`(d-w12) → **#90**
    `feat/d-w13-aiw-readiness` @ `da821094985006945d0306dd7b16be576378bc18`,
    base = `feat/d-w12-g3-readiness` @ `19b296de0380`.
  - A remediation: **#94** `fix/a-contract-telemetry-remediation` @
    `ae23a36fe98f...` (7 files: schema raw fields + HANDOFF regen + tests) and
    **#95** `fix/a-main-acceptance-integrity` @ `815387d19a38` (44 files) —
    both from main base, independent, unmerged.
  - Note: `feat/a-w24-final-acceptance` (7dc7cf8) is an ancestor of base —
    it is already inside main; it is NOT an open remediation.

## Missing / stale / divergent sources found

1. **B#102 head `824a5389` was absent** from the local object store, and the
   local `origin/feat/b-w12-benchmark-g3-review` (`a27eeed`) is a stale
   snapshot of #102's actual base (`34435bd`). Earlier phase evidence that
   used `a27eeed` as a stand-in for "#102 compatibility" is therefore
   superseded by this run's direct HEAD verification.
2. C-W13's stack files (#60–#68 heads) are not standalone local objects;
   they are verified THROUGH the #69 head tree (same SHAs confirmed by
   GitHub API). D likewise through the #90 head tree.
3. C-W01..W04 line (`#47` merged into a non-main base) sits outside both
   main ancestry and the #69 stack — recorded `DIVERGED`, needs member
   confirmation; it predates the W13 integration scope (not referenced by
   any W01–W13 owner adapter).

## Snapshots acquired (SHA-pinned, outside the repository)

- B#102 full source tree via codeload tarball
  `...tar.gz/824a5389c29ade0e56ecef7ef21eb35c2a379a7b`
  (tarball sha256 `eb0d7064d8774cc3ada32defc1ca12b6619c1086c33cebf0d4bdb1e78273f028`),
  extracted to the session disposable dir; integrity of the exact revision
  is guaranteed by the SHA-pinned codeload URL; local `git` metadata was
  never touched.
- A#94/A#95/C#69/D#90 objects already exist locally and their SHAs were
  re-verified against the live GitHub API (identical).

## What was previously tested against obsolete/tincomplete source

- All prior "B compatibility" statements (ml 162 PASS, closure runs) were
  executed against the BASE ml tree, not B#102. This run replaces them with
  the real-head results below.

## Newly verified (this run)

1. **B#102 real head**: full ml suite **835 PASS / 0 FAIL** (its own uv
   lock, frozen, with xgboost); W13 horizon suite alone **32/32 PASS**
   including the 3 CLI replay proofs once COLDGUARD_W13_A_DATASET_DIR pointed
   at the committed A 20261107 dataset (the same pinned data the owner
   closure uses; B itself pins dataset sha `f028441d...`).
2. Owner-critical B modules `observations/labels/windows/splitting` at
   `824a5389` are byte-identical to base (verified hashes) — the owner
   B→D closure is **structurally unaffected**.
3. **Owner closure executed against B#102's real `coldguard_ml`resolves**
   (cached-import probe): output **byte-equal to the committed owner sidecar**
   (`docs/owner-integration/w13-bd-closure/bd-dependency-closure-20261110.json`).
4. B#102 horizon engineering assertions verified in source and by tests:
   `CANDIDATE_HORIZONS_S = (30, 60, 120, 300)` (identical to the owner's
   frozen set); `NOT_ESTIMABLE` distinct from zero everywhere including
   door→critical and AIW; 300 s retained for sensitivity only — no primary
   horizon is frozen; real-population metrics stay
   `REAL_METRICS_NOT_ESTIMABLE`; the locked test partition is never read.
5. A#94 re-verified against its real head earlier this session (its 9/9
   tests + gateway/trace probes under the PR schema), and A#94's head was
   re-confirmed unchanged (`ae23a36`) by the live API today.

## Data / evidence reconciliation

- 18-run/9,293-frame dataset, 9 accepted runs, 3,721 admitted observations:
  hashes re-verified earlier phases, and now additionally consumed
  end-to-end by B#102's own CLI replay proofs — data is byte-compatible with
  the real B#102 tooling (the PR's pinned dataset sha `f028441d...` matches
  the committed export the closure uses).
- No upstream data changes were observed this run (A#95's dataset additions
  were already accounted in earlier phases; main is unchanged).
- W09 reproducibility: verified FIXED at A#95 (`815387d`) in a disposable
  copy — unchanged today.
