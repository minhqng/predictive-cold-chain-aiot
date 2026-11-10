# Leader Delivery Execution Checklist — for the owner-authorized Git delivery

## Pre-conditions (verified by Phase 8)

- [x] Five member PR heads verified (A#94 `ae23a36…`, A#95 `815387d…`, C#69 `361e732…`, D#90 `da82109…`, B#102 `824a5389…`), base `d22c8d5b…`.
- [x] Combined content assembled and tested in the disposable sandbox (Phase 7B.1 verified tree `f7830dcd…`; Phase 8 re-merge produces equivalent content on `leader/delivery/w01-w13-combined-reviewed`).
- [x] 14 frozen tracked files inventoried, dispositioned, and preserved in the protected worktree.
- [x] 12 atomic-commit plan records in `leader-delivery-atomic-commits.md`.
- [x] Premerge docs re-pinned (12/12 SHA OK) after the Phase 8 packaging correction.

## Owner-authorized operations (one at a time, in order)

1. **Read-only source re-verification on GitHub** — confirm the 5 member PR heads and `main` have not drifted.
2. **Push the delivery branch** `leader/delivery/w01-w13-combined-reviewed` from the sandbox history to the remote.
3. **Open ONE PR** to `main` using `leader-delivery-pr-description.md`.
4. **Independent review** (second reviewer per repo policy).
5. **Merge into `main`** after approval.
6. **Post-merge reconciliation** using `leader-delivery-pr-reconciliation.md` — close each superseded member PR with owner-approved comment.
7. **Run post-merge regression** on `main` (backend services 408, ML 832 + 32/32, control 428 suites).

## NOT authorized as part of this delivery

- Physical TEC / COM / firmware work.
- PR base or head editing of member PRs.
- Force-push, branch deletion, or git history rewriting on published branches.
- Closing member PRs without owner-approved comment.
- W14+ scope.
