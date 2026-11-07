"""W12 Gate G3 evidence matrix and decision (B-W12-05).

Software GREEN cannot buy a physical/data RED. Every row is tied to an
authoritative committed source or is explicitly NOT_VERIFIED.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

G3_SCHEMA = "coldguard-w12-gate-g3-v1"
G3_EVIDENCE_MATRIX_SCHEMA = "coldguard-w12-gate-g3-evidence-matrix-v1"
PASS_VERIFIED = "PASS_VERIFIED"
FAIL_VERIFIED = "FAIL_VERIFIED"
BLOCKED_BY_MISSING_EVIDENCE = "BLOCKED_BY_MISSING_EVIDENCE"
NOT_VERIFIED = "NOT_VERIFIED"
NOT_APPLICABLE = "NOT_APPLICABLE"
GO = "GO"
GO_WITH_LIMITATIONS = "GO WITH LIMITATIONS"
NO_GO_FIX_DATA = "NO-GO / FIX DATA"

HARD_REQUIREMENTS = (
    "G3-A-PHYSICAL-PLANT",
    "G3-B-GROUPED-DATASET",
    "G3-B-XGB-BENCHMARK",
    "G3-D-CONTROLLER-A",
    "G3-D-COMMAND-VERIFY",
    "G3-C-PLATFORM-BACKUP",
    "G3-TEAM-APPROVAL",
    "G3-B-LEAKAGE",
)


class GateReadinessError(ValueError):
    """A gate row would claim more than its source evidence supports."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path_record(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.exists():
        return {
            "path": relative,
            "exists": False,
            "sha256": None,
        }
    return {
        "path": relative,
        "exists": True,
        "sha256": _sha256(path),
    }


def _relative_or_str(root: Path, path: str | Path) -> str:
    resolved = Path(path)
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def _load_json(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class GateRow:
    requirement_id: str
    requirement: str
    canonical_source: str
    owning_team_member: str
    required_evidence: str
    actual_file_reference: str
    source_hash_revision: str
    observed_result: str
    evidence_quality: str
    readiness_status: str
    blocking_reason: str
    next_required_evidence: str
    review_authority: str

    def to_row(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "requirement": self.requirement,
            "canonical_source": self.canonical_source,
            "owning_team_member": self.owning_team_member,
            "required_evidence": self.required_evidence,
            "actual_file_reference": self.actual_file_reference,
            "source_hash_revision": self.source_hash_revision,
            "observed_result": self.observed_result,
            "evidence_quality": self.evidence_quality,
            "readiness_status": self.readiness_status,
            "blocking_reason": self.blocking_reason,
            "next_required_evidence": self.next_required_evidence,
            "review_authority": self.review_authority,
        }


@dataclass(frozen=True)
class GateDecision:
    decision: str
    hard_blockers: tuple[str, ...]
    rationale: tuple[str, ...]
    software_status: str
    physical_status: str
    human_authority: str
    permitted_work: tuple[str, ...]
    forbidden_work: tuple[str, ...]


@dataclass(frozen=True)
class GateReadinessReport:
    schema: str
    rows: tuple[GateRow, ...]
    decision: GateDecision
    source_revisions: Mapping[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "rows": [row.to_row() for row in self.rows],
            "decision": {
                "decision": self.decision.decision,
                "hard_blockers": list(self.decision.hard_blockers),
                "rationale": list(self.decision.rationale),
                "software_status": self.decision.software_status,
                "physical_status": self.decision.physical_status,
                "human_authority": self.decision.human_authority,
                "permitted_work": list(self.decision.permitted_work),
                "forbidden_work": list(self.decision.forbidden_work),
            },
            "source_revisions": dict(self.source_revisions),
            "limitations": list(self.limitations),
        }


def _gate_row(**kwargs: Any) -> GateRow:
    return GateRow(**kwargs)


def build_gate_g3_readiness(
    *,
    repo_root: str | Path,
    w11_manifest: Mapping[str, Any],
    w08_manifest: Mapping[str, Any],
    w09_manifest: Mapping[str, Any],
    w10_manifest: Mapping[str, Any],
    w11_manifest_path: str | Path,
    w08_manifest_path: str | Path,
    w09_manifest_path: str | Path,
    w10_manifest_path: str | Path,
    software_status: str = "GREEN",
) -> GateReadinessReport:
    root = Path(repo_root)
    a_census = _load_json(root, "evidence/A/W24/acceptance-census.json")
    a_dry_run = _load_json(root, "evidence/A/W18/controller-B-dry-run-index.json")
    a_checklist = _load_json(root, "evidence/A/W18/pre-run-safety-checklist.json")
    a_freeze = _load_json(root, "evidence/A/W16/final-freeze-evidence-schema.json")
    physical = w08_manifest.get("physical_gate", {})
    predictive = w08_manifest.get("predictive_gate", {})
    split_gate = w08_manifest.get("split_gate", {})
    real_a = w10_manifest.get("real_a", {})
    real_w11 = w11_manifest.get("real_development", {})
    a_paths = [
        "evidence/A/W24/acceptance-census.json",
        "evidence/A/W18/controller-B-dry-run-index.json",
        "evidence/A/W18/pre-run-safety-checklist.json",
        "evidence/A/W16/final-freeze-evidence-schema.json",
    ]
    a_sources = {
        relative: _path_record(root, relative) for relative in a_paths
    }
    missing_a = [name for name, record in a_sources.items() if not record["exists"]]
    if missing_a:
        raise GateReadinessError(
            "authoritative A evidence is missing: " + ", ".join(missing_a)
        )
    w08_path = _path_record(root, _relative_or_str(root, w08_manifest_path))
    w09_path = _path_record(root, _relative_or_str(root, w09_manifest_path))
    w10_path = _path_record(root, _relative_or_str(root, w10_manifest_path))
    w11_path = _path_record(root, _relative_or_str(root, w11_manifest_path))
    for binding_name, record in (
        ("w08_binding", w08_path),
        ("w09_binding", w09_path),
        ("w10_binding", w10_path),
    ):
        binding = w11_manifest.get(binding_name)
        if not isinstance(binding, dict) or not binding.get("sha256"):
            raise GateReadinessError(
                f"W11 {binding_name} is missing provenance; evidence is not accepted"
            )
        if binding["sha256"] != record["sha256"]:
            raise GateReadinessError(
                f"W11 {binding_name} does not match the actual source bytes; "
                "mismatched evidence bundles are refused"
            )
    w10_w08 = w10_manifest.get("w08", {})
    if w10_w08.get("sha256") and w10_w08["sha256"] != w08_path["sha256"]:
        raise GateReadinessError(
            "W10 W08 receipt does not match the actual W08 manifest bytes"
        )
    physical_source = w10_manifest.get("real_a", {}).get("source_sha256")
    if physical_source:
        source_file = root / "evidence/A/W09/exports/CG-S1-H8C-600S.json"
        if not source_file.exists():
            raise GateReadinessError(
                "the physical source referenced by W10 is not committed"
            )
        actual_source = _sha256(source_file)
        if actual_source != physical_source:
            raise GateReadinessError(
                "W10 physical source SHA does not match the actual A export"
            )
        if physical_source not in physical.get("evidence_sha256", ()):
            raise GateReadinessError(
                "W08 Gate B does not bind the same physical source SHA as W10"
            )
    a_status = a_census.get("physical_acceptance_status", "UNKNOWN")
    a_gates = a_census.get("open_hardware_gates_count", "UNKNOWN")
    a_posture = a_census.get("hardware_posture", "UNKNOWN")
    gate_b = physical.get("observed_status", "UNKNOWN")
    eligible_runs = real_a.get("eligible_s1_runs", 0) + real_a.get("eligible_s2_runs", 0)
    ap_by_method: dict[str, list[float]] = {}
    for comparison in w11_manifest.get("baseline_comparison", ()):
        value = comparison.get("sample_ap")
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number and number not in (float("inf"), float("-inf")):
            ap_by_method.setdefault(comparison["method"], []).append(number)
    ap_text = ", ".join(
        f"{method}=" + (f"{sum(values) / len(values):.4f}" if values else "undefined")
        for method, values in sorted(ap_by_method.items())
    ) or "undefined"
    leakage = w11_manifest.get("leakage_audit", {})
    leakage_probes = leakage.get("probes", ())
    leakage_failures = [
        probe.get("probe_id")
        for probe in leakage_probes
        if probe.get("status") != "PASS"
    ]
    rows = (
        _gate_row(
            requirement_id="G3-A-PHYSICAL-PLANT",
            requirement="physical plant stable enough",
            canonical_source="docs/04 §27 Gate G3; docs/01; docs/05A",
            owning_team_member="Member A",
            required_evidence=(
                "hardware configuration/calibration, repeatability, valid S1/S2 "
                "runs, electrical qualification and response timing when claimed"
            ),
            actual_file_reference=(
                "evidence/A/W24/acceptance-census.json; evidence/A/W18/"
                "pre-run-safety-checklist.json; reports/W08/gate-b-manifest-W08.json"
            ),
            source_hash_revision=(
                f"A_W24={a_sources['evidence/A/W24/acceptance-census.json']['sha256']}; "
                f"A_W18_CHECKLIST="
                f"{a_sources['evidence/A/W18/pre-run-safety-checklist.json']['sha256']}; "
                f"W08={w08_path['sha256']}"
            ),
            observed_result=(
                f"physical_acceptance_status={a_status}; hardware_posture={a_posture}; "
                f"open_hardware_gates={a_gates}; W08 Gate B={gate_b}; "
                f"eligible real runs={eligible_runs}"
            ),
            evidence_quality="AUTHORITATIVE_A_EVIDENCE + B_GATE_MANIFEST",
            readiness_status=BLOCKED_BY_MISSING_EVIDENCE,
            blocking_reason=(
                f"A physical acceptance is blocked on hardware gates; W08 "
                f"physical data gate is {gate_b} with "
                f"{physical.get('population', 'UNKNOWN')}"
            ),
            next_required_evidence=(
                "A-valid physical plant and run evidence: resolved run/device "
                "identity, verified hardware/calibration/clock, enough independent "
                "S1 and valid S2 runs, and a GREEN Gate B decision"
            ),
            review_authority="Project lead + Member A (physical evidence)",
        ),
        _gate_row(
            requirement_id="G3-B-GROUPED-DATASET",
            requirement="grouped dataset valid",
            canonical_source="docs/04 §27 Gate G3; docs/03 §§47–49, 123",
            owning_team_member="Member B",
            required_evidence=(
                "W08 Gate B, independently valid grouped runs, frozen label "
                "protocol, grouped split and leakage audit"
            ),
            actual_file_reference=(
                "reports/W08/gate-b-manifest-W08.json; "
                "reports/W10/feature-manifest-W10.json; "
                "reports/W11/benchmark-manifest-W11.json"
            ),
            source_hash_revision=(
                f"W08={w08_path['sha256']}; W10={w10_path['sha256']}; "
                f"W11={w11_path['sha256']}"
            ),
            observed_result=(
                f"W08 Gate B={gate_b}; predictive dataset="
                f"{predictive.get('observed_status', 'UNKNOWN')}; split="
                f"{split_gate.get('observed_status', 'UNKNOWN')}; "
                f"eligible S1={real_a.get('eligible_s1_runs')}; "
                f"eligible S2={real_a.get('eligible_s2_runs')}; "
                f"real development={real_w11.get('REAL_DEVELOPMENT_SPLIT')}"
            ),
            evidence_quality="B_GATE_MANIFEST + REAL_A_ADMISSION",
            readiness_status=FAIL_VERIFIED,
            blocking_reason=(
                "no eligible real independent predictive development runs; "
                "only deterministic synthetic software-control data exists"
            ),
            next_required_evidence=(
                "a GREEN Gate B and a real grouped development dataset with "
                "independent run groups, frozen labels and a locked test"
            ),
            review_authority="Project lead + Member B; A for physical validity",
        ),
        _gate_row(
            requirement_id="G3-B-XGB-BENCHMARK",
            requirement="XGBoost has interpretable benchmark",
            canonical_source="docs/04 §27 Gate G3; docs/03 §§52–57, 61–65",
            owning_team_member="Member B",
            required_evidence=(
                "grouped XGBoost evaluation with baselines, leakage audit, "
                "event-level metrics and a real development population"
            ),
            actual_file_reference=(
                "reports/W11/benchmark-manifest-W11.json; "
                "reports/W12/benchmark-synthesis-W12.md; "
                "reports/W12/grouped-metrics-W12.csv"
            ),
            source_hash_revision=(
                f"W11={w11_path['sha256']}; W11_REVISION="
                f"{w11_manifest.get('repository_revision')}; W12 manifest carries "
                "the synthesis artifact hashes"
            ),
            observed_result=(
                "synthetic grouped benchmark only: 8 pair groups, 4 folds; mean "
                f"sample AP by method: {ap_text}; no real benchmark"
            ),
            evidence_quality="SYNTHETIC_SOFTWARE_CONTROL_ONLY",
            readiness_status=BLOCKED_BY_MISSING_EVIDENCE,
            blocking_reason=(
                "synthetic AP cannot establish a physical predictive benchmark; "
                "the real benchmark is NOT_ESTABLISHED"
            ),
            next_required_evidence=(
                "real grouped development data and a leakage-safe real XGBoost "
                "benchmark with event-level operational metrics"
            ),
            review_authority="Project lead + Member B",
        ),
        _gate_row(
            requirement_id="G3-D-CONTROLLER-A",
            requirement="Controller A stable",
            canonical_source="docs/04 §27 Gate G3; docs/02; docs/05D",
            owning_team_member="Member D",
            required_evidence=(
                "committed Controller A policy, thresholds/hysteresis, TTL, "
                "idempotency, ACK behavior, applied-state verification and "
                "physical electrical/thermal verification"
            ),
            actual_file_reference="evidence/D/W01–W03 contracts only; no committed D-W12 evidence",
            source_hash_revision=(
                f"D_W01_W03_CONTRACTS_PRESENT; W12_EVIDENCE=NOT_COMMITTED; "
                f"W08={w08_path['sha256']}"
            ),
            observed_result=(
                "no committed Controller A stability or physical verification "
                "evidence on the W12 parent; open D PRs are not merged"
            ),
            evidence_quality="DESIGN_CONTRACTS_ONLY",
            readiness_status=NOT_VERIFIED,
            blocking_reason="D W12 evidence is absent from the reviewed parent stack",
            next_required_evidence=(
                "D-committed Controller A stability and physical verification "
                "evidence with hash/revision provenance"
            ),
            review_authority="Project lead + Member D",
        ),
        _gate_row(
            requirement_id="G3-D-COMMAND-VERIFY",
            requirement="command verification works",
            canonical_source="docs/04 §27 Gate G3; docs/02 command/ACK/SAFE_LOCAL",
            owning_team_member="Member D",
            required_evidence=(
                "command TTL/idempotency, ACK behavior, applied-state "
                "verification, electrical response and thermal response evidence"
            ),
            actual_file_reference="no committed D W12 command-verification evidence",
            source_hash_revision=(
                f"D_W12_COMMAND_VERIFICATION=NOT_COMMITTED; W08={w08_path['sha256']}"
            ),
            observed_result=(
                f"A dry-run status={a_dry_run.get('status')}, dry_runs="
                f"{a_dry_run.get('dry_runs_recorded')}; A enablement="
                f"{a_checklist.get('enablement_verdict')}; final-freeze schema "
                f"requires {len(a_freeze.get('required_evidence', {}))} open evidence items"
            ),
            evidence_quality="A_PRE_ENERGIZATION_CHECKLIST_ONLY",
            readiness_status=NOT_VERIFIED,
            blocking_reason=(
                "no physical command→ACK→electrical→thermal verification chain is "
                "committed; software policy tests are not physical actuation"
            ),
            next_required_evidence=(
                "D-committed command verification and A-verified electrical/thermal "
                "response on the real plant"
            ),
            review_authority="Project lead + Member D + Member A",
        ),
        _gate_row(
            requirement_id="G3-C-PLATFORM-BACKUP",
            requirement="platform backup/export works",
            canonical_source="docs/04 §27 Gate G3; docs/05C; docs/01 data lineage",
            owning_team_member="Member C",
            required_evidence=(
                "raw export reproducibility, backup/restore, data lineage, "
                "duplicate/replay handling and a platform release signoff"
            ),
            actual_file_reference="no committed C backup/export evidence",
            source_hash_revision="C_W12_BACKUP_EXPORT=NOT_COMMITTED",
            observed_result=(
                "no committed C signoff or operational backup/restore evidence"
            ),
            evidence_quality="MISSING",
            readiness_status=NOT_VERIFIED,
            blocking_reason="C platform evidence is absent; software tests do not prove backup",
            next_required_evidence=(
                "C-committed export/backup/restore and lineage evidence with a "
                "platform release signoff"
            ),
            review_authority="Project lead + Member C",
        ),
        _gate_row(
            requirement_id="G3-B-EWT-AIW",
            requirement="warning timing evidence is interpretable",
            canonical_source="docs/03 §§55–57; docs/05B §40 B-W12-03",
            owning_team_member="Member B",
            required_evidence=(
                "eligible non-intervened physical trajectory with frozen warning/"
                "reactive definitions and measured latency chain"
            ),
            actual_file_reference="reports/W12/ewt-assessment-W12.csv",
            source_hash_revision="W12_MANIFEST_RECORDS_EWT_ASSESSMENT_HASH",
            observed_result=(
                f"REAL_EWT={real_w11.get('REAL_EWT', 'NOT_ESTIMABLE')}; "
                f"REAL_AIW={real_w11.get('REAL_AIW', 'NOT_ESTIMABLE')}"
            ),
            evidence_quality="SOURCE_AUTHORIZED_REFUSAL",
            readiness_status=BLOCKED_BY_MISSING_EVIDENCE,
            blocking_reason=(
                "no eligible physical non-intervened event population and no "
                "measured system/physical latency chain"
            ),
            next_required_evidence=(
                "a valid non-intervened physical event with frozen timing "
                "definitions and a complete measured latency chain"
            ),
            review_authority="Project lead + Member B; A for timing evidence",
        ),
        _gate_row(
            requirement_id="G3-B-LEAKAGE",
            requirement="grouped evaluation is leakage-safe",
            canonical_source="docs/03 §§123–125; docs/04 §27",
            owning_team_member="Member B",
            required_evidence="leakage audit, grouped split and locked-test discipline",
            actual_file_reference="reports/W11/leakage-audit-W11.md",
            source_hash_revision=f"W11={w11_path['sha256']}",
            observed_result=(
                "W11 leakage probes all PASS on the synthetic grouped fixture"
                if not leakage_failures
                else "W11 leakage probes failed: " + ", ".join(leakage_failures)
            ),
            evidence_quality="SOFTWARE_VERIFICATION",
            readiness_status=(
                PASS_VERIFIED if not leakage_failures else FAIL_VERIFIED
            ),
            blocking_reason=(
                ""
                if not leakage_failures
                else "leakage audit failures: " + ", ".join(leakage_failures)
            ),
            next_required_evidence=(
                "none for the synthetic scope; repeat on real data"
                if not leakage_failures
                else "repair the failing leakage probes before any benchmark claim"
            ),
            review_authority="Project lead + Member B",
        ),
        _gate_row(
            requirement_id="G3-TEAM-APPROVAL",
            requirement="team-level Gate G3 approval",
            canonical_source="docs/04 §27 Gate G3",
            owning_team_member="Project lead",
            required_evidence="explicit A/B/C/D review and maintainer authorization",
            actual_file_reference="no approval record committed",
            source_hash_revision="TEAM_APPROVAL=NOT_RECORDED",
            observed_result="approval pending; no signatures or dates are invented",
            evidence_quality="MISSING",
            readiness_status=NOT_VERIFIED,
            blocking_reason="team approval is absent",
            next_required_evidence=(
                "explicit dependency-ordered review and approval by the project "
                "lead and A/C/D owners"
            ),
            review_authority="Project lead",
        ),
    )
    hard_blockers = tuple(
        row.requirement_id
        for row in rows
        if row.requirement_id in HARD_REQUIREMENTS
        and row.readiness_status != PASS_VERIFIED
    )
    decision = NO_GO_FIX_DATA if hard_blockers else GO
    rationale = (
        "A hard physical/data prerequisite is not PASS_VERIFIED; synthetic "
        "software metrics cannot override it.",
        f"W12 software status is {software_status}, but the physical dataset and "
        "grouped real benchmark remain invalid.",
        "GO WITH LIMITATIONS is not available while the physical dataset gate is RED.",
    )
    gate_decision = GateDecision(
        decision=decision,
        hard_blockers=hard_blockers,
        rationale=rationale,
        software_status=software_status,
        physical_status=f"Gate B {gate_b}",
        human_authority="Member B recommendation only; team-lead approval pending",
        permitted_work=(
            "offline engineering work, tests and contract refinement",
            "synthetic software-control experiments clearly labeled as such",
        ),
        forbidden_work=(
            "predictive physical deployment or Controller B actuation",
            "treating synthetic AP as physical predictive evidence",
            "unilateral A/C/D signoff",
        ),
    )
    source_revisions = {
        "w08_manifest": w08_path,
        "w09_manifest": w09_path,
        "w10_manifest": w10_path,
        "w11_manifest": w11_path,
        "a_sources": a_sources,
        "w08_repository_revision": w08_manifest.get("repository_revision"),
        "w09_repository_revision": w09_manifest.get("repository_revision"),
        "w10_repository_revision": w10_manifest.get("repository_revision"),
        "w11_repository_revision": w11_manifest.get("repository_revision"),
    }
    limitations = (
        "The W12 report is Member B's evidence input, not a team approval.",
        "A/C/D evidence not committed to the reviewed parent stays NOT_VERIFIED.",
        "A missing C signoff is not evidence of a working backup.",
        "A D software policy test is not verified physical actuation.",
    )
    return GateReadinessReport(
        schema=G3_SCHEMA,
        rows=rows,
        decision=gate_decision,
        source_revisions=source_revisions,
        limitations=limitations,
    )
