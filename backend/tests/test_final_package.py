"""W22 frozen-source package gates; all fixtures are SOFTWARE_SIMULATION."""

import json
from datetime import timedelta

from coldguard_backend.campaign_export import build_campaign_export
from coldguard_backend.campaign_integrity import close_run
from coldguard_backend.ingest import ingest_message
from coldguard_backend.simulator import build_event
from tests.campaign_testkit import campaign_draft, complete_run, register_fixture, snapshot_transaction
from tests.command_testkit import utcnow


def test_registered_s1_pair_can_export_complete_non_door_timelines(db_engine):
    draft = campaign_draft()
    for plan in draft["runs"]:
        plan["run"]["scenario_id"] = "S1_NORMAL_BASELINE"
        plan["required_events"] = ["SIM_RUN_START", "SIM_RUN_END"]
    context = register_fixture(db_engine, draft)
    for arm in ("A", "B"):
        run = complete_run(context, arm, events=False)
        for seq, kind in ((1, "SIM_RUN_START"), (4, "SIM_RUN_END")):
            event = build_event(device_id=run["device_id"], boot_id="software-boot-" + run["run_id"],
                                seq=seq, run_id=run["run_id"], event_type=kind, base_time=context["started"])
            ingest_message(db_engine, topic=f"coldguard/{run['device_id']}/event", payload=json.dumps(event).encode(),
                           received_at=context["started"] + timedelta(seconds=seq, milliseconds=100))
        with snapshot_transaction(db_engine) as connection:
            close_run(connection, draft["campaign_id"], run["run_id"], reason="SOFTWARE_SIMULATION baseline package audit")
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        bundle = json.loads(build_campaign_export(connection, draft["campaign_id"], created_at=utcnow(), backend_commit="a" * 40))
    assert len(bundle["dataset"]["traces"]) == 2
    assert all(len(trace["timeline"]) == 6 for trace in bundle["dataset"]["traces"])
    assert all({row["kind"] for row in trace["timeline"]} == {"telemetry", "event_receipt"} for trace in bundle["dataset"]["traces"])
