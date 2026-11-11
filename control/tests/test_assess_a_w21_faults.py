import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assess_a_w21_faults.py"
SPEC = importlib.util.spec_from_file_location("assess_a_w21_faults", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_a_w21_sources_match_d_oracles_without_claiming_runtime():
    root = Path(__file__).resolve().parents[2]
    result = MODULE.assess(root)

    assert result["aggregate"] == "2_SOURCE_CASES_MATCH_D_ORACLES"
    assert result["physical_enablement"] is False
    assert {case["protocol_id"] for case in result["cases"]} == {
        "SENSOR-DEGRADED",
        "PZEM-UNAVAILABLE",
    }
    assert all(
        case["source_oracle_verdict"] == "MATCHED_NON_ENERGIZED_SOURCE_CASE"
        for case in result["cases"]
    )
    assert any("C persistence" in item for item in result["remaining"])
