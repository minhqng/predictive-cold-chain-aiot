# D-W11-05 — diagnosis event handoff to Member C

**Contract proposed by D; backend persistence remains OPEN.** Member C owns
the storage schema and ingestion implementation. A persistable diagnosis event
must keep these fields together, without converting an ACK into physical proof:

| Field | Purpose |
|---|---|
| `event_id`, `schema_version` | Stable event identity and schema evolution |
| `device_id`, `boot_id`, `seq_start`, `seq_end`, `run_id` | Join to the exact source telemetry window; never join by wall time alone |
| `command_id`, `ack_status`, `applied_cooling` | Keep intent, protocol handling and applied feedback separate |
| `window_start_uptime_s`, `window_end_uptime_s`, `clock_quality` | Bound the electrical/thermal observation window on a declared clock |
| `cooling_health_state`, `reason_code`, `verification_state` | Observable classification and the specific verdict/reason |
| `evidence_quality`, `envelope_id`, `policy_version` | Explain confidence and frozen policy provenance |
| `source_capture_sha256`, `is_physical_measurement` | Pin the raw source and prevent a fixture from being presented as a device run |

Minimum invariants for C's ingestion test: the sequence/time window is ordered;
duplicate `event_id` is idempotent; `UNKNOWN` remains visible; a health claim
requires qualified electrical and thermal evidence plus applied-state feedback;
the raw source and policy/envelope versions remain queryable. A received or
accepted ACK alone never produces `HEALTHY_RESPONSE`.

The current pure verifier can supply state/reason/window information but does
not publish an event or write to C's database. A/C must agree on the wire
schema and validate one end-to-end run before D-W11-05 can be marked complete.

Sources: Doc 02 §§32–36, Doc 03 §5, Doc 05D D-W11-05.
