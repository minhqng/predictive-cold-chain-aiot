# Pre-merge conflict ledger — Phase 7

## Actual conflicts encountered during the five merges

**NONE.** Sequence executed in the disposable sandbox clone
(`phase7-combined`):

| Merge | Result |
|---|---|
| `ae23a36` (A#94) | clean — 7 files (schema raw fields, HANDOFF regen, 2 new tests) |
| `815387d` (A#95) | clean — 44 files (SOURCES/20261109 acquisition, HANDOFF, acceptance-integrity, W09 validator fix) |
| `361e732` (C#69) | clean — command stack: contracts (+114 lines: `CommandAck`, `AppliedState`), ack_consumer, command_store/publisher/timing, ingest/main/mqtt_consumer, observability |
| `da82109` (D#90) | clean — control: clock gate, TTL bounds, aiw.py, verification.py, quality/faults/safe_local/device_safety, tests |
| `824a5389` (B#102) | clean — ml: horizon_engineering + W11 empty-run reconcile + reports + tests |

Reason: none of the five PR trees shares mutable files with the others
(A = firmware/evidence, C = backend, D = control, B = ml — disjoint trees) —
verified by the intersection checks done in Phase 5 correction
(`comm -12` produced zero shared paths except none here).

## Behavioral conflict (not textual): the combined tree changes owner verdicts

Running the OWNER backend suite on the combined tree reproduced **22 test
failures** — ALL owned by two cleanly separated causes:

1. **D#90's `clock_synchronized` gate (15 failures)** — the merged D#90
   contract SAFETY_BLOCKs any dispatch whose evidence does not prove a
   synchronized device clock (Doc 02 §31.1; `clock_synchronized=False`
   default). This is the CORRECT combined behavior, and it flips every
   owner happy-path assertion written against the pre-#90 base matrix.
   **Resolution (owner-owned, sandbox):** explicit `clock_synchronized`
   claims in owner tests, clearly labeled `SIMULATION_ONLY`:
   - `tests/test_command_path_runner.py::_run()` → SIMULATION-only sync
     claim; every dispatching test passes `clock_synchronized=True`.
   - NEW test: unclaimed clock ⇒ `SAFETY_BLOCKED` (correct fail-closed
     record, keeping detail + `checks_passed` order proof — clock gate
     precedes expiry).
   - `tests/test_command_path_runner_d90.py`: the legacy "base happy path"
     test rewritten as the D#90 fail-closed check
     (`member_d_matrix == d90-latest`); the base-refusal test legitimately
     SKIPs when the running matrix already carries the field.
   - `tests/test_cross_team_paths.py` paths 5/6: SIMULATION-labeled claim.
   The WORKTREE copies stay untouched; these edits are sandbox-side and will
   be transferred by the owner-approved atomic commit plan below.
2. **C#69's hardened `Command` envelope (2 failures)** — naive timestamps
   are now rejected by pydantic (`AwareDatetime`) BEFORE the translation
   guard runs; the fail-closed invariant is unchanged, so the owner tests
   now accept `(CommandTranslationError, ValidationError)`.
3. **ACL/user gap in the disposable broker (5 failures)** — the C#69 test
   publishers use a third principal `backend-command` (not present in the
   Phase 6 two-principal ACL); with a deny-all fallback, Broker 2.1
   disconnects on publish and the transport reports `failed`/
   `PUBLISH_FAILED`/`UNKNOWN`. **Resolution = infrastructure (not code):**
   added the user + `topic readwrite coldguard/+/command` to the scratch
   ACL; all five service tests then PASS.

## Unresolved blockers (owner decision / external)

- **A/D verification semantics** — owner decision F3 recorded Phases 4–6
  (A observational ≠ D qualified); NOT promoted silently anywhere.
- **Critical-Tmean numeric freeze** — requires approved characterization
  source (Member D).
- **Device clock synchronization** — USB time architecture SELECTED,
  NOT implemented/verified (owner: separate safety review for real TEC).
- **C-W01..04 DIVERGED ancestry** (merged into a non-main base) — member
  confirmation; outside W01–W13 adapter scope.
- **Combined-source CI environment** — PostgreSQL/TimescaleDB/Mosquitto run
  from a scratch dir; reproduce via `delivery-readiness.md` infrastructure
  section or any CI with equivalent services.
