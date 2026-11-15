import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_s2_critical.py"
SPEC = importlib.util.spec_from_file_location("evaluate_s2_critical", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_current_s2_runs_are_right_censored_at_candidate_threshold():
    root = Path(__file__).resolve().parents[2]
    result = MODULE.evaluate(root)

    assert result["critical_threshold_c"] == 30.5
    assert result["source_pr"]["number"] == 91
    assert result["source_pr"]["head"] == "63982e9592e0687099afb53fa1e4422f57761d74"
    assert result["accepted_s2_door_runs"] == 4
    assert result["threshold_reached_runs"] == 0
    assert result["aggregate_status"] == (
        "RIGHT_CENSORED_NO_CAPTURE_REACHED_THRESHOLD"
    )
    assert result["a_w13_03_result"] == "NOT_COMPUTABLE_THRESHOLD_NOT_REACHED"
    assert result["physical_enablement"] is False
    for run in result["runs"]:
        assert run["status"] == "RIGHT_CENSORED_THRESHOLD_NOT_REACHED"
        assert run["door_to_critical_s"] is None
        assert run["right_censored_lower_bound_s"] > 0
        assert run["max_tmean_after_door_c"] < 30.5
