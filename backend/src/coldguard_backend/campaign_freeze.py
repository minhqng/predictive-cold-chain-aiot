"""Content-addressed freeze records and fail-closed artifact publication."""

import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import Column, DateTime, LargeBinary, MetaData, Table, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine

from coldguard_backend.campaign_export import build_campaign_export
from coldguard_backend.campaign_store import campaigns, get_campaign
from coldguard_backend.evidence_backup import read_verified_backup, restore_backup_bytes, verify_backup_bytes
from coldguard_backend.evidence_paths import portable_component
from coldguard_backend.evidence_tables import fingerprint_connection
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import Identifier

campaign_freezes = Table(
    "campaign_freezes", MetaData(),
    Column("freeze_id", Text, primary_key=True), Column("campaign_id", Text),
    Column("dataset_id", Text), Column("request_sha256", Text), Column("manifest", JSONB),
    Column("manifest_sha256", Text), Column("export_sha256", Text), Column("export_bytes", LargeBinary),
    Column("source_fingerprints", JSONB), Column("frozen_at", DateTime(timezone=True)),
    Column("recorded_at", DateTime(timezone=True)),
)
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
FileName = Annotated[str, StringConstraints(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"), AfterValidator(portable_component)]


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: FileName
    kind: Literal["model_metadata", "policy_metadata", "broker_config", "backend_config", "model_reference", "policy_reference"]
    sha256: Digest


class FreezeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    freeze_id: Identifier
    campaign_id: Identifier
    created_at: AwareDatetime
    backend_commit: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    artifacts: Annotated[list[ArtifactReference], Field(min_length=4, max_length=100)]

    @model_validator(mode="after")
    def _complete_references(self):
        kinds = [item.kind for item in self.artifacts]
        if len(set(item.name for item in self.artifacts)) != len(self.artifacts) or len(set(kinds)) != len(kinds):
            raise ValueError("artifact names and roles must be distinct")
        if not {"model_metadata", "policy_metadata", "broker_config", "backend_config"} <= set(kinds):
            raise ValueError("freeze requires model/policy metadata and broker/backend config")
        return self


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _artifact_bytes(root: Path, reference: ArtifactReference) -> bytes:
    path = root / reference.name
    if path.is_symlink() or path.resolve().parent != root.resolve():
        raise ValueError("artifact must be a direct regular file inside its configured directory")
    content = path.read_bytes()
    if _digest(content) != reference.sha256:
        raise ValueError("artifact checksum differs: " + reference.name)
    return content


def _metadata_versions(campaign: dict, artifacts: dict[str, bytes]) -> None:
    namespace = campaign["namespace"]
    for kind, collection, field in (("model_metadata", "models", "model_version"), ("policy_metadata", "policies", "policy_version")):
        document = json.loads(artifacts[kind])
        if document.get("data_class") != campaign["data_class"] or not isinstance(document.get(collection), list):
            raise ValueError("metadata data class or version collection differs")
        declared = {plan["run"]["versions"][field] for plan in namespace["runs"]}
        rows = document[collection]
        versions = [row.get(field) for row in rows if isinstance(row, dict)]
        if len(versions) != len(rows) or len(set(versions)) != len(versions) or set(versions) != declared:
            raise ValueError("metadata versions conflict with the frozen campaign")
        reference_kind = "model_reference" if kind == "model_metadata" else "policy_reference"
        for row in rows:
            if row[field] == "NOT_APPLICABLE":
                continue
            if reference_kind not in artifacts or row.get("artifact_sha256") != _digest(artifacts[reference_kind]):
                raise ValueError("metadata artifact provenance is missing or conflicting")
            if kind == "model_metadata" and any(
                row.get("feature_version") != plan["run"]["versions"]["feature_version"]
                for plan in namespace["runs"] if plan["run"]["versions"]["model_version"] == row[field]
            ):
                raise ValueError("model feature provenance conflicts with the frozen campaign")


def get_freeze(connection, freeze_id: str) -> dict:
    row = connection.execute(select(campaign_freezes).where(campaign_freezes.c.freeze_id == freeze_id)).mappings().one_or_none()
    if row is None:
        raise ValueError("freeze record not found")
    return dict(row)


def _safe_package_path(root: Path, name: str) -> Path:
    path = root / name
    if path.is_symlink() or root.resolve() not in path.resolve().parents:
        raise ValueError("frozen artifact path escapes the package")
    return path


def read_verified_frozen_package(directory: Path, *, expected_manifest_sha256: str) -> tuple[dict, dict[str, bytes]]:
    if re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) is None:
        raise ValueError("a trusted immutable manifest SHA-256 is required")
    content = _safe_package_path(directory, "manifest.json").read_bytes()
    if _digest(content) != expected_manifest_sha256:
        raise ValueError("frozen manifest checksum differs from its immutable anchor")
    manifest = json.loads(content)
    if manifest.get("format") != "coldguard-campaign-freeze-v1":
        raise ValueError("unsupported frozen package format")
    expected_files = {"manifest.json", *manifest["files"]}
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if actual != expected_files:
        raise ValueError("frozen package has missing or unexpected artifacts")
    files = {}
    for name, checksum in manifest["files"].items():
        data = _safe_package_path(directory, name).read_bytes()
        if _digest(data) != checksum:
            raise ValueError("frozen artifact checksum differs: " + name)
        files[name] = data
    bundle = json.loads(files["campaign-export.json"])
    if _digest(encode_evidence(bundle["dataset"])) != bundle["manifest"]["dataset_sha256"] or bundle["manifest"]["dataset_id"] != manifest["dataset_id"]:
        raise ValueError("frozen dataset checksum or identity differs")
    backup = verify_backup_bytes(files["backup/receipt.json"], files["backup/database.dump"])
    if backup["source_fingerprints"] != manifest["source_fingerprints"]:
        raise ValueError("frozen backup source fingerprints differ from its anchored manifest")
    return manifest, files


def verify_frozen_package(directory: Path, *, expected_manifest_sha256: str) -> dict:
    manifest, _ = read_verified_frozen_package(directory, expected_manifest_sha256=expected_manifest_sha256)
    return manifest


def _write_artifact(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(content)


def freeze_campaign(engine: Engine, draft: FreezeDraft, *, artifact_root: Path, backup_directory: Path, destination: Path) -> dict:
    if draft.created_at > datetime.now(timezone.utc):
        raise ValueError("freeze timestamp cannot be in the future")
    references = {item.kind: _artifact_bytes(artifact_root, item) for item in draft.artifacts}
    receipt, backup_receipt, archive = read_verified_backup(backup_directory)
    request = {**draft.model_dump(mode="json"), "backup_receipt_sha256": _digest(backup_receipt), "archive_sha256": _digest(archive)}
    request["artifacts"].sort(key=lambda item: item["kind"])
    request_sha = _digest(encode_evidence(request))
    stage = None
    published = False
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with connection.begin():
                # A stable lock snapshot is required; serialization failures are not retried silently.
                connection.execute(select(campaigns.c.campaign_id).where(campaigns.c.campaign_id == draft.campaign_id).with_for_update())
                existing = connection.execute(select(campaign_freezes).where(campaign_freezes.c.freeze_id == draft.freeze_id)).mappings().one_or_none()
                if existing is not None:
                    if existing["request_sha256"] != request_sha:
                        raise ValueError("freeze ID already has different immutable inputs")
                    if not destination.exists():
                        raise ValueError("existing freeze has no package at this path; restore the original artifacts explicitly")
                    verify_frozen_package(destination, expected_manifest_sha256=existing["manifest_sha256"])
                    return dict(existing)
                if destination.exists():
                    raise FileExistsError("freeze destination already exists; never overwrite a frozen artifact")
                campaign = get_campaign(connection, draft.campaign_id)
                if receipt["campaign_id"] != draft.campaign_id or receipt["namespace_sha256"] != campaign["namespace_sha256"] or receipt["data_class"] != campaign["data_class"]:
                    raise ValueError("backup belongs to another campaign or namespace")
                _metadata_versions(campaign, references)
                content = build_campaign_export(connection, draft.campaign_id, created_at=draft.created_at, backend_commit=draft.backend_commit)
                fingerprints = fingerprint_connection(connection)
                # Freeze records are backed up separately after publication. They cannot be part of their own input hash.
                comparable = lambda value: {key: row for key, row in value["tables"].items() if key != "campaign_freezes"}
                if fingerprints["revisions"] != receipt["source_fingerprints"]["revisions"] or comparable(fingerprints) != comparable(receipt["source_fingerprints"]):
                    raise ValueError("backup snapshot differs from current campaign evidence")
                bundle = json.loads(content)
                models = {row["model_version"]: row for row in json.loads(references["model_metadata"])["models"]}
                if any(row["model_sha256"] != models[row["model_version"]]["artifact_sha256"] for row in bundle["dataset"]["tables"]["predictions"]):
                    raise ValueError("prediction model hash conflicts with frozen model metadata")
                files = {"campaign-export.json": content, "backup/receipt.json": backup_receipt, "backup/database.dump": archive}
                for item in draft.artifacts:
                    files["artifacts/" + item.name] = references[item.kind]
                manifest = {"format": "coldguard-campaign-freeze-v1", "freeze_id": draft.freeze_id,
                    "campaign_id": draft.campaign_id, "dataset_id": bundle["manifest"]["dataset_id"],
                    "data_class": campaign["data_class"], "run_ids": bundle["manifest"]["run_ids"],
                    "pair_ids": bundle["manifest"]["pair_ids"], "namespace_sha256": campaign["namespace_sha256"],
                    "created_at": draft.created_at, "backend_commit": draft.backend_commit,
                    "schema_revision": fingerprints["revisions"][0], "request_sha256": request_sha,
                    "artifact_roles": {item.kind: "artifacts/" + item.name for item in draft.artifacts},
                    "files": {name: _digest(data) for name, data in sorted(files.items())},
                    "source_fingerprints": receipt["source_fingerprints"], "physical_acceptance": "BLOCKED_EXTERNAL"}
                manifest_content = encode_evidence(manifest)
                stage = Path(tempfile.mkdtemp(prefix=".freeze-staging-", dir=destination.parent))
                for name, data in files.items():
                    _write_artifact(stage / name, data)
                _write_artifact(stage / "manifest.json", manifest_content)
                row = connection.execute(insert(campaign_freezes).values(
                    freeze_id=draft.freeze_id, campaign_id=draft.campaign_id, dataset_id=manifest["dataset_id"],
                    request_sha256=request_sha, manifest=json.loads(manifest_content), manifest_sha256=_digest(manifest_content),
                    export_sha256=_digest(content), export_bytes=content, source_fingerprints=receipt["source_fingerprints"],
                    frozen_at=draft.created_at, recorded_at=func.clock_timestamp(),
                ).returning(campaign_freezes)).mappings().one()
                if destination.exists():
                    raise FileExistsError("freeze destination appeared during generation")
                stage.rename(destination)
                published = True
            return dict(row)
    except BaseException:
        if published and stage is not None:
            # Preserve failed files, but remove their ready name if DB commit failed.
            destination.rename(stage)
        raise


def verify_frozen_restore(directory: Path, record: dict, restore_url, *, pg_restore="pg_restore") -> dict:
    manifest, files = read_verified_frozen_package(directory, expected_manifest_sha256=record["manifest_sha256"])
    if (any(record[key] != manifest[key] for key in ("freeze_id", "campaign_id", "dataset_id"))
        or record["export_bytes"] != files["campaign-export.json"] or record["export_sha256"] != _digest(files["campaign-export.json"])):
        raise ValueError("freeze record differs from the anchored package snapshot")
    report = restore_backup_bytes(files["backup/receipt.json"], files["backup/database.dump"], restore_url, pg_restore=pg_restore,
        expected_receipt_sha256=manifest["files"]["backup/receipt.json"], expected_archive_sha256=manifest["files"]["backup/database.dump"])
    from sqlalchemy import create_engine
    engine = create_engine(restore_url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            original = json.loads(record["export_bytes"])
            content = build_campaign_export(connection, record["campaign_id"],
                created_at=datetime.fromisoformat(original["manifest"]["created_at"]), backend_commit=original["manifest"]["backend_commit"])
        if _digest(content) != record["export_sha256"]:
            raise ValueError("restored paired export differs from the immutable frozen export")
        return {**report, "freeze_id": record["freeze_id"], "export_match": True, "export_sha256": _digest(content)}
    finally:
        engine.dispose()
