# Leader Delivery PR Reconciliation Plan — post-merge member PR dispositions

After the owner approves the single Leader Delivery PR and it is merged into `main`,
each original member PR receives an explicit disposition (no false `Merged` labels,
no silent closes, no branch deletion).

## Disposition per member PR

| Member PR | Current state | Post-merge action | Status |
|---|---|---|---|
| A #94 | open | Verify required content in main, then close with supersession comment (owner must approve) | `SUPERSEDED_BY_LEADER_DELIVERY` |
| A #95 | open | Same as A #94 — content verified present (6/6 files of capture 20261109 + 38 others tracked) | `SUPERSEDED_BY_LEADER_DELIVERY` |
| C #69 | open | Same — content verified present through merge `98dc386` | `SUPERSEDED_BY_LEADER_DELIVERY` |
| D #90 | open | Same — content verified present through merge `5f4c859` | `SUPERSEDED_BY_LEADER_DELIVERY` |
| B #102 | open | Same — content verified present through merge `ce9661a` | `SUPERSEDED_BY_LEADER_DELIVERY` |
| C #44 | closed, unmerged | Already superseded on main (W04 twin_store + `0004_device_twin.py` migration); no longer part of the stack | `SUPERSEDED_BY_LEADER_DELIVERY` (pre-existing) |

## Comment template (owner must approve before any close)

```
Integrated through Leader Delivery PR #<NUMBER>. Original member contribution and
provenance preserved; required W01–W13 content verified on main
(<verify commit sha> from the merged Leader Delivery PR). This PR is superseded by
the reviewed combined delivery.
```

Only the owner (or a delegated maintainer per GitHub permission) may post this comment
or close the PRs. Phase 8 does not perform any GitHub write operation.

## Branch handling

Member W14+ work may depend on these feature branches; Phase 8 does not delete branches.
The branch deletion (if desired) happens only after the owner confirms W14+ is not
blocked by it.
