"""Tests for synthetic report/demo evidence validator (Member D W14-W24).

Verifies SYNTHETIC_DEMO_ONLY constraints:
- Never claims physical execution, live evidence, gate signoff, or final acceptance
- Validates exact week coverage W14 through W24 (11 weeks)
- Rejects duplicate or missing weeks
- Rejects any fixture combining synthetic authority with live/physical/signoff claims
- No invented real measurements or engineering thresholds
"""

from __future__ import annotations

import pytest

from coldguard_control.report_demo import (
    ReportDemoAuthority,
    WeekCoverageStatus,
    WeeklySyntheticEntry,
    SyntheticReportFixture,
    WeekCoverageAssessment,
    SyntheticReportSummary,
    REQUIRED_WEEKS,
    validate_weekly_entry,
    validate_synthetic_fixture,
    assess_week_coverage,
    assess_synthetic_report,
    build_default_synthetic_fixture,
    build_synthetic_fixture_from_json,
)


class TestReportDemoAuthority:
    """Test ReportDemoAuthority enum values."""
    
    def test_authority_values(self):
        """Verify both authority levels are synthetic-only."""
        assert ReportDemoAuthority.SYNTHETIC_DEMO.value == "SYNTHETIC_DEMO"
        assert ReportDemoAuthority.HOST_SIMULATION.value == "HOST_SIMULATION"
    
    def test_no_live_authority(self):
        """Verify no live/physical authority exists."""
        values = [a.value for a in ReportDemoAuthority]
        assert "LIVE_INDEPENDENT" not in values
        assert "PHYSICAL_EXECUTION" not in values
        assert "GATE_SIGNOFF" not in values
        assert "FINAL_ACCEPTANCE" not in values


class TestRequiredWeeks:
    """Test REQUIRED_WEEKS constant."""
    
    def test_week_range(self):
        """Verify weeks 14-24 are required."""
        assert 14 in REQUIRED_WEEKS
        assert 24 in REQUIRED_WEEKS
        assert len(REQUIRED_WEEKS) == 11
        assert REQUIRED_WEEKS == frozenset(range(14, 25))


class TestWeeklySyntheticEntry:
    """Test WeeklySyntheticEntry dataclass."""
    
    def test_valid_entry(self):
        """Valid synthetic entry for W14."""
        entry = WeeklySyntheticEntry(
            week=14,
            implementation_complete=True,
            host_validation_passed=True,
            live_validation_complete=False,
            final_acceptance=False,
            authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            notes="Synthetic demo for W14",
        )
        assert entry.week == 14
        assert entry.implementation_complete is True
        assert entry.host_validation_passed is True
        assert entry.live_validation_complete is False
        assert entry.final_acceptance is False
    
    def test_entry_without_notes(self):
        """Entry without notes is valid."""
        entry = WeeklySyntheticEntry(
            week=20,
            implementation_complete=True,
            host_validation_passed=True,
            live_validation_complete=False,
            final_acceptance=False,
            authority=ReportDemoAuthority.HOST_SIMULATION,
        )
        assert entry.notes is None
    
    def test_week_must_be_in_range(self):
        """Week must be between 14 and 24."""
        with pytest.raises(ValueError, match="week must be between 14 and 24"):
            WeeklySyntheticEntry(
                week=13,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            )
        
        with pytest.raises(ValueError, match="week must be between 14 and 24"):
            WeeklySyntheticEntry(
                week=25,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            )
    
    def test_live_validation_must_be_false(self):
        """SYNTHETIC_DEMO_ONLY: live_validation_complete must be False."""
        with pytest.raises(ValueError, match="SYNTHETIC_DEMO_ONLY.*live_validation_complete must be False"):
            WeeklySyntheticEntry(
                week=18,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=True,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            )
    
    def test_final_acceptance_must_be_false(self):
        """SYNTHETIC_DEMO_ONLY: final_acceptance must be False."""
        with pytest.raises(ValueError, match="SYNTHETIC_DEMO_ONLY.*final_acceptance must be False"):
            WeeklySyntheticEntry(
                week=22,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=True,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            )
    
    def test_notes_cannot_claim_physical(self):
        """Notes cannot claim physical or live execution."""
        with pytest.raises(ValueError, match="SYNTHETIC_DEMO_ONLY.*notes cannot claim physical"):
            WeeklySyntheticEntry(
                week=16,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
                notes="PHYSICAL test completed",
            )
    
    def test_notes_cannot_claim_signoff(self):
        """Notes cannot claim signoff or acceptance."""
        with pytest.raises(ValueError, match="SYNTHETIC_DEMO_ONLY.*notes cannot claim signoff"):
            WeeklySyntheticEntry(
                week=19,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
                notes="Gate signoff received",
            )
    
    def test_implementation_complete_must_be_bool(self):
        """implementation_complete must be strict boolean."""
        with pytest.raises(TypeError, match="implementation_complete must be a strict boolean"):
            WeeklySyntheticEntry(
                week=17,
                implementation_complete="yes",
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            )
    
    def test_week_must_be_int(self):
        """Week must be integer."""
        with pytest.raises(TypeError, match="week must be an integer"):
            WeeklySyntheticEntry(
                week="14",
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            )

        with pytest.raises(TypeError, match="week must be an integer"):
            WeeklySyntheticEntry(
                week=True,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            )


class TestSyntheticReportFixture:
    """Test SyntheticReportFixture dataclass."""
    
    def test_valid_fixture(self):
        """Valid synthetic fixture."""
        entries = (
            WeeklySyntheticEntry(
                week=14,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            ),
        )
        fixture = SyntheticReportFixture(
            entries=entries,
            authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            description="Synthetic report for W14",
        )
        assert len(fixture.entries) == 1
        assert fixture.authority == ReportDemoAuthority.SYNTHETIC_DEMO
    
    def test_description_cannot_claim_physical(self):
        """Description cannot claim physical or live execution."""
        entries = (
            WeeklySyntheticEntry(
                week=14,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            ),
        )
        with pytest.raises(ValueError, match="SYNTHETIC_DEMO_ONLY.*description cannot claim physical"):
            SyntheticReportFixture(
                entries=entries,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
                description="LIVE physical execution evidence",
            )
    
    def test_entries_must_be_tuple(self):
        """Entries must be a tuple."""
        with pytest.raises(TypeError, match="entries must be a tuple"):
            SyntheticReportFixture(
                entries=[],
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
                description="Test",
            )


class TestValidateWeeklyEntry:
    """Test validate_weekly_entry function."""
    
    def test_valid_entry(self):
        """Valid entry passes validation."""
        entry = WeeklySyntheticEntry(
            week=15,
            implementation_complete=True,
            host_validation_passed=True,
            live_validation_complete=False,
            final_acceptance=False,
            authority=ReportDemoAuthority.SYNTHETIC_DEMO,
        )
        result = validate_weekly_entry(entry)
        assert result is entry
    
    def test_invalid_type(self):
        """Invalid type raises TypeError."""
        with pytest.raises(TypeError, match="entry must be a WeeklySyntheticEntry"):
            validate_weekly_entry("invalid")


class TestValidateSyntheticFixture:
    """Test validate_synthetic_fixture function."""
    
    def test_valid_fixture(self):
        """Valid fixture passes validation."""
        fixture = build_default_synthetic_fixture()
        result = validate_synthetic_fixture(fixture)
        assert result is fixture
    
    def test_invalid_type(self):
        """Invalid type raises TypeError."""
        with pytest.raises(TypeError, match="fixture must be a SyntheticReportFixture"):
            validate_synthetic_fixture("invalid")


class TestAssessWeekCoverage:
    """Test assess_week_coverage function."""
    
    def test_complete_coverage(self):
        """All 11 weeks W14-W24 present."""
        entries = tuple(
            WeeklySyntheticEntry(
                week=week,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            )
            for week in range(14, 25)
        )
        result = assess_week_coverage(entries)
        assert result.all_weeks_present is True
        assert result.no_duplicates is True
        assert result.valid is True
        assert len(result.blockers) == 0
        assert len(result.weeks_covered) == 11
    
    def test_missing_weeks(self):
        """Missing weeks detected."""
        entries = (
            WeeklySyntheticEntry(
                week=14,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            ),
            WeeklySyntheticEntry(
                week=16,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            ),
        )
        result = assess_week_coverage(entries)
        assert result.all_weeks_present is False
        assert 15 in result.missing_weeks
        assert 17 in result.missing_weeks
        assert result.valid is False
        assert any(b.startswith("MISSING_WEEK:") for b in result.blockers)
    
    def test_duplicate_weeks(self):
        """Duplicate weeks detected."""
        entries = (
            WeeklySyntheticEntry(
                week=14,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            ),
            WeeklySyntheticEntry(
                week=14,
                implementation_complete=True,
                host_validation_passed=True,
                live_validation_complete=False,
                final_acceptance=False,
                authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            ),
        )
        result = assess_week_coverage(entries)
        assert result.no_duplicates is False
        assert 14 in result.duplicate_weeks
        assert result.valid is False
        assert any(b.startswith("DUPLICATE_WEEK:") for b in result.blockers)
    
    def test_invalid_input_type(self):
        """Invalid input type raises TypeError."""
        with pytest.raises(TypeError, match="entries must be a Sequence"):
            assess_week_coverage("invalid")


class TestAssessSyntheticReport:
    """Test assess_synthetic_report function."""
    
    def test_none_fixture(self):
        """None fixture returns empty summary."""
        result = assess_synthetic_report(None)
        assert result.fixture is None
        assert result.valid is False
        assert "NO_FIXTURE_PROVIDED" in result.blockers
    
    def test_complete_fixture(self):
        """Complete W14-W24 fixture validates."""
        fixture = build_default_synthetic_fixture()
        result = assess_synthetic_report(fixture)
        assert result.valid is True
        assert result.total_weeks == 11
        assert result.expected_weeks == 11
        assert result.implementation_complete_count == 11
        assert result.host_validation_passed_count == 11
        assert result.live_validation_complete_count == 0
        assert result.final_acceptance_count == 0
        assert result.all_synthetic is True
        assert "SYNTHETIC_DEMO_ONLY" in result.summary_text
    
    def test_summary_text_format(self):
        """Summary text contains required information."""
        fixture = build_default_synthetic_fixture()
        result = assess_synthetic_report(fixture)
        assert "SYNTHETIC REPORT/DEMO EVIDENCE PACK" in result.summary_text
        assert "Member D W14-W24" in result.summary_text
        assert "SYNTHETIC_DEMO_ONLY" in result.summary_text
        assert "MUST BE 0" in result.summary_text
    
    def test_invalid_fixture_type(self):
        """Invalid fixture type raises TypeError."""
        with pytest.raises(TypeError, match="fixture must be a SyntheticReportFixture"):
            assess_synthetic_report("invalid")


class TestBuildDefaultSyntheticFixture:
    """Test build_default_synthetic_fixture function."""
    
    def test_default_fixture(self):
        """Default fixture covers W14-W24."""
        fixture = build_default_synthetic_fixture()
        assert len(fixture.entries) == 11
        assert fixture.authority == ReportDemoAuthority.SYNTHETIC_DEMO
        assert all(e.implementation_complete for e in fixture.entries)
        assert all(e.host_validation_passed for e in fixture.entries)
        assert all(not e.live_validation_complete for e in fixture.entries)
        assert all(not e.final_acceptance for e in fixture.entries)
    
    def test_host_simulation_authority(self):
        """Can build with HOST_SIMULATION authority."""
        fixture = build_default_synthetic_fixture(
            authority=ReportDemoAuthority.HOST_SIMULATION
        )
        assert fixture.authority == ReportDemoAuthority.HOST_SIMULATION
        assert all(e.authority == ReportDemoAuthority.HOST_SIMULATION for e in fixture.entries)


class TestBuildSyntheticFixtureFromJson:
    """Test build_synthetic_fixture_from_json function."""
    
    def test_valid_json_data(self):
        """Valid JSON-like dict builds fixture."""
        data = {
            "entries": [
                {
                    "week": 14,
                    "implementation_complete": True,
                    "host_validation_passed": True,
                    "live_validation_complete": False,
                    "final_acceptance": False,
                },
                {
                    "week": 15,
                    "implementation_complete": True,
                    "host_validation_passed": True,
                    "live_validation_complete": False,
                    "final_acceptance": False,
                },
            ],
            "authority": "SYNTHETIC_DEMO",
            "description": "Test synthetic fixture",
        }
        fixture = build_synthetic_fixture_from_json(data)
        assert len(fixture.entries) == 2
        assert fixture.entries[0].week == 14
        assert fixture.entries[1].week == 15
    
    def test_missing_required_key(self):
        """Missing required key raises ValueError."""
        data = {
            "entries": [],
            "authority": "SYNTHETIC_DEMO",
        }
        with pytest.raises(ValueError, match="data must contain 'description' key"):
            build_synthetic_fixture_from_json(data)
    
    def test_invalid_authority(self):
        """Invalid authority raises ValueError."""
        data = {
            "entries": [],
            "authority": "LIVE_INDEPENDENT",
            "description": "Test",
        }
        with pytest.raises(ValueError, match="invalid authority"):
            build_synthetic_fixture_from_json(data)
    
    def test_invalid_data_type(self):
        """Invalid data type raises TypeError."""
        with pytest.raises(TypeError, match="data must be a dict"):
            build_synthetic_fixture_from_json("invalid")

    def test_non_claim_flag_cannot_be_flipped_true(self):
        data = {
            "entries": [],
            "authority": "SYNTHETIC_DEMO",
            "description": "Test",
            "non_claims": {"physical_execution": True},
        }
        with pytest.raises(ValueError, match="physical_execution_claimed must be False"):
            build_synthetic_fixture_from_json(data)

    def test_non_claims_must_be_an_object(self):
        data = {
            "entries": [],
            "authority": "SYNTHETIC_DEMO",
            "description": "Test",
            "non_claims": "invalid",
        }
        with pytest.raises(TypeError, match="non_claims must be a dict"):
            build_synthetic_fixture_from_json(data)


class TestSyntheticDemoOnlyConstraints:
    """Test SYNTHETIC_DEMO_ONLY constraints are enforced."""
    
    def test_no_live_validation_in_fixture(self):
        """Fixture cannot contain live validation claims."""
        entry = WeeklySyntheticEntry(
            week=14,
            implementation_complete=True,
            host_validation_passed=True,
            live_validation_complete=False,
            final_acceptance=False,
            authority=ReportDemoAuthority.SYNTHETIC_DEMO,
        )
        # This should work - live_validation_complete is False
        fixture = SyntheticReportFixture(
            entries=(entry,),
            authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            description="Test",
        )
        result = assess_synthetic_report(fixture)
        assert result.live_validation_complete_count == 0
    
    def test_no_final_acceptance_in_fixture(self):
        """Fixture cannot contain final acceptance claims."""
        entry = WeeklySyntheticEntry(
            week=14,
            implementation_complete=True,
            host_validation_passed=True,
            live_validation_complete=False,
            final_acceptance=False,
            authority=ReportDemoAuthority.SYNTHETIC_DEMO,
        )
        fixture = SyntheticReportFixture(
            entries=(entry,),
            authority=ReportDemoAuthority.SYNTHETIC_DEMO,
            description="Test",
        )
        result = assess_synthetic_report(fixture)
        assert result.final_acceptance_count == 0
    
    def test_summary_emphasizes_synthetic_only(self):
        """Summary text emphasizes SYNTHETIC_DEMO_ONLY."""
        fixture = build_default_synthetic_fixture()
        result = assess_synthetic_report(fixture)
        assert "SYNTHETIC_DEMO_ONLY" in result.summary_text
        assert "does NOT claim physical execution" in result.summary_text
        assert "does NOT claim" in result.summary_text


class TestWeekRangeValidation:
    """Test exact week range W14-W24 validation."""
    
    def test_exact_week_count(self):
        """Exactly 11 weeks required."""
        fixture = build_default_synthetic_fixture()
        result = assess_synthetic_report(fixture)
        assert result.total_weeks == 11
        assert result.expected_weeks == 11
    
    def test_week_boundaries(self):
        """Week boundaries are 14 and 24."""
        fixture = build_default_synthetic_fixture()
        result = assess_synthetic_report(fixture)
        assert result.week_range_start == 14
        assert result.week_range_end == 24


class TestControlTests:
    """Focused control tests for synthetic report validator."""
    
    def test_control_all_weeks_present(self):
        """Control: All W14-W24 weeks present."""
        fixture = build_default_synthetic_fixture()
        coverage = assess_week_coverage(fixture.entries)
        assert coverage.all_weeks_present is True
        assert coverage.missing_weeks == ()
    
    def test_control_no_duplicates(self):
        """Control: No duplicate weeks."""
        fixture = build_default_synthetic_fixture()
        coverage = assess_week_coverage(fixture.entries)
        assert coverage.no_duplicates is True
        assert coverage.duplicate_weeks == ()
    
    def test_control_all_synthetic_authority(self):
        """Control: All entries have synthetic authority."""
        fixture = build_default_synthetic_fixture()
        coverage = assess_week_coverage(fixture.entries)
        assert coverage.all_synthetic_authority is True
    
    def test_control_no_live_claims(self):
        """Control: No live validation claims."""
        fixture = build_default_synthetic_fixture()
        coverage = assess_week_coverage(fixture.entries)
        assert coverage.no_live_claims is True
    
    def test_control_no_physical_claims(self):
        """Control: No final acceptance claims."""
        fixture = build_default_synthetic_fixture()
        coverage = assess_week_coverage(fixture.entries)
        assert coverage.no_physical_claims is True
    
    def test_control_full_validation_pass(self):
        """Control: Full validation passes."""
        fixture = build_default_synthetic_fixture()
        result = assess_synthetic_report(fixture)
        assert result.valid is True
        assert result.blockers == ()
