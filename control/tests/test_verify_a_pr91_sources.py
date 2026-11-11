import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_a_pr91_sources.py"
SPEC = importlib.util.spec_from_file_location("verify_a_pr91_sources", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_a_pr91_s1_s2_sources_are_hash_verified():
    root = Path(__file__).resolve().parents[2]
    result = MODULE.verify(root)

    assert result["source_pr"]["number"] == 91
    assert result["source_pr"]["head"] == "63982e9592e0687099afb53fa1e4422f57761d74"
    assert result["s1"]["outcome"] == "PASS"
    assert result["s1"]["valid_windows"] == 4
    assert result["s1"]["frames"] == 2401
    assert result["s2"]["outcome"] == "PASS"
    assert result["s2"]["valid_windows"] == 4
    assert result["s2"]["frames"] == 1200
    assert result["verdict"] == "PR91_SOURCES_HASH_VERIFIED"
