# Final frozen data package (W22)

`scripts/final_package.py` produces Member B's machine-readable **JSON input**
from an existing immutable freeze, not from changing live campaign tables. It
does not compute statistics, impute data, change thresholds, approve validity,
or claim another member's acceptance. Generated packages remain
`SOFTWARE_SIMULATION`; physical/official/G5 acceptance is `BLOCKED_EXTERNAL`.

## One-command build

Run from a clean backend Git commit with locked, provisioned dependencies. Set
`DATABASE_URL` to the owned direct-loopback DB containing the immutable
`campaign_freezes` record (or its separately restored copy).

```sh
cd backend
python scripts/final_package.py build --frozen ../evidence-out/freeze-v1 --freeze-id SOFTWARE-FREEZE --created-at 2026-11-08T00:00:00+00:00 --directory ../evidence-out/final-json-v1 --report ../evidence-out/final-json-report.json
```

The current clean **builder** commit is recorded separately from the original
frozen exporter/acquisition versions. Rebuilding from a later commit never
rewrites the old export, source manifest or frozen references. The builder reads
only the trusted freeze record from the DB; all dataset/audit/package work uses
the retained anchor-checked input bytes. No migration, online command dispatch,
new schema or re-close is performed.

## Optional, separately scoped incident inputs

Add `--incidents incident-inputs.json`, a strict JSON list, at most20 packages:

```json
[
  {
    "name": "resilience",
    "directory": "../evidence-out/incidents-v1",
    "manifest_sha256": "REPLACE_WITH_SEPARATELY_TRUSTED_64_HEX_SHA256"
  }
]
```

Use the trusted incident capture/handover anchor, not a hash computed from an
untrusted received package. Labels must be distinct portable filenames. Each
input keeps its own campaign/run/device scope, journal, audit, source bytes and
manifest. A resilience campaign or environment-wide auth probe is **not** added
to the A/B run list. Observer evidence remains
`RECORDED_NOT_INDEPENDENTLY_ACCEPTED`, with clock synchronization unverified.

## Package contract

| File | Meaning |
|---|---|
| `dataset.json` | Exact original `campaign-export.json` bytes, including its original manifest; no JSON reserialization or CSV coercion |
| `run-list.json` | Exact frozen registered runs, recorded statuses, versions and paired arms |
| `integrity-audit.json` | Pure frozen-input roster/pair/version, identity, raw/winner, source-report/current-close, event/window and child-reference checks; retained duplicate/gap diagnostics |
| `checksums.json` | Original export/source manifest/model/policy/config/file hashes, canonical exported-table hashes, separate whole-DB fingerprints and incident anchors |
| `claim-index.json` | Content-bound file hashes, JSON pointers and row hashes for recorded run/command/transport/ACK/policy/assessment/incident claims |
| `frozen/` | Original source manifest, archive/receipt and model/policy/config/export bytes |
| `incidents/<name>/` | Original optional incident audit/manifest/source bytes, separately scoped |
| `manifest.json` | SHA-256 of every package file plus source anchors and builder provenance |

The manifest cannot hash itself. Its SHA-256 is returned in the **separate**
build report and must be retained as the handover anchor. Exported-table hashes
use canonical JSON arrays; whole-DB fingerprints use the documented PostgreSQL
row-text representation and must not be conflated with those export hashes.

Member B should read `dataset.json` → `dataset.tables.telemetry` for normalized
winners and retain `telemetry_raw`, lifecycle, closures and traces as provenance.
Do not treat raw retransmissions as additional independent A/B samples. Sequence
gaps/exact retransmissions remain diagnostics; missing critical evidence or
conflicting identities refuse qualification rather than being repaired.

All table primary identities and normalized `(device_id, boot_id, seq)` are
checked. The audit revalidates wire text/checksums/JSON caches, raw-to-normalized
content, optional wire version contradictions, declared acquisition windows,
recorded lifecycle/VALID status and exact current `campaign-integrity-v3` closure
hashes. Historical closes remain retained. Wider/global context was qualified
at the original source freeze; this pure audit does not pretend to re-read the
entire historical DB or independently accept every physical attempt.

Command claims distinguish intent, PUBACK and accepted device ACK from physical
effect. Stored policy/assessment records are indexed, not reauthenticated or
converted into official Member D/A approval. Positive software storage fixtures
remain fixtures even when their protocol/assessment record has a positive stage.
Before a VALID ACK can support an acceptance claim, the strict ACK wire contract
and all stored identity/verdict/interpretability projections must agree. Late,
conflicting and invalid receipts remain evidence, not accepted protocol claims.

## Verification, failure and restore

```sh
# Verify needs no DATABASE_URL, broker or public Internet.
python scripts/final_package.py verify --directory ../evidence-out/final-json-v1 --manifest-sha256 TRUSTED_FINAL_SHA256 --report ../evidence-out/final-json-verify.json
```

Verification checks the trusted outer anchor, every retained file and nested
source anchor, then recomputes the audit/run list/checksum/claim-index bytes from
the retained source. Missing, corrupt, extra, aliased or internally inconsistent
input is refused. Names are portable; input/output directories must not overlap;
operational reports must be new files outside every immutable package.
Explicit operator roots may use `.`/`..` navigation, resolved under the root
overlap/alias policy. That is not permission for internal artifact traversal:
reserved names, trailing dots/spaces and dot-navigation artifact components
remain rejected before filesystem access.
Publication is exclusive and staged. Interrupted writes may retain diagnostic
`.evidence-staging-*` files, but do not publish a ready destination. Retry with a
new destination/report; never delete or overwrite historical evidence to retry.

Restore the **later post-freeze archive** to a separate empty, provisioned local
DB to recover the immutable freeze record. Do not migrate the restore target
first. See [campaign archive/freeze instructions](CAMPAIGNS.md). Build again with
the same source/incident bytes, builder commit and creation timestamp. The whole
final package must be byte-identical. The original pre-freeze source archive
cannot contain its own freeze record; retain both archive identities explicitly.

Primary S2 exports keep the existing paginated door timeline and its query bytes.
Legal non-S2 supporting runs use the existing generic backend-time timeline;
they are not forced into an S2 disturbance protocol.
