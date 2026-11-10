# A/D verification-semantics decision record (Phase 4, F3)

Status: **REQUIRES_CROSS_TEAM_CONTRACT_DECISION** (Members A + D must both
sign; Phase 4 does not make this decision).

## The semantic conflict (both sides read from their committed sources)

**Member A — `firmware/tools/cg_command_trace.py`** (per-run stage
promotion): a run's stages promote
`COMMAND_SEEN → DEVICE_ACK → APPLIED_STATE → ELECTRICAL_VERIFIED →
THERMAL_VERIFIED` when the attributed frames carry a fresh electrical
reading at/above the analysis floor and a chamber movement in the requested
direction (±0.25 °C analysis choice). A reached stage is a *per-run
observational promotion*: possible on one capture that happened to be
recorded near a characterized operating point.

**Member D#90 — `control/src/coldguard_control/verification.py`** (Doc 02
§35-36): `VERIFIED`/`HEALTHY_RESPONSE` require an
`EnvelopeQualification.QUALIFIED` envelope — frozen from an *approved
characterization source* — plus observed applied ON, valid current/power,
and a quality-tagged thermal baseline AND follow-up at the response
deadline. A's W08/W09 electrical numbers are real observations whose status
tokens are empty (`usable_for_a_health_claim: false`), so D's tracker marks
the imported candidate envelope `CANDIDATE_UNQUALIFIED` and **terminates at
`UNKNOWN`** — it can report "a response was observed" but never "verified".

## Why the conflict is real

The same physical capture legitimately reaches `ELECTRICAL_VERIFIED` /
`THERMAL_VERIFIED` in A's ledger while D's tracker reports `UNKNOWN` for the
identical frames. Both are honest under their own contracts; the conflict
is the promotion *authority*: A's tool uses characterized-looking analysis
thresholds per run, D's requires the characterization itself to be an
approved, frozen envelope.成员 D's rule is strictly stronger, and nothing in
A's evidence today states the envelope is approved-frozen.

## The minimal decision to request (owner drafts it, members approve)

1. A's per-run promoted stages are recorded as **observational run-level
   promotions** with the vocabulary kept (`*_VERIFIED` names stay, with a
   `usable_for_a_health_claim: false` marker attached).
2. D#90's tracker remains the **only authority** for
   `CoolingHealthState.VERIFIED` / `HEALTHY_RESPONSE` health claims.
3. A characterization campaign whose output D freezes into a
   `QUALIFIED` envelope closes the gap; until then the six-path board's
   physical claims stay capped at `PARTIAL` even when A's trace shows a
   full stage chain.

## What Phase 1–4 components do while the decision is open

- The command-path runner/trace reports carry A's promotion but never map
  it into D's `CoolingHealthState` or `EnvelopeQualification` vocabularies
  (`device_mode` and `PolicyState` stay separate for the same reason).
- The B→D closure sidecar's `prediction_views` stay `UNAVAILABLE` and its
  labels uncensored-honest, so no D-qualified health claim is fabricated.
- The W13/W06 evidence sidecars keep their honest-verdict gates
  (`validate_w13.py` refuses a whole-team GREEN; `validate_w06.py` keeps
  "honest verdict intact").
