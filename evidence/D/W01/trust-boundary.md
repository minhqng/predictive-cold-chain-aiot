# Trust-boundary map (W01)

**Deliverable:** `trust-boundary.png` (rendered) + `trust_boundary_source.py`
(reproducible stdlib renderer, no extra dependency).
**Regenerate:** `python evidence/D/W01/trust_boundary_source.py`
**Status:** design evidence. It is not a security certification and no network
or device was configured to produce it.

## 1. Zones in the diagram

| Zone | Contains | Trust property |
|---|---|---|
| Device / local safety zone | ESP32, sensors, local policy + safety gate, TEC/fan driver | Physical authority; may reject any remote command; keeps working without cloud |
| Transport | MQTT broker | Authenticated routing only; no actuation authority |
| Cloud / backend zone | Backend API/worker, database, model service | Authenticates, authorizes, validates, stores and advises; never writes GPIO |
| User / operations zone | Frontend and operator | Human intent; must pass backend authn/authz; no device credentials |

## 2. What each actor can and cannot authorize

| Actor | Can | Cannot |
|---|---|---|
| Device | Read sensors, evaluate local policy, reject a command, hold OFF/ON within the characterized family, enter SAFE_LOCAL/FAULT_LOCKOUT | Trust a model score as a command; ignore a hardware stop; invent thresholds |
| Broker | Authenticate clients, enforce topic ACLs, route QoS 1 messages | Authorize an actuation, alter command semantics, bypass the device gate |
| Backend | Authenticate users/services, authorize actions, enforce TTL and idempotency, validate command shape, write audit, publish a command | Publish directly to GPIO, override device safety, claim physical verification from an ACK |
| Database | Persist telemetry, commands, ACKs, state and audit records | Publish control commands or act as a command source |
| Frontend | Present state, collect operator intent, call backend APIs | Hold device credentials, sign/publish device commands, write GPIO |
| Model | Produce a versioned, horizon-bound risk advisory from valid features | Issue commands, read/write GPIO, suppress Controller A, act on stale/invalid data |
| Operator | Authenticate, inspect, request permitted actions | Direct actuator/GPIO access, bypass backend authz, disable interlocks |

## 3. Authorized paths (only these)

1. Operator → Frontend → Backend (HTTPS + RBAC) → Broker → Device validator →
   local safety gate → actuator driver.
2. Sensors → local policy → actuator driver (works with no network).
3. Device → Broker → Backend → Database (telemetry, ACK, audit).
4. Model → Backend (risk advisory only) → policy input as an **advisory view**.
5. Operator/Frontend ← Backend ← Database (read/observe).

Every remote actuation must pass, in order: backend authz → TTL →
idempotency → range → device-local safety/state freshness. The device gate is
last and may reject anything.

## 4. Forbidden paths

- Model → GPIO/actuator (directly or via broker).
- Database → command publish.
- Frontend/operator → device credential or direct actuator access.
- Backend → device actuator without the device-local safety gate.
- Any path that treats an ACK as physical proof.

These are W03 implementation targets; no code-level enforcement is included
in this W01 branch. Broker ACLs and backend authorization must also be
enforced at deployment (owners: infra/C; see `security-baseline-v0.md`).

## 5. Diagram reading notes

- The red dashed segment and the red "X" mark the explicitly forbidden model
  path; it is drawn only to make the prohibition visible.
- Green is local authority; blue is an authorized control/evidence flow; red is
  blocked.
- The diagram deliberately shows **no** arrow from the model to the broker or
  device.
- The rendered artifact is at 1500×980 RGB PNG. Text is uppercase because the
  bundled 5×7 bitmap font is ASCII-only; the source of truth for wording is this
  Markdown file.
