# Pre-merge: owner-owned patch plan (transferrable, sandbox-only so far)

All changes below EXIST ONLY in the disposable sandbox (`p7sandbox`,
`e9681be` + sandbox-side test repairs). The protected owner worktree and
every member PR remain untouched. Transfer happens ONLY after owner
approval, as the commit plan in `premerge-atomic-commit-plan.md`.

## 1. `backend/tests/test_command_path_runner.py` (owner test suite)

- `_run()` now passes `clock_synchronized=True` — labeled `SIMULATION_ONLY`
  in the docstring: no synchronized-clock evidence exists physically; the
  flag exists only to reach the dispatch/ACK/trace stages of the D#90
  contract in offline tests.
- NEW `test_unclaimed_clock_safety_blocks_by_default_under_d90`: no claim →
  `SAFETY_BLOCKED` + `COMMAND_SAFETY_BLOCKED` + "not synchronized" detail +
  clock gate BEFORE expiry in `checks_passed` + nothing dispatched.
- Justification: D#90 (`da82109`) makes the old base-matrix happy path
  impossible; the fail-closed direction is preserved and now tested BOTH
  ways (explicit SIM claim → full path; no claim → blocked).

## 2. `backend/tests/test_command_path_runner_d90.py` (owner D#90 harness)

- Legacy "base happy path" test → replaced by
  `test_unclaimed_clock_safety_blocks_under_d90` (the merged matrix is the
  D#90 matrix; `member_d_matrix == d90-latest` is asserted).
- `_extract_d90` gains the merged-tree fallback: when
  `git archive <ref>` has no ref (sandbox/merged contexts), the tree's own
  `control/src` IS the D#90 source (verified `da82109`) — no source
  invention, no stale-substitution.
- Remaining 1 SKIP is legitimate and documented (the base-refusal test is
  not applicable when the running matrix already carries the D#90 field).

## 3. `backend/tests/test_command_translation.py` + `test_command_ack_integration.py`

- `test_naive_*` now accepts `(CommandTranslationError, ValidationError)`:
  C#69's `Command` envelope (AwareDatetime) rejects naive datetimes one
  layer EARLIER; the fail-closed invariant is unchanged and stronger.

## 4. `backend/tests/test_cross_team_paths.py`

- Paths 5/6 end-to-end test carries the SIMULATION-labeled
  `clock_synchronized=True` claim (D#90 contract compliance).

## NOT changed (verified)

- Every member-owned file (A firmware/tools, B ml, C backend src, D
  control src) — the sandbox merge history shows zero owner-side edits to
  member sources; ownership verified commit-by-commit.
- Every dataset/sidecar byte (see premerge-data-integrity.md).
- The 14 frozen tracked files' CONTENT (they arrive via the owner layer
  snapshot verbatim; see the commit plan for their disposition).
