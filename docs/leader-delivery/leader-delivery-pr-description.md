# PR Description — ColdGuard W01–W13 Combined Leader Integration Delivery

**Target:** `main` (baseline `d22c8d5b` — GitHub main, no drift)
**Source branch:** `leader/delivery/w01-w13-atomic-reviewed`
**Delivery mode:** ONE reviewed Leader PR (Ride Hailing #88 / #90 / #93 pattern)

## Scope

Integrates all Member A/B/C/D W01–W13 contributions through their five verified
upstream PR heads plus the owner integration layer as a 17-commit atomic owner
range, one terminal docs commit, and one terminal traceability reference.
It does NOT include W14+ work and does NOT run physical TEC hardware.

## Member provenance (per member — full table in
`docs/leader-delivery/leader-delivery-member-pr-traceability.md`)

- **A** — W01–W13: entries via merged baseline series (#7 #8 #9 #13 #77 + #91–93);
  remaining delta via remediation PRs #94 (`ae23a36…`) and #95 (`815387d…`), both
  verified delivery ancestors. 13/13 weeks covered, 0 missing.
- **B** — W01–W03 via merged #42 (b-pre-w04 intake); W04–W12 per-week PRs
  (#43–#59, open) superseded by the #102 stack (`824a53…`); W13 ships with #102.
- **C** — W01–W04 superseded line (#47 into non-main base; #44 closed; exactly one
  `twin_store.py` + one `versions/0004_device_twin.py` in the delivery tree — no
  re-merge); W05–W12 per-week PRs (#60–#68, open) superseded by the #69 stack
  (`361e73…`); W13 ships with #69.
- **D** — W01–W03 via the base control package (no own PR); W04–W12 per-week PRs
  (#81–#89, open) superseded by the #90 stack (`da82109…`); W13 ships with #90.

Classification result (52/52 member-weeks): ALREADY_IN_MAIN 19,
INCLUDED_VIA_ANCESTRY 29, SUPERSEDED 4 (C W01–W04), MISSING 0.

Original Author/AuthorDate of all member commits preserved via SHA-preserving
merge commits and verified ancestry — no squash, no rebase of member history.

## Owner integration delta (`ce9661a..<terminal delivery HEAD>`)

- 17-commit metadata-normalized owner range: 14 atomic owner commits
  (commands/ack contract A W06, b-to-d W13 closure, composition runner, harness
  test, evidence sidecars, A-D semantics, scope-architecture, provenance tooling,
  two packaging dossiers) + 3 terminal docs commits. Full mapping:
  `docs/leader-delivery/phase8-2-atomic-commit-ledger.md` and
  `docs/leader-delivery/phase8-2-attribution-repin.md`.
- Observer-side pre-merge dossier and manifest pins:
  `docs/premerge/`, `docs/leader-delivery/.SHA256SUMS.txt` (20/20 OK).

## Safety limitations remaining (not in this PR)

- USB clock-sync + watchdog + real-TEC actuation are deferred (physical gates).
- No critical-Tmean freeze yet (demo-specific, owner to freeze separately).
- A observational VERIFIED != D qualified physical health (F3 decision, owner-approved separation).
- `UNSYNCHRONIZED_COMMAND = SAFETY_BLOCKED` remains authoritative.
- ACK_ACCEPTED != PHYSICALLY_APPLIED.

## Test results (executed against the exact verified tree)

| Suite | Result |
|---|---|
| Backend (+ PG/Timescale/Mosquitto services) | 408 PASS / 0 FAIL / 1 known SKIP |
| Backend standalone | 237 PASS |
| ML (B#102 exact) | 832 PASS + 32/32 horizon |
| Control (D#90 exact) | 428 PASS |
| Owner cross-team / owner suites on merged tree | 81 PASS / 1 known SKIP |

Post-merge regression requirements, per-member file counts, and the reconciliation
plan for the original member PRs are in
`docs/leader-delivery/leader-delivery-pr-reconciliation.md` and
`docs/leader-delivery/leader-delivery-source-lock.md`.
