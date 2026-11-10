"""W18 runtime-monitoring driver (B-W18-01...04).

Consumes the immutable W15/W16/W17 artifacts and the read-only Member A W18
dossier, runs the read-only monitors, records adversarial controls and writes a
deterministic W18 report family.  It never dispatches a command, connects to a
device or broker, mutates a model/policy artifact, or opens the W16 holdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from coldguard_ml.feature_registry import load_registry
from coldguard_ml.w15_artifact import load_guarded_artifact
from coldguard_ml.w18_freeze_audit import (
    CHANGE_REQUIRED_FIELDS,
    assess_change_request,
    compare_freeze_state,
    load_pinned_baseline,
    observe_protected_values,
    verify_model_file_binding,
)
from coldguard_ml.w18_readiness import assess_controller_b_readiness
from coldguard_ml.w18_runtime_monitor import (
    DIMENSION_FEATURE,
    DIMENSION_FRESHNESS,
    DIMENSION_MODEL,
    DIMENSION_PREDICTION,
    MONITOR_SOFTWARE_VALID,
    REFUSED_EVIDENCE_CLASS,
    REFUSED_FEATURE_IDENTITY,
    REFUSED_MODEL_IDENTITY,
    REFUSED_POLICY_UNFROZEN,
    REFUSED_PREDICTION_SEMANTICS,
    REFUSED_RELEASE_AUTHORIZATION,
    REFUSED_STALE_INPUT,
    REFUSED_TEMPORAL_ORDER,
    STATUS_FAIL,
    STATUS_NOT_VERIFIED,
    STATUS_PASS,
    expected_runtime_identity,
    monitor_runtime_records,
    policy_expectation_from_w17_header,
)
from coldguard_ml.w18_trace_integrity import (
    TRACE_COMPLETE_SOFTWARE_FIXTURE,
    TRACE_INCONSISTENT_IDENTITY,
    TRACE_NOT_AUTHORIZED,
    TRACE_PARTIAL_MISSING_EVIDENCE,
    TRACE_PHYSICAL_UNVERIFIED,
    TRACE_TEMPORAL_CONTRADICTION,
    assess_trace,
    build_test_only_fixture,
    summarize_w17_replay_trace,
)
from coldguard_ml.xgb_benchmark import load_benchmark_config

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
W15_MODEL_DIR = ML_ROOT / "reports" / "W15" / "model"
W15_MODEL_MANIFEST = W15_MODEL_DIR / "model-manifest-W15.json"
W15_MODEL_FILE = W15_MODEL_DIR / "model.ubj"
W16_MANIFEST = ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"
W17_DIR = ML_ROOT / "reports" / "W17"
W17_MANIFEST = W17_DIR / "w17-manifest.json"
W17_TRACE = W17_DIR / "shadow-trace-W17.json"
W18_DIR = ML_ROOT / "reports" / "W18"
FREEZE_BASELINE = W18_DIR / "freeze-baseline-W18.json"
A_W18_DIR = REPO_ROOT / "evidence" / "A" / "W18"

W18_LAYER_VERSION = "coldguard-w18-runtime-monitoring-v1"
W18_BASE_REVISION = "d3de0716f9694b37a6da50fd3935534bfe14038c"
W18_BASE_REVISION_SEMANTICS = "W17_STACK_HEAD_BASE_NOT_W18_DELIVERY_COMMIT"

EXPECTED_REPORTS = (
    "runtime-monitor-W18.md",
    "predictive-trace-W18.md",
    "no-online-tuning-W18.md",
    "controller-b-readiness-W18.md",
)

EXTERNAL_DEPENDENCIES = {
    "member_a_w18_physical_dry_runs": "ZERO_DRY_RUNS_RECORDED_SOFTWARE_READY_ONLY",
    "member_a_w18_signoff": "BLOCKED_ON_PREREQUISITES",
    "member_c_pr_73_shadow_trace": "OPEN_UNMERGED_NOT_INTEGRATION_ACCEPTANCE",
    "member_c_pr_74_controller_b_lifecycle": "OPEN_UNMERGED_NOT_FROZEN_API",
    "member_d_predictive_policy": "NOT_FROZEN",
    "member_d_physical_verification_interface": "UNMERGED_STACKED_BRANCH",
    "runtime_freshness_policy": "PENDING_C_D",
    "model_release_candidate": "NOT_ISSUED",
    "gate_g4": "NOT_READY",
    "w16_holdout": "NOT_OPENED",
    "team_lead_cross_member_acceptance": "NOT_ESTABLISHED",
}

EXTERNAL_REVISIONS = {
    "member_c": {
        "pr_73": {
            "state": "OPEN",
            "head": "fb71b3c87bf140732cc85c520baf630d38ae18cb",
            "base": "feat/c-w16-outage-resynchronization",
            "title": "Member C W17 shadow trace and timing audit",
        },
        "pr_74": {
            "state": "OPEN",
            "head": "27c654be0eaaa477d7fc92576f1d3c355e2d06c0",
            "base": "feat/c-w17-shadow-trace",
            "title": "Member C W18 approved dispatch and verification",
        },
        "interface_semantics": "UNMERGED_INTERFACE_NAMES_ARE_NOT_A_FROZEN_API",
    },
    "member_d": {
        "merged_policy_contract": "control/src/coldguard_control/policy.py (origin/main)",
        "predictive_policy_status": "NOT_FROZEN",
        "physical_verification_interface": (
            "feat/d-w10-w13-diagnosis-predictive-stacked@7e9aad6 UNMERGED"
        ),
        "authority": "D owns policy authorization and control authority",
    },
}

EVIDENCE_LABELS = (
    "Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17 and Member A "
    "files), SYNTHETIC_SOFTWARE_FIXTURE (W17 replay and TEST_ONLY fixture), "
    "DERIVED_SOFTWARE_ASSERTION (monitor/trace/freeze/readiness results), "
    "EXTERNAL_DEPENDENCY (A/C/D interface snapshots), NOT_VERIFIED (absent "
    "live/physical evidence)."
)

A_W18_FILES = (
    "controller-B-dry-run-index.json",
    "pre-run-safety-checklist.json",
    "readiness-signoff.md",
    "abort-criteria.yaml",
    "registry/A-W18-01.json",
    "registry/publication-index.json",
    "SHA256SUMS.txt",
    "validate_w18.py",
)


class W18DriverError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    _write(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
    )


def _analysis_code_sha256() -> str:
    files = [
        ML_ROOT / "src" / "coldguard_ml" / "w18_runtime_monitor.py",
        ML_ROOT / "src" / "coldguard_ml" / "w18_trace_integrity.py",
        ML_ROOT / "src" / "coldguard_ml" / "w18_freeze_audit.py",
        ML_ROOT / "src" / "coldguard_ml" / "w18_readiness.py",
        ML_ROOT / "scripts" / "w18-runtime-audit-W18.py",
        ML_ROOT / "tests" / "test_w18_runtime_monitor.py",
        ML_ROOT / "tests" / "test_w18_trace_integrity.py",
        ML_ROOT / "tests" / "test_w18_freeze_audit.py",
        ML_ROOT / "tests" / "test_w18_delivery.py",
        ML_ROOT / "tests" / "test_w18_readiness.py",
    ]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(ML_ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise W18DriverError(f"{label} is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _member_a_state() -> dict[str, Any]:
    index = _read_json(
        A_W18_DIR / "controller-B-dry-run-index.json", "Member A dry-run index"
    )
    checklist = _read_json(
        A_W18_DIR / "pre-run-safety-checklist.json", "Member A pre-run checklist"
    )
    files: dict[str, Any] = {}
    for relative in A_W18_FILES:
        path = A_W18_DIR / relative
        files[relative] = {
            "sha256": _sha256(path) if path.is_file() else None,
            "present": path.is_file(),
        }
    dry_runs = index.get("dry_runs_recorded")
    if not isinstance(dry_runs, int) or isinstance(dry_runs, bool):
        raise W18DriverError(
            "Member A W18 dry-run index does not declare an integer run count"
        )
    return {
        "dry_runs_recorded": dry_runs,
        "index_status": index.get("status"),
        "enablement_verdict": checklist.get("enablement_verdict"),
        "physical_state": checklist.get("physical_state"),
        "cross_team_prerequisites": checklist.get("cross_team_prerequisites"),
        "files": files,
        "observed": (
            f"dry_runs_recorded={dry_runs}; "
            f"enablement={checklist.get('enablement_verdict')}; "
            f"physical_state={checklist.get('physical_state')}"
        ),
    }


def _clone(payload: Any) -> Any:
    return json.loads(json.dumps(payload))


def _monitor_probes(
    record: Mapping[str, Any], expected: Any, policy: Any
) -> list[dict[str, Any]]:
    probes: list[tuple[str, str, dict[str, Any]]] = []

    def add(name: str, expected_verdict: str, mutate) -> None:
        candidate = _clone(record)
        mutate(candidate)
        probes.append((name, expected_verdict, candidate))

    def drop_anchor(candidate: dict[str, Any]) -> None:
        candidate.pop("prediction_anchor_event_s", None)

    add(
        "wrong_model_sha",
        REFUSED_MODEL_IDENTITY,
        lambda c: c["model"].__setitem__("model_artifact_sha256", "0" * 64),
    )
    add(
        "wrong_config_binding",
        REFUSED_MODEL_IDENTITY,
        lambda c: c["model"].__setitem__("model_config_sha256", "1" * 64),
    )
    add(
        "wrong_library_version",
        REFUSED_MODEL_IDENTITY,
        lambda c: c["model"].__setitem__("model_library_version", "9.9.9"),
    )
    add(
        "missing_model_identity",
        REFUSED_MODEL_IDENTITY,
        lambda c: c.__setitem__("model", {}),
    )
    add(
        "wrong_ordered_feature_hash",
        REFUSED_FEATURE_IDENTITY,
        lambda c: c.__setitem__("ordered_feature_ids_sha256", "2" * 64),
    )
    add(
        "feature_vector_tamper",
        REFUSED_FEATURE_IDENTITY,
        lambda c: c.__setitem__("feature_vector_sha256", "3" * 64),
    )

    def zero_fill(candidate: dict[str, Any]) -> None:
        candidate["features"][0]["value"] = 0.0
        candidate["features"][0]["missing_reason"] = "MISSING_INPUT"

    add("missing_value_zero_filled", REFUSED_FEATURE_IDENTITY, zero_fill)
    add(
        "release_authorization_claim",
        REFUSED_RELEASE_AUTHORIZATION,
        lambda c: c["model"].__setitem__("registered_for_operation", True),
    )
    add(
        "release_eligibility_claim",
        REFUSED_RELEASE_AUTHORIZATION,
        lambda c: c["model"].__setitem__(
            "release_eligibility", "APPROVED_RELEASE_CANDIDATE"
        ),
    )
    add(
        "physical_evidence_class_claim",
        REFUSED_EVIDENCE_CLASS,
        lambda c: c.__setitem__("evidence_class", "REAL_PHYSICAL_EVIDENCE"),
    )
    add(
        "threshold_claimed_frozen",
        REFUSED_POLICY_UNFROZEN,
        lambda c: c["hypothetical_warning"].__setitem__(
            "rule_status", "FROZEN_APPROVED"
        ),
    )
    add(
        "dispatchable_policy_claim",
        REFUSED_RELEASE_AUTHORIZATION,
        lambda c: c["hypothetical_policy"].__setitem__("dispatchable", True),
    )

    def stale_with_score(candidate: dict[str, Any]) -> None:
        candidate["freshness"] = {
            "verdict": "REFUSED_STALE_INPUT",
            "disposition": "REFUSED_STALE_INPUT",
            "reasons": ["TEST_PROBE_STALE_INPUT"],
            "policy_status": "RUNTIME_FRESHNESS_POLICY_PENDING_C_D",
            "anchor_age_s": 999.0,
            "electrical_age_s": 999.0,
            "door_age_s": 999.0,
            "late_observation_ids": [],
            "sanitized_input_ids": [],
        }

    add("stale_input_with_score", REFUSED_STALE_INPUT, stale_with_score)
    add(
        "fresh_input_without_score",
        REFUSED_PREDICTION_SEMANTICS,
        lambda c: c.__setitem__("risk_score", None),
    )

    def future_window(candidate: dict[str, Any]) -> None:
        candidate["input_window_end_s"] = float(
            candidate["prediction_anchor_event_s"]
        ) + 5.0

    add("future_observation_in_prediction", REFUSED_TEMPORAL_ORDER, future_window)
    add("missing_event_time_provenance", REFUSED_TEMPORAL_ORDER, drop_anchor)

    results = []
    for name, expected_verdict, candidate in probes:
        result = _monitor_one(candidate, expected, policy)
        results.append(
            {
                "probe": name,
                "expected_verdict": expected_verdict,
                "observed_verdict": result.verdict,
                "passed": result.verdict == expected_verdict,
                "refusal_reasons": list(result.refusal_reasons),
            }
        )
    return results


def _monitor_one(record: Mapping[str, Any], expected: Any, policy: Any):
    from coldguard_ml.w18_runtime_monitor import monitor_runtime_record

    return monitor_runtime_record(record, expected=expected, policy=policy)


def _trace_probes(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    probes: list[tuple[str, str, dict[str, Any]]] = []

    def add(name: str, expected_outcome: str, mutate) -> None:
        candidate = _clone(fixture)
        mutate(candidate)
        probes.append((name, expected_outcome, candidate))

    def remove_downstream(candidate: dict[str, Any]) -> None:
        for stage in ("command", "ack", "applied_state", "physical_verification"):
            candidate.pop(stage, None)

    add(
        "missing_downstream_stages",
        TRACE_PARTIAL_MISSING_EVIDENCE,
        remove_downstream,
    )
    add(
        "missing_applied_state",
        TRACE_PARTIAL_MISSING_EVIDENCE,
        lambda c: c.pop("applied_state", None),
    )
    add(
        "command_prediction_mismatch",
        TRACE_INCONSISTENT_IDENTITY,
        lambda c: c["command"].__setitem__("prediction_id", "pred-other-run"),
    )
    add(
        "policy_run_mismatch",
        TRACE_INCONSISTENT_IDENTITY,
        lambda c: c["policy"].__setitem__("run_id", "run-other"),
    )
    add(
        "ack_before_command",
        TRACE_TEMPORAL_CONTRADICTION,
        lambda c: c["ack"].__setitem__("acknowledged_event_s", 100.9),
    )

    def ack_shortcut(candidate: dict[str, Any]) -> None:
        candidate.pop("physical_verification", None)
        candidate["command"]["status"] = "SUCCEEDED"

    add(
        "success_without_physical_verification",
        TRACE_PHYSICAL_UNVERIFIED,
        ack_shortcut,
    )
    add(
        "fixture_claims_physical_success",
        TRACE_INCONSISTENT_IDENTITY,
        lambda c: c.__setitem__("claimed_physical_success", True),
    )
    add(
        "hypothetical_command_unmarked",
        TRACE_NOT_AUTHORIZED,
        lambda c: c["command"].__setitem__("hypothetical_test_record", False),
    )

    def remove_thermal(candidate: dict[str, Any]) -> None:
        candidate["physical_verification"]["thermal_response"] = None

    add("thermal_verification_missing", TRACE_PHYSICAL_UNVERIFIED, remove_thermal)

    def parent_class_only_physical(candidate: dict[str, Any]) -> None:
        candidate["fixture"] = False
        candidate["evidence_class"] = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
        candidate["physical_verification"][
            "evidence_class"
        ] = "MEASURED_PHYSICAL_DATA"

    add(
        "parent_class_only_physical",
        TRACE_PHYSICAL_UNVERIFIED,
        parent_class_only_physical,
    )
    add(
        "electrical_quality_unknown",
        TRACE_PHYSICAL_UNVERIFIED,
        lambda c: c["physical_verification"]["electrical_response"].__setitem__(
            "quality", "UNKNOWN"
        ),
    )

    def claimed_success_without_command(candidate: dict[str, Any]) -> None:
        for stage in ("command", "ack", "applied_state", "physical_verification"):
            candidate.pop(stage, None)
        candidate["fixture"] = False
        candidate["evidence_class"] = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
        candidate["claimed_physical_success"] = True

    add(
        "claimed_success_without_command",
        TRACE_PHYSICAL_UNVERIFIED,
        claimed_success_without_command,
    )

    def applied_without_physical(candidate: dict[str, Any]) -> None:
        candidate.pop("physical_verification", None)

    add(
        "applied_state_without_physical",
        TRACE_PHYSICAL_UNVERIFIED,
        applied_without_physical,
    )
    add(
        "physical_without_command",
        TRACE_NOT_AUTHORIZED,
        lambda c: [c.pop(stage, None) for stage in ("command", "ack", "applied_state")],
    )
    add(
        "synthetic_fixture_mislabeled",
        TRACE_INCONSISTENT_IDENTITY,
        lambda c: c.__setitem__("fixture", False),
    )
    add(
        "authorized_without_evidence",
        TRACE_NOT_AUTHORIZED,
        lambda c: c["policy"].__setitem__("decision_status", "AUTHORIZED"),
    )

    def terminal_contradiction(candidate: dict[str, Any]) -> None:
        candidate["command"]["status"] = "SUCCEEDED"
        candidate["ack"]["ack_status"] = "REJECTED"

    add(
        "terminal_status_contradiction",
        TRACE_INCONSISTENT_IDENTITY,
        terminal_contradiction,
    )
    add(
        "physical_attribution_cross_boot",
        TRACE_INCONSISTENT_IDENTITY,
        lambda c: c["physical_verification"].__setitem__("boot_id", "boot-other"),
    )
    results = []
    for name, expected_outcome, candidate in probes:
        assessment = assess_trace(candidate)
        results.append(
            {
                "probe": name,
                "expected_outcome": expected_outcome,
                "observed_outcome": assessment.outcome,
                "passed": assessment.outcome == expected_outcome,
                "refusal_reasons": list(assessment.refusal_reasons),
            }
        )
    return results


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    def cell(value: Any) -> str:
        if value is None:
            text = "-"
        elif isinstance(value, (dict, list)):
            text = json.dumps(value, sort_keys=True, separators=(",", ":"))
        else:
            text = str(value)
        return text.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return lines


def _short(value: Any, length: int = 24) -> str:
    text = (
        json.dumps(value, sort_keys=True, separators=(",", ":"))
        if isinstance(value, (dict, list))
        else str(value)
    )
    return text if len(text) <= length else text[: length - 3] + "..."


def _dimension_summary(result: Any) -> list[list[Any]]:
    rows = []
    for dimension in (
        DIMENSION_MODEL,
        DIMENSION_FEATURE,
        DIMENSION_PREDICTION,
        DIMENSION_FRESHNESS,
    ):
        checks = [check for check in result.checks if check.dimension == dimension]
        counts = {
            STATUS_PASS: sum(1 for check in checks if check.status == STATUS_PASS),
            STATUS_FAIL: sum(1 for check in checks if check.status == STATUS_FAIL),
            STATUS_NOT_VERIFIED: sum(
                1 for check in checks if check.status == STATUS_NOT_VERIFIED
            ),
        }
        rows.append(
            [
                dimension,
                len(checks),
                counts[STATUS_PASS],
                counts[STATUS_FAIL],
                counts[STATUS_NOT_VERIFIED],
            ]
        )
    return rows


def _monitor_report(
    *,
    expected: Any,
    audit: Any,
    representative: Any,
    monitor_probes: Sequence[Mapping[str, Any]],
    w15_manifest_sha: str,
    w17_record_count: int,
) -> str:
    sequence = audit.sequence.to_dict()
    lines = [
        "# W18 model runtime monitoring — software scope",
        "",
        "Evidence class: SYNTHETIC_SOFTWARE_CONTROL_ONLY.",
        EVIDENCE_LABELS,
        "The monitor is read-only: it inspects declared prediction records and never",
        "deploys, registers, dispatches, tunes or physically authorizes anything.",
        "",
        "## Expected identity (computed from actual W15/W10 files)",
        "",
        *_table(
            ("field", "value", "canonical ref"),
            [
                ("artifact_id", expected.artifact_id, "05B §46"),
                ("model_artifact_sha256", expected.model_artifact_sha256, "03 §92"),
                ("model_config_sha256", expected.model_config_sha256, "03 §92"),
                ("model_library_version", expected.model_library_version, "03 §92"),
                ("feature_version", expected.feature_version, "05B §9"),
                ("feature_schema_sha256", expected.feature_schema_sha256, "03 §92"),
                (
                    "ordered_feature_ids_sha256",
                    expected.ordered_feature_ids_sha256,
                    "02 §60.5",
                ),
                ("feature_count", expected.feature_count, "05B §46"),
                ("score_semantics", expected.score_semantics, "03 §58-60"),
                (
                    "target_status",
                    expected.target_status,
                    "03 §42-43",
                ),
                (
                    "horizon",
                    f"{expected.horizon_s:g} s / {expected.horizon_status}",
                    "03 §44",
                ),
                (
                    "operating_threshold",
                    f"{expected.operating_threshold:g} / "
                    f"{expected.operating_threshold_status}",
                    "03 §87",
                ),
                (
                    "warning_persistence_status",
                    expected.warning_persistence_status,
                    "03 §88",
                ),
                ("calibration_status", expected.calibration_status, "03 §58-60"),
                ("data_evidence_class", expected.data_evidence_class, "03 §3"),
                ("release_eligibility", expected.release_eligibility, "05B §44"),
            ],
        ),
        "",
        "## Records monitored",
        "",
        f"W17 replay records inspected: {w17_record_count}.",
        f"W15 model manifest SHA-256: {w15_manifest_sha}.",
        "",
        "Verdict counts:",
        "",
        *_table(
            ("verdict", "count"),
            sorted(audit.verdict_counts.items()),
        ),
        "",
        "Refusal reason counts:",
        "",
        *(
            _table(("reason", "count"), sorted(audit.reason_counts.items()))
            if audit.reason_counts
            else ["None."]
        ),
        "",
        "## Identity is not approval",
        "",
        *_table(
            ("question", "value"),
            [
                ("MODEL_HASH_MATCH", str(audit.identity_match_all).lower()),
                ("FEATURE_SCHEMA_MATCH", str(audit.identity_match_all).lower()),
                (
                    "OFFLINE_REPLAY_SCORE_VALID",
                    str(
                        audit.verdict_counts.get(MONITOR_SOFTWARE_VALID, 0)
                        == w17_record_count
                    ).lower(),
                ),
                ("MODEL_RELEASE_APPROVED", "false"),
                ("PHYSICAL_CONTROLLER_B_AUTHORIZED", "false"),
                ("RELEASE_CLAIM_COUNT", audit.release_claim_count),
                ("CONTROL_CLAIM_COUNT", audit.control_claim_count),
            ],
        ),
        "",
        "## Boot/sequence continuity",
        "",
        f"Groups: {sequence['group_count']}; issues: "
        f"{', '.join(sequence['issues']) if sequence['issues'] else 'none'}.",
        "",
        *_table(
            ("run_id", "boot_id", "records", "first_seq", "last_seq", "monotonic"),
            [
                (
                    group["run_id"],
                    group["boot_id"],
                    group["record_count"],
                    group["first_seq"],
                    group["last_seq"],
                    group["monotonic"],
                )
                for group in sequence["groups"]
            ],
        ),
        "",
        "## Representative record — dimension status",
        "",
        *_table(
            ("dimension", "checks", "pass", "fail", "not_verified"),
            _dimension_summary(representative),
        ),
        "",
        "## Negative controls",
        "",
        "These probes mutate an in-memory copy of one accepted record; no committed",
        "artifact is modified.",
        "",
        *_table(
            ("probe", "expected", "observed", "passed"),
            [
                (
                    probe["probe"],
                    probe["expected_verdict"],
                    probe["observed_verdict"],
                    probe["passed"],
                )
                for probe in monitor_probes
            ],
        ),
        "",
        "## Limitations",
        "",
        "- W17 replay records are synthetic software controls, not live inference.",
        "- W17 records do not declare a model-config hash; config binding is verified",
        "  through the W15 manifest and the actual config file.",
        "- The runtime freshness policy remains pending C/D.",
        "- A hash match proves byte identity only; it does not approve release.",
        "",
    ]
    return "\n".join(lines)


def _trace_report(
    *,
    w17_summary: Any,
    fixture_assessment: Any,
    trace_probes: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# W18 predictive-intervention trace audit",
        "",
        "Evidence class: SYNTHETIC_SOFTWARE_CONTROL_ONLY / TEST_ONLY fixture.",
        EVIDENCE_LABELS,
        "",
        "## W17 replay stage coverage (actual repo evidence)",
        "",
        *_table(
            ("stage", "status"),
            sorted(w17_summary.stage_status.items()),
        ),
        "",
        f"W17 records summarized: {w17_summary.record_count}; detailed records copied: "
        f"{str(w17_summary.records_copied).lower()}.",
        f"Trace internal SHA-256: {w17_summary.trace_sha256}.",
        f"Freshness verdicts: {json.dumps(w17_summary.freshness_verdict_counts, sort_keys=True)}.",
        f"Warning statuses: {json.dumps(w17_summary.warning_status_counts, sort_keys=True)}.",
        f"Policy statuses: {json.dumps(w17_summary.policy_status_counts, sort_keys=True)}.",
        "",
        f"W17 trace outcome: {w17_summary.outcome}.",
        f"Physical chain status: {w17_summary.physical_chain_status}.",
        "The W17 replay contains no authorized policy decision, command, ACK or",
        "physical response; the physical chain is unavailable and is not invented.",
        "",
        "## TEST_ONLY fixture assessment",
        "",
        f"Fixture outcome: {fixture_assessment.outcome}.",
        f"fixture={str(fixture_assessment.fixture).lower()}, "
        f"physical_verified={str(fixture_assessment.physical_verified).lower()}, "
        f"authorized_control={str(fixture_assessment.authorized_control).lower()}, "
        f"real_intervention={str(fixture_assessment.real_intervention).lower()}, "
        f"controller_b_acceptance={str(fixture_assessment.controller_b_acceptance).lower()}.",
        "",
        *_table(
            ("invariant", "status", "observed", "reason"),
            [
                (
                    invariant.invariant_id,
                    invariant.status,
                    invariant.observed,
                    invariant.reason_code or "-",
                )
                for invariant in fixture_assessment.invariants
            ],
        ),
        "",
        "## Negative controls",
        "",
        *_table(
            ("probe", "expected", "observed", "passed"),
            [
                (
                    probe["probe"],
                    probe["expected_outcome"],
                    probe["observed_outcome"],
                    probe["passed"],
                )
                for probe in trace_probes
            ],
        ),
        "",
        "## Physical boundary",
        "",
        "- An ACK is an acknowledgement only; it is never electrical or thermal evidence.",
        "- Applied state is a device report; it is not independent physical verification.",
        "- The synthetic fixture proves parsing and refusal behavior, not physical execution.",
        "- No record in this audit establishes a real predictive intervention.",
        "- A measured physical trace evidence class is not accepted in this W18",
        "  software scope; adding one is scheduled before any authorized physical run.",
        "",
    ]
    return "\n".join(lines)


def _freeze_report(
    *,
    baseline: Any,
    comparison: Any,
    model_binding: Mapping[str, Any],
    w15_manifest_sha: str,
    w16_manifest_sha: str,
    w17_manifest_sha: str,
) -> str:
    lines = [
        "# W18 no-online-tuning and freeze-drift audit",
        "",
        EVIDENCE_LABELS,
        "Canonical rule: do not adjust the model or threshold after each physical run.",
        "This audit is read-only and implements no tuner, updater, retrainer,",
        "recalibrator or threshold optimizer.",
        "",
        "## Baseline distinction",
        "",
        f"Pinned baseline input: ml/reports/W18/freeze-baseline-W18.json "
        f"({_sha256(FREEZE_BASELINE)}).",
        f"- Development baseline: {comparison.development_status}.",
        f"- Approved release freeze: {baseline.approved_freeze_status}.",
        "- A stable development baseline is not an approved release freeze.",
        "",
        "## Protected fields",
        "",
        *_table(
            ("field", "baseline value", "observed", "status"),
            [
                (
                    row["field_id"],
                    _short(row["baseline_value"], 48),
                    _short(row["observed_value"], 48),
                    row["status"],
                )
                for row in comparison.field_rows
            ],
        ),
        "",
        "## Native model binding",
        "",
        f"Model file matches declared SHA-256: {str(model_binding['matches']).lower()}.",
        f"Observed SHA-256: {model_binding['observed_sha256'] or 'MISSING'}.",
        f"Expected SHA-256: {model_binding['expected_sha256']}.",
        "",
        "## Inputs observed",
        "",
        f"- W15 model manifest SHA-256: {w15_manifest_sha}",
        f"- W16 locked-test manifest SHA-256: {w16_manifest_sha}",
        f"- W17 manifest SHA-256: {w17_manifest_sha}",
        "",
        "## Change-control contract",
        "",
        "A future legitimate change must provide:",
        "",
        *[
            f"- {field}"
            for field in CHANGE_REQUIRED_FIELDS
        ],
        "",
        "A change following locked-test exposure must declare a new independent",
        "evaluation; the old locked test is no longer untouched for the new model.",
        "",
        "## Forbidden behaviors covered by controls",
        "",
        "- threshold changed after an observed trace",
        "- persistence modified after observed warnings",
        "- model bytes changed without an identity update",
        "- model swapped while preserving old hash metadata",
        "- feature order changed silently",
        "- horizon changed after inspecting evaluation output",
        "- calibration semantics changed from risk score to probability",
        "- a post-test revision reusing the old locked-test acceptance",
        "- a missing freeze record treated as a verified freeze",
        "",
        "## Result",
        "",
        f"Drift detected: {str(comparison.drift_detected).lower()}.",
        "No approved freeze record exists, so no software assertion converts the",
        "development baseline into a release freeze.",
        "",
    ]
    return "\n".join(lines)


def _readiness_report(
    *,
    readiness: Any,
    member_a: Mapping[str, Any],
    w16_state: Mapping[str, Any],
    w17_state: Mapping[str, Any],
) -> str:
    lines = [
        "# W18 Controller B readiness assessment",
        "",
        EVIDENCE_LABELS,
        "Member B reports model/scientific readiness; it does not own physical",
        "acceptance, policy authorization or Controller B enablement.",
        "",
        "## Readiness dimensions",
        "",
        *_table(
            ("dimension", "owner", "status", "observed", "evidence"),
            [
                (
                    row.dimension_id,
                    row.owner,
                    row.status,
                    row.observed,
                    _short(row.evidence, 40),
                )
                for row in readiness.dimensions
            ],
        ),
        "",
        f"Blocking dimensions: {', '.join(readiness.blockers) if readiness.blockers else 'none'}.",
        "",
        "## External evidence observed",
        "",
        f"- Member A: {member_a['observed']}.",
        f"- W16 holdout opened: {str(w16_state['holdout_opened']).lower()}; "
        f"locked evaluation: {w16_state['locked_evaluation']}; "
        f"model release candidate: {w16_state['model_release_candidate']}.",
        f"- W17 live shadow: {w17_state['live_shadow_verdict']}; "
        f"feature parity: {w17_state['feature_parity']}; "
        f"prediction parity: {w17_state['prediction_parity']}.",
        "- Member C: PR #73 (W17 shadow trace) and PR #74 (W18 Controller B",
        "  lifecycle) remain OPEN and unmerged; no interface is a frozen API.",
        "- Member D: predictive policy and physical verification interfaces are",
        "  not frozen; policy authorization remains D-owned.",
        "",
        "## Verdicts",
        "",
        "```text",
        f"B_W18_SOFTWARE_MONITORING = {readiness.software_monitoring}",
        f"B_W18_TRACE_VALIDATOR = {readiness.trace_validator}",
        f"PHYSICAL_INTERVENTION_TRACE = {readiness.physical_intervention_trace}",
        f"MODEL_RELEASE = {readiness.model_release}",
        f"G4 = {readiness.gate_g4}",
        f"CONTROLLER_B_READINESS_SIGNOFF = {readiness.signoff}",
        "```",
        "",
        readiness.human_authority_note,
        "",
        "No approval, signature, date or signoff record is fabricated by this report.",
        "",
    ]
    return "\n".join(lines)


def _readiness_observations(
    *,
    audit: Any,
    w17_verdicts: Mapping[str, Any],
    w16_state: Mapping[str, Any],
    member_a: Mapping[str, Any],
    expected: Any,
    w15_manifest_sha: str,
    w17_manifest_sha: str,
    w16_manifest_sha: str,
) -> dict[str, dict[str, Any]]:
    monitor_records = len(audit.results)
    all_valid = audit.verdict_counts.get(MONITOR_SOFTWARE_VALID, 0) == monitor_records
    return {
        "model_identity": {
            "ready": bool(audit.identity_match_all and all_valid),
            "observed": (
                f"{monitor_records}/{monitor_records} runtime records match the "
                "declared model identity" if monitor_records else "NO_RECORDS"
            ),
            "evidence": f"W15 model manifest {w15_manifest_sha}",
        },
        "feature_schema_compatibility": {
            "ready": bool(audit.identity_match_all and all_valid),
            "observed": (
                f"{expected.feature_count} ordered features; schema "
                f"{expected.feature_schema_sha256[:16]}"
            ),
            "evidence": f"W10 registry; W15 manifest {w15_manifest_sha}",
        },
        "prediction_freshness": {
            "ready": False,
            "observed": (
                "SOFTWARE_FRESHNESS_VERIFIED; RUNTIME_FRESHNESS_POLICY_PENDING_C_D"
            ),
            "evidence": f"W17 manifest {w17_manifest_sha}",
        },
        "risk_score_semantics": {
            "ready": bool(all_valid),
            "observed": "risk_score semantics in every monitored record; no probability wording",
            "evidence": f"W17 manifest {w17_manifest_sha}",
        },
        "policy_freeze": {
            "ready": False,
            "observed": (
                f"target={expected.target_status}; horizon={expected.horizon_status}; "
                f"threshold={expected.operating_threshold_status}; "
                f"persistence={expected.warning_persistence_status}"
            ),
            "evidence": f"W15 manifest {w15_manifest_sha}",
        },
        "offline_parity": {
            "ready": (
                w17_verdicts.get("B_W17_01_FEATURE_PARITY")
                == "OFFLINE_FEATURE_PARITY_VERIFIED"
                and w17_verdicts.get("B_W17_01_PREDICTION_PARITY")
                == "OFFLINE_PREDICTION_PARITY_VERIFIED"
            ),
            "observed": (
                f"feature={w17_verdicts.get('B_W17_01_FEATURE_PARITY')}; "
                f"prediction={w17_verdicts.get('B_W17_01_PREDICTION_PARITY')}"
            ),
            "evidence": f"W17 manifest {w17_manifest_sha}",
        },
        "approved_model_candidate": {
            "ready": False,
            "observed": f"model_release_candidate={w16_state['model_release_candidate']}",
            "evidence": f"W16 manifest {w16_manifest_sha}",
        },
        "locked_predictive_evaluation": {
            "ready": False,
            "observed": f"locked_evaluation={w16_state['locked_evaluation']}",
            "evidence": f"W16 manifest {w16_manifest_sha}",
        },
        "c_inference_trace_integration": {
            "ready": False,
            "observed": (
                "PR_73_OPEN_UNMERGED; PR_74_OPEN_UNMERGED; "
                "NO_REAL_INFERENCE_RECORD"
            ),
            "evidence": "Member C PR #73 / #74 interface audit",
        },
        "d_policy_safety_authorization": {
            "ready": False,
            "observed": "D_PREDICTIVE_POLICY_NOT_FROZEN; COMMAND_AUTHORITY_NOT_ESTABLISHED",
            "evidence": "Member D control interfaces; PR #74 open",
        },
        "a_physical_response_verification": {
            "ready": False,
            "observed": str(member_a["observed"]),
            "evidence": "evidence/A/W18 dry-run index and pre-run checklist",
        },
        "g4_evidence": {
            "ready": False,
            "observed": f"W16 readiness decision={w16_state['readiness_decision']}",
            "evidence": f"W16 manifest {w16_manifest_sha}",
        },
    }


def generate(out_dir: Path, *, source_revision: str = W18_BASE_REVISION) -> dict[str, Any]:
    out_dir = Path(out_dir)
    registry = load_registry()
    config = load_benchmark_config(ML_ROOT / "xgb-v1-config.yaml", registry)
    feature_ids = list(config.feature_policy.allowlist)
    model = load_guarded_artifact(
        manifest_path=W15_MODEL_MANIFEST,
        model_path=W15_MODEL_FILE,
        expected_feature_ids=feature_ids,
        expected_feature_schema_hash=registry.schema_sha256,
        expected_model_config_hash=config.config_sha256,
    )
    expected = expected_runtime_identity(
        model_manifest=model.manifest,
        registry=registry,
        config=config,
    )

    w16 = _read_json(W16_MANIFEST, "W16 locked-test manifest")
    holdout_opened = w16.get("holdout_opened")
    if not isinstance(holdout_opened, bool):
        raise W18DriverError("W16 holdout_opened is not an explicit boolean")
    if holdout_opened:
        raise W18DriverError("the W16 holdout is recorded as opened")
    w16_state = {
        "manifest_sha256": _sha256(W16_MANIFEST),
        "holdout_opened": holdout_opened,
        "locked_evaluation": w16.get("evaluation_disposition", {}).get(
            "locked_evaluation"
        ),
        "model_release_candidate": w16.get("evaluation_disposition", {}).get(
            "model_release_candidate"
        ),
        "readiness_decision": w16.get("readiness_decision", {}).get("decision"),
    }

    w17_manifest = _read_json(W17_MANIFEST, "W17 manifest")
    model_identity = w17_manifest.get("model_artifact", {})
    if model_identity.get("model_artifact_sha256") != expected.model_artifact_sha256:
        raise W18DriverError("W17 manifest model identity moved from the W15 artifact")
    if (
        w17_manifest.get("feature_registry", {}).get("registry_sha256")
        != expected.feature_schema_sha256
    ):
        raise W18DriverError("W17 manifest feature identity moved from the W10 registry")
    trace_file_sha = _sha256(W17_TRACE)
    if w17_manifest.get("shadow_trace", {}).get("file_sha256") != trace_file_sha:
        raise W18DriverError("W17 trace file bytes do not match the W17 manifest")
    for report_name, expected_sha in w17_manifest.get("reports", {}).items():
        report_path = W17_DIR / report_name
        if not report_path.is_file() or _sha256(report_path) != expected_sha:
            raise W18DriverError(
                f"W17 report {report_name} does not match the W17 manifest"
            )
    trace = _read_json(W17_TRACE, "W17 shadow trace")
    policy = policy_expectation_from_w17_header(trace["header"], expected)
    w17_summary = summarize_w17_replay_trace(trace)
    if w17_summary.model_artifact_sha256 != expected.model_artifact_sha256:
        raise W18DriverError("W17 trace header model identity moved")
    records = trace["records"]
    audit = monitor_runtime_records(records, expected=expected, policy=policy)
    representative = audit.results[0]
    monitor_probes = _monitor_probes(records[0], expected, policy)
    failed_monitor_probes = [
        probe for probe in monitor_probes if not probe["passed"]
    ]
    if failed_monitor_probes:
        raise W18DriverError(
            "monitor negative controls failed: "
            + json.dumps(failed_monitor_probes, sort_keys=True)
        )

    fixture = build_test_only_fixture(
        model_artifact_sha256=expected.model_artifact_sha256,
        feature_schema_sha256=expected.feature_schema_sha256,
        ordered_feature_ids_sha256=expected.ordered_feature_ids_sha256,
    )
    fixture_assessment = assess_trace(fixture)
    if fixture_assessment.outcome != TRACE_COMPLETE_SOFTWARE_FIXTURE:
        raise W18DriverError(
            "the TEST_ONLY fixture did not validate: "
            f"{fixture_assessment.outcome}"
        )
    trace_probes = _trace_probes(fixture)
    failed_trace_probes = [probe for probe in trace_probes if not probe["passed"]]
    if failed_trace_probes:
        raise W18DriverError(
            "trace negative controls failed: "
            + json.dumps(failed_trace_probes, sort_keys=True)
        )

    baseline = load_pinned_baseline(FREEZE_BASELINE)
    observed_values = observe_protected_values(
        registry=registry,
        config=config,
        model_manifest=model.manifest,
        manifest_path=W15_MODEL_MANIFEST,
        model_path=W15_MODEL_FILE,
    )
    comparison = compare_freeze_state(baseline, observed_values)
    model_binding = verify_model_file_binding(baseline, W15_MODEL_FILE)
    if not model_binding["matches"]:
        raise W18DriverError("native model bytes do not match the W15 manifest")

    sample_change = {
        "artifact_id": "coldguard-w15-candidate-next",
        "model_artifact_sha256": "a" * 64,
        "model_config_sha256": expected.model_config_sha256,
        "feature_schema_hash": expected.feature_schema_sha256,
        "ordered_feature_ids_sha256": expected.ordered_feature_ids_sha256,
        "reason": "CONTROL_CONTRACT_CHECK_ONLY",
        "owner": "B",
        "affected_evidence": ["ml/reports/W15", "ml/reports/W17"],
        "evaluation_implications": "REQUIRES_NEW_INDEPENDENT_EVALUATION",
        "review_gate": {"status": "PENDING_REVIEW"},
        "comparability": "REQUIRES_NEW_INDEPENDENT_EVALUATION",
    }
    change_decision = assess_change_request(
        sample_change, baseline=baseline, locked_test_exposed=False
    )
    if not change_decision.decision.startswith("CHANGE_ACCEPTED_"):
        raise W18DriverError("the change-control contract did not accept a valid request")

    member_a = _member_a_state()
    w17_verdicts = w17_manifest.get("verdicts", {})
    freshness_verified = (
        w17_manifest.get("freshness", {}).get("verdict") == "SOFTWARE_VERIFIED"
    )
    observations = _readiness_observations(
        audit=audit,
        w17_verdicts=w17_verdicts,
        w16_state=w16_state,
        member_a=member_a,
        expected=expected,
        w15_manifest_sha=_sha256(W15_MODEL_MANIFEST),
        w17_manifest_sha=_sha256(W17_MANIFEST),
        w16_manifest_sha=_sha256(W16_MANIFEST),
    )
    trace_validator_verified = (
        fixture_assessment.outcome == TRACE_COMPLETE_SOFTWARE_FIXTURE
        and not failed_trace_probes
        and w17_summary.outcome == TRACE_PARTIAL_MISSING_EVIDENCE
    )
    readiness = assess_controller_b_readiness(
        observations,
        trace_validator_verified=trace_validator_verified,
        freshness_software_verified=freshness_verified,
        approval_records=(),
    )

    all_records_valid = (
        audit.verdict_counts.get(MONITOR_SOFTWARE_VALID, 0) == len(audit.results)
    )
    software_verified = (
        all_records_valid
        and audit.identity_match_all
        and audit.release_claim_count == 0
        and audit.control_claim_count == 0
        and freshness_verified
        and not failed_monitor_probes
    )
    trace_verified = trace_validator_verified and not failed_monitor_probes
    freeze_verified = (
        comparison.development_status == "DEVELOPMENT_BASELINE_UNCHANGED"
        and not comparison.drift_detected
        and model_binding["matches"]
    )
    software_complete = software_verified and trace_verified and freeze_verified

    verdicts = {
        "SOFTWARE": (
            "COMPLETE_PERMITTED_W18_SCOPE" if software_complete else "PARTIAL_PERMITTED_W18_SCOPE"
        ),
        "B_W18_01_MODEL_MONITORING": (
            "SOFTWARE_VERIFIED" if software_verified else "PARTIAL"
        ),
        "B_W18_02_TRACE_VALIDATION": (
            "SOFTWARE_VERIFIED" if trace_verified else "PARTIAL"
        ),
        "PHYSICAL_INTERVENTION_TRACE": readiness.physical_intervention_trace,
        "B_W18_03_NO_ONLINE_TUNING": (
            "SOFTWARE_VERIFIED" if freeze_verified else "PARTIAL"
        ),
        "B_W18_04_CONTROLLER_B_READINESS": (
            readiness.signoff if not readiness.signoff_withheld
            else "SIGNOFF_WITHHELD"
        ),
        "G4": readiness.gate_g4,
        "W16_HOLDOUT": "NOT_OPENED" if not holdout_opened else "OPENED",
        "MODEL_RC": readiness.model_release,
        "W17_LIVE_SHADOW": w17_verdicts.get(
            "LIVE_SHADOW", "NOT_ESTABLISHED"
        ),
        "DELIVERY": "PENDING_PUBLICATION",
    }

    report_texts = {
        "runtime-monitor-W18.md": _monitor_report(
            expected=expected,
            audit=audit,
            representative=representative,
            monitor_probes=monitor_probes,
            w15_manifest_sha=_sha256(W15_MODEL_MANIFEST),
            w17_record_count=len(records),
        ),
        "predictive-trace-W18.md": _trace_report(
            w17_summary=w17_summary,
            fixture_assessment=fixture_assessment,
            trace_probes=trace_probes,
        ),
        "no-online-tuning-W18.md": _freeze_report(
            baseline=baseline,
            comparison=comparison,
            model_binding=model_binding,
            w15_manifest_sha=_sha256(W15_MODEL_MANIFEST),
            w16_manifest_sha=_sha256(W16_MANIFEST),
            w17_manifest_sha=_sha256(W17_MANIFEST),
        ),
        "controller-b-readiness-W18.md": _readiness_report(
            readiness=readiness,
            member_a=member_a,
            w16_state=w16_state,
            w17_state={
                "live_shadow_verdict": w17_verdicts.get(
                    "LIVE_SHADOW", "NOT_ESTABLISHED"
                ),
                "feature_parity": w17_verdicts.get("B_W17_01_FEATURE_PARITY"),
                "prediction_parity": w17_verdicts.get(
                    "B_W17_01_PREDICTION_PARITY"
                ),
            },
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in report_texts.items():
        _write(out_dir / name, text)

    manifest = {
        "schema": "coldguard-w18-runtime-readiness-v1",
        "layer_version": W18_LAYER_VERSION,
        "scientific_evidence_class": "SYNTHETIC_SOFTWARE_CONTROL_ONLY",
        "physical_authorization_status": "CONTROLLER_B_NOT_AUTHORIZED",
        "source_revision": source_revision,
        "revision_semantics": W18_BASE_REVISION_SEMANTICS,
        "analysis_code_sha256": _analysis_code_sha256(),
        "generation_inputs": {
            "w15_model": {
                "manifest_path": "ml/reports/W15/model/model-manifest-W15.json",
                "manifest_sha256": _sha256(W15_MODEL_MANIFEST),
                "model_path": "ml/reports/W15/model/model.ubj",
                "model_sha256": _sha256(W15_MODEL_FILE),
            },
            "w16_readiness": {
                "manifest_path": "ml/reports/W16/locked-test-manifest-W16.json",
                **w16_state,
            },
            "w17_shadow": {
                "manifest_path": "ml/reports/W17/w17-manifest.json",
                "manifest_sha256": _sha256(W17_MANIFEST),
                "trace_path": "ml/reports/W17/shadow-trace-W17.json",
                "trace_file_sha256": trace_file_sha,
                "trace_internal_sha256": w17_summary.trace_sha256,
                "record_count": w17_summary.record_count,
                "freshness_software_verified": freshness_verified,
                "runtime_freshness_policy": "RUNTIME_FRESHNESS_POLICY_PENDING_C_D",
                "live_shadow": w17_verdicts.get("LIVE_SHADOW", "NOT_ESTABLISHED"),
                "report_sha256": {
                    name: w17_manifest.get("reports", {}).get(name)
                    for name in sorted(w17_manifest.get("reports", {}))
                },
            },
            "feature_registry": {
                "feature_version": registry.feature_version,
                "registry_sha256": registry.schema_sha256,
                "file_sha256": _sha256(ML_ROOT / "feature-registry-v1.yaml"),
                "feature_count": len(registry.features),
                "model_feature_count": expected.feature_count,
                "ordered_feature_ids_sha256": expected.ordered_feature_ids_sha256,
            },
            "model_config": {
                "version": config.config_version,
                "sha256": config.config_sha256,
                "file_sha256": _sha256(ML_ROOT / "xgb-v1-config.yaml"),
            },
            "freeze_baseline": {
                "path": "ml/reports/W18/freeze-baseline-W18.json",
                "sha256": _sha256(FREEZE_BASELINE),
            },
            "member_a_w18": member_a,
            "member_c": EXTERNAL_REVISIONS["member_c"],
            "member_d": EXTERNAL_REVISIONS["member_d"],
        },
        "expected_runtime_identity": expected.to_dict(),
        "runtime_monitor": {
            **audit.to_summary(),
            "representative_record": representative.record_key,
            "representative_dimensions": _dimension_summary(representative),
            "w17_record_count": len(records),
        },
        "adversarial_controls": {
            "monitor_probe_count": len(monitor_probes),
            "monitor_probes_passed": sum(
                1 for probe in monitor_probes if probe["passed"]
            ),
            "trace_probe_count": len(trace_probes),
            "trace_probes_passed": sum(1 for probe in trace_probes if probe["passed"]),
            "monitor_probes": monitor_probes,
            "trace_probes": trace_probes,
        },
        "w17_trace_assessment": w17_summary.to_dict(),
        "fixture_trace_assessment": fixture_assessment.to_dict(),
        "freeze_audit": {
            "baseline": baseline.to_dict(),
            "comparison": comparison.to_dict(),
            "model_file_binding": model_binding,
            "approved_release_freeze_status": baseline.approved_freeze_status,
            "development_only_statement": (
                "The development baseline is stable but no approved release freeze "
                "exists; this audit does not convert one into the other."
            ),
            "change_control": {
                "required_fields": list(CHANGE_REQUIRED_FIELDS),
                "sample_decision": change_decision.to_dict(),
                "locked_test_rule": (
                    "After locked-test exposure a new model requires new independent "
                    "data; prior locked-test acceptance cannot be reused."
                ),
            },
        },
        "readiness": readiness.to_dict(),
        "verdicts": verdicts,
        "external_dependency_states": dict(EXTERNAL_DEPENDENCIES),
        "external_dependency_semantics": "INTERFACE_AUDIT_SNAPSHOT_AT_IMPLEMENTATION",
        "capabilities": {
            "physical_control": False,
            "command_transport": False,
            "network": False,
            "model_registered": False,
            "actuator_client": False,
            "online_tuning": False,
            "broker_connection": False,
        },
        "unfinished_physical_requirements": [
            "frozen approved model release candidate",
            "frozen primary horizon, threshold and warning persistence",
            "locked predictive evaluation by its authorized owner",
            "live C inference and trace integration",
            "D policy and safety authorization",
            "A electrical and thermal physical response verification",
            "complete Gate G4 evidence",
            "Controller B physical dry runs and human signoff",
        ],
        "next_member_b_action": (
            "Prepare only W19 pair-ledger software scaffolding; do not authorize or "
            "start the final paired campaign while Gate G4 remains NOT_READY."
        ),
        "reports": {
            name: hashlib.sha256(
                (out_dir / name).read_bytes()
            ).hexdigest()
            for name in EXPECTED_REPORTS
        },
        "limitations": [
            "synthetic software controls only; no live inference or physical run",
            "W17 replay has no authorized policy, command, ACK or physical stage",
            "the TEST_ONLY fixture proves parsing and refusals, not physical execution",
            "runtime freshness policy, horizon, threshold and persistence remain unfrozen",
            "C/D interfaces are open and unmerged; field names are not a frozen API",
            "Member A W18 dossier records zero physical dry runs",
            "approval records are shape-checked only; B cannot verify external signatures",
            "a measured physical trace class is scheduled debt before authorized operation",
            "no model release, no G4 readiness and no Controller B signoff is issued",
        ],
    }
    manifest_path = out_dir / "w18-manifest.json"
    _write_json(manifest_path, manifest)
    return {
        "verdicts": verdicts,
        "runtime_monitor": manifest["runtime_monitor"]["verdict_counts"],
        "trace_outcome": w17_summary.outcome,
        "fixture_outcome": fixture_assessment.outcome,
        "freeze": comparison.development_status,
        "approved_freeze": baseline.approved_freeze_status,
        "readiness": {
            "software_monitoring": readiness.software_monitoring,
            "trace_validator": readiness.trace_validator,
            "signoff": readiness.signoff,
        },
        "manifest_sha256": _sha256(manifest_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the W18 report family")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ML_ROOT / "reports" / "W18",
        help="output directory (default: ml/reports/W18)",
    )
    parser.add_argument(
        "--source-revision",
        default=W18_BASE_REVISION,
        help="implementation base revision recorded in the manifest",
    )
    args = parser.parse_args(argv)
    try:
        summary = generate(args.out_dir, source_revision=args.source_revision)
    except Exception as exc:
        print(f"W18 driver refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
