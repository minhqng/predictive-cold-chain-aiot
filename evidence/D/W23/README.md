# Week 23 — Demo hardening and security/resilience rehearsal

**Status: PURE ASSESSMENT MODULE IMPLEMENTED; HOST SIMULATION TESTED; LIVE REHEARSAL PENDING.**

The `demo_rehearsal.py` module implements Doc 05D section 55 (D-W23-01..D-W23-05) as a
pure typed decision layer. It models four required demo scenes and three full
rehearsal records for defense preparation.

## Module Structure

### RehearsalScene

The four required Week 23 demo scenes:

```python
RehearsalScene.VERIFIED_ACTUATION    # D-W23-01
RehearsalScene.SAFE_LOCAL            # D-W23-02
RehearsalScene.STALE_COMMAND         # D-W23-03
RehearsalScene.SECURITY_EXPLANATION  # D-W23-04
```

### SceneOutcome

Each scene has explicit required outcomes:

| Scene | Outcomes |
|---|---|
| VERIFIED_ACTUATION | PREDICTION_VALID, THRESHOLD_CROSSED, POLICY_DECISION_MADE, COMMAND_ISSUED, ACK_RECEIVED, ELECTRICAL_VERIFIED, THERMAL_VERIFIED |
| SAFE_LOCAL | DISCONNECT_DETECTED, MODE_TRANSITION_TO_SAFE_LOCAL, LOCAL_PROTECTION_ACTIVE, RECONNECT_SUCCESSFUL, NO_STALE_COMMAND_REPLAY |
| STALE_COMMAND | STALE_COMMAND_REJECTED, NO_ACTUATION_ON_STALE, AUDIT_EVENT_RECORDED |
| SECURITY_EXPLANATION | TLS_PURPOSE_EXPLAINED, ACL_PURPOSE_EXPLAINED, AUTHORIZATION_PURPOSE_EXPLAINED, TTL_PURPOSE_EXPLAINED, IDEMPOTENCY_PURPOSE_EXPLAINED |

### RehearsalMetrics

Each rehearsal record measures three dimensions:

```python
RehearsalMetrics(
    failure_recovery=True,       # Ability to recover from injected faults
    operator_clarity=True,       # Clear state transitions and reason codes
    end_to_end_latency_ms=150,   # Recorded latency
    timing_recorded=True,        # No undocumented numeric pass bound
)
```

### RehearsalRecord

One complete rehearsal with all four scenes:

```python
RehearsalRecord(
    record_id="REC-01",
    authority=RehearsalAuthority.LIVE_REHEARSAL,  # or HOST_SIMULATED
    scene_evidence=(...),      # All four SceneEvidence
    metrics=RehearsalMetrics(...),
    scene_assessments=(...),   # Per-scene pass/fail
    all_scenes_pass=True,      # All scenes + metrics pass
    blockers=(...),            # Explicit failure reasons
)
```

### assess_rehearsal()

The main assessment function returns a `RehearsalDecision` with:

- `records` — all submitted rehearsal records;
- `missing_records` — count of records short of required three;
- `passing_records` — count of records with all scenes passing;
- `live_rehearsal_complete` — True when at least 3 LIVE_REHEARSAL records pass;
- `readiness_achieved` — True when live_rehearsal_complete is True;
- `blockers` — explicit list of issues preventing readiness.

## Required Scenes

### D-W23-01 — Verified Actuation

Demonstrates the complete control chain:

```text
prediction/threshold
→ policy decision
→ command issued
→ ACK received
→ electrical verified
→ thermal verified
```

**Outcomes required:**
- PREDICTION_VALID
- THRESHOLD_CROSSED
- POLICY_DECISION_MADE
- COMMAND_ISSUED
- ACK_RECEIVED
- ELECTRICAL_VERIFIED
- THERMAL_VERIFIED

### D-W23-02 — SAFE_LOCAL

Demonstrates resilience during remote path loss:

```text
disconnect detected
→ mode transition to SAFE_LOCAL
→ local protection active
→ reconnect successful
→ no stale command replay
```

**Outcomes required:**
- DISCONNECT_DETECTED
- MODE_TRANSITION_TO_SAFE_LOCAL
- LOCAL_PROTECTION_ACTIVE
- RECONNECT_SUCCESSFUL
- NO_STALE_COMMAND_REPLAY

### D-W23-03 — Stale Command

Demonstrates command integrity defense:

```text
stale command presented
→ rejected with reason
→ no actuation
→ audit event recorded
```

**Outcomes required:**
- STALE_COMMAND_REJECTED
- NO_ACTUATION_ON_STALE
- AUDIT_EVENT_RECORDED

### D-W23-04 — Security Explanation

Explains distinct security layer purposes:

| Layer | Purpose |
|---|---|
| TLS | Encrypted transport, prevents eavesdropping/tampering |
| ACL | Broker-level topic authorization, prevents unauthorized publish |
| Authorization | Backend command authorization, prevents role escalation |
| TTL | Command freshness, prevents stale command replay |
| Idempotency | Duplicate prevention, prevents repeated physical action |

**Outcomes required:**
- TLS_PURPOSE_EXPLAINED
- ACL_PURPOSE_EXPLAINED
- AUTHORIZATION_PURPOSE_EXPLAINED
- TTL_PURPOSE_EXPLAINED
- IDEMPOTENCY_PURPOSE_EXPLAINED

## Rehearsal Records

### D-W23-05 — Three Full Rehearsals

Readiness requires at least three passing `LIVE_REHEARSAL` records.
Each record measures:

1. **failure_recovery** — Demonstrates recovery from injected faults
2. **operator_clarity** — Clear state transitions and reason codes
3. **timing** — End-to-end latency within bounds (≤500ms)

**Important:** Host simulation can validate the decision contract, but only
`LIVE_REHEARSAL` authority records count toward readiness.

## Evidence Authority

The module distinguishes:

- `RehearsalAuthority.HOST_SIMULATED` — Host-based simulation/testing;
- `RehearsalAuthority.LIVE_REHEARSAL` — Live rehearsal with operator present.

**This module does not claim live rehearsal completion.** Host simulation can
validate the contract, but only live rehearsal evidence can mark W23 complete.

## Usage Example

```python
from coldguard_control.demo_rehearsal import (
    RehearsalAuthority,
    RehearsalScene,
    REQUIRED_SCENE_OUTCOMES,
    SceneOutcome,
    build_demo_rehearsal_record,
    assess_rehearsal,
)

# Build a host-simulated record
host_record = build_demo_rehearsal_record("REC-HOST-01")
assert host_record.all_scenes_pass is True
assert host_record.authority is RehearsalAuthority.HOST_SIMULATED

# Live records require provenance and explicit outcomes for every scene; the
# helper never upgrades its host defaults to live evidence.
live_records = [
    build_demo_rehearsal_record(
        f"REC-LIVE-{i}",
        authority=RehearsalAuthority.LIVE_REHEARSAL,
        override_outcomes={scene: REQUIRED_SCENE_OUTCOMES[scene] for scene in RehearsalScene},
        evidence_ref=f"evidence/D/W23/REC-LIVE-{i}.json",
        operator_identity="member-C",
    )
    for i in range(1, 4)
]

# Assess complete rehearsal campaign
decision = assess_rehearsal(live_records)
assert decision.live_rehearsal_complete is True
assert decision.readiness_achieved is True
assert decision.blockers == ()

# Host-only cannot claim readiness
host_records = [
    build_demo_rehearsal_record(f"REC-HOST-{i}", authority=RehearsalAuthority.HOST_SIMULATED)
    for i in range(1, 4)
]
decision = assess_rehearsal(host_records)
assert decision.passing_records == 3
assert decision.live_rehearsal_complete is False
assert decision.readiness_achieved is False
```

## Tests

The `test_demo_rehearsal.py` suite verifies:

- Enum definitions (4 scenes, all outcomes);
- RehearsalMetrics validation (strict booleans, non-negative latency);
- SceneEvidence validation (type checks, immutability);
- RehearsalRecord validation (all scenes required, metrics gating);
- assess_rehearsal logic (3 LIVE_REHEARSAL required, host cannot claim readiness);
- Doc 05D section 55 compliance (all four scenes, three records, metrics).

## Limitations

- **No live rehearsal claimed** — all records default to HOST_SIMULATED;
- **No physical execution** — pure assessment layer only;
- **No transport/actuation** — does not emit commands or execute scenarios;
- **Pure assessment** — validates caller-supplied evidence, does not generate it.

## Gate G6 Readiness

This module supports Gate G6 (final defense preparation) by providing:

1. Structured demo scene definitions;
2. Explicit outcome requirements per scene;
3. Rehearsal record tracking with metrics;
4. Clear readiness gating (3 LIVE_REHEARSAL records required).

**G6 requires live rehearsal evidence** for demo readiness. This module provides
the decision structure; live rehearsals must supply LIVE_REHEARSAL authority
records.

## Readiness Checklist

| Requirement | Status |
|---|---|
| VERIFIED_ACTUATION scene defined | ✅ |
| SAFE_LOCAL scene defined | ✅ |
| STALE_COMMAND scene defined | ✅ |
| SECURITY_EXPLANATION scene defined | ✅ |
| Three rehearsal records modeled | ✅ |
| Failure recovery metric tracked | ✅ |
| Operator clarity metric tracked | ✅ |
| Timing metric tracked | ✅ |
| Host simulation tested | ✅ |
| LIVE_REHEARSAL evidence | ⏳ PENDING |
