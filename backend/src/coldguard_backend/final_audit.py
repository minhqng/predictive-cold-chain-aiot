"""Pure final audit of frozen JSON evidence; no DB, imputation or validity writes."""

import json
from collections import Counter, defaultdict
from datetime import datetime

from coldguard_backend.campaign_export import QUERY_VERSION, _validate_associations, _validate_required_evidence
from coldguard_backend.campaign_integrity import _observed_schema_errors, _raw_source_errors, critical_window_report
from coldguard_backend.campaign_store import CampaignCreate, VERSION_REFERENCES, run_identity
from coldguard_backend.command_publisher import command_from_row
from coldguard_backend.command_store import command_payload_sha256
from coldguard_backend.dataset_export import sample_integrity
from coldguard_backend.evidence_package import digest
from coldguard_backend.evidence_tables import evidence_keys
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import ALLOWED_TRANSITIONS
from coldguard_backend.normalized_store import classify_replay, map_to_row
from coldguard_backend.raw_store import RECEIVED_OBSERVED, RECEIVED_VALID
from coldguard_backend.reconciliation import validate_winner
from coldguard_backend.timing import compute_timing_metrics
from coldguard_backend.validation import validate_telemetry_payload

EXPORT_TABLES = (
    "experiments", "experiment_transitions", "telemetry", "telemetry_raw", "commands",
    "predictions", "command_attempts", "command_transitions", "command_acks",
    "physical_assessments", "policy_approvals", "prediction_inputs", "shadow_decisions", "campaign_run_closures",
)


def require(condition, message: str) -> None:
    if not condition:
        raise ValueError(message)


def document(content: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "JSON evidence has duplicate object keys")
            result[key] = value
        return result
    def nonfinite(_value):
        raise ValueError("JSON evidence cannot contain nonfinite numbers")
    value = json.loads(content, object_pairs_hook=unique, parse_constant=nonfinite)
    require(isinstance(value, dict), "JSON evidence must be an object")
    return value


def stamp(value, *, optional=False):
    if value is None and optional:
        return None
    require(isinstance(value, (str, datetime)), "evidence time must be an aware timestamp")
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    require(result.utcoffset() is not None, "evidence time must be timezone-aware")
    return result


def row_index(rows: list[dict], keys: tuple[str, ...]) -> dict:
    require(isinstance(rows, list), "evidence table must be a list")
    result = {}
    for row in rows:
        require(isinstance(row, dict), "evidence row must be an object")
        identity = tuple(row[key] for key in keys)
        require(all(type(value) in (str, int) and value != "" for value in identity), "evidence identity is missing or invalid")
        require(identity not in result, "duplicate evidence table identity")
        result[identity] = row
    return result


def _scoped_raw(run: dict, samples: list[dict], raw: list[dict]) -> list[dict]:
    identities = {(row["device_id"], row["boot_id"], row["seq"]) for row in samples}
    sources = {row["raw_id"] for row in samples}
    return [row for row in raw if row["run_id"] == run["run_id"] or row["id"] in sources
            or (row["device_id"], row["boot_id"], row["seq"]) in identities
            or (row["run_id"] is None and row["topic"] in {
                f"coldguard/{run['device_id']}/{family}" for family in ("telemetry", "event", "state", "health")
            } and run["started_at"] <= stamp(row["backend_received_at"]) <= run["ended_at"])]


def _run_audit(campaign, plan, run, samples, raw, report, closures):
    converted = [{**row, "event_time": stamp(row["event_time"], optional=True),
                  "backend_received_at": stamp(row["backend_received_at"])} for row in samples]
    winners = {(row["device_id"], row["boot_id"], row["seq"]): row for row in converted}
    deliveries, events, variants = Counter(), Counter(), defaultdict(set)
    for source in raw:
        converted_source = {**source, "captured_at": stamp(source["captured_at"], optional=True),
                            "backend_received_at": stamp(source["backend_received_at"])}
        errors, wire = _raw_source_errors(converted_source)
        require(not errors, "raw wire/hash/cache or extracted provenance differs")
        require(source["ingest_status"] in {RECEIVED_VALID, RECEIVED_OBSERVED}, "frozen raw evidence has an invalid record")
        require(source["run_id"] in {None, run["run_id"]} and source["device_id"] in {None, run["device_id"]}, "raw run/device association differs")
        require(all(key not in wire or wire[key] == run[key] for key in ("pair_id", "controller_id")), "raw pair/controller association differs")
        require(all(key not in wire or wire[key] == run["versions"][key] for key in VERSION_REFERENCES), "wire version contradicts frozen run")
        if campaign["data_class"] == "PHYSICAL":
            require(wire.get("synthetic") is not True and wire.get("replay") is not True and wire.get("is_replay") is not True,
                    "physical frozen evidence contains generated or replay input")
        if source["ingest_status"] == RECEIVED_VALID:
            key = (source["device_id"], source["boot_id"], source["seq"])
            winner = winners.get(key)
            validated, _ = validate_telemetry_payload(wire)
            require(winner is not None and validated is not None, "valid raw telemetry lacks its normalized winner")
            incoming = map_to_row(validated, raw_id=source["id"], received_at=converted_source["backend_received_at"])
            require(classify_replay({**winner, "time": winner["event_time"]}, incoming) == "exact_duplicate", "conflicting raw duplicate identity")
            deliveries[(source["boot_id"], source["seq"])] += 1
        else:
            event = source["topic"] == f"coldguard/{run['device_id']}/event"
            observed_errors, _ = _observed_schema_errors(wire, event=event)
            require(not observed_errors, "invalid observed schema/event record")
            if event:
                events[wire["event_type"]] += 1
                variants[wire["event_id"]].add(digest(encode_evidence(wire)))
    require(all(len(values) == 1 for values in variants.values()), "conflicting event identity")
    duplicate_ids = [{"boot_id": boot, "seq": seq, "raw_deliveries": count}
                     for (boot, seq), count in sorted(deliveries.items()) if count > 1]
    basic = sample_integrity(run, converted, duplicate_identities=duplicate_ids)
    critical = critical_window_report(converted, run["started_at"], plan["critical_windows"])
    require(samples and not basic["clockless_count"] and not basic["version_mismatches"]
            and not basic["mixed_version_fields"] and not basic["event_time_outside_run_unverified"], "sample acquisition/version integrity is incomplete")
    require(not any(row["missing"] for row in critical) and not set(plan["required_events"]) - events.keys(), "critical window or required event is missing")
    expected = {"campaign_id": campaign["campaign_id"], "namespace_sha256": campaign["namespace_sha256"],
                "run_id": run["run_id"], "pair_id": run["pair_id"], "controller_id": run["controller_id"],
                "run_status": "VALID", "data_class": campaign["data_class"], "assessment_recipe": "campaign-integrity-v3",
                "raw_count": len(raw), "normalized_count": len(samples), "event_counts": dict(events),
                "raw_telemetry_count": sum(row["topic"].endswith("/telemetry") for row in raw),
                "raw_status_counts": dict(Counter(row["ingest_status"] for row in raw)),
                "source_sha256": digest(encode_evidence({"raw": raw, "samples": samples})),
                "integrity": json.loads(encode_evidence(basic)), "critical_windows": json.loads(encode_evidence(critical)),
                "assessment": "SOFTWARE_INTEGRITY_CLEAR", "issues": [], "missing_events": [],
                "global_event_conflicts": [], "message_error_raw_ids": [], "schema_mismatch_raw_ids": [], "observed_message_errors": [],
                "validity_authority": campaign["namespace"]["validity_rule_reference"],
                "automatic_validity_approval": False, "physical_acceptance": "BLOCKED_EXTERNAL"}
    require(all(report[key] == value for key, value in expected.items()), "qualified source report differs from frozen evidence")
    report_sha = digest(encode_evidence(report))
    require(any(row["run_id"] == run["run_id"] and row["report_sha256"] == report_sha for row in closures), "current qualified run closure is missing")
    return {"run_id": run["run_id"], "pair_id": run["pair_id"], "controller_id": run["controller_id"],
            "versions": run["versions"], "recorded_run_status": run["status"], "source_sha256": expected["source_sha256"],
            "current_report_sha256": report_sha, "raw_count": len(raw), "normalized_count": len(samples),
            "raw_duplicate_identities": duplicate_ids, "sequence_gaps": basic["sequence_gaps"],
            "unattributed_raw_ids": [row["id"] for row in raw if row["run_id"] is None], "invalid_run_records": []}


def _child_audit(runs, tables):
    _validate_associations(runs, tables)
    commands = {row["command_id"]: row for row in tables["commands"]}
    predictions = {row["prediction_id"]: row for row in tables["predictions"]}
    samples = {row["id"]: row for row in tables["telemetry"]}
    expected = {run["run_id"]: run for run in runs}
    for name in ("command_attempts", "command_transitions", "command_acks", "physical_assessments", "policy_approvals"):
        require(all(row["command_id"] in commands for row in tables[name]), "orphan command evidence reference")
    for name in ("prediction_inputs", "shadow_decisions"):
        require(all(row["prediction_id"] in predictions for row in tables[name]), "orphan prediction evidence reference")
    for row in commands.values():
        parsed = {**row, "created_at": stamp(row["created_at"]), "expires_at": stamp(row["expires_at"])}
        require(command_payload_sha256(command_from_row(parsed)) == row["payload_sha256"], "command envelope checksum differs")
    for row in tables["command_attempts"]:
        require(row["payload_sha256"] == commands[row["command_id"]]["payload_sha256"], "publish attempt envelope checksum differs")
    row_index(tables["command_attempts"], ("command_id", "attempt_no"))
    for row in tables["command_acks"]:
        require(digest(row["raw_payload"].encode("utf-8")) == row["payload_sha256"], "ACK wire checksum differs")
        if row["validity"] == "VALID":
            require(row["topic_device_id"] == row["payload_device_id"] == commands[row["command_id"]]["device_id"], "valid ACK device association differs")
    for row in predictions.values():
        inputs = [item for item in tables["prediction_inputs"] if item["prediction_id"] == row["prediction_id"]]
        require(sorted(item["ordinal"] for item in inputs) == list(range(len(inputs)))
                and len({item["telemetry_id"] for item in inputs}) == len(inputs), "prediction input identities/order differ")
        require(all(stamp(row["input_window_start"]) <= stamp(samples[item["telemetry_id"]]["backend_received_at"]) <= stamp(row["input_window_end"])
                    for item in inputs), "prediction input receipt window differs")
    for row in tables["shadow_decisions"]:
        run = expected[predictions[row["prediction_id"]]["run_id"]]
        require(row["policy_version"] == run["versions"]["policy_version"], "shadow policy version differs")
    row_index(tables["shadow_decisions"], ("prediction_id",))
    for row in tables["policy_approvals"]:
        command = commands[row["command_id"]]
        require(row["policy_version"] == command["policy_version"] and row["command_sha256"] == command["payload_sha256"]
                and digest(encode_evidence(row["model_spec"])) == row["model_spec_sha256"], "recorded policy approval provenance differs")
    for row in tables["physical_assessments"]:
        claim, command = row["claim"], commands[row["command_id"]]
        require(digest(encode_evidence(claim)) == row["claim_sha256"] and all(claim[key] == command[key] for key in ("command_id", "device_id", "run_id"))
                and claim["assessment_id"] == row["assessment_id"] and claim["stage"] == row["stage"], "recorded assessment provenance differs")
        require(len(claim["telemetry_ids"]) == len(claim["raw_sha256"]) and len(set(claim["telemetry_ids"])) == len(claim["telemetry_ids"]), "assessment evidence identities differ")
        for identity, checksum in zip(claim["telemetry_ids"], claim["raw_sha256"], strict=True):
            sample = samples.get(identity)
            require(sample is not None and (sample["device_id"], sample["run_id"], sample["raw_sha256"]) ==
                    (command["device_id"], command["run_id"], checksum), "assessment measurement reference differs")


def _audit(bundle: dict) -> dict:
    manifest, dataset = bundle["manifest"], bundle["dataset"]
    campaign, tables, integrity = dataset["campaign"], dataset["tables"], dataset["integrity"]
    namespace = campaign["namespace"]
    validated = CampaignCreate.model_validate_json(encode_evidence(namespace))
    require(validated.model_dump(mode="json") == namespace, "namespace normalization would change frozen identities")
    checksum = digest(encode_evidence(dataset))
    require(manifest["format"] == "coldguard-campaign-export-v1" and manifest["dataset_sha256"] == checksum
            and manifest["dataset_id"] == "coldguard-" + campaign["data_class"].lower() + "-" + checksum, "frozen dataset checksum/identity differs")
    require(manifest["query_version"] == QUERY_VERSION and manifest["query_sha256"] == digest(QUERY_VERSION.encode()), "unsupported export query provenance")
    require(digest(encode_evidence(namespace)) == campaign["namespace_sha256"], "frozen namespace checksum differs")
    for key in ("campaign_id", "data_class", "namespace_sha256"):
        require(manifest[key] == campaign[key] == integrity[key], "campaign/export/integrity identity differs")
    require(namespace["campaign_id"] == campaign["campaign_id"] and namespace["data_class"] == campaign["data_class"], "namespace campaign identity differs")
    require(manifest["physical_acceptance"] == integrity["physical_acceptance"] == "BLOCKED_EXTERNAL", "frozen source cannot grant physical acceptance")
    stamp(manifest["created_at"])
    require(set(tables) == set(manifest["table_sha256"]) == set(EXPORT_TABLES), "frozen evidence table inventory differs")
    keys = evidence_keys("0014")
    for name, rows in tables.items():
        row_index(rows, tuple(part.strip() for part in keys[name].split(",")))
        require(digest(encode_evidence(rows)) == manifest["table_sha256"][name], "evidence table checksum differs")
    row_index(tables["telemetry"], ("device_id", "boot_id", "seq"))
    row_index(tables["telemetry"], ("raw_id",))
    runs = sorted(tables["experiments"], key=lambda row: row["run_id"])
    run_ids = [plan["run"]["run_id"] for plan in namespace["runs"]]
    require(sorted(run_ids) == [run["run_id"] for run in runs] == manifest["run_ids"], "frozen run count/roster differs")
    require(integrity["run_count"] == len(runs) and integrity["run_status_counts"] == {"VALID": len(runs)}
            and all(integrity[key] is True for key in ("backup_ready", "integrity_clear", "freeze_ready"))
            and integrity["missing_current_closures"] == [], "source is not qualified for final frozen input")
    pairs = [{"pair_id": pair, "runs": [{"run_id": plan["run"]["run_id"], "arm": plan["arm"], "controller_id": plan["run"]["controller_id"]}
              for plan in namespace["runs"] if plan["run"]["pair_id"] == pair]} for pair in sorted({run["pair_id"] for run in runs})]
    require(dataset["pairs"] == pairs and manifest["pair_ids"] == [pair["pair_id"] for pair in pairs], "frozen pair/arm roster differs")
    reports = {key[0]: value for key, value in row_index(integrity["runs"], ("run_id",)).items()}
    require(set(reports) == set(run_ids), "source assessment roster differs")
    closures = tables["campaign_run_closures"]
    for row in closures:
        checksum = digest(encode_evidence(row["report"]))
        require(row["campaign_id"] == campaign["campaign_id"] and row["run_id"] in run_ids
                and row["report"]["run_id"] == row["run_id"] and row["report"]["campaign_id"] == row["campaign_id"]
                and checksum == row["report_sha256"] and row["closure_id"] == "campaign-close-" + checksum
                and isinstance(row["reason"], str) and row["reason"].strip(), "immutable closure report identity/checksum differs")
    raw_by_id = {row["id"]: row for row in tables["telemetry_raw"]}
    require(all(row["run_id"] in run_ids for row in tables["telemetry"]), "normalized sample is outside frozen run scope")
    for row in tables["telemetry"]:
        source = raw_by_id.get(row["raw_id"])
        require(source is not None, "normalized sample lacks raw source")
        norm = {**row, "time": stamp(row["event_time"], optional=True)}
        parsed_source = {**source, "backend_received_at": stamp(source["backend_received_at"])}
        require(not validate_winner(norm, parsed_source) and row["raw_sha256"] == source["payload_sha256"]
                and row["raw_status"] == source["ingest_status"] and row["backend_received_at"] == source["backend_received_at"], "raw-normalized content/provenance differs")
        wire = json.loads(source["raw_payload"])
        replay = wire.get("replay") is True or wire.get("is_replay") is True
        timing = compute_timing_metrics(stamp(row["backend_received_at"]), norm["time"], clock_sync_verified=False,
                                       serial_source=row["serial_source"], is_replay=replay).to_dict()
        require(row["synthetic"] == wire.get("synthetic") and row["is_replay"] is replay
                and row["timing"] == json.loads(encode_evidence(timing)), "derived sample origin/timing differs")
        if campaign["data_class"] == "SOFTWARE_SIMULATION":
            require(row["synthetic"] is True, "unlabeled software sample")
    details, used_raw = [], set()
    parsed_runs = []
    for run in runs:
        plan = next(plan for plan in namespace["runs"] if plan["run"]["run_id"] == run["run_id"])
        require(run_identity(run) == run_identity(plan["run"]) and run["status"] == "VALID", "run/pair/controller/version or recorded validity differs")
        parsed = {**run, "started_at": stamp(run["started_at"]), "ended_at": stamp(run["ended_at"])}
        require(parsed["started_at"] <= parsed["ended_at"], "run acquisition window is inverted")
        history = sorted((row for row in tables["experiment_transitions"] if row["run_id"] == run["run_id"]), key=lambda row: row["id"])
        require(history and history[0]["from_status"] is None and history[0]["to_status"] == "PLANNED", "initial lifecycle record is missing")
        status = "PLANNED"
        for row in history[1:]:
            require(row["from_status"] == status and row["to_status"] in ALLOWED_TRANSITIONS.get(status, ())
                    and (row["to_status"] != "VALID" or isinstance(row["reason"], str) and row["reason"].strip()), "invalid recorded lifecycle chain")
            status = row["to_status"]
        require(status == run["status"], "run status lacks matching lifecycle evidence")
        samples = sorted((row for row in tables["telemetry"] if row["run_id"] == run["run_id"]), key=lambda row: (stamp(row["backend_received_at"]), row["id"]))
        require(all(row["device_id"] == run["device_id"] for row in samples), "sample device association differs")
        raw = sorted(_scoped_raw(parsed, samples, tables["telemetry_raw"]), key=lambda row: row["id"])
        used_raw.update(row["id"] for row in raw)
        details.append(_run_audit(campaign, plan, parsed, samples, raw, reports[run["run_id"]], closures))
        parsed_runs.append(parsed)
    require(used_raw == set(raw_by_id) and all(row["run_id"] in run_ids for row in tables["experiment_transitions"]), "unscoped raw or lifecycle evidence")
    _child_audit(parsed_runs, {**tables, "telemetry_raw": [{**row, "captured_at": stamp(row["captured_at"], optional=True)} for row in tables["telemetry_raw"]]})
    _validate_required_evidence(campaign, runs, tables)
    traces = row_index(dataset["traces"], ("run_id",))
    require({key[0] for key in traces} == set(run_ids), "paired trace roster differs")
    for (run_id,), trace in traces.items():
        run = next(run for run in runs if run["run_id"] == run_id)
        require(trace["pair_id"] == run["pair_id"] and trace["controller_id"] == run["controller_id"], "paired trace association differs")
    return {"format": "coldguard-final-integrity-audit-v1", "assessment": "FROZEN_INPUT_INTEGRITY_CLEAR",
            "campaign_id": campaign["campaign_id"], "dataset_id": manifest["dataset_id"], "data_class": campaign["data_class"],
            "run_count": len(runs), "pair_count": len(pairs), "runs": details,
            "table_sha256": manifest["table_sha256"], "normalized_duplicate_identities": [], "invalid_run_records": [],
            "automatic_validity_approval": False, "statistics": "NOT_COMPUTED", "physical_acceptance": "BLOCKED_EXTERNAL"}


def audit_campaign_export(content: bytes) -> dict:
    """Fail closed on structural/semantic defects, even in a newly rehashed candidate."""
    try:
        return _audit(document(content))
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("malformed frozen campaign evidence") from error
