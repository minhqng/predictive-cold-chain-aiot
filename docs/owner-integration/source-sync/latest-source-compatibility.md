# Latest-source compatibility — six cross-team paths (Phase 6)

Levels: `CONTRACT_VERIFIED` → `OWNER_RUNNER_INTEGRATED` →
`LATEST_SOURCE_TESTED` → (`REAL_SERVICE_VERIFIED`, `PHYSICAL_VERIFIED` — NOT
claimed anywhere below). `BLOCKED` where an external dependency stops.

| # | Path | Producer SHA | Consumer SHA | Owner adapter | Actual executed test (this run) | Result | Level / remaining blocker |
|---|---|---|---|---|---|---|---|
| 1 | A→C telemetry | A schema v3 @ `ae23a36` (#94) + base firmware | C gateway (base; unchanged in #69) | `serial_gateway` probe with A#94 schema cached | gateway translate of committed W06 TELEM frame: 1 payload, `t2_role=TEC_HOT_SIDE` | PASS | `LATEST_SOURCE_TESTED` (A#94 + base); real broker = `BLOCKED` (no Mosquitto) |
| 2 | C→B data | C normalized rows (base; #69 adds export tooling, needs PG) | **B#102 `824a5389`** | `normalized_row_to_observation`/`admit_rows` + closure | owner closure under B#102's real `coldguard_ml`: 9 runs/3,721 admitted, byte-equal sidecar; B's own CLI replay proofs 32/32 on the same pinned dataset | PASS | `LATEST_SOURCE_TESTED` (B#102); DB-export real-service = `SKIP_INFRASTRUCTURE` |
| 3 | B→D predictive | B#102 (no model at W13; horizons 30/60/120/300; NOT_ESTIMABLE gates) | D base + `da82109` (#90) UNAVAILABLE fallback | `label_records_to_prediction_view` + closure labels | closure prediction views UNAVAILABLE→ D `AI_UNAVAILABLE` fallback (re-asserted under B#102 source); B#102 keeps real metrics NOT_ESTIMABLE, no primary-horizon freeze | PASS | `LATEST_SOURCE_TESTED`; predictive full use blocked by design (no B model) |
| 4 | A→D thermal/door | A W13 sidecar (committed, hash-verified) + measured envelopes | D `da82109` policy runs + D email verification gate | `door_critical_sidecar_to_policy_views` | Phase 4/5 tests (path-4), re-confirmed unchanged; F3 decision record retained | PASS | `LATEST_SOURCE_TESTED`; `REQUIRES_CROSS_TEAM_DECISION` on A/D verification authority |
| 5 | D→C→A command | D `da82109` matrix (clock gate lonely default False) | C Command (base; unchanged in #69) → A record | `command_path_runner` + `d90_compatible_evidence` | d90 suite 6/6 under `da82109`: unsynchronized ⇒ `SAFETY_BLOCKED` before expiry; base-D demo stamped `member_d_matrix: base` | PASS | `LATEST_SOURCE_TESTED` on both matrices; firmware execution not possible locally (no toolchain) |
| 6 | A→C→D ACK/lifecycle | A W06 committed fixtures + demo capture | C#69 `361e732` `CommandAck`/`ack_consumer`; D trace/verification | `ack_translation`, `command_ack_bridge`, `cg_command_trace` ledger | CommandAck `model_validate` 5/5 (Phase 3, re-confirmed); trace stages under A#94 schema probe (5 commands, honest PARTIAL) | PASS | `LATEST_SOURCE_TESTED` (A#94 + #69 model); `ack_consumer` service = `SKIP_INFRASTRUCTURE` (PG/Mosquitto) |

**Cross-cutting:** main HEAD `d22c8d5b` verified unchanged at start and end of
run (no drift). All SHA pins above come from the live GitHub API; every local
object used (A#94/A#95/#69/#90 + the acquired B#102 tarball) matches its
remote SHA exactly.
