# Leader Delivery Source Lock — ColdGuard W01–W13

本 document is the Phase 8 provenance lock for the single combined Leader Integration Delivery PR.

## Reference heads (verified on GitHub in Phase 6, re-pinned through the sandbox DAG)

| Member | PR | Head SHA (full) | Base branch | Stack ancestry |
|---|---|---|---|---|
| A | #94 | `ae23a36fe98fcf1bf6005dd9fcd79b95fb796570` | main | independent |
| A | #95 | `815387d19a3898e6b33ccb65758a554dd0c589e1` | main | independent |
| B | #102 | `824a5389c29ade0e56ecef7ef21eb35c2a379a7b` | feat/b-w12-benchmark-g3-review | b-w04..b-w13 stacked |
| C | #69 | `361e73246a3a6746a39a7e2769dffdfb7b1ce486` | feat/c-w12-* | c-w04..c-w12 stacked |
| D | #90 | `da821094985006945d0306dd7b16be576378bc18` | feat/d-w12-* | d-w04..d-w12 stacked |

Baseline (verified main): `d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85` ("Merge pull request #93 feat/a-dataset-regen").

## Actual integration merge commits in the sandbox (p8leader, cloned from p7sandbox)

| Merge commit | PR | Parent 1 (base) | Parent 2 (member head) | Files introduced |
|---|---|---|---|---|
| `240b393` | #94 | `d22c8d5` | `ae23a36` | 7 |
| `2cd8023` | #95 | `240b393` | `815387d` | 44 |
| `98dc386` | #69 | `2cd8023` | `361e732` | 59 |
| `5f4c859` | #90 | `98dc386` | `da82109` | 53 |
| `ce9661a` | #102 | `5f4c859` | `824a538` | 122 |
| `e9681be` | Owner integration | `ce9661a` | — | 44 (owner layer) |
| `e53f5f2` | Test alignment | `e9681be` | — | owner suites |

Final tested sandbox tree (after Phase 7B.1 test alignment): `f7830dcdd023ecc276df32282741ebb3e17cb263` (commit `4b25349` including Phase 7B packaging corrections — see below).

## Notes

- A#94 and A#95 are independent branches off `main`; both survive as separate merge parents.
- PR #44 (C-W04) is closed/unmerged and SUPERSEDED: its W04 behavior is already on main through `0004_device_twin.py` + `twin_store.py` + W04 tests. It is NOT merged again.
- All 5 member PRs stay OPEN on GitHub until the owner-reviewed Leader Delivery PR is merged.
- Phase 8 does not restart Phase 7B.1. It re-locks the final verified commits and prepares delivery.
