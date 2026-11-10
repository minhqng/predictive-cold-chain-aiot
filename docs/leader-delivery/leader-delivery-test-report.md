# Leader Delivery Test Report — combined source

## Reused verified Phase 7B.1 tree (commit `4b25349`, tree `f7830dcd…`)

The Phase 8 Leader Delivery re-creates the same verified content through the DAG
`d22c8d5 → 240b393 (#94) → 2cd8023 (#95) → 98dc386 (#69) → 5f4c859 (#90) → ce9661a (#102)
→ e9681be (owner) → e53f5f2 (test align) → b2586f4/4b25349/5d73b1b (packaging)`.
Only packaging docs changed since the tested tree; no member source, no owner adapter
logic, no test logic changed after the executed regression run.

## Executed suites (exact Phase 7 / 7B / 7B.1 results against this tree)

| Suite | Environment | Result |
|---|---|---|
| Backend (full services) | PostgreSQL 16.6 portable + TimescaleDB 2.28.3 + Mosquitto 2.1.2, isolated test credentials and DBs | **408 PASS / 0 FAIL / 1 SKIP** (documented, matrix already carries the D#90 field) |
| Backend (standalone, no services) | portable test config | **237 PASS** |
| ML (`B#102` tree + pinned A data env) | `COLDGUARD_W13_A_DATASET_DIR` env | **832 PASS / 3 skip requiring dataset env; 32/32 individually when pinned** |
| Control (D#90 tree) | owner harness | **428 PASS** |
| Owner cross-team, owner suites re-run on merged tree | sandbox | **81 PASS / 1 documented SKIP** |
| A-pinned horizon regression | `COLDGUARD_W13_A_DATASET_DIR` | **32/32 PASS** |

These are the results of tests actually executed against the Phase 7B.1 verified tree.
Phase 8 makes **no new claim** beyond that executed evidence — it does not silently pass
unre-run suites.

## Not executed in Phase 8 (explicitly not claimed)

- Real-service GitHub CI (PG / Timescale / Mosquitto) — infrastructure gate, not software.
- Real TEC actuation, USB clock sync, watchdog / physical demo — deferred physical acceptance.
- Cross-teams simultaneous combined integration in one real repository — only the sandbox
  combined tree has been tested (this is the `COMBINED_TREE_TESTED` state, not `MERGED_TO_MAIN`).

## Safety gates preserved on the tested tree

- `UNSYNCHRONIZED_COMMAND = SAFETY_BLOCKED`
- `A_OBSERVATIONAL_VERIFIED != D_QUALIFIED_PHYSICAL_HEALTH`
- `UNKNOWN / NOT_ESTIMABLE / UNAVAILABLE` prediction fallbacks intact
- `ACK_ACCEPTED != PHYSICALLY_APPLIED`
- No critical-Tmean fabrication, no clock forging
