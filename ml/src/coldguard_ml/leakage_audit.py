"""W11 executable leakage audit (B-W11-06).

Every critical risk in ``ml/leakage-risk-register.md`` is mapped to a concrete
control or an honest non-result. ``PASS`` is emitted only when an executable
probe ran and passed; missing real evidence is reported as
``BLOCKED_BY_MISSING_EVIDENCE`` rather than silently converted to PASS.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .event_evaluator import (
    EventEvaluationError,
    EpisodePolicy,
    WarningSample,
    build_warning_episodes,
)
from .feature_fixtures import build_predictive_control_trajectory, build_trajectory
from .feature_pipeline import FeaturePipelineError, feature_rows
from .feature_registry import FeatureRegistry
from .grouped_evaluation import (
    EvaluationRun,
    GroupingLeakageError,
    LOCKED_TEST_PARTITION,
    PreprocessingLeakageError,
    assert_train_only_fit,
    build_evaluation_runs,
    make_grouped_folds,
    validate_run_population,
)
from .xgb_benchmark import (
    BenchmarkConfig,
    BenchmarkFixture,
    BenchmarkResult,
    ConfigError,
    FeaturePolicy,
    assess_real_admission,
    feature_matrix,
    LabeledSample,
)

PASS = "PASS"
FAIL = "FAIL"
NOT_TESTED = "NOT_TESTED"
NOT_APPLICABLE = "NOT_APPLICABLE"
BLOCKED_BY_MISSING_EVIDENCE = "BLOCKED_BY_MISSING_EVIDENCE"

OWNER = "Member B — AI & Experimental Data"


@dataclass(frozen=True)
class ProbeResult:
    probe_id: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RiskRecord:
    risk_id: str
    title: str
    attack_mechanism: str
    source_api: str
    preventive_check: str
    regression_tests: str
    result: str
    residual_limitation: str
    scientific_consequence: str
    owner: str = OWNER

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "title": self.title,
            "attack_mechanism": self.attack_mechanism,
            "source_api": self.source_api,
            "preventive_check": self.preventive_check,
            "regression_tests": self.regression_tests,
            "observed_audit_result": self.result,
            "residual_limitation": self.residual_limitation,
            "scientific_consequence": self.scientific_consequence,
            "owner": self.owner,
        }


@dataclass(frozen=True)
class LeakageAuditResult:
    records: tuple[RiskRecord, ...]
    probes: tuple[ProbeResult, ...]

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.result] = counts.get(record.result, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [record.to_dict() for record in self.records],
            "probes": [probe.to_dict() for probe in self.probes],
            "summary": self.summary(),
        }

    def to_markdown(self) -> str:
        lines = [
            "# W11 leakage audit",
            "",
            "> W11 software audit. Synthetic fixtures are software controls; "
            "this document is not physical evidence and does not certify a "
            "real predictive dataset.",
            "",
            "## Result summary",
            "",
            "| Result | Count |",
            "|---|---|",
        ]
        for result, count in self.summary().items():
            lines.append(f"| `{result}` | {count} |")
        lines.extend(
            [
                "",
                "`PASS` is only used where the named executable probe ran and "
                "passed. `NOT_TESTED` and `BLOCKED_BY_MISSING_EVIDENCE` are "
                "retained rather than upgraded.",
                "",
                "## Risk register",
                "",
                "| Risk | Attack mechanism | Source/API | Preventive check | "
                "Regression tests | Result | Residual limitation | Scientific consequence |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for record in self.records:
            lines.append(
                "| {risk} | {attack} | {source} | {check} | {tests} | **{result}** | "
                "{residual} | {consequence} |".format(
                    risk=record.risk_id,
                    attack=record.attack_mechanism,
                    source=record.source_api,
                    check=record.preventive_check,
                    tests=record.regression_tests,
                    result=record.result,
                    residual=record.residual_limitation,
                    consequence=record.scientific_consequence,
                )
            )
        lines.extend(
            [
                "",
                "## Executable probes",
                "",
                "| Probe | Result | Detail |",
                "|---|---|---|",
            ]
        )
        for probe in self.probes:
            lines.append(
                f"| `{probe.probe_id}` | **{probe.status}** | {probe.detail} |"
            )
        lines.extend(
            [
                "",
                "## Unresolved evidence dependency",
                "",
                "- `LRK-16` (ambient/day covariate drift) cannot be probed from "
                "the single invalid A capture or from synthetic controls. It "
                "remains `BLOCKED_BY_MISSING_EVIDENCE` until a multi-day, "
                "A-valid physical population exists.",
                "- `LRK-06` (test-set calibration) is `NOT_APPLICABLE`: W11 is a "
                "score-only benchmark and no calibration transform is fitted.",
                "",
            ]
        )
        return "\n".join(lines)


def _expect_raises(
    expected: type[BaseException],
    substring: str,
    fn: Callable[[], Any],
) -> str:
    try:
        fn()
    except expected as exc:
        text = str(exc)
        if substring and substring.lower() not in text.lower():
            raise AssertionError(
                f"expected {expected.__name__} containing {substring!r}, got {text!r}"
            ) from exc
        return text
    except BaseException as exc:
        raise AssertionError(
            f"expected {expected.__name__} containing {substring!r}, got "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(
        f"expected {expected.__name__} containing {substring!r}, but no exception "
        "was raised"
    )


class _FakeSplit:
    def __init__(self, partitions: Mapping[str, str | None]):
        self._partitions = dict(partitions)
        self.group_of = {
            run_id: run_id for run_id, partition in partitions.items() if partition
        }
        self.pair_lineage: tuple[dict[str, Any], ...] = ()

    def partition_of(self, run_id: str) -> str | None:
        return self._partitions.get(run_id)


def _future_mutation_probe(
    fixture: BenchmarkFixture, registry: FeatureRegistry
) -> str:
    candidates = [
        trajectory
        for trajectory in fixture.development_trajectories
        if trajectory.scenario_id == "S2"
    ]
    if not candidates:
        raise AssertionError("no development S2 trajectory for the mutation probe")
    trajectory = sorted(candidates, key=lambda item: item.run_id or "")[0]
    partition = fixture.split.partition_of(trajectory.run_id or "")
    baseline = feature_rows(
        trajectory, registry, partition=partition, split=fixture.split
    )
    mutated_samples = tuple(
        dataclasses.replace(
            sample,
            chamber_c=tuple((role, None if value is None else value + 5.0) for role, value in sample.chamber_c),
            hot_side_c=None if sample.hot_side_c is None else sample.hot_side_c + 5.0,
            door_state="CLOSED",
            applied_cooling="OFF",
            applied_duty=0.0,
            requested_duty_permille=999,
            readback_duty_permille=999,
            cooling_voltage_v=None,
            cooling_current_a=None,
            cooling_power_w=None,
            cooling_energy_counter_wh=None,
            t_air_c=None if sample.t_air_c is None else sample.t_air_c + 5.0,
            rh_pct=None if sample.rh_pct is None else sample.rh_pct + 10.0,
            electrical_quality="INVALID",
            environment_quality="DEGRADED",
            thermal_quality="INVALID",
        )
        if sample.time_s > 60.0
        else sample
        for sample in trajectory.samples
    )
    mutated = feature_rows(
        dataclasses.replace(trajectory, samples=mutated_samples),
        registry,
        partition=partition,
        split=fixture.split,
    )
    left = [row for row in baseline if row.anchor_t_s <= 60.0]
    right = [row for row in mutated if row.anchor_t_s <= 60.0]
    if len(left) != len(right) or any(
        (a.values, a.missing_reasons) != (b.values, b.missing_reasons)
        for a, b in zip(left, right)
    ):
        raise AssertionError("future mutation changed a past feature")
    return f"future observations after 60 s mutated; {len(left)} past anchors unchanged"


def _split_before_windows_probe(
    fixture: BenchmarkFixture,
) -> str:
    trajectory = fixture.development_trajectories[0]
    run_id = trajectory.run_id or ""
    fake = _FakeSplit({run_id: None})
    _expect_raises(
        GroupingLeakageError,
        "not partitioned",
        lambda: build_evaluation_runs(
            [trajectory],
            fake,
            hardware_config_by_run={run_id: fixture.hardware_config_by_run[run_id]},
        ),
    )
    return "an unpartitioned run is refused before any feature window is built"


def _locked_test_probe(fixture: BenchmarkFixture) -> str:
    test_runs = set(fixture.test_runs)
    trajectories = [
        trajectory
        for trajectory in fixture.trajectories
        if trajectory.run_id in test_runs
    ]
    if not trajectories:
        raise AssertionError("fixture has no locked test trajectory")
    trajectory = trajectories[0]
    _expect_raises(
        GroupingLeakageError,
        "locked test",
        lambda: build_evaluation_runs(
            [trajectory],
            fixture.split,
            hardware_config_by_run={
                trajectory.run_id: fixture.hardware_config_by_run[trajectory.run_id]
            },
        ),
    )
    _expect_raises(
        GroupingLeakageError,
        "locked-test",
        lambda: validate_run_population(
            [
                EvaluationRun(
                    run_id=trajectory.run_id,
                    group_id="TEST-GROUP",
                    pair_id=None,
                    source_sha256=trajectory.source_sha256,
                    physical_source_key=trajectory.physical_source_key,
                    scenario_id=trajectory.scenario_id or "S2",
                    controller_id=trajectory.controller_id or "OBSERVATIONAL",
                    hardware_config_id=fixture.hardware_config_by_run[trajectory.run_id],
                    partition=LOCKED_TEST_PARTITION,
                )
            ]
        ),
    )
    return "locked-test runs are refused by the run builder and the fold validator"


def _predictive_probe(fixture: BenchmarkFixture) -> str:
    trajectory, _ = build_predictive_control_trajectory()
    run_id = trajectory.run_id or ""
    fake = _FakeSplit({run_id: "train"})
    _expect_raises(
        GroupingLeakageError,
        "predictive",
        lambda: build_evaluation_runs(
            [trajectory],
            fake,
            hardware_config_by_run={run_id: fixture.hardware_config_by_run.get(run_id, "CG-HW")},
        ),
    )
    return "a Controller B interventional trajectory is refused for observational training"


def _grouped_disjoint_probe() -> str:
    runs = [
        EvaluationRun(
            run_id=f"R{index}",
            group_id=f"PAIR-{index // 2}",
            pair_id=f"PAIR-{index // 2}",
            source_sha256=f"source-{index}",
            physical_source_key=f"source-{index}:boot",
            scenario_id="S2",
            controller_id="CONTROLLER-A",
            hardware_config_id="CG-HW",
            partition="train",
        )
        for index in range(8)
    ]
    cv = make_grouped_folds(runs, n_splits=4, seed=42)
    expected = {run.run_id for run in runs}
    for fold in cv.folds:
        if set(fold.train_runs) & set(fold.validation_runs):
            raise AssertionError("train and validation runs overlap")
        if set(fold.train_groups) & set(fold.validation_groups):
            raise AssertionError("train and validation groups overlap")
        if set(fold.train_runs) | set(fold.validation_runs) != expected:
            raise AssertionError("fold does not cover the development population")
    return "4 grouped folds are disjoint and cover every development run once"


def _pair_preservation_probe() -> str:
    runs = [
        EvaluationRun(
            run_id=f"R{index}",
            group_id=f"PAIR-{index // 2}",
            pair_id=f"PAIR-{index // 2}",
            source_sha256=f"source-{index}",
            physical_source_key=f"source-{index}:boot",
            scenario_id="S2",
            controller_id="CONTROLLER-A",
            hardware_config_id="CG-HW",
            partition="train",
        )
        for index in range(8)
    ]
    cv = make_grouped_folds(runs, n_splits=4, seed=42)
    for fold in cv.folds:
        train = set(fold.train_runs)
        validation = set(fold.validation_runs)
        for pair_id in {run.pair_id for run in runs}:
            members = {run.run_id for run in runs if run.pair_id == pair_id}
            sides = {
                "train" if run_id in train else "validation" for run_id in members
            }
            if len(sides) != 1:
                raise AssertionError(f"pair {pair_id} straddles folds")
    return "every paired S1/S2 arm stays inside one fold side"


def _gate_bypass_probe() -> str:
    forged = {
        "physical_gate": {
            "observed_status": "GREEN",
            "evidence_sha256": ["0" * 64],
            "scenario": "S1",
        },
        "runs": [],
        "data_origin": "MEASURED_PHYSICAL_DATA",
        "synthetic_control": False,
        "completeness_policy": {
            "thresholds": [
                {
                    "threshold_status": "FROZEN",
                    "freeze_evidence": "forged",
                }
            ]
        },
    }
    decision = assess_real_admission(forged, capture=None, capture_sha256=None)
    if decision.allowed:
        raise AssertionError("a forged GREEN manifest admitted real training")
    if "SOURCE_HASH_NOT_BOUND_BY_W08" not in decision.reasons:
        raise AssertionError("the bypass refusal did not name the source binding")
    return "a forged GREEN manifest without a matching W08 receipt is refused"


def _duplicate_source_probe(fixture: BenchmarkFixture) -> str:
    trajectory = fixture.development_trajectories[0]
    run_a = EvaluationRun(
        run_id="DUP-RUN-A",
        group_id="DUP-GROUP-A",
        pair_id=None,
        source_sha256=trajectory.source_sha256,
        physical_source_key=trajectory.physical_source_key,
        scenario_id="S2",
        controller_id="CONTROLLER-A",
        hardware_config_id="CG-HW",
        partition="train",
    )
    run_b = dataclasses.replace(
        run_a, run_id="DUP-RUN-B", group_id="DUP-GROUP-B"
    )
    _expect_raises(
        GroupingLeakageError,
        "physical source",
        lambda: validate_run_population([run_a, run_b]),
    )
    return "two export views of one physical source are refused as independent groups"


def _duplicate_delivery_probe() -> str:
    policy = EpisodePolicy(
        policy_version="w11-audit-duplicate-v1",
        min_persistence_s=0.0,
        bridge_gap_s=2.0,
        bridge_unknown_gaps=False,
        status="AUDIT_ONLY",
        source="W11 leakage audit",
    )
    samples = (
        WarningSample(time_s=0.0, state="WARNING", sample_id="S1"),
        WarningSample(time_s=1.0, state="NO_WARNING", sample_id="S1"),
    )
    _expect_raises(
        EventEvaluationError,
        "contradictory duplicate",
        lambda: build_warning_episodes(
            samples,
            policy,
            run_id="RUN-DUP",
            source_sha256="d" * 64,
            synthetic_control=True,
        ),
    )
    return "a contradictory duplicate delivery fails closed in episode construction"


def _boot_probe() -> str:
    trajectory, _ = build_trajectory(
        "CG-W11-AUDIT-BOOT-001", scenario="S2", seed=1500, door_start_s=40.0
    )
    samples = list(trajectory.samples)
    samples[2] = dataclasses.replace(samples[2], boot_id="BOOT-OTHER")
    _expect_raises(
        FeaturePipelineError,
        "belongs to boot",
        lambda: dataclasses.replace(trajectory, samples=tuple(samples)),
    )
    return "a mixed-boot trajectory is refused before feature computation"


def _training_only_probe() -> str:
    _expect_raises(
        PreprocessingLeakageError,
        "non-training groups",
        lambda: assert_train_only_fit({"G1"}, {"G1", "G2"}),
    )
    return "a transform fitted on validation groups identifies and refuses the illegal population"


def _label_schema_probe(registry: FeatureRegistry) -> str:
    policy = FeaturePolicy(
        allowlist=("critical_event_time_s",),
        excluded_diagnostic_features=(),
        prohibited_fields=("critical_event_time_s",),
    )
    _expect_raises(
        ConfigError,
        "not in the frozen registry",
        lambda: policy.assert_safe(registry),
    )
    return "a future critical-event field cannot enter the feature allowlist"


def _missing_not_zero_probe() -> str:
    sample = LabeledSample(
        run_id="RUN-NAN",
        group_id="GROUP-NAN",
        partition="train",
        source_sha256="e" * 64,
        sample_identity="NAN:1",
        anchor_t_s=0.0,
        features=(float("nan"), 1.0),
        y=0,
        series_id="series",
    )
    matrix, _ = feature_matrix([sample], ("electrical_power_w", "other"))
    if matrix.shape != (1, 2) or not np.isnan(matrix[0, 0]) or matrix[0, 0] == 0:
        raise AssertionError("missing electrical value was not preserved as NaN")
    return "a missing/UNKNOWN electrical value becomes NaN, never a silent zero"


def _hardware_probe(fixture: BenchmarkFixture) -> str:
    trajectories = list(fixture.development_trajectories[:2])
    if len(trajectories) < 2:
        raise AssertionError("fixture needs two development runs")
    hardware = {
        trajectory.run_id: (
            "CG-HW-A" if index == 0 else "CG-HW-B"
        )
        for index, trajectory in enumerate(trajectories)
    }
    _expect_raises(
        GroupingLeakageError,
        "more than one hardware",
        lambda: build_evaluation_runs(
            trajectories, fixture.split, hardware_config_by_run=hardware
        ),
    )
    return "mixed hardware/config lineages are refused as non-comparable"


def _metric_probe(
    config: BenchmarkConfig, benchmark: BenchmarkResult | None
) -> str:
    if config.primary_metric != "AVERAGE_PRECISION":
        raise AssertionError("primary metric is not predeclared AP")
    if config.raw.get("imbalance", {}).get("selection_rule") != (
        "PREDECLARED_AP_ALL_FOLDS_REPORTED"
    ):
        raise AssertionError("strategy selection rule is not predeclared")
    if benchmark is not None:
        strategies = {row.strategy for row in benchmark.fold_runs}
        if strategies != set(config.strategies):
            raise AssertionError("not every predeclared strategy is reported")
        for fold in benchmark.cv.folds:
            if not any(row["fold_id"] == fold.fold_id for row in benchmark.baseline_rows):
                raise AssertionError(f"fold {fold.fold_id} is missing from the report")
    return "AP and every predeclared strategy/fold are reported; no best-fold selection"


def _run_probe(
    probe_id: str,
    fn: Callable[[], str],
) -> ProbeResult:
    try:
        detail = fn()
        return ProbeResult(probe_id, PASS, detail)
    except BaseException as exc:
        return ProbeResult(probe_id, FAIL, f"{type(exc).__name__}: {exc}")


def run_leakage_audit(
    fixture: BenchmarkFixture,
    registry: FeatureRegistry,
    config: BenchmarkConfig,
    *,
    benchmark: BenchmarkResult | None = None,
) -> LeakageAuditResult:
    probes = [
        _run_probe("future_mutation", lambda: _future_mutation_probe(fixture, registry)),
        _run_probe("split_before_windows", lambda: _split_before_windows_probe(fixture)),
        _run_probe("grouped_disjoint", _grouped_disjoint_probe),
        _run_probe("pair_preservation", _pair_preservation_probe),
        _run_probe("locked_test", lambda: _locked_test_probe(fixture)),
        _run_probe("predictive_intervention", lambda: _predictive_probe(fixture)),
        _run_probe("duplicate_source", lambda: _duplicate_source_probe(fixture)),
        _run_probe("duplicate_delivery", _duplicate_delivery_probe),
        _run_probe("boot_boundary", _boot_probe),
        _run_probe("train_only_transform", _training_only_probe),
        _run_probe("label_schema", lambda: _label_schema_probe(registry)),
        _run_probe("missing_not_zero", _missing_not_zero_probe),
        _run_probe("hardware_identity", lambda: _hardware_probe(fixture)),
        _run_probe("metric_predeclared", lambda: _metric_probe(config, benchmark)),
        _run_probe("gate_b_bypass", _gate_bypass_probe),
    ]
    by_id = {probe.probe_id: probe for probe in probes}

    def result_for(probe_id: str) -> str:
        probe = by_id[probe_id]
        return probe.status

    records = (
        RiskRecord(
            "LRK-01",
            "Random row split",
            "Rows or windows from one run land in both train and validation.",
            "grouped_evaluation.make_grouped_folds / validate_folds",
            "The split API accepts runs and effective groups, never rows; train and validation groups must be disjoint.",
            "test_grouped_evaluation.py::test_folds_are_group_disjoint_and_deterministic",
            result_for("grouped_disjoint"),
            "The audit cannot prove a future caller will not build a row-level dataset outside this API.",
            "A row split would overstate AP by memorising one run's thermal history.",
        ),
        RiskRecord(
            "LRK-02",
            "Window before split",
            "Overlapping windows are generated before run partition and leak across folds.",
            "xgb_benchmark.build_labeled_dataset / feature_rows(split=...)",
            "Features and labels are built only for runs whose split partition is development; an unpartitioned run is refused.",
            "test_grouped_evaluation.py::test_unpartitioned_run_is_refused",
            result_for("split_before_windows"),
            "The benchmark trusts the supplied split identity; a forged split is outside this software control.",
            "Window-before-split can make empty folds look separable.",
        ),
        RiskRecord(
            "LRK-03",
            "Future rolling feature",
            "A rolling statistic uses samples after the anchor.",
            "feature_pipeline.feature_rows",
            "Future mutation/truncation probes must leave every past feature byte-identical.",
            "test_w11_leakage.py::test_future_mutation_invariance",
            result_for("future_mutation"),
            "Covers the registered feature set only.",
            "Future leakage would make the model clairvoyant at prediction time.",
        ),
        RiskRecord(
            "LRK-04",
            "Future command/state",
            "A command, door or electrical state after t enters X_t.",
            "feature_pipeline._compute_one",
            "The same future mutation probe mutates all post-anchor command/state fields.",
            "test_w11_leakage.py::test_future_mutation_invariance",
            result_for("future_mutation"),
            "Feature definitions are frozen only by the W10 registry identity.",
            "A post-intervention state in X cannot be known by Controller A.",
        ),
        RiskRecord(
            "LRK-05",
            "Global imputation/scaling",
            "An imputer or scaler is fitted on the union of training and validation groups.",
            "grouped_evaluation.assert_train_only_fit",
            "The API refuses any fit population that includes a non-training group; XGBoost's native NaN handling makes a global imputer unnecessary.",
            "test_grouped_evaluation.py::test_fit_population_must_be_train_only",
            result_for("train_only_transform"),
            "A caller could implement a transform outside this API.",
            "Validation statistics would leak the validation distribution into training.",
        ),
        RiskRecord(
            "LRK-06",
            "Test-set calibration",
            "A calibrator is fitted on the locked test partition.",
            "xgb_benchmark.score_semantics = risk_score",
            "No calibration is performed; outputs are labelled risk_score and calibration_status is NOT_PERFORMED.",
            "test_xgb_benchmark.py::test_outputs_are_risk_scores_not_probabilities",
            NOT_APPLICABLE,
            "If calibration is added later, it must be fitted on grouped development data only.",
            "Uncalibrated scores must not be called physical probabilities.",
        ),
        RiskRecord(
            "LRK-07",
            "Test-set threshold selection",
            "A decision threshold is tuned using locked-test outcomes.",
            "grouped_evaluation.validate_run_population / risk_threshold",
            "The operating threshold is predeclared in the config; locked-test runs are refused before prediction.",
            "test_w11_leakage.py::test_locked_test_boundary",
            result_for("locked_test"),
            "The numeric 0.5 is an illustrative development operating point, not a tuned test result.",
            "Test-tuned thresholds overstate deployable performance.",
        ),
        RiskRecord(
            "LRK-08",
            "Near-duplicate groups",
            "A renamed export or second view of one boot is counted as another run.",
            "grouped_evaluation.validate_run_population",
            "Each source hash and physical_source_key may belong to exactly one run and one effective group.",
            "test_grouped_evaluation.py::test_duplicate_physical_source_is_refused; "
            "test_grouped_evaluation.py::test_pair_lineage_never_straddles_folds",
            result_for("duplicate_source"),
            "Source identity is only as strong as the W04/W08 provenance.",
            "Duplicate exports inflate the apparent independent population.",
        ),
        RiskRecord(
            "LRK-09",
            "Predictive intervention contamination",
            "A Controller B interventional trajectory is used as an observational negative.",
            "grouped_evaluation.build_evaluation_runs",
            "Predictive controller ids are refused for observational training.",
            "test_grouped_evaluation.py::test_predictive_controller_is_refused",
            result_for("predictive_intervention"),
            "Controller id strings are a declared contract, not a hardware attestation.",
            "An event prevented by intervention is an unobserved counterfactual, not a negative.",
        ),
        RiskRecord(
            "LRK-10",
            "Future label into feature",
            "Critical-event time, y or a post-intervention outcome is inserted into X.",
            "xgb_benchmark.FeaturePolicy.assert_safe",
            "The explicit allowlist must contain only frozen registry features; provenance/target fields are rejected.",
            "test_xgb_benchmark.py::test_identifier_and_label_fields_cannot_enter_x",
            result_for("label_schema"),
            "A caller could bypass the config loader and construct a custom matrix.",
            "Label leakage yields a near-perfect but meaningless AP.",
        ),
        RiskRecord(
            "LRK-11",
            "Locked test peeking",
            "P3 outcomes are inspected during W11 development.",
            "grouped_evaluation.build_evaluation_runs / validate_run_population",
            "Locked-test runs are refused by both the run builder and fold validator; the W10 test pair is untouched.",
            "test_grouped_evaluation.py::test_locked_test_run_is_refused",
            result_for("locked_test"),
            "No real P3 population exists yet; W12 owns the locked-test boundary.",
            "Any test peek invalidates the later Gate G3 report.",
        ),
        RiskRecord(
            "LRK-12",
            "Duplicate delivery",
            "A repeated sample delivery is treated as a new independent observation.",
            "feature_pipeline._dedupe_samples / event_evaluator.build_warning_episodes",
            "Contradictory duplicate identities fail closed; identical duplicates are deduplicated.",
            "test_w11_leakage.py::test_contradictory_duplicate_delivery_is_refused",
            result_for("duplicate_delivery"),
            "Adapter-level dedup depends on the quality of sample identity.",
            "Repeated deliveries can inflate sample counts and apparent warning episodes.",
        ),
        RiskRecord(
            "LRK-13",
            "Boot/time semantics",
            "Samples from separate boots are stitched onto one time axis.",
            "feature_pipeline.Trajectory.__post_init__",
            "A trajectory is one device/boot acquisition domain; mixed boots are refused and must be partitioned by an adapter.",
            "test_feature_causality.py::test_direct_constructor_refuses_mixed_boot_samples",
            result_for("boot_boundary"),
            "Boot-scoped uptime is not absolute UTC; W11 real admission requires EVENT_UTC.",
            "Cross-boot continuity fabricates thermal history that never existed.",
        ),
        RiskRecord(
            "LRK-14",
            "Missing electrical equals zero",
            "UNKNOWN electrical quality is silently filled with 0 W or 0 A.",
            "xgb_benchmark.feature_matrix",
            "None/absent values become NaN; the matrix never substitutes zero.",
            "test_xgb_benchmark.py::test_missing_electrical_is_nan_not_zero",
            result_for("missing_not_zero"),
            "The model treats NaN natively; missingness semantics remain an assumption of the fixture.",
            "Zero-filling would fabricate a measured no-load state.",
        ),
        RiskRecord(
            "LRK-15",
            "Hardware/config identity",
            "Runs from different hardware or configuration lineages are pooled.",
            "grouped_evaluation.build_evaluation_runs",
            "More than one hardware/config lineage in development is refused.",
            "test_grouped_evaluation.py::test_mixed_hardware_lineage_is_refused",
            result_for("hardware_identity"),
            "The single-rig fixture has no real multi-lineage evidence.",
            "Pooled hardware can confound thermal behaviour with model skill.",
        ),
        RiskRecord(
            "LRK-16",
            "Ambient/day covariate drift",
            "A model learns ambient or day-specific context that is not stable for deployment.",
            "W11 real admission gate",
            "No multi-day, A-valid physical population exists to probe drift.",
            "none executed",
            BLOCKED_BY_MISSING_EVIDENCE,
            "Needs a qualified multi-day physical dataset; synthetic fixtures cannot establish drift.",
            "Deployment performance may degrade when ambient conditions change.",
        ),
        RiskRecord(
            "LRK-17",
            "Metric/definition shopping",
            "The best-looking fold or metric is selected after seeing outcomes.",
            "xgb_benchmark.primary_metric / imbalance.selection_rule",
            "AP and all predeclared folds/strategies are reported; no post-hoc best-fold selection.",
            "test_xgb_benchmark.py::test_all_folds_and_strategies_are_reported",
            result_for("metric_predeclared"),
            "A human could still selectively quote a favorable fold; the report keeps every fold visible.",
            "Selective reporting overstates the benchmark.",
        ),
    )
    return LeakageAuditResult(records=records, probes=tuple(probes))
