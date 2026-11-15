import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assess_main_integration.py"
SPEC = importlib.util.spec_from_file_location("assess_main_integration", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_integrated_main_remains_honest_about_physical_and_predictive_gaps():
    root = Path(__file__).resolve().parents[2]
    result = MODULE.assess(root)
    assert result["main_sha"] == "557e887432d1a72b3d097f92644fe72b809c824e"
    assert result["command_path"]["a_observational_trace_verdict"] == "TRACED"
    assert result["command_path"]["firmware_executed"] is False
    assert result["command_path"]["d_direct_health_promotion_allowed"] is False
    assert result["predictive_path"]["all_prediction_views_unavailable"] is True
    assert result["predictive_path"]["door_to_critical_s"] is None
    assert result["decisions"]["physical_enablement"] is False


def test_committed_crosscheck_matches_generator():
    root = Path(__file__).resolve().parents[2]
    committed = json.loads(
        (root / "evidence/D/W13/main-integration-crosscheck-20261111.json")
        .read_text(encoding="utf-8")
    )
    assert committed == MODULE.assess(root)
