# Pre-merge combined tests — Phase 7 (executed on the combined tree)

Combined candidate: `phase7-combined` @ `e9681be` (base `d22c8d5` + A#94 +
A#95 + C#69 + D#90 + B#102 + owner integration layer).

## Environment (reused Phase 6 portable services, verified healthy first)

- PostgreSQL 16.6 @ localhost:54329 (user `coldguard`, db `coldguard_test`
  + three migration databases), TimescaleDB 2.28.3 (`CREATE EXTENSION`
  verified + `timescaledb_information.hypertables` queryable).
- Mosquitto 2.1.2 @ localhost:18830 (no anonymous, per-principal ACLs,
  password file with thedevelopment-only test credentials from the
  committed `backend/tests/mqtt_testkit.py` — values not repeated here).

## Combined-tree test matrix

| Suite | Command | PASS | FAIL | SKIP |
|---|---|---|---|---|
| Backend, services + Timescale + Mosquitto, `--with-editable ../ml` | `uv run --frozen --extra test python -m pytest -q` | **404** | 0 | 1 |
| ML (combined tree = B#102's) | `uv run --frozen --extra test python -m pytest -q` (ml/) | **832** | 0 | 3 |
| Control (combined tree = D#90's) | `uv run --frozen --extra test python -m pytest -q` (control/) | **428** | 0 | 0 |
| D#90 harness (extract-fallback against the merged tree) | `pytest tests/test_command_path_runner_d90.py` | 5 | 0 | 1 |
| Owner six-path + closure + d90 suites (targeted) | see repair log | 44 | 0 | 0 |

**Combined totals: 404 + 832 + 428 = 1,664 PASS / 0 FAIL across the three
member suites; the single backend SKIP is the legitimate
"the running matrix already carries the D#90 clock field" fixture inapplicable to the merged matrix (documented; not a coverage gap).**

## The six integration paths — executed ON THE COMBINED TREE

1. **A→C telemetry**: `serial_gateway.translate/pump` with the A#94 schema
   (raw fields present) over the committed W06 capture — PASS.
2. **C→B data**: the B#102 admission path (owner `admit_rows` +
   `run_csv_to_c_rows`) against the merged `coldguard_ml` — 3,721 rows,
   determinism byte-equal sidecar — PASS.
3. **B→D predictive**: labels at 30/60/120/300 s = B#102's own
   `CANDIDATE_HORIZONS_S`; owner horizon set identical; D receives
   UNAVAILABLE with no invented score — PASS.
4. **A→D thermal/door**: committed W13 sidecar envelopes → D policy
   (`CRITICAL_PROTECTION` boundary) + D#90 verification gate — PASS.
5. **D→C→A command**: `validate_command` (clock gate) → `Command` →
   `dispatch_command` → device record → ACK fixture — PASS (SIMULATION_ONLY
   clock claims, labeled per test).
6. **A→C→D ACK/lifecycle**: CMDACK fixtures → `ingest_ack` correlation →
   `cg_command_trace` five-stage ledger (honest PARTIAL; ACK at
   `APPLIED_STATE` boundary) — PASS.

## Service-level verification (distinct from unit/fixture success)

- Broker ACLs verified by real SUBACK/PUBACK round-trips (anonymous denied,
  wrong password refused, cross-namespace denies).
- Database persistence verified by real connections + commit/replay flows
  (migration baselines downgrade/upgrade, exact/conflict replay classes).
- **Not claimed**: real TEC actuation, physical hardware timing, production
  MQTT/Postgres deployment — `BLOCKED` on the owner's bench session.
