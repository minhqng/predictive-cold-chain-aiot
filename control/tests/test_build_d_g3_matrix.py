import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_d_g3_matrix.py"
SPEC = importlib.util.spec_from_file_location("build_d_g3_matrix", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_current_main_sources_update_readiness_without_claiming_g3():
    root = Path(__file__).resolve().parents[2]
    result = MODULE.build(root)

    assert result["overall"] == "NOT_VERIFIED"
    assert result["team_gate_decision"] == "NOT_CLAIMED"
    assert result["source_facts"] == {
        "accepted_s1_runs": 4,
        "accepted_s2_windows": 5,
        "accepted_s2_electrical_ok_rows": 1320,
        "accepted_s2_electrical_not_ok_rows": 0,
        "post_freeze_inspection": "PASS",
        "supplementary_s1_runs": 1,
        "supplementary_s1_frozen_package_admission": (
            "NOT_ADMITTED_MANIFEST_UNCHANGED"
        ),
    }
    statuses = {check["id"]: check["status"] for check in result["checks"]}
    assert statuses["D-W12-02"] == "SOURCE_AVAILABLE_RESULT_OPEN"
    assert statuses["D-W12-03"] == "PARTIAL_INPUTS"
    assert statuses["D-W12-05"] == "OPEN"
