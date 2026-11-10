"""W22 scientific limitations, final-report contract and readiness gate.

Canonical anchors: Doc 03 sections 99-101, 130-135, 158-163; Doc 05B
section 50 (B-W22-06).  The module prepares the final reporting contract and
the interpretation vocabulary without computing any real result.  The W20
campaign-lock assessment remains the only authorization authority; W22 adds
no second, weaker unlock path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .w20_campaign_lock import (
    ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION,
    assess_campaign_lock,
)
from .w22_paired_statistics import W22BoundaryError

W22_READINESS_LAYER_VERSION = "coldguard-w22-readiness-v1"
W22_READINESS_SCHEMA = "coldguard-w22-analysis-readiness-v1"

PHYSICAL_ANALYSIS_AUTHORIZED = "AUTHORIZED"
PHYSICAL_ANALYSIS_NOT_AUTHORIZED = "NOT_AUTHORIZED"
REAL_PAIRED_STATISTICS_NOT_COMPUTED = "NOT_COMPUTED"

INTERPRETATION_SUPPORTS = "SUPPORTS_PHYSICAL_BENEFIT"
INTERPRETATION_MIXED = "MIXED_OR_UNCERTAIN_EVIDENCE"
INTERPRETATION_DOES_NOT_SUPPORT = "DOES_NOT_SUPPORT_PHYSICAL_BENEFIT"
INTERPRETATION_NOT_RUN = "NO_INTERPRETATION_ANALYSIS_NOT_RUN"
INTERPRETATION_CATEGORIES = (
    INTERPRETATION_SUPPORTS,
    INTERPRETATION_MIXED,
    INTERPRETATION_DOES_NOT_SUPPORT,
    INTERPRETATION_NOT_RUN,
)
INTERPRETATION_EVIDENCE_CATEGORIES = (
    INTERPRETATION_SUPPORTS,
    INTERPRETATION_MIXED,
    INTERPRETATION_DOES_NOT_SUPPORT,
)

CURRENT_INTERPRETATION_CATEGORY = INTERPRETATION_NOT_RUN

PREDICTIVE_QUALITY_QUESTION = (
    "Did the model identify an impending thermal event on eligible "
    "non-intervened data?"
)
PHYSICAL_TREATMENT_EFFECT_QUESTION = (
    "Did Controller B actually improve the measured thermal or energy "
    "outcome relative to Controller A?"
)
EWT_CAUSAL_BOUNDARY = (
    "CLOSED_LOOP_PHYSICAL_AB_OUTCOME cannot provide a naive counterfactual "
    "EWT; the reactive crossing that predictive action prevented is not "
    "observable and must not be invented."
)

LIMITATIONS = (
    "Independent pair count: the inferential unit is one accepted matched "
    "Controller A/B pair; telemetry rows, windows and repeated event samples "
    "add no independent N.",
    "Invalid or excluded pairs: every exclusion is listed with its rule, and "
    "a valid extreme pair is never removed from the primary analysis.",
    "Dependence between runs on one rig: repeated runs share session context "
    "and are not multi-site evidence.",
    "One chamber and one hardware unit: the campaign is a single apparatus, "
    "not a population of installations.",
    "Scenario-specific model: predictive quality is conditional on the "
    "frozen scenario, features, threshold and policy.",
    "Potential run-order and ambient drift: randomization, reset criteria and "
    "recorded order bound the bias but do not eliminate it.",
    "Physical measurement and calibration limitations: sensor placement, "
    "ROM identity, calibration lineage and timing provenance constrain what "
    "the outcome numbers mean.",
    "PZEM cooling-branch-only energy: energy is measured on the cooling "
    "branch, never whole-system energy.",
    "Small-N confidence-interval sensitivity: interval width and method "
    "choice matter more as N shrinks; a zero-width interval is not proof of "
    "certainty.",
    "Uncertainty from incomplete recovery: censored recovery is never a "
    "finite time and never enters as a numeric outcome.",
    "Missing physical model acceptance: software verification, synthetic "
    "metrics and offline replay are not a physical model acceptance.",
    "No biological quality ground truth: product-quality claims are outside "
    "the measured thermal/energy outcomes.",
    "Inability to infer unobserved counterfactual outcomes: the closed-loop "
    "A/B pair identifies a measured difference under the frozen protocol, "
    "not every counterfactual trajectory.",
)

WITHHELD_RESULT_ARTIFACTS = (
    "every-pair physical result plot",
    "final paired statistics over accepted physical pairs",
    "primary 95% confidence interval",
    "predeclared paired test result",
    "physical effect size",
    "real sensitivity analysis",
    "final scientific-limitations statement for the campaign",
)

FINAL_REPORT_SECTIONS = (
    "population and pair flow with exclusion reasons",
    "excluded/invalid pair table with rule citations",
    "method statement: primary CI, bootstrap seed/iterations, test family",
    "descriptive statistics with raw arms and I_i per pair",
    "primary 95% CI and physically interpreted effect size",
    "predeclared test result with assumption license",
    "sensitivity and exploratory section, each labelled",
    "scientific limitations",
    "provenance: dataset/split/manifest ids, seeds, code version, freeze gates",
)

REQUIRED_FUTURE_CONDITIONS = (
    "Gate G4 ready and final A/B campaign authorized",
    "frozen pair target completed",
    "completed accepted matched pairs with full attempt history",
    "approved hardware/model/policy freeze",
    "approved statistical and outcome-definition freeze",
    "accepted physical-source and export hashes",
    "verified backup/trace provenance",
    "externally verified analysis-execution authorization (W20 gate decision)",
    "separately reviewed real-data intake bridge (not implemented in W22)",
)


@dataclass(frozen=True)
class FinalAnalysisReadiness:
    """W22's view of whether a real paired analysis may ever be executed."""

    campaign_id: str
    gate_decision: str
    analysis_authorization_status: str
    analysis_authorized: bool
    evidence_class: str
    physical_analysis: str
    real_paired_statistics: str
    outcome_access: bool
    counted_valid_pairs: int
    reasons: tuple[str, ...]
    findings: tuple[str, ...]


def assess_real_analysis_readiness(
    evidence: Mapping[str, Any],
    *,
    verified_artifacts: Mapping[str, str] | None = None,
) -> FinalAnalysisReadiness:
    """Run the authoritative W20 gate and derive W22 readiness from it.

    The function accepts campaign metadata only and delegates every
    authorization decision to ``assess_campaign_lock``; a caller cannot pass
    a pre-labelled assessment object to manufacture authorization.
    """
    if not isinstance(evidence, Mapping):
        raise TypeError(
            "W22 readiness requires the W20 campaign metadata mapping, not an "
            "externally labelled assessment object"
        )
    campaign_lock = assess_campaign_lock(
        evidence, verified_artifacts=verified_artifacts
    )
    authorized = (
        campaign_lock.gate_decision == ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION
        and campaign_lock.analysis_authorization_status == "ISSUED"
        and not campaign_lock.refusal_reasons
        and campaign_lock.outcome_access is False
    )
    reasons = list(campaign_lock.refusal_reasons)
    findings: list[str] = []
    if not authorized:
        reasons.append(f"W20_GATE={campaign_lock.gate_decision}")
        findings.append("W20_ANALYSIS_GATE_NOT_AUTHORIZED")
    else:
        findings.append("W20_GATE_AUTHORIZES_SEPARATE_EXECUTION")
    findings.append(
        "W22_HAS_NO_REAL_DATA_BRIDGE_STATISTICS_REMAIN_NOT_COMPUTED"
    )
    return FinalAnalysisReadiness(
        campaign_id=campaign_lock.campaign_id,
        gate_decision=campaign_lock.gate_decision,
        analysis_authorization_status=campaign_lock.analysis_authorization_status,
        analysis_authorized=authorized,
        evidence_class=campaign_lock.evidence_class,
        physical_analysis=(
            PHYSICAL_ANALYSIS_AUTHORIZED
            if authorized
            else PHYSICAL_ANALYSIS_NOT_AUTHORIZED
        ),
        real_paired_statistics=REAL_PAIRED_STATISTICS_NOT_COMPUTED,
        outcome_access=campaign_lock.outcome_access,
        counted_valid_pairs=campaign_lock.counted_valid_pairs,
        reasons=tuple(dict.fromkeys(reasons)),
        findings=tuple(findings),
    )


def assert_real_analysis_authorized(readiness: FinalAnalysisReadiness) -> None:
    """Fail closed: W22 never executes a real analysis without the W20 gate."""
    if not readiness.analysis_authorized:
        raise W22BoundaryError(
            "PHYSICAL_ANALYSIS_NOT_AUTHORIZED",
            "W20 campaign gate is not authorized for separate execution",
        )
    raise W22BoundaryError(
        "REAL_DATA_BRIDGE_NOT_IMPLEMENTED",
        "W22 provides pure statistics only; a separately reviewed, "
        "authorized intake bridge is required before any real outcome value "
        "may enter these functions",
    )


def declare_interpretation(
    category: str, *, analysis_completed: bool
) -> str:
    """Validate a human-declared interpretation category; never classify."""
    if not analysis_completed:
        if category != INTERPRETATION_NOT_RUN:
            raise W22BoundaryError(
                "INTERPRETATION_WITHOUT_ANALYSIS",
                "no interpretation beyond NO_INTERPRETATION_ANALYSIS_NOT_RUN "
                "is permitted before an authorized analysis",
            )
        return INTERPRETATION_NOT_RUN
    if category not in INTERPRETATION_EVIDENCE_CATEGORIES:
        raise W22BoundaryError(
            "INTERPRETATION_CATEGORY_INVALID",
            "a completed analysis needs an explicit evidence category",
        )
    return category


def build_final_report_template() -> dict[str, object]:
    """Return the final reporting contract, explicitly not a result."""
    return {
        "schema": "coldguard-w22-final-report-template-v1",
        "status": "TEMPLATE_ONLY_NO_RESULT",
        "sections": FINAL_REPORT_SECTIONS,
        "limitations": LIMITATIONS,
        "interpretation_categories": INTERPRETATION_CATEGORIES,
        "current_interpretation": CURRENT_INTERPRETATION_CATEGORY,
        "predictive_quality_question": PREDICTIVE_QUALITY_QUESTION,
        "physical_treatment_effect_question": PHYSICAL_TREATMENT_EFFECT_QUESTION,
        "ewt_causal_boundary": EWT_CAUSAL_BOUNDARY,
        "withheld_result_artifacts": WITHHELD_RESULT_ARTIFACTS,
        "required_future_conditions": REQUIRED_FUTURE_CONDITIONS,
        "synthetic_not_physical": (
            "Synthetic AP, synthetic A1/A2/A3 gains, offline EWT, model "
            "serialization checks and diagnosis software tests are not a "
            "physical paired A/B result."
        ),
    }


def render_final_report_template_markdown() -> str:
    """Render the template as Markdown (no data values, no timestamps)."""
    template = build_final_report_template()
    lines = [
        "# Final matched Controller A/B report — template",
        "",
        "> TEMPLATE ONLY — NO RESULT. The final physical analysis has not run.",
        "",
        "## Scientific questions (separate evidence requirements)",
        "",
        f"- Predictive quality: {template['predictive_quality_question']}",
        f"- Physical treatment effect: {template['physical_treatment_effect_question']}",
        "",
        "## Required sections",
        "",
    ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(FINAL_REPORT_SECTIONS, 1))
    lines.extend(["", "## Mandatory limitations", ""])
    lines.extend(f"- {item}" for item in LIMITATIONS)
    lines.extend(
        [
            "",
            "## Interpretation categories",
            "",
            f"Current: `{CURRENT_INTERPRETATION_CATEGORY}`.",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in INTERPRETATION_CATEGORIES)
    lines.extend(
        [
            "",
            "## EWT causal boundary",
            "",
            EWT_CAUSAL_BOUNDARY,
            "",
            "## Synthetic evidence is not physical evidence",
            "",
            str(template["synthetic_not_physical"]),
            "",
            "## Withheld while the analysis remains locked",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in WITHHELD_RESULT_ARTIFACTS)
    return "\n".join(lines) + "\n"
