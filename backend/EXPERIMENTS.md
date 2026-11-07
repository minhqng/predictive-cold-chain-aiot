# Experiment runs and evidence export

Apply Alembic revision 0009 before using the experiment endpoints. The API runs
within the backend's trusted local deployment boundary.

| Route | Purpose |
|---|---|
| `POST /api/runs` | Register a unique run with a device, scenario, controller, optional pair, version references, and notes. |
| `POST /api/runs/{run_id}/transitions` | Record a lifecycle change with `status` and an optional `reason`. A final verdict requires a reason. |
| `GET /api/runs/{run_id}` | Read metadata and ordered lifecycle history. |
| `GET /api/runs/{run_id}/export` | Read one JSON v0 bundle with a manifest, run history, and normalized telemetry with raw provenance. |
| `GET /api/runs/{run_id}/timeline` | Read command, ACK, device event/state receipt, and telemetry chronology. |

The lifecycle follows Doc 03 §6. Move from `PLANNED` through `ARMED`,
`RUNNING`, `COMPLETED_RAW`, and `VALIDITY_REVIEW` before recording `VALID`
or `INVALID`. A run may be aborted before collection ends or during review.
Lifecycle calls record backend timestamps and serialize final decisions.
Use Doc 03 §7 predeclared validity rules and record the review reason.

Association uses the registered run's exact `run_id` and `device_id`.
Overlapping timestamps alone confer no membership. A missing, unknown, or
wrong-device run claim stays available in the ingest evidence and outside the
registered run view. Replayed identities follow the existing normalized winner
policy. Unknown claims remain unassociated until an exact run and device pair
is registered. The JSON v0 export reflects the current evidence snapshot.

The manifest hashes the UTF-8 serialization of the `dataset` object, with keys
sorted and compact JSON separators. Telemetry order is backend receipt time
followed by normalized row ID. Clockless event time stays null. Timing retains
the W05 clock-trust policy. Each sample carries its raw ID and SHA-256.
The timeline uses backend chronology with kind and stable row identity as
tie-breakers. Door state on a telemetry sample is a snapshot. A standalone
door event appears only when an explicit event receipt exists, and the
receipt carries its ingest classification.

Downgrade from revision 0009 requires empty experiment tables. Preserve the
database and its history when taking a populated environment out of service.
