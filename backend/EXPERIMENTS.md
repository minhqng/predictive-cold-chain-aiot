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
| `GET /api/runs/{run_id}/integrity` | Check raw duplicates, normalized sequence ranges, time anomalies, quality, and declared versions. |
| `GET /api/runs/{run_id}/telemetry`, `/events`, `/commands` | Page through evidence for the exact run and device. |

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

## S1 dataset handoff

From `backend/`, point `DATABASE_URL` at the approved source database. The
exporter requires valid, nonempty S1 runs and attributes the export to the
current backend Git commit. It accepts the scenario IDs `S1`,
`NORMAL_BASELINE`, and `S1_NORMAL_BASELINE`.

```sh
uv run --locked python scripts/export_s1.py \
  --run-id CG-S1-A-001 --created-at 2026-11-07T12:00:00Z --output s1.json
```

Repeat `--run-id` to export multiple runs. The manifest contains its schema and
query version, the sorted run IDs, the UTC creation instant, the backend SHA,
and a content-derived dataset ID. The SHA-256 covers the canonical compact JSON
`dataset` object. Reuse the creation instant and source snapshot to reproduce
the full artifact. The exporter refuses to overwrite an existing file.

Integrity entries report sequence gaps per boot, repeated raw receipts for the
winning logical identity, unverified event-time anomalies, receipt-time
anomalies, clockless samples, quality counts, and version mismatches. Record
`firmware_version`, `hardware_config_id`, `calibration_id`, and
`schema_version` in the run versions when available. A reviewer's lifecycle
verdict and the integrity report remain distinct. Flagged synthetic sample
counts and per-sample provenance let Member B identify software fixtures.

Each evidence page accepts a `limit` of 1–500 and an `offset` of 0–100000.
Receipts sort by backend time and ID. Commands sort by creation time and
command ID. Follow `next_offset` while the run's evidence snapshot remains
stable. New arrivals may change the contents of later pages.
