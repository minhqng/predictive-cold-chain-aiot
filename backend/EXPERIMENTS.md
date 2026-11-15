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
| `GET /api/runs/{run_id}/s2-timeline` | Read a bounded door-disturbance timeline page or download that page as JSON. |

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

## S2 timeline feed

Use the `s2-timeline` endpoint for runs with scenario ID `S2`,
`DOOR_DISTURBANCE`, or `S2_DOOR_DISTURBANCE`. Pass `limit` (1–500) and
the preceding page's opaque `next_cursor`. Set `download=true` to export the
same JSON page. A page exposes stable source row IDs for chart markers and
sorts by backend time, source kind, and source ID. A client can poll from the
last cursor to fetch newer entries and periodically refresh the displayed
window to catch late commits. The feed is a database view of evidence, with
separate pages reflecting separate snapshots.

Door events come from observed device receipts on the exact topic. The feed
keeps the first receipt for each distinct JSON payload under a source event
ID within the device and run. Later conflicting variants carry
`event_id_conflict: true` and retain their boot provenance for review.
Telemetry snapshots provide thermal, electrical, and control context. The
backend projects command creation from its transition history and command
acceptance only when a matching accepted ACK is present. Verification event
types are reserved for trusted evidence. Raw device claims of verification
remain available as receipts through the ordinary run evidence API.

Reported event time remains separate from backend receipt time. Missing or
invalid source times are null. A command link resolves only within the same
run and device. The feed carries reported correlation and prediction IDs
where available, alongside backend command prediction references.

## Prediction evidence

Revision 0010 adds append-only prediction records and ordered references to
normalized telemetry. The trusted backend writer records model and feature
versions and SHA-256 values, the input receipt-time window, horizon and
risk score. Input IDs must belong to the exact device and run and fall within
the declared window. Freshness ends at the newest linked input receipt plus
the configured input age limit. The same prediction ID and payload can be
retried without changing provenance or refreshing it.

| Route | Purpose |
|---|---|
| `GET /api/devices/{device_id}/predictions/current` | Newest prediction scoped to the device and optional `run_id`. Returns `UNAVAILABLE` without evidence and suppresses stale risk. |
| `GET /api/devices/{device_id}/predictions` | Paginated historical evidence with optional `run_id`, `limit` of 1–100, and bounded `offset`. |
| `GET /api/devices/{device_id}/predictions/{prediction_id}` | Immutable evidence and ordered telemetry IDs for a single prediction. |

The Twin stores prediction metadata in `derived_state.prediction`. Reading it
computes age and suppresses stale risk while retaining historical evidence.
Measured reported state and desired intent keep their independent authorities.
These read APIs expose evidence and freshness. Model trust and permission to
act require separate policy checks. A populated prediction schema refuses a
downgrade that would delete its provenance.

## Shadow policy trace

Revision 0011 stores hypothetical decisions separately from commands.
The prediction and its shadow decision commit together. A rejected decision
identity cannot leave a new prediction or derived Twin update behind.
The trusted runner reads a bounded receipt-time window from the registered
device's active boot. It excludes replay and future inputs, checks the
feature adapter against the approved frozen model, and records ordered
feature values and input IDs for offline comparison. The runner adapts
Member D's pure policy decision. Stale inference records a skip without
calling the policy. This path has no publisher or command dispatch route.

`GET /api/runs/{run_id}/shadow-trace` returns prediction evidence, input IDs,
the hypothetical decision and its timing, and independent Controller A
command records for the same device and run. Limits are 1–50 per section.
The query preserves missing decisions and explicitly reports unavailable
physical response evidence. Member B can rerun the model on the exported
ordered feature vector. Open `/audit/runs/{run_id}/shadow` in a browser for
the recorded prediction times, policy evaluation time and duration. The view
is read-only and accepts the same bounded `limit` and `offset` parameters.
Official online model/features and actual physical
run evidence remain separate acceptance items.
