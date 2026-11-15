"""Explicit SOFTWARE_SIMULATION observer fixtures; never real/official signoff."""

from pathlib import Path

from coldguard_backend.evidence_package import digest
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.incident_audit import IncidentJournal
from tests.command_testkit import utcnow


def journal_fixture(context, root: Path, *, sources=None, observations=None):
    sources = sources or {"observer.json": encode_evidence({"data_class": "SOFTWARE_SIMULATION",
        "note": "generated unit fixture, not evidence of an actual broker outage"})}
    root.mkdir(parents=True, exist_ok=True)
    for name, content in sources.items():
        (root / name).write_bytes(content)
    run = context["draft"]["runs"][0]["run"]
    observations = observations or [{"event_id": "software-observer-1", "event_type": "BROKER_DISCONNECTED",
        "observed_at": utcnow(), "run_id": run["run_id"], "device_id": run["device_id"], "source_name": "observer.json",
        "source_sha256": digest(sources["observer.json"]), "source_kind": "observer_snapshot",
        "summary": "SOFTWARE_SIMULATION unit observer fixture; not an actual outage or physical acceptance"}]
    return IncidentJournal.model_validate({"campaign_id": context["draft"]["campaign_id"],
                                           "data_class": "SOFTWARE_SIMULATION", "observations": observations})
