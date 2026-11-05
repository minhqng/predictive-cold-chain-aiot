# A-W12 handoff — what W12 gives B/C/D

Week-scoped slice of the docs/05A §5 / §6.1–§6.3 handover. Payloads are
`drift-audit.json`, `dataset-validity.csv`, `mechanical-audit-checklist.csv` and
`gate-g3-input.json`; this file says what each may and may not be used for.

## A → B (docs/05A §6.1)

| Field | W12 contribution | Honest state |
|---|---|---|
| configuration identity | `drift-audit.json` → per-capture `evidence_derived_config_identity` (`config:image=<sha>|limits=<policy>` **plus** `content_sha256` and the `boot_ids` set), published separately from `intended_hardware_config` and from `config_verification` | Derived from evidence, not a constant. This is the fix for the defect where two different images collapsed to one key and a byte-copy of a capture produced a fabricated "zero intra-configuration drift". Consumers must read `evidence_derived_config_identity` for grouping and `config_verification` for status; the old `hardware_config_id` column was removed because a bare `CG-HW-001` label is not a verified identity and must not be read as one |
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
  table, which is the only way the configuration identity stops being a *declared* label.
- Hardware-configuration **signoff** (A-W12-04): a decision, not a Member A artifact. The
  validity table separates the intended label `CG-HW-001` from an evidence-derived
  configuration identity, the physical session identity, the per-capture affirmative
  evidence census and the verification status — because a row stamped `hardware_config_id`
  reads as certified while signoff is open. Verification is three separate layers: every
  capture-side requirement met, **and** a named person's review hash-bound to that exact
  inspection record, **and** an approval traceable to provenance outside the namespace this
  tool generates. Satisfying the evidence checks alone does not verify a configuration, an
  empty open-items list is not a signoff, and a matching content hash proves binding only —
  never that an inspection happened or that a person approved anything. A can prepare signoff
  and name what is missing; A cannot sign it.

- **What a reference is not.** `REFERENCE_VALID` means a dated, repository-resolvable
  inspection record exists; it is the existence of a record, not an act by a person, and
  it never lifts the state on its own. `role_map_consistent_with_freeze` compares the
  capture's own role tokens with the frozen map held in source - it is a consistency test,
  not proof that a probe has not moved since the freeze (W14 publishes that as
  `NOT_VERIFIABLE_FROM_ARCHIVED_DATA`).
- **Unresolved historical record, stated so nobody has to rediscover it:** the operator
  measured the branch conductor's **copper-core diameter as 1.75 mm**, which is *not* a
  cross-section; ≈2.405 mm² follows only if the core is solid round, and that construction
  is unconfirmed. W12 carries the corrected reading in
  `drift-audit.json`/`mechanical-audit-checklist.csv`; the `1.75 mm²` strings that appear
  below are **quotations of W04's unresolved wording**, not W12's measurement. `evidence/A/W04/fuse-commissioning-note.md` `:36` and `:62` still publish
  1.75 mm² as a confirmed cross-section, so the two dossiers disagree until W04 carries its
  own dated correction — a documentation defect in W04, referenced here and not edited by
  this slice. Neither reading supports a fuse-suitability or ampacity claim.
