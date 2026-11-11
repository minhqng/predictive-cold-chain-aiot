# Pre-merge data integrity — Phase 7

## Datasets (all preserved, byte-identical where re-checked)

| Dataset | Integrity evidence |
|---|---|
| 18-run / 9,293-frame physical package | manifest `totals` intact (18 runs, frames_by_scenario sums 9293); every run CSV re-hashed against `run_index.csv` `dataset_sha256` in Phase 6 (9/9 accepted-run hashes match) |
| 9 accepted S1/S2 runs (3,721 rows admitted) | admitted/dedup counts stable across Phases 2B/6/7 (3,721; dedup no-loss); sidecar byte-equal under B#102's real `coldguard_ml` (this phase) |
| 600-second S1 capture (W09 `CG-S1-H8C-600S`) | `frames.rows=957`, companion CSV unpinned-but-hash-recorded; not training-eligible (UNKNOWN quality / no event time) — classification PRESERVED, not rewritten |
| W10 S2 pilot | 2 event rows preserved with their NOT-valid dispositions |
| W13 door-critical sidecar | `critical_tmean_c=null`, `NOT_FROZEN_PENDING_MEMBER_D` — freeze gate intact; input hashes 5/5 verified (Phase 2B) |
| W06 command artifacts | `ack-fixture.json` + `demo-command-capture.log` reused read-only by every probe (hashes unchanged — validator `W06 DOSSIER: OK (22 pinned)`) |
| B#102 pinned dataset | B's own suite pins dataset sha `f028441d…`; the committed 20261107 export supplied via `COLDGUARD_W13_A_DATASET_DIR` matches — B's own replay proofs 32/32 PASS on it |

## Data-handling rules enforced during Phase 7

- No dataset/sidecar was rewritten, moved, or reclassified; the sandbox
  merge series contains zero modifications to `evidence/**` other than the
  upstream PR content itself (A#94/A#95).
- Owner sidecars from Phases 1–6 were added to the combined tree verbatim
  (copy commit `e9681be`); the W13 closure sidecars remain in
  `docs/owner-integration/w13-bd-closure/` (Phase 4 relocation pack).
- No synthetic result was upgraded to real evidence; no EVENT_UTC, clock
  sync, threshold, label, or model output was invented anywhere.

## Exclusions ledger (what is NOT counted as evidence)

- `ml/reports/W13/horizon-study.md` metrics: synthetic software controls
  (B#102's own rule: highest synthetic AP never selects a primary horizon —
  copied verbatim from the PR).
- The 600 s S1 capture: physical measurement, but admission-refused
  (UNKNOWN quality vocabulary + missing identity/time) — preserved as
  physical-evidence-adjacent, NOT as ML training data.
- The A#95 `SOURCES/20261109/s1` passive capture: new member data (out of
  W01–W13 scope; not integrated by any owner adapter).
