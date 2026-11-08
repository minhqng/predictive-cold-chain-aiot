"""Predeclared campaign membership and immutable run identities."""

import hashlib
from collections import defaultdict
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Column, DateTime, MetaData, Table, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Connection

from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import (
    Identifier, RunConflict, RunCreate, RunNotFound, create_run, experiments, get_run,
)

metadata = MetaData()
campaigns = Table(
    "campaigns", metadata,
    Column("campaign_id", Text, primary_key=True),
    Column("data_class", Text),
    Column("namespace", JSONB),
    Column("namespace_sha256", Text),
    Column("created_at", DateTime(timezone=True)),
)
campaign_runs = Table(
    "campaign_runs", metadata,
    Column("run_id", Text, primary_key=True),
    Column("campaign_id", Text),
    Column("pair_id", Text),
    Column("arm", Text),
    Column("frozen_run", JSONB),
)

VERSION_REFERENCES = (
    "hardware_config_id", "pin_map_version", "firmware_version", "backend_version",
    "schema_version", "calibration_id", "feature_version", "model_version", "policy_version",
)
PAIR_COMPARABILITY = (
    "hardware_config_id", "pin_map_version", "firmware_version", "schema_version", "calibration_id",
)
RUN_IDENTITY_FIELDS = ("run_id", "device_id", "scenario_id", "controller_id", "pair_id", "versions")
PositiveSeconds = Annotated[float, Field(gt=0, le=86400, allow_inf_nan=False)]


class CriticalWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    window_id: Identifier
    start_offset_sec: Annotated[float, Field(ge=0, le=86400, allow_inf_nan=False)]
    end_offset_sec: PositiveSeconds
    max_gap_sec: PositiveSeconds

    @model_validator(mode="after")
    def _ordered(self):
        if self.start_offset_sec >= self.end_offset_sec:
            raise ValueError("critical window must have positive duration")
        return self


class CampaignRunPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    arm: Literal["A", "B"]
    run: RunCreate
    critical_windows: Annotated[list[CriticalWindow], Field(min_length=1, max_length=100)]
    required_events: Annotated[list[Identifier], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def _predeclared_identity(self):
        if self.run.pair_id is None:
            raise ValueError("campaign runs require a pair_id")
        if self.run.controller_id != {"A": "REACTIVE", "B": "PREDICTIVE"}[self.arm]:
            raise ValueError("campaign arm must match the canonical controller_id")
        missing = [key for key in VERSION_REFERENCES if self.run.versions.get(key) is None]
        if missing:
            raise ValueError("campaign version references are required: " + ", ".join(missing))
        if type(self.run.versions["schema_version"]) is not int or self.run.versions["schema_version"] != 1:
            raise ValueError("final campaign requires supported telemetry schema_version 1")
        if len(set(self.required_events)) != len(self.required_events):
            raise ValueError("required event types must be distinct")
        if len({window.window_id for window in self.critical_windows}) != len(self.critical_windows):
            raise ValueError("critical window IDs must be distinct")
        return self


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    campaign_id: Identifier
    data_class: Literal["SOFTWARE_SIMULATION", "PHYSICAL"]
    protocol_version: Identifier
    validity_rule_reference: Identifier
    max_sample_age_sec: PositiveSeconds
    runs: Annotated[list[CampaignRunPlan], Field(min_length=2, max_length=2000)]

    @model_validator(mode="after")
    def _complete_pairs(self):
        if len({plan.run.run_id for plan in self.runs}) != len(self.runs):
            raise ValueError("campaign run IDs must be distinct")
        pairs = defaultdict(dict)
        for plan in self.runs:
            pair = pairs[plan.run.pair_id]
            if plan.arm in pair:
                raise ValueError("a pair must contain exactly one run for each arm")
            pair[plan.arm] = plan.run
        for pair in pairs.values():
            if set(pair) != {"A", "B"}:
                raise ValueError("a pair must contain both A and B arms")
            if pair["A"].scenario_id != pair["B"].scenario_id:
                raise ValueError("paired runs must have the same scenario")
            if any(pair["A"].versions[key] != pair["B"].versions[key] for key in PAIR_COMPARABILITY):
                raise ValueError("paired runs have conflicting physical version references")
        return self


class CampaignNotFound(RunNotFound):
    pass


def run_identity(run: dict) -> dict:
    return {key: run[key] for key in RUN_IDENTITY_FIELDS}


def get_campaign(connection: Connection, campaign_id: str) -> dict:
    row = connection.execute(select(campaigns).where(campaigns.c.campaign_id == campaign_id)).mappings().one_or_none()
    if row is None:
        raise CampaignNotFound(campaign_id)
    return dict(row)


def campaign_plan(campaign: dict, run_id: str) -> dict:
    for plan in campaign["namespace"]["runs"]:
        if plan["run"]["run_id"] == run_id:
            return plan
    raise RunConflict("run is not a member of this frozen campaign")


def register_campaign(connection: Connection, draft: CampaignCreate) -> dict:
    """Freeze the full roster before acquisition; retries never change membership."""
    namespace = draft.model_dump(mode="json")
    namespace["runs"].sort(key=lambda plan: plan["run"]["run_id"])
    digest = hashlib.sha256(encode_evidence(namespace)).hexdigest()
    connection.execute(select(func.pg_advisory_xact_lock(func.hashtext("campaign"), func.hashtext(draft.campaign_id))))
    old = connection.execute(select(campaigns).where(campaigns.c.campaign_id == draft.campaign_id)).mappings().one_or_none()
    if old is not None:
        if old["namespace_sha256"] != digest:
            raise RunConflict("campaign ID already has a different frozen namespace")
        return dict(old)
    # Lock in stable order to serialize cross-campaign attempts at the same run.
    for plan in sorted(draft.runs, key=lambda plan: plan.run.run_id):
        current = connection.execute(select(experiments).where(
            experiments.c.run_id == plan.run.run_id,
        ).with_for_update()).mappings().one_or_none()
        if current is None:
            create_run(connection, plan.run)
        elif run_identity(dict(current)) != run_identity(plan.run.model_dump()):
            raise RunConflict("registered run differs from the campaign identity/version references")
        elif current["status"] != "PLANNED":
            raise RunConflict("campaign namespace must be frozen before runs are armed")
        if connection.scalar(select(campaign_runs.c.campaign_id).where(campaign_runs.c.run_id == plan.run.run_id)) is not None:
            raise RunConflict("run is already associated with another campaign")
    row = connection.execute(insert(campaigns).values(
        campaign_id=draft.campaign_id, data_class=draft.data_class, namespace=namespace,
        namespace_sha256=digest, created_at=func.clock_timestamp(),
    ).returning(campaigns)).mappings().one()
    connection.execute(campaign_runs.insert(), [{
        "campaign_id": draft.campaign_id, "run_id": plan.run.run_id,
        "pair_id": plan.run.pair_id, "arm": plan.arm,
        "frozen_run": run_identity(plan.run.model_dump(mode="json")),
    } for plan in draft.runs])
    return dict(row)


def verify_membership(connection: Connection, campaign: dict, run_id: str) -> dict:
    plan = campaign_plan(campaign, run_id)
    run = get_run(connection, run_id)
    saved = connection.execute(select(campaign_runs).where(campaign_runs.c.run_id == run_id)).mappings().one_or_none()
    if saved is None or (saved["campaign_id"], saved["pair_id"], saved["arm"]) != (
        campaign["campaign_id"], plan["run"]["pair_id"], plan["arm"],
    ) or saved["frozen_run"] != run_identity(run) or saved["frozen_run"] != run_identity(plan["run"]):
        raise RunConflict("campaign run/pair/controller/version association differs from its frozen namespace")
    return run
