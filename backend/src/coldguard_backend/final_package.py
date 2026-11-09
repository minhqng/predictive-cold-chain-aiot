"""Frozen-source B-ready JSON package with honest, content-bound claim references."""

import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import TypeAdapter

from coldguard_backend.campaign_freeze import FileName, _metadata_versions
from coldguard_backend.evidence_backup import verify_backup_bytes
from coldguard_backend.evidence_package import digest, publish_package, read_verified_package
from coldguard_backend.evidence_paths import portable_component
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.final_audit import audit_campaign_export, document, require, row_index, stamp
from coldguard_backend.incident_audit import FORMAT as INCIDENT_FORMAT, IncidentJournal

FORMAT = "coldguard-final-data-package-v1"
FROZEN_FORMAT = "coldguard-campaign-freeze-v1"
LABEL = TypeAdapter(FileName)


def _labels(labels):
    require(len(labels) <= 20, "too many incident package inputs")
    for label in labels:
        LABEL.validate_python(label)
    require(len({label.casefold() for label in labels}) == len(labels), "incident package labels collide")


def _root(path: Path):
    for part in path.parts:
        if part not in {path.anchor, ".", ".."}:
            portable_component(part)
    require(not path.is_symlink() and not (hasattr(path, "is_junction") and path.is_junction()), "package root must not be an alias")
    return path.resolve()


def _snapshot(files: dict[str, bytes], *, format: str, anchor: str) -> dict:
    require(isinstance(anchor, str) and re.fullmatch(r"[0-9a-f]{64}", anchor), "a separately trusted manifest anchor is required")
    require(digest(files["manifest.json"]) == anchor, "nested source manifest differs from trusted anchor")
    manifest = document(files["manifest.json"])
    require(manifest["format"] == format and isinstance(manifest["files"], dict)
            and set(files) == {"manifest.json", *manifest["files"]}, "nested source file inventory differs")
    require(all(digest(files[name]) == checksum for name, checksum in manifest["files"].items()), "nested source checksum differs")
    return manifest


def _frozen(files: dict[str, bytes], *, anchor: str, record: dict | None = None) -> tuple[dict, dict, dict]:
    manifest = _snapshot(files, format=FROZEN_FORMAT, anchor=anchor)
    content = files["campaign-export.json"]
    audit = audit_campaign_export(content)
    bundle = document(content)
    export = bundle["manifest"]
    for key in ("campaign_id", "dataset_id", "data_class", "namespace_sha256", "run_ids", "pair_ids", "backend_commit", "created_at"):
        require(manifest[key] == export[key], "frozen manifest/export identity or provenance differs")
    require(manifest["physical_acceptance"] == "BLOCKED_EXTERNAL", "frozen input cannot grant physical acceptance")
    receipt = verify_backup_bytes(files["backup/receipt.json"], files["backup/database.dump"])
    require(receipt["source_fingerprints"] == manifest["source_fingerprints"]
            and manifest["source_fingerprints"]["revisions"] == [manifest["schema_revision"]]
            and manifest["schema_revision"] == "0014", "frozen backup/schema fingerprints differ")
    for key in ("campaign_id", "data_class", "namespace_sha256"):
        require(receipt[key] == manifest[key], "frozen backup campaign scope differs")
    roles = manifest["artifact_roles"]
    require(isinstance(roles, dict) and {"model_metadata", "policy_metadata", "broker_config", "backend_config"} <= set(roles)
            and set(roles) <= {"model_metadata", "policy_metadata", "broker_config", "backend_config", "model_reference", "policy_reference"}
            and len(set(roles.values())) == len(roles), "frozen artifact roles are incomplete or aliased")
    require(set(files) == {"manifest.json", "campaign-export.json", "backup/receipt.json", "backup/database.dump", *roles.values()}, "unbound frozen artifact")
    artifacts = {kind: files[name] for kind, name in roles.items()}
    models = document(artifacts["model_metadata"])
    document(artifacts["policy_metadata"])
    _metadata_versions(bundle["dataset"]["campaign"], artifacts)
    model_rows = {row["model_version"]: row for row in models["models"]}
    for prediction in bundle["dataset"]["tables"]["predictions"]:
        reference = model_rows[prediction["model_version"]]
        require(prediction["model_sha256"] == reference["artifact_sha256"], "prediction model reference checksum differs")
        if "feature_schema_sha256" in reference:
            require(prediction["feature_schema_sha256"] == reference["feature_schema_sha256"], "prediction feature schema checksum differs")
    if record is not None:
        require(record["manifest_sha256"] == anchor and record["manifest"] == manifest
                and record["export_bytes"] == content and record["export_sha256"] == digest(content)
                and record["source_fingerprints"] == manifest["source_fingerprints"]
                and all(record[key] == manifest[key] for key in ("freeze_id", "campaign_id", "dataset_id", "request_sha256")),
                "immutable freeze record differs from retained frozen source")
    return manifest, bundle, audit


def _incident(files: dict[str, bytes], *, anchor: str) -> tuple[dict, dict]:
    manifest = _snapshot(files, format=INCIDENT_FORMAT, anchor=anchor)
    audit = document(files["incident-audit.json"])
    require(digest(files["incident-audit.json"]) == manifest["audit_sha256"]
            and all(audit[key] == manifest[key] for key in ("campaign_id", "data_class", "physical_acceptance")), "incident manifest/audit differs")
    require(audit["format"] == "coldguard-incident-audit-v1" and audit["observation_status"] == "RECORDED_NOT_INDEPENDENTLY_ACCEPTED"
            and audit["observer_clock_sync_verified"] is False and audit["automatic_validity_approval"] is False
            and audit["physical_acceptance"] == "BLOCKED_EXTERNAL", "incident source cannot grant independent acceptance")
    journal = IncidentJournal.model_validate_json(encode_evidence(audit["journal"]))
    require(journal.campaign_id == audit["campaign_id"] and journal.data_class == audit["data_class"], "incident journal scope differs")
    runs = {key[0]: row for key, row in row_index(audit["runs"], ("run_id",)).items()}
    commands = audit["command_evidence"]["commands"]
    row_index(commands, ("command_id",))
    for observation in journal.observations:
        source = "sources/" + observation.source_name
        require(source in files and digest(files[source]) == observation.source_sha256, "incident observer source differs")
        selected = [observation.run_id] if observation.run_id is not None else list(runs)
        require(all(run_id in runs for run_id in selected), "incident observation has unknown run scope")
        require(observation.device_id is None or all(runs[run_id]["device_id"] == observation.device_id for run_id in selected), "incident observation device scope differs")
        raw_ids = {row["id"] for run_id in selected for row in runs[run_id]["raw_receipts"]}
        command_ids = {row["command_id"] for row in commands if row["run_id"] in selected}
        require(set(observation.raw_ids) <= raw_ids and set(observation.command_ids) <= command_ids, "incident observation row reference is missing or outside scope")
    require(set(files) == {"manifest.json", "incident-audit.json", *("sources/" + row.source_name for row in journal.observations)}, "unbound incident source file")
    return manifest, audit


def _reference(file: str, content: bytes, pointer: str, row: dict) -> dict:
    return {"file": file, "file_sha256": digest(content), "json_pointer": pointer, "row_sha256": digest(encode_evidence(row))}


def _claims(export: bytes, bundle: dict, incidents: dict) -> dict:
    claims = []
    def add(identity, status, meaning, references, *, campaign_id=None, run_id=None):
        claims.append({"claim_id": identity, "status": status, "interpretation": meaning,
                       "campaign_id": campaign_id or bundle["manifest"]["campaign_id"], "run_id": run_id,
                       "references": references, "physical_acceptance": "BLOCKED_EXTERNAL"})
    tables = bundle["dataset"]["tables"]
    def table_ref(name, index, row):
        return {**_reference("dataset.json", export, f"/dataset/tables/{name}/{index}", row),
                "table": name}
    for index, run in enumerate(tables["experiments"]):
        add("run:" + run["run_id"], "RECORDED_VALID_FROZEN_INPUT",
            "Recorded software/source qualification and exact run identity; not independent physical or statistical acceptance.",
            [table_ref("experiments", index, run)], run_id=run["run_id"])
    for name in ("commands", "command_attempts", "command_acks", "policy_approvals", "physical_assessments"):
        for index, row in enumerate(tables[name]):
            identity = str(row.get("id", row.get("assessment_id", row["command_id"])))
            status, meaning = "RECORD_PRESENT", "Content-bound evidence row; no physical effect asserted."
            if name == "commands":
                status, meaning = "COMMAND_INTENT_RECORDED", "Intent and envelope identity only, not broker delivery, device execution or physical effect."
            elif name == "command_attempts":
                status = "BROKER_PUBACK_RECORDED" if row["outcome"] == "PUBACK" else "PUBLISH_ATTEMPT_RECORDED"
                meaning = "Recorded publish outcome " + row["outcome"] + "; PUBACK proves transport acknowledgement, not actuation."
            elif name == "command_acks":
                accepted = row["validity"] == "VALID" and (row["device_status"] == "ACCEPTED" or
                           row["device_status"] == "DUPLICATE_CANONICAL" and row["canonical_status"] == "ACCEPTED")
                status = "DEVICE_ACCEPTANCE_ACK_RECORDED" if accepted else "ACK_RECEIPT_RECORDED"
                meaning = "Retained device protocol verdict; an accepted ACK is not independent electrical/thermal/physical verification."
            elif name == "policy_approvals":
                status, meaning = "POLICY_APPROVAL_RECORD_PRESENT", "Stored approval provenance and signature hash, not reauthentication or official Member D acceptance."
            elif name == "physical_assessments":
                status, meaning = "ASSESSMENT_RECORD_PRESENT", "Stored assessment and measurement references, not independent physical acceptance; software fixtures remain fixtures."
            command = next(item for item in tables["commands"] if item["command_id"] == row["command_id"])
            add(name + ":" + identity, status, meaning, [table_ref(name, index, row)], run_id=command["run_id"])
    for label, (_anchor, files, _manifest, audit) in sorted(incidents.items()):
        for index, observation in enumerate(audit["journal"]["observations"]):
            prefix = "incidents/" + label + "/"
            source = "sources/" + observation["source_name"]
            references = [_reference(prefix + "incident-audit.json", files["incident-audit.json"], f"/journal/observations/{index}", observation),
                          {"file": prefix + source, "file_sha256": digest(files[source])}]
            for run_index, run in enumerate(audit["runs"]):
                for raw_index, row in enumerate(run["raw_receipts"]):
                    if row["id"] in observation["raw_ids"]:
                        references.append(_reference(prefix + "incident-audit.json", files["incident-audit.json"], f"/runs/{run_index}/raw_receipts/{raw_index}", row))
            for command_index, row in enumerate(audit["command_evidence"]["commands"]):
                if row["command_id"] in observation["command_ids"]:
                    references.append(_reference(prefix + "incident-audit.json", files["incident-audit.json"], f"/command_evidence/commands/{command_index}", row))
            add("incident:" + label + ":" + observation["event_id"], "RECORDED_NOT_INDEPENDENTLY_ACCEPTED",
                observation["event_type"] + "; separately scoped observer evidence, not an A/B sample or official D/A approval.",
                references, campaign_id=audit["campaign_id"], run_id=observation["run_id"])
    require(len({row["claim_id"] for row in claims}) == len(claims), "claim identities collide")
    return {"format": "coldguard-claim-evidence-index-v1", "data_class": bundle["manifest"]["data_class"],
            "claims": claims, "statistics": "NOT_COMPUTED", "physical_acceptance": "BLOCKED_EXTERNAL"}


def _assemble(source_files: dict, *, source_anchor: str, created_at: datetime, backend_commit: str, incidents: dict, record=None):
    require(isinstance(created_at, datetime) and created_at.utcoffset() is not None and created_at <= datetime.now(timezone.utc), "final builder needs an aware nonfuture time")
    require(isinstance(backend_commit, str) and re.fullmatch(r"[0-9a-f]{40}", backend_commit), "final builder needs a full clean source SHA")
    _labels(incidents)
    source, bundle, audit = _frozen(source_files, anchor=source_anchor, record=record)
    export = source_files["campaign-export.json"]
    inputs = {}
    for label, (anchor, files) in sorted(incidents.items()):
        manifest, incident = _incident(files, anchor=anchor)
        require(incident["data_class"] == source["data_class"], "incident and final package data classes differ")
        inputs[label] = anchor, files, manifest, incident
    run_list = {"format": "coldguard-final-run-list-v1", "data_class": source["data_class"], "dataset_id": source["dataset_id"],
                "campaign_id": source["campaign_id"], "pairs": bundle["dataset"]["pairs"], "runs": bundle["dataset"]["tables"]["experiments"]}
    checksums = {"algorithm": "SHA-256", "original_export_sha256": digest(export), "frozen_manifest_sha256": source_anchor,
                 "frozen_files": {name: digest(data) for name, data in sorted(source_files.items())},
                 "table_sha256": bundle["manifest"]["table_sha256"], "whole_database_fingerprints": source["source_fingerprints"],
                 "artifact_sha256": {kind: digest(source_files[name]) for kind, name in sorted(source["artifact_roles"].items())},
                 "incident_manifest_sha256": {label: value[0] for label, value in sorted(inputs.items())}}
    files = {"dataset.json": export, "run-list.json": encode_evidence(run_list), "integrity-audit.json": encode_evidence(audit),
             "checksums.json": encode_evidence(checksums), "claim-index.json": encode_evidence(_claims(export, bundle, inputs)),
             **{"frozen/" + name: data for name, data in source_files.items()}}
    for label, (_anchor, snapshot, _manifest, _audit) in inputs.items():
        files.update({"incidents/" + label + "/" + name: data for name, data in snapshot.items()})
    metadata = {"campaign_id": source["campaign_id"], "freeze_id": source["freeze_id"], "dataset_id": source["dataset_id"], "data_class": source["data_class"],
                "created_at": created_at.astimezone(timezone.utc).isoformat(), "builder_commit": backend_commit, "frozen_exporter_commit": source["backend_commit"],
                "frozen_export_created_at": source["created_at"], "frozen_manifest_sha256": source_anchor, "original_export_sha256": digest(export),
                "incident_manifest_sha256": checksums["incident_manifest_sha256"], "physical_acceptance": "BLOCKED_EXTERNAL", "statistics": "NOT_COMPUTED"}
    return files, metadata


def create_final_package(directory: Path, record: dict, *, destination: Path, created_at: datetime, backend_commit: str,
                         incidents: dict[str, tuple[Path, str]] | None = None) -> dict:
    """The caller supplies a trusted DB freeze record; no live re-export is performed."""
    try:
        _labels(incidents or {})
        destination_root = _root(destination)
        for root in (directory, *(value[0] for value in (incidents or {}).values())):
            source_root = _root(root)
            require(destination_root != source_root and source_root not in destination_root.parents
                    and destination_root not in source_root.parents, "final output must not overlap immutable input packages")
        _manifest, source = read_verified_package(directory, expected_manifest_sha256=record["manifest_sha256"], format=FROZEN_FORMAT)
        snapshots = {}
        for label, (root, anchor) in sorted((incidents or {}).items()):
            _manifest, snapshot = read_verified_package(root, expected_manifest_sha256=anchor, format=INCIDENT_FORMAT)
            snapshots[label] = anchor, snapshot
        files, metadata = _assemble(source, source_anchor=record["manifest_sha256"], created_at=created_at,
                                    backend_commit=backend_commit, incidents=snapshots, record=record)
        return publish_package(destination, files, format=FORMAT, metadata=metadata)
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("malformed final package inputs") from error


def verify_final_package(directory: Path, *, expected_manifest_sha256: str) -> dict:
    """Recompute all derived audit/hash/index bytes from retained, chained snapshots."""
    try:
        _root(directory)
        manifest, snapshot = read_verified_package(directory, expected_manifest_sha256=expected_manifest_sha256, format=FORMAT)
        source = {name.removeprefix("frozen/"): data for name, data in snapshot.items() if name.startswith("frozen/")}
        incidents = {label: (anchor, {name.removeprefix("incidents/" + label + "/"): data for name, data in snapshot.items()
                     if name.startswith("incidents/" + label + "/")}) for label, anchor in manifest["incident_manifest_sha256"].items()}
        files, metadata = _assemble(source, source_anchor=manifest["frozen_manifest_sha256"], created_at=stamp(manifest["created_at"]),
                                    backend_commit=manifest["builder_commit"], incidents=incidents)
        require(snapshot == {"manifest.json": snapshot["manifest.json"], **files}, "final dataset/audit/index differs from retained source")
        require(manifest == document(encode_evidence({"format": FORMAT, **metadata, "files": {name: digest(data) for name, data in sorted(files.items())}})),
                "final manifest metadata differs from retained source")
        return manifest
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("malformed final package") from error
