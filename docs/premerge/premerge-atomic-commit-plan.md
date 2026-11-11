# Pre-merge atomic commit plan (owner approval required before execution)

Base for delivery: `main` @ `d22c8d5` after the member-PR sequence
(A#94 → A#95 → C#69 → D#90 → B#102) is merged by the owner (see
`premerge-main-delivery-plan.md`). The owner-integration commits below are
prepared from the sandbox `phase7-combined` tree (`e9681be` + sandbox test
repairs) and rebase cleanly on that point.

| # | Commit message | Purpose | Files | Origin | Tests | Behavior | Evidence | Frozen file | Risk |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `feat(commands): add device serial translation for the backend command envelope` | C-envelope → A device `key=value` record | `backend/src/coldguard_backend/command_translation.py` | owner (new) | `test_command_translation.py` | yes | no | no | low |
| 2 | `feat(ack): translate device CMDACK records into backend envelopes` | A `#CG CMDACK` → C ACK envelope | `backend/src/coldguard_backend/ack_translation.py` | owner (new) | `test_ack_translation.py` | yes | no | no | low |
| 3 | `feat(commands): add fail-closed command/ACK correlation bridge` | dispatch + correlate + fail-closed refusal | `backend/src/coldguard_backend/command_ack_bridge.py` | owner (new) | `test_command_ack_integration.py` | yes | no | no | low |
| 4 | `feat(backend): add cross-team data hand-off adapters` | C rows → B observations; label horizon → D view | `backend/src/coldguard_backend/cross_team_paths.py` | owner (new) | `test_cross_team_paths.py`, `test_cross_team_data_paths.py`, `test_bd_dependency_closure.py` | yes | no | no | medium |
| 5 | `feat(backend): add owner command-path composition runner` | full D→C→A path, matrix-versioned | `backend/src/coldguard_backend/command_path_runner.py` | owner (new) | `test_command_path_runner.py`, `test_command_path_runner_d90.py` | yes | no | no | medium |
| 6 | `evidence(a): add healthy-ranges and door-critical analysis sidecars` | W08/W09/W13 sidecars + builders | `evidence/A/W08/w08-w16-preclosure-analysis-20261110.md`, `evidence/A/W09/build_healthy_ranges_s1.py`, `healthy-ranges-s1-20261109.json`, `evidence/A/W13/build_door_critical_input.py`, `door-critical-input-20261109.json` | owner (new data) | W08/W09/W13 validators | no | **yes** | no | low |
| 7 | `evidence(a): record command-path integration runs` | W06 sidecars + hash manifest + relocation note | `evidence/A/W06/command-path-integration-20261110-*.json/.SHA256SUMS.txt`, `evidence/A/W06/ack-fixture.json` (if additive), relocation pack | owner (new data) | W06 validator | no | **yes** | no | low |
| 8 | `test(commands): align owner suites with the D#90 clock gate` | SIMULATION-labeled sync claims + default-blocked test + merged-tree d90 fallback + C#69 envelope-level naive rejection | **exactly 5 owner test files** (the files modified between `e9681be` and the pinned tested tree `e53f5f2`/tree `5f7dfc08…`: `test_command_ack_integration.py`, `test_command_path_runner.py`, `test_command_path_runner_d90.py`, `test_command_translation.py`, `test_cross_team_paths.py`; the other 4 owner test files are byte-identical) | owner | the 5 files themselves | test-only | no | no | low |
| 9 | `docs(qa): record A-D verification semantics decision` | F3 owner-approved separation | `docs/owner-integration/a-d-verification-semantics-DECISION.md` (new) | owner | none (record) | no | **yes** | no | none |
| 10 | `docs(qa): add source synchronization and service-gate reports` | Phase 6/7 reports | `docs/owner-integration/source-sync/*` (6 files + manifests) | owner | none | no | **yes** | no | none |
| 11 | `docs(evidence): record premerge verification artifacts` | Phase 7 premerge dossier | `docs/premerge/*` (this set) | owner | none | no | **yes** | no | none |
| 12 | The 14 frozen tracked modifications | owner-approved pre-existing edits (Phase-1 era) + their document/evidence intent | the exact 14 paths (see map) | owner-approved A-side edits | W01/W03/W13 validators | per file | **yes** | **YES** | medium — requires owner re-approval at PR time |

Rules applied: one coherent purpose per commit; fixes carry their
regression tests in the same commit when separation would break the state;
evidence commits are separate from code; no unrelated formatting; no empty
commits; no generic messages.

## Sequencing

1–5 (code) → 8 (test alignment; depends on 1–5) → 6–7 (evidence) →
9–11 (docs) → 12 (frozen files, LAST, owner re-approval).

Every commit above is created ONLY after the owner approves this plan and
the member-PR sequence merge.
