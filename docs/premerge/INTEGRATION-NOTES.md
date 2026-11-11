# W01–W13 integration + delivery notes (Phase 1–7 consolidated)

Owner-reviewed running record for the integration candidate prepared in
Phase 7 (see `docs/premerge/*` for the full premerge dossier).

## Quick product map (owner layers)

- `backend/src/coldguard_backend/command_translation.py` — C envelope →
  device record (W06 `cg_command.c` surface).
- `backend/src/coldguard_backend/ack_translation.py` — device `#CG CMDACK`
  → C `CommandAck` shape.
- `backend/src/coldguard_backend/command_ack_bridge.py` — fail-closed
  dispatch + correlation.
- `backend/src/coldguard_backend/command_path_runner.py` — full
  D→C→A→C composition; supports both the base matrix and D#90's
  `clock_synchronized` contract explicitly.
- `backend/src/coldguard_backend/cross_team_paths.py` — C→B observation
  admission, B horizon labels, A→D door/thermal envelopes, the D#90
  B→D data closure.
- Tests: `backend/tests/test_command_*`, `test_ack_*`,
  `test_cross_team*`, `test_bd_dependency_closure.py`.
- Evidence: `evidence/A/W06` (path runs), `W08/W09/W13` (analysis
  sidecars), `docs/owner-integration/` (decisions + sync manifests).

## Verification gates carried forward

- A/D verification semantics: owner-approved separation (D authorizes
  health claims only).
- Critical-Tmean: numeric freeze reserved to Member D.
- Clock sync: USB-provided time — selected, not yet implemented; all
  unsynchronized paths fail closed.
- The 30-min H8-E-1800s capture + W13 timing sidecars carry the measured
  electrical/thermal response numbers.
