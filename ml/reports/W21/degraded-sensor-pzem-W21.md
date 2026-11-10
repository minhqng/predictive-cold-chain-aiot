# W21 Degraded Sensor and PZEM Assessment (B-W21-03)

## Current sensor role map

| Slot | Physical position | ROM | Chamber-air aggregate |
|---|---|---|---|
| t1 | CHAMBER_CENTER | `287088CA00000051` | True |
| t2 | TEC_HOT_SIDE | `28AEBF2200000006` | False |
| t3 | CHAMBER_BOTTOM | `28CBE9CA00000072` | True |
| t4 | CHAMBER_NEAR_DOOR | `283BE5C9000000A9` | True |

`T2` is `TEC_HOT_SIDE`. It is never substituted for a missing chamber-air role.

Provenance: this is the as-built A W07 role record consumed by `ml/feature-registry-v1.yaml`. It is a role record, not an independently measured calibration; physical position verification remains A-owned. An earlier A W02 assignment listed T1/T2/T3 positions differently and is superseded by the as-built record. The W21 refusal uses only the current registry: a missing chamber-air role is not replaced by the hot-side role.

## Recorded observations

| Item | A-W21-02 | A-W21-03 |
|---|---|---|
| Injected condition | DS18B20 T1 software injection | PZEM transport software disable |
| Frames | 25 | 25 |
| Explicit invalid role/channel | T1 | electrical quality |
| Overall quality | UNKNOWN 25 | INVALID 24, UNKNOWN 1 |
| Thermal / electrical | DEGRADED 25 | electrical INVALID 24, VALID 1; thermal not recorded |
| Current | UNKNOWN | MISSING 24 |
| Recovery | 25/25 valid frames | 24/25 valid frames |
| Output state | OFF, stage compiled out | OFF, stage compiled out |
| ROM map | unchanged | unchanged |

## Missingness and quality rules

| Prohibited conversion | Enforced behaviour |
|---|---|
| missing chamber-air sensor replaced by T2 | refused; T2 is hot-side |
| hidden ROM remap | refused; role map must remain stable |
| UNKNOWN door converted to CLOSED | normalized to UNKNOWN |
| invalid temperature converted to a number | normalized to null |
| stale PZEM carried forward | measurement missing |
| missing current converted to 0 A | measurement missing |
| missing power integrated as zero energy | energy missing |
| energy counter reset hidden | reset detected; no negative delta |
| recovery inferred without fresh samples | refused |
| degraded-model inference without validation | refused |
| W21 fault evidence used as training data | refused |

## Model and feature consequence

The W15 model is a synthetic, nondeployable candidate; no degraded-feature validation exists and the final policy version is NOT_FROZEN. Under a missing required chamber-air channel or an invalid electrical channel, predictive inference must be refused or disabled and Controller A/local semantics apply. W21 does not claim positive model robustness under real sensor loss.

## Source binding

| Binding | Value |
|---|---|
| Firmware image SHA-256 | `e1073935168c01be029c23a87f6f012d852016deac0afb672437f234a269206b` |
| Device / boot | `coldguard-001` / `4cf9be5f` |
| Hardware config | `CG-HW-001` |
| Firmware version | `cg-w06-0.1.0` |
| Raw log SHA-256 | `faf008eb6c7e250c8b8f98385e6eb3817b1084771a56d800a3735c576c7106fa` |
| Test mechanism | on-device software injection |
| Output-stage limitation | compiled out; fuse OUT; TEC OFF |
| Physical disconnection | NONE |

## Descriptive counts

- Fault-window frames: 50 (25 + 25).
- Recovery frames: 50 (25 + 25).
- Total recorded frames: 100.
- Independent on-device sessions: 1.
- Explicit degraded/unknown states: 50 frames across two test IDs.
- Documented fresh recoveries: 2 (25/25 and 24/25 valid frames).
- These are descriptive source-bound counts, not physical reliability rates.

```text
diagnostic_accuracy = NOT_ESTIMABLE
fault_recall = NOT_ESTIMABLE
real_model_robustness = NOT_ESTABLISHED
physical_cooling_response = NOT_ESTABLISHED
```
