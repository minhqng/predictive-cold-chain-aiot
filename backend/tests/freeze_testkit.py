"""Local freeze fixtures; generated references are not official B/D artifacts."""

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from coldguard_backend.campaign_freeze import FreezeDraft
from coldguard_backend.evidence_backup import backup_campaign
from coldguard_backend.experiment_evidence import encode_evidence
from tests.command_testkit import utcnow
from tests.test_campaign_backup import ready_campaign


def freeze_context(engine, directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    context = ready_campaign(engine)
    artifact_root = directory / "inputs"
    artifact_root.mkdir()
    model = b"SOFTWARE_SIMULATION model reference; no trained model or physical acceptance"
    policy = encode_evidence({"policy_version": "policy-software-1", "data_class": "SOFTWARE_SIMULATION",
                              "note": "fixture reference; not Member D implementation or approval"})
    artifacts = {
        "model_metadata": ("model-metadata.json", encode_evidence({"data_class": "SOFTWARE_SIMULATION", "models": [{
            "model_version": "model-software-1", "feature_version": "feature-software-1", "artifact_sha256": hashlib.sha256(model).hexdigest(),
        }]})),
        "policy_metadata": ("policy-metadata.json", encode_evidence({"data_class": "SOFTWARE_SIMULATION", "policies": [{
            "policy_version": "policy-software-1", "artifact_sha256": hashlib.sha256(policy).hexdigest(),
        }]})),
        "broker_config": ("broker.conf", b"# SOFTWARE_SIMULATION config reference\nallow_anonymous false\n"),
        "backend_config": ("backend-config.json", encode_evidence({"data_class": "SOFTWARE_SIMULATION", "profile": "dev", "credential_values": "NOT_INCLUDED"})),
        "model_reference": ("model-reference.bin", model), "policy_reference": ("policy-reference.json", policy),
    }
    references = []
    for kind, (name, content) in artifacts.items():
        (artifact_root / name).write_bytes(content)
        references.append({"name": name, "kind": kind, "sha256": hashlib.sha256(content).hexdigest()})
    backup = directory / "source-backup"
    backup_campaign(engine, context["draft"]["campaign_id"], backup, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    draft = FreezeDraft.model_validate({"freeze_id": "software-freeze-" + uuid4().hex,
        "campaign_id": context["draft"]["campaign_id"], "created_at": utcnow(), "backend_commit": "a" * 40, "artifacts": references})
    return {**context, "freeze_draft": draft, "artifact_root": artifact_root, "backup": backup, "destination": directory / "frozen"}
