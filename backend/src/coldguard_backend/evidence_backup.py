"""Consistent PostgreSQL archives and verified restore into an empty local DB."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url

from coldguard_backend.campaign_integrity import campaign_integrity
from coldguard_backend.campaign_store import CampaignNotFound, get_campaign
from coldguard_backend.evidence_tables import fingerprint_connection
from coldguard_backend.experiment_evidence import encode_evidence


def local_database_url(value):
    url = make_url(value)
    if (url.drivername != "postgresql+psycopg" or url.host != "127.0.0.1" or url.query
        or not url.username or not url.database or url.database in {"postgres", "template0", "template1"}):
        raise ValueError("use a dedicated direct loopback PostgreSQL database, never a system database")
    return url


def _postgres_command(executable: str, url, *arguments: str) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    if url.password is not None:
        env["PGPASSWORD"] = url.password
    command = [executable, "--host", url.host, "--port", str(url.port or 5432), "--username", url.username,
               "--dbname", url.database, "--no-password", *arguments]
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if result.returncode:
        # PostgreSQL diagnostics can include credentials or paths; logs are deliberately bounded/redacted.
        raise RuntimeError(f"{Path(executable).name} failed with exit {result.returncode}; archive/restore is not verified")


def backup_campaign(engine: Engine, campaign_id: str, destination: Path, *, pg_dump: str = "pg_dump") -> dict:
    url = local_database_url(engine.url)
    if destination.exists():
        raise FileExistsError("backup destination already exists; do not overwrite evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".backup-staging-", dir=destination.parent))
    with engine.connect().execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True) as connection:
        readiness = campaign_integrity(connection, campaign_id)
        if not readiness["backup_ready"]:
            raise ValueError("campaign backup readiness failed: incomplete evidence inventory or current closures")
        fingerprints = fingerprint_connection(connection)
        exported_snapshot = connection.scalar(text("SELECT pg_export_snapshot()"))
        archive = stage / "database.dump"
        _postgres_command(pg_dump, url, "--format=custom", "--no-owner", "--no-acl",
                          "--snapshot=" + exported_snapshot, "--file=" + str(archive))
    receipt = {"format": "coldguard-backup-v1", "campaign_id": campaign_id,
               "data_class": readiness["data_class"], "namespace_sha256": readiness["namespace_sha256"],
               "archive": "database.dump", "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
               "source_fingerprints": fingerprints, "restore_verified": False,
               "integrity_clear": readiness["integrity_clear"], "freeze_ready": readiness["freeze_ready"],
               "run_status_counts": readiness["run_status_counts"], "known_generated_input": readiness["known_generated_input"],
               "run_issues": {row["run_id"]: row["issues"] for row in readiness["runs"]},
               "snapshot_consistency": "pg_export_snapshot", "physical_acceptance": "BLOCKED_EXTERNAL"}
    (stage / "receipt.json").write_bytes(encode_evidence(receipt))
    if destination.exists():
        raise FileExistsError("backup destination appeared during generation")
    stage.rename(destination)
    return receipt


def read_verified_backup(directory: Path) -> tuple[dict, bytes, bytes]:
    receipt_bytes = (directory / "receipt.json").read_bytes()
    archive_bytes = (directory / "database.dump").read_bytes()
    receipt = json.loads(receipt_bytes)
    if (receipt.get("format") != "coldguard-backup-v1" or receipt.get("archive") != "database.dump"
        or hashlib.sha256(archive_bytes).hexdigest() != receipt.get("archive_sha256")):
        raise ValueError("backup checksum or format differs")
    return receipt, receipt_bytes, archive_bytes


def verify_backup(directory: Path) -> dict:
    receipt, _, _ = read_verified_backup(directory)
    return receipt


def restore_backup(directory: Path, restore_url, *, pg_restore: str = "pg_restore") -> dict:
    receipt, _, archive_bytes = read_verified_backup(directory)
    url = local_database_url(restore_url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.begin() as connection:
            if inspect(connection).get_table_names(schema="public"):
                raise ValueError("restore target must have no application tables")
            if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='timescaledb')")):
                connection.execute(text("SELECT timescaledb_pre_restore()"))
        # pg_restore consumes exactly the verified bytes, not a raced second read of the source.
        with tempfile.TemporaryDirectory(prefix="coldguard-verified-restore-") as temporary:
            archive = Path(temporary) / "database.dump"
            archive.write_bytes(archive_bytes)
            _postgres_command(pg_restore, url, "--exit-on-error", "--no-owner", "--no-acl", str(archive))
        with engine.begin() as connection:
            connection.execute(text("SELECT timescaledb_post_restore()"))
        with engine.connect().execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True) as connection:
            restored = fingerprint_connection(connection)
            try:
                campaign = get_campaign(connection, receipt["campaign_id"])
            except (CampaignNotFound, KeyError) as exc:
                raise ValueError("backup receipt does not identify the restored campaign") from exc
            if any(receipt.get(key) != campaign[key] for key in ("campaign_id", "namespace_sha256", "data_class")):
                raise ValueError("backup receipt provenance differs from the restored campaign")
            inventory = campaign_integrity(connection, campaign["campaign_id"])
            for key in ("integrity_clear", "freeze_ready", "run_status_counts", "known_generated_input"):
                if key in receipt and receipt[key] != inventory[key]:
                    raise ValueError("backup receipt assessment differs from the restored campaign")
        if restored != receipt["source_fingerprints"]:
            raise ValueError("restored evidence differs from the archive's consistent source snapshot")
        return {"match": True, "archive_sha256": receipt["archive_sha256"], "restored": restored,
                "data_class": campaign["data_class"], "known_generated_input": inventory["known_generated_input"],
                "physical_acceptance": "BLOCKED_EXTERNAL"}
    finally:
        engine.dispose()
