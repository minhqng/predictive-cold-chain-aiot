# W17 feature freshness and temporal integrity

- Layer: `coldguard-w17-shadow-parity-v1`
- Runtime freshness policy: `RUNTIME_FRESHNESS_POLICY_PENDING_C_D`
- Offline test parameters: `SYNTHETIC_ILLUSTRATIVE_TEST_PARAMETER`
- Maximum anchor input age: 2 s
- Maximum electrical (PZEM) channel age: 5 s
- Maximum door channel age: 5 s
- Channel timestamp basis: frame event time when no channel timestamp is attested (declared synthetic assumption, not physical attestation)

## Clock domains

| Domain | W17 representation | Declared status |
|---|---|---|
| Physical event time | fixture event offset `t` | synthetic exact; physical UTC sync NOT verified |
| Sample receipt/arrival | `event + deterministic transport delay`; one deliberate late delivery is injected | simulated test parameter |
| Prediction anchor | observed sample event time | synthetic |
| Processing time | `anchor + deterministic processing delay`; all anchor/channel ages are measured against this instant | simulated test parameter |

Host receipt time is never equated with physical event time, and no local script runtime is reported as transport or physical latency.

## Disposition rules

| Disposition | Rule |
|---|---|
| `READY_FOR_SOFTWARE_REPLAY` | anchor frame arrived by prediction time; identity/schema/order consistent; anchor, electrical and door ages measured at prediction time are within the test parameters; thermal/electrical/door quality trusted |
| `REFUSED_STALE_INPUT` | missing anchor observation, anchor input age or electrical/door channel age measured at prediction time beyond the declared test parameter |
| `REFUSED_UNTRUSTED_INPUT` | thermal or electrical quality not VALID; overall INVALID; door not OPEN/CLOSED, door quality not VALID or polarity unattested |
| `REFUSED_TEMPORAL_ORDER` | anchor frame not available at emission; sequence regression with a newer event time; contradictory temporal state |
| `REFUSED_IDENTITY_MISMATCH` | foreign boot/device, contradictory duplicate identity, ambiguous anchor time |
| `REFUSED_FEATURE_SCHEMA_MISMATCH` | feature version/registry hash or ordered schema identity mismatch |

A refused anchor never receives a score and never receives a warning. Sanitized channels become missing values with explicit reasons; stale electrical values are never replaced by zero and old door state never becomes current trusted state.

## Executable probes

| Probe | Outcome | Detail |
|---|---|---|
| `fresh_anchor` | `READY` | `{"disposition": "READY_FOR_SOFTWARE_REPLAY", "reasons": []}` |
| `fresh_anchor_missingness` | `OBSERVED` | `{"door_open_reason": "PRESENT", "rolling_mean_reason": "MISSING_INSUFFICIENT_HISTORY"}` |
| `late_packet_excluded` | `PASS` | `{"earlier_prediction_unchanged": true, "included_only_at_later_anchor": true, "late_identity": "cg-synthetic-001:CG-W11-S2-003-BOOT-1:30", "late_observations": ["cg-synthetic-001:CG-W11-S2-003-BOOT-1:30"]}` |
| `future_event_excluded` | `PASS` | `{"future_identity": "cg-synthetic-001:CG-W11-S2-003-BOOT-1:999"}` |
| `stale_pzem` | `REFUSED_STALE` | `{"cooling_power_is_zero": false, "cooling_power_reason": "MISSING_ELECTRICAL_UNQUALIFIED", "disposition": "REFUSED_STALE_INPUT"}` |
| `degraded_channels` | `REFUSED_UNTRUSTED` | `{"disposition": "REFUSED_UNTRUSTED_INPUT", "reasons": ["THERMAL_QUALITY_DEGRADED", "ELECTRICAL_QUALITY_INVALID", "OVERALL_QUALITY_INVALID"]}` |
| `counter_reset` | `OBSERVED` | `{"disposition": "READY_FOR_SOFTWARE_REPLAY", "energy_counter_reason": "MISSING_COUNTER_RESET"}` |
| `door_polarity_unattested` | `REFUSED_UNTRUSTED` | `{"disposition": "REFUSED_UNTRUSTED_INPUT", "reasons": ["DOOR_POLARITY_UNATTESTED"]}` |
| `unknown_door` | `REFUSED_UNTRUSTED` | `{"disposition": "REFUSED_UNTRUSTED_INPUT", "door_open_reason": "MISSING_UNKNOWN_DOOR", "duration_reason": "MISSING_UNKNOWN_DOOR", "reasons": ["DOOR_CONTEXT_UNKNOWN"], "time_since_open_reason": "PRESENT"}` |

## Coverage of the adversarial matrix

- Future event-time observations and late packets cannot influence an earlier anchor; a late frame is recorded separately and only becomes available at a later prediction whose processing time follows its arrival.
- Duplicate identical deliveries collapse; contradictory payloads for one identity fail closed. Out-of-order event times are accepted deterministically and sorted; a lower sequence with a newer event time is rejected.
- Boot transitions partition state; no rolling, door or actuation state crosses a boot boundary. A reconnect gap beyond the anchor age is refused as stale instead of reviving old state.
- Stale PZEM samples are sanitized to missing electrical values (`MISSING_ELECTRICAL_UNQUALIFIED`), never zero. Counter resets are reported as `MISSING_COUNTER_RESET` and never create negative consumption.
- UNKNOWN door state and unattested polarity keep door features missing (`MISSING_UNKNOWN_DOOR`, `MISSING_POLARITY_UNATTESTED`); UNKNOWN never becomes CLOSED and no duration crosses the interruption.
- T2 is treated as a diagnostic hot-side probe and never enters the chamber-air aggregate.

The delivered parity run injected one deterministic late delivery (`cg-synthetic-001:CG-W11-S2-003-BOOT-1:30` in `CG-W11-S2-003`, scheduled arrival 60 s) and recorded 1 late observation(s); it refused 1 anchor(s). The delivered fixtures contain no stale channel, so stale-PZEM and stale-door behavior is demonstrated by the probes above and by `tests/test_w17_freshness.py`, not by the clean parity run.

## Limitations

- Stale-channel dispositions are exercised by probes and adversarial tests; the clean parity fixture has no stale channel.
- Channel timestamps absent from a raw frame default to the frame event time; this is a synthetic assumption, not a physical attestation.

- Policy thresholds are illustrative test parameters, not the frozen runtime freshness policy owned by C/D.
- Physical clock synchronization, transport latency and physical response are not measured in W17.
