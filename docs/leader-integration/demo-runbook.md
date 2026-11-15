# Leader integration and demo

The Leader gateway converts authenticated device frames to the Member C MQTT telemetry contract. The backend stores those frames in PostgreSQL and projects the Digital Twin. The Dashboard displays device-reported measurements and valid model output. The door orchestrator evaluates Member D policy and records a **shadow proposal**. Its output does not enter the physical command transport.

Use the dependency locks and service setup in the [repository README](../../README.md) and [Member C runbook](../../backend/RUNBOOK.md). Keep each runtime's credentials outside Git. MQTT ACL for diagnostic frames is limited to the configured device principal and the read-only ingest principal.

From the repository root, in a Python environment provisioned by the backend lock with the gateway and inference extras (uv sync --locked --extra gateway --extra inference from backend), put the repo's backend directory on PYTHONPATH. Run each service from its own terminal:

| Component | Command | Configuration |
| --- | --- | --- |
| Member C backend | python -m integration.leader_launch_backend | DATABASE_URL and Member C MQTT environment |
| Leader gateway | python -m integration.leader_launch_gateway | MQTT_USERNAME and MQTT_PASSWORD for the device; COLDGUARD_SERIAL_PORT if USB identity is ambiguous |
| Vietnamese Dashboard | python -m integration.leader_dashboard_server | DATABASE_URL for history/forecast; CG_DASHBOARD_MQTT_USERNAME and CG_DASHBOARD_MQTT_PASSWORD for the read-only ingest principal |
| Member D shadow overlay | python -m scripts.leader_door_orchestrator | CG_EVENTS_FILE for a shared shadow log if overriding its default; CG_POLICY_LOWER_OFF_C and CG_POLICY_UPPER_ON_C for the shadow temperature band |
| Twin boot reconciliation | python -m scripts.leader_boot_reconcile | DATABASE_URL and optional --device-id; requires the fresh Dashboard boot to match the newest eligible observation in PostgreSQL |

Use a consistent MQTT_HOST/MQTT_PORT across processes. Dashboard and shadow overlay accept CG_BACKEND_URL. The shadow overlay accepts CG_DASHBOARD_URL. The Dashboard and shadow overlay default to coldguard-001; set CG_DEVICE_ID consistently if using another ID, and pass the same identity to the gateway and broker ACL. Keep the local Dashboard bound to loopback.

The Dashboard has read-only routes. A shadow proposal and measured applied duty are separate. PZEM zero is a valid reading when the device reports valid electrical data. Missing or stale data appears unavailable. Historic observations are separated by boot and are not treated as live telemetry. The feature and model bundle supplies a +60 s forecast only with validated inputs from the matching boot.

## Physical commissioning

An attended bench trial needs fresh current-boot BOOT/AUTH, valid electrical and thermal measurements, one local GRANT TEC200 from the gateway console, a correlated ACK, firmware ARM and START, measured applied feedback, and verified final OFF/0. Start the gateway with --operator-console only for this workflow, on a compatible Windows console. Arrange capture before the authorized device boot. Console ABORT TEC200 revokes the request. No Dashboard or forecast request grants physical authority.

The fixture command runner is backend/scripts/leader_tec200_run.py. It requires DATABASE_URL, MQTT_HOST, MQTT_PORT, MQTT_INGEST_PASSWORD and MQTT_COMMAND_PASSWORD at runtime. Use its help for the explicit expected-boot, command ID, operator authorization, and local evidence directory arguments. A retained MQTT command or a command for another boot cannot authorize a trial.

The default firmware does not enable the supervised limits. The separately staged build option for the reviewed bench profile is --supervised-limits --supervised-no-cold-probe --duty-permille 200. The installed T2 is the hot-side probe. The cold-side probe is NOT_FITTED. The explicit no-cold-probe deviation applies only to the attended 200-permille profile. Select the as-built interlock mode according to the device configuration. The untracked continuous TEC100 demo controller and its alternative authority path are outside this release.

[Historical H8 TEC traces](../../evidence/A/SOURCES/20261107/datasets/datasets/H8-C-600s-TEC-100pct-normalized.csv) and earlier signed-off trial observations remain evidence of their original builds and fixtures. Release software checks cannot establish a new physical commissioning result.
