# W01 evidence — safety hierarchy, hazard ledger, trust boundary, security baseline

## Goal

Define what may never happen before control code exists, and make the device,
broker, backend, database, frontend, model and operator authority boundary
explicit. W01 has no physical or control-code test scope.

## Deliverables

| Deliverable | File | W01 status |
|---|---|---|
| Safety hierarchy | `safety-hierarchy.md` | Complete as v0 design |
| Hazard ledger (≥11 hazards) | `hazard-ledger-v0.md` | 16 rows; qualitative and open items explicit |
| Trust-boundary diagram | `trust-boundary.png` | Rendered; seven actors and forbidden path shown |
| Editable diagram source | `trust_boundary_source.py` | Reproducible stdlib renderer |
| Trust-boundary explanation | `trust-boundary.md` | Complete as design |
| P0 security baseline | `security-baseline-v0.md` | Requirements only; not deployed or tested |

## Reproduction check

From repository root:

```powershell
python evidence\D\W01\trust_boundary_source.py
```

Expected: rewrites `trust-boundary.png` deterministically. No graphics package,
physical device, broker, database, credentials or control code is used by this
W01 renderer. The rendered PNG was visually checked for the seven actors, the
model's advisory-only relationship and the red blocked model-to-actuator path.

## Design acceptance

| Check | Evidence | Verdict |
|---|---|---|
| Authority chain | `safety-hierarchy.md` §1–3 | PASS (design) |
| Required hazards | `hazard-ledger-v0.md`: 16 rows, including all 11 Doc 05D minimum hazards | PASS (design) |
| Trust-boundary actors and permissions | `trust-boundary.md` + diagram | PASS (design) |
| No conceptual model → GPIO path | Diagram + forbidden-path list | PASS (design only) |
| P0 identity/TLS/ACL/authz/TTL/idempotency/audit | `security-baseline-v0.md` §1 | Specified, not verified |
| Optional hardening separated | `security-baseline-v0.md` §2 | PASS (scope) |

The automated test names in the hazard ledger and hierarchy are **planned
W03 verification targets**, not tests executed or included in this W01 branch.
The subsequent stacked W03 change supplies the pure policy/validator unit
implementation; this W01 change does not claim it exists.

## Limitations / unverified

- No broker TLS, ACL, backend authz, device provisioning, audit storage,
  penetration test or physical default-OFF measurement was performed.
- The hazard ledger is qualitative; it does not claim quantitative risk
  acceptance or a completed FMEA.
- Control-task starvation, watchdog behavior, board boot output and actuator
  interlocks require firmware/hardware evidence from the owning members.
- Thresholds, hysteresis, freshness, TTL and duty limits are not frozen.
