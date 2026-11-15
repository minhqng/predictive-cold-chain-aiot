"""W17 shadow-parity driver (B-W17-01...04).

Generates the deterministic W17 report family from the synthetic W11 fixture.
Only the declared development trajectories are passed to the replay; no
locked-test run is scored, inspected or written.  The driver refuses if the
development and W16 locked-test run sets overlap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from coldguard_ml.feature_fixtures import (
    build_quality_degraded_trajectory,
    build_trajectory,
)
from coldguard_ml.feature_registry import FeatureRegistry, load_registry
from coldguard_ml.w15_artifact import GuardedModel, load_guarded_artifact
from coldguard_ml.w17_shadow_parity import (
    EVIDENCE_OFFLINE_REPLAY,
    EVIDENCE_SYNTHETIC,
    FEATURE_TOLERANCE,
    RUNTIME_FRESHNESS_POLICY_PENDING,
    SCORE_TOLERANCE,
    SYNTHETIC_TEST_PARAMETER,
    VERDICT_LIVE_NOT_ESTABLISHED,
    VERDICT_PHYSICAL_BLOCKED,
    W17_BASE_REVISION,
    W17_BASE_REVISION_SEMANTICS,
    W17_LAYER_VERSION,
    FreshnessPolicy,
    assess_shadow_readiness,
    fixture_identity,
    freshness_probes,
    run_shadow_parity,
)
from coldguard_ml.xgb_benchmark import (
    build_expanded_w11_fixture,
    load_benchmark_config,
)

ML_ROOT = Path(__file__).resolve().parents[1]
W15_MODEL_DIR = ML_ROOT / "reports" / "W15" / "model"
W16_MANIFEST = ML_ROOT / "reports" / "W16" / "locked-test-manifest-W16.json"

ANCHOR_SPECIALS = (
    0.0,
    1.0,
    5.0,
    39.0,
    40.0,
    41.0,
    59.0,
    60.0,
    61.0,
    79.0,
    80.0,
    81.0,
    82.0,
    83.0,
    99.0,
    100.0,
    101.0,
    179.0,
    180.0,
)

EXTERNAL_DEPENDENCIES = {
    "member_a_w17_shadow_audit": "DATA_INSUFFICIENT_ZERO_SYNCHRONIZED_RUNS",
    "member_c_pr_73_shadow_trace": "OPEN_UNMERGED_NOT_INTEGRATION_ACCEPTANCE",
    "member_d_shadow_policy": "NOT_FROZEN",
    "runtime_freshness_policy": "PENDING_C_D",
    "team_lead_cross_member_acceptance": "NOT_ESTABLISHED",
    "model_release_candidate": "NOT_ISSUED",
    "gate_g4": "NOT_READY",
}

W16_TEST_COUNT_RECONCILIATION = {
    "source": "PREFLIGHT_FULL_SUITE_RUN_ON_W16_HEAD",
    "w16_head": "c2b62234466b09585cf4e868c67a4d49ae06597f",
    "w15_base_collected": 992,
    "w16_added_test_functions": 105,
    "w16_collected": 1097,
    "actual_passed": 1094,
    "actual_skipped": 3,
    "skip_reason": (
        "pinned A 20261107 export absent; set COLDGUARD_W13_A_DATASET_DIR to "
        "the read-only git-archive export to run the CLI replay proof"
    ),
    "pr_105_body_passed": 1088,
    "pr_105_body_skipped": 3,
    "pr_105_body_collected": 1091,
    "conclusion": "STALE_PR_BODY_NOT_A_DELIVERED_REGRESSION",
    "explanation": (
        "No test file changed between daf85e0 and c2b6223; the delivered W16 "
        "tree contains all 105 added tests. The PR body count is six tests "
        "below the reproducible collection, consistent with a description "
        "written before the final six W16 tests were added."
    ),
    "recommendation": (
        "Correct the PR #105 body factually to 1094 passed, 3 skipped; no W16 "
        "history rewrite and no W16 code change are required."
    ),
}


class W17DriverError(RuntimeError):
    pass


_EXPECTED_PROBE_OUTCOMES = {
    "fresh_anchor": "READY",
    "late_packet_excluded": "PASS",
    "future_event_excluded": "PASS",
    "stale_pzem": "REFUSED_STALE",
    "degraded_channels": "REFUSED_UNTRUSTED",
    "counter_reset": "OBSERVED",
    "door_polarity_unattested": "REFUSED_UNTRUSTED",
    "unknown_door": "REFUSED_UNTRUSTED",
}


def _freshness_verified(
    probes: Sequence[Mapping[str, Any]],
) -> tuple[bool, str | None]:
    by_name = {probe["probe"]: probe for probe in probes}
    for name, expected in _EXPECTED_PROBE_OUTCOMES.items():
        actual = by_name.get(name, {}).get("outcome")
        if actual != expected:
            return False, f"PROBE_{name}_EXPECTED_{expected}_GOT_{actual}"
    stale = by_name["stale_pzem"]["detail"]
    if stale.get("cooling_power_is_zero") is not False:
        return False, "STALE_PZEM_WAS_ZERO_FILLED"
    counter = by_name["counter_reset"]["detail"]
    if counter.get("energy_counter_reason") != "MISSING_COUNTER_RESET":
        return False, "COUNTER_RESET_NOT_MISSING"
    unknown = by_name["unknown_door"]["detail"]
    if unknown.get("door_open_reason") != "MISSING_UNKNOWN_DOOR":
        return False, "UNKNOWN_DOOR_DID_NOT_STAY_MISSING"
    return True, None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    ).hexdigest()


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def _analysis_code_sha256() -> str:
    files = [
        ML_ROOT / "src" / "coldguard_ml" / "w17_shadow_parity.py",
        ML_ROOT / "scripts" / "w17-shadow-replay-W17.py",
        ML_ROOT / "tests" / "test_w17_shadow_parity.py",
        ML_ROOT / "tests" / "test_w17_freshness.py",
        ML_ROOT / "tests" / "test_w17_delivery.py",
    ]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(ML_ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _load_model(
    ml_root: Path, registry: FeatureRegistry, feature_ids: Sequence[str]
) -> GuardedModel:
    config = load_benchmark_config(ml_root / "xgb-v1-config.yaml", registry)
    model = load_guarded_artifact(
        manifest_path=W15_MODEL_DIR / "model-manifest-W15.json",
        model_path=W15_MODEL_DIR / "model.ubj",
        expected_feature_ids=feature_ids,
        expected_feature_schema_hash=registry.schema_sha256,
        expected_model_config_hash=config.config_sha256,
    )
    manifest = model.manifest
    if manifest["data_evidence_class"] != EVIDENCE_SYNTHETIC:
        raise W17DriverError("W15 artifact evidence class changed")
    if manifest["release_eligibility"] != "NON_DEPLOYABLE_CANDIDATE":
        raise W17DriverError("W15 artifact release eligibility changed")
    if manifest["score_semantics"] != "risk_score":
        raise W17DriverError("W15 artifact score semantics changed")
    if manifest["calibration_status"] != "RISK_SCORE_ONLY":
        raise W17DriverError("W15 calibration status changed")
    if manifest["horizon_status"] != "ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN":
        raise W17DriverError("W15 horizon status changed")
    if manifest["operating_threshold_status"] != "ILLUSTRATIVE_NOT_FROZEN":
        raise W17DriverError("W15 illustrative threshold status changed")
    if manifest["warning_persistence_status"] != "NOT_FROZEN":
        raise W17DriverError("W15 warning persistence status changed")
    if tuple(manifest["ordered_feature_ids"]) != tuple(feature_ids):
        raise W17DriverError("W15 ordered feature contract changed")
    return model


def _select_anchors(times: Sequence[float]) -> tuple[float, ...]:
    specials = set(ANCHOR_SPECIALS)
    return tuple(
        sorted(
            {
                float(time_s)
                for time_s in times
                if time_s % 5.0 == 0.0 or time_s in specials
            }
        )
    )


def _read_w16_state(development_runs: Sequence[str]) -> dict[str, Any]:
    if not W16_MANIFEST.is_file():
        raise W17DriverError("the W16 pre-registration manifest is missing")
    manifest = json.loads(W16_MANIFEST.read_text(encoding="utf-8"))
    registration = manifest.get("registration", {})
    test_runs = list(registration.get("test_runs", ()))
    overlap = sorted(set(development_runs) & set(test_runs))
    if overlap:
        raise W17DriverError(
            "the W17 development population overlaps the W16 locked test runs: "
            f"{overlap}"
        )
    if manifest.get("holdout_opened") is not False:
        raise W17DriverError("the W16 holdout is not recorded as unopened")
    decision = manifest.get("readiness_decision", {}).get("decision")
    return {
        "manifest_sha256": _sha256(W16_MANIFEST),
        "schema": manifest.get("schema"),
        "manifest_kind": manifest.get("manifest_kind"),
        "holdout_access": manifest.get("holdout_access"),
        "holdout_opened": manifest.get("holdout_opened"),
        "evaluation_status": manifest.get("evaluation_status"),
        "locked_evaluation": manifest.get("evaluation_disposition", {}).get(
            "locked_evaluation"
        ),
        "model_release_candidate": manifest.get("evaluation_disposition", {}).get(
            "model_release_candidate"
        ),
        "readiness_decision": decision,
        "g4_ready": decision == "READY",
        "test_runs": test_runs,
        "development_test_overlap": overlap,
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    _write(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
    )


def _write_json_compact(path: Path, payload: Any) -> None:
    _write(
        path,
        json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
        + "\n",
    )


def _parity_report(
    *,
    parity: Any,
    model: GuardedModel,
    registry: FeatureRegistry,
    fixture: Any,
    development_runs: Sequence[str],
    w16: Mapping[str, Any],
    late_delivery: Mapping[str, Any],
) -> str:
    compared = parity.compared_anchor_count
    feature_failed = sum(
        1 for item in parity.feature_comparisons if not item.passed
    )
    prediction_failed = sum(
        1 for item in parity.prediction_comparisons if not item.passed
    )
    lines = [
        "# W17 online/offline shadow parity — software replay",
        "",
        f"- Layer: `{W17_LAYER_VERSION}`",
        f"- Source basis: W16 stack head `{W17_BASE_REVISION}` "
        f"({W17_BASE_REVISION_SEMANTICS})",
        f"- Dataset: `{fixture.dataset_id}` / `{fixture.fixture_version}` "
        "(synthetic development population)",
        f"- Development runs: {len(development_runs)}",
        f"- W10 registry: `{registry.feature_version}` "
        f"`{registry.schema_sha256}`",
        f"- W15 model: `{model.manifest['artifact_id']}` "
        f"`{model.manifest['model_artifact_sha256']}`",
        f"- Evidence class: `{EVIDENCE_SYNTHETIC}` (data origin); "
        f"`{parity.offline_replay_verdict}` (verification level)",
        "",
        "## Verdicts",
        "",
        f"- B-W17-01 feature parity: "
        f"`{'OFFLINE_FEATURE_PARITY_VERIFIED' if parity.feature_parity_verified else 'NOT_VERIFIED'}`",
        f"- B-W17-01 prediction parity: "
        f"`{'OFFLINE_PREDICTION_PARITY_VERIFIED' if parity.prediction_parity_verified else 'NOT_VERIFIED'}`",
        "- Real online shadow: `LIVE_SHADOW_NOT_ESTABLISHED`",
        "- Physical shadow: `PHYSICAL_SHADOW_BLOCKED`",
        "",
        "## Method",
        "",
        "The offline reference is the canonical W10 causal batch pipeline over "
        "the history authorized at the anchor: event time at or before the "
        "anchor *and* deterministic receipt at or before prediction emission. "
        "The online path independently assembles the same authorized set "
        "incrementally: it ingests frames in deterministic arrival order, "
        "deduplicates identical deliveries, rejects contradictory identities, "
        "classifies late/out-of-order delivery, enforces the event-time and "
        "arrival-time cuts, sanitizes stale channels to missing values and only "
        "then calls the same W10 formulas on the accepted prefix. Both paths "
        "share the canonical W10 formula implementation by design; W17 does not "
        "create a competing feature definition.",
        "",
        f"- Feature tolerance: `{FEATURE_TOLERANCE}` absolute "
        "(identical float64 formula and authorized sample order; the observed "
        f"maximum deviation is {_fmt(parity.max_feature_deviation)}, the "
        "tolerance covers future serialization drift only)",
        f"- Score tolerance: `{SCORE_TOLERANCE}` absolute (same guarded model "
        "instance, same library version, deterministic single-threaded booster; "
        "W15 reload parity uses the same bound)",
        "- Wider tolerances are refused by the comparison API, so a changed "
        "formula cannot be hidden by relaxing the tolerance.",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Replay runs | {parity.replay_run_count} |",
        f"| Anchors | {parity.anchor_count} |",
        f"| Compared anchors | {compared} |",
        f"| Defined feature values compared | {parity.defined_values} |",
        f"| Missing feature values compared | {parity.missing_values} |",
        f"| Feature comparisons failed | {feature_failed} |",
        f"| Prediction comparisons failed | {prediction_failed} |",
        f"| Maximum feature deviation | {_fmt(parity.max_feature_deviation)} |",
        f"| Maximum risk-score deviation | {_fmt(parity.max_score_deviation)} |",
        f"| Rejected anchors | {parity.anchor_count - compared} |",
        f"| Excluded degraded windows | {parity.excluded_degraded_windows} |",
        f"| First mismatch | {parity.first_mismatch or 'none'} |",
        f"| Late observations recorded | {parity.late_observation_count} |",
        f"| Unconsumed trailing records | {parity.unconsumed_record_count} |",
        f"| Replay input records | {parity.replay_input_count} |",
        f"| Replay input hash | `{parity.replay_inputs_sha256}` |",
        "",
        f"One deterministic late delivery was injected in run "
        f"`{late_delivery['run_id']}` for frame "
        f"`{late_delivery['telemetry_id']}` at scheduled arrival "
        f"{late_delivery['scheduled_arrival_s']:g} s (default "
        f"{late_delivery['default_transport_delay_s']:g} s transport delay). "
        "The reference applies the same availability cut, so the frame is "
        "excluded from earlier anchors and included only after receipt; the "
        "recorded late count above is real, not structural.",
        "",
    ]
    if parity.refused_by_reason:
        lines.extend(
            ["| Refusal disposition | Count |", "|---|---|"]
            + [f"| `{reason}` | {count} |" for reason, count in parity.refused_by_reason]
            + [""]
        )
    else:
        lines.extend(
            [
                "No anchor was refused in the clean development parity run; "
                "fail-closed refusals are demonstrated in the freshness report "
                "and in the adversarial test suite.",
                "",
            ]
        )
    if parity.refusals:
        lines.extend(
            [
                "",
                "### Refused anchor detail",
                "",
                "| Run | Anchor | Disposition | Reasons |",
                "|---|---|---|---|",
            ]
        )
        for item in parity.refusals[:20]:
            reasons = "; ".join(item["reasons"])
            lines.append(
                f"| `{item['run_id']}` | {item['anchor_t_s']:g} | "
                f"`{item['disposition']}` | `{reasons}` |"
            )
        if len(parity.refusals) > 20:
            lines.append(
                f"| … | | | {len(parity.refusals) - 20} further refusals |"
            )
        lines.append("")
    proof = parity.mutation_proof
    lines.extend(
        [
            "## Unused-feature mutation proof",
            "",
            "The W15 synthetic model uses only `time_since_open`; every other "
            "feature is unused. A deliberate +0.5 mutation to an unused, defined "
            "feature must fail feature parity while leaving the score unchanged.",
            "",
            f"- Performed: {proof.get('performed')}",
            f"- Mutated feature: `{proof.get('feature_id', '-')}`",
            f"- Mutation delta: {_fmt(proof.get('mutation_delta'))}",
            f"- Feature-parity failure detected: {proof.get('feature_parity_detected')}",
            f"- Score unchanged: {proof.get('score_unchanged')}",
            f"- First mismatch: {proof.get('mismatch') or '-'}",
            "",
            "This prevents a misleading score-only PASS: score equality alone is "
            "never accepted as feature evidence.",
            "",
            "## Independence of the two paths",
            "",
            "The online path owns the arrival queue, deduplication, identity "
            "checks, boot boundary, late classification, availability cut and "
            "channel sanitization; the offline path filters the declared "
            "authorized history and recomputes the canonical batch formulas. "
            "Parity is only reported after both paths are exercised, and the "
            "harness rejects any online input that was not available at "
            "prediction time.",
            "",
            "This is authorization/assembly parity over a shared canonical "
            "formula implementation, not formula independence. A defect inside "
            "the shared W10 formula would not be detected here; W10's own "
            "formula tests remain the authority for that risk.",
            "",
            "Discriminating negative controls in the test suite: a future-event "
            "frame leaves a past anchor byte-identical; a late packet cannot "
            "change an emitted anchor and only enters a later prediction after "
            "its receipt; a contradictory duplicate identity fails closed; a "
            "boot transition clears door/observation state; the unused-feature "
            "mutation above fails feature parity while the score stays equal. "
            "These controls fail if the online assembly ignores availability, "
            "boot boundaries, duplicate identity or channel staleness.",
            "",
            "## Provenance and boundaries",
            "",
            f"- Fixture identity: `{fixture_identity([t for t in fixture.development_trajectories])}`",
            "- The W11 synthetic fixture is generated as declared by W11/W15; "
            "only development trajectories are passed to the replay. The W16 "
            "locked test runs were never evaluated, inspected or included; "
            f"development/test overlap: `{w16['development_test_overlap']}`.",
            "- The W15 artifact remains `NON_DEPLOYABLE_CANDIDATE`, "
            "`SYNTHETIC_SOFTWARE_CONTROL_ONLY`, `RISK_SCORE_ONLY`.",
            "- No command, broker, actuator, backend or network capability is "
            "reachable from this path; no subprocess is executed during replay.",
            "",
            "## Limitations",
            "",
            "- Synthetic fixture only; no physical predictive claim.",
            "- Parity verifies availability/assembly parity over the shared "
            "canonical formula implementation; it cannot detect a pure formula "
            "defect.",
            "- The clean population contains no stale channel; stale PZEM/door "
            "behavior is demonstrated by the dedicated probes and adversarial "
            "tests, not by the delivered parity run.",
            "- A raw frame without an explicit channel timestamp is treated as "
            "if its channels were observed at the frame event time; this is a "
            "declared synthetic assumption, not a physical attestation.",
            "- The primary horizon, operating threshold, warning persistence and "
            "runtime freshness policy remain unfrozen.",
            "- Offline replay parity does not imply live online shadow acceptance.",
            "",
        ]
    )
    return "\n".join(lines)


def _freshness_report(
    *,
    probes: Sequence[Mapping[str, Any]],
    policy: FreshnessPolicy,
    parity: Any,
    late_delivery: Mapping[str, Any],
) -> str:
    lines = [
        "# W17 feature freshness and temporal integrity",
        "",
        f"- Layer: `{W17_LAYER_VERSION}`",
        f"- Runtime freshness policy: `{RUNTIME_FRESHNESS_POLICY_PENDING}`",
        f"- Offline test parameters: `{SYNTHETIC_TEST_PARAMETER}`",
        f"- Maximum anchor input age: {policy.max_anchor_input_age_s:g} s",
        f"- Maximum electrical (PZEM) channel age: {policy.max_electrical_age_s:g} s",
        f"- Maximum door channel age: {policy.max_door_age_s:g} s",
        "- Channel timestamp basis: frame event time when no channel timestamp "
        "is attested (declared synthetic assumption, not physical attestation)",
        "",
        "## Clock domains",
        "",
        "| Domain | W17 representation | Declared status |",
        "|---|---|---|",
        "| Physical event time | fixture event offset `t` | synthetic exact; "
        "physical UTC sync NOT verified |",
        "| Sample receipt/arrival | `event + deterministic transport delay`; "
        "one deliberate late delivery is injected | simulated test parameter |",
        "| Prediction anchor | observed sample event time | synthetic |",
        "| Processing time | `anchor + deterministic processing delay`; all "
        "anchor/channel ages are measured against this instant | simulated test "
        "parameter |",
        "",
        "Host receipt time is never equated with physical event time, and no "
        "local script runtime is reported as transport or physical latency.",
        "",
        "## Disposition rules",
        "",
        "| Disposition | Rule |",
        "|---|---|",
        "| `READY_FOR_SOFTWARE_REPLAY` | anchor frame arrived by prediction "
        "time; identity/schema/order consistent; anchor, electrical and door "
        "ages measured at prediction time are within the test parameters; "
        "thermal/electrical/door quality trusted |",
        "| `REFUSED_STALE_INPUT` | missing anchor observation, anchor input age "
        "or electrical/door channel age measured at prediction time beyond the "
        "declared test parameter |",
        "| `REFUSED_UNTRUSTED_INPUT` | thermal or electrical quality not VALID; "
        "overall INVALID; door not OPEN/CLOSED, door quality not VALID or "
        "polarity unattested |",
        "| `REFUSED_TEMPORAL_ORDER` | anchor frame not available at emission; "
        "sequence regression with a newer event time; contradictory temporal state |",
        "| `REFUSED_IDENTITY_MISMATCH` | foreign boot/device, contradictory "
        "duplicate identity, ambiguous anchor time |",
        "| `REFUSED_FEATURE_SCHEMA_MISMATCH` | feature version/registry hash or "
        "ordered schema identity mismatch |",
        "",
        "A refused anchor never receives a score and never receives a warning. "
        "Sanitized channels become missing values with explicit reasons; stale "
        "electrical values are never replaced by zero and old door state never "
        "becomes current trusted state.",
        "",
        "## Executable probes",
        "",
        "| Probe | Outcome | Detail |",
        "|---|---|---|",
    ]
    for probe in probes:
        lines.append(
            f"| `{probe['probe']}` | `{probe['outcome']}` | "
            f"`{json.dumps(probe['detail'], sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "## Coverage of the adversarial matrix",
            "",
            "- Future event-time observations and late packets cannot influence "
            "an earlier anchor; a late frame is recorded separately and only "
            "becomes available at a later prediction whose processing time "
            "follows its arrival.",
            "- Duplicate identical deliveries collapse; contradictory payloads "
            "for one identity fail closed. Out-of-order event times are accepted "
            "deterministically and sorted; a lower sequence with a newer event "
            "time is rejected.",
            "- Boot transitions partition state; no rolling, door or actuation "
            "state crosses a boot boundary. A reconnect gap beyond the anchor "
            "age is refused as stale instead of reviving old state.",
            "- Stale PZEM samples are sanitized to missing electrical values "
            "(`MISSING_ELECTRICAL_UNQUALIFIED`), never zero. Counter resets are "
            "reported as `MISSING_COUNTER_RESET` and never create negative "
            "consumption.",
            "- UNKNOWN door state and unattested polarity keep door features "
            "missing (`MISSING_UNKNOWN_DOOR`, `MISSING_POLARITY_UNATTESTED`); "
            "UNKNOWN never becomes CLOSED and no duration crosses the "
            "interruption.",
            "- T2 is treated as a diagnostic hot-side probe and never enters the "
            "chamber-air aggregate.",
            "",
            f"The delivered parity run injected one deterministic late delivery "
            f"(`{late_delivery['telemetry_id']}` in `{late_delivery['run_id']}`, "
            f"scheduled arrival {late_delivery['scheduled_arrival_s']:g} s) and "
            f"recorded {parity.late_observation_count} late observation(s); it "
            f"refused {parity.anchor_count - parity.compared_anchor_count} "
            "anchor(s). The delivered fixtures contain no stale channel, so "
            "stale-PZEM and stale-door behavior is demonstrated by the probes "
            "above and by `tests/test_w17_freshness.py`, not by the clean parity "
            "run.",
            "",
            "## Limitations",
            "",
            "- Stale-channel dispositions are exercised by probes and adversarial "
            "tests; the clean parity fixture has no stale channel.",
            "- Channel timestamps absent from a raw frame default to the frame "
            "event time; this is a synthetic assumption, not a physical "
            "attestation.",
            "",
            "- Policy thresholds are illustrative test parameters, not the "
            "frozen runtime freshness policy owned by C/D.",
            "- Physical clock synchronization, transport latency and physical "
            "response are not measured in W17.",
            "",
        ]
    )
    return "\n".join(lines)


def _readiness_report(
    *,
    readiness: Any,
    parity: Any,
    w16: Mapping[str, Any],
) -> str:
    lines = [
        "# W17 shadow readiness assessment",
        "",
        f"- Layer: `{W17_LAYER_VERSION}`",
        f"- Evidence class: `{EVIDENCE_SYNTHETIC}` (data origin); "
        f"`{readiness.evidence_class}` (verification level)",
        "",
        "## Four levels",
        "",
        "| Level | Verdict |",
        "|---|---|",
        f"| 1. Offline feature parity | `{readiness.level_1_offline_feature_parity}` |",
        f"| 2. Offline prediction parity | `{readiness.level_2_offline_prediction_parity}` |",
        f"| 3. Software shadow-trace readiness | `{readiness.level_3_shadow_trace_software}` |",
        f"| 4. Real online shadow acceptance | `{readiness.level_4_real_online_shadow}` |",
        "",
        f"Physical shadow: `{readiness.physical_shadow}`.",
        "",
        "Levels 1-3 are software-verifiable. Level 4 stays blocked by the "
        "scientific and cross-member prerequisites below; no replay result "
        "overrides them.",
        "",
        "## W16 prerequisite relationship",
        "",
        "| Item | State |",
        "|---|---|",
        f"| W16 manifest | `{w16['manifest_sha256']}` |",
        f"| Holdout access | `{w16['holdout_access']}` |",
        f"| Holdout opened | `{w16['holdout_opened']}` |",
        f"| Locked evaluation | `{w16['locked_evaluation']}` |",
        f"| Model release candidate | `{w16['model_release_candidate']}` |",
        f"| W16 readiness decision | `{w16['readiness_decision']}` |",
        f"| G4 ready | `{w16['g4_ready']}` |",
        "| W13 primary horizon | `ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN` |",
        "| W15 model release eligibility | `NON_DEPLOYABLE_CANDIDATE` |",
        "| W15 score semantics | `risk_score` (`RISK_SCORE_ONLY`) |",
        "",
        "W17 software replay does not issue a model release candidate, does not "
        "open the holdout and does not change Gate G4.",
        "",
        "## W16 test-count reconciliation (preflight evidence)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| W16 head | `{W16_TEST_COUNT_RECONCILIATION['w16_head']}` |",
        f"| W15 base collected | {W16_TEST_COUNT_RECONCILIATION['w15_base_collected']} |",
        f"| W16-added test functions | {W16_TEST_COUNT_RECONCILIATION['w16_added_test_functions']} |",
        f"| W16 collected | {W16_TEST_COUNT_RECONCILIATION['w16_collected']} |",
        f"| Actual passed | {W16_TEST_COUNT_RECONCILIATION['actual_passed']} |",
        f"| Actual skipped | {W16_TEST_COUNT_RECONCILIATION['actual_skipped']} |",
        f"| PR #105 body passed | {W16_TEST_COUNT_RECONCILIATION['pr_105_body_passed']} |",
        f"| PR #105 body skipped | {W16_TEST_COUNT_RECONCILIATION['pr_105_body_skipped']} |",
        f"| Conclusion | `{W16_TEST_COUNT_RECONCILIATION['conclusion']}` |",
        "",
        W16_TEST_COUNT_RECONCILIATION["explanation"] + " "
        + W16_TEST_COUNT_RECONCILIATION["recommendation"],
        "",
        "## Acceptance terminology",
        "",
        "| Term | Status |",
        "|---|---|",
        f"| `OFFLINE_FEATURE_PARITY_VERIFIED` | "
        f"`{'yes' if parity.feature_parity_verified else 'no'}` |",
        f"| `OFFLINE_PREDICTION_PARITY_VERIFIED` | "
        f"`{'yes' if parity.prediction_parity_verified else 'no'}` |",
        f"| `SHADOW_TRACE_SOFTWARE_VERIFIED` | "
        f"`{'yes' if readiness.level_3_shadow_trace_software == 'SHADOW_TRACE_SOFTWARE_VERIFIED' else 'no'}` |",
        "| `LIVE_SHADOW_NOT_ESTABLISHED` | yes |",
        "| `PHYSICAL_SHADOW_BLOCKED` | yes |",
        "",
        "The ambiguous standalone verdict `SHADOW PASS` is not used.",
        "",
        "## Distinction",
        "",
        "- `OFFLINE_SOFTWARE_REPLAY`: the W17 result. Synthetic fixture, offline "
        "harness, no live telemetry.",
        "- `REAL_ONLINE_SHADOW_ACCEPTANCE`: not established. It requires a "
        "physical dataset, frozen model release, frozen policy/freshness "
        "semantics, accepted C integration and D safety evidence.",
        "",
        "## Team dependencies",
        "",
        "| Owner | Needed evidence | Current state |",
        "|---|---|---|",
        "| Member A | physically valid live/observational runs; trusted sensor "
        "and event-time provenance; shadow isolation | not available in the W16 "
        "base; A W17 audit reports data insufficient |",
        "| Member C | accepted online inference integration; durable "
        "prediction/trace schema; prediction input identity and freshness | "
        "PR #73 open/unmerged; not treated as the final runtime contract |",
        "| Member D | frozen shadow-policy semantics; hypothetical-decision "
        "safety rules; proof predictive output cannot bypass Controller A | "
        "not frozen; W17 does not invent policy |",
        "| Member B | feature/model identity; offline/online parity; freshness "
        "and input correctness; reproducible trace; limitations | this delivery |",
        "| Leader | cross-member acceptance and integration ordering | not "
        "established |",
        "",
        "## External dependency snapshot",
        "",
        "| Dependency | State |",
        "|---|---|",
    ]
    for name, status in sorted(EXTERNAL_DEPENDENCIES.items()):
        lines.append(f"| `{name}` | `{status}` |")
    lines.extend(
        [
            "",
            "The dependency states are a read-only interface-audit snapshot at "
            "implementation time; they are not runtime monitoring.",
            "",
            "## One next Member B action",
            "",
            "Prepare the W18 runtime monitoring harness against the frozen W15 "
            "artifact contract (hash, feature version, threshold and freshness "
            "status checks) while keeping Controller B physically disabled; do "
            "not enable predictive actuation until G4 is established.",
            "",
        ]
    )
    return "\n".join(lines)


def generate(out_dir: Path, *, source_revision: str) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = load_registry(ML_ROOT / "feature-registry-v1.yaml")
    config = load_benchmark_config(ML_ROOT / "xgb-v1-config.yaml", registry)
    feature_ids = tuple(config.feature_policy.allowlist)
    model = _load_model(ML_ROOT, registry, feature_ids)
    fixture = build_expanded_w11_fixture()
    development = tuple(fixture.development_trajectories)
    development_runs = tuple(sorted(item.run_id for item in development if item.run_id))
    if len(development_runs) != len(development):
        raise W17DriverError("a development trajectory has no run identity")
    w16 = _read_w16_state(development_runs)
    anchors_by_run = {
        item.run_id: _select_anchors([sample.time_s for sample in item.samples])
        for item in development
        if item.run_id is not None
    }
    policy = FreshnessPolicy()
    late_run = next(
        item
        for item in sorted(development, key=lambda entry: entry.run_id or "")
        if item.scenario_id == "S2"
    )
    late_sample = next(
        sample for sample in late_run.samples if sample.time_s == 30.0
    )
    late_delivery = {
        "injected": True,
        "run_id": late_run.run_id,
        "telemetry_id": late_sample.identity,
        "event_time_s": late_sample.time_s,
        "scheduled_arrival_s": 60.0,
        "default_transport_delay_s": 0.25,
        "purpose": "exercise the late-delivery availability cut in the delivered run",
    }
    parity = run_shadow_parity(
        development,
        registry,
        model=model,
        anchors_by_run=anchors_by_run,
        policy=policy,
        arrival_overrides={
            late_run.run_id: {late_sample.identity: 60.0}
        },
    )
    s2 = next(item for item in development if item.scenario_id == "S2")
    degraded, _ = build_quality_degraded_trajectory()
    counter_reset, _ = build_trajectory(
        "CG-W17-COUNTER-RESET-001",
        scenario="S2",
        seed=305,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(100.0,),
        counter_reset_at_s=70.0,
    )
    polarity, _ = build_trajectory(
        "CG-W17-POLARITY-001",
        scenario="S2",
        seed=306,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(100.0,),
        door_polarity_attested=False,
    )
    stale, _ = build_trajectory(
        "CG-W17-STALE-PZEM-001",
        scenario="S2",
        seed=307,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(100.0,),
    )
    unknown_door, _ = build_trajectory(
        "CG-W17-UNKNOWN-DOOR-001",
        scenario="S2",
        seed=308,
        door_start_s=40.0,
        door_duration_s=20.0,
        unknown_start_s=80.0,
        unknown_duration_s=3.0,
        critical_offsets_s=(100.0,),
    )
    probes = freshness_probes(
        s2,
        registry,
        feature_ids,
        stale_trajectory=stale,
        degraded_trajectory=degraded,
        counter_reset_trajectory=counter_reset,
        polarity_trajectory=polarity,
        unknown_door_trajectory=unknown_door,
    )
    test_runs = set(w16["test_runs"])
    if test_runs & {
        counter_reset.run_id,
        polarity.run_id,
        stale.run_id,
        unknown_door.run_id,
        degraded.run_id,
        late_run.run_id,
    }:
        raise W17DriverError("an adversarial fixture reuses a locked test run id")
    freshness_verified, freshness_failure = _freshness_verified(probes)
    readiness = assess_shadow_readiness(
        parity,
        trace_record_count=parity.trace["record_count"],
        external_dependencies=EXTERNAL_DEPENDENCIES,
    )
    trace_payload = parity.trace
    trace_path = out_dir / "shadow-trace-W17.json"
    _write_json_compact(trace_path, trace_payload)
    parity_report = _parity_report(
        parity=parity,
        model=model,
        registry=registry,
        fixture=fixture,
        development_runs=development_runs,
        w16=w16,
        late_delivery=late_delivery,
    )
    freshness_report = _freshness_report(
        probes=probes,
        policy=policy,
        parity=parity,
        late_delivery=late_delivery,
    )
    readiness_report = _readiness_report(
        readiness=readiness, parity=parity, w16=w16
    )
    _write(out_dir / "online-offline-parity-W17.md", parity_report)
    _write(out_dir / "feature-freshness-W17.md", freshness_report)
    _write(out_dir / "shadow-readiness-W17.md", readiness_report)
    compare_outcomes = {
        "feature_passed": sum(
            1 for item in parity.feature_comparisons if item.passed
        ),
        "feature_failed": sum(
            1 for item in parity.feature_comparisons if not item.passed
        ),
        "prediction_passed": sum(
            1 for item in parity.prediction_comparisons if item.passed
        ),
        "prediction_failed": sum(
            1 for item in parity.prediction_comparisons if not item.passed
        ),
        "refused_by_reason": dict(parity.refused_by_reason),
        "excluded_degraded_windows": parity.excluded_degraded_windows,
    }
    manifest = {
        "schema": "coldguard-w17-shadow-readiness-v1",
        "layer_version": W17_LAYER_VERSION,
        "scientific_evidence_class": EVIDENCE_SYNTHETIC,
        "evidence_level": parity.offline_replay_verdict,
        "source_revision": source_revision,
        "revision_semantics": W17_BASE_REVISION_SEMANTICS,
        "analysis_code_sha256": _analysis_code_sha256(),
        "fixture": {
            "dataset_id": fixture.dataset_id,
            "fixture_version": fixture.fixture_version,
            "fixture_sha256": fixture_identity(development),
            "run_ids": list(development_runs),
            "run_count": len(development),
            "sample_count": sum(
                len(item.samples) for item in development
            ),
            "source_type": "SYNTHETIC_FIXTURE",
            "locked_test_used": False,
        },
        "feature_registry": {
            "feature_version": registry.feature_version,
            "registry_sha256": registry.schema_sha256,
            "feature_count": len(registry.features),
            "model_feature_count": len(feature_ids),
        },
        "model_artifact": {
            "artifact_id": model.manifest["artifact_id"],
            "model_artifact_sha256": model.manifest["model_artifact_sha256"],
            "feature_schema_hash": model.manifest["feature_schema_hash"],
            "ordered_feature_ids": list(model.ordered_feature_ids),
            "ordered_feature_ids_sha256": model.manifest[
                "ordered_feature_ids_sha256"
            ],
            "model_library_version": model.manifest["model_library_version"],
            "release_eligibility": model.manifest["release_eligibility"],
            "data_evidence_class": model.manifest["data_evidence_class"],
            "score_semantics": model.manifest["score_semantics"],
            "calibration_status": model.manifest["calibration_status"],
            "horizon_status": model.manifest["horizon_status"],
            "operating_threshold": model.manifest["operating_threshold"],
            "operating_threshold_status": model.manifest[
                "operating_threshold_status"
            ],
            "warning_persistence_status": model.manifest[
                "warning_persistence_status"
            ],
        },
        "w16_readiness": w16,
        "w16_test_count_reconciliation": dict(W16_TEST_COUNT_RECONCILIATION),
        "verdicts": {
            "SOFTWARE": (
                "COMPLETE_PERMITTED_W17_SCOPE"
                if parity.feature_parity_verified
                and parity.prediction_parity_verified
                and readiness.level_3_shadow_trace_software
                == "SHADOW_TRACE_SOFTWARE_VERIFIED"
                and freshness_verified
                else "PARTIAL_PERMITTED_W17_SCOPE"
            ),
            "B_W17_01_FEATURE_PARITY": (
                "OFFLINE_FEATURE_PARITY_VERIFIED"
                if parity.feature_parity_verified
                else "NOT_VERIFIED"
            ),
            "B_W17_01_PREDICTION_PARITY": (
                "OFFLINE_PREDICTION_PARITY_VERIFIED"
                if parity.prediction_parity_verified
                else "NOT_VERIFIED"
            ),
            "B_W17_02_SHADOW_TRACE": readiness.level_3_shadow_trace_software,
            "B_W17_03_FEATURE_FRESHNESS": (
                "SOFTWARE_VERIFIED" if freshness_verified else "PARTIAL"
            ),
            "B_W17_04_REAL_SHADOW_READINESS": VERDICT_LIVE_NOT_ESTABLISHED,
            "W16_HOLDOUT": "NOT_OPENED",
            "G4": "NOT_READY",
            "LIVE_SHADOW": VERDICT_LIVE_NOT_ESTABLISHED,
            "PHYSICAL_SHADOW": VERDICT_PHYSICAL_BLOCKED,
            "DELIVERY": "PENDING_PUBLICATION",
        },
        "parity": {
            "replay_run_count": parity.replay_run_count,
            "anchor_count": parity.anchor_count,
            "compared_anchor_count": parity.compared_anchor_count,
            "feature_comparison_count": len(parity.feature_comparisons),
            "prediction_comparison_count": len(parity.prediction_comparisons),
            "defined_feature_values": parity.defined_values,
            "missing_feature_values": parity.missing_values,
            "feature_tolerance": FEATURE_TOLERANCE,
            "score_tolerance": SCORE_TOLERANCE,
            "max_feature_deviation": parity.max_feature_deviation,
            "max_score_deviation": parity.max_score_deviation,
            "first_mismatch": parity.first_mismatch,
            "comparison_outcomes": compare_outcomes,
            "mutation_proof": dict(parity.mutation_proof),
            "replay_inputs_sha256": parity.replay_inputs_sha256,
            "replay_input_count": parity.replay_input_count,
            "late_observation_count": parity.late_observation_count,
            "unconsumed_record_count": parity.unconsumed_record_count,
            "offline_replay_verdict": parity.offline_replay_verdict,
            "late_delivery": dict(late_delivery),
        },
        "freshness": {
            "policy_status": RUNTIME_FRESHNESS_POLICY_PENDING,
            "parameter_class": SYNTHETIC_TEST_PARAMETER,
            "verdict": "SOFTWARE_VERIFIED" if freshness_verified else "PARTIAL",
            "failure_reason": freshness_failure,
            "parameters": {
                "max_anchor_input_age_s": policy.max_anchor_input_age_s,
                "max_electrical_age_s": policy.max_electrical_age_s,
                "max_door_age_s": policy.max_door_age_s,
            },
            "channel_timestamp_basis": "FRAME_EVENT_TIME_WHEN_UNATTESTED",
            "probes": list(probes),
        },
        "shadow_trace": {
            "path": "shadow-trace-W17.json",
            "file_sha256": _sha256(trace_path),
            "internal_sha256": trace_payload["trace_sha256"],
            "record_count": trace_payload["record_count"],
            "evidence_class": EVIDENCE_SYNTHETIC,
        },
        "readiness": readiness.to_dict(),
        "external_dependency_states": dict(EXTERNAL_DEPENDENCIES),
        "external_dependency_semantics": "INTERFACE_AUDIT_SNAPSHOT_AT_IMPLEMENTATION",
        "physical_control_capability": False,
        "command_transport_capability": False,
        "network_capability": False,
        "model_registered": False,
        "physical_controller_b": "NOT_ENABLED",
        "reports": {
            "online-offline-parity-W17.md": _sha256(
                out_dir / "online-offline-parity-W17.md"
            ),
            "feature-freshness-W17.md": _sha256(
                out_dir / "feature-freshness-W17.md"
            ),
            "shadow-readiness-W17.md": _sha256(
                out_dir / "shadow-readiness-W17.md"
            ),
        },
        "limitations": [
            "synthetic development fixture only",
            "offline software replay is not live shadow acceptance",
            "primary horizon, operating threshold, warning persistence and "
            "runtime freshness policy remain unfrozen",
            "model is NON_DEPLOYABLE_CANDIDATE and was not registered",
        ],
    }
    manifest_path = out_dir / "w17-manifest.json"
    _write_json(manifest_path, manifest)
    return {
        "verdicts": manifest["verdicts"],
        "parity": manifest["parity"],
        "trace": manifest["shadow_trace"],
        "readiness": manifest["readiness"],
        "manifest_sha256": _sha256(manifest_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the W17 report family")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ML_ROOT / "reports" / "W17",
        help="output directory (default: ml/reports/W17)",
    )
    parser.add_argument(
        "--source-revision",
        default=W17_BASE_REVISION,
        help="implementation base revision recorded in the manifest",
    )
    args = parser.parse_args(argv)
    try:
        summary = generate(args.out_dir, source_revision=args.source_revision)
    except Exception as exc:  # driver refuses rather than emitting partial claims
        print(f"W17 driver refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
