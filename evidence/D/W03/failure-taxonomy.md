# W03 failure taxonomy (Doc 01 §28 → disposition)

**Implementation:** `control/src/coldguard_control/taxonomy.py`
**Tests:** `control/tests/test_taxonomy.py`
**Status:** v0 mapping. `NOT_CONTRACTED` is deliberate; it means the control
disposition is owned by a later work package and is not approved yet.

## 1. Rule set

Doc 05D D-W03-03 asks: ignore / degrade / fallback / lockout? W03 answers:

- There is **no `IGNORE`**. Docs 00–02 never authorize silently ignoring a
  physical failure. A failure always has an explicit, auditable disposition.
- `DEGRADE`: keep operating with explicitly reduced evidence/function.
- `FALLBACK`: hand authority to the local deterministic path.
- `LOCKOUT`: actuation cannot be guaranteed safe; no new actuation.
- `NOT_CONTRACTED`: observation exists, control action is not yet approved.
  It must not be treated as a policy decision or as "no problem".

## 2. Mapping

| Failure | Title | Disposition | Reason code | Contract | Owner of the missing/remaining decision |
|---|---|---|---|---|---|
| F-PHY-01 | Sensor missing | DEGRADE | `SENSOR_DEGRADED` | PARTIAL | A quality/degraded protocol; escalation if no representative remains |
| F-PHY-02 | Sensor invalid/CRC/read error | DEGRADE | `SENSOR_INVALID` | PARTIAL | A quality; invalid value never substituted |
| F-PHY-03 | Position/configuration drift | NOT_CONTRACTED | none | NOT_CONTRACTED | A installation validity / W11 diagnosis |
| F-PHY-04 | Door signal unavailable | DEGRADE | `DOOR_DISTURBANCE` | PARTIAL | B features / C telemetry; not a P0 interlock |
| F-ELEC-01 | PZEM communication unavailable | DEGRADE | `PZEM_UNAVAILABLE` | PARTIAL | A hardware truth / W11 diagnosis |
| F-ELEC-02 | Wrong PZEM range/profile | DEGRADE | `PZEM_CONFIG_INVALID` | PARTIAL | A calibration/config |
| F-ELEC-03 | Unexpected OFF current | LOCKOUT | `CONTROL_ELECTRICAL_ANOMALY` | CONTRACTED | D lockout + A measurement; W11 D-W11-03 |
| F-ELEC-04 | ON current missing | NOT_CONTRACTED | `ELECTRICAL_RESPONSE_MISSING` | NOT_CONTRACTED | W11 D-W11-01/04 (force OFF/lockout timing) |
| F-ELEC-05 | Supply/terminal abnormality | LOCKOUT | none | PARTIAL | A characterization / W11; hardware safety stop |
| F-THERM-01 | Weak cooling | DEGRADE | `THERMAL_EFFECTIVENESS_DEGRADED` | PARTIAL | W11 D-W11-02/04; predictive blocked, local threshold continues |
| F-THERM-02 | Hot-side rejection limitation | NOT_CONTRACTED | none | NOT_CONTRACTED | A thermal characterization / W11; no frozen stop condition |
| F-THERM-03 | Excessive spatial gradient | NOT_CONTRACTED | none | NOT_CONTRACTED | A validity / B features / W11; no approved bound |
| F-NET-01 | Backend/broker unavailable | FALLBACK | `NETWORK_UNAVAILABLE` | CONTRACTED | D SAFE_LOCAL + A local control |
| F-AI-01 | Inference unavailable/invalid | FALLBACK | `AI_UNAVAILABLE` | CONTRACTED | D fallback + B model health |

## 3. How each disposition reaches the policy

| Disposition | Policy effect in W03 |
|---|---|
| DEGRADE | Keep local protection; set `degraded_sensing`/`predictive_blocked`; do not upgrade quality to VALID |
| FALLBACK | `SAFE_LOCAL` (network/AI) or Controller A (model unavailable) |
| LOCKOUT | `FAULT_LOCKOUT`, HOLD; no new actuation |
| NOT_CONTRACTED | Not implemented as an automatic action; the observation must be surfaced and escalated to the owner. The policy only acts if a separate, contracted input (`fault_active`, `hardware_safety_condition`, quality state) is asserted |

## 4. Important distinctions

- `F-ELEC-03` is the only fully contracted automatic **lockout** mapping in this
  slice. `F-ELEC-05` is lockout-class by Doc 02 §2.7, but its exact detector
  and characterized stop remain with A/W11.
- `F-ELEC-04` is *not* silently mapped to OFF. The observation is required, but
  the control reaction is explicitly deferred to W11; inventing it here would
  violate the ownership rule.
- `F-THERM-02`/`F-THERM-03` are not contracted. If the hardware/thermal state
  becomes unusable through a *contracted* quality signal, `F-PHY-*` handling and
  the policy's INVALID/UNKNOWN gate still apply.
- `F-NET-01` and `F-AI-01` fall back; they never create a new actuation request.
- One DS18B20 failure may be DEGRADE if a valid representative remains. If no
  representative remains, the quality becomes INVALID/UNKNOWN and the policy
  locks out; that escalation is documented in each `FailureRule.escalation`.

## 5. Verification

```text
tests/test_taxonomy.py::test_every_doc01_failure_id_is_mapped
tests/test_taxonomy.py::test_documented_disposition[<id>]
tests/test_taxonomy.py::test_no_ignore_disposition_exists
tests/test_taxonomy.py::test_uncontracted_rules_are_explicit
tests/test_taxonomy.py::test_lockout_rule_matches_policy_reason_code
tests/test_taxonomy.py::test_network_and_ai_failures_fall_back_to_local_policy
tests/test_taxonomy.py::test_every_rule_is_auditable[<id>]
```

Observed result of the final run: see `README.md` in this directory.

## 6. Limitations

- The mapping is a policy-level disposition, not a diagnosis algorithm. Actual
  detection of PZEM/thermal/fan anomalies is A/W11 work.
- No physical failure was injected. Taxonomy tests are pure unit tests of the
  mapping table.
- Contract status is a documentation judgment based on Docs 00–05D; it is not a
  formal sign-off from A/B/C.
- If a later document changes a failure's disposition, both the table and the
  tests must change together; otherwise the test suite will fail (by design).
