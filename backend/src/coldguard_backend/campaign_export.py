"""Deterministic paired campaign evidence from a single database snapshot."""

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.engine import Connection

from coldguard_backend.campaign_integrity import _raw_evidence, _raw_source_errors, campaign_integrity, run_closures
from coldguard_backend.campaign_store import get_campaign, verify_membership
from coldguard_backend.command_store import command_acks, command_attempts, command_transitions, commands
from coldguard_backend.controller_b import policy_approvals
from coldguard_backend.event_timeline import S2_SCENARIOS, s2_timeline_page
from coldguard_backend.experiment_evidence import encode_evidence, run_samples, run_timeline
from coldguard_backend.experiment_store import experiment_transitions, experiments
from coldguard_backend.physical_verification import physical_assessments
from coldguard_backend.prediction_store import prediction_inputs, predictions
from coldguard_backend.shadow_trace import shadow_decisions

QUERY_VERSION = "campaign-evidence-v1"


def _rows(connection: Connection, table, predicate) -> list[dict]:
    return [dict(row) for row in connection.execute(select(table).where(predicate).order_by(*table.primary_key.columns)).mappings()]


def complete_timeline(connection: Connection, run: dict) -> list[dict]:
    if run["scenario_id"] not in S2_SCENARIOS:
        return run_timeline(connection, run)
    result, cursor = [], None
    while True:
        page = s2_timeline_page(connection, run, limit=500, cursor=cursor)
        result.extend(page["items"])
        if not page["has_more"]:
            return result
        cursor = page["next_cursor"]


def campaign_dataset(connection: Connection, campaign_id: str) -> dict:
    """Refuse incomplete/invalid campaigns; retain raw retransmissions and traces."""
    campaign = get_campaign(connection, campaign_id)
    integrity = campaign_integrity(connection, campaign_id)
    if not integrity["freeze_ready"]:
        raise ValueError("campaign freeze requires every frozen run VALID, clear integrity and a current closure")
    namespace = campaign["namespace"]
    runs = [verify_membership(connection, campaign, plan["run"]["run_id"]) for plan in namespace["runs"]]
    run_ids = [run["run_id"] for run in runs]
    registered = _rows(connection, experiments, experiments.c.run_id.in_(run_ids))
    tables = {"experiments": registered,
              "experiment_transitions": _rows(connection, experiment_transitions, experiment_transitions.c.run_id.in_(run_ids))}
    samples, raw, traces = [], {}, []
    for run in runs:
        samples.extend(run_samples(connection, run))
        for row in _raw_evidence(connection, run):
            raw[row["id"]] = row
        traces.append({"run_id": run["run_id"], "pair_id": run["pair_id"], "controller_id": run["controller_id"],
                       "timeline": complete_timeline(connection, run)})
    tables["telemetry"] = sorted(samples, key=lambda row: row["id"])
    tables["telemetry_raw"] = [raw[key] for key in sorted(raw)]
    tables["commands"] = _rows(connection, commands, commands.c.run_id.in_(run_ids))
    tables["predictions"] = _rows(connection, predictions, predictions.c.run_id.in_(run_ids))
    command_ids = [row["command_id"] for row in tables["commands"]]
    prediction_ids = [row["prediction_id"] for row in tables["predictions"]]
    for table in (command_attempts, command_transitions, command_acks, physical_assessments, policy_approvals):
        tables[table.name] = _rows(connection, table, table.c.command_id.in_(command_ids))
    for table in (prediction_inputs, shadow_decisions):
        tables[table.name] = _rows(connection, table, table.c.prediction_id.in_(prediction_ids))
    tables["campaign_run_closures"] = _rows(connection, run_closures, run_closures.c.campaign_id == campaign_id)
    _validate_associations(runs, tables)
    _validate_required_evidence(campaign, runs, tables)
    return {"campaign": campaign, "integrity": integrity, "tables": tables,
            "pairs": [{"pair_id": pair_id, "runs": [{"run_id": plan["run"]["run_id"], "arm": plan["arm"],
                "controller_id": plan["run"]["controller_id"]} for plan in namespace["runs"] if plan["run"]["pair_id"] == pair_id]}
                for pair_id in sorted({run["pair_id"] for run in runs})], "traces": traces}


def _validate_associations(runs: list[dict], tables: dict) -> None:
    expected = {run["run_id"]: run for run in runs}
    predictions_by_id = {row["prediction_id"]: row for row in tables["predictions"]}
    samples = {row["id"]: row for row in tables["telemetry"]}
    raw = {row["id"]: row for row in tables["telemetry_raw"]}
    for source in raw.values():
        errors, _ = _raw_source_errors(source)
        if errors:
            raise ValueError("exported raw evidence has inconsistent wire/hash/projection provenance")
    for row in tables["telemetry"]:
        source = raw.get(row["raw_id"])
        if source is None or source["payload_sha256"] != row["raw_sha256"]:
            raise ValueError("normalized sample is missing matching raw provenance")
        if hashlib.sha256(source["raw_payload"].encode("utf-8")).hexdigest() != source["payload_sha256"]:
            raise ValueError("raw evidence checksum differs from its source payload")
    for prediction in predictions_by_id.values():
        run = expected[prediction["run_id"]]
        if prediction["device_id"] != run["device_id"] or any(prediction[key] != run["versions"][key] for key in ("model_version", "feature_version")):
            raise ValueError("prediction association or frozen version differs")
        inputs = [row for row in tables["prediction_inputs"] if row["prediction_id"] == prediction["prediction_id"]]
        if not inputs or any(row["telemetry_id"] not in samples or (
            samples[row["telemetry_id"]]["device_id"], samples[row["telemetry_id"]]["run_id"]
        ) != (prediction["device_id"], prediction["run_id"]) for row in inputs):
            raise ValueError("prediction inputs are missing or associated with another run")
    for command in tables["commands"]:
        run = expected[command["run_id"]]
        if any(command[key] != run[key] for key in ("device_id", "controller_id")) or command["policy_version"] != run["versions"]["policy_version"]:
            raise ValueError("command run/controller/policy association differs")
        if command["prediction_id"] is not None:
            prediction = predictions_by_id.get(command["prediction_id"])
            if prediction is None or (prediction["device_id"], prediction["run_id"]) != (command["device_id"], command["run_id"]):
                raise ValueError("command prediction provenance is unavailable for its exact run")


def _validate_required_evidence(campaign: dict, runs: list[dict], tables: dict) -> None:
    for sample in tables["telemetry"]:
        if any(sample[field] != "VALID" for field in ("thermal_quality", "environment_quality", "electrical_quality", "overall_quality")):
            raise ValueError("required campaign measurement quality is unavailable")
        if any(sample[field] is None for field in ("t1_c", "t2_c", "t3_c", "cooling_voltage_v", "cooling_current_a")):
            raise ValueError("required campaign sensor evidence is missing")
    if campaign["data_class"] != "PHYSICAL":
        return
    if any(sample["synthetic"] is True for sample in tables["telemetry"]):
        raise ValueError("physical campaign cannot freeze synthetic measurement evidence")
    approvals = {row["command_id"]: row for row in tables["policy_approvals"]}
    for run in runs:
        if run["controller_id"] != "PREDICTIVE":
            continue
        if not any(row["run_id"] == run["run_id"] for row in tables["predictions"]):
            raise ValueError("physical predictive run lacks required prediction evidence")
        for command in tables["commands"]:
            if command["run_id"] != run["run_id"]:
                continue
            if command["command_id"] not in approvals:
                raise ValueError("physical predictive command lacks signed policy approval evidence")
            if command["action_cooling"] != "OFF" and not any(
                row["command_id"] == command["command_id"] and row["stage"] == "VERIFIED"
                for row in tables["physical_assessments"]
            ):
                raise ValueError("physical command lacks final assessment evidence")


def build_campaign_export(connection: Connection, campaign_id: str, *, created_at, backend_commit: str) -> bytes:
    if created_at.utcoffset() is None or re.fullmatch(r"[0-9a-f]{40}", backend_commit) is None:
        raise ValueError("export needs an aware timestamp and full backend Git SHA")
    dataset = campaign_dataset(connection, campaign_id)
    digest = hashlib.sha256(encode_evidence(dataset)).hexdigest()
    data_class = dataset["campaign"]["data_class"]
    manifest = {"format": "coldguard-campaign-export-v1", "data_class": data_class,
                "dataset_id": "coldguard-" + data_class.lower() + "-" + digest, "dataset_sha256": digest,
                "campaign_id": campaign_id, "namespace_sha256": dataset["campaign"]["namespace_sha256"],
                "query_version": QUERY_VERSION, "query_sha256": hashlib.sha256(QUERY_VERSION.encode()).hexdigest(),
                "created_at": created_at, "backend_commit": backend_commit,
                "run_ids": sorted(row["run_id"] for row in dataset["tables"]["experiments"]),
                "pair_ids": [pair["pair_id"] for pair in dataset["pairs"]],
                "table_sha256": {name: hashlib.sha256(encode_evidence(rows)).hexdigest() for name, rows in dataset["tables"].items()},
                "physical_acceptance": "BLOCKED_EXTERNAL"}
    return encode_evidence({"manifest": manifest, "dataset": dataset})
