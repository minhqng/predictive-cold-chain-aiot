# Member D assessment after main `557e887`

## Newly usable inputs

- A PR #94/#95 are now merged into main, including the supplementary passive
  S1 package and updated handoff contracts.
- Main now contains D→C→A command projection, ACK translation and a complete
  software lifecycle trace.
- The B→D closure deterministically admits 3,721 rows across nine accepted
  S1/S2 runs and maps every W13 prediction view honestly as `UNAVAILABLE`.
- A's official door-response input records the five S2/timing envelopes without
  inventing a door-to-critical number.

## D result after inspection

The command lifecycle reaches A's observational stages through
`THERMAL_VERIFIED`, but the committed trace declares `firmware_executed=false`
and uses synthetic post-ACK frames. D therefore keeps physical health at
`UNKNOWN`. `verification_bridge.py` now makes this authority boundary
executable: A stage names can enter D's tracker only with physical provenance,
an approved `QUALIFIED` envelope and a health-usable source, and can never
directly promote a D health state.

The predictive path remains disabled: there are zero positive labels, no
usable B prediction, no frozen physical critical definition, no measured
door-to-critical value and no complete measured AIW chain.

## Verification run

- D W04–W13 follow-up control suite: **440 passed**.
- Integrated backend selection (`test_command_path_runner_d90`,
  `test_bd_dependency_closure`, `test_ack_translation`): **33 passed, 1
  infrastructure/dependency-conditioned skip**.

## Work that remains physical or cross-team

- A/D must jointly approve the verification-semantics decision and run the
  characterization that can produce a qualified envelope.
- D cannot honestly freeze the six TEC operating limits or 55 °C hot-side stop
  from the current host/bench evidence alone.
- A must run the stage-enabled supervised characterization after those safety
  inputs and operator gates exist.
- B #103 and C #70–#73 remain open. W14–W17 host gates are delivered in
  separate stacked follow-up PRs; live calibration, ACL/TLS, outage/resync and
  shadow acceptance are not complete.
