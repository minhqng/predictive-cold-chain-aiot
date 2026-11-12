# Week 15 — Security enforcement with C

**Current status: HOST AUTHORIZATION LOGIC TESTED; LIVE ENFORCEMENT PENDING.**

C PR #71 was inspected at
`27c12aa7d6d75f9125db1621ce8afbdccd196eca`. Its backend gateway authenticates
the caller, scopes devices and requires policy approval; its MQTT/TLS layer
uses provisioned credentials and TLS 1.2 or later.

`security.py` adds D's pure role/device/audit gate for the required
`VIEWER`, `OPERATOR`, `EXPERIMENTER`, `ADMIN` vocabulary. Tests prove that a
read-only role is denied, an out-of-scope device is denied, and a predictive
command is denied when durable audit is unavailable. Allowed roles are an
explicit deployment input; D does not silently grant a role command access.

Still required for live acceptance: deploy broker ACL and credentials, publish
with an unauthorized test principal and observe `DENIED`, prove no device
actuation, test an insufficient backend role, scan the deployed secret/log
path, and run trusted/invalid TLS endpoint tests. No secret was added here.
