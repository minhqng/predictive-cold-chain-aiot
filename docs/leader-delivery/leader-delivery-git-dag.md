# Leader Delivery Git DAG — W01–W13

## Proposed DAG for the single Leader Delivery PR

Member integration layer (verified sandbox merges, SHA-preserving, `--no-ff`):

```
main (d22c8d5)
└─ 240b393  Merge PR #94: telemetry contract remediation          (A#94, parent2 = ae23a36)
   └─ 2cd8023  Merge PR #95: acceptance integrity + provenance    (A#95, parent2 = 815387d)
      └─ 98dc386  Merge PR #69: C observability stack (c-w04..c-w12) (C#69, parent2 = 361e732)
         └─ 5f4c859  Merge PR #90: D AIW/verification (d-w04..d-w12)  (D#90, parent2 = da82109)
            └─ ce9661a  Merge PR #102: B W13 horizon engineering (b-w04..b-w13)  (B#102, parent2 = 824a538)
               └─ e9681be  chore(integration): owner cross-team integration layer
                  └─ e53f5f2  test(integration): align owner suites with merged D#90 matrix
                     └─ b2586f4  docs(premerge): record the 7B packaging corrections
                        └─ 4b25349  fix(premerge): rebuild commit-file map from git ancestry
                           └─ 5d73b1b  docs(evidence): complete file-map A#95 capture entries and repin manifest
```

## Merge mode

- Every member PR arrives as a **real SHA-preserving merge commit** — original member commits keep Author / AuthorDate / body, joined unchanged into the delivery branch.
- No squash, no rebase, no rewrite of member history.
- The A#94 / A#95 overlap: both merge cleanly (verified — 0 textual conflicts across all 5 merges).
- PR #44 (C-W04) is superseded by content already integrated on main; it is not merged again.

## Delivery branch

`leader/delivery/w01-w13-combined-reviewed` (created only in the disposable sandbox `p8leader`).

After the owner approves the delivery:
1. Push `leader/delivery/w01-w13-combined-reviewed` from the sandbox *history only if the owner explicitly commands it*.
2. Open ONE PR to main with the exact content of final tree `5f7dfc08…` (the 7B.1 verified tree, equivalently re-created through this DAG).
3. After merge, post the reconciliation comment from `leader-delivery-pr-reconciliation.md` on each member PR (owner must approve each close).
