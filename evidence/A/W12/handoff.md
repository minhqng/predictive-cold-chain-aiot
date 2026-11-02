# A-W12 handoff — what W12 gives B/C/D

Week-scoped slice of the docs/05A §5 / §6.1–§6.3 handover. Payloads are
`drift-audit.json`, `dataset-validity.csv`, `mechanical-audit-checklist.csv` and
`gate-g3-input.json`; this file says what each may and may not be used for.

## A → B (docs/05A §6.1)

| Field | W12 contribution | Honest state |
|---|---|---|
| `hardware_config_id` | `drift-audit.json` → per-capture `configuration` key, now `config:image=<sha>|limits=<policy>` **plus** `content_sha256` and the `boot_ids` set | Derived from evidence, not a constant. This is the fix for the defect where two different images collapsed to one key and a byte-copy of a capture produced a fabricated "zero intra-configuration drift" |
| sensor identity / placement | `role_geometry_audit` per capture, checked against the frozen as-built map (T1 centre, T2 hot side, T3 bottom, T4 near door) | Labels are compared, never silently rewritten. Canonical `docs/01` 823–825 naming stays a documented discrepancy |
| quality flags | `pzem_audit` + `electrical_qualification` per capture | The committed capture has **no qualified electrical channel**, so every W12 electrical figure is `UNQUALIFIED`. Qualification is never inferred from silence |
| valid/invalid run status | `dataset-validity.csv`: which captures may be pooled and which may not, with the reason | One distinct physical session exists, so intra-configuration drift is reported as a single-session statement, not as a distribution |
| PROBE_IDENTIFICATION exclusion | `is_probe_identification`, now reading path **and** session content | A renamed touch capture no longer slips into drift statistics; the guard is also applied downstream in W13 and W16 because both import this module |

## A → C (§6.2)

Nothing new: W12 adds no telemetry schema, no boot/seq behaviour and no ACK fields. Its
`boot_ids` handling does confirm the operational fact C needs — opening the serial port
resets the board and changes `boot_id`, so a session key derived from boot identity is not
stable across a reconnect.

## A → D (§6.3)

`gate-g3-input.json` is Member A's side of a G3 input, and it is built to be read as such:
`a_side_status: NEED_USER_ACTION`, `does_not_declare` naming what A cannot decide, and
`blockers[]` where each entry carries a `derivation` field — `COMPUTED_FROM_AUDIT` for the
electrical one, labelled `AUTHORED` for the mechanical ones. Nothing in this file declares a
gate GREEN, and the blockers are derived from the audit rather than hardcoded, so closing the
underlying evidence closes the blocker instead of leaving a stale "open" string.

## What only a session can give W12

- A second and third session of the same configuration, before any drift or repeatability
  claim is more than one observation.
- Qualified electrical frames (`current_status`/`voltage_status` recorded, and a status field
  for power/energy, which the capture does not carry at all) — this is the single item that
  moves A-W12-02 from UNQUALIFIED to something checkable.
- The mechanical audit in the field: sensor fixtures, V1 mounting and routing, terminals,
  fuse and conductor insulation evidence, with photos. A checklist written by a host tool is
  a plan, not an inspection.
- ROM/per-channel identity readback from the devices rather than from the configuration
  table, which is the only way `hardware_config_id` stops being a *declared* identity.
- Hardware-configuration **signoff** (A-W12-04): a decision, not a Member A artifact. A can
  prepare it and name what is missing; A cannot sign it.
