# Week 18 — Controller B physical enablement preparation

**Current status: PURE ENABLEMENT GATE IMPLEMENTED AND TESTED; FIRST PHYSICAL INTERVENTIONS AND FREEZE REMAIN PENDING.**

## Context and Requirements
Following `docs/05D-member-d-control-security-resilience.md` §50 (Week 18):
- Predictive physical actuation requires an explicit controlled enable request (`enable_requested`).
- The pure fail-closed gate requires all documented preconditions:
  - Gate G4 GREEN
  - Member A physical envelope stable
  - Member B model frozen
  - Member B policy frozen
  - Member B action frozen
  - Member C command/trace stable
  - Complete prediction-to-thermal trace (`prediction → policy → safety gate → command → ACK → applied → electrical → thermal`)
  - Failure behavior frozen (electrical/thermal failure classifies and falls back/locks rather than repeatedly escalating output)
  - Controlled clean dry runs verified
  - Multi-stakeholder review signoffs / witnesses (Member A, Member B, Member C, Member D)

## Implementation
- `enablement.py`:
  - `EnablementPreconditions`: validates the prerequisites plus pinned
    policy/config/action identities and explicit threshold/persistence values.
  - `REVIEW_READY` requires provenance-backed live G4 evidence and signoff;
    an all-green software vector alone remains blocked.
  - `EnablementStatus`: `DISABLED` (when enable is not requested), `BLOCKED` (when requested but any precondition fails), or `REVIEW_READY` (when requested and all prerequisites are verified).
  - Invariant: `physical_command_emitted=False` across all states. The gate is a pure logical evaluation and never directly emits a physical command.
- Public exports in `coldguard_control/__init__.py`.
- Unit tests in `tests/test_enablement.py`.

## Physical Actuation and Freeze Status
- **First physical interventions remain pending:** live physical bench execution, fuse installation, and unenergized pre-run checklists remain blocked on physical operator attendance and hardware tests.
- **Controller B freeze remains pending:** formal freeze candidate signoff will only follow observed clean dry runs and multi-member audit.
- No physical actuation commands have been issued.
