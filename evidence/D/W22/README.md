# Week 22 — Final safety case and residual-risk analysis

**Status: PURE DECISION MODULE IMPLEMENTED; HOST SIMULATION TESTED; LIVE EVIDENCE PENDING.**

The `safety_case.py` module implements Doc 05D section 54 (D-W22-01..D-W22-04) as a
pure typed decision layer. It models:

- **Hazard→invariant→test matrix** (D-W22-01) with explicit PASS/FAIL/PENDING
  results and evidence authority tracking;
- **Residual risks** (D-W22-02) with nonempty mitigation and limitation fields;
- **Qualitative severity and likelihood** (D-W22-03) enums only—no numerical
  probability claims;
- **Optional-scope gating** (D-W22-04) that is allowed only when every core
  matrix entry passes and all core evidence is green.

## Module Structure

### SafetyMatrixEntry

Each matrix entry captures one row of the hazard ledger:

```python
SafetyMatrixEntry(
    hazard_id="CTRL-STALE-01",
    hazard_description="Stale command causes unintended actuation",
    hazard_category=HazardCategory.COMMAND_INTEGRITY,
    severity=Severity.HIGH,
    invariant="Expired commands are rejected with no actuation",
    test_id="SEC-EXP-01",
    test_description="Send expired command; verify REJECTED + NO_ACTUATION",
    result=MatrixResult.PASS,  # or FAIL or PENDING
    evidence_authority=EvidenceAuthority.HOST_SIMULATED,  # or LIVE_EVIDENCE
)
```

### ResidualRisk

Each residual risk requires both mitigation and limitation:

```python
ResidualRisk(
    risk_id="RR-01",
    risk_description="Single physical hardware unit limits fault coverage",
    severity=Severity.MEDIUM,
    likelihood=Likelihood.LIKELY,
    mitigation="Comprehensive simulation and host-based negative testing",
    limitation="Hardware-specific failure modes may remain unobserved",
)
```

### OptionalScopeItem

Optional topics (Secure Boot, Flash Encryption, PWM energy policy) are tracked
separately and gated on core matrix success:

```python
OptionalScopeItem(
    item_id="OPT-01",
    item_name="Secure Boot Research",
    description="ESP32-S3 Secure Boot v2 feasibility study",
    core_prerequisite_met=True,  # only when core_matrix_all_pass and core_evidence_green
    status="RESEARCH_ONLY",
)
```

### assess_safety_case()

The main assessment function returns a `SafetyCaseSummary` with:

- `passed_entries`, `failed_entries`, `pending_entries` — categorized matrix entries;
- `core_matrix_all_pass` — True only when no failed or pending entries;
- `core_evidence_green` — True when all entries have valid evidence authority;
- `optional_scope_allowed` — True only when core_matrix_all_pass AND core_evidence_green;
- `blockers` — explicit list of issues preventing safety case completion.

## Default Hazards

The module provides `DEFAULT_CORE_HAZARDS` covering canonical hazards from
Doc 05D:

| Category | Hazard ID | Description |
|---|---|---|
| COMMAND_INTEGRITY | CTRL-STALE-01 | Stale command causes unintended actuation |
| COMMAND_INTEGRITY | CTRL-DUP-01 | Duplicate command causes repeated physical action |
| RESILIENCE_FAILURE | RES-CLOUD-01 | Cloud/broker outage removes all protection |
| RESILIENCE_FAILURE | RES-AI-01 | AI/model unavailable causes unsafe behavior |
| PHYSICAL_VERIFICATION | PHYS-ACK-01 | ACK-only success claim without physical verify |
| SECURITY_THREAT | SEC-UNAUTH-01 | Unauthorized client publishes command |

## Default Residual Risks

Four canonical residual risks are provided:

| ID | Description | Severity | Likelihood |
|---|---|---|---|
| RR-01 | Single physical hardware unit limits fault coverage | MEDIUM | LIKELY |
| RR-02 | No formal penetration test or security certification | MEDIUM | POSSIBLE |
| RR-03 | Optional Secure Boot / Flash Encryption not deployed | LOW | UNLIKELY |
| RR-04 | Uninstrumented internal TEC junction temperature | LOW | RARE |

## Optional Scope Items

When `include_optional=True`, three optional items are tracked:

| ID | Name | Status |
|---|---|---|
| OPT-01 | Secure Boot Research | RESEARCH_ONLY |
| OPT-02 | Flash Encryption Lab Plan | LAB_PLAN_DRAFTED |
| OPT-03 | PWM Energy Policy | NOT_STARTED |

**Important:** Optional scope items NEVER jeopardize core delivery. The
`optional_scope_allowed` flag is True only when the core matrix is fully green.

## Evidence Authority

The module distinguishes:

- `EvidenceAuthority.HOST_SIMULATED` — host-based simulation/testing;
- `EvidenceAuthority.LIVE_EVIDENCE` — live physical/transport evidence.

**This module does not claim live evidence.** Host simulation can validate the
decision contract, but only live evidence from physical campaigns can mark the
final safety case complete.

## Usage Example

```python
from coldguard_control.safety_case import (
    build_default_safety_case,
    EvidenceAuthority,
    MatrixResult,
)

# Defaults are host-only PENDING fixtures and fail closed
summary = build_default_safety_case()
assert summary.core_matrix_all_pass is False
assert summary.core_evidence_green is False
assert summary.optional_scope_allowed is False

# Override one entry to FAIL
summary = build_default_safety_case(
    result_override={"CTRL-STALE-01": MatrixResult.FAIL}
)
assert summary.core_matrix_all_pass is False
assert summary.optional_scope_allowed is False
assert "FAILED_ENTRY:CTRL-STALE-01" in summary.blockers

# Optional items may be listed, but remain gated until every core row is a
# provenance-backed LIVE_EVIDENCE PASS.
summary = build_default_safety_case(include_optional=True)
assert len(summary.optional_scope_items) == 3
assert summary.optional_scope_allowed is False
```

## Tests

The `test_safety_case.py` suite verifies:

- Entry validation (nonempty fields, correct types, immutability);
- Residual risk validation (nonempty mitigation/limitation);
- Optional scope item validation (strict boolean for prerequisite);
- Assessment logic (categorization, gating, blockers);
- Doc 05D section 54 compliance (matrix structure, qualitative enums, gating);
- No numerical probability fields (qualitative only).

## Limitations

- **No live evidence claimed** — all entries default to HOST_SIMULATED;
- **No physical tests executed** — pure decision layer only;
- **No evidence modification** — inputs are validated and categorized, not mutated;
- **Optional scope is research-only** — Secure Boot, Flash Encryption, and PWM
  policy remain optional hardening, not P0 requirements per Doc 05D section 26.

## Gate G6 Readiness

This module supports Gate G6 (final safety case) by providing:

1. Structured hazard→invariant→test matrix;
2. Explicit residual risk register;
3. Qualitative risk assessment (no unjustified numerical claims);
4. Clear gating for optional scope items.

**G6 requires live evidence** for the final safety case. This module provides
the decision structure; live campaigns must supply LIVE_EVIDENCE authority
entries.
