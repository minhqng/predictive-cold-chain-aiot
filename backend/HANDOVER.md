# Digital handover contract

Deliver the reproducible software spine and separately anchored evidence, not a
claim of hardware safety, cooling, statistics, official Member A/B/D approval or
G5/G6 acceptance. Generated preservation data is **SOFTWARE_SIMULATION**. Physical
and independent human gates stay **BLOCKED_EXTERNAL** until their actual owners
execute and accept them.

## Entry points and ownership

| Delivered surface | Executable/document owner |
|---|---|
| Local Compose topology and runtime image | [`infra/compose.yaml`](../infra/compose.yaml), [`Dockerfile`](Dockerfile) |
| Broker listeners, identities and ACL | [`mosquitto.conf`](../infra/mosquitto/mosquitto.conf), [`acl.conf`](../infra/mosquitto/acl.conf) |
| TLS trust/hostname/auth and separate command authority | [security/inference contract](SECURITY_INFERENCE.md), [`mosquitto-tls.conf`](../infra/mosquitto/mosquitto-tls.conf) |
| Migration chain, schema inventory and extension ownership | [`migrations`](src/coldguard_backend/migrations), [`alembic.ini`](alembic.ini), [`evidence_tables.py`](src/coldguard_backend/evidence_tables.py), [`001_extensions.sql`](../infra/postgres/init/001_extensions.sql) |
| Wire schemas and strict admission | [`contracts.py`](src/coldguard_backend/contracts.py), [`validation.py`](src/coldguard_backend/validation.py) |
| API and generated local OpenAPI | [`main.py`](src/coldguard_backend/main.py), local `/openapi.json`; [run API](EXPERIMENTS.md) |
| Reported/desired/derived Twin and boot/replay authority | [`twin_store.py`](src/coldguard_backend/twin_store.py), [recovery contract](PLATFORM_RECOVERY.md) |
| Commands, ACKs, predictions and physical boundary | [command path](COMMAND_PATH.md), [security/inference](SECURITY_INFERENCE.md) |
| Consistent backup, clean restore and immutable freeze | [campaign operations](CAMPAIGNS.md) |
| Runtime observability and reconstructed incidents | [platform observability](PLATFORM_RECOVERY.md#runtime-observability), [incident evidence](RESILIENCE.md) |
| Dataset, checksums and claim-to-evidence index | [frozen JSON contract](FINAL_DATA_PACKAGE.md) |
| Owned start/stop/health/logs/auth/migrate/restore/reconnect | [local runbook](RUNBOOK.md), [`check_stack.py`](scripts/check_stack.py) |
| Populated software preservation gate | [`tests/test_handover.py`](tests/test_handover.py), [`handover_testkit.py`](tests/handover_testkit.py) |

Canonical project authority remains Doc03/Doc05C and their parent documents.
These pointers do not replace another member's data, policy or commissioning
authority. Follow the current runbook, not historical startup examples.

## What travels with the handover

- Exact reviewed local branch/commit and locked dependencies; no silent model,
  policy, schema or threshold replacement.
- **Original pre-freeze** source package and independently trusted manifest
  anchor, plus the distinct **later post-freeze** archive containing the immutable
  freeze record. Retain both identities and all failed/invalid/aborted attempts.
- Final JSON package, separately trusted manifest SHA, dataset/freeze IDs,
  original exporter and current builder provenance. Keep optional incident/probe
  campaigns separate from A/B samples.
- Actual migration-from-zero and applicable full-regression reports, populated
  clean-restore fingerprints, and byte-identical export/package comparisons.
  Empty advanced tables cannot establish preservation of their histories.
- Private provisioning and credential retrieval instructions kept separately
  restricted. Never put real secrets in Git, source dumps or shareable reports.

An anchor carried only inside an untrusted received package is not independently
trusted. Preserve the out-of-band ownership/anchor route with the handover owner.
Stateful test results and private bindings belong in the separate handover
evidence, not this evergreen contract.

## Recipient's software verification route

1. Confirm the supplied Git revision and trusted anchors with the owner. Work
   from a fresh owned clone and pre-provisioned runtime/images or locked offline
   dependencies. Do not merge or write `main` as part of the drill.
2. Follow the [runbook](RUNBOOK.md). Explicitly match `DATABASE_URL` and all
   `POSTGRES_*` worker bindings to the selected owned provider before network
   access. Liveness is not schema, subscription, recovery or physical acceptance.
3. Provision a **different empty**, Timescale-enabled restore DB. Do not migrate
   that target first. Restore the post-freeze archive with the campaign CLI and
   compare every revision-specific evidence-table fingerprint.
4. Verify the original frozen package against its restored immutable record and
   the final JSON package against its separately trusted SHA. Rebuild with the
   same frozen/incident bytes, creation time and builder commit; bytes must match.
5. Retain failed attempts, raw retransmissions and invalid receipts. Never remove,
   repair, interpolate or promote them to make a gate pass.
6. Rehearse the software-only Twin/timeline/command/reconnect scenes while keeping
   desired, reported and derived state distinct. No implicit hardware, production
   provider or command publisher is authorized.

### Reproduce the populated preservation test

From a clean owned checkout, retrieve private bindings for
`COLDGUARD_TEST_HANDOVER_SOURCE_URL` and `COLDGUARD_TEST_HANDOVER_RESTORE_URL`:
distinct direct-loopback psycopg URLs for fresh DBs with extensions provisioned
and no application tables. Also provide approved executable paths in
`COLDGUARD_TEST_PG_DUMP` and `COLDGUARD_TEST_PG_RESTORE`.

From `backend/`, with the locked Python/test prerequisites already staged:

```sh
uv run --offline --locked --extra test pytest -q tests/test_handover.py
```

Use a new uniquely owned temporary/report directory outside Git and immutable
packages for retained results. Never point pytest `--basetemp` at existing
evidence: pytest clears that directory. Each repeat requires new empty source
and restore DBs; a missing prerequisite is NOT_RUN/SKIP, not PASS.

The test seeds explicit software QA/storage fixtures only in a fresh source.
Positive protocol/status/policy/assessment rows and their labelled test-only
signature-field byte hashes do not authenticate a person, commission an envelope,
publish a command or establish physical effect. Their origins/authority labels
must remain visible and command physical status must not be promoted. The test
exercises existing contracts; it adds no application feature or B statistics.

## Independent member drill — not agent self-certification

The real receiving member executes the route; C observes. Retain a separate
secret-free report with:

- [ ] receiving member identity, selected revision and start/end time;
- [ ] owned checkout/provider namespace, private binding verification and staged
  offline prerequisites;
- [ ] actual startup/migration/readiness commands and exits;
- [ ] clean restore, complete fingerprints and export/package hashes;
- [ ] software scenes and deliberate reconnect/negative readiness observations;
- [ ] every failure and manual intervention, including undocumented steps;
- [ ] receiving member's own acceptance or remaining blockers.

An undocumented manual fix is a documentation defect: preserve the failure,
correct the owning guide and repeat the affected command. Do not fill this
checklist with an agent, another process or fabricated member approval. Missing
Compose or a real receiving member keeps the corresponding gate open while the
independent software artifacts are delivered.
