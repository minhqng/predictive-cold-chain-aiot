# D-W11-04 — candidate incident-action map

**Status: CANDIDATE_NOT_RUNTIME_APPROVED.** This is a Member D policy proposal,
not an actuator implementation or G3 signoff. The pure function
`recommend_incident_actions()` returns recommendations only. Member A's safe
fault captures and the A/C/D review must precede runtime enforcement.

| Observed cooling-health state | Candidate actions | Deliberately withheld |
|---|---|---|
| HEALTHY_RESPONSE | none | incident action |
| ELECTRICAL_RESPONSE_MISSING | WARN, BLOCK_PREDICTIVE | automatic lockout or force OFF; W10 oracle says HOLD and no invented lockout |
| THERMAL_EFFECTIVENESS_DEGRADED | WARN, BLOCK_PREDICTIVE | component diagnosis or automatic physical action without controlled evidence |
| CONTROL_ELECTRICAL_ANOMALY | WARN, BLOCK_PREDICTIVE, ENTER_LOCKOUT | assuming an OFF command actually removes unexpected current; hardware interlock remains authoritative |
| UNKNOWN | WARN, BLOCK_PREDICTIVE; USE_LOCAL_THRESHOLD only if thermal safety state is usable | treating missing electrical evidence as healthy, or using invalid thermal state |

`FORCE_OFF` is not selected automatically by this candidate map. An unsafe
electrical state may not respond to a software OFF request. The final action
must be chosen against the characterized hardware stop path and reviewed fault
oracles. No root cause is inferred from an observable response class.

This closes the **draft mapping** part of D-W11-04. Physical disposition,
runtime enforcement and D-W11-01/02/03/05 stay open.

Sources: Doc 01 §23, Doc 02 §36, Doc 05D D-W11-04, and the W10 fault oracle.
