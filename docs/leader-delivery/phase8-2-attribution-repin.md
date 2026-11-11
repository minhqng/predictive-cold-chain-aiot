# PHASE 8.2 — Terminal Git Reference After Owner Attribution Repin

## Scope executed (owner-authorized; Git metadata only)

The owner (GitHub account `giaback`) authorized rewriting exactly the linear
owner range of 17 commits below — the 14 owner atomic commits plus the 3
terminal Phase 8.2 documentation commits — to carry the owner's real Git
identity and the project's Conventional Commit types. The rewrite was executed
verbatim: 17 commits, nothing above or below the range.

- Range: `ce9661a` (last member merge, B #102) .. pre-attribution terminal HEAD
- Author/Committer after the rewrite (17/17): `giaback <dlbach2005@gmail.com>`
- Content: unchanged — `git diff <pre-attribution terminal HEAD> HEAD` = 0 files
- Final tree: `1f7a2283dbf6979cde3ad645c1885ae452a9b018` — unchanged by the rewrite
- AuthorDate: preserved 17/17 at the original values; CommitterDate after the
  rewrite equals the original commit dates (measured 2026-11-11
  02:06:51–02:21:39 +0700; no date reset)
- Subjects: 14 unchanged; exactly 3 normalized from `evidence(a):` to
  `docs(evidence):` (ledger rows 7, 8, 12)
- Member/base history below `ce9661a` untouched: all five member PR heads
  (`ae23a36`, `815387d`, `361e732`, `da82109`, `824a538`) remain the same
  objects and ancestors of the terminal HEAD
- Pre-attribution chain preserved at ref
  `leader/delivery/w01-w13-atomic-reviewed-preattrib` (terminal `4360a444`)

## Old → new commit mapping (terminal chain, oldest → newest)

| # | Pre-attribution | Terminal | Subject (type after normalization) |
|---|---|---|---|
| 1 | `cc5b527` | `467c256` | feat(commands): add device serial translation for the backend envelope |
| 2 | `c0227ab` | `33be9aa` | feat(ack): translate device CMDACK records to CommandAck envelopes |
| 3 | `6307f27` | `263d9a1` | feat(commands): add fail-closed command and ACK correlation bridge |
| 4 | `375ee30` | `c248f2f` | feat(backend): add cross-team data hand-off adapters |
| 5 | `5caa11c` | `9c9e6eb` | feat(backend): add owner command-path composition runner |
| 6 | `a7bbe3b` | `577a4f8` | test(tools): cover the MAX3485 variant in the member A app harness |
| 7 | `160014b` | `84b587f` | docs(evidence): add healthy-ranges and door-critical analysis sidecars |
| 8 | `a8db671` | `6105ffa` | docs(evidence): record W06 command-path integration runs |
| 9 | `6b6e46d` | `e0275c3` | docs(qa): record the A-to-D verification semantics decision |
| 10 | `8982016` | `4e5f9a4` | docs(integration): add owner source sync and scope architecture records |
| 11 | `68103bb` | `bfcad23` | fix(evidence): add the reproducible source-file-map dev tool |
| 12 | `32b9f5f` | `4c1dc87` | docs(evidence): preserve the 14 owner-frozen tracked modifications |
| 13 | `09e26fe` | `c72862a` | docs(qa): add the premerge verification dossier |
| 14 | `e75ec86` | `5b95647` | docs(qa): add the leader delivery packaging dossier |
| 15 | `edabbb9` | `a6818a4` | docs(qa): record the phase8.2 atomic repackaging verification |
| 16 | `9df99b3` | `7825524` | docs(qa): record the phase8.2 final verification verdict |
| 17 | `4360a44` | `cddce2a` | docs(qa): pin the phase8.2 terminal verdict and manifest |

## Repin

This commit is the terminal reference after the attribution rewrite. Earlier
Phase 8.2 documents (`phase8-2-atomic-commit-ledger.md`,
`phase8-2-frozen-disposition.md`, `phase8-2-final-verdict.md`,
`phase8-2-github-delivery-runbook.md`) pin the pre-attribution measured states;
those are historical audit records and were intentionally not modified. The
pre-attribution column above is the cross-reference for those records.

## Verification measured at this terminal state

- Content diff vs the pre-attribution terminal HEAD: only this file added and
  the leader-delivery manifest extended (docs-only) — zero source, test,
  runtime, data or evidence change
- Identity audit of the 17 rewritten commits: 17/17 giaback,
  `dlbach2005@gmail.com`, 0 residue of any other identity in the range
- Member ancestry 5/5 PASS + base `d22c8d5` PASS
- 14 frozen tracked paths: SHA256 re-measured, byte-identical to the
  frozen-disposition pins
- Manifests: `docs/premerge/.SHA256SUMS.txt` 12/12 OK;
  `docs/leader-delivery/.SHA256SUMS.txt` fully OK (20 entries, includes this file)
- `git fsck --full`: no corruption
- Protected owner worktree: untouched (HEAD `d22c8d5`, status 37 lines)
