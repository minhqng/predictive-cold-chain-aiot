"""Synthetic report/demo evidence validator for Member D W14-W24.

Pure decision module for synthetic demonstration evidence only.
Implements week coverage validation, synthetic authority enforcement,
and explicit non-claim of physical execution or live evidence.

Key principles:
- UNMISTAKABLY SYNTHETIC_DEMO_ONLY
- Never claims physical execution, live evidence, gate signoff, or final acceptance
- Validates exact week coverage W14 through W24 (11 weeks)
- Rejects duplicate or missing weeks
- Rejects any fixture combining synthetic authority with live/physical/signoff claims
- No invented real measurements or engineering thresholds

Authority levels (SYNTHETIC_DEMO_ONLY):
- SYNTHETIC_DEMO: Synthetic demonstration evidence, no physical claim
- HOST_SIMULATION: Host-based simulation, no live claim

This module does NOT:
- Claim physical execution or live evidence
- Claim gate signoff or final acceptance
- Invent real measurements or engineering thresholds
- Validate or certify physical systems
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class ReportDemoAuthority(str, Enum):
    """Authority level for synthetic report/demo evidence.
    
    IMPORTANT: All values are SYNTHETIC_DEMO_ONLY.
    None represent physical execution, live evidence, or gate signoff.
    """
    
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
    HOST_SIMULATION = "HOST_SIMULATION"


class WeekCoverageStatus(str, Enum):
    """Status of week coverage in synthetic report."""
    
    IMPLEMENTATION_COMPLETE = "IMPLEMENTATION_COMPLETE"
    HOST_VALIDATION_PASSED = "HOST_VALIDATION_PASSED"
    LIVE_VALIDATION_PENDING = "LIVE_VALIDATION_PENDING"
    FINAL_ACCEPTANCE_PENDING = "FINAL_ACCEPTANCE_PENDING"


@dataclass(frozen=True, slots=True)
class WeeklySyntheticEntry:
    """One week of synthetic report/demo evidence.
    
    Attributes:
        week: Week number (14-24 for this report)
        implementation_complete: Whether implementation is complete (synthetic)
        host_validation_passed: Whether host validation passed (synthetic)
        live_validation_complete: Always False for synthetic evidence
        final_acceptance: Always False for synthetic evidence
        authority: Must be SYNTHETIC_DEMO or HOST_SIMULATION
        notes: Optional synthetic notes
    """
    
    week: int
    implementation_complete: bool
    host_validation_passed: bool
    live_validation_complete: bool
    final_acceptance: bool
    authority: ReportDemoAuthority
    notes: str | None = None
    
    def __post_init__(self) -> None:
        if isinstance(self.week, bool) or not isinstance(self.week, int):
            raise TypeError("week must be an integer")
        if self.week < 14 or self.week > 24:
            raise ValueError("week must be between 14 and 24 inclusive")
        if not isinstance(self.implementation_complete, bool):
            raise TypeError("implementation_complete must be a strict boolean")
        if not isinstance(self.host_validation_passed, bool):
            raise TypeError("host_validation_passed must be a strict boolean")
        if not isinstance(self.live_validation_complete, bool):
            raise TypeError("live_validation_complete must be a strict boolean")
        if not isinstance(self.final_acceptance, bool):
            raise TypeError("final_acceptance must be a strict boolean")
        if not isinstance(self.authority, ReportDemoAuthority):
            raise TypeError("authority must be a ReportDemoAuthority")
        if self.live_validation_complete:
            raise ValueError(
                "SYNTHETIC_DEMO_ONLY: live_validation_complete must be False. "
                "This is synthetic evidence, not live execution."
            )
        if self.final_acceptance:
            raise ValueError(
                "SYNTHETIC_DEMO_ONLY: final_acceptance must be False. "
                "This is synthetic evidence, not final acceptance."
            )
        if self.notes is not None:
            if not isinstance(self.notes, str):
                raise TypeError("notes must be a string if provided")
            if "PHYSICAL" in self.notes.upper() or "LIVE" in self.notes.upper():
                raise ValueError(
                    "SYNTHETIC_DEMO_ONLY: notes cannot claim physical or live execution"
                )
            if "SIGNOFF" in self.notes.upper() or "ACCEPTANCE" in self.notes.upper():
                raise ValueError(
                    "SYNTHETIC_DEMO_ONLY: notes cannot claim signoff or acceptance"
                )


@dataclass(frozen=True, slots=True)
class SyntheticReportFixture:
    """Complete synthetic report fixture for W14-W24.
    
    Attributes:
        entries: Weekly synthetic entries
        authority: Overall authority level
        description: Synthetic report description
    """
    
    entries: tuple[WeeklySyntheticEntry, ...]
    authority: ReportDemoAuthority
    description: str
    physical_execution_claimed: bool = False
    gate_signoff_claimed: bool = False
    real_measurements_claimed: bool = False
    engineering_thresholds_claimed: bool = False
    
    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be a tuple")
        if not all(isinstance(e, WeeklySyntheticEntry) for e in self.entries):
            raise TypeError("all entries must be WeeklySyntheticEntry")
        if not isinstance(self.authority, ReportDemoAuthority):
            raise TypeError("authority must be a ReportDemoAuthority")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be a nonempty string")
        if "PHYSICAL" in self.description.upper() or "LIVE" in self.description.upper():
            raise ValueError(
                "SYNTHETIC_DEMO_ONLY: description cannot claim physical or live execution"
            )
        for name in (
            "physical_execution_claimed",
            "gate_signoff_claimed",
            "real_measurements_claimed",
            "engineering_thresholds_claimed",
        ):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a strict boolean")
            if value:
                raise ValueError(f"SYNTHETIC_DEMO_ONLY: {name} must be False")


@dataclass(frozen=True, slots=True)
class WeekCoverageAssessment:
    """Assessment result for week coverage validation."""
    
    weeks_covered: tuple[int, ...]
    missing_weeks: tuple[int, ...]
    duplicate_weeks: tuple[int, ...]
    all_weeks_present: bool
    no_duplicates: bool
    all_synthetic_authority: bool
    no_live_claims: bool
    no_physical_claims: bool
    no_signoff_claims: bool
    valid: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticReportSummary:
    """Summary of synthetic report validation."""
    
    fixture: SyntheticReportFixture | None
    week_range_start: int | None
    week_range_end: int | None
    total_weeks: int
    expected_weeks: int
    implementation_complete_count: int
    host_validation_passed_count: int
    live_validation_complete_count: int  # Should always be 0
    final_acceptance_count: int  # Should always be 0
    authority: ReportDemoAuthority | None
    all_synthetic: bool
    valid: bool
    blockers: tuple[str, ...]
    summary_text: str


REQUIRED_WEEKS: frozenset[int] = frozenset(range(14, 25))  # W14 through W24


def validate_weekly_entry(entry: WeeklySyntheticEntry) -> WeeklySyntheticEntry:
    """Validate a single weekly synthetic entry.
    
    Args:
        entry: Weekly synthetic entry to validate.
        
    Returns:
        The same entry if valid.
        
    Raises:
        TypeError: If entry has invalid types.
        ValueError: If entry violates synthetic-only constraints.
    """
    if not isinstance(entry, WeeklySyntheticEntry):
        raise TypeError("entry must be a WeeklySyntheticEntry")
    return entry


def validate_synthetic_fixture(fixture: SyntheticReportFixture) -> SyntheticReportFixture:
    """Validate a synthetic report fixture.
    
    Args:
        fixture: Synthetic report fixture to validate.
        
    Returns:
        The same fixture if valid.
        
    Raises:
        TypeError: If fixture has invalid types.
        ValueError: If fixture violates synthetic-only constraints.
    """
    if not isinstance(fixture, SyntheticReportFixture):
        raise TypeError("fixture must be a SyntheticReportFixture")
    return fixture


def assess_week_coverage(
    entries: Sequence[WeeklySyntheticEntry],
) -> WeekCoverageAssessment:
    """Assess week coverage for synthetic report.
    
    Validates:
    - Exact week coverage W14 through W24
    - No duplicate weeks
    - No missing weeks
    - All entries have synthetic authority (no live/physical claims)
    - No signoff or acceptance claims
    
    Args:
        entries: Weekly synthetic entries to assess.
        
    Returns:
        WeekCoverageAssessment with validation results.
    """
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise TypeError("entries must be a Sequence of WeeklySyntheticEntry")
    
    weeks_seen: dict[int, WeeklySyntheticEntry] = {}
    duplicates: list[int] = []
    
    for entry in entries:
        if not isinstance(entry, WeeklySyntheticEntry):
            raise TypeError("each entry must be a WeeklySyntheticEntry")
        
        if entry.week in weeks_seen:
            duplicates.append(entry.week)
        else:
            weeks_seen[entry.week] = entry
    
    weeks_covered = tuple(sorted(weeks_seen.keys()))
    missing = tuple(sorted(REQUIRED_WEEKS - set(weeks_covered)))
    duplicate_weeks = tuple(sorted(set(duplicates)))
    
    all_present = len(missing) == 0
    no_dups = len(duplicate_weeks) == 0
    
    all_synthetic = all(
        e.authority in (ReportDemoAuthority.SYNTHETIC_DEMO, ReportDemoAuthority.HOST_SIMULATION)
        for e in entries
    )
    
    no_live = all(not e.live_validation_complete for e in entries)
    no_physical = all(not e.final_acceptance for e in entries)
    no_signoff = all(not e.final_acceptance for e in entries)
    all_implementation_complete = all(e.implementation_complete for e in entries)
    all_host_validation_passed = all(e.host_validation_passed for e in entries)
    
    blockers: list[str] = []
    
    if not all_present:
        blockers.extend(f"MISSING_WEEK:W{w}" for w in missing)
    if not no_dups:
        blockers.extend(f"DUPLICATE_WEEK:W{w}" for w in duplicate_weeks)
    if not all_synthetic:
        blockers.append("NON_SYNTHETIC_AUTHORITY_DETECTED")
    if not no_live:
        blockers.append("LIVE_VALIDATION_CLAIM_NOT_ALLOWED_IN_SYNTHETIC")
    if not no_physical:
        blockers.append("FINAL_ACCEPTANCE_CLAIM_NOT_ALLOWED_IN_SYNTHETIC")
    if not all_implementation_complete:
        blockers.extend(
            f"IMPLEMENTATION_INCOMPLETE:W{entry.week}"
            for entry in entries
            if not entry.implementation_complete
        )
    if not all_host_validation_passed:
        blockers.extend(
            f"HOST_VALIDATION_NOT_PASSED:W{entry.week}"
            for entry in entries
            if not entry.host_validation_passed
        )
    
    valid = (
        all_present
        and no_dups
        and all_synthetic
        and no_live
        and no_physical
        and no_signoff
        and all_implementation_complete
        and all_host_validation_passed
    )
    
    return WeekCoverageAssessment(
        weeks_covered=weeks_covered,
        missing_weeks=missing,
        duplicate_weeks=duplicate_weeks,
        all_weeks_present=all_present,
        no_duplicates=no_dups,
        all_synthetic_authority=all_synthetic,
        no_live_claims=no_live,
        no_physical_claims=no_physical,
        no_signoff_claims=no_signoff,
        valid=valid,
        blockers=tuple(blockers),
    )


def assess_synthetic_report(
    fixture: SyntheticReportFixture | None,
) -> SyntheticReportSummary:
    """Assess complete synthetic report.
    
    Args:
        fixture: Synthetic report fixture to assess, or None.
        
    Returns:
        SyntheticReportSummary with validation results and summary.
    """
    if fixture is None:
        return SyntheticReportSummary(
            fixture=None,
            week_range_start=None,
            week_range_end=None,
            total_weeks=0,
            expected_weeks=len(REQUIRED_WEEKS),
            implementation_complete_count=0,
            host_validation_passed_count=0,
            live_validation_complete_count=0,
            final_acceptance_count=0,
            authority=None,
            all_synthetic=False,
            valid=False,
            blockers=("NO_FIXTURE_PROVIDED",),
            summary_text="No synthetic report fixture provided.",
        )
    
    if not isinstance(fixture, SyntheticReportFixture):
        raise TypeError("fixture must be a SyntheticReportFixture or None")
    
    coverage = assess_week_coverage(fixture.entries)
    
    weeks = sorted(e.week for e in fixture.entries)
    week_start = weeks[0] if weeks else None
    week_end = weeks[-1] if weeks else None
    
    impl_complete = sum(1 for e in fixture.entries if e.implementation_complete)
    host_passed = sum(1 for e in fixture.entries if e.host_validation_passed)
    live_complete = sum(1 for e in fixture.entries if e.live_validation_complete)
    final_accept = sum(1 for e in fixture.entries if e.final_acceptance)
    
    all_synthetic = coverage.all_synthetic_authority
    valid = coverage.valid
    
    blockers = list(coverage.blockers)
    
    summary_parts: list[str] = []
    summary_parts.append(f"SYNTHETIC REPORT/DEMO EVIDENCE PACK — Member D W{week_start}-W{week_end}")
    summary_parts.append(f"Authority: {fixture.authority.value} (SYNTHETIC_DEMO_ONLY)")
    summary_parts.append(f"Week Coverage: {len(weeks)}/{len(REQUIRED_WEEKS)} weeks")
    summary_parts.append(f"Implementation Complete: {impl_complete}/{len(weeks)} weeks (synthetic)")
    summary_parts.append(f"Host Validation Passed: {host_passed}/{len(weeks)} weeks (synthetic)")
    summary_parts.append(f"Live Validation Complete: {live_complete}/{len(weeks)} weeks (MUST BE 0)")
    summary_parts.append(f"Final Acceptance: {final_accept}/{len(weeks)} weeks (MUST BE 0)")
    
    if valid:
        summary_parts.append("VALIDATION: PASSED — All synthetic constraints satisfied")
    else:
        summary_parts.append(f"VALIDATION: FAILED — {'; '.join(blockers)}")
    
    summary_parts.append("")
    summary_parts.append("IMPORTANT: This is SYNTHETIC_DEMO_ONLY evidence.")
    summary_parts.append("It does NOT claim physical execution, live evidence, gate signoff, or final acceptance.")
    
    summary_text = "\n".join(summary_parts)
    
    return SyntheticReportSummary(
        fixture=fixture,
        week_range_start=week_start,
        week_range_end=week_end,
        total_weeks=len(weeks),
        expected_weeks=len(REQUIRED_WEEKS),
        implementation_complete_count=impl_complete,
        host_validation_passed_count=host_passed,
        live_validation_complete_count=live_complete,
        final_acceptance_count=final_accept,
        authority=fixture.authority,
        all_synthetic=all_synthetic,
        valid=valid,
        blockers=tuple(blockers),
        summary_text=summary_text,
    )


def build_default_synthetic_fixture(
    authority: ReportDemoAuthority = ReportDemoAuthority.SYNTHETIC_DEMO,
) -> SyntheticReportFixture:
    """Build default synthetic fixture covering W14-W24.
    
    All weeks have:
    - implementation_complete=True
    - host_validation_passed=True
    - live_validation_complete=False
    - final_acceptance=False
    
    Args:
        authority: Authority level for all entries.
        
    Returns:
        SyntheticReportFixture with all 11 weeks (W14-W24).
    """
    entries = tuple(
        WeeklySyntheticEntry(
            week=week,
            implementation_complete=True,
            host_validation_passed=True,
            live_validation_complete=False,
            final_acceptance=False,
            authority=authority,
            notes=f"Synthetic demo evidence for W{week}",
        )
        for week in range(14, 25)
    )
    
    return SyntheticReportFixture(
        entries=entries,
        authority=authority,
        description="Synthetic report/demo evidence pack for Member D W14-W24",
    )


def build_synthetic_fixture_from_json(
    data: dict,
) -> SyntheticReportFixture:
    """Build synthetic fixture from JSON-like dict.
    
    Args:
        data: Dict with 'entries', 'authority', and 'description' keys.
        
    Returns:
        SyntheticReportFixture built from data.
        
    Raises:
        TypeError: If data has invalid structure.
        ValueError: If data violates synthetic-only constraints.
    """
    if not isinstance(data, dict):
        raise TypeError("data must be a dict")
    
    if "entries" not in data:
        raise ValueError("data must contain 'entries' key")
    if "authority" not in data:
        raise ValueError("data must contain 'authority' key")
    if "description" not in data:
        raise ValueError("data must contain 'description' key")
    
    authority_str = data["authority"]
    try:
        authority = ReportDemoAuthority(authority_str)
    except ValueError:
        raise ValueError(f"invalid authority: {authority_str}")
    
    entries_data = data["entries"]
    if not isinstance(entries_data, list):
        raise TypeError("entries must be a list")
    
    entries = []
    for ed in entries_data:
        if not isinstance(ed, dict):
            raise TypeError("each entry must be a dict")
        
        required_keys = ["week", "implementation_complete", "host_validation_passed",
                        "live_validation_complete", "final_acceptance"]
        for key in required_keys:
            if key not in ed:
                raise ValueError(f"entry missing required key: {key}")
        
        entries.append(WeeklySyntheticEntry(
            week=ed["week"],
            implementation_complete=ed["implementation_complete"],
            host_validation_passed=ed["host_validation_passed"],
            live_validation_complete=ed["live_validation_complete"],
            final_acceptance=ed["final_acceptance"],
            authority=authority,
            notes=ed.get("notes"),
        ))
    
    non_claims = data.get("non_claims", {})
    if not isinstance(non_claims, dict):
        raise TypeError("non_claims must be a dict if provided")
    for key in (
        "physical_execution",
        "gate_signoff",
        "real_measurements",
        "engineering_thresholds",
    ):
        if key in non_claims and not isinstance(non_claims[key], bool):
            raise TypeError(f"non_claims.{key} must be a strict boolean")

    return SyntheticReportFixture(
        entries=tuple(entries),
        authority=authority,
        description=data["description"],
        physical_execution_claimed=non_claims.get("physical_execution", False),
        gate_signoff_claimed=non_claims.get("gate_signoff", False),
        real_measurements_claimed=non_claims.get("real_measurements", False),
        engineering_thresholds_claimed=non_claims.get(
            "engineering_thresholds", False
        ),
    )
