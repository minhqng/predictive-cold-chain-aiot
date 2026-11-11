"""Delivery and adversarial integration probes for the recovery package.

Covers probes 6 and 23-30, plus fixture-level provenance and determinism.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

from coldguard_ml import existing_data_recovery as recovery

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
REPORTS = ML_ROOT / "reports" / "DataRecovery"
CLI = ML_ROOT / "scripts" / "existing-data-recovery.py"
MODULE = ML_ROOT / "src" / "coldguard_ml" / "existing_data_recovery.py"

HEADER = [
    "run_tag",
    "scenario",
    "host_time_utc",
    "boot_id",
    "seq",
    "uptime_ms",
    "firmware_version",
    "hardware_config_id",
    "t1_c",
    "t1_status",
    "t2_c",
    "t2_status",
    "t3_c",
    "t3_status",
    "t4_c",
    "t4_status",
    "tmean_air_c",
    "door_open",
    "door_status",
    "current_a",
    "current_status",
    "power_w",
    "power_status",
    "energy_wh",
    "quality",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv_text(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=HEADER, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in HEADER})
    return buffer.getvalue()


def _make_rows(
    *, run_tag: str, scenario: str, boot: str, count: int, door: bool
) -> list[dict[str, str]]:
    rows = []
    for index in range(count):
        open_state = "1.0" if door and index in {30, 31} else "0.0"
        rows.append(
            {
                "run_tag": run_tag,
                "scenario": scenario,
                "host_time_utc": f"2026-01-01T00:00:{index:02d}Z",
                "boot_id": boot,
                "seq": str(index + 1),
                "uptime_ms": str(1000 + index * 1000),
                "firmware_version": "fixture",
                "hardware_config_id": "CG-HW-001",
                "t1_c": "30.0",
                "t1_status": "OK",
                "t2_c": "29.8",
                "t2_status": "OK",
                "t3_c": "29.9",
                "t3_status": "OK",
                "t4_c": "30.1",
                "t4_status": "OK",
                "tmean_air_c": "",
                "door_open": open_state,
                "door_status": "OK",
                "current_a": "0.0",
                "current_status": "OK",
                "power_w": "0.0",
                "power_status": "OK",
                "energy_wh": "1.0",
                "quality": "OK",
            }
        )
    return rows


def _write_fixture(
    tmp_path: Path, *, missing_s2: bool = False, duplicate: bool = False
) -> tuple[Path, Path]:
    dataset_dir = tmp_path / "a-dataset"
    datasets = dataset_dir / "datasets"
    datasets.mkdir(parents=True, exist_ok=True)
    s1 = _make_rows(
        run_tag="fixture-s1",
        scenario="S1",
        boot="11111111",
        count=6,
        door=False,
    )
    if duplicate:
        s1.append(dict(s1[2]))
    s2 = _make_rows(
        run_tag="fixture-s2",
        scenario="S2_DOOR",
        boot="22222222",
        count=70,
        door=True,
    )
    texts = {
        "fixture-s1": _csv_text(s1),
        "fixture-s2": _csv_text(s2),
    }
    (datasets / "fixture-s1-normalized.csv").write_bytes(
        texts["fixture-s1"].encode("utf-8")
    )
    if not missing_s2:
        (datasets / "fixture-s2-normalized.csv").write_bytes(
            texts["fixture-s2"].encode("utf-8")
        )
    run_index_rows = []
    outputs = []
    for run_tag, scenario, boot, classification, rows in (
        ("fixture-s1", "S1", "11111111", "DATASET_ACCEPTED_S1", s1),
        ("fixture-s2", "S2_DOOR", "22222222", "DATASET_ACCEPTED_S2", s2),
    ):
        dataset_path = f"datasets/{run_tag}-normalized.csv"
        digest = hashlib.sha256(texts[run_tag].encode("utf-8")).hexdigest()
        run_index_rows.append(
            {
                "run_tag": run_tag,
                "scenario": scenario,
                "classification": classification,
                "raw_source": "",
                "boot_id": boot,
                "device_run_id": "UNSET",
                "firmware_version": "fixture",
                "hardware_config_id": "CG-HW-001",
                "started_utc": "2026-01-01T00:00:00Z",
                "ended_utc": "2026-01-01T00:01:10Z",
                "capture_date_record": "",
                "timebase": "HOST_STAMP",
                "frames": str(len(rows)),
                "host_time_source": "FIXTURE",
                "device_timestamp_utc_source": "DEVICE_HAS_NO_WALL_CLOCK",
                "dataset_path": dataset_path,
                "dataset_sha256": digest,
            }
        )
        outputs.append({"package_path": dataset_path, "sha256": digest})
    run_index_text = io.StringIO()
    writer = csv.DictWriter(
        run_index_text, fieldnames=list(run_index_rows[0].keys()), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(run_index_rows)
    (dataset_dir / "run_index.csv").write_bytes(
        run_index_text.getvalue().encode("utf-8")
    )
    manifest = {
        "totals": {
            "runs_and_segments": len(run_index_rows),
            "frames_total": sum(int(row["frames"]) for row in run_index_rows),
        },
        "outputs": outputs,
        "inputs": [],
    }
    (dataset_dir / "manifest.json").write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    inventory = {
        "schema": recovery.INPUT_INVENTORY_SCHEMA,
        "a_package_pins": {
            "source_revision": "FIXTURE",
            "manifest_sha256": _sha(dataset_dir / "manifest.json"),
            "run_index_sha256": _sha(dataset_dir / "run_index.csv"),
        },
        "sources": [
            {
                "source_id": "FIXTURE:RUN_INDEX",
                "kind": "A_RUN_INDEX",
                "path": "run_index.csv",
                "expected_sha256": _sha(dataset_dir / "run_index.csv"),
                "required": True,
                "root": "A_DATASET",
            },
            {
                "source_id": "FIXTURE:MANIFEST",
                "kind": "A_DATASET_MANIFEST",
                "path": "manifest.json",
                "expected_sha256": _sha(dataset_dir / "manifest.json"),
                "required": True,
                "root": "A_DATASET",
            },
            {
                "source_id": "A:TIMING",
                "kind": "A_TIMING_REPORT",
                "path": "evidence/A/W13/plant-timing-report.json",
                "expected_sha256": recovery.A_W13_TIMING_REPORT_SHA256,
                "required": True,
                "root": "REPOSITORY",
            },
            {
                "source_id": "W05:EXPORT",
                "kind": "W05_EXPORT",
                "path": "evidence/A/W09/exports/CG-S1-H8C-600S.json",
                "expected_sha256": recovery.W05_EXPORT_SHA256,
                "required": True,
                "root": "REPOSITORY",
            },
            {
                "source_id": "W05:ROW_VALIDITY",
                "kind": "W05_ROW_VALIDITY",
                "path": "evidence/A/W09/exports/CG-S1-H8C-600S.row-validity.csv",
                "expected_sha256": recovery.W05_ROW_VALIDITY_SHA256,
                "required": True,
                "root": "REPOSITORY",
            },
            {
                "source_id": "W05:RAW",
                "kind": "W05_RAW",
                "path": "evidence/A/W04/tec-cooling-response-600s.csv",
                "expected_sha256": recovery.W05_RAW_SHA256,
                "required": True,
                "root": "REPOSITORY",
            },
            {
                "source_id": "W05:RUN_INDEX",
                "kind": "W05_RUN_INDEX",
                "path": "evidence/A/W09/s1-run-index.json",
                "expected_sha256": recovery.W05_RUN_INDEX_SHA256,
                "required": True,
                "root": "REPOSITORY",
            },
            {
                "source_id": "W21:MANIFEST",
                "kind": "W21_MANIFEST",
                "path": "ml/reports/W21/w21-manifest.json",
                "expected_sha256": recovery.W21_MANIFEST_SHA256,
                "required": True,
                "root": "REPOSITORY",
            },
        ],
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_bytes(
        (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    return dataset_dir, inventory_path


def _run_cli(
    *,
    dataset_dir: Path,
    inventory: Path | None,
    out: Path,
    revision: str = "FIXTURE",
) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(CLI),
        "--a-dataset-dir",
        str(dataset_dir),
        "--a-dataset-label",
        "fixture-dataset",
        "--out",
        str(out),
        "--repository-revision",
        revision,
    ]
    if inventory is not None:
        args.extend(["--source-inventory", str(inventory)])
    return subprocess.run(
        args,
        cwd=str(ML_ROOT),
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# Probe 23 and manifest binding
def test_committed_reports_exist_and_manifest_binds_hashes():
    assert REPORTS.is_dir()
    expected = {
        "source-inventory.json",
        "physical-data-assessment.md",
        "real-observation-summary.csv",
        "predictive-eligibility-review.md",
        "gate-b-reassessment.md",
        "presentation-summary-vi.md",
        "recovery-manifest.json",
    }
    assert {path.name for path in REPORTS.iterdir() if path.is_file()} >= expected
    manifest = json.loads((REPORTS / "recovery-manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["reports"].items():
        assert _sha(REPORTS / name) == digest, name
    for name, digest in manifest["plots"].items():
        assert _sha(REPORTS / name) == digest, name
    assert _sha(REPORTS / "source-inventory.json") == manifest["source_inventory_sha256"]
    assert (
        _sha(REPORTS / "real-observation-summary.csv")
        == manifest["observations_csv_sha256"]
    )


# Probe 23
def test_plots_declare_source_identity_units_and_limits():
    plot_dir = REPORTS / "real-physical-plots"
    assert plot_dir.is_dir()
    for path in sorted(plot_dir.glob("*.svg")):
        text = path.read_text(encoding="utf-8")
        assert "PHYSICAL_RECORDED_DATA" in text, path.name
        assert "sha256" in text, path.name
        assert re.search(r"[0-9a-f]{64}", text), path.name
        assert "scenario" in text, path.name
        assert "boot" in text, path.name
        assert "degC" in text, path.name
        if path.name.startswith("cooling-"):
            assert "T2" in text, path.name
        if path.name.startswith("door-"):
            assert "door" in text.lower(), path.name
        if path.name == "w05-diagnostic.svg":
            assert "A ledger INVALID" in text, path.name
        if path.name == "missingness-inventory.svg":
            assert "A20261107 manifest sha256" in text, path.name
            assert "W05 export sha256" in text, path.name


# Probe 24
def test_missing_ewt_and_aiw_are_never_rendered_as_zero():
    text = (REPORTS / "real-observation-summary.csv").read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    for quantity in ("EWT", "AIW"):
        values = [row["value"] for row in rows if row["quantity"] == quantity]
        assert values
        assert all(value == "NOT_ESTIMABLE" for value in values)
    reports = "\n".join(
        path.read_text(encoding="utf-8")
        for path in REPORTS.glob("*.md")
    )
    assert not re.search(r"\bEWT\s*=\s*0(?:\.0+)?\b", reports)
    assert not re.search(r"\bAIW\s*=\s*0(?:\.0+)?\b", reports)


# Probe 25
def test_no_final_physical_ab_improvement_is_fabricated():
    manifest = json.loads((REPORTS / "recovery-manifest.json").read_text(encoding="utf-8"))
    assert manifest["scientific_status"]["W20_PHYSICAL_AB_ANALYSIS"] == "NOT_RUN"
    text = (REPORTS / "physical-data-assessment.md").read_text(encoding="utf-8")
    assert "W20" in text or "A/B" in text or "Gate B" in text
    assert "W20_PHYSICAL_AB_ANALYSIS:\nNOT_RUN" in text


# Probe 26
def test_gate_b_is_independent_of_demo_readiness():
    manifest = json.loads((REPORTS / "recovery-manifest.json").read_text(encoding="utf-8"))
    statuses = manifest["scientific_status"]
    gate_b = manifest["gate_b"]
    assert statuses["GATE_B_PHYSICAL_DATA"] == gate_b["GATE_B_PHYSICAL_DATA"]
    assert statuses["PREDICTIVE_DATASET_READINESS"] == gate_b[
        "PREDICTIVE_DATASET_READINESS"
    ]
    assert statuses["DEADLINE_DEMO_PACKAGE"] in {"READY", "PARTIAL", "BLOCKED"}
    assert statuses["EXISTING_DATA_REUSE"] == "READY_FOR_BOUNDED_ANALYSIS"
    assert "DEADLINE_DEMO_PACKAGE" not in gate_b
    assert gate_b["GATE_B_PHYSICAL_DATA"] == "RED"


def test_w05_quantities_bind_to_the_row_validity_bytes():
    rows = list(
        csv.DictReader(
            io.StringIO(
                (REPORTS / "real-observation-summary.csv").read_text(encoding="utf-8")
            )
        )
    )
    w05 = [row for row in rows if row["source_id"] == "W05A:CG-S1-H8C-600S"]
    assert w05
    assert all(
        row["source_path"].endswith("CG-S1-H8C-600S.row-validity.csv")
        for row in w05
    )
    assert all(
        row["source_sha256"] == recovery.W05_ROW_VALIDITY_SHA256 for row in w05
    )


def test_unknown_door_windows_are_not_labelled_closed_in_inventory():
    inventory = json.loads((REPORTS / "source-inventory.json").read_text(encoding="utf-8"))
    by_id = {source["source_id"]: source for source in inventory["sources"]}
    assert (
        by_id["A20261107:trial1-imported"]["door_event_availability"]
        == "RECORDED_UNVERIFIED_NO_EVENT"
    )
    assert (
        by_id["A20261107:trial2"]["door_event_availability"]
        == "RECORDED_CLOSED_NO_EVENT"
    )


def test_gate_b_report_does_not_claim_the_18_row_package_was_admitted():
    text = (REPORTS / "gate-b-reassessment.md").read_text(encoding="utf-8")
    assert "18_ROW_PACKAGE_ADMITTED = NO" in text
    assert "W08_EVALUATED = W05_CANDIDATE_ONLY" in text
    assert "CANONICAL_VALIDATOR_ACCEPTS_18_ROW_PACKAGE = YES" not in text


# Probe 27
def test_descriptive_sources_are_not_discarded_because_training_admission_fails():
    inventory = json.loads((REPORTS / "source-inventory.json").read_text(encoding="utf-8"))
    sources = inventory["sources"]
    assert inventory["family_totals"]["predictive_eligible_runs"] == 0
    assert any(
        recovery.USE_DESCRIPTION in source["permitted_uses"]
        or recovery.USE_DISTURBANCE in source["permitted_uses"]
        for source in sources
    )
    assert any(
        source["source_family"] == "W05_A_EXPORT" for source in sources
    )


# Probe 28
def test_every_quantitative_result_maps_to_source_and_calculation():
    text = (REPORTS / "real-observation-summary.csv").read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows
    for row in rows:
        assert row["source_id"]
        assert row["source_path"]
        assert re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])
        assert row["calculation_rule"]
        assert row["frame_count"]
        assert row["independent_run_count"] == "0"
        assert row["independent_session_count"] in {"0", "1", "8"}
        assert row["value"] not in {"", "None", "nan", "NaN"}
        assert row["evidence_class"]


# Probe 6 and 3 (fixture integration)
def test_missing_optional_source_does_not_stop_other_analysis(tmp_path):
    dataset_dir, inventory = _write_fixture(tmp_path, missing_s2=True)
    out = tmp_path / "out"
    completed = _run_cli(dataset_dir=dataset_dir, inventory=inventory, out=out)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    payload = json.loads((out / "source-inventory.json").read_text(encoding="utf-8"))
    unavailable = {item["source_id"] for item in payload["unavailable_sources"]}
    assert "A20261107:fixture-s2" in unavailable
    assert payload["family_totals"]["analyzed_segments"] == 1
    assert (out / "physical-data-assessment.md").is_file()


def test_duplicate_exact_rows_are_detected_and_disclosed(tmp_path):
    dataset_dir, inventory = _write_fixture(tmp_path, duplicate=True)
    out = tmp_path / "out"
    completed = _run_cli(dataset_dir=dataset_dir, inventory=inventory, out=out)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    payload = json.loads((out / "source-inventory.json").read_text(encoding="utf-8"))
    record = next(
        source
        for source in payload["sources"]
        if source["source_id"] == "A20261107:fixture-s1"
    )
    assert record["record_count"] == 7
    assert record["descriptive_metrics"]["analyzed_frames"] == 6
    assert any(
        flag.startswith("EXACT_DUPLICATE_ROWS_DEDUPLICATED=1")
        for flag in record["quality_flags"]
    )


# Probe 29
def test_fixture_cli_is_deterministic_and_has_no_absolute_paths(tmp_path):
    dataset_dir, inventory = _write_fixture(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    one = _run_cli(dataset_dir=dataset_dir, inventory=inventory, out=first)
    two = _run_cli(dataset_dir=dataset_dir, inventory=inventory, out=second)
    assert one.returncode == 0, one.stderr + one.stdout
    assert two.returncode == 0, two.stderr + two.stdout
    assert _file_hashes(first) == _file_hashes(second)
    for path in first.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".csv", ".json", ".svg"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            assert "D:\\" not in text
            assert "C:\\" not in text
            assert "/d/iot" not in text
            assert str(tmp_path) not in text


def test_missing_required_provenance_pin_fails_closed(tmp_path):
    dataset_dir, inventory = _write_fixture(tmp_path)
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["kind"] == "A_TIMING_REPORT":
            source.pop("expected_sha256", None)
    inventory.write_bytes(
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    out = tmp_path / "out"
    completed = _run_cli(dataset_dir=dataset_dir, inventory=inventory, out=out)
    assert completed.returncode == 2
    assert "SHA-256 pin" in completed.stderr
    assert not out.exists() or not any(out.iterdir())


def test_generated_inventory_replay_matches_direct_run(tmp_path):
    dataset_dir, inventory = _write_fixture(tmp_path)
    first = tmp_path / "first"
    replay = tmp_path / "replay"
    one = _run_cli(dataset_dir=dataset_dir, inventory=inventory, out=first)
    assert one.returncode == 0, one.stderr + one.stdout
    two = _run_cli(
        dataset_dir=dataset_dir,
        inventory=first / "source-inventory.json",
        out=replay,
    )
    assert two.returncode == 0, two.stderr + two.stdout
    assert _file_hashes(first) == _file_hashes(replay)


# Probe 30
def test_no_network_actuator_or_device_control_capability():
    forbidden_imports = {
        "socket",
        "requests",
        "httpx",
        "paho",
        "serial",
        "gpio",
        "smbus",
        "spidev",
        "http",
        "urllib",
    }
    for path in (MODULE, CLI):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & forbidden_imports), (path.name, imported)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"system", "popen", "spawn"}:
                    raise AssertionError(f"{path.name} calls {node.func.attr}")
    source = MODULE.read_text(encoding="utf-8") + CLI.read_text(encoding="utf-8")
    for token in ("mqtt", "paho", "serial.Serial", "GPIO", "actuate_"):
        assert token not in source


def test_w16_locked_test_is_not_opened_or_bound():
    manifest = json.loads((REPORTS / "recovery-manifest.json").read_text(encoding="utf-8"))
    assert manifest["scientific_status"]["W16_LOCKED_TEST"] == "NOT_OPENED"
    inventory = json.loads((REPORTS / "source-inventory.json").read_text(encoding="utf-8"))
    for source in inventory["sources"]:
        assert "W16" not in source["source_path"]
    observations = (REPORTS / "real-observation-summary.csv").read_text(encoding="utf-8")
    assert "W16" not in observations
    assert any("W16" in item for item in inventory["not_read"])
