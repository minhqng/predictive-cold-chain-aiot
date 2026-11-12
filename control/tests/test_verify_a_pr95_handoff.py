import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_a_pr95_handoff.py"
SPEC = importlib.util.spec_from_file_location("verify_a_pr95_handoff", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_a_pr95_supplementary_s1_is_verified_but_not_admitted():
    root = Path(__file__).resolve().parents[2]
    result = MODULE.verify(root)

    assert result["source_pr"]["number"] == 95
    assert result["result"]["outcome"] == "PASS"
    assert result["result"]["frames"] == 600
    assert result["result"]["commands_sent"] == 0
    assert result["result"]["bytes_written"] == 0
    assert result["admission"]["frozen_18_run_package"] == (
        "NOT_ADMITTED_MANIFEST_UNCHANGED"
    )
    assert result["verdict"] == "PR95_SUPPLEMENTARY_S1_HASH_VERIFIED_NOT_ADMITTED"
