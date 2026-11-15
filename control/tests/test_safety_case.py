"""Tests for Week 22 safety case module."""

from dataclasses import FrozenInstanceError

import pytest

from coldguard_control.safety_case import (
    DEFAULT_CORE_HAZARDS,
    EvidenceAuthority,
    HazardCategory,
    Likelihood,
    MatrixResult,
    OptionalScopeItem,
    ResidualRisk,
    SafetyCaseSummary,
    SafetyMatrixEntry,
    Severity,
    assess_safety_case,
    build_default_safety_case,
)


class TestSafetyMatrixEntry:
    """Tests for SafetyMatrixEntry validation."""

    def test_valid_entry_creation(self):
        entry = SafetyMatrixEntry(
            hazard_id="CTRL-01",
            hazard_description="Test hazard",
            hazard_category=HazardCategory.COMMAND_INTEGRITY,
            severity=Severity.HIGH,
            invariant="Test invariant",
            test_id="TEST-01",
            test_description="Test description",
            result=MatrixResult.PASS,
        )
        assert entry.hazard_id == "CTRL-01"
        assert entry.result is MatrixResult.PASS
        assert entry.evidence_authority is EvidenceAuthority.HOST_SIMULATED

    def test_entry_with_live_evidence(self):
        entry = SafetyMatrixEntry(
            hazard_id="CTRL-01",
            hazard_description="Test hazard",
            hazard_category=HazardCategory.COMMAND_INTEGRITY,
            severity=Severity.HIGH,
            invariant="Test invariant",
            test_id="TEST-01",
            test_description="Test description",
            result=MatrixResult.PASS,
            evidence_authority=EvidenceAuthority.LIVE_EVIDENCE,
        )
        assert entry.evidence_authority is EvidenceAuthority.LIVE_EVIDENCE

    def test_empty_hazard_id_rejected(self):
        with pytest.raises(ValueError, match="hazard_id must be nonempty"):
            SafetyMatrixEntry(
                hazard_id="",
                hazard_description="Test",
                hazard_category=HazardCategory.COMMAND_INTEGRITY,
                severity=Severity.HIGH,
                invariant="Test",
                test_id="TEST-01",
                test_description="Test",
                result=MatrixResult.PASS,
            )

    def test_empty_invariant_rejected(self):
        with pytest.raises(ValueError, match="invariant must be nonempty"):
            SafetyMatrixEntry(
                hazard_id="CTRL-01",
                hazard_description="Test",
                hazard_category=HazardCategory.COMMAND_INTEGRITY,
                severity=Severity.HIGH,
                invariant="",
                test_id="TEST-01",
                test_description="Test",
                result=MatrixResult.PASS,
            )

    def test_invalid_hazard_category_type(self):
        with pytest.raises(TypeError, match="hazard_category must be a HazardCategory"):
            SafetyMatrixEntry(
                hazard_id="CTRL-01",
                hazard_description="Test",
                hazard_category="COMMAND_INTEGRITY",  # type: ignore[arg-type]
                severity=Severity.HIGH,
                invariant="Test",
                test_id="TEST-01",
                test_description="Test",
                result=MatrixResult.PASS,
            )

    def test_invalid_result_type(self):
        with pytest.raises(TypeError, match="result must be a MatrixResult"):
            SafetyMatrixEntry(
                hazard_id="CTRL-01",
                hazard_description="Test",
                hazard_category=HazardCategory.COMMAND_INTEGRITY,
                severity=Severity.HIGH,
                invariant="Test",
                test_id="TEST-01",
                test_description="Test",
                result="PASS",  # type: ignore[arg-type]
            )

    def test_entry_is_immutable(self):
        entry = SafetyMatrixEntry(
            hazard_id="CTRL-01",
            hazard_description="Test",
            hazard_category=HazardCategory.COMMAND_INTEGRITY,
            severity=Severity.HIGH,
            invariant="Test",
            test_id="TEST-01",
            test_description="Test",
            result=MatrixResult.PASS,
        )
        with pytest.raises(FrozenInstanceError):
            entry.result = MatrixResult.FAIL  # type: ignore[misc]


class TestResidualRisk:
    """Tests for ResidualRisk validation."""

    def test_valid_risk_creation(self):
        risk = ResidualRisk(
            risk_id="RR-01",
            risk_description="Test risk",
            severity=Severity.MEDIUM,
            likelihood=Likelihood.POSSIBLE,
            mitigation="Test mitigation",
            limitation="Test limitation",
        )
        assert risk.risk_id == "RR-01"
        assert risk.severity is Severity.MEDIUM
        assert risk.likelihood is Likelihood.POSSIBLE

    def test_empty_mitigation_rejected(self):
        with pytest.raises(ValueError, match="mitigation must be nonempty"):
            ResidualRisk(
                risk_id="RR-01",
                risk_description="Test",
                severity=Severity.MEDIUM,
                likelihood=Likelihood.POSSIBLE,
                mitigation="",
                limitation="Test",
            )

    def test_empty_limitation_rejected(self):
        with pytest.raises(ValueError, match="limitation must be nonempty"):
            ResidualRisk(
                risk_id="RR-01",
                risk_description="Test",
                severity=Severity.MEDIUM,
                likelihood=Likelihood.POSSIBLE,
                mitigation="Test",
                limitation="",
            )

    def test_invalid_severity_type(self):
        with pytest.raises(TypeError, match="severity must be a Severity"):
            ResidualRisk(
                risk_id="RR-01",
                risk_description="Test",
                severity="MEDIUM",  # type: ignore[arg-type]
                likelihood=Likelihood.POSSIBLE,
                mitigation="Test",
                limitation="Test",
            )

    def test_invalid_likelihood_type(self):
        with pytest.raises(TypeError, match="likelihood must be a Likelihood"):
            ResidualRisk(
                risk_id="RR-01",
                risk_description="Test",
                severity=Severity.MEDIUM,
                likelihood="POSSIBLE",  # type: ignore[arg-type]
                mitigation="Test",
                limitation="Test",
            )

    def test_risk_is_immutable(self):
        risk = ResidualRisk(
            risk_id="RR-01",
            risk_description="Test",
            severity=Severity.MEDIUM,
            likelihood=Likelihood.POSSIBLE,
            mitigation="Test",
            limitation="Test",
        )
        with pytest.raises(FrozenInstanceError):
            risk.severity = Severity.HIGH  # type: ignore[misc]


class TestOptionalScopeItem:
    """Tests for OptionalScopeItem validation."""

    def test_valid_optional_item(self):
        item = OptionalScopeItem(
            item_id="OPT-01",
            item_name="Secure Boot Research",
            description="Research on Secure Boot v2",
            core_prerequisite_met=True,
            status="RESEARCH_ONLY",
        )
        assert item.item_id == "OPT-01"
        assert item.core_prerequisite_met is True

    def test_core_prerequisite_must_be_bool(self):
        with pytest.raises(TypeError, match="core_prerequisite_met must be a strict boolean"):
            OptionalScopeItem(
                item_id="OPT-01",
                item_name="Test",
                description="Test",
                core_prerequisite_met=1,  # type: ignore[arg-type]
                status="NOT_STARTED",
            )

    def test_empty_item_name_rejected(self):
        with pytest.raises(ValueError, match="item_name must be nonempty"):
            OptionalScopeItem(
                item_id="OPT-01",
                item_name="",
                description="Test",
                core_prerequisite_met=True,
                status="NOT_STARTED",
            )

    def test_item_is_immutable(self):
        item = OptionalScopeItem(
            item_id="OPT-01",
            item_name="Test",
            description="Test",
            core_prerequisite_met=True,
            status="NOT_STARTED",
        )
        with pytest.raises(FrozenInstanceError):
            item.status = "COMPLETED"  # type: ignore[misc]


class TestAssessSafetyCase:
    """Tests for assess_safety_case function."""

    def _make_entry(
        self,
        hazard_id="CTRL-01",
        result=MatrixResult.PASS,
        authority=EvidenceAuthority.HOST_SIMULATED,
    ):
        return SafetyMatrixEntry(
            hazard_id=hazard_id,
            hazard_description="Test hazard",
            hazard_category=HazardCategory.COMMAND_INTEGRITY,
            severity=Severity.HIGH,
            invariant="Test invariant",
            test_id="TEST-01",
            test_description="Test description",
            result=result,
            evidence_authority=authority,
            evidence_ref=("evidence/D/W22/CTRL-01.json"
                          if authority is EvidenceAuthority.LIVE_EVIDENCE else None),
        )

    def _make_risk(self, risk_id="RR-01"):
        return ResidualRisk(
            risk_id=risk_id,
            risk_description="Test risk",
            severity=Severity.MEDIUM,
            likelihood=Likelihood.POSSIBLE,
            mitigation="Test mitigation",
            limitation="Test limitation",
        )

    def test_all_pass_entries_produce_green_core(self):
        summary = assess_safety_case(
            matrix_entries=[self._make_entry(authority=EvidenceAuthority.LIVE_EVIDENCE)],
            residual_risks=[self._make_risk()],
        )
        assert summary.core_matrix_all_pass is True
        assert summary.core_evidence_green is True
        assert len(summary.passed_entries) == 1
        assert len(summary.failed_entries) == 0
        assert len(summary.pending_entries) == 0

    def test_failed_entry_blocks_core_matrix(self):
        summary = assess_safety_case(
            matrix_entries=[self._make_entry(result=MatrixResult.FAIL)],
            residual_risks=[self._make_risk()],
        )
        assert summary.core_matrix_all_pass is False
        assert len(summary.failed_entries) == 1
        assert "FAILED_ENTRY:CTRL-01" in summary.blockers

    def test_pending_entry_blocks_core_matrix(self):
        summary = assess_safety_case(
            matrix_entries=[self._make_entry(result=MatrixResult.PENDING)],
            residual_risks=[self._make_risk()],
        )
        assert summary.core_matrix_all_pass is False
        assert len(summary.pending_entries) == 1
        assert "PENDING_ENTRY:CTRL-01" in summary.blockers

    def test_mixed_results_categorized_correctly(self):
        entries = [
            self._make_entry("CTRL-01", MatrixResult.PASS),
            self._make_entry("CTRL-02", MatrixResult.FAIL),
            self._make_entry("CTRL-03", MatrixResult.PENDING),
        ]
        summary = assess_safety_case(
            matrix_entries=entries,
            residual_risks=[self._make_risk()],
        )
        assert len(summary.passed_entries) == 1
        assert len(summary.failed_entries) == 1
        assert len(summary.pending_entries) == 1
        assert summary.core_matrix_all_pass is False

    def test_empty_residual_risks_rejected(self):
        with pytest.raises(ValueError, match="residual_risks must be nonempty"):
            assess_safety_case(
                matrix_entries=[self._make_entry()],
                residual_risks=[],
            )

    def test_optional_scope_allowed_when_core_green(self):
        optional = [
            OptionalScopeItem(
                item_id="OPT-01",
                item_name="Test",
                description="Test",
                core_prerequisite_met=True,
                status="NOT_STARTED",
            )
        ]
        summary = assess_safety_case(
            matrix_entries=[self._make_entry(authority=EvidenceAuthority.LIVE_EVIDENCE)],
            residual_risks=[self._make_risk()],
            optional_scope_items=optional,
        )
        assert summary.optional_scope_allowed is True

    def test_optional_scope_not_allowed_when_core_has_failures(self):
        optional = [
            OptionalScopeItem(
                item_id="OPT-01",
                item_name="Test",
                description="Test",
                core_prerequisite_met=False,
                status="NOT_STARTED",
            )
        ]
        summary = assess_safety_case(
            matrix_entries=[self._make_entry(result=MatrixResult.FAIL)],
            residual_risks=[self._make_risk()],
            optional_scope_items=optional,
        )
        assert summary.optional_scope_allowed is False
        # Core failure already blocks optional scope; blocker is about failed entry
        assert any("FAILED_ENTRY" in b for b in summary.blockers)

    def test_optional_item_without_confirmed_prerequisite_blocks_scope(self):
        optional = [
            OptionalScopeItem(
                item_id="OPT-01",
                item_name="Test",
                description="Test",
                core_prerequisite_met=False,
                status="NOT_STARTED",
            )
        ]
        summary = assess_safety_case(
            matrix_entries=[self._make_entry()],
            residual_risks=[self._make_risk()],
            optional_scope_items=optional,
        )
        assert summary.core_matrix_all_pass is True
        assert summary.optional_scope_allowed is False
        assert any(
            blocker.startswith("OPTIONAL_SCOPE_NOT_ALLOWED:OPT-01")
            for blocker in summary.blockers
        )

    def test_no_passing_entries_blocks(self):
        summary = assess_safety_case(
            matrix_entries=[],
            residual_risks=[self._make_risk()],
        )
        assert summary.core_matrix_all_pass is False
        assert "NO_PASSING_ENTRIES" in summary.blockers

    def test_matrix_entries_type_check(self):
        with pytest.raises(TypeError, match="matrix_entries must be a Sequence"):
            assess_safety_case(
                matrix_entries="not a sequence",  # type: ignore[arg-type]
                residual_risks=[self._make_risk()],
            )

    def test_residual_risks_type_check(self):
        with pytest.raises(TypeError, match="residual_risks must be a Sequence"):
            assess_safety_case(
                matrix_entries=[self._make_entry()],
                residual_risks="not a sequence",  # type: ignore[arg-type]
            )

    def test_invalid_matrix_entry_type(self):
        with pytest.raises(TypeError, match="each matrix entry must be a SafetyMatrixEntry"):
            assess_safety_case(
                matrix_entries=[object()],  # type: ignore[list-item]
                residual_risks=[self._make_risk()],
            )

    def test_invalid_residual_risk_type(self):
        with pytest.raises(TypeError, match="each residual risk must be a ResidualRisk"):
            assess_safety_case(
                matrix_entries=[self._make_entry()],
                residual_risks=[object()],  # type: ignore[list-item]
            )

    def test_optional_scope_items_type_check(self):
        with pytest.raises(TypeError, match="optional_scope_items must be a Sequence"):
            assess_safety_case(
                matrix_entries=[self._make_entry()],
                residual_risks=[self._make_risk()],
                optional_scope_items="not a sequence",  # type: ignore[arg-type]
            )

    def test_invalid_optional_item_type(self):
        with pytest.raises(TypeError, match="each optional item must be an OptionalScopeItem"):
            assess_safety_case(
                matrix_entries=[self._make_entry()],
                residual_risks=[self._make_risk()],
                optional_scope_items=[object()],  # type: ignore[list-item]
            )

    def test_summary_is_immutable(self):
        summary = assess_safety_case(
            matrix_entries=[self._make_entry()],
            residual_risks=[self._make_risk()],
        )
        with pytest.raises(FrozenInstanceError):
            summary.core_matrix_all_pass = False  # type: ignore[misc]


class TestBuildDefaultSafetyCase:
    """Tests for build_default_safety_case helper."""

    def test_default_case_has_all_categories(self):
        summary = build_default_safety_case()
        categories = {e.hazard_category for e in summary.matrix_entries}
        assert HazardCategory.COMMAND_INTEGRITY in categories
        assert HazardCategory.RESILIENCE_FAILURE in categories
        assert HazardCategory.PHYSICAL_VERIFICATION in categories
        assert HazardCategory.SECURITY_THREAT in categories

    def test_default_case_is_pending_and_fail_closed(self):
        summary = build_default_safety_case()
        assert summary.core_matrix_all_pass is False
        assert summary.core_evidence_green is False
        assert summary.optional_scope_allowed is False
        assert all(entry.result is MatrixResult.PENDING for entry in summary.matrix_entries)

    def test_result_override_applied(self):
        summary = build_default_safety_case(
            result_override={"CTRL-STALE-01": MatrixResult.FAIL}
        )
        failed_ids = {e.hazard_id for e in summary.failed_entries}
        assert "CTRL-STALE-01" in failed_ids
        assert summary.core_matrix_all_pass is False

    def test_live_evidence_authority(self):
        summary = build_default_safety_case(
            evidence_authority=EvidenceAuthority.LIVE_EVIDENCE
        )
        assert all(
            e.evidence_authority is EvidenceAuthority.LIVE_EVIDENCE
            for e in summary.matrix_entries
        )

    def test_default_has_residual_risks(self):
        summary = build_default_safety_case()
        assert len(summary.residual_risks) >= 4
        risk_ids = {r.risk_id for r in summary.residual_risks}
        assert "RR-01" in risk_ids
        assert "RR-02" in risk_ids

    def test_residual_risks_have_nonempty_mitigation_limitation(self):
        summary = build_default_safety_case()
        for risk in summary.residual_risks:
            assert risk.mitigation.strip()
            assert risk.limitation.strip()

    def test_optional_items_not_included_by_default(self):
        summary = build_default_safety_case()
        assert len(summary.optional_scope_items) == 0

    def test_optional_items_included_when_requested(self):
        summary = build_default_safety_case(include_optional=True)
        assert len(summary.optional_scope_items) == 3
        item_ids = {i.item_id for i in summary.optional_scope_items}
        assert "OPT-01" in item_ids
        assert "OPT-02" in item_ids
        assert "OPT-03" in item_ids

    def test_optional_items_are_canonical_three(self):
        summary = build_default_safety_case(include_optional=True)
        names = {i.item_name for i in summary.optional_scope_items}
        assert "Secure Boot Research" in names
        assert "Flash Encryption Lab Plan" in names
        assert "PWM Energy Policy" in names


class TestSeverityAndLikelihoodEnums:
    """Tests for qualitative enums."""

    def test_severity_levels(self):
        assert Severity.LOW.value == "LOW"
        assert Severity.MEDIUM.value == "MEDIUM"
        assert Severity.HIGH.value == "HIGH"
        assert Severity.CRITICAL.value == "CRITICAL"

    def test_likelihood_levels(self):
        assert Likelihood.RARE.value == "RARE"
        assert Likelihood.UNLIKELY.value == "UNLIKELY"
        assert Likelihood.POSSIBLE.value == "POSSIBLE"
        assert Likelihood.LIKELY.value == "LIKELY"
        assert Likelihood.ALMOST_CERTAIN.value == "ALMOST_CERTAIN"

    def test_no_numerical_probability(self):
        """Verify no numerical probability fields exist."""
        import inspect
        from coldguard_control.safety_case import ResidualRisk, SafetyMatrixEntry

        risk_sig = inspect.signature(ResidualRisk)
        entry_sig = inspect.signature(SafetyMatrixEntry)

        risk_params = list(risk_sig.parameters.keys())
        entry_params = list(entry_sig.parameters.keys())

        assert "probability" not in risk_params
        assert "probability" not in entry_params
        assert "numerical_risk" not in risk_params
        assert "numerical_risk" not in entry_params


class TestMatrixResultEnum:
    """Tests for MatrixResult enum."""

    def test_explicit_pass_fail_pending(self):
        assert MatrixResult.PASS.value == "PASS"
        assert MatrixResult.FAIL.value == "FAIL"
        assert MatrixResult.PENDING.value == "PENDING"

    def test_no_implicit_states(self):
        """Verify only explicit states exist."""
        values = {e.value for e in MatrixResult}
        assert values == {"PASS", "FAIL", "PENDING"}


class TestEvidenceAuthorityEnum:
    """Tests for EvidenceAuthority enum."""

    def test_authority_levels(self):
        assert EvidenceAuthority.HOST_SIMULATED.value == "HOST_SIMULATED"
        assert EvidenceAuthority.LIVE_EVIDENCE.value == "LIVE_EVIDENCE"

    def test_host_cannot_claim_live(self):
        """Host-simulated entries don't count as live evidence."""
        entry = SafetyMatrixEntry(
            hazard_id="CTRL-01",
            hazard_description="Test",
            hazard_category=HazardCategory.COMMAND_INTEGRITY,
            severity=Severity.HIGH,
            invariant="Test",
            test_id="TEST-01",
            test_description="Test",
            result=MatrixResult.PASS,
            evidence_authority=EvidenceAuthority.HOST_SIMULATED,
        )
        assert entry.evidence_authority is not EvidenceAuthority.LIVE_EVIDENCE


class TestDoc05DSection54Compliance:
    """Tests verifying Doc 05D section 54 requirements."""

    def test_hazard_invariant_test_matrix_structure(self):
        """D-W22-01: Hazard→invariant→test matrix exists."""
        summary = build_default_safety_case()
        for entry in summary.matrix_entries:
            assert entry.hazard_id
            assert entry.invariant
            assert entry.test_id
            assert entry.result in MatrixResult

    def test_residual_risks_have_mitigation_and_limitation(self):
        """D-W22-02: Residual risks have nonempty mitigation/limitation."""
        summary = build_default_safety_case()
        for risk in summary.residual_risks:
            assert risk.mitigation.strip()
            assert risk.limitation.strip()

    def test_qualitative_severity_and_likelihood_only(self):
        """D-W22-03: Qualitative severity/likelihood, no numerical probability."""
        summary = build_default_safety_case()
        for risk in summary.residual_risks:
            assert isinstance(risk.severity, Severity)
            assert isinstance(risk.likelihood, Likelihood)

    def test_optional_scope_gated_on_core_green(self):
        """D-W22-04: Optional scope only when core matrix all pass and evidence green."""
        hazard_ids = {
            hazard["hazard_id"]
            for hazards in DEFAULT_CORE_HAZARDS.values()
            for hazard in hazards
        }
        all_pass = build_default_safety_case(
            result_override={hazard_id: MatrixResult.PASS for hazard_id in hazard_ids},
            evidence_authority=EvidenceAuthority.LIVE_EVIDENCE,
            evidence_refs={
                hazard_id: f"evidence/D/W22/{hazard_id}.json"
                for hazard_id in hazard_ids
            },
            include_optional=True,
        )
        assert all_pass.core_matrix_all_pass is True
        assert all_pass.core_evidence_green is True
        assert all_pass.optional_scope_allowed is True

        with_failure = build_default_safety_case(
            result_override={"CTRL-STALE-01": MatrixResult.FAIL},
            include_optional=True,
        )
        assert with_failure.core_matrix_all_pass is False
        assert with_failure.optional_scope_allowed is False

    def test_optional_items_are_canonical_three(self):
        """D-W22-04: Secure Boot, Flash Encryption, PWM energy policy."""
        summary = build_default_safety_case(include_optional=True)
        names = {i.item_name for i in summary.optional_scope_items}
        assert names == {
            "Secure Boot Research",
            "Flash Encryption Lab Plan",
            "PWM Energy Policy",
        }

    def test_no_live_evidence_claimed_by_default(self):
        """Verify default build uses HOST_SIMULATED."""
        summary = build_default_safety_case()
        assert all(
            e.evidence_authority is EvidenceAuthority.HOST_SIMULATED
            for e in summary.matrix_entries
        )
