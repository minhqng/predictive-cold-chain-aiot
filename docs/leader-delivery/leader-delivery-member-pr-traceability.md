# Leader Delivery — Member PR Traceability (52/52 member-weeks, W01–W13)

## Method

Classification sources, all measured from verified Git state:

1. `docs/owner-integration/source-sync/source-sync-matrix.csv` (Phase 6–8 registry,
   manifest-pinned) — 1 header + exactly 52 member-week rows.
2. Delivery ancestry `ce9661a..776c022` (verified HEAD `776c022`) and baseline main
   `d22c8d5` (GitHub main, no drift): per-row object existence, ancestor checks,
   baseline file-presence counts.
3. GitHub PR state index for the referenced PRs (read-only, session of record).

## Classification labels

- **ALREADY_IN_MAIN** — content already merged on main before the delivery window
  (via the baseline series); no re-merge performed.
- **INCLUDED_VIA_ANCESTRY** — content enters the delivery through a verified
  ancestor (one of the five member PR heads), not through the owner delta.
- **INCLUDED_IN_DELIVERY** — owner-side delta commit in `ce9661a..776c022`
  (14 atomic owner commits + documentation terminal commits).
- **SUPERSEDED** — content superseded by a later line already in the delivery or
  baseline; the old PR/line must not be re-merged.
- **MISSING** — required contribution absent from the final delivery tree and the
  main baseline. **Result: 0 rows.**

Reference: PR `#44` (C W04) is superseded — the final tree carries exactly one
`twin_store.py` and one `versions/0004_device_twin.py` (measured); PR #44 stays
closed, no cherry-pick, no re-merge.

## Totals (52/52 classified)

| Classification | Rows |
|---|---|
| ALREADY_IN_MAIN | 19 |
| INCLUDED_VIA_ANCESTRY | 29 |
| INCLUDED_IN_DELIVERY (owner delta) | n/a to member-weeks (14 atomic+docs commits) |
| SUPERSEDED | 4 (C W01–W04) |
| MISSING | 0 |

Open per-week PRs superseded by their member stacks (close at reconciliation,
owner-approved step each): B #43 #46 #48 #49 #50 #52 #54 #58 #59 (via #102);
C #60–#68 (via #69); D #81–#89 (via #90). Open PRs beyond delivery scope
(W14+/post-W13): #70–#74, #96–#101 — excluded, not audited.

## 52-row traceability matrix

| Member | Week | PR ref | PR state | Ancestry / registry pin | Classification |
|---|---|---|---|---|---|
| A | 1 | #7 | closed (merged) | content on baseline main; evidence/A/W01 = 46 files at `d22c8d5` | ALREADY_IN_MAIN |
| A | 2 | #8 | closed (merged) | as above (baseline series) | ALREADY_IN_MAIN |
| A | 3 | #9 | closed (merged) | as above | ALREADY_IN_MAIN |
| A | 4 | #13 | closed (merged) | row SHA ancestor-verified from delivery HEAD | ALREADY_IN_MAIN |
| A | 5 | via merged series #91–93 | closed (merged) | "in main via merged series"; delta = #94/#95 remediation | ALREADY_IN_MAIN |
| A | 6 | via merged series #91–93 | closed (merged) | as above | ALREADY_IN_MAIN |
| A | 7 | via merged series #91–93 | closed (merged) | as above | ALREADY_IN_MAIN |
| A | 8 | via merged series #91–93 | closed (merged) | as above | ALREADY_IN_MAIN |
| A | 9 | via merged series #91–93 | closed (merged) | as above | ALREADY_IN_MAIN |
| A | 10 | via merged series #91–93 | closed (merged) | as above | ALREADY_IN_MAIN |
| A | 11 | via merged series #91–93 | closed (merged) | as above | ALREADY_IN_MAIN |
| A | 12 | #77 | closed (merged) | row SHA ancestor-verified from delivery HEAD | ALREADY_IN_MAIN |
| A | 13 | via merged series #91–93 | closed (merged) | as above | ALREADY_IN_MAIN |
| A | 5–13 delta | #94, #95 | OPEN (pinned heads `ae23a36`, `815387d`) | verified ancestors via the five member merges | INCLUDED_VIA_ANCESTRY |
| B | 1 | via #42 (b-pre-w04-contract-intake) | closed (merged) | baseline `ml/` content; no own weekly PR | ALREADY_IN_MAIN |
| B | 2 | via #42 | closed (merged) | as above | ALREADY_IN_MAIN |
| B | 3 | via #42 | closed (merged) | as above | ALREADY_IN_MAIN |
| B | 4 | #43 | OPEN | ancestor in #102 stack (`824a53…`) | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| B | 5 | #46 | OPEN | ancestor in #102 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| B | 6 | #48 | OPEN | ancestor in #102 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| B | 7 | #49 | OPEN | ancestor in #102 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| B | 8 | #50 | OPEN | ancestor in #102 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| B | 9 | #52 | OPEN | ancestor in #102 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| B | 10 | #54 | OPEN | ancestor in #102 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| B | 11 | #58 | OPEN | ancestor in #102 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| B | 12 | #59 | OPEN | ancestor in #102 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| B | 13 | #102 | OPEN (pinned head `824a53…`) | W13 snapshot; stack b-w04..b-w12 (+ #43..#59) merged at `ce9661a` | INCLUDED_VIA_ANCESTRY |
| C | 1 | #47 (c-w01..w04 line) | closed — merged into non-main base | outside main/#69 ancestry (registry: DIVERGED) | SUPERSEDED |
| C | 2 | #47 line | as above | as above | SUPERSEDED |
| C | 3 | #47 line | as above | as above | SUPERSEDED |
| C | 4 | #44 (C-W04 twin) | closed | superseded: final tree = 1× `twin_store.py`, 1× `versions/0004_device_twin.py` | SUPERSEDED |
| C | 5 | #60 | OPEN | ancestor in #69 stack (`361e73…`) | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| C | 6 | #61 | OPEN | ancestor in #69 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| C | 7 | #62 | OPEN | ancestor in #69 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| C | 8 | #63 | OPEN | ancestor in #69 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| C | 9 | #64 | OPEN | ancestor in #69 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| C | 10 | #65 | OPEN | ancestor in #69 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| C | 11 | #66 | OPEN | ancestor in #69 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| C | 12 | #68 | OPEN | ancestor in #69 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| C | 13 | #69 | OPEN (pinned head `361e73…`) | c-w14 platform-baseline merged inside the #69 head; c-w05..c-w12 (#60..#68) | INCLUDED_VIA_ANCESTRY |
| D | 1 | no own PR | — | control package enters main via base (`control/` at `d22c8d5`) | ALREADY_IN_MAIN |
| D | 2 | no own PR | — | as above | ALREADY_IN_MAIN |
| D | 3 | no own PR | — | as above | ALREADY_IN_MAIN |
| D | 4 | #81 | OPEN | ancestor in #90 stack (`da82109…`) | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| D | 5 | #82 | OPEN | ancestor in #90 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| D | 6 | #83 | OPEN | ancestor in #90 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| D | 7 | #84 | OPEN | ancestor in #90 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| D | 8 | #85 | OPEN | ancestor in #90 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| D | 9 | #86 | OPEN | ancestor in #90 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| D | 10 | #87 | OPEN | ancestor in #90 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| D | 11 | #88 | OPEN | ancestor in #90 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| D | 12 | #89 | OPEN | ancestor in #90 stack | INCLUDED_VIA_ANCESTRY (PR superseded by stack) |
| D | 13 | #90 | OPEN (pinned head `da82109…`) | stack d-w04..d-w12 (#81..#89) merged at `5f4c859` | INCLUDED_VIA_ANCESTRY |

## Owner fix → member/week/contract mapping (owner delta `ce9661a..776c022`)

| Owner commit (terminal SHA) | Member / week | Contract |
|---|---|---|
| `467c256` (device serial translation) | A W06 | A key=value serial mapping + malformed-input refusal |
| `33be9aa` (CMDACK → CommandAck) | A W06 ↔ C | A/C command-ACK envelope contract |
| `263d9a1` (fail-closed bridge) | A W06 ↔ C/D | fail-closed dispatch + correlation |
| `c248f2f` (cross-team adapters) | B W13 → D | b-to-d data-dependency closure sidecars |
| `9c9e6eb` (composition runner) | A ↔ D | D #90 variant command-path runs |
| `577a4f8` (MAX3485 harness test) | A tools | member-A app harness variant |
| `84b587f`, `6105ffa`, `4c1dc87` (evidence sidecars/runs/frozen set) | A W06/W08/W09/W13 | owner-frozen evidence records + manifests |
| `e0275c3`, `4e5f9a4`, `bfcad23`, dossier/verdict docs | cross-team | semantics decision, scope architecture, provenance tooling, packaging |

Per-row registry SHAs and contract columns: `docs/owner-integration/source-sync/source-sync-matrix.csv`.
