# A-W13 handoff — physical timing that B and D can actually use

Week-scoped slice of the docs/05A §5 / §6.1–§6.3 handover. Payloads are
`plant-timing-report.json`, `response-delay.csv`, `door-critical.csv` and
`data-gap-register.csv`. Every interval here is computed on a **device** clock, and each
block carries `boot_continuity` so a consumer can see whether the number crossed a reboot.

## A → B (§6.1)

| Field | W13 value | State |
|---|---|---|
| physical response delay | command-accept → electrical onset **1.094 s**, `median = P95 = max = 1.094` with **n=1** | `REAL_DATA_ANALYZED`, explicitly *not a distribution*. Quantisation is stated: onset is the first 1 Hz poll at/above the 0.1 A threshold, so the true delay is **1.094 s ± 1 s** |
| command → thermal | 1 °C reached at **0.85 min** (51 s) after applied-on, raw first-crossing, no smoothing; baseline is the mean of the first 5 fully-valid driven frames | `REAL_DATA_ANALYZED`, one session. `excluded_nonvalid_frames: 0` says what was dropped rather than hiding it |
| door → critical | **no number emitted** | `NOT_COMPUTABLE`: no door-open event exists in any committed capture (`door_open` is only `0`/`UNKNOWN`, no confirmed open polarity). The gap register names the session that would produce it |
| time constants | cooling τ ≈ **174 s**, recovery τ ≈ **86 s** | **Proxy**, not a fitted tau. Each block states its own limitation: the swing uses observed endpoints, so a run that has not reached steady state **underestimates** τ. The passive segment reports **no** tau because the signal shows no first-order rise — a number was not manufactured for it |

## A → D (§6.3)

D's thermal response window comes from `command_to_thermal` and the two τ proxies, with the
bias direction spelled out so a threshold is never set from a value known to be low. Nothing
here is a limit: W13 measures the plant, D chooses the thresholds, and the fail-closed
firmware posture (output stage compiled out, six limits `UNRESOLVED`) is unchanged by any
number in this dossier.

## A → C (§6.2)

One fact matters and it is operational, not schema: the H6 console trace's bracket column is
**device log uptime**, not host wall clock, and the ~0.156 s operator-keystroke → `START
accepted` segment is excluded from the reported interval. Any consumer correlating device
timestamps with host logs must respect that boundary. The H6 trace carries no `boot_id`
column, so boot continuity there is recorded as `UNVERIFIED` — and the tool refuses any
interval that crosses a `boot_id` change.

## What only a session can give W13

- Three to five console `START → ON → OFF` traces, which is what turns `1.094 s` from one
  observation into a median with a spread. The single-trace basis is stated in the artifact,
  not in a footnote.
- A longer steady-state cooling run, so τ stops being a truncated-window proxy.
- A supervised door-disturbance pilot with confirmed open polarity — the only path to
  door→critical, and the gap is published instead of estimated.
