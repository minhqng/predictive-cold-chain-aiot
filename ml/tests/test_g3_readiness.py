"""W12 Gate G3 precedence: software GREEN cannot override physical/data RED."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coldguard_ml.g3_readiness import (
    BLOCKED_BY_MISSING_EVIDENCE,
    FAIL_VERIFIED,
    GO_WITH_LIMITATIONS,
    NO_GO_FIX_DATA,
    NOT_VERIFIED,
    PASS_VERIFIED,
    GateReadinessError,
    build_gate_g3_readiness,
)

REPO = Path(__file__).resolve().parents[2]
ML = REPO / "ml"
W11 = ML / "reports" / "W11" / "benchmark-manifest-W11.json"
W08 = ML / "reports" / "W08" / "gate-b-manifest-W08.json"
W09 = ML / "reports" / "W09" / "baseline-manifest-W09.json"
W10 = ML / "reports" / "W10" / "feature-manifest-W10.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report():
    return build_gate_g3_readiness(
        repo_root=REPO,
        w11_manifest=_json(W11),
        w08_manifest=_json(W08),
        w09_manifest=_json(W09),
        w10_manifest=_json(W10),
        w11_manifest_path=W11,
        w08_manifest_path=W08,
        w09_manifest_path=W09,
        w10_manifest_path=W10,
        software_status="GREEN",
    )


def test_software_green_plus_gate_b_red_yields_no_go(report):
    assert report.decision.software_status == "GREEN"
    assert report.decision.physical_status == "Gate B RED"
    assert report.decision.decision == NO_GO_FIX_DATA
    assert report.decision.decision != GO_WITH_LIMITATIONS


def test_hard_blockers_are_retained_and_reconciled(report):
    rows = {row.requirement_id: row for row in report.rows}
    assert "G3-A-PHYSICAL-PLANT" in report.decision.hard_blockers
    assert "G3-B-GROUPED-DATASET" in report.decision.hard_blockers
    assert "G3-B-XGB-BENCHMARK" in report.decision.hard_blockers
    assert "G3-D-CONTROLLER-A" in report.decision.hard_blockers
    assert "G3-D-COMMAND-VERIFY" in report.decision.hard_blockers
    assert "G3-C-PLATFORM-BACKUP" in report.decision.hard_blockers
    assert rows["G3-A-PHYSICAL-PLANT"].readiness_status != PASS_VERIFIED
    assert rows["G3-A-PHYSICAL-PLANT"].readiness_status == BLOCKED_BY_MISSING_EVIDENCE
    assert rows["G3-B-GROUPED-DATASET"].readiness_status == FAIL_VERIFIED
    assert rows["G3-D-CONTROLLER-A"].readiness_status == NOT_VERIFIED
    assert rows["G3-C-PLATFORM-BACKUP"].readiness_status == NOT_VERIFIED


def test_missing_a_c_d_evidence_cannot_become_pass(report):
    rows = {row.requirement_id: row for row in report.rows}
    assert rows["G3-D-CONTROLLER-A"].readiness_status == NOT_VERIFIED
    assert rows["G3-D-COMMAND-VERIFY"].readiness_status == NOT_VERIFIED
    assert rows["G3-C-PLATFORM-BACKUP"].readiness_status == NOT_VERIFIED
    assert rows["G3-TEAM-APPROVAL"].readiness_status == NOT_VERIFIED


def test_approval_is_not_invented(report):
    row = next(
        item for item in report.rows if item.requirement_id == "G3-TEAM-APPROVAL"
    )
    assert "pending" in row.observed_result.lower()
    assert "NOT_RECORDED" in row.source_hash_revision
    assert "pending" in report.decision.human_authority.lower()


def test_every_row_carries_required_evidence_fields(report):
    for row in report.rows:
        payload = row.to_row()
        for field in (
            "requirement_id",
            "canonical_source",
            "owning_team_member",
            "required_evidence",
            "actual_file_reference",
            "source_hash_revision",
            "observed_result",
            "evidence_quality",
            "readiness_status",
            "blocking_reason",
            "next_required_evidence",
            "review_authority",
        ):
            assert payload[field] is not None
        assert payload["readiness_status"] in {
            PASS_VERIFIED,
            FAIL_VERIFIED,
            BLOCKED_BY_MISSING_EVIDENCE,
            NOT_VERIFIED,
            "NOT_APPLICABLE",
        }


def test_source_bundle_mismatch_is_refused(tmp_path):
    w11 = _json(W11)
    w11["w08_binding"]["sha256"] = "0" * 64
    tampered = tmp_path / "w11.json"
    tampered.write_text(json.dumps(w11), encoding="utf-8")
    with pytest.raises(GateReadinessError, match="does not match"):
        build_gate_g3_readiness(
            repo_root=REPO,
            w11_manifest=w11,
            w08_manifest=_json(W08),
            w09_manifest=_json(W09),
            w10_manifest=_json(W10),
            w11_manifest_path=tampered,
            w08_manifest_path=W08,
            w09_manifest_path=W09,
            w10_manifest_path=W10,
        )
