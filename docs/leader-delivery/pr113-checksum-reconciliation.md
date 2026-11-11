# PR #113 checksum reconciliation

The [frozen-file review](leader-delivery-frozen-file-review.md) and
[Phase 8.2 disposition](phase8-2-frozen-disposition.md) record earlier snapshots.
For the W08, W09 and W13 manifests, the effective Git history is:

1. Member A's PR #95 (`815387d`) supplied correct pins for the six affected
   artifacts. The manifests at integration merge `2cd8023` matched that PR.
2. Owner commit `4c1dc87` restored the frozen manifests, bringing back six
   stale expected hashes alongside five valid owner sidecar pins. The artifact
   bytes still matched PR #95. GitHub Actions run 42960146666 failed the two
   W08 dossier tests against that integrated state.
3. The repaired delivery uses the three manifests under `evidence/A/` as the
   current checksum authority. The six values match the delivered artifact
   bytes and PR #95. All five sidecar entries and all artifact bytes are
   preserved.

The earlier reports and their commit and checksum references remain records
of the snapshots they describe.
