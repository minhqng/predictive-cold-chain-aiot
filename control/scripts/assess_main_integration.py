"""Bind D's current verdicts to the integrated main artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from coldguard_control.types import EnvelopeQualification
from coldguard_control.verification_bridge import (
    AObservationalLifecycle,
    assess_a_lifecycle_for_d,
)


MAIN_SHA = "557e887432d1a72b3d097f92644fe72b809c824e"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assess(root: Path) -> dict[str, object]:
    trace_path = root / "evidence/A/W06/command-path-integration-20261110-traced.json"
    closure_path = (
        root / "docs/owner-integration/w13-bd-closure"
        / "bd-dependency-closure-20261110.json"
    )
    door_path = root / "evidence/A/W13/door-critical-input-20261109.json"
    decision_path = root / "docs/owner-integration/a-d-verification-semantics-DECISION.md"

    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    door = json.loads(door_path.read_text(encoding="utf-8"))

    command = trace["lifecycle"]["commands"][0]
    lifecycle = AObservationalLifecycle(
        command_id=command["command_id"],
        stages=tuple(command["stages"]),
        usable_for_health_claim=False,
        firmware_executed=trace["device_provenance"]["firmware_executed"],
        source=trace["post_ack_frame_provenance"],
    )
    bridge = assess_a_lifecycle_for_d(
        lifecycle, EnvelopeQualification.CANDIDATE_UNQUALIFIED
    )

    prediction_views = closure["prediction_views"]
    b_unavailable = all(
        view["health"] == "UNAVAILABLE" and view["risk_score"] is None
        for view in prediction_views.values()
    )
    if not b_unavailable:
        raise ValueError("integrated B closure unexpectedly claims a usable prediction")
    if door["door_to_critical"]["number_emitted"]:
        raise ValueError("integrated A handoff unexpectedly emitted door-to-critical")

    return {
        "schema": "coldguard-d-main-integration-crosscheck-v1",
        "main_sha": MAIN_SHA,
        "sources": [
            {"path": trace_path.relative_to(root).as_posix(), "sha256": _sha256(trace_path)},
            {"path": closure_path.relative_to(root).as_posix(), "sha256": _sha256(closure_path)},
            {"path": door_path.relative_to(root).as_posix(), "sha256": _sha256(door_path)},
            {"path": decision_path.relative_to(root).as_posix(), "sha256": _sha256(decision_path)},
        ],
        "command_path": {
            "backend_policy_accepted": trace["accepted"]["accepted"],
            "a_observational_trace_verdict": trace["lifecycle"]["summary"]["verdict"],
            "a_observational_stages": list(lifecycle.stages),
            "firmware_executed": lifecycle.firmware_executed,
            "source": lifecycle.source,
            "d_direct_health_promotion_allowed": bridge.direct_health_promotion_allowed,
            "d_health_state": bridge.d_health_state.value,
            "d_reason": bridge.reason,
        },
        "predictive_path": {
            "horizons_s": sorted(float(value) for value in prediction_views),
            "all_prediction_views_unavailable": b_unavailable,
            "positive_labels": 0,
            "door_to_critical_s": door["door_to_critical"]["value_s"],
            "critical_tmean_status": door["critical_tmean_status"],
        },
        "decisions": {
            "physical_verification": "UNKNOWN",
            "controller_b": "DISABLED",
            "aiw": "NOT_ESTIMABLE",
            "physical_enablement": False,
        },
        "verdict": "MAIN_INTEGRATION_SOFTWARE_PATH_PRESENT_PHYSICAL_AND_PREDICTIVE_GATES_OPEN",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    result = assess(root)
    target = root / "evidence/D/W13/main-integration-crosscheck-20261111.json"
    target.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
