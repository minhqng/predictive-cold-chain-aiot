# PHASE 8.2 — GitHub Delivery Runbook (after owner approval)

## Preconditions

- Owner reviews and explicitly approves this document.
- The delivery branch `leader/delivery/w01-w13-atomic-reviewed` (sandbox
  `p8atomic`) is intended to be recreated as ONE branch holding the atomic
  commit sequence.

## Exact commands (proposed, NOT executed; no GitHub write in Phase 8.2)

Inside the disposable sandbox `p8atomic`:

```bash
# 1. Verify the finished candidate one last time
git rev-parse HEAD                  # actual final HEAD  (verify same value reported in phase8-2-final-verdict.md)
git rev-parse HEAD^{tree}           # expected 80f788cd0aaf… (exact Phase 8 tree)
git log --oneline --first-parent ce9661a..HEAD | wc -l   # 14 atomic commits
for h in ae23a36 815387d 361e732 da82109 824a5389; do
  git merge-base --is-ancestor $h HEAD && echo "ANCESTOR-OK $h" || echo "MISSING $h"
done

# 2. (Optionally) push the branch to GitHub — owner has to authorize this explicitly
#    and may choose the target remote and any credential-handling policy.
# git push <authorized-remote> leader/delivery/w01-w13-atomic-reviewed

# 3. Open ONE PR to main with the description from leader-delivery-pr-description.md.

# 4. After the review/merge of that PR, post the reconciliation comment from
#    leader-delivery-pr-reconciliation.md on each original member PR.
```

## NOT authorized here

- `git push`, GitHub PR create/merge, PR base/head edits, member-PR close.
- Force-push / branch deletions.
- Physical TEC, serial, firmware work.
- W14+ scope.

## Protected-repository integrity (asserted before delivery)

- HEAD stays `d22c8d5` ("Merge pull request #93 …"),
- status = 37 listed lines (14 frozen tracked + untracked owner content),
- `git diff --check` OK,
- no commit, no staged change, no ref change in the protected worktree.
