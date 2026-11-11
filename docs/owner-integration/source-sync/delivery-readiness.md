# Delivery readiness — Phase 6 (source-synchronized)

## Member PR incorporation order (per live GitHub, 2026-11-10)

1. **A#94** (`ae23a36`, base main) — telemetry schema raw fields + HANDOFF
   probe regen; owner paths 1/5/6 already revalidated on this exact source.
2. **A#95** (`815387d`, base main) — W09 reproducibility + pins + acceptance
   integrity; fold the three shared manifest files carefully (see below).
3. **C#69** (`361e732`) **with its stacked ancestors** c-w05..c-w12
   (#60..#68; the PR carries them) — after merge, run the owner backend suite
   and the C service tests (PostgreSQL/Mosquitto needed).
4. **D#90** (`da82109`) **with its stack** d-w04..d-w12 (#81..#89) — after
   merge, the owner d90 tests become the primary matrix (verdicts flip to
   SAFETY_BLOCKED for unsynchronized evidence, by design).
5. **B#102** (`824a5389`) **with its stack** b-w04..b-w11 — real-head
   verification is already complete (835 PASS including 32/32 horizon proofs
   on the pinned A dataset); merge order relative to C/D is free (independent
   stacks); place before the owner PR.
6. **Owner integration PR** (single PR; commit groups as Phase 5 §11).

## The 14 frozen tracked files — disposition (no destructive migration)

- `evidence/A/W08/SHA256SUMS.txt`, `evidence/A/W09/SHA256SUMS.txt`,
  `evidence/A/W13/SHA256SUMS.txt`: **joint append** with A#95's refreshed
  pins — keep both owners' lines in one file, then re-verify every hash
  (lossless; independently checkable). These are the only collisions.
- `evidence/A/W01/README.md`, `acceptance.md`, `bom-audit.csv`,
  `freeze-deviation-review.md`; `W03/*` docs ×3: preserve as original
  evidence; `CANONICAL_DOC_REVIEW` in the owner PR description.
- `evidence/A/W01/validate_w01.py`, `tools/member_a_app/evaluators_extra.py`,
  `tools/member_a_app/requirements/w01_w06.py`: prior owner-approved code
  edits — check against merged A#95 for upstream equivalents before the
  owner PR; keep both if divergent (owner edits are additive).

## Tests to rerun after each merge

- After A#94: dossier validators + owner schema/gateway probes (already
  green on the exact PR source).
- After A#95: W08/W09/W13 validators, and hash re-verification of the three
  merged manifests.
- After C#69 (+stack): backend full suite; ack consumer service tests
  (infrastructure); owner ack probes against the merged contracts.
- After D#90 (+stack): control suite; `test_command_path_runner_d90.py` as
  primary; owner demo expectations (SAFETY_BLOCKED path).
- After B#102 (+stack): ml suite (expect ≥835 PASS on merged tree); owner
  B→D closure determinism check; F3-sensitive verification tests.

## Remaining gates (unchanged, with accountable owners)

- `REQUIRES_CROSS_TEAM_DECISION`: A/D verification-semantics (F3 decision
  record `docs/owner-integration/a-d-verification-semantics-DECISION.md`).
- Member D: critical-Tmean freeze; Optional TTL bounds decision.
- Member A: device clock synchronization authority (no evidence exists).
- Infrastructure: PostgreSQL + Mosquitto for 66/68 service skips
  (`SKIP_INFRASTRUCTURE`, not PASS).
- Physical: W13 controller-in-the-loop run session, energization evidence —
  never claimed in software phases.

## Readiness

**The owner candidate is READY FOR DELIVERY PREPARATION.** Every W01–W13
adapter now has explicit compatibility evidence against the exact live PR
heads (or their quietly-byte-identical bases), the previously asserted B
compatibility was confirmed true against the real head of #102, and no
adverse source drift occurred during execution. MERGE_READY must be claimed
only after the combined-merge regressions above actually run.
