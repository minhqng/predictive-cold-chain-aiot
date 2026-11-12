"""Tests for Week 24 handover assessment module.

Verifies Doc 05D section 56 compliance:
- D-W24-01: Policy freeze archive (Controller A/B config, policy version, reason codes, freshness, SAFE_LOCAL)
- D-W24-02: Final negative-test smoke (expired, duplicate, unauthorized, SAFE_LOCAL)
- D-W24-03: Another member executes runbook while D observes
- D-W24-04: Final handover completeness

Key invariants tested:
- No destructive tests allowed in W24 smoke matrix
- Executor must be another member (not D)
- Undocumented control assumptions are blocking defects
- Host-validated manifest distinguished from live independent execution
- Final handover NOT complete by default (requires live evidence)
"""

from __future__ import annotations

import pytest

from coldguard_control.handover import (
    FreezeArchiveComponent,
    FreezeArchiveEntry,
    FreezeArchiveAssessment,
    HandoverAuthority,
    HandoverCoverageArea,
    CoverageAreaEntry,
    SmokeTestCase,
    SmokeTestOutcome,
    SmokeTestEvidence,
    SmokeTestAssessment,
    SmokeMatrixDecision,
    RunbookExecutionStatus,
    RunbookExecutionRecord,
    REQUIRED_SMOKE_OUTCOMES,
    assess_freeze_archive,
    assess_smoke_matrix,
    assess_runbook_execution,
    assess_handover_completeness,
    build_default_coverage_areas,
    build_default_freeze_archive,
    build_default_smoke_evidence,
    HandoverCompletenessDecision,
)


class TestHandoverAuthority:
    """Test HandoverAuthority enum values."""

    def test_authority_values(self):
        """Verify both authority levels exist."""
        assert HandoverAuthority.HOST_VALIDATED.value == "HOST_VALIDATED"
        assert HandoverAuthority.LIVE_INDEPENDENT.value == "LIVE_INDEPENDENT"


class TestHandoverCoverageArea:
    """Test HandoverCoverageArea enum completeness."""

    def test_all_required_areas(self):
        """Verify all 13 required coverage areas exist."""
        areas = [area.value for area in HandoverCoverageArea]
        assert "SAFETY_HIERARCHY" in areas
        assert "POLICY_STATE_MACHINE" in areas
        assert "CONTROLLER_A" in areas
        assert "CONTROLLER_B" in areas
        assert "COMMAND_MATRIX" in areas
        assert "VERIFICATION_RULES" in areas
        assert "SAFE_LOCAL" in areas
        assert "THREAT_MODEL" in areas
        assert "SECURITY_CONFIG" in areas
        assert "NEGATIVE_TEST_MATRIX" in areas
        assert "RESILIENCE_EVIDENCE" in areas
        assert "RESIDUAL_RISK_REGISTER" in areas
        assert "DEFENSE_RUNBOOK" in areas
        assert len(HandoverCoverageArea) == 13


class TestFreezeArchiveComponent:
    """Test FreezeArchiveComponent enum."""

    def test_all_components(self):
        """Verify all 6 freeze archive components."""
        components = [comp.value for comp in FreezeArchiveComponent]
        assert "CONTROLLER_A_CONFIG" in components
        assert "CONTROLLER_B_CONFIG" in components
        assert "POLICY_VERSION" in components
        assert "REASON_CODES" in components
        assert "FRESHNESS" in components
        assert "SAFE_LOCAL" in components
        assert len(FreezeArchiveComponent) == 6


class TestSmokeTestCase:
    """Test SmokeTestCase enum."""

    def test_all_smoke_cases(self):
        """Verify all 4 non-destructive smoke test cases."""
        cases = [case.value for case in SmokeTestCase]
        assert "EXPIRED_COMMAND" in cases
        assert "DUPLICATE_COMMAND" in cases
        assert "UNAUTHORIZED_COMMAND" in cases
        assert "SAFE_LOCAL_TRANSITION" in cases
        assert len(SmokeTestCase) == 4


class TestRequiredSmokeOutcomes:
    """Test REQUIRED_SMOKE_OUTCOMES mapping."""

    def test_expired_command_outcomes(self):
        """Expired command requires REJECTED + NO_ACTUATION + AUDIT_EVENT."""
        outcomes = REQUIRED_SMOKE_OUTCOMES[SmokeTestCase.EXPIRED_COMMAND]
        assert SmokeTestOutcome.REJECTED in outcomes
        assert SmokeTestOutcome.NO_ACTUATION in outcomes
        assert SmokeTestOutcome.AUDIT_EVENT in outcomes

    def test_duplicate_command_outcomes(self):
        """Duplicate command requires NO_DUPLICATE_EFFECT."""
        outcomes = REQUIRED_SMOKE_OUTCOMES[SmokeTestCase.DUPLICATE_COMMAND]
        assert SmokeTestOutcome.NO_DUPLICATE_EFFECT in outcomes
        assert len(outcomes) == 1

    def test_unauthorized_command_outcomes(self):
        """Unauthorized command requires ACL_DENIED + NO_ACTUATION."""
        outcomes = REQUIRED_SMOKE_OUTCOMES[SmokeTestCase.UNAUTHORIZED_COMMAND]
        assert SmokeTestOutcome.ACL_DENIED in outcomes
        assert SmokeTestOutcome.NO_ACTUATION in outcomes

    def test_safe_local_outcomes(self):
        """SAFE_LOCAL requires MODE_TRANSITION + LOCAL_PROTECTION_ACTIVE."""
        outcomes = REQUIRED_SMOKE_OUTCOMES[SmokeTestCase.SAFE_LOCAL_TRANSITION]
        assert SmokeTestOutcome.MODE_TRANSITION in outcomes
        assert SmokeTestOutcome.LOCAL_PROTECTION_ACTIVE in outcomes


class TestFreezeArchiveEntry:
    """Test FreezeArchiveEntry dataclass."""

    def test_valid_entry(self):
        """Valid entry with all fields."""
        entry = FreezeArchiveEntry(
            component=FreezeArchiveComponent.CONTROLLER_A_CONFIG,
            version="v1.0.0-W24",
            authority=HandoverAuthority.HOST_VALIDATED,
            checksum_sha256="abc123",
            location_path="evidence/D/W24/controller_a_config.json",
        )
        assert entry.component == FreezeArchiveComponent.CONTROLLER_A_CONFIG
        assert entry.version == "v1.0.0-W24"
        assert entry.authority == HandoverAuthority.HOST_VALIDATED

    def test_entry_without_optional_fields(self):
        """Entry without checksum/location is valid."""
        entry = FreezeArchiveEntry(
            component=FreezeArchiveComponent.POLICY_VERSION,
            version="v1.0.0",
            authority=HandoverAuthority.LIVE_INDEPENDENT,
        )
        assert entry.checksum_sha256 is None
        assert entry.location_path is None

    def test_invalid_component_type(self):
        """Component must be FreezeArchiveComponent."""
        with pytest.raises(TypeError, match="component must be"):
            FreezeArchiveEntry(
                component="INVALID",
                version="v1",
                authority=HandoverAuthority.HOST_VALIDATED,
            )

    def test_empty_version(self):
        """Version must be nonempty."""
        with pytest.raises(ValueError, match="version must be nonempty"):
            FreezeArchiveEntry(
                component=FreezeArchiveComponent.POLICY_VERSION,
                version="",
                authority=HandoverAuthority.HOST_VALIDATED,
            )

    def test_invalid_authority_type(self):
        """Authority must be HandoverAuthority."""
        with pytest.raises(TypeError, match="authority must be"):
            FreezeArchiveEntry(
                component=FreezeArchiveComponent.POLICY_VERSION,
                version="v1",
                authority="HOST",
            )


class TestSmokeTestEvidence:
    """Test SmokeTestEvidence dataclass."""

    def test_valid_evidence(self):
        """Valid smoke test evidence."""
        evidence = SmokeTestEvidence(
            test_case=SmokeTestCase.EXPIRED_COMMAND,
            authority=HandoverAuthority.HOST_VALIDATED,
            observed_outcomes=frozenset({
                SmokeTestOutcome.REJECTED,
                SmokeTestOutcome.NO_ACTUATION,
                SmokeTestOutcome.AUDIT_EVENT,
            }),
        )
        assert evidence.test_case == SmokeTestCase.EXPIRED_COMMAND
        assert evidence.destructive is False

    def test_destructive_not_allowed(self):
        """Destructive tests are forbidden in W24."""
        with pytest.raises(ValueError, match="destructive tests are not allowed"):
            SmokeTestEvidence(
                test_case=SmokeTestCase.EXPIRED_COMMAND,
                authority=HandoverAuthority.HOST_VALIDATED,
                observed_outcomes=frozenset(),
                destructive=True,
            )

    def test_invalid_test_case_type(self):
        """Test case must be SmokeTestCase."""
        with pytest.raises(TypeError, match="test_case must be"):
            SmokeTestEvidence(
                test_case="INVALID",
                authority=HandoverAuthority.HOST_VALIDATED,
                observed_outcomes=frozenset(),
            )


class TestRunbookExecutionRecord:
    """Test RunbookExecutionRecord dataclass."""

    def test_valid_record_member_a(self):
        """Valid record with member A as executor."""
        record = RunbookExecutionRecord(
            executor_member="A",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
        )
        assert record.executor_member == "A"
        assert record.status == RunbookExecutionStatus.COMPLETED_OBSERVED

    def test_executor_cannot_be_d(self):
        """Executor must be another member, not D."""
        with pytest.raises(ValueError, match="executor must be member A, B, or C"):
            RunbookExecutionRecord(
                executor_member="D",
                status=RunbookExecutionStatus.COMPLETED_OBSERVED,
                observer_member="D",
            )

    def test_executor_must_be_known_team_member(self):
        with pytest.raises(ValueError, match="executor must be member A, B, or C"):
            RunbookExecutionRecord(
                executor_member="X",
                status=RunbookExecutionStatus.NOT_STARTED,
            )

    def test_undocumented_assumptions_tuple(self):
        """Undocumented assumptions stored as tuple."""
        record = RunbookExecutionRecord(
            executor_member="B",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
            undocumented_assumptions=("threshold source unclear",),
        )
        assert len(record.undocumented_assumptions) == 1

    def test_blocking_defects_tuple(self):
        """Blocking defects stored as tuple."""
        record = RunbookExecutionRecord(
            executor_member="C",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
            blocking_defects=("SAFE_LOCAL exit condition missing",),
        )
        assert len(record.blocking_defects) == 1


class TestCoverageAreaEntry:
    """Test CoverageAreaEntry dataclass."""

    def test_valid_entry(self):
        """Valid coverage area entry."""
        entry = CoverageAreaEntry(
            area=HandoverCoverageArea.SAFETY_HIERARCHY,
            documented=True,
            evidence_authority=HandoverAuthority.LIVE_INDEPENDENT,
            location_path="evidence/D/W01/safety-hierarchy.md",
        )
        assert entry.area == HandoverCoverageArea.SAFETY_HIERARCHY
        assert entry.documented is True

    def test_undocumented_area(self):
        """Entry can be undocumented."""
        entry = CoverageAreaEntry(
            area=HandoverCoverageArea.THREAT_MODEL,
            documented=False,
            evidence_authority=HandoverAuthority.HOST_VALIDATED,
        )
        assert entry.documented is False

    def test_invalid_area_type(self):
        """Area must be HandoverCoverageArea."""
        with pytest.raises(TypeError, match="area must be"):
            CoverageAreaEntry(
                area="INVALID",
                documented=True,
                evidence_authority=HandoverAuthority.HOST_VALIDATED,
            )

    def test_documented_must_be_bool(self):
        """Documented must be strict boolean."""
        with pytest.raises(TypeError, match="documented must be a strict boolean"):
            CoverageAreaEntry(
                area=HandoverCoverageArea.SAFETY_HIERARCHY,
                documented="yes",
                evidence_authority=HandoverAuthority.HOST_VALIDATED,
            )


class TestAssessFreezeArchive:
    """Test assess_freeze_archive function."""

    def test_complete_archive(self):
        """All components present."""
        entries = build_default_freeze_archive()
        result = assess_freeze_archive(entries)
        assert result.all_components_present is True
        assert len(result.missing_components) == 0
        assert result.has_live_independent is False

    def test_missing_components(self):
        """Missing components detected."""
        entries = [
            FreezeArchiveEntry(
                component=FreezeArchiveComponent.CONTROLLER_A_CONFIG,
                version="v1",
                authority=HandoverAuthority.HOST_VALIDATED,
            ),
        ]
        result = assess_freeze_archive(entries)
        assert result.all_components_present is False
        assert len(result.missing_components) == 5

    def test_live_independent_evidence(self):
        """Live independent evidence detected."""
        entries = build_default_freeze_archive(
            authority=HandoverAuthority.LIVE_INDEPENDENT
        )
        result = assess_freeze_archive(entries)
        assert result.has_live_independent is True

    def test_duplicate_component_rejected(self):
        """Duplicate component raises error."""
        entries = [
            FreezeArchiveEntry(
                component=FreezeArchiveComponent.POLICY_VERSION,
                version="v1",
                authority=HandoverAuthority.HOST_VALIDATED,
            ),
            FreezeArchiveEntry(
                component=FreezeArchiveComponent.POLICY_VERSION,
                version="v2",
                authority=HandoverAuthority.HOST_VALIDATED,
            ),
        ]
        with pytest.raises(ValueError, match="duplicate component"):
            assess_freeze_archive(entries)

    def test_invalid_input_type(self):
        """Invalid input type raises TypeError."""
        with pytest.raises(TypeError, match="entries must be a Sequence"):
            assess_freeze_archive("invalid")


class TestAssessSmokeMatrix:
    """Test assess_smoke_matrix function."""

    def test_complete_smoke_matrix(self):
        """All smoke cases pass."""
        evidence = build_default_smoke_evidence()
        result = assess_smoke_matrix(evidence)
        assert result.all_cases_pass is True
        assert len(result.missing_cases) == 0
        assert len(result.failed_cases) == 0

    def test_missing_cases(self):
        """Missing cases detected."""
        evidence = [
            SmokeTestEvidence(
                test_case=SmokeTestCase.EXPIRED_COMMAND,
                authority=HandoverAuthority.HOST_VALIDATED,
                observed_outcomes=REQUIRED_SMOKE_OUTCOMES[SmokeTestCase.EXPIRED_COMMAND],
            ),
        ]
        result = assess_smoke_matrix(evidence)
        assert result.all_cases_pass is False
        assert len(result.missing_cases) == 3

    def test_missing_outcomes(self):
        """Missing outcomes detected."""
        evidence = [
            SmokeTestEvidence(
                test_case=SmokeTestCase.EXPIRED_COMMAND,
                authority=HandoverAuthority.HOST_VALIDATED,
                observed_outcomes=frozenset({SmokeTestOutcome.REJECTED}),
            ),
        ]
        result = assess_smoke_matrix(evidence)
        assert result.all_cases_pass is False
        assert len(result.failed_cases) == 1

    def test_no_destructive_tests(self):
        """Destructive tests rejected at construction."""
        with pytest.raises(ValueError, match="destructive tests are not allowed"):
            SmokeTestEvidence(
                test_case=SmokeTestCase.EXPIRED_COMMAND,
                authority=HandoverAuthority.HOST_VALIDATED,
                observed_outcomes=REQUIRED_SMOKE_OUTCOMES[SmokeTestCase.EXPIRED_COMMAND],
                destructive=True,
            )

    def test_live_independent_evidence(self):
        """Live independent evidence tracked."""
        evidence = build_default_smoke_evidence(
            authority=HandoverAuthority.LIVE_INDEPENDENT
        )
        result = assess_smoke_matrix(evidence)
        assert result.has_live_independent is True


class TestAssessRunbookExecution:
    """Test assess_runbook_execution function."""

    def test_completed_observed_valid(self):
        """Completed observed with D as observer is valid."""
        record = RunbookExecutionRecord(
            executor_member="A",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
        )
        result = assess_runbook_execution(record)
        assert result.status == RunbookExecutionStatus.COMPLETED_OBSERVED

    def test_blocking_defects_raise(self):
        """Blocking defects raise ValueError."""
        record = RunbookExecutionRecord(
            executor_member="B",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
            blocking_defects=("Undocumented assumption",),
        )
        with pytest.raises(ValueError, match="blocking defects"):
            assess_runbook_execution(record)

    def test_observer_must_be_d(self):
        """Observer must be D for COMPLETED_OBSERVED."""
        record = RunbookExecutionRecord(
            executor_member="C",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="A",
        )
        with pytest.raises(ValueError, match="observer must be D"):
            assess_runbook_execution(record)

    def test_not_started_valid(self):
        """NOT_STARTED status is valid (just not complete)."""
        record = RunbookExecutionRecord(
            executor_member="A",
            status=RunbookExecutionStatus.NOT_STARTED,
        )
        result = assess_runbook_execution(record)
        assert result.status == RunbookExecutionStatus.NOT_STARTED


class TestAssessHandoverCompleteness:
    """Test assess_handover_completeness function."""

    def test_complete_handover_host_only(self):
        """Host-only handover is NOT complete (requires live evidence)."""
        freeze = assess_freeze_archive(build_default_freeze_archive())
        smoke = assess_smoke_matrix(build_default_smoke_evidence())
        runbook = RunbookExecutionRecord(
            executor_member="A",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
        )
        coverage = build_default_coverage_areas()

        result = assess_handover_completeness(
            freeze_archive=freeze,
            smoke_matrix=smoke,
            runbook_execution=runbook,
            coverage_areas=coverage,
        )

        assert result.freeze_archive_complete is True
        assert result.smoke_matrix_complete is True
        assert result.runbook_execution_valid is True
        assert result.all_coverage_documented is True
        assert result.no_blocking_defects is True
        assert result.live_independent_evidence is False
        assert result.handover_complete is False
        assert "NO_LIVE_INDEPENDENT_EVIDENCE" in result.blockers

    def test_complete_handover_with_live_evidence(self):
        """Handover complete with live independent evidence."""
        freeze = assess_freeze_archive(
            build_default_freeze_archive(authority=HandoverAuthority.LIVE_INDEPENDENT)
        )
        smoke = assess_smoke_matrix(
            build_default_smoke_evidence(authority=HandoverAuthority.LIVE_INDEPENDENT)
        )
        runbook = RunbookExecutionRecord(
            executor_member="A",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            authority=HandoverAuthority.LIVE_INDEPENDENT,
            observer_member="D",
        )
        coverage = build_default_coverage_areas(
            authority=HandoverAuthority.LIVE_INDEPENDENT
        )

        result = assess_handover_completeness(
            freeze_archive=freeze,
            smoke_matrix=smoke,
            runbook_execution=runbook,
            coverage_areas=coverage,
        )

        assert result.handover_complete is True
        assert result.live_independent_evidence is True
        assert result.blockers == ()

    def test_missing_freeze_archive(self):
        """Missing freeze archive blocks completion."""
        smoke = assess_smoke_matrix(build_default_smoke_evidence())
        runbook = RunbookExecutionRecord(
            executor_member="B",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
        )
        coverage = build_default_coverage_areas()

        result = assess_handover_completeness(
            freeze_archive=None,
            smoke_matrix=smoke,
            runbook_execution=runbook,
            coverage_areas=coverage,
        )

        assert result.freeze_archive_complete is False
        assert result.handover_complete is False
        assert "FREEZE_ARCHIVE_NOT_ASSESSED" in result.blockers

    def test_undocumented_coverage_area(self):
        """Undocumented coverage area blocks completion."""
        freeze = assess_freeze_archive(build_default_freeze_archive())
        smoke = assess_smoke_matrix(build_default_smoke_evidence())
        runbook = RunbookExecutionRecord(
            executor_member="C",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
        )
        coverage = (
            CoverageAreaEntry(
                area=HandoverCoverageArea.SAFETY_HIERARCHY,
                documented=True,
                evidence_authority=HandoverAuthority.HOST_VALIDATED,
            ),
            CoverageAreaEntry(
                area=HandoverCoverageArea.THREAT_MODEL,
                documented=False,
                evidence_authority=HandoverAuthority.HOST_VALIDATED,
            ),
        )

        result = assess_handover_completeness(
            freeze_archive=freeze,
            smoke_matrix=smoke,
            runbook_execution=runbook,
            coverage_areas=coverage,
        )

        assert result.all_coverage_documented is False
        assert result.handover_complete is False
        assert "UNDOCUMENTED_AREA:THREAT_MODEL" in result.blockers

    def test_blocking_defects_block_completion(self):
        """Blocking defects prevent completion."""
        freeze = assess_freeze_archive(build_default_freeze_archive())
        smoke = assess_smoke_matrix(build_default_smoke_evidence())
        runbook = RunbookExecutionRecord(
            executor_member="A",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
            blocking_defects=("SAFE_LOCAL exit condition undocumented",),
        )
        coverage = build_default_coverage_areas()

        result = assess_handover_completeness(
            freeze_archive=freeze,
            smoke_matrix=smoke,
            runbook_execution=runbook,
            coverage_areas=coverage,
        )

        assert result.no_blocking_defects is False
        assert result.handover_complete is False
        assert "BLOCKING_DEFECT:SAFE_LOCAL exit condition undocumented" in result.blockers

    def test_invalid_coverage_areas_type(self):
        """Invalid coverage areas type raises TypeError."""
        with pytest.raises(TypeError, match="coverage_areas must be a Sequence"):
            assess_handover_completeness(
                freeze_archive=None,
                smoke_matrix=None,
                runbook_execution=None,
                coverage_areas="invalid",
            )

    def test_missing_coverage_areas_cannot_pass_vacuously(self):
        freeze = assess_freeze_archive(build_default_freeze_archive())
        smoke = assess_smoke_matrix(build_default_smoke_evidence())
        runbook = RunbookExecutionRecord(
            executor_member="A",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            authority=HandoverAuthority.LIVE_INDEPENDENT,
            observer_member="D",
        )
        result = assess_handover_completeness(freeze, smoke, runbook, [])
        assert result.all_coverage_documented is False
        assert result.handover_complete is False
        assert any(
            blocker.startswith("MISSING_COVERAGE_AREA:")
            for blocker in result.blockers
        )

    def test_duplicate_coverage_area_is_rejected(self):
        area = build_default_coverage_areas()[0]
        with pytest.raises(ValueError, match="duplicate coverage area"):
            assess_handover_completeness(None, None, None, [area, area])


class TestBuildDefaultHelpers:
    """Test helper functions for building default structures."""

    def test_build_default_coverage_areas(self):
        """Build all 13 coverage areas."""
        areas = build_default_coverage_areas()
        assert len(areas) == 13
        assert all(area.documented is True for area in areas)
        assert all(
            area.evidence_authority == HandoverAuthority.HOST_VALIDATED
            for area in areas
        )

    def test_build_default_freeze_archive(self):
        """Build all 6 freeze archive components."""
        entries = build_default_freeze_archive()
        assert len(entries) == 6
        assert all(entry.version == "v1.0.0-W24" for entry in entries)

    def test_build_default_smoke_evidence(self):
        """Build all 4 smoke test cases."""
        evidence = build_default_smoke_evidence()
        assert len(evidence) == 4
        assert all(e.destructive is False for e in evidence)


class TestDoc05DSection56Compliance:
    """Test compliance with Doc 05D section 56 requirements."""

    def test_d_w24_01_policy_freeze_archive(self):
        """D-W24-01: Policy freeze archive components."""
        entries = build_default_freeze_archive()
        components = {e.component for e in entries}
        assert FreezeArchiveComponent.CONTROLLER_A_CONFIG in components
        assert FreezeArchiveComponent.CONTROLLER_B_CONFIG in components
        assert FreezeArchiveComponent.POLICY_VERSION in components
        assert FreezeArchiveComponent.REASON_CODES in components
        assert FreezeArchiveComponent.FRESHNESS in components
        assert FreezeArchiveComponent.SAFE_LOCAL in components

    def test_d_w24_02_smoke_matrix_cases(self):
        """D-W24-02: Non-destructive smoke matrix cases."""
        evidence = build_default_smoke_evidence()
        cases = {e.test_case for e in evidence}
        assert SmokeTestCase.EXPIRED_COMMAND in cases
        assert SmokeTestCase.DUPLICATE_COMMAND in cases
        assert SmokeTestCase.UNAUTHORIZED_COMMAND in cases
        assert SmokeTestCase.SAFE_LOCAL_TRANSITION in cases
        assert all(e.destructive is False for e in evidence)

    def test_d_w24_03_another_member_executes(self):
        """D-W24-03: Another member (not D) executes runbook."""
        for member in ["A", "B", "C"]:
            record = RunbookExecutionRecord(
                executor_member=member,
                status=RunbookExecutionStatus.COMPLETED_OBSERVED,
                observer_member="D",
            )
            assert record.executor_member != "D"
            assert record.observer_member == "D"

    def test_d_w24_04_handover_coverage_areas(self):
        """D-W24-04: All 13 handover coverage areas."""
        areas = build_default_coverage_areas()
        area_values = {a.area.value for a in areas}
        required = {
            "SAFETY_HIERARCHY",
            "POLICY_STATE_MACHINE",
            "CONTROLLER_A",
            "CONTROLLER_B",
            "COMMAND_MATRIX",
            "VERIFICATION_RULES",
            "SAFE_LOCAL",
            "THREAT_MODEL",
            "SECURITY_CONFIG",
            "NEGATIVE_TEST_MATRIX",
            "RESILIENCE_EVIDENCE",
            "RESIDUAL_RISK_REGISTER",
            "DEFENSE_RUNBOOK",
        }
        assert area_values == required

    def test_host_vs_live_distinction(self):
        """Host-validated manifest distinguished from live independent execution."""
        host_entries = build_default_freeze_archive(
            authority=HandoverAuthority.HOST_VALIDATED
        )
        live_entries = build_default_freeze_archive(
            authority=HandoverAuthority.LIVE_INDEPENDENT
        )

        host_result = assess_freeze_archive(host_entries)
        live_result = assess_freeze_archive(live_entries)

        assert host_result.has_live_independent is False
        assert live_result.has_live_independent is True

    def test_handover_not_complete_by_default(self):
        """Final handover NOT complete by default (requires live evidence)."""
        freeze = assess_freeze_archive(build_default_freeze_archive())
        smoke = assess_smoke_matrix(build_default_smoke_evidence())
        runbook = RunbookExecutionRecord(
            executor_member="A",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            observer_member="D",
        )
        coverage = build_default_coverage_areas()

        result = assess_handover_completeness(
            freeze_archive=freeze,
            smoke_matrix=smoke,
            runbook_execution=runbook,
            coverage_areas=coverage,
        )

        assert result.handover_complete is False
        assert "NO_LIVE_INDEPENDENT_EVIDENCE" in result.blockers

    def test_undocumented_assumption_is_blocking(self):
        """Undocumented control assumption is a blocking defect."""
        runbook = RunbookExecutionRecord(
            executor_member="B",
            status=RunbookExecutionStatus.COMPLETED_OBSERVED,
            authority=HandoverAuthority.LIVE_INDEPENDENT,
            observer_member="D",
            undocumented_assumptions=("Controller B threshold source undocumented",),
        )

        freeze = assess_freeze_archive(build_default_freeze_archive())
        smoke = assess_smoke_matrix(build_default_smoke_evidence())
        coverage = build_default_coverage_areas()

        result = assess_handover_completeness(
            freeze_archive=freeze,
            smoke_matrix=smoke,
            runbook_execution=runbook,
            coverage_areas=coverage,
        )

        assert result.handover_complete is False
        assert result.no_blocking_defects is False
        assert any(
            blocker.startswith("UNDOCUMENTED_ASSUMPTION:")
            for blocker in result.blockers
        )
