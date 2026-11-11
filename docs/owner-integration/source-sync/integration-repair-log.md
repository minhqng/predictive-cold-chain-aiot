# Integration repair log — Phase 6 source synchronization

Only defects actually reproduced against the live/real sources are listed.
After revalidation against the real B#102 head, **no owner-owned code defect
was reproduced this run**; the candidate defects investigated and their
outcomes are recorded below with evidence.

## D1 — "B#102 compatibility unproven" (process defect, reproduced)

- **Source/owner:** process (previous phases), owner integration base.
- **Reproduction:** local object store lacked `824a5389`; earlier evidence
  used base ml (`162 PASS`) as a compatibility proxy — a source-version gap,
  confirmed by the live API (`#102` head vs base `34435bd ≠ stale a27eeed`).
- **Minimum owner-owned change:** none to code — the fix is acquiring the
  SHA-pinned snapshot and running the real suite (done: 835 PASS) plus the
  owner-closure determinism probe (byte-equal sidecar TRUE).
- **Tests/outcomes:** B#102 full suite 835 PASS; horizon suite 32/32 with the
  pinned A dataset; owner closure under B#102's `coldguard_ml` byte-equal.
- **Unresolved:** remaining stacked weekly heads (b-w04..w12) are verified via
  the #102 tree rather than standalone; acceptable because #102's tree
  contains them and the suite passed on the full tree.

## D2 — "owner horizon set could conflict with B#102 horizon engineering" (hypothesis, DISPROVEN)

- Reproduction attempt: read `horizon_engineering.py` at the real head and
  compared `CANDIDATE_HORIZONS_S` and freeze semantics with the owner's
  `W13_HORIZONS_S` / closure labels.
- Result: identical intact set (30/60/120/300); NOT_ESTIMABLE vocabulary is
  explicitly non-zero; no freeze without evidence; real metrics refused.
- **Owner repair required: NONE.** The owner closure and B#102 agree.

## D3 — "W09 validator FAIL on base" (previously verified upstream-fixed)

- Confirmed earlier (A#95 disposable run, W09 OK 20 pinned/957 rows); re-run
  today against unchanged `815387d` via object SHA; status unchanged.
- Owner action: none (upstream fixed in #95); integration dependency recorded.

## D4 — "frozen manifests may collide with A#95" (delivery-level, not a code defect)

- The three pinned manifests (W08/W09/W13 SHA256SUMS.txt) are the only files
  in both the frozen-14 set and A#95's 44-file change set. Disposition in
  `delivery-readiness.md` (joint-append merge + hash re-verification). No
  changes made this phase.

## Safety gates exercised this run (no bypass)

- Unsynchronized clock ⇒ SAFETY_BLOCKED (D#90 probe suite, 6/6, verified
  against `da82109` earlier this session; unchanged).
- B#102 keeps real predictive metrics NOT_ESTIMABLE and does not freeze a
  primary horizon; the owner closure remains UNAVAILABLE/fallback at W13.
- No member file, no dataset byte, no frozen-14 entry was modified.
