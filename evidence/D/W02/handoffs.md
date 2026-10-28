# W02 handoffs to A, B and C

**Status:** draft interface handoff, not an acceptance record. Each row needs
the receiving owner's confirmation before it is frozen.
**Sources:** Doc 04 §6 (ownership), §10.3/§10.7/§10.8 (handoff), Doc 05D
§30.1–30.6 and §34; Doc 02 §21–32/§37–38.

## 1. D → A (local control / firmware)

| ID | D provides | A must confirm / provide | Status |
|---|---|---|---|
| H-A-01 | `PolicyInput`/`PolicyDecision` field list and meaning | Mapping to real sensor/actuator state; who computes `age_s` | Draft |
| H-A-02 | Gate order: lockout → critical → fault → stale → SAFE_LOCAL → predictive | Hardware default-off and lockout output behavior at boot/reset | Open |
| H-A-03 | `OFF` is the safe direction; `ON` requires confirmed fan and usable thermal state | Hardware fan interlock and TEC driver truth table | Open |
| H-A-04 | `CRITICAL_PROTECTION` latches above the lower recovery boundary | Characterization of upper/lower values, hysteresis and sensor placement | Open — no numbers frozen |
| H-A-05 | Thermal freshness field `thermal_max_age_s` | Sensor sampling/age semantics and a defensible bound | Open |
| H-A-06 | `INVALID`/`UNKNOWN` cannot authorize action; `DEGRADED` is not VALID | Sensor quality classifier and degraded representative rules | Open |
| H-A-07 | Command validator expects fan/state evidence and refuses ON on `fan_available != True` | How fan availability is measured and debounced | Open |
| H-A-08 | `FAULT`/`FAULT_LOCKOUT` require hardware/W10 reset semantics | Lockout latch/reset procedure and physical safe state | Open |
| H-A-09 | No invented thresholds; `PolicyConfig` is mandatory and versioned | The actual characterized values | Open — W11/W12 |

## 2. D → C (backend / cloud / integration)

| ID | D provides | C must confirm / provide | Status |
|---|---|---|---|
| H-C-01 | Policy-state vocabulary and transition labels (`transition`) | Persisted state schema, event naming and retention | Draft |
| H-C-02 | `PolicyDecision` fields: state, intent, controller, reason, policy_version, missing exit requirements | API/telemetry mapping; must not expose intent as "physical state" | Draft |
| H-C-03 | Reason codes (Doc 02 §58–59, 05D §28) and canonical rejection code rule | Reason-code storage/query and UI display semantics | Draft |
| H-C-04 | TTL/expiry and duplicate semantics | Command lifecycle implementation, dedup persistence window, replay test | Open |
| H-C-05 | `authorized` is asserted by the caller; validator cannot verify credentials | Backend authn/authz and broker identity/ACL evidence | Open — P0 |
| H-C-06 | SAFE_LOCAL entry/exit requires reconciled, fresh, trusted state | Twin state synchronization/versioning and reconnect semantics | Open |
| H-C-07 | Prediction must be READY/fresh/version-matched when predictive is enabled | Prediction record fields, freshness, model health propagation | Open |
| H-C-08 | ACK is not physical verification | Separate applied/verified events and UI wording | Open — W04/W12 |
| H-C-09 | No DB/UI/model → command source path | Broker ACL and backend command-creation authorization | Open — P0 |

## 3. D → B (model interface, informational)

| ID | D provides | B must provide | Status |
|---|---|---|---|
| H-B-01 | Prediction is advisory only; cannot actuate | Model/feature version and health status | Open |
| H-B-02 | Risk must be in [0,1] with a horizon | Risk semantics, horizon, persistence evidence | Open |
| H-B-03 | `watch_threshold`, `preemptive_threshold`, `persistence_required_s`, `prediction_max_age_s` are policy config, not model output | Candidate thresholds + false-warning/EWT evidence | Open |
| H-B-04 | Stale/unhealthy prediction → SAFE_LOCAL when predictive is enabled | Freshness/version-mismatch signaling | Open |
| H-B-05 | Degraded/missing sensor evidence blocks predictive action | Which degraded feature sets the model supports | Open |

## 4. What D needs before freezing policy v1

```text
[ ] A: upper/lower threshold + hysteresis characterization
[ ] A: sensor quality/degraded representative rules
[ ] A: fan availability evidence and hardware interlock behavior
[ ] A: OFF-current and ON-response envelopes; hot-side stop condition
[ ] A: lockout latch/reset and boot default-off measurement
[ ] B: model/feature versioning, risk semantics, horizon, persistence,
       false-warning rate, EWT/AIW, limitations
[ ] C: twin-state synchronization semantics and freshness
[ ] C: command lifecycle, dedup persistence, ACK/applied/verified events
[ ] C/infra: device identity, broker TLS/ACL, backend authz, audit
```

Until these are supplied, `PolicyConfig` values in planned W03 unit tests are synthetic and
unacceptable for commissioning.

## 5. Non-negotiables in every handoff

1. The model never gets an actuator or command publish path.
2. Any layer may reject; only the local safety gate can authorize energization.
3. ACK is not physical proof; physical verification is separate.
4. Reconnect does not restore remote trust; the full SAFE_LOCAL exit gate is
   required.
5. No hidden numbers in code or docs; every operating value has a versioned
   owner and evidence.
6. A failure is never silently ignored; it is degraded, fallen back, locked out
   or explicitly marked `NOT_CONTRACTED`.
