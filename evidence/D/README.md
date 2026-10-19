# Member D evidence — W01–W03

**Date:** 2026-10-19
**Owner:** Member D (control / safety / security / resilience)
**Precedence used:** Docs 00–03 (correctness) → Doc 04 (ownership/schedule) →
Doc 05D (Member D scope). No child document was used to weaken a parent
invariant.

> This directory contains design and unit evidence for the first three Member D
> weeks. It is not a safety case, not a certification and not physical test
> evidence. Member C's backend W03 is a different work package and is not
> claimed complete by this work.

## 1. What is actually implemented

```text
control/src/coldguard_control/
  types.py       frozen vocabulary (quality, states, actions, ACK, reason codes)
  config.py      mandatory versioned PolicyConfig; no numeric defaults
  policy.py      pure PolicyInput -> PolicyDecision, 7 states, SAFE_LOCAL gate
  commands.py    pure command validator (schema -> ... -> state freshness)
  taxonomy.py    Doc 01 §28 failures -> DEGRADE/FALLBACK/LOCKOUT/NOT_CONTRACTED
  __init__.py    public exports

control/tests/
  test_policy_priorities.py
  test_policy_states.py
  test_command_matrix.py
  test_taxonomy.py
  test_purity.py
  test_package.py (pre-existing smoke test)
```

Nothing in the package imports or calls MQTT, a database, GPIO, FastAPI,
serial, a clock, or an actuator. The package does not publish commands, run a
controller loop, or verify physical cooling.

## 2. Criteria → source → current state → gap → fix → evidence

| Criterion | Source | Current state | Gap / limit | What was done | Evidence |
|---|---|---|---|---|---|
| W01-01 safety hierarchy | Doc 00 §2.7/§4.3/§4.7; Doc 02 §21–23; 05D §33 | One-page authority chain + gate order + non-negotiables | Design only; thresholds not frozen | `safety-hierarchy.md` | W01/`safety-hierarchy.md` |
| W01-02 hazard ledger | 05D D-W01-02 (11 named hazards) | 16 hazards, each with prevention/detection/mitigation/evidence/status | Qualitative; no risk scoring; 3 hazards open | `hazard-ledger-v0.md` | W01/`hazard-ledger-v0.md` |
| W01-03 trust boundary | 05D D-W01-03 (7 actors) | Rendered PNG + editable stdlib source + actor permissions | No network/config validation | PNG, `trust_boundary_source.py`, `trust-boundary.md` | W01 |
| W01-04 P0 security baseline | 05D D-W01-04 | Identity/TLS/ACL/authz/TTL/idempotency/audit specified; optional Secure Boot/Flash/OTA separated | P0 infrastructure not deployed or tested; auth evidence is an asserted input | `security-baseline-v0.md` | W01 |
| No model → GPIO | 05D W01 pass criteria | Advisory-only type path; forbidden path in diagram; purity tests | Code-level guard only; broker ACL/architecture review still required | type/API design + AST tests | `test_purity.py`, `trust-boundary.png` |
| W02-01 seven states | 05D D-W02-01/§3 | All seven states implemented with meaning, intent, controller, reasons | FAULT/stale semantics provisional | `policy-states.md`, `types.py` | `test_policy_states.py` |
| W02-02 transition table | 05D D-W02-02 | 25 transitions with source/condition/destination/action/reason | Model-checked? No | `transitions.md`, TR-01..TR-25 | `test_policy_states.py` |
| W02-03 SAFE_LOCAL entry | Doc 02 §37; 05D D-W02-03 | Broker/backend/sync/command-path/AI triggers | Device mode transition owned by firmware | gate P8/P9 | SAFE_LOCAL tests |
| W02-04 SAFE_LOCAL exit | Doc 02 §38; 05D §19 | All-of gate: stable network, reconciled state, fresh VALID telemetry, no stale command, no fault, healthy prediction if enabled | Timings synthetic | `safe_local_exit_status()` + missing list | `test_reconnect_alone_does_not_restore_remote_trust` |
| W02-05 validator contract | Doc 02 §31–32/§63; 05D D-W02-05 | Draft contract + implementation, 8 ordered checks | Authorization verification/dedup persistence/ACK lifecycle external | `command-validator-contract.md`, `commands.py` | `test_command_matrix.py` |
| W02 handoff A/C | Doc 04 §10; 05D §30/§34 | Draft handoff tables with named missing inputs | Not signed by A/B/C | `handoffs.md` | W02/`handoffs.md` |
| W03-01 pure policy | 05D D-W03-01 | `PolicyInput → PolicyDecision`; no I/O/clock/global state | No runtime controller | `policy.py` | priority/purity tests |
| W03-02 command matrix | 05D D-W03-02 (7 cases) | 33 tests: fresh ON, expired, duplicate, wrong device, range, invalid state, safety fault + edges | No wire/MQTT/ACK integration | `commands.py` + matrix evidence | `command-matrix.md` |
| W03-03 failure taxonomy | 05D D-W03-03; Doc 01 §28 | All 14 failures mapped; no `IGNORE`; 4 `NOT_CONTRACTED` | Detection/incident action owned by A/W11 | `taxonomy.py`, `failure-taxonomy.md` | `test_taxonomy.py` |
| W03-04 priority assertions | 05D D-W03-04 | CRITICAL > PREEMPTIVE; FAULT > optimization; lockout > both; stale prediction never reused | Unit level only | gate order + tests | `test_policy_priorities.py` |
| Non-finite inputs fail closed | Review follow-up (fail-open NaN) | NaN/±inf/bool rejected in config, policy input, SAFE_LOCAL exit and command freshness | No physical value involved | explicit finite guards + regression tests | `test_nonfinite.py` (88 tests) |
| Enum fields are runtime-checked | Review follow-up (raw string bypass) | `PolicyInput`/nested enums and `LocalSafetyEvidence` enums must be actual members; bool `now_s` rejected | No physical value involved | explicit `isinstance` guards before identity comparisons | `test_enum_types.py` (43 tests) |
| Boolean flags are runtime-checked | Review follow-up (truthy `"false"` / falsy fault flags) | Remote trust flags and fault/safety flags must be actual `bool`; `fan_available` is `bool`/`None`; malformed evidence never ACCEPTED | No physical value involved | strict bool guards + fail-closed exit/evidence checks | `test_bool_types.py` (66 tests) |
| Real thresholds/timings | Doc 01 §39; Doc 02 §24.4; Doc 04 §10.3 | **Not invented**; every value mandatory caller config | Not characterized/frozen | numeric-default purity test | `test_policy_config_has_no_numeric_defaults` |
| Physical verification | Doc 02 §32.2; 05D §29 | Explicitly absent from W03 | W04/W11/W12 | decision wording + docs state ACK ≠ proof | W03 README / matrix |

## 3. Test result (actual)

From `control/`:

```powershell
uv run --locked --extra test pytest
```

```text
319 passed in 0.41s
```

Inventory: 14 policy priority, 35 policy state, 33 command matrix,
88 non-finite regression, 43 enum-type regression, 66 boolean-type regression,
34 taxonomy, 5 purity, 1 package smoke test. `--locked` succeeded; no lockfile
change was needed.

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
   `policy-unit.md` — implementation/test evidence.

## 5. Honest status summary

| Area | Status |
|---|---|
| W01 deliverables | Complete as v0 design/evidence |
| W02 deliverables | Complete as v0 design + pure implementation |
| W03 unit scope | Complete; 319 tests pass |
| Physical/plant verification | Not started in this slice |
| P0 security deployment | Not verified; requirements only |
| Thresholds/timings freeze | Open — needs A characterization and B contract |
| Stale/fault incident policy | Open — W05/W10/W11 |
| Control-task timing/watchdog | Open — A/firmware/W13 |
| Backend/broker/DB integration | Not in W03; W04/C |

## 6. Constraints observed

- The original working folder had no Git metadata, so the work was assembled
  from a clean clone of current `origin/main`; no reset or mass deletion was used.
  Existing Member A/B/C files were not modified.
- No secrets, certificates or real credentials were added.
- No physical fault injection and no device command was issued.
- No threshold, deadline or duty bound was invented; synthetic test values are
  labelled and carry no commissioning authority.
- `README.md` and `control/pyproject.toml` were updated only to describe the
  actual W01–W03 state instead of a skeleton.
