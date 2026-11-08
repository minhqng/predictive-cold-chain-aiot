# Resilience and incident evidence (W21)

The sealed W20 A/B package remains unchanged. Run resilience/security exercises
on separate, owned software fixtures. Do not migrate an active final campaign,
relax ACLs, replay unresolved commands automatically, or claim physical SAFE_LOCAL
from a broker PUBACK, device ACK, process restart or software test.

## What is durable

- Raw deliveries and normalized winners preserve duplicate/conflicting/reordered
  input without regressing the current Twin or promoting an unverified boot.
- Commands, publish attempts, transitions and ACK receipts retain uncertainty,
  expiry and rejected protocol evidence. A pending crash window becomes UNKNOWN;
  expiry/reconciliation does not publish a replacement command.
- Broker-denied traffic need not reach backend ingestion. Retain its actual
  CONNACK/PUBACK or broker-log artifact; never invent a corresponding raw row.
- Runtime counters are process-scoped. Retain observer snapshots and finalized
  backend/broker logs separately when reconstructing an outage across restarts.

## Read-only incident package

`scripts/audit_incidents.py` binds the existing campaign roster, current integrity
issues, raw receipts, timelines, command history and all-table DB fingerprints to
an explicit observer journal and SHA-256-verified source artifacts. It creates no
new DB schema, online mutation endpoint or command publisher.

The journal follows `IncidentJournal` / `IncidentObservation` in
`src/coldguard_backend/incident_audit.py`. It contains a declared data class,
campaign ID, distinct event IDs, genuine aware observation timestamps, source
name/kind/checksum and an explicit summary. Optional run/device/raw/command
references must exist in their exact campaign scope. Leave scope absent for
environment-wide observations; explain separately scoped probes in their source
receipt rather than fabricating an A/B association. Observer clock synchronization
is not assumed. Source files must be direct regular files, at most100 distinct,
16MiB each and64MiB combined. Keep credentials out of shareable source artifacts.

```sh
# DATABASE_URL is the owned direct-loopback source DB; use a clean backend commit.
python scripts/audit_incidents.py capture --journal observer-journal.json --artifact-root observer-sources --created-at 2026-11-08T00:00:00+00:00 --directory ../evidence-out/incidents-v1 --report incident-report.json
# Use the trusted manifest_sha256 from the separate capture report, not a value
# computed from an untrusted package received from someone else.
python scripts/audit_incidents.py verify --directory ../evidence-out/incidents-v1 --manifest-sha256 TRUSTED_SHA256 --report incident-verify.json
```

Each package contains `incident-audit.json`, retained source bytes and a checksum
manifest. Publication is staged, exclusive and non-overwriting; a failed write
may leave a diagnostic `.evidence-staging-*` directory but no ready destination.
Reports must resolve outside the immutable package. Verification retains each
anchor-checked file once and uses those same bytes for internal source checks.
Artifact names and every nested package component must be portable: trailing
dots/spaces, Windows device names and invalid characters are rejected, never
trimmed or renamed. The same pure check applies to direct journal sources and
shared freeze artifact names before filesystem resolution or publication; no
serial/printer/device path is opened by these validations.

`RECORDED_NOT_INDEPENDENTLY_ACCEPTED` is intentional: the package proves retained
bytes and DB/artifact associations, not that an observer's prose is official
truth. Generated evidence is `SOFTWARE_SIMULATION`; physical origin, official
A/B/D approvals, G5 and joint physical acceptance stay `BLOCKED_EXTERNAL`.

## Rebuild after restore

Archive the DB using `scripts/backup_campaign.py` and retain the incident package
and its separate trusted anchor. Restore into a **different empty** provisioned
local DB, without migrating that target first. Re-run capture with the same
journal, source bytes, original `created_at` and the exact exporter commit. The
audit and manifest bytes must match. A later live DB mutation changes snapshot
fingerprints; use the archived snapshot, not silently repaired data.

Relevant real-provider regressions are `test_offline_replay.py`,
`test_platform_reconnect.py`, `test_outage_recovery.py`, `test_broker_security.py`,
`test_mqtt_tls.py`, `test_command_authorization.py`, `test_verify_restore.py` and
`test_incident_audit.py`. Missing provider prerequisites are SKIP/NOT RUN, never
PASS. TLS trust/hostname failures are distinct from broker auth/ACL refusal.
