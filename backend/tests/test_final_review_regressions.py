"""W22 review discriminators; owned fixtures only, never physical acceptance."""

import json
import os
from pathlib import Path

import pytest

from coldguard_backend.evidence_package import digest, package_path
from coldguard_backend.evidence_paths import portable_component
from coldguard_backend.final_audit import audit_campaign_export
from coldguard_backend.final_package import _root, create_final_package
from tests.command_testkit import utcnow
from tests.test_final_package import final_context, rehashed


@pytest.mark.parametrize("path", ["../evidence-out/freeze-v1", "../evidence-out/final-json-v1",
    "../evidence-out/final-json-report.json", "../evidence-out/final-json-verify.json"])
def test_explicit_operator_roots_allow_documented_parent_navigation(tmp_path, monkeypatch, path):
    from scripts.final_package import _portable
    backend = tmp_path / "backend"
    backend.mkdir()
    monkeypatch.chdir(backend)
    value = Path(path)
    _portable(value)
    assert _root(value) == (backend / value).resolve()


def test_actual_json_cli_accepts_parent_relative_paths_and_verifies_without_db(db_engine, tmp_path, monkeypatch):
    from scripts import final_package as cli
    context, record = final_context(db_engine, tmp_path / "source")
    working = tmp_path / "backend"
    working.mkdir()
    monkeypatch.chdir(working)
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    # This test isolates JSON/path admission. A separate clean-Git CLI drill proves real provenance.
    monkeypatch.setattr(cli, "clean_backend_commit", lambda _root: "b" * 40)
    target = tmp_path / "evidence-out/final"
    report = tmp_path / "build.json"
    monkeypatch.setattr("sys.argv", ["final_package.py", "build", "--frozen", os.path.relpath(context["destination"], working),
        "--freeze-id", record["freeze_id"], "--created-at", utcnow().isoformat(), "--directory", os.path.relpath(target, working),
        "--report", os.path.relpath(report, working)])
    assert cli.main() == 0
    result = json.loads(report.read_bytes())
    assert (target / "dataset.json").read_bytes() == record["export_bytes"]
    monkeypatch.setattr(cli, "create_engine", lambda *_args, **_kwargs: pytest.fail("verify created a DB engine"))
    monkeypatch.setattr("sys.argv", ["final_package.py", "verify", "--directory", os.path.relpath(target, working),
        "--manifest-sha256", result["manifest_sha256"], "--report", "../verify.json"])
    assert cli.main() == 0


@pytest.mark.parametrize("component", ["NUL", "CON.txt", "COM\u00b9.log", "name.", "name "])
def test_root_navigation_fix_does_not_open_reserved_or_aliased_components(component, monkeypatch):
    monkeypatch.setattr(Path, "is_symlink", lambda *_args: pytest.fail("reserved name reached filesystem"))
    with pytest.raises(ValueError):
        _root(Path("..") / component)
    with pytest.raises(ValueError):
        portable_component(component)


def test_internal_package_traversal_remains_rejected(tmp_path):
    for name in ("../outside.json", "sources/../observer.json", "sources/./observer.json"):
        with pytest.raises(ValueError):
            package_path(tmp_path, name)


@pytest.mark.parametrize("defect", ["verdict", "command", "device", "canonical_verdict", "reapplied", "ack_time", "schema", "applied"])
def test_valid_ack_wire_and_cached_protocol_projection_must_agree(db_engine, tmp_path, defect):
    _context, record = final_context(db_engine, tmp_path, commands=True)
    bundle = json.loads(record["export_bytes"])
    row = bundle["dataset"]["tables"]["command_acks"][0]
    wire = json.loads(row["raw_payload"])
    if defect == "verdict":
        wire["status"] = "REJECTED"
    elif defect == "command":
        wire["command_id"] = "different-software-command"
    elif defect == "device":
        wire["device_id"] = "different-software-device"
    elif defect == "canonical_verdict":
        wire["status"] = row["device_status"] = "DUPLICATE_CANONICAL"
        wire["canonical_status"], row["canonical_status"] = "REJECTED", "ACCEPTED"
    elif defect == "reapplied":
        wire["reapplied"] = True
    elif defect == "ack_time":
        wire["ack_time"] = utcnow().isoformat()
    elif defect == "schema":
        wire["schema_version"] = True
    else:
        wire["applied"] = {"cooling": "ON", "duty": 0.5}
    row["raw_payload"] = json.dumps(wire)
    row["payload_sha256"] = digest(row["raw_payload"].encode())
    with pytest.raises(ValueError, match="ACK"):
        audit_campaign_export(rehashed(bundle))


@pytest.mark.parametrize("status,canonical,accepted", [("ACCEPTED", None, True), ("REJECTED", None, False),
    ("DUPLICATE_CANONICAL", "ACCEPTED", True), ("DUPLICATE_CANONICAL", "REJECTED", False)])
def test_legitimate_accepted_rejected_and_canonical_ack_controls(db_engine, tmp_path, status, canonical, accepted):
    context, record = final_context(db_engine, tmp_path / "source", commands=True, ack_status=status, canonical_status=canonical)
    audit_campaign_export(record["export_bytes"])
    target = tmp_path / "final"
    create_final_package(context["destination"], record, destination=target, created_at=utcnow(), backend_commit="b" * 40)
    claim = next(row for row in json.loads((target / "claim-index.json").read_bytes())["claims"] if row["claim_id"].startswith("command_acks:"))
    assert (claim["status"] == "DEVICE_ACCEPTANCE_ACK_RECORDED") is accepted
    assert claim["physical_acceptance"] == "BLOCKED_EXTERNAL"


@pytest.mark.parametrize("validity", ["CONFLICT", "LATE"])
def test_nonaccepted_receipts_remain_retained_and_do_not_become_acceptance_claims(db_engine, tmp_path, validity):
    from coldguard_backend.final_package import _claims
    _context, record = final_context(db_engine, tmp_path, commands=True)
    bundle = json.loads(record["export_bytes"])
    row = bundle["dataset"]["tables"]["command_acks"][0]
    row["validity"] = validity
    content = rehashed(bundle)
    original_wire = row["raw_payload"]
    audit_campaign_export(content)
    claims = _claims(content, json.loads(content), {})["claims"]
    claim = next(item for item in claims if item["claim_id"].startswith("command_acks:"))
    assert claim["status"] == "ACK_RECEIPT_RECORDED"
    assert json.loads(content)["dataset"]["tables"]["command_acks"][0]["raw_payload"] == original_wire
