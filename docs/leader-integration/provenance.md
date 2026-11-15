# Release provenance

The release continues from b65889fdca658100e346c4ad5725ff97269ca12a on the 557e887432d1a72b3d097f92644fe72b809c824e main baseline. The 35 open Member PR head objects remain reachable. C's original final stack was restored by a tree-neutral merge. No Member source branch, original commit or historical PR is rewritten by this release.

## Leader sources

The primary and fallback Leader worktrees were at the same committed tree, 914eec09ed192c5a7959cb2e7df5d20097abf468. Their firmware provenance and paired-enable followups are 6507fa7 and 326ed9f. Leader source is reconstructed in new release commits using reviewed file content. None of these historical Leader branches is merged. The runbook introduced in 156fc58 contained local runtime credentials and its commit lineage remains outside release ancestry. Runtime credentials are provisioned separately.

The compact Vietnamese dashboard, safe inference changes, and tests are based on the newest TEC100 working source. Unreviewed continuous TEC100 firmware and direct AI command dispatch are excluded. The dashboard ARM mutation routes, unscoped arm file, and controller-restart behavior are excluded. The temperature setpoint is preserved as an authenticated desired-state configuration: a bearer operator token (environment-provisioned `CG_OPERATOR_TOKEN`, constant-time compare, fail-closed when unprovisioned) gates a write to the Member D policy target, and the write never dispatches ARM/START or energizes the TEC. The shadow temperature band comes from operator-provisioned environment settings and is display-only on the Dashboard. The hardened boot reconcile tool only updates the Digital Twin when its new boot is supported by dashboard and database observations.

The hardware-facing firmware baseline is preserved unchanged in the release. Uncommitted Member A firmware diffs and new Leader firmware components are excluded from release commits and preserved in the worktree pending physical validation and an explicit Leader decision; see [hardware-baseline.md](hardware-baseline.md) and [final-release-limitations.md](final-release-limitations.md).

## Historical Member heads

An original PR head SHA and the content landed by a historical integration are different checks. The original head refs below still resolve on GitHub. The content is already integrated, so this release does not create empty ancestry merges or apply those changes again.

| PR | Original head | GitHub landing | Reachable integration | Disposition |
| --- | --- | --- | --- | --- |
| [#1](https://github.com/minhqng/predictive-cold-chain-aiot/pull/1) | 8e7aeaf | 3f19d06 | 3f19d06 | HISTORICAL_MERGE_METHOD_EXPLAINS_MISSING_HEAD |
| [#2](https://github.com/minhqng/predictive-cold-chain-aiot/pull/2) | 58b7a13 | 6750275 | 6750275 | HISTORICAL_MERGE_METHOD_EXPLAINS_MISSING_HEAD |
| [#3](https://github.com/minhqng/predictive-cold-chain-aiot/pull/3) | 347ca54 | bd76ed9 | bd76ed9 | HISTORICAL_MERGE_METHOD_EXPLAINS_MISSING_HEAD |
| [#7](https://github.com/minhqng/predictive-cold-chain-aiot/pull/7) | 7d03512 | 77a5fb6 | 1c26465 | CONTENT_ALREADY_PRESENT |
| [#8](https://github.com/minhqng/predictive-cold-chain-aiot/pull/8) | 07a87b1 | 6cc5c96 | f4bf4e1 | CONTENT_ALREADY_PRESENT |
| [#9](https://github.com/minhqng/predictive-cold-chain-aiot/pull/9) | 0d350a5 | fd58ef4 | ab099ec | CONTENT_ALREADY_PRESENT |

The C squash landing trees exactly match their original heads. A's original merge commits are preserved on the remote historical backup at 990e0cf. Each reachable replacement merge tree and replacement Member head tree match the corresponding original, with the same author/committer identities and timestamps. Later owning commits account for subsequent file differences. GitHub contribution graph attribution is not asserted.
