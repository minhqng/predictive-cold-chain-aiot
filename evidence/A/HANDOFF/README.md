# Member A handoff index

What Members B, C and D can consume from Member A today, what is only tooling, and what the
operator must physically do. Requirement IDs and canonical wording come from `docs/05A`
(§5 handover list, §6.1-§6.3 interfaces, §16-§25 weekly asks); nothing here restates a
canonical rule as a Member A opinion.

| File | Audience | Question it answers |
|---|---|---|
| [`coverage-matrix.md`](coverage-matrix.md) | all | For each of the 44 assigned `A-W07-01..A-W16-04` items: current state, where the artifact is, and precisely what is missing |
| [`a-to-bcd-fields.md`](a-to-bcd-fields.md) | B, C, D | Field by field against docs/05A §6.1-§6.3: which handoff fields exist in committed data now, which are unqualified, and which do not exist yet |
| [`supervised-session-plan.md`](supervised-session-plan.md) | operator + Member D | The GO/NO-GO gate, then one consolidated set of supervised sessions with prerequisites, exact actions, independent-run counts, capture mechanism, invalidation rules and which requirements each authentic run serves |

## Read-this-first summary

- **One item is delivered as a PR today:** A-W07-01/04/05 on PR #18 (unmerged). Everything
  else from W08 to W16 is tooling on task branches, under review or under repair.
- **Thirteen items are blocked on physical sessions, not on code.** No host test, artifact
  count or PR closes any of them.
- **There is exactly one real thermal session in the repository** (957 rows, one `boot_id`
  carrying two `run_id`s), so nothing that needs variance — repeatability, tolerances,
  horizons, distributions — can be computed yet.
- **The unpowered inspection in session S-0 is necessary, not sufficient.** Until it exists,
  `evidence/A/W04/fuse-commissioning-note.md` §4 says it plainly — no conductor evidence
  means **no fuse freeze** and no powered test beyond what the operator authorises case by
  case. Completing S-0 does not by itself clear any energised gate: the zero-duty current
  frame still needs a supervised classification, and a conductor marking is not an ampacity.
- **One high-severity physical question is open and Member A cannot close it:** a frame with
  applied duty 0 carrying 7.15 A / 84.2 W, which docs/01 §22.4 makes a candidate
  `CONTROL_ELECTRICAL_ANOMALY`. The capture also shows what follows it — the reading decays
  7.15 → 0.56 → 0.02 → 0.0 A and reaches zero three seconds later, which supports a lagging
  PZEM channel and weakens sustained energization. It stays open because those are meter
  values with no independent instrument behind them.
- **Conductor size was mis-recorded until 2026-11-02:** 1.75 mm is the copper-core
  **diameter**, so a round solid core is about 2.405 mm² of copper. That narrows the gap to
  the canonical `2 × 2.5 mm²` ask from ~30 % to ~4 % by area and puts the conductor inside
  the FDD2-250 termination range — without establishing compliance, an ampacity, or a fuse
  rating, and a shop listing is not evidence about installed hardware.

## Provenance and limits

Every physical quantity quoted in this directory was recomputed from committed files, not
carried over from a report. Where a number exists only in local, uncommitted bench data it is
marked as such, and untracked files are never cited as proof for a published claim.
