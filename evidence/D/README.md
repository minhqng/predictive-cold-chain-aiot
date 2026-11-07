# Member D evidence — W01–W06

**Date:** 2026-11-07
**Owner:** Member D (control / safety / security / resilience)
**Precedence used:** Docs 00–03 (correctness) → Doc 04 (ownership/schedule) →
Doc 05D (Member D scope). No child document was used to weaken a parent
invariant.

> This directory contains design and unit evidence for Member D weeks W01–W06.
> It is not a safety case, not a certification and not physical test evidence.
> Member C's backend W03 is a different work package and is not claimed complete
> by this work.

## 1. What is actually implemented (W01–W06)

```text
control/src/coldguard_control/
  types.py       frozen vocabulary (quality, states, actions, ACK, reason codes, verification)
  config.py      mandatory versioned PolicyConfig; TTL/freshness bounds (W04/W05)
  policy.py      pure PolicyInput -> PolicyDecision, 7 states, SAFE_LOCAL gate
  commands.py    pure command validator (schema -> ... -> state freshness) + TTL (W04/W06)
  taxonomy.py    Doc 01 §28 failures -> DEGRADE/FALLBACK/LOCKOUT/NOT_CONTRACTED
  quality.py     physical-quality input contract (W05)
  device_safety.py  device/actuator safety input contract (W04)
  __init__.py    public exports

control/tests/
  test_policy_priorities.py
  test_policy_states.py
  test_command_matrix.py
  test_command_ttl.py           (W04/W06)
  test_device_safety.py         (W04)
  test_quality.py               (W05)
  test_taxonomy.py
  test_purity.py
  test_package.py (pre-existing smoke test)
```

Nothing in the package imports or calls MQTT, a database, GPIO, FastAPI,
serial, a clock, or an actuator. The package does not publish commands, run a
controller loop, or verify physical cooling.

## 2. Weekly evidence

| Week | Focus | Evidence |
|---|---|---|
| W01 | Safety hierarchy, hazard ledger, trust boundaries | `W01/` |
| W02 | Policy states, SAFE_LOCAL entry/exit, validator contract | `W02/` |
| W03 | Pure policy unit, command matrix, failure taxonomy | `W03/` |
| W04 | Command TTL semantics, device safety review | `W04/` |
| W05 | Physical-quality integration, stale-state prevention | `W05/` |
| W06 | Command negative tests, lifecycle integration | `W06/` |

## 3. Test result (actual)

From `control/`:

```powershell
uv run --locked --extra test pytest
```

```text
370 passed in 0.77s
```

Inventory:
* 14 policy priority tests
* 35 policy state tests
* 33 command matrix tests
* 11 command TTL tests (W04/W06)
* 18 device safety tests (W04)
* 12 quality tests (W05)
* 88 non-finite regression tests
* 43 enum-type regression tests
* 66 boolean-type regression tests
* 34 taxonomy tests
* 5 purity tests
* 1 package smoke test

`--locked` succeeded; no lockfile change was needed.

## 4. Read order

1. `W01/safety-hierarchy.md` — what may never happen.
2. `W01/hazard-ledger-v0.md` — hazards and current status.
3. `W01/trust-boundary.md` + `trust-boundary.png` — who can authorize what.
4. `W01/security-baseline-v0.md` — P0 vs optional; non-claims.
5. `W02/policy-states.md` — seven states.
6. `W02/transitions.md` — every transition and SAFE_LOCAL entry/exit.
7. `W02/command-validator-contract.md` — check order/ACK meaning.
8. `W02/handoffs.md` — what A/B/C still owe.
9. `W03/README.md`, `command-matrix.md`, `failure-taxonomy.md`,
   `policy-unit.md` — W03 implementation/test evidence.
10. `W04/README.md` — TTL semantics and device safety.
11. `W05/README.md` — physical-quality integration.
12. `W06/README.md` — command negative tests and lifecycle.

## 5. Honest status summary

| Area | Status |
|---|---|
| W01 deliverables | Complete as v0 design/evidence |
| W02 deliverables | Complete as v0 design + pure implementation |
| W03 unit scope | Complete; 319 tests pass (subset of 370) |
| W04 TTL semantics | Complete; 11 tests pass |
| W04 device safety | Complete; 18 tests pass |
| W05 quality integration | Complete; 12 tests pass |
| W06 negative tests | Complete; covered by command matrix + TTL tests |
| Physical/plant verification | Not started in this slice |
| P0 security deployment | Not verified; requirements only |
| Thresholds/timings freeze | Open — needs A characterization and B contract |
| Stale/fault incident policy | Open — W10/W11 |
| Control-task timing/watchdog | Open — A/firmware/W13 |
| Backend/broker/DB integration | Not in W03–W06; W04+/C |

## 6. Constraints observed

* No secrets, certificates or real credentials were added.
* No physical fault injection and no device command was issued.
* No threshold, deadline or duty bound was invented; synthetic test values are
  labelled and carry no commissioning authority.
* `README.md` and `control/pyproject.toml` were updated only to describe the
  actual W01–W06 state instead of a skeleton.
* All changes scoped to Member D control/evidence.
