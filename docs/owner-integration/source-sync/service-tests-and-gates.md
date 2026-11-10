# Service tests & evidence gates — Phase 6 addendum (2026-11-10)

## Infrastructure provisioned (owner-authorized, unprivileged)

- **PostgreSQL 16.6** (EDB portable binaries zip, 304MB) — `initdb` in the
  session scratch dir, port **54329**, user `coldguard`, db `coldguard_test`;
  connectivity verified with real `SELECT version()` + `createdb` before any
  suite run.
- **TimescaleDB 2.28.3** (official Windows PG16 asset) — DLLs + control/SQL
  installed into the portable tree, `shared_preload_libraries='timescaledb'`
  (the parameter name must be exactly `shared_preload_libraries`), verified
  live: `CREATE EXTENSION timescaledb` + `timescaledb_information.hypertables`
  queryable.
- **Mosquitto 2.1.2** (NSIS installer silently extracted to the scratch dir —
  no elevation, no service registration): listener `127.0.0.1:18830`,
  `allow_anonymous false`, password file using the development-only
  test credentials already committed in `backend/tests/mqtt_testkit.py`
  (values deliberately NOT reproduced in this document), ACL file enforcing:
  device reads its command topic but CANNOT publish commands or other
  devices' telemetry; backend reads `coldguard/#` and CANNOT spoof device
  telemetry; anonymous denied. Pub/sub round-trip verified with the real
  tools before the suite ran.

## Service suite results (exact)

`pytest` (backend, ml deps, services env): **237 passed, 0 failed, 0
skipped** — the previous 66 service skips all ran: 
ingestion/qos-dedup/persistence, migration baselines (W02/W03/W04 —
downgrade/upgrade head, hypertable guard, replay-classification), normalized
store exact/conflict replay, twin paths, broker security (anonymous denied,
wrong password refused, ACL denials verified by SUBACK codes), serial
gateway replay through the real broker, command publish/service paths,
ACK-consumption correlation, dataset-export flows, recovery/redelivery.
NOT_RUN: none. The only items still NOT_RUN anywhere are tests that require
the combined A+B+C+D merge (no combined tree has been assembled — by policy,
do not claim it).

## Owner QA decisions recorded (this addendum)

1. F3: A observational `*_VERIFIED` and D `EnvelopeQualification.QUALIFIED`
   health states are **distinct claims**; D remains the only authority for
   cooling-health verification.
2. Temperature threshold: demo-specific values only; the numeric
   critical-Tmean is **not frozen** until the approved characterization
   source exists.
3. Clock-sync architecture: **USB-serial laptop-provided time** is the
   selected design direction for future real command execution
   (implementation needs a separate safety review — hardware watchdog and
   real TEC control require separate authorization).

## Physical evidence ledger (W13, already MEASURED — no new measurement required)

From the committed W13 sidecars (verified this session):

| Metric | Value | Provenance |
|---|---|---|
| `command_to_electrical_delay` | **1.094 s** | Measured, n=1 (single trace). This is NOT a distribution — a network-command latency experiment adds the missing first-sample handling for the serial path; the protocol-level command→electrical relation is however proven on the physical capture (PZEM register event, `post_ramp` excluded) |
| `command_to_thermal_delay_min` | **0.85 min** | MEASURED (image `01cedce3`, boot `56044b74`) |
| `cooling_tau_proxy` | **174 s** | MEASURED |
| `recovery_tau_proxy` | **86 s** | MEASURED |

- 30-minute capture sufficiency: **H8-E-1800s (1,800 s, 2,915 frames)** meets
  the W13 A-side duration requirements for cooling tau and recovery tau —
  its measuredთeta proxies carry boot continuity (`01cedce3`/`56044b74`).
- **Missing network command→device latency evidence:** all persisted
  command→* metrics came from a local console trace. A network-issued
  command (backend `command_publisher` → MQTT → device) has never been
  physically captured — requires the C#69 command service on real
  infrastructure + a bench session. This does NOT invalidate the existing
  serial-path physical cooling measurements.
