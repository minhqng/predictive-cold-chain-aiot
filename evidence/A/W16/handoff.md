# A-W16 handoff — the comparability framework, and what it refuses to decide

Week-scoped slice of the docs/05A §5 / §6.1–§6.3 handover. Payloads are
`comparability-framework.json`, `final-freeze-evidence-schema.json`,
`response-tolerance-format.json` and `w16-rerun-requirements.csv`. `evidence_kind` is
`HOST_FRAMEWORK_ON_COMMITTED_CAPTURES` and `frozen: false` — this week defines what a freeze
must contain; it does not create one.

## The correction that matters most for W16

`compare_snapshots()` used to answer `COMPARABLE` when the "other side" was the baseline's own
absence: `geometry_roles` compared only the boolean `consistent_with_freeze`, which is true for
an unlabelled slot, `hardware_config_id` was a constant that can never mismatch, and
`physical_output` carried `"UNQUALIFIED(empty column)"`. A snapshot that copied the baseline's
nulls through the real CLI returned `verdict=COMPARABLE, comparison_allowed=true`.

Now absence is its own state. Every dimension reports `MISSING_SIDE` when either side is
null, unlabelled, `UNQUALIFIED` or `UNVERIFIED`, and `comparison_allowed: false` follows from
that rather than from a flag. Concretely today: `cadence_hz` baseline 1.0 with current `null`,
`geometry_roles` baseline showing `t1/t3/t4 = null` and only `t2 = HOT_SIDE`, `hardware_config_id`
baseline `UNVERIFIED` — six dimensions, all `MISSING_SIDE`, so the cross-era comparison is not
permitted and says why.

## A → B (§6.1)

| Field | W16 state |
|---|---|
| pairing context / tolerances | `response-tolerance-format.json`: all four values `NOT_MEASURED`, each carrying the `definition_ref` it will hang on (docs/01 §20.3 `G_T = Tmax − Tmin` for gradient, the frozen critical definition owned by D for the disturbance tolerance). The **form** is delivered; no number is invented |
| hardware_config_id | derived from the shared W12 evidence key, `UNVERIFIED` on the baseline side rather than a constant that always matches |
| valid/invalid run status | `w16-rerun-requirements.csv` enumerates each re-run item with `host_can_compute: false` and its status — `NEED_USER_ACTION` for the OFF envelope and the core ON point, `TEAM_DEPENDENCY` for response delay, which needs the W16 capture to exist before W13's baseline means anything |

W16 gives B no rows. It gives B the schema in which A's future rows become comparable, so a
tolerance freeze later is not retrofitted to whatever happens to be pooled.

## A → D (§6.3)

Two things D needs, both stated as limits rather than conclusions: the freeze-evidence schema
(spells out what "physically frozen" would require, including the unresolved deviation between
the installed conductor and the canonical ask), and the fact that the disturbance tolerance
cannot be chosen from data that does not exist yet. `assert_no_freeze` is a real guard: filling
`frozen: true` or any tolerance trips both the validator and the guard, and it was proven to by
mutation with the pins rebuilt.

## A → C (§6.2)

Nothing. W16 adds no schema, no fixture and no command semantics, and the file says so instead
of manufacturing a contribution.

## What only sessions give this week

A W16-era characterization on the frozen geometry, then the comparison becomes computable:
short OFF-envelope idle current with recorded status, one core ON point at the frozen duty,
response delay re-measured, and an S2 disturbance. Until then `configuration_drift` is empty
because there is one era to look at, not zero drift between two.

Also open and outside Member A's authority: the whole-team G4 reading. W16 supplies A's
physical half and nothing more.
