# Frozen inference and backend command authority

Install the optional CPU runtime with `uv sync --locked --extra inference`
when an approved Member B artifact is available. The backend can start
without an inference artifact. It reports prediction evidence as unavailable
until a trusted caller has recorded a valid result.

Load native XGBoost JSON or UBJSON using `load_frozen_model`. Supply the
candidate's version metadata and a separate trusted `FrozenModelSpec`.
Provide the frozen feature definition file and artifact file. The adapter
checks both SHA-256 values, the model and feature versions, and ordered
feature names before accepting a feature vector. The manifest specifies the
horizon in seconds. Invalid vectors or model output fail closed. No training
or replacement model runs in the backend.

The trusted inference caller supplies the exact normalized telemetry IDs
and receipt-time window. `infer_and_record` commits the prediction and ordered
inputs before returning. Only the currently fresh result carries a risk score
in that response. The official model and Member B feature production flow
require separate integration acceptance.

## TLS and MQTT identities

Use `infra/mosquitto/mosquitto-tls.conf` for the TLS-only broker listener.
Mount a trusted server certificate and private key at the configured paths
and provision a password file. Bind the exposed host port to the approved
interface. The secured listener requires TLS 1.2 or later and disallows
anonymous connections. Use device-specific ACL entries for additional
devices.

Set backend `MQTT_TLS_CA` to the CA bundle path, `MQTT_HOST` to the certificate
hostname or IP, and configure the TLS port and provisioned credentials. The
backend verifies trust and hostname. It fails startup when trust or
credentials are invalid. The development listener remains an explicit local
profile with its existing configuration.

Use separate identities for devices, backend ingestion, and the
`backend-command` publisher. Provision the publisher only for server-side
authorized control. A device may subscribe to its own command topic.
It cannot publish commands or access another device's command path.

## Command authorization

`AuthorizedCommandGateway` is the internal backend dispatch entrypoint.
It requires an authenticated server caller, explicit device scope, and a
trusted policy decision before creating durable intent. Configure a private
backend token of at least 32 characters and keep it separate from broker
credentials. The public application exposes read-only command timing
and has no HTTP dispatch route.

The disposable TLS tests exercise certificate trust, hostname verification,
failed authentication, both backend subscribers, scoped ACL denial, and
authorized software-only delivery. Member D signoff and hardware acceptance
remain separate.

## Predictive dispatch and physical assessment authority

W18 uses `ControllerBDispatch` for predictive commands. It requires the private
backend token/device scope, an explicitly provisioned `DPolicyAuthority`, a
trusted frozen model specification, and an exact-envelope approval signature.
Approval is checked again against current durable context immediately before
the broker handoff. An immutable receipt records key and evidence digests
before transport; it does not export approval keys or reusable signatures.
Generic publication is not a predictive-authority bypass. An uncertain
predictive command is not automatically replayed on reconnect.

Physical certification has a different authority, `PhysicalAuthority`. It is
not configured by default or exposed as an MQTT/HTTP verdict route. The
authority must be provisioned out of band for a commissioned operating envelope
and must sign scoped measurement evidence. Neither broker PUBACK, accepted ACK,
desired state, raw device verification claims nor a test PHYSICAL label grants
that authority. Provisioned software test keys exercise the boundary only.

See [the command path](COMMAND_PATH.md#controller-b-integration-w18-revision-0012)
for the stage sequence, database fences, migration safeguards, acquisition-time
freshness and deterministic trace contract. These controls do not replace
device-side expiry/idempotency or Member A/D physical safety approval.
