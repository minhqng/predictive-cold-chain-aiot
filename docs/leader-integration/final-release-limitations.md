# Final release limitations and technical deviations

This document records what the final release delivers, what was demonstrated on
hardware, what was verified only in software, and where the release deviates
from the proposed architecture. It is written to be academically defensible and
technically truthful: deviations are documented, not presented as completed
acceptance, and the original approved ColdGuard scope is preserved.

Companion ledger: [hardware-baseline.md](hardware-baseline.md).
Provenance: [provenance.md](provenance.md).

## A. Completed implementation

The release integrates the Leader-owned software layer on top of the preserved
Member A/B/C/D contributions:

- Compact Vietnamese live Dashboard (`backend/integration/leader_dashboard.html`
  + `leader_dashboard_server.py`): T1/T2/T3/T4 thermal probes, BME280
  environment, real PZEM voltage/current/power/energy, door OPEN/CLOSED, true
  applied TEC percentage and pause state, device/boot and Digital-Twin readiness,
  historical chart, XGBoost +60 s forecast, history-API and forecast-check
  status, and sensor freshness/validity.
- Temperature setpoint control preserved as an **authenticated desired-state
  configuration** (see F). It updates the Member D policy target; it never
  grants physical ARM/START authority.
- Leader serial gateway, boot reconcile tool, door-aware shadow orchestrator,
  live inference bridge and portable stack launcher.
- Member D reactive controller and CRITICAL_PROTECTION precedence preserved
  unchanged; door-aware policy semantics preserved.
- Member B frozen W15 XGBoost artifact used for the experimental +60 s forecast
  display, with honest blocked/stale/unavailable reporting.

## B. Physically demonstrated

`HARDWARE_BENCH_VERIFIED` on **historical** images only (see the ledger for
evidence locations): BME280 and MC-38 sensor benches, fuse/commissioning
electrical safety, the H8 supervised bench A–E (IBT-2 paired-enable load-current
path, T2 hot-side probe), and the W06 demo command capture. These are separate
bench records on historical firmware images. They do **not** demonstrate the
release stack running together, and they do **not** demonstrate AI-driven
closed-loop physical control.

## C. Software-only verified

`INTEGRATION_OFFLINE_VERIFIED` / `SHADOW_ONLY_VERIFIED`, re-run for this release:

- Backend full suite with disposable PostgreSQL 16.10 + pg_dump/pg_restore:
  **857 passed, 94 skipped, 0 failed**. The 94 skips require Mosquitto, OpenSSL
  or dedicated migration/restore databases that were not provisioned; they skip
  honestly, not as failures.
- Backend no-database baseline: 580 passed, 371 skipped, 0 failed.
- Member D control regression: **770 passed** (matches the prior checkpoint).
- Member B ML focused (`test_feature_causality`, `test_w15_artifact`):
  **57 passed** (matches the prior checkpoint).
- Leader setpoint authority: 8 passed (fail-closed unprovisioned/missing/wrong
  token; desired-state-only write; legacy ARM/AI routes 405).
- Leader dashboard XGBoost contract: 8 passed; live inference: 35 passed.
- Shadow boundary tests prove zero physical dispatch and that the operator
  setpoint becomes the Member D target without actuation.
- PZEM zero-vs-missing current (`test_zero_measurement_is_not_missing`), twin
  desired-vs-reported separation, and applied-duty-from-device-telemetry are
  covered by the passing backend suite.

## D. Unverified on the final release

`PHYSICAL_END_TO_END_NOT_RUN` / `NOT_PROVEN` (hardware unavailable):

- The release firmware + Dashboard + gateway were not run together on hardware.
- AI-driven closed-loop physical TEC control was not demonstrated.
- AI electrical-efficiency improvement is not proven.
- XGBoost production-ready prediction is not proven (persistence beat the
  experimental model on holdout; the forecast is experimental demo only).
- Cold-face temperature is not proven (no cold-side probe fitted).
- The excluded Leader firmware components and Member A working-tree diffs were
  not re-verified on hardware; their host harness tests need a host C compiler
  that is unavailable, so they are `NOT RUN` offline.

All physical hardware tests are recorded `NOT RUN — PHYSICAL HARDWARE
UNAVAILABLE`. No `PHYSICAL TEC PASS` or `RUNTIME FIRMWARE VERIFIED` is claimed.

## E. Known architectural deviations

The release preserves the instructor-approved ColdGuard architecture and does
not redesign physical control:

1. **Physical authority stays with Member D + Leader orchestrator.** The newest
   TEC100 demo independently turned XGBoost forecasts into TEC demand (AI_DEMO)
   and relaxed the console grant in dashboard mode. That direct AI actuation
   path is **excluded** from the release. AI inference and display are preserved;
   physical decision authority is not delegated to the model or to an HTTP
   endpoint. This is a deliberate security deviation from the demo, documented
   here rather than hidden.
2. **Setpoint is desired-state, not actuation.** The demonstrated demo setpoint
   could mutate runtime state directly. The release setpoint is an authenticated
   configuration value consumed by the unchanged Member D policy. The safe
   execution semantics differ from the demo and the difference is explicit.
3. **Shadow mode is an additional validation capability, not a downgrade.** The
   project identity and supervised-physical objective are preserved. Shadow mode
   lets decisions be observed offline with zero physical dispatch; it does not
   redefine the product as shadow-only.
4. **Hardware-facing firmware is preserved, not refactored.** The committed
   Member A firmware baseline is unchanged in the release. Unverified Leader
   firmware components and Member A diffs are preserved in the worktree and
   excluded pending hardware validation and an explicit Leader decision.

## F. Security restrictions

Unsafe externally accessible physical command paths are disabled or gated in
Leader-owned boundaries; the proven firmware/serial protocol is unchanged:

- AI_DEMO direct physical dispatch: **removed** (no independent AI authority).
- Dashboard console-grant relaxation: **removed**.
- Unauthenticated ARM/setpoint POST: setpoint now requires a bearer operator
  token provisioned via `CG_OPERATOR_TOKEN` (constant-time compare, fail-closed
  503 when unprovisioned, 401 on missing/wrong token). Legacy `/ai/arm`,
  `/ai/setpoint`, `/arm`, `/grant`, `/start` routes return 405.
- Unscoped persistent ARM flag: **removed** (no bare arm file).
- SHADOW mode disallows GRANT/ARM/START/nonzero duty/production MQTT dispatch.
- SUPERVISED PHYSICAL remains behind separate operator authorization, current
  boot-scoped admission, authenticated command, correlated ACK and a bounded
  session. Loopback binding alone is never treated as authorization.
- Runtime credentials are environment-provisioned; `/runtime/leader/` is
  gitignored; the credential-bearing Leader lineage (`156fc58`, `326ed9f`,
  `914eec09`, `6507fa7`) is excluded from release ancestry.

## G. Future work

- Physical commissioning of the release firmware + Dashboard + gateway together
  (`PHYSICAL_END_TO_END_NOT_RUN` today), under supervised operator authorization.
- Hardware validation and an explicit Leader decision before releasing the
  excluded Leader firmware components and Member A working-tree diffs.
- End-to-end physical regression: ACK → ARM → START sequencing, applied-state
  feedback, door pause and final OFF evidence on real hardware.
- Model validation against the persistence baseline before any production or
  superiority claim; cold-side probe fitting if cold-face control is required.
- Provision Mosquitto/OpenSSL and dedicated migration databases to convert the
  94 honest backend skips into executed tests in CI.