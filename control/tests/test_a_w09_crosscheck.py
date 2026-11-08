import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "a_w09_crosscheck.py"
SPEC = importlib.util.spec_from_file_location("a_w09_crosscheck", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_missing_electrical_quality_stays_unknown(tmp_path):
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text(
        "electrical_quality,boot_id,run_id,seq\nUNKNOWN,b1,r1,1\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps({"valid_s1_run_ids_for_member_b": ["r1"]}),
        encoding="utf-8",
    )
    result = MODULE.analyze(csv_path, index_path)
    assert result["verdict"] == "UNKNOWN"
    assert result["source_admissible_for_review"] is False


def test_source_admission_does_not_claim_physical_verification(tmp_path):
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text(
        "electrical_quality,boot_id,run_id,seq\nVALID,b1,r1,1\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps({"valid_s1_run_ids_for_member_b": ["r1"]}),
        encoding="utf-8",
    )
    result = MODULE.analyze(csv_path, index_path)
    assert result["verdict"] == "SOURCE_ADMISSIBLE_ONLY"
    assert "never qualifies" in result["note"]
