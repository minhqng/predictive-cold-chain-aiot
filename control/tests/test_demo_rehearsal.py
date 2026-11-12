"""Tests for Week 23 demo rehearsal module."""

from dataclasses import FrozenInstanceError

import pytest

from coldguard_control.demo_rehearsal import (
    REQUIRED_SCENE_SEQUENCE,
    REQUIRED_SCENE_OUTCOMES,
    RehearsalAuthority,
    RehearsalDecision,
    RehearsalMetrics,
    RehearsalRecord,
    RehearsalScene,
    SceneEvidence,
    SceneOutcome,
    assess_rehearsal,
    build_demo_rehearsal_record,
)


class TestRehearsalScene:
    """Tests for RehearsalScene enum."""

    def test_four_required_scenes_defined(self):
        assert len(RehearsalScene) == 4
        assert RehearsalScene.VERIFIED_ACTUATION in RehearsalScene
        assert RehearsalScene.SAFE_LOCAL in RehearsalScene
        assert RehearsalScene.STALE_COMMAND in RehearsalScene
        assert RehearsalScene.SECURITY_EXPLANATION in RehearsalScene

    def test_scene_values(self):
        assert RehearsalScene.VERIFIED_ACTUATION.value == "VERIFIED_ACTUATION"
        assert RehearsalScene.SAFE_LOCAL.value == "SAFE_LOCAL"
        assert RehearsalScene.STALE_COMMAND.value == "STALE_COMMAND"
        assert RehearsalScene.SECURITY_EXPLANATION.value == "SECURITY_EXPLANATION"


class TestSceneOutcome:
    """Tests for SceneOutcome enum."""

    def test_verified_actuation_outcomes(self):
        outcomes = REQUIRED_SCENE_OUTCOMES[RehearsalScene.VERIFIED_ACTUATION]
        assert SceneOutcome.PREDICTION_VALID in outcomes
        assert SceneOutcome.THRESHOLD_CROSSED in outcomes
        assert SceneOutcome.POLICY_DECISION_MADE in outcomes
        assert SceneOutcome.COMMAND_ISSUED in outcomes
        assert SceneOutcome.ACK_RECEIVED in outcomes
        assert SceneOutcome.ELECTRICAL_VERIFIED in outcomes
        assert SceneOutcome.THERMAL_VERIFIED in outcomes

    def test_safe_local_outcomes(self):
        outcomes = REQUIRED_SCENE_OUTCOMES[RehearsalScene.SAFE_LOCAL]
        assert SceneOutcome.DISCONNECT_DETECTED in outcomes
        assert SceneOutcome.MODE_TRANSITION_TO_SAFE_LOCAL in outcomes
        assert SceneOutcome.LOCAL_PROTECTION_ACTIVE in outcomes
        assert SceneOutcome.RECONNECT_SUCCESSFUL in outcomes
        assert SceneOutcome.NO_STALE_COMMAND_REPLAY in outcomes

    def test_stale_command_outcomes(self):
        outcomes = REQUIRED_SCENE_OUTCOMES[RehearsalScene.STALE_COMMAND]
        assert SceneOutcome.STALE_COMMAND_REJECTED in outcomes
        assert SceneOutcome.NO_ACTUATION_ON_STALE in outcomes
        assert SceneOutcome.AUDIT_EVENT_RECORDED in outcomes

    def test_security_explanation_outcomes(self):
        outcomes = REQUIRED_SCENE_OUTCOMES[RehearsalScene.SECURITY_EXPLANATION]
        assert SceneOutcome.TLS_PURPOSE_EXPLAINED in outcomes
        assert SceneOutcome.ACL_PURPOSE_EXPLAINED in outcomes
        assert SceneOutcome.AUTHORIZATION_PURPOSE_EXPLAINED in outcomes
        assert SceneOutcome.TTL_PURPOSE_EXPLAINED in outcomes
        assert SceneOutcome.IDEMPOTENCY_PURPOSE_EXPLAINED in outcomes

    def test_all_scenes_have_required_outcomes(self):
        for scene in RehearsalScene:
            assert scene in REQUIRED_SCENE_OUTCOMES
            assert len(REQUIRED_SCENE_OUTCOMES[scene]) > 0


class TestRehearsalMetrics:
    """Tests for RehearsalMetrics validation."""

    def test_valid_metrics_creation(self):
        metrics = RehearsalMetrics(
            failure_recovery=True,
            operator_clarity=True,
            timing_within_bounds=True,
            end_to_end_latency_ms=150,
        )
        assert metrics.failure_recovery is True
        assert metrics.operator_clarity is True
        assert metrics.timing_within_bounds is True
        assert metrics.end_to_end_latency_ms == 150

    def test_failure_recovery_must_be_bool(self):
        with pytest.raises(TypeError, match="failure_recovery must be a strict boolean"):
            RehearsalMetrics(
                failure_recovery=1,  # type: ignore[arg-type]
                operator_clarity=True,
                timing_within_bounds=True,
            )

    def test_operator_clarity_must_be_bool(self):
        with pytest.raises(TypeError, match="operator_clarity must be a strict boolean"):
            RehearsalMetrics(
                failure_recovery=True,
                operator_clarity="yes",  # type: ignore[arg-type]
                timing_within_bounds=True,
            )

    def test_timing_within_bounds_must_be_bool(self):
        with pytest.raises(TypeError, match="timing_within_bounds must be a strict boolean"):
            RehearsalMetrics(
                failure_recovery=True,
                operator_clarity=True,
                timing_within_bounds=1,  # type: ignore[arg-type]
            )

    def test_latency_must_be_non_negative(self):
        with pytest.raises(ValueError, match="end_to_end_latency_ms must be non-negative"):
            RehearsalMetrics(
                failure_recovery=True,
                operator_clarity=True,
                timing_within_bounds=True,
                end_to_end_latency_ms=-1,
            )

    def test_latency_must_be_int(self):
        with pytest.raises(TypeError, match="end_to_end_latency_ms must be an int"):
            RehearsalMetrics(
                failure_recovery=True,
                operator_clarity=True,
                timing_within_bounds=True,
                end_to_end_latency_ms=150.5,  # type: ignore[arg-type]
            )

    def test_metrics_is_immutable(self):
        metrics = RehearsalMetrics(
            failure_recovery=True,
            operator_clarity=True,
            timing_within_bounds=True,
        )
        with pytest.raises(FrozenInstanceError):
            metrics.failure_recovery = False  # type: ignore[misc]


class TestSceneEvidence:
    """Tests for SceneEvidence validation."""

    def test_valid_evidence_creation(self):
        evidence = SceneEvidence(
            scene=RehearsalScene.VERIFIED_ACTUATION,
            observed_outcomes=frozenset(REQUIRED_SCENE_OUTCOMES[RehearsalScene.VERIFIED_ACTUATION]),
        )
        assert evidence.scene is RehearsalScene.VERIFIED_ACTUATION
        assert len(evidence.observed_outcomes) == 7

    def test_scene_must_be_enum(self):
        with pytest.raises(TypeError, match="scene must be a RehearsalScene"):
            SceneEvidence(
                scene="VERIFIED_ACTUATION",  # type: ignore[arg-type]
                observed_outcomes=frozenset(),
            )

    def test_outcomes_must_be_frozenset(self):
        with pytest.raises(TypeError, match="observed_outcomes must be a frozenset"):
            SceneEvidence(
                scene=RehearsalScene.STALE_COMMAND,
                observed_outcomes={SceneOutcome.STALE_COMMAND_REJECTED},  # type: ignore[arg-type]
            )

    def test_outcomes_must_be_scene_outcome_values(self):
        with pytest.raises(TypeError, match="observed_outcomes must contain SceneOutcome values"):
            SceneEvidence(
                scene=RehearsalScene.STALE_COMMAND,
                observed_outcomes=frozenset({"STALE_COMMAND_REJECTED"}),  # type: ignore[arg-type]
            )

    def test_evidence_is_immutable(self):
        evidence = SceneEvidence(
            scene=RehearsalScene.SAFE_LOCAL,
            observed_outcomes=frozenset(),
        )
        with pytest.raises(FrozenInstanceError):
            evidence.scene = RehearsalScene.STALE_COMMAND  # type: ignore[misc]


class TestSceneAssessment:
    """Tests for SceneAssessment."""

    def test_passing_assessment(self):
        from coldguard_control.demo_rehearsal import _assess_scene

        evidence = SceneEvidence(
            scene=RehearsalScene.STALE_COMMAND,
            observed_outcomes=REQUIRED_SCENE_OUTCOMES[RehearsalScene.STALE_COMMAND],
            observed_sequence=REQUIRED_SCENE_SEQUENCE[RehearsalScene.STALE_COMMAND],
        )
        assessment = _assess_scene(evidence)
        assert assessment.scene is RehearsalScene.STALE_COMMAND
        assert assessment.passed is True
        assert assessment.missing_outcomes == ()

    def test_failing_assessment_with_missing_outcomes(self):
        from coldguard_control.demo_rehearsal import _assess_scene

        evidence = SceneEvidence(
            scene=RehearsalScene.STALE_COMMAND,
            observed_outcomes=frozenset({SceneOutcome.STALE_COMMAND_REJECTED}),
        )
        assessment = _assess_scene(evidence)
        assert assessment.passed is False
        assert SceneOutcome.NO_ACTUATION_ON_STALE in assessment.missing_outcomes
        assert SceneOutcome.AUDIT_EVENT_RECORDED in assessment.missing_outcomes


class TestRehearsalRecord:
    """Tests for RehearsalRecord validation."""

    def _make_complete_evidence(self):
        return tuple(
            SceneEvidence(
                scene=scene,
                observed_outcomes=REQUIRED_SCENE_OUTCOMES[scene],
                observed_sequence=REQUIRED_SCENE_SEQUENCE[scene],
            )
            for scene in RehearsalScene
        )

    def test_wrong_scene_order_blocks_record(self):
        from coldguard_control.demo_rehearsal import _build_rehearsal_record

        evidence = list(self._make_complete_evidence())
        first = evidence[0]
        evidence[0] = SceneEvidence(
            scene=first.scene,
            observed_outcomes=first.observed_outcomes,
            observed_sequence=tuple(reversed(first.observed_sequence)),
        )
        record = _build_rehearsal_record(
            record_id="REC-WRONG-ORDER",
            authority=RehearsalAuthority.HOST_SIMULATED,
            scene_evidence=evidence,
            metrics=self._make_metrics(),
        )
        assert record.all_scenes_pass is False
        assert "INVALID_SCENE_SEQUENCE:VERIFIED_ACTUATION" in record.blockers

    def _make_metrics(self, all_pass=True):
        return RehearsalMetrics(
            failure_recovery=all_pass,
            operator_clarity=all_pass,
            timing_within_bounds=all_pass,
            end_to_end_latency_ms=150,
        )

    def test_complete_record_creation(self):
        from coldguard_control.demo_rehearsal import _build_rehearsal_record

        record = _build_rehearsal_record(
            record_id="REC-01",
            authority=RehearsalAuthority.HOST_SIMULATED,
            scene_evidence=self._make_complete_evidence(),
            metrics=self._make_metrics(),
        )
        assert record.record_id == "REC-01"
        assert record.authority is RehearsalAuthority.HOST_SIMULATED
        assert len(record.scene_evidence) == 4
        assert record.all_scenes_pass is True

    def test_record_id_must_be_nonempty(self):
        with pytest.raises(ValueError, match="record_id must be nonempty"):
            RehearsalRecord(
                record_id="",
                authority=RehearsalAuthority.HOST_SIMULATED,
                scene_evidence=(),
                metrics=self._make_metrics(),
            )

    def test_authority_must_be_enum(self):
        with pytest.raises(TypeError, match="authority must be a RehearsalAuthority"):
            RehearsalRecord(
                record_id="REC-01",
                authority="HOST_SIMULATED",  # type: ignore[arg-type]
                scene_evidence=(),
                metrics=self._make_metrics(),
            )

    def test_missing_scene_blocks_record(self):
        from coldguard_control.demo_rehearsal import _build_rehearsal_record

        record = _build_rehearsal_record(
            record_id="REC-02",
            authority=RehearsalAuthority.HOST_SIMULATED,
            scene_evidence=self._make_complete_evidence()[:-1],  # Missing one scene
            metrics=self._make_metrics(),
        )
        assert record.all_scenes_pass is False
        assert any("MISSING_SCENE:" in b for b in record.blockers)

    def test_duplicate_scene_in_record_rejected(self):
        from coldguard_control.demo_rehearsal import _build_rehearsal_record

        evidence = list(self._make_complete_evidence())
        evidence.append(evidence[0])  # Duplicate first scene
        with pytest.raises(ValueError, match="duplicate scene in record"):
            _build_rehearsal_record(
                record_id="REC-03",
                authority=RehearsalAuthority.HOST_SIMULATED,
                scene_evidence=evidence,
                metrics=self._make_metrics(),
            )

    def test_failed_metrics_block_readiness(self):
        from coldguard_control.demo_rehearsal import _build_rehearsal_record

        record = _build_rehearsal_record(
            record_id="REC-04",
            authority=RehearsalAuthority.HOST_SIMULATED,
            scene_evidence=self._make_complete_evidence(),
            metrics=RehearsalMetrics(
                failure_recovery=False,
                operator_clarity=True,
                timing_within_bounds=True,
            ),
        )
        assert record.all_scenes_pass is False
        assert "FAILURE_RECOVERY_NOT_DEMONSTRATED" in record.blockers

    def test_record_is_immutable(self):
        from coldguard_control.demo_rehearsal import _build_rehearsal_record

        record = _build_rehearsal_record(
            record_id="REC-05",
            authority=RehearsalAuthority.HOST_SIMULATED,
            scene_evidence=self._make_complete_evidence(),
            metrics=self._make_metrics(),
        )
        with pytest.raises(FrozenInstanceError):
            record.all_scenes_pass = False  # type: ignore[misc]


class TestBuildDemoRehearsalRecord:
    """Tests for build_demo_rehearsal_record helper."""

    def test_host_simulated_complete_record(self):
        record = build_demo_rehearsal_record("REC-HOST-01")
        assert record.record_id == "REC-HOST-01"
        assert record.authority is RehearsalAuthority.HOST_SIMULATED
        assert len(record.scene_evidence) == 4
        assert record.all_scenes_pass is True

    def test_live_rehearsal_record(self):
        record = build_demo_rehearsal_record(
            "REC-LIVE-01",
            authority=RehearsalAuthority.LIVE_REHEARSAL,
        )
        assert record.authority is RehearsalAuthority.LIVE_REHEARSAL
        assert record.all_scenes_pass is True

    def test_override_outcomes_allows_partial_scene(self):
        record = build_demo_rehearsal_record(
            "REC-PARTIAL-01",
            override_outcomes={
                RehearsalScene.STALE_COMMAND: frozenset(
                    {SceneOutcome.STALE_COMMAND_REJECTED}
                ),
            },
        )
        stale_assessment = next(
            a for a in record.scene_assessments
            if a.scene is RehearsalScene.STALE_COMMAND
        )
        assert stale_assessment.passed is False
        assert record.all_scenes_pass is False

    def test_high_latency_fails_timing_check(self):
        record = build_demo_rehearsal_record(
            "REC-SLOW-01",
            latency_ms=600,
        )
        assert record.metrics.timing_within_bounds is False
        assert record.all_scenes_pass is False
        assert "TIMING_NOT_WITHIN_BOUNDS" in record.blockers


class TestAssessRehearsal:
    """Tests for assess_rehearsal function."""

    def _make_passing_record(self, record_id: str, authority=RehearsalAuthority.HOST_SIMULATED):
        return build_demo_rehearsal_record(record_id, authority=authority)

    def test_single_host_record_does_not_complete_rehearsal(self):
        decision = assess_rehearsal([self._make_passing_record("REC-01")])
        assert decision.passing_records == 1
        assert decision.live_rehearsal_complete is False
        assert decision.readiness_achieved is False
        assert "INSUFFICIENT_LIVE_REHEARSAL:0/3" in decision.blockers

    def test_three_live_records_complete_rehearsal(self):
        records = [
            build_demo_rehearsal_record(f"REC-LIVE-{i}", authority=RehearsalAuthority.LIVE_REHEARSAL)
            for i in range(1, 4)
        ]
        decision = assess_rehearsal(records)
        assert decision.passing_records == 3
        assert decision.live_rehearsal_complete is True
        assert decision.readiness_achieved is True
        assert decision.blockers == ()

    def test_mixed_authority_counts_live_separately(self):
        records = [
            build_demo_rehearsal_record("REC-LIVE-01", authority=RehearsalAuthority.LIVE_REHEARSAL),
            build_demo_rehearsal_record("REC-HOST-01", authority=RehearsalAuthority.HOST_SIMULATED),
            build_demo_rehearsal_record("REC-HOST-02", authority=RehearsalAuthority.HOST_SIMULATED),
        ]
        decision = assess_rehearsal(records)
        assert decision.passing_records == 3
        assert decision.live_rehearsal_complete is False
        assert "INSUFFICIENT_LIVE_REHEARSAL:1/3" in decision.blockers

    def test_failing_records_contribute_blockers(self):
        failing = build_demo_rehearsal_record(
            "REC-FAIL-01",
            override_outcomes={
                RehearsalScene.SECURITY_EXPLANATION: frozenset(),
            },
        )
        decision = assess_rehearsal([failing])
        assert decision.passing_records == 0
        assert any("MISSING_OUTCOME:SECURITY_EXPLANATION:" in b for b in decision.blockers)

    def test_duplicate_record_id_rejected(self):
        rec = self._make_passing_record("REC-DUP")
        with pytest.raises(ValueError, match="duplicate record_id"):
            assess_rehearsal([rec, rec])

    def test_records_must_be_sequence(self):
        with pytest.raises(TypeError, match="records must be a Sequence"):
            assess_rehearsal("not a sequence")  # type: ignore[arg-type]

    def test_each_record_must_be_rehearsal_record(self):
        with pytest.raises(TypeError, match="each record must be a RehearsalRecord"):
            assess_rehearsal([object()])  # type: ignore[list-item]

    def test_missing_records_counted(self):
        decision = assess_rehearsal([])
        assert decision.missing_records == 3

    def test_decision_is_immutable(self):
        decision = assess_rehearsal([self._make_passing_record("REC-01")])
        with pytest.raises(FrozenInstanceError):
            decision.readiness_achieved = True  # type: ignore[misc]


class TestDoc05DSection55Compliance:
    """Tests verifying Doc 05D section 55 requirements."""

    def test_d_w23_01_verified_actuation_chain(self):
        """D-W23-01: prediction/threshold → policy → command → ACK → current → thermal."""
        outcomes = REQUIRED_SCENE_OUTCOMES[RehearsalScene.VERIFIED_ACTUATION]
        assert SceneOutcome.PREDICTION_VALID in outcomes
        assert SceneOutcome.THRESHOLD_CROSSED in outcomes
        assert SceneOutcome.POLICY_DECISION_MADE in outcomes
        assert SceneOutcome.COMMAND_ISSUED in outcomes
        assert SceneOutcome.ACK_RECEIVED in outcomes
        assert SceneOutcome.ELECTRICAL_VERIFIED in outcomes
        assert SceneOutcome.THERMAL_VERIFIED in outcomes

    def test_d_w23_02_safe_local_full_sequence(self):
        """D-W23-02: disconnect, mode transition, local protection, reconnect, no stale command."""
        outcomes = REQUIRED_SCENE_OUTCOMES[RehearsalScene.SAFE_LOCAL]
        assert SceneOutcome.DISCONNECT_DETECTED in outcomes
        assert SceneOutcome.MODE_TRANSITION_TO_SAFE_LOCAL in outcomes
        assert SceneOutcome.LOCAL_PROTECTION_ACTIVE in outcomes
        assert SceneOutcome.RECONNECT_SUCCESSFUL in outcomes
        assert SceneOutcome.NO_STALE_COMMAND_REPLAY in outcomes

    def test_d_w23_03_stale_command_rejection(self):
        """D-W23-03: controlled replay with rejection."""
        outcomes = REQUIRED_SCENE_OUTCOMES[RehearsalScene.STALE_COMMAND]
        assert SceneOutcome.STALE_COMMAND_REJECTED in outcomes
        assert SceneOutcome.NO_ACTUATION_ON_STALE in outcomes
        assert SceneOutcome.AUDIT_EVENT_RECORDED in outcomes

    def test_d_w23_04_security_explanation_five_purposes(self):
        """D-W23-04: TLS, ACL, authorization, TTL, idempotency distinct purposes."""
        outcomes = REQUIRED_SCENE_OUTCOMES[RehearsalScene.SECURITY_EXPLANATION]
        assert SceneOutcome.TLS_PURPOSE_EXPLAINED in outcomes
        assert SceneOutcome.ACL_PURPOSE_EXPLAINED in outcomes
        assert SceneOutcome.AUTHORIZATION_PURPOSE_EXPLAINED in outcomes
        assert SceneOutcome.TTL_PURPOSE_EXPLAINED in outcomes
        assert SceneOutcome.IDEMPOTENCY_PURPOSE_EXPLAINED in outcomes

    def test_d_w23_05_three_rehearsal_records_required(self):
        """D-W23-05: Three full rehearsals measuring failure recovery, operator clarity, timing."""
        records = [
            build_demo_rehearsal_record(f"REC-{i}", authority=RehearsalAuthority.LIVE_REHEARSAL)
            for i in range(1, 4)
        ]
        decision = assess_rehearsal(records)
        assert decision.live_rehearsal_complete is True
        assert decision.readiness_achieved is True
        for rec in records:
            assert rec.metrics.failure_recovery is True
            assert rec.metrics.operator_clarity is True
            assert rec.metrics.timing_within_bounds is True

    def test_host_simulation_cannot_claim_readiness(self):
        """Host simulation validates contract but cannot claim rehearsal completion."""
        records = [
            build_demo_rehearsal_record(f"REC-HOST-{i}", authority=RehearsalAuthority.HOST_SIMULATED)
            for i in range(1, 4)
        ]
        decision = assess_rehearsal(records)
        assert decision.passing_records == 3
        assert decision.live_rehearsal_complete is False
        assert decision.readiness_achieved is False

    def test_pure_assessment_no_physical_execution(self):
        """Module is pure assessment, no transport/physical execution."""
        record = build_demo_rehearsal_record("REC-PURE-01")
        # Verify no side-effect attributes exist
        assert not hasattr(record, "physical_command_emitted")
        assert not hasattr(record, "transport_executed")
