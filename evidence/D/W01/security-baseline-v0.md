# P0 security baseline v0 (W01)

**Scope:** minimum security boundary for remote control of the ColdGuard
chamber. This is a requirement/design document, not a deployed configuration
or certification.
**Status:** P0 items are mandatory before any remote actuation is accepted;
optional hardening does not gate control safety (Doc 05D §27).
**Ownership:** Member D specifies control-facing requirements; identity,
broker, backend authorization and infrastructure belong to Member C/platform/
infra per Doc 04. No validator or deployment control is included in this W01
branch; the later W03 stack adds only pure unit-level validation.

## 1. P0 controls (mandatory)

| ID | Requirement | Threat addressed | Minimum control | W01 status | Evidence required before deployment |
|---|---|---|---|---|---|
| SEC-P0-01 | Device identity | Spoofed device, wrong-device command, impersonation | Unique device-bound credentials; no shared device secret | Requirement specified; no credential provisioning | Broker/device provisioning record and rotation procedure (C/infra) |
| SEC-P0-02 | TLS-capable broker and clients | Eavesdropping, tampering, credential theft | TLS on all broker links; no plaintext fallback for production; certificate validation | Requirement specified; no broker configuration | Broker config, TLS scan and client trust-store review (infra/C) |
| SEC-P0-03 | Topic ACL / least privilege | Pub/sub scope creep, rogue client, cross-device control | Per-device allowlist; separate telemetry, command and ACK topics; deny by default | Trust-boundary design only; no ACL file | ACL export and wrong-topic negative test (C/infra) |
| SEC-P0-04 | Backend authentication and authorization | Unauthorized operator/service, privilege escalation | Human authn + role-based authz; service identity for model/worker; audit decision before command creation | Requirement specified; no backend authz implementation | Backend tests and subject/role/decision audit (C) |
| SEC-P0-05 | Command TTL | Stale/replayed command after delay or reconnect | `expires_at` enforced server-side and device-side; retained command delivery forbidden; bounded clock skew | Requirement specified; TTL semantics and code are later work | Command lifecycle tests and clock-skew policy (C/A/D) |
| SEC-P0-06 | Idempotency | Duplicate delivery causes repeated actuation | Stable `command_id`; return canonical result; no second actuation; persistence across relevant reconnects | Requirement specified; no dedup store | Reconnect/replay test and retention window (C/A) |
| SEC-P0-07 | Audit | Undetected misuse, non-repudiation gap, unsafe trend | Append-only lifecycle audit with policy version, state, reason and auth decision | Required fields identified; no persistence implementation | Audit schema and retrieval by `command_id` (C) |
| SEC-P0-08 | Command shape/range validation | Malformed payload, wrong action, duty injection, stale state | Schema, identity, expiry, duplicate, range, safety and freshness checks; malformed values fail closed | W01 specifies the requirement; pure validator is a later W03 deliverable | W04 integration test against the real wire contract |
| SEC-P0-09 | Local authority / default-OFF | Remote compromise reaches actuator; boot actuation | Device-local gate may reject any command; hardware default-OFF; hardware stop dominates | Conceptual boundary only; no firmware/hardware evidence | Boot/reset measurement and interlock review (A) |
| SEC-P0-10 | No model/DB/UI → GPIO path | Model or convenience endpoint bypasses validation | Model advisory only; single local gate; broker ACL blocks model from device topics | Shown as a forbidden path in the design; no runtime enforcement in W01 | Architecture review and ACL negative test (C/infra) |

## 2. Optional hardening (not a control-safety dependency)

| Item | Benefit | Status / rule |
|---|---|---|
| Secure Boot | Prevents unauthorized firmware | Optional per Doc 05D §27; not implemented or claimed. Must not be required to keep the actuator safe. |
| Flash Encryption | Protects secrets/at-rest firmware | Optional; recovery/provisioning procedure required before enabling. |
| Signed OTA + rollback protection | Prevents malicious/corrupt update, supports recovery | Optional; signed, versioned and auditable; control safety cannot depend on OTA. |

Enabling optional items must not brick recovery or change default-OFF behavior.
None is evidence of certification.

## 3. Threat scenarios considered

1. A valid but stale command is replayed after outage → TTL, no retained
   commands and SAFE_LOCAL exit gate.
2. A duplicate QoS 1 delivery causes repeated actuation → command-id
   idempotency and canonical result.
3. A command for another device is delivered → device-id rejection.
4. Malformed schema or duty enters the device → schema/range rejection.
5. The model or a compromised service attempts direct actuation → no
   credential/topic path; model output remains advisory.
6. DB/broker outage continues remote control → remote path becomes unhealthy;
   device falls back to SAFE_LOCAL.
7. Frontend/operator bypasses backend authorization → frontend has no device
   credentials; backend is the only command creator.
8. Wrong-topic client publishes a command → per-device ACL denial.
9. TLS is downgraded/misconfigured → deployment check must fail closed.
10. Credential leakage → device-scoped identity, revocation and rotation.

## 4. Non-claims and open gaps

- No penetration test, TLS scan, broker ACL audit, backend authorization test or
  physical fault test was performed in W01.
- Authorization must be verified by backend/broker identity; a future pure
  validator can only consume an asserted authorization result.
- Clock-skew, TTL, dedup retention and topic semantics need owners and evidence
  before remote actuation.
- Reason codes are vocabulary, not proof of end-to-end detection.

## 5. Minimum evidence to close P0

```text
[ ] broker TLS configuration + client certificate validation
[ ] per-device ACL export and wrong-topic negative test
[ ] backend authn/authz tests for operator, model and worker identities
[ ] command lifecycle test: create -> authorize -> publish -> ACK -> verify
[ ] duplicate/replay test across a device reconnect
[ ] audit retrieval by command_id and policy_version
[ ] boot default-OFF measurement and hardware-stop review
[ ] architecture review confirming no model/DB/UI -> GPIO path
```

Until these exist, the baseline is **specified**, not **verified**.
