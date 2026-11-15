# Week 16 — Resilience gate

**Current status: PURE OUTAGE/RECONNECT MATRIX TESTED; G4 NOT SIGNED.**

C PR #72 was inspected at
`e31d30bce7b6aedb4116385a86dcaaace4f6b142`. Its recovery path reconciles old
pending attempts and expired intent without republishing or inferring device
state.

`resilience.py` covers D-W16-01 through D-W16-05 as a fail-closed decision
matrix:

- AI unavailable or stale prediction → reactive only; never reuse a stale
  score;
- broker/backend unavailable → `SAFE_LOCAL`;
- DB unavailable → no new predictive command requiring durable audit;
- reconnect remains `SAFE_LOCAL` until state is resynced, no stale command is
  pending and the configured stability interval has elapsed.

The all-green software vector reports `software_vector_green=true` but keeps
`g4_ready=false`. G4 additionally requires a live evidence reference plus an
explicit signer and timestamp. Those live outage, local-continuity and
end-to-end resync records do not yet exist, so G4 remains unsigned.
