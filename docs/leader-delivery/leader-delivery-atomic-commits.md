# Leader Delivery Atomic Commit Plan

Baseline: 12 owner commit groups from Phase 7/7B/7B.1 planning; Phase 8 groups them into the
final Leader Delivery package without changing actual code content beyond the verified
Phase 7B.1 tree. Every commit below exists inside the disposable sandbox `p8leader` (branch
`leader/delivery/w01-w13-combined-reviewed`), not on GitHub and not in the protected worktree.

## Commit sequence (as executed in the sandbox)

| # | Commit | Type/scope | Purpose | Behaviour change | Frozen-file affected | Risk |
|---|---|---|---|---|---|---|
| 1 | `240b393` — Merge PR #94 | member merge | A#94 telemetry contract remediation (7 files) | member-owned | none | member original |
| 2 | `2cd8023` — Merge PR #95 | member merge | A#95 acceptance integrity + provenance (44 files) | member-owned | W08/W09/W13 SHA256SUMS pins land from member side (see frozen review) | member original |
| 3 | `98dc386` — Merge PR #69 | member merge | C observability stack c-w04..c-w12 (59 files) | member-owned | none | member original |
| 4 | `5f4c859` — Merge PR #90 | member merge | D AIW/verification d-w04..d-w12 (53 files) | member-owned | none | member original |
| 5 | `ce9661a` — Merge PR #102 | member merge | B W13 horizon engineering b-w04..b-w13 (122 files) | member-owned | none | member original |
| 6 | `e9681be` — chore(integration): add owner cross-team integration layer | feat(integration) | Owner command/ACK translators, 6-path runner, owner config | yes (owner-owned) | no (owner-owned files only) | low |
| 7 | `e53f5f2` — test(integration): align owner suites with merged D#90 matrix | test(integration) | Owner tests aligned to D#90 explicit `clock_synchronized` contract and fail-closed invariant | no (test-only) | no | low |
| 8 | `b2586f4` — docs(premerge): record the 7B packaging corrections | docs(qa) | 7B/7B.1 packaging-correction records | no | no | low |
| 9 | `4b25349` — fix(premerge): rebuild commit-file map from git ancestry | fix(evidence) | Corrected attribution table — no member-source edit | no | no | low |
| 10 | `5d73b1b` — docs(evidence): complete file-map A#95 capture entries and repin manifest | docs(evidence) | Add 2 missing evidence/A/SOURCES/20261109 entries + refresh SHA pins | no | no | low |

## Frozen-file disposition (14 tracked files)

All 14 tracked frozen files are preserved unchanged in the *protected worktree* and delivered
through commit #6 (owner integration layer) only where the file is owner-owned at its
destination, never via a direct source edit. Full content and justification live in
`leader-delivery-frozen-file-review.md`; no frozen file is silently overwritten by this plan.

## Rules applied

- No member commit was rewritten; each arrives through SHA-preserving merge.
- No Co-authored-by trailers were added to member commits.
- No secrets, caches, egg-info, `__pycache__` or temporary artifacts are included in the
  delivery tree (verified via `combined-tree-manifest.json` exclusion lists).
