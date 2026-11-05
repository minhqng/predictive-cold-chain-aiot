# Member A session invalidation log (machine-derived from the session store)

Session `capture-20261104T092140Z`. Derived read-only from `results/*.json`, `results/history/`
and the recorded repetitions. No attempt was deleted and no verdict was rewritten;
every superseded version is preserved under `results/history/`.
**Status: awaiting operator review** - the content is factual, the review is not yet given.

Registry totals at generation time: {"FAIL": 2, "PASS": 34, "NOT_RUN": 72, "INCOMPLETE": 6} of 114.

## 1. Invalid attempts retained with a reason

- Invalid repetitions found: **0**
- Invalid repetitions missing a reason: **0** []

## 2. Valid repetitions retained (kept, never re-counted as extra independent trials)

- Valid repetitions: **6**
  - A-W07-02 repetition 0 (no reason recorded)
  - A-W07-02 repetition 1 (no reason recorded)
  - A-W07-02 repetition 2 (no reason recorded)
  - A-W07-03 repetition 0 (no reason recorded)
  - A-W07-03 repetition 1 (no reason recorded)
  - A-W07-03 repetition 2 (no reason recorded)

## 3. Recorded non-PASS verdicts and their causes

| Requirement | Outcome | Recorded reason |
|---|---|---|
| A-W01-01 | FAIL | UNAPPROVED_SUBSTITUTION |
| A-W02-07 | INCOMPLETE | H8_BENCH_IMAGE: canonical W06 telemetry/command fields are absent; use the H8 read-only/bench profile; this canonical requirement is INCOMPLETE, not P |
| A-W03-02 | FAIL | vcc_3v3_ABOVE_MAXIMUM |
| A-W06-01 | INCOMPLETE | NETWORK_TRANSPORT_UNAVAILABLE: the local source gate precedes field-level validation, so canonical duty/device/expiry checks are unreachable |
| A-W06-02 | INCOMPLETE | NETWORK_COMMAND_TRANSPORT_UNAVAILABLE: duplicate-canonical requires the docs/02 NETWORK source; the local console source is rejected before the idempo |
| A-W07-02 | INCOMPLETE | START_CONDITION_SIMILARITY_AND_INDEPENDENCE_NOT_VERIFIED: three valid 300 s trials are contiguous (~1 s gaps), no stabilization gate, no start-conditi |
| A-W07-04 | INCOMPLETE | PREREQUISITE_INCOMPLETE A-W07-02: START_CONDITION_SIMILARITY_AND_INDEPENDENCE_NOT_VERIFIED: three valid 300 s trials are contiguous (~1 s gaps), no st |
| A-W24-01 | INCOMPLETE | FINAL_FUSE_NOT_RECORDED: run A-W08-02 before freezing the configuration |

## 4. Known invalidating events in this session (from the dated records)

- 2026-11-04 A-W07-02: three contiguous 300 s warm-up trials were retained but the verdict is
  INCOMPLETE - `START_CONDITION_SIMILARITY_AND_INDEPENDENCE_NOT_VERIFIED` (start spread
  0.125 C, ~1 s gaps, no stabilization proof). See `A-W07-02-CORRECTION-20261104.md`.
- 2026-11-04 A-W12-01 first attempt: INCOMPLETE - INVALID_CONDITIONS, because a common-mode
  ambient ramp (0.406 C) was being read as sensor offset drift (0.021 C). Re-run on a
  verified flat ambient: PASS with 0.0233 C offset drift. See
  `A-W12-01-CONDITIONS-20261104.md`.
- 2026-11-04 batch B: verdicts corrected after independent review, see
  `BATCH-B-CORRECTIONS-20261104.md`.
- 2026-11-04 A-W04-05 first attempt: refused at SUPERVISE (authorization token case), so the
  TEC never energized; the attempt left no actuated evidence and the re-run is the recorded
  PASS. No invalid attempt was deleted.
- Door polarity: the flashed image asserts OPEN = raw 1 (sketch-era W02 assumption, annotated
  'ESP-IDF INTEGRATION NOT VERIFIED'). Only CLOSED at raw 0 has ever been observed on the
  installed GPIO35 wiring (983 attested frames, 0 transitions, 0 cycles), so attested door
  states are unproven and every door-dependent verdict stays INCOMPLETE until a real
  OPEN/CLOSED observation exists.
- Stale H8-image verdicts: A-W02-07 and A-W05-04 were recorded INCOMPLETE on the pre-flash H8
  bench image. A-W05-04 was re-evaluated on the canonical W06 image (PASS, boot `141ebaad`,
  60/60 frames, zero warnings, explicit BME missing-state semantics); A-W02-07 still needs
  the genuine 20-cycle campaign.
- A-W07-03 trials were each separately authorized and each re-read the boot TEC_LIMIT lines;
  no trial was reused as another trial. Trial 1 was reconstructed from the immutable raw
  telemetry of its own START/STOP window rather than re-run.

## 5. Superseded verdict files preserved

- 15 archived result versions under `results/history/`

## 6. Related session records

- A-W07-02-CORRECTION-20261104.md
- BATCH-B-CORRECTIONS-20261104.md
- A-W12-01-CONDITIONS-20261104.md
