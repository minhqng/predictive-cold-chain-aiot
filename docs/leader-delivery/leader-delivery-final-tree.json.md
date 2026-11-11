# Leader Delivery Final Tree — combined-tree manifest

Final verified sandbox tree (after Phase 7B.1 test alignment and Phase 7B/7B.1
packaging corrections):

- HEAD commit: `4b25349` ("fix(premerge): rebuild commit-file map from git ancestry")
- Final file-map completion commit (Phase 8): `5d73b1b`
- Phase 7B.1 verified tree id: `5f7dfc084fd4a6041e683ac6ef66e571451d72a9`
  (equiv. content reachable through the Phase 8 re-merge `f7830dcd…`)
- Sandbox: `p8leader` (scratchpad, disposable)

## Verified contents

- 5 member PRs merged as real SHA-preserving merge commits (no squash, no rebase).
- 0 textual conflicts across all 5 merges.
- File counts per member merge: A#94=7, A#95=44, C#69=59, D#90=53, B#102=122
  (exactly matching the GitHub PR head file counts).
- A#95 capture `evidence/A/SOURCES/20261109/s1/s1-20261109T081304Z/`: **6/6 entries
  tracked** (acceptance-verification, read-only-capture-summary, SHA256SUMS,
  trial.json, commands.log, raw/telemetry_raw.log).
- PR #44 (C-W04) NOT re-merged — superseded by content already on main.

## Structural counts (from `premerge-commit-file-map.csv`, normalized to relative paths)

```
main/base                              962
member B (W13 horizon engineering)     122
member C (observability stack)          59
member D (AIW/verification)             53
owner integration layer                 44
member A (acceptance integrity)         44
member A (telemetry remediation)         7
                                    -----
Total                                 1291
```
