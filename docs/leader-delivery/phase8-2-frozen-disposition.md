# PHASE 8.2 — Frozen-File Disposition (14 paths) — actual Git objects

For each of the 14 frozen tracked modifications (from the protected owner
worktree `_owner-w01-w13`), the Phase 8.2 audit compares exact blob identities
across four states and classifies the result.

Legend
- **worktree** = current protected worktree file bytes (SHA-256, 256-hex, abbreviated 12)
- **baseline** = blob at `d22c8d5b…` (original main / member baseline)
- **candidate** = blob at the approved Phase 8 candidate `e90335e` tree `80f788cd…`
- **final** = blob at the Phase 8.2 final atomic tree (target = same tree object)

| Path | worktree | baseline | candidate | Phase 8.2 result |
|---|---|---|---|---|
| docs/00-project-scope-architecture.md | bc581295a0f3 | 88462c539765 | bc581295a0f3 | byte-identical |
| evidence/A/W01/README.md | d3a8458a5f45 | 6910e73d4b83 | d3a8458a5f45 | byte-identical |
| evidence/A/W01/acceptance.md | 30c6e0037d9f | 798935cd1422 | 30c6e0037d9f | byte-identical |
| evidence/A/W01/bom-audit.csv | 932be9cf9dc6 | d6405fe1ff3d | 932be9cf9dc6 | byte-identical |
| evidence/A/W01/freeze-deviation-review.md | e8087dbd0930 | a2ed3d4f5305 | e8087dbd0930 | byte-identical |
| evidence/A/W01/validate_w01.py | 33f6cf5793ae | 8c8844cf1eea | 33f6cf5793ae | byte-identical |
| evidence/A/W03/acceptance.md | 679b8b125c62 | 31847fb024cc | 679b8b125c62 | byte-identical |
| evidence/A/W03/hardware-deviation-and-safety.md | 8af58321d170 | e6788a017612 | 8af58321d170 | byte-identical |
| evidence/A/W03/rs485-pin-and-compatibility.md | f7f1fcd4e89c | 4e23f65d1c23 | f7f1fcd4e89c | byte-identical |
| evidence/A/W08/SHA256SUMS.txt | 4769cec5f043 | c7ec539154fa | 4769cec5f043 | byte-identical |
| evidence/A/W09/SHA256SUMS.txt | 36b00be45b84 | 78d696c34dd0 | 36b00be45b84 | byte-identical |
| evidence/A/W13/SHA256SUMS.txt | 7f093ad6eeba | 25d29d34a281 | 7f093ad6eeba | byte-identical |
| tools/member_a_app/evaluators_extra.py | b6e50d58b782 | 0556c803e1d1 | b6e50d58b782 | byte-identical |
| tools/member_a_app/requirements/w01_w06.py | 3fcf30c4aa9b | a8c2e3985143 | 3fcf30c4aa9b | byte-identical |

## Classification — all 14 paths

**`_OWNER_DELTA_COMMITTED`** for the Phase 8.2 atomic target: the owner
modification is a real delta against the original baseline, and the Phase 8.2
atomic commit sequence has captured that delta inside an actual owner-side
commit (either `8982016` — the scope-architecture doc group — or `32b9f5f` —
the owner-evidence group), verified byte-for-byte against the worktree.

### Rationale per change path

- 11 evidence files (W01/W03/W08/W09/W13) are pinned evidence-side edits, not
  placeholders. Each carries an explicit provenance entry in
  `docs/owner-integration/source-sync/` and preset in the premerge file-map.
- 2 `tools/member_a_app/` files are owner additive modules (evaluator
  extensions and a pinned requirements file), not member-owned source overwrites.
- 1 `docs/00-project-scope-architecture.md` owner revision is the pinned
  scope-architecture doc from `integration/w01-w13-owner-20261110`.

## Final dispositions

| Path | Result |
|---|---|
| docs/00-project-scope-architecture.md | `ALREADY_PRESENT_UPSTREAM` — verified already inherited in candidate content (byte-identical to worktree) + admitted directly through `8982016`. |
| evidence/A/W01/* and evidence/A/W03/* and W08/W09/W13 | `ALREADY_PRESENT_UPSTREAM` — verified byte-identical to the candidate; also carried explicitly in owner-evidence commit `32b9f5f`. |
| tools/member_a_app/evaluators_extra.py, requirements/w01_w06.py | `ALREADY_PRESENT_UPSTREAM` — verified byte-identical to the candidate; also carried explicitly in owner-evidence commit `32b9f5f`. |

## The four-file pending-commit plan discrepancy — resolved

The prior Phase 8 plan still described four files as pending commit in the
sandbox. Per actual Git objects:

1. All four paths exist at `ce9661a` (inherited from main).
2. All four paths exist at `e90335e` (Phase 8 candidate) with the content the
   worktree expects, byte-identical.
3. This means the owner delta was already committed in the candidate tree, not
   held pending.
4. The additional phase 8.2 atomic commits (`8982016`, `32b9f5f`) replicate the
   same content in a cleaner, more-atomic packaging.

Result: **`ALREADY_PRESENT_NO_ADDITIONAL_COMMIT`** for the four-file plan
discrepancy — no new owner commit is needed for those four specifically.
