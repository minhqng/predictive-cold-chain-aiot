"""Read-only incident reconstruction; observer reports never grant physical acceptance."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine

from coldguard_backend.campaign_freeze import Digest, FileName
from coldguard_backend.campaign_integrity import _raw_evidence, campaign_integrity
from coldguard_backend.campaign_store import get_campaign, verify_membership
from coldguard_backend.command_store import command_acks, command_attempts, command_transitions, commands
from coldguard_backend.evidence_package import digest, publish_package, read_verified_package
from coldguard_backend.evidence_paths import portable_component
from coldguard_backend.evidence_tables import fingerprint_connection
from coldguard_backend.experiment_evidence import encode_evidence, run_timeline
from coldguard_backend.experiment_store import DeviceIdentifier, Identifier, Reason

FORMAT = "coldguard-incident-package-v1"
EventType = Literal["MQTT_CONNECT_DENIED", "MQTT_PUBLISH_DENIED", "MQTT_PUBLISH_ACCEPTED", "BROKER_DISCONNECTED",
                    "BROKER_RECONNECTED", "BACKEND_STARTED", "BACKEND_RESTARTED", "DATABASE_UNAVAILABLE", "COMMAND_DISPATCH_BLOCKED",
                    "DUPLICATE_REORDER_OBSERVED", "REPLAY_IGNORED"]


class IncidentObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event_id: Identifier
    event_type: EventType
    observed_at: AwareDatetime
    run_id: Identifier | None = None
    device_id: DeviceIdentifier | None = None
    source_name: FileName
    source_sha256: Digest
    source_kind: Literal["protocol_receipt", "broker_log", "backend_log", "observer_snapshot"]
    summary: Reason
    raw_ids: list[Annotated[int, Field(gt=0)]] = Field(default_factory=list, max_length=1000)
    command_ids: list[Identifier] = Field(default_factory=list, max_length=1000)


class IncidentJournal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format: Literal["coldguard-incident-journal-v1"] = "coldguard-incident-journal-v1"
    campaign_id: Identifier
    data_class: Literal["SOFTWARE_SIMULATION", "PHYSICAL"]
    observations: Annotated[list[IncidentObservation], Field(min_length=1, max_length=2000)]

    @model_validator(mode="after")
    def _identities(self):
        if len({row.event_id for row in self.observations}) != len(self.observations):
            raise ValueError("incident event IDs must be distinct")
        sources = {}
        for row in self.observations:
            if row.source_name in sources and sources[row.source_name] != row.source_sha256:
                raise ValueError("one source name cannot have conflicting checksums")
            sources[row.source_name] = row.source_sha256
        if len(sources) > 100:
            raise ValueError("incident journal exceeds the bounded source-file count")
        return self


def journal_sources(root: Path, journal: IncidentJournal) -> dict[str, bytes]:
    result = {}
    for row in journal.observations:
        portable_component(row.source_name)
        if row.source_name in result:
            continue
        path = root / row.source_name
        if path.is_symlink() or path.resolve().parent != root.resolve() or not path.is_file():
            raise ValueError("incident source must be a direct regular file in the evidence root")
        content = path.read_bytes()
        if len(content) > 16 * 1024 * 1024 or sum(map(len, result.values())) + len(content) > 64 * 1024 * 1024:
            raise ValueError("incident source artifacts exceed the bounded byte budget")
        if digest(content) != row.source_sha256:
            raise ValueError("incident source checksum differs: " + row.source_name)
        result[row.source_name] = content
    return result


def build_incident_audit(connection: Connection, journal: IncidentJournal, *, created_at: datetime, backend_commit: str) -> bytes:
    if connection.get_isolation_level() not in {"REPEATABLE READ", "SERIALIZABLE"}:
        raise ValueError("incident audit requires a single repeatable snapshot")
    if (not isinstance(created_at, datetime) or created_at.utcoffset() is None or created_at > datetime.now(timezone.utc)
        or not isinstance(backend_commit, str) or re.fullmatch(r"[0-9a-f]{40}", backend_commit) is None):
        raise ValueError("incident audit requires an aware nonfuture time and full backend SHA")
    if any(row.observed_at > created_at for row in journal.observations):
        raise ValueError("incident observation cannot occur after the audit snapshot time")
    campaign = get_campaign(connection, journal.campaign_id)
    if campaign["data_class"] != journal.data_class:
        raise ValueError("incident journal data class differs from its campaign")
    runs = {plan["run"]["run_id"]: verify_membership(connection, campaign, plan["run"]["run_id"])
            for plan in campaign["namespace"]["runs"]}
    raw = {run_id: _raw_evidence(connection, run) for run_id, run in runs.items()}
    command_rows = [dict(row) for row in connection.execute(select(commands).where(commands.c.run_id.in_(list(runs))).order_by(commands.c.command_id)).mappings()]
    for command in command_rows:
        if command["device_id"] != runs[command["run_id"]]["device_id"]:
            raise ValueError("incident command has conflicting run/device provenance")
    for observation in journal.observations:
        selected = [observation.run_id] if observation.run_id is not None else list(runs)
        if any(run_id not in runs for run_id in selected):
            raise ValueError("incident observation is outside the campaign run scope")
        if observation.device_id is not None and any(runs[run_id]["device_id"] != observation.device_id for run_id in selected):
            raise ValueError("incident observation has conflicting device scope")
        scoped_raw_ids = {row["id"] for run_id in selected for row in raw[run_id]}
        scoped_command_ids = {row["command_id"] for row in command_rows if row["run_id"] in selected}
        if not set(observation.raw_ids) <= scoped_raw_ids or not set(observation.command_ids) <= scoped_command_ids:
            raise ValueError("incident source references are missing or outside its exact run scope")
    campaign_command_ids = [row["command_id"] for row in command_rows]
    command_evidence = {"commands": command_rows}
    for table in (command_attempts, command_transitions, command_acks):
        command_evidence[table.name] = [dict(row) for row in connection.execute(
            select(table).where(table.c.command_id.in_(campaign_command_ids)).order_by(*table.primary_key.columns)
        ).mappings()]
    journal_document = journal.model_dump()
    journal_document["observations"].sort(key=lambda row: (row["observed_at"], row["event_id"]))
    return encode_evidence({"format": "coldguard-incident-audit-v1", "campaign_id": journal.campaign_id,
        "data_class": journal.data_class, "created_at": created_at, "backend_commit": backend_commit,
        "snapshot_fingerprints": fingerprint_connection(connection), "integrity": campaign_integrity(connection, journal.campaign_id),
        "runs": [{"run_id": run_id, "device_id": run["device_id"], "raw_receipts": raw[run_id], "timeline": run_timeline(connection, run)}
                 for run_id, run in sorted(runs.items())], "command_evidence": command_evidence, "journal": journal_document,
        "observation_status": "RECORDED_NOT_INDEPENDENTLY_ACCEPTED", "observer_clock_sync_verified": False,
        "automatic_validity_approval": False, "physical_acceptance": "BLOCKED_EXTERNAL"})


def create_incident_package(engine: Engine, journal: IncidentJournal, *, artifact_root: Path, destination: Path,
                            created_at: datetime, backend_commit: str) -> dict:
    sources = journal_sources(artifact_root, journal)
    with engine.connect().execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True) as connection:
        content = build_incident_audit(connection, journal, created_at=created_at, backend_commit=backend_commit)
    return publish_package(destination, {"incident-audit.json": content, **{"sources/" + name: data for name, data in sources.items()}},
        format=FORMAT, metadata={"campaign_id": journal.campaign_id, "data_class": journal.data_class,
                                 "audit_sha256": digest(content), "physical_acceptance": "BLOCKED_EXTERNAL"})


def read_verified_incident_package(directory: Path, *, expected_manifest_sha256: str) -> tuple[dict, dict[str, bytes]]:
    manifest, files = read_verified_package(directory, expected_manifest_sha256=expected_manifest_sha256, format=FORMAT)
    content = files["incident-audit.json"]
    audit = json.loads(content)
    if digest(content) != manifest["audit_sha256"] or any(audit[key] != manifest[key] for key in ("campaign_id", "data_class", "physical_acceptance")):
        raise ValueError("incident audit identity differs from its anchored manifest")
    journal = IncidentJournal.model_validate_json(encode_evidence(audit["journal"]))
    if journal.campaign_id != audit["campaign_id"] or journal.data_class != audit["data_class"]:
        raise ValueError("incident journal identity differs from the audit")
    for row in journal.observations:
        content = files.get("sources/" + row.source_name)
        if content is None or digest(content) != row.source_sha256:
            raise ValueError("incident source checksum differs from the anchored journal")
    return manifest, files


def verify_incident_package(directory: Path, *, expected_manifest_sha256: str) -> dict:
    manifest, _ = read_verified_incident_package(directory, expected_manifest_sha256=expected_manifest_sha256)
    return manifest
