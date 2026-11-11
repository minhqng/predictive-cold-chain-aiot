# PHASE 8.2 — Tree Equivalence vs Phase 8 candidate

## Reference trees

- Approved Phase 8 candidate tree: `80f788cd0aaf6679d4bd802189b068a1099af06c` (commit `e90335e`)
- Phase 7B.1 tested tree: `5f7dfc084fd4a6041e683ac6ef66e571451d72a9`
- Phase 8.2 atomic final tree (before ledger commit): `80f788cd0aaf6679d4bd802189b068a1099af06c` — **exact tree-object SHA equality with the approved Phase 8 candidate `80f788cd…`**.
- Total tracked files in final tree: **1385** (host-native manifest, excluding pytest caches / egg-info).

## Deviation classification (measured coverage)

- source:   unchanged (0 files)
- tests:    unchanged (0 files)
- runtime:  unchanged (0 files)
- data:     unchanged (0 files)
- evidence: unchanged (0 files)
- docs / metadata (ccupt256SUMs, file-map, and premerge/leader-delivery docs): added/modified only

The exact list of the 22 tracked differences measured by Phase 8 Gate against
the Phase 7B.1 tree is in the Phase 8 Gate report; all 22 are confined to
`docs/leader-delivery/*` (added), `docs/premerge/*` (modified), and
`reb_src_file_map.py` (modified), i.e. delivery-documentation and metadata only.

## Phase 8.2 result

The final atomic tree is byte-level identical to the Phase 8 candidate tree
`80f788cd…`. Verified directly by `git diff e90335e HEAD` (0 files) and by
matching SHA-256 manifests (`12/12 premerge`, `11/11 leader-delivery`).
