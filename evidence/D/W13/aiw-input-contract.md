# D-W13-01 — AIW input and calculation contract

`assess_aiw()` implements Doc 02 §27 with explicit inputs:

```text
AIW = critical_at - warning_at - physical_response_delay - system_latency
```

`warning_at` comes from B's EWT/horizon evaluation, `critical_at` and
`physical_response_delay` from A's characterized plant runs, and
`system_latency` from C's measured sensing/inference/policy/command path.
Warning and critical timestamps must name the same run and clock domain; the
physical response profile must match its hardware configuration. Every input
has a source and a qualified flag; missing, unqualified or incomparable inputs
return `UNKNOWN`, including when a numeric placeholder exists. Negative and
zero AIW are preserved as `NON_POSITIVE`, never rounded into an opportunity.

The calculation is **candidate analysis only**: the result's
`physical_enablement` is always false. It does not bypass G3 or replace the
W14 AIW/policy gate, model/feature version agreement, or safety checks.
Synthetic unit examples are not measured timing evidence.

Current blockers: `evidence/A/W13/plant-timing-report.json` has no physical
door→critical value and no backend-command→device latency; the available
command→electrical observation has n=1 and is not a distribution. Member B's
qualified warning timing and C's end-to-end latency must be supplied before
this contract can produce a project AIW figure.
