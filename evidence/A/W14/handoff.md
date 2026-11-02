# A-W14 handoff — what W14 gives B/C/D

Week-scoped slice of the docs/05A §5 / §6.1–§6.3 handover. Counts quoted below (the
957-row session, the 9 570 long-format rows, 10 feature sets) are a **PHASE SNAPSHOT -
MUST EVOLVE**: they describe the capture set W14 holds today, and `validate_w14.py`
re-derives them, so a second session makes them wrong on purpose. The payload files themselves are
`ablation-support.{json,csv,md}`, `spatial-statistics.json`, `sensor-position-qa.{json,md}`
and `pairing-input.json` / `member-b-handoff.md`; this file only states what each can and
cannot be used for, so a consumer does not have to re-derive the limits.

## A → B (docs/05A §6.1)

| Field | W14 contribution | Honest state |
|---|---|---|
| sensor identity / placement | `sensor-position-qa.json` compares captured role labels and per-channel behaviour against the frozen record (`../W07/geometry-v1.md` §1) | **MATCH** on labels; behaviour signature confirms only `t2_c` rose while the air probes fell. Physical non-movement is **`NEEDS_A_NEW_CAPTURE`** — archived data cannot prove it, and this dossier never prints "no movement verified" |
| pairing context | `pairing-input.json` + `member-b-handoff.md`: initial mean, initial gradient and response variation across what exists | **Input side only.** `tolerance_proposed: false`, `tolerance_value: null`. A structural guard raises if any number ever appears under a tolerance-named key. B freezes the tolerance (A-W14-04 is explicitly "with B") |
| valid/invalid run status, `run_id` | not produced here — W14 consumes W09's registry rather than minting run identity | Single session stays single: every `ablation-support` row carries the capture's conditioning fingerprint (`device_ms/state/pwm_applied_permille/door_open/boot_id` hashed over the rows a statistic walked), and `validate_w14.py` re-derives it and every row's `device_ms` → `feature_c`/`pwm`/`door`/`boot` attribution from the committed CSV. That recomputation, not the stamped field, is what makes "the same physical run" checkable; it is one boot, never three |
| quality flags | every feature set carries `is_chamber_air` / `includes_hot_side` | Hot side is excluded from all chamber-air sets; `require_air()` raises rather than averaging T2 into an air statistic, and W07's flag and the role map cross-check each other at import |
| physical response delay | none — that is W13 | W14 measures spatial field and ablation, not latency |

**What B can use now:** the ablation design itself — 10 feature sets × 3 phases over the *same*
957 rows (9 570 long-format rows joinable on `device_ms`), so a one-probe-versus-three-probe
comparison is physical-condition-controlled rather than run-to-run, exactly as A-W14-02 asks.
No probe was unplugged, and none should be.

**What B must not infer from it:** variance. `spatial-report.md` is labelled
`SINGLE_SESSION_OBSERVATION`; the gradient distribution is `NOT_COMPUTABLE_AS_DISTRIBUTION`
(1 of 3 sessions) and the disturbance-specific response is `NOT_COMPUTABLE` because no door
event was ever applied (`door_open`: 940 × `0`, 17 × `UNKNOWN`, 0 OPEN).

## A → C (§6.2)

Nothing new. W14 adds no telemetry schema, no boot/seq behaviour and no ACK information; C's
inputs remain the W05/W06 fixtures, and W14 does not restate them.

## A → D (§6.3)

Indirect only, and stated as such: the spatial agreement figures (max pairwise air difference
**1.126 °C** during cooling; air-vs-hot-side surface difference **18.938 °C**) describe where
a chamber-air reading is representative of the volume. They are not a threshold, a control
limit or a degraded-state rule, and D's thresholds remain D's.

## Sessions this week needs

- Two more full sessions (three total) before the gradient figure becomes a distribution and
  before any tolerance estimate is more than a form.
- One capture taken under the QA protocol in `sensor-position-qa.md` (ROM/per-channel identity
  readback) to move non-movement from *not verifiable* to *checked*.
- The A-W07-01 geometry items (photo with scale, mounting method/height/clearance, cable path,
  wire-label confirmation), which also gate A-W14-01's physical half.

## Open project decision this week depends on

`docs/01` §20.1's literal `mean(T1,T2,T3)` averages the hot side into what its own name calls
chamber air. On this rig that is a **6.1456 °C** difference from the as-built air mean at the
driven block. W14 refuses to label a hot-side average as air; the naming question stays a
project-level decision, not a W14 one.
