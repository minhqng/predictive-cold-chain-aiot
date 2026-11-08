# Campaign integrity (Member C)

Campaigns freeze an exact paired roster **before any run is armed**. A `campaign_id`
owns each run once, with a `pair_id`, arm A (`REACTIVE`) or B (`PREDICTIVE`), all
version references, a protocol/Doc 03 validity reference, required event types and
predeclared critical acquisition windows. Paired hardware, pin map, firmware,
schema and calibration references must agree. Model/policy references remain
arm-specific and cannot change after registration.

`SOFTWARE_SIMULATION` identifies generated fixtures. It is not a final physical
campaign, official A/B/D approval, statistical result, or G5 acceptance. Physical
acceptance remains `BLOCKED_EXTERNAL`. This software never interpolates, backfills,
rewrites a normalized winner or automatically changes run validity.

## Schema and mutation boundary

Apply Alembic revision `0013` **before** a campaign is registered. It adds
`campaigns`, `campaign_runs` and append-only `campaign_run_closures`. Namespaces,
associations and close reports reject updates/deletes. Registered campaign run
identity/version fields also reject updates. Existing lifecycle transitions are
unchanged; `COMPLETED_RAW → VALIDITY_REVIEW → VALID/INVALID` still needs an explicit
recorded validity reason. Counts alone do not approve a run.

The new HTTP views are read-only and remain restricted to the existing trusted
loopback deployment boundary. Mutations use a local operator CLI with an explicit
dedicated loopback `DATABASE_URL`:

```sh
cd backend
python scripts/campaign.py --output registration.json register --plan campaign-plan.json
python scripts/campaign.py --output integrity.json integrity --campaign SOFTWARE-CAMPAIGN
python scripts/campaign.py --output run-close.json close --campaign SOFTWARE-CAMPAIGN --run SOFTWARE-A --reason "SOFTWARE_SIMULATION QA close"
```

`campaign-plan.json` follows the validated `CampaignCreate` contract in
`src/coldguard_backend/campaign_store.py`. The software-only example generator is
`tests/campaign_testkit.py`; its controlled clock fixtures are for tests only.
Required run versions are `hardware_config_id`, `pin_map_version`,
`firmware_version`, `backend_version`, `schema_version`, `calibration_id`,
`feature_version`, `model_version`, and `policy_version`. Use an explicit
`NOT_APPLICABLE` reference where a model/policy genuinely does not apply; do not
invent an official reference. Critical windows specify offsets from run start,
their maximum permitted gap, and a unique `window_id`. Freeze actual tolerances
from the Doc 03 protocol, not from results observed after the run.

CLI output files are exclusive-create. If a report write fails after registration
or closure commits, retry with a new output path: identical requests are
idempotent, and a late receipt creates a new content-addressed assessment rather
than overwriting the earlier close.

## Read-only API

- `GET /api/campaigns/{campaign_id}`: frozen namespace and its SHA-256.
- `GET /api/campaigns/{campaign_id}/integrity`: live DB health, acquisition age,
  ingestion connectivity/subscription snapshot, raw schema/message errors,
  per-run counts, duplicates/conflicts, gaps, event completeness, critical-window
  issues and backup readiness.
- `GET /api/campaigns/{campaign_id}/closures?limit=100&offset=0`: bounded immutable
  close records (maximum page 500), each with a reason and report SHA-256.

Acquisition age is separate from receipt time. Delayed duplicate ingestion cannot
renew it. Unverified/clockless acquisition times are never replaced by receipt
timestamps. `raw_count` includes conflicting receipts that share a normalized
logical identity and malformed unassigned telemetry on the run's device topic
during its receipt interval. These are diagnostic associations, not valid samples.
Exact duplicate deliveries are counted without duplicating normalized authority;
conflicting payloads and wrong run/pair associations remain visible issues.

`SOFTWARE_INTEGRITY_CLEAR` is an assessment, **not** `VALID`. Missing critical
windows and events produce `ISSUES_REQUIRING_VALIDITY_REVIEW`. Invalid and aborted
attempts remain in the namespace and evidence history; they must never be silently
removed to improve the campaign result.

## Wave-block archive and restore

The local `pg_dump`/`pg_restore` binaries must match the database major version.
Set `COLDGUARD_PG_DUMP` / `COLDGUARD_PG_RESTORE` if they are not on PATH. Current
closures and clear integrity are required for a ready campaign archive.

```sh
python scripts/backup_campaign.py backup --directory ../evidence-out/wave1 --campaign SOFTWARE-CAMPAIGN --report ../evidence-out/wave1-report.json
# COLDGUARD_BACKUP_RESTORE_URL points to a DIFFERENT empty local database.
python scripts/backup_campaign.py restore --directory ../evidence-out/wave1 --report ../evidence-out/restore-report.json
```

Backups use a PostgreSQL exported snapshot: table fingerprints and `pg_dump` see
the **same transaction snapshot**, not independently changing database reads.
`database.dump` and `receipt.json` publish together in a new directory; existing
destinations are never intentionally overwritten. An interrupted generation can
leave a `.backup-staging-*` directory for diagnosis, but no published ready archive.
The receipt says `restore_verified: false` until an actual separate restore report
proves the comparison. Source configuration and archive hashes are not hardware
signoff.

Restore targets must have no public application tables. Provision TimescaleDB
using `infra/postgres/init/001_extensions.sql`, then restore (do **not** migrate
the restore target first). The restore command uses Timescale pre/post hooks,
fails on any PostgreSQL error, and compares every reviewed public evidence table
for the installed revision. No clean/drop operation is implicit. The corrected
`scripts/verify_restore.py` also works for a separately prepared pair of local
databases and refuses missing/extra tables or unsupported revisions.

## Deterministic evidence freeze

Install revision `0014` before registering the final campaign. No migration is
performed by a freeze operation. All local proofs use new disposable databases;
they do not change an actual locked physical campaign. During a real final
campaign, an emergency correctness change requires stopping/restarting and
documenting comparability under Doc 03.

`FreezeDraft` names an exact freeze ID, campaign ID, aware creation timestamp,
clean backend Git SHA and SHA-256-tagged artifact references. Required roles are
model metadata, policy metadata, broker config and backend config, plus a model
or policy reference for every applicable declared version. Metadata must name
the frozen version collection and the reference content hash. Keep credential
values out of shareable config artifacts; retain actual secrets separately in
restricted operator storage. Generated reference blobs are explicitly
`SOFTWARE_SIMULATION`, not official artifacts or executable controller code.

```sh
# Set DATABASE_URL to the source local DB; finish validity review and close both arms.
python scripts/freeze_campaign.py freeze --spec freeze-spec.json --artifact-root frozen-inputs --backup ../evidence-out/wave2 --directory ../evidence-out/freeze-v1 --report freeze-report.json
python scripts/freeze_campaign.py verify --freeze-id SOFTWARE-FREEZE --directory ../evidence-out/freeze-v1 --report freeze-verify.json
# Set COLDGUARD_BACKUP_RESTORE_URL to a different empty, provisioned local DB.
python scripts/freeze_campaign.py restore --freeze-id SOFTWARE-FREEZE --directory ../evidence-out/freeze-v1 --report freeze-restore.json
```

The exporter refuses a dirty backend, absent/conflicting versions, unavailable
required measurements, missing/currently-invalid runs, stale close reports,
or a backup that differs from the current evidence snapshot. Commands must
reference their exact run/controller/policy and any referenced prediction must
exist with scoped inputs. A physically labelled export cannot relabel synthetic
measurements; predictive physical records also need their existing signed policy
and assessment evidence. This still does **not** confer G5 or official acceptance.

`campaign-export.json` contains the full paired list, raw/normalized rows,
experiment transitions, events/timelines, predictions/inputs, commands/attempts/
ACKs/transitions, shadow decisions, existing policy approvals/physical assessments
and all immutable run-close versions. The dataset ID is derived from canonical
dataset bytes, with a distinct `coldguard-software_simulation-...` namespace.
Repeated export with the same snapshot/timestamp/provenance is byte-identical.

The freeze directory contains the export, source DB archive/receipt, model/policy
metadata/references, config references and a file checksum manifest. Its manifest
SHA-256 and exact export bytes are anchored in an append-only `campaign_freezes`
record. Verify against that DB record (or its trusted handover SHA), not only
against checksums supplied by the package itself. Missing, changed or unexpected
files are refused, including a silently changed manifest.

The source archive precedes its own freeze record: self-referential freeze rows
are excluded only from that input comparison. After freezing, take another
final-ish/final backup to include `campaign_freezes` along with every other table.
The original frozen source can be restored without its record and still
reconstruct the exact paired export; the record is backed up separately by the
later final backup and its manifest anchor is handed over explicitly.

Partial file writes roll back the DB transaction. A commit failure moves the
published directory back to its staging name; an unregistered/staged package is
never trusted. Staging files are preserved for diagnosis. Reusing a freeze ID
requires identical immutable inputs and intact original artifacts. Changes
require a new explicit version/ID, never an overwritten freeze.
