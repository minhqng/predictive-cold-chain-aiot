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

## CURRENT HANDOFF (2026-11-09 — read this first)

This section is the current state and supersedes the historical snapshots below it wherever
they disagree. The lines above it in "Read-this-first summary" describe the pre-dataset era;
treat every "zero valid runs" / "NOT_ESTABLISHED" statement there as historical.

### What is published on this branch (PR #95)

- **Accepted real S1/S2 dataset**: `evidence/A/SOURCES/20261107/datasets/` — 18 runs/segments,
  9,293 measured frames, manifest + SHA256SUMS + standalone regeneration. Read its
  `README.md` + `manifest.json` first. It backs A-W09-02 (S1 baseline) and A-W10-03
  (S2 pilot) PASS verdicts in the authoritative acceptance store.
- **Additional independent S1 baseline run (A-W11-03)**:
  `evidence/A/SOURCES/20261109/s1/s1-20261109T081304Z/` — a genuine 600 s read-only
  passive S1 trial captured 2026-11-09T08:13Z (600/600 schema-3 frames, single boot
  `c0e43470`, coverage 0.99833, thermal_valid_rate 0.99833, electrical_valid_rate 0.99667,
  fault bits 0, cooling OFF in every frame, zero bytes written to the port, zero commands,
  fuse slot-3 OUT, PSU ON after operator action, door operator-confirmed closed with
  `door_raw=0` in 600/600 frames). Every file is hash-pinned in its `SHA256SUMS.txt`;
  the acceptance store recorded `A-W11-03: PASS` (source HARDWARE) with this evidence
  imported and manifest-verified. Its exact admissibility levels are in
  [`a-to-bcd-fields.md`](a-to-bcd-fields.md) §"New 2026-11-09 S1 trial".
- **Acceptance integrity tooling repaired on this branch**: Python 3.12 artifact
  reproducibility, schema-3 telemetry classification in the read-only collector, tolerating
  ISO host stamps with fractional seconds/offsets, schema-aware fail-closed Phase E gates,
  and fully reconciled evidence pins (dossier validators W05–W16 all OK).

### Authoritative acceptance ledger (recounted live 2026-11-09 from the store)

`114 items: 80 PASS / 2 FAIL / 7 INCOMPLETE / 25 NOT_RUN` (store:
`evidence/A/h8-captures/capture-20261104T092140Z` on branch `feat/a-acceptance-app`).
The earlier `79 PASS` figure (PR #95's historical description) predates the A-W11-03
physical trial. FAILs (operator hardware items): A-W01-01 unapproved BOM substitution,
A-W03-02 vcc_3v3 above maximum. INCOMPLETEs: A-W06-01/02/03/06 (Member C merged transport/
command contracts), A-W10-05 + A-W13-03 (Member D frozen critical-Tmean threshold; offline
rerun closes them with zero new captures), A-W23-03 (physical labels). The W07–W16 audit
with per-item status is in [`coverage-matrix.md`](coverage-matrix.md) §"Current audit".

### What each member can consume

- **B (ML/data)**: the accepted dataset package (18 runs: 4 S1, 5 S2 windows, cooling/recovery
  segments, W07 repeats) plus the supplementary 2026-11-09 S1 trial — with the field
  availability and eligibility rules in [`a-to-bcd-fields.md`](a-to-bcd-fields.md) §6.1.
  B owns: horizon choice (A-W10-05), pairing tolerance freeze (A-W14-04/A-W16-03).
- **C (backend/device contract)**: schema-3 frame grammar + parser
  (`firmware/tools/cg_telemetry_schema.py`), read-only capture behaviour
  (`tools/acceptance/read_only_capture.py`), the acceptance runner gates and the console
  grammar documentation — see §6.2 in the fields file. The typed command/ACK integration
  (A-W06-01..03, A-W06-06) waits on Member C's merged contracts, not on Member A.
- **D (safety)**: the physical evidence chain (observed envelope, fuse decision + its
  documented limitations, anomaly status, TEC limits policy) — see §6.3 plus
  [`supervised-session-plan.md`](supervised-session-plan.md). D owns: the six TEC operating
  limit freezes (gate A) and the critical-Tmean threshold.

### Physical blockers that stay explicit

1. A-W08-03 supervised loaded COOLING_STEP: requires Member D's TEC limit freeze, a
   stage-enabled W06 build + flash (operator-gated, restore/backup recipe in
   `tools/acceptance/README.md`), slot-3 fuse insertion at the session, and live ARM/START
   consent. The 7.15 A zero-duty anomaly remains a candidate
   CONTROL_ELECTRICAL_ANOMALY until independently resolved.
2. A-W16-01..04 depend on that session (prereq chain) and on B's freeze.
3. A-W08-02 fuse rating is recorded as PASS-with-limitation: 15 A against measured bases;
   certified ampacity does not exist and the installed body carries no legible marking —
   do not read it as an ampacity certification.

### Recommended reading order for B/C/D

1. This file → 2. `coverage-matrix.md` (current audit) → 3. `a-to-bcd-fields.md`
(current sections) → 4. `evidence/A/SOURCES/20261107/datasets/README.md` + `manifest.json`
→ 5. your own §6.x subsection → 6. `supervised-session-plan.md` (only when planning a
physical session).
