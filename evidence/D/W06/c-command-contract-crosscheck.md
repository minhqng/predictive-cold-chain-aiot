# D/C v0 command contract cross-check

The canonical request example is `backend/fixtures/command_v0.json`. D's
`CommandRequest` is a reduced, pure-validator input: it holds epoch seconds and
the fields needed by D's safety decision. The boundary-only
`control/scripts/command_projection.py` requires
the C provenance fields `controller_id`, `policy_version` and `reason_code`,
checks UTC timestamps and nested `action.cooling`/`action.duty`, then constructs
that input. Unit tests read the actual C fixture and reject missing provenance,
naive timestamps and string duty. This guards the handoff shape; it does not
claim authentication, MQTT delivery, serial translation, ACK persistence or
physical actuation. The C W06 disposable-broker test and the A flat serial
gateway remain separate integration work.
