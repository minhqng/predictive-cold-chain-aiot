# Member D W07 — Controller A candidate

**Status:** unit implementation and replay only; physical baseline freeze and first real Controller A run remain OPEN.

`control/src/coldguard_control/controller_a.py` adds deterministic hysteresis, optional persistence/dwell, and replay. `control/tests/test_controller_a.py` exercises synthetic rising, recovery, noise, invalid sensor, and reset paths. The JSON candidate in this folder is a **synthetic test fixture**, not a characterized threshold or commissioning config.

| Item | Evidence now | Remaining gate |
|---|---|---|
| D-W07-01 threshold source | `PolicyConfig.representative_source` explicit; A W07 handoff reviewed | Choose a physical representation and qualified thresholds with A. A W07 handoff says n=1 and physical roles/representation remain unsettled. |
| D-W07-02/03 hysteresis/persistence | Pure Controller A and replay test | Freeze upper/lower/persistence from independent plant runs. |
| D-W07-04 minimum dwell | Optional config and replay test | Enable only with switching/chatter evidence. |
| D-W07-05 tests | Synthetic tests pass in the stacked branch | Review against real capture once qualified. |
| D-W07-06 first real run | No Member D device run | A/D supervised capture, command and physical response trace. |

Source: `evidence/A/W07/handoff.md`; Doc 05D §39. No real actuation or safety signoff is claimed.
