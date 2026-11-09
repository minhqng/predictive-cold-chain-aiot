"""Independent physical verification authority, separate from MQTT verdicts."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Column, DateTime, MetaData, Table, Text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from coldguard_backend import command_store as cs
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import DeviceIdentifier, Identifier
from coldguard_backend.measurement_integrity import live_measurement_errors, measurement_rows
from coldguard_backend.prediction_store import Digest, InputId

physical_assessments = Table(
    "physical_assessments", MetaData(),
    Column("assessment_id", Text, primary_key=True),
    Column("command_id", Text),
    Column("authority_id", Text),
    Column("stage", Text),
    Column("assessed_at", DateTime(timezone=True)),
    Column("claim", JSONB),
    Column("claim_sha256", Text),
    Column("signature_sha256", Text),
)

_ALLOWED_PHYSICAL = {
    cs.ACK_ACCEPTED: {cs.EXECUTED, cs.FAILED_VERIFICATION},
    cs.EXECUTED: {cs.ELECTRICAL_VERIFIED, cs.FAILED_VERIFICATION},
    cs.ELECTRICAL_VERIFIED: {cs.THERMAL_VERIFIED, cs.FAILED_VERIFICATION},
    cs.THERMAL_VERIFIED: {cs.VERIFIED, cs.FAILED_VERIFICATION},
}


class PhysicalEvidenceDenied(PermissionError):
    pass


class PhysicalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    assessment_id: Identifier
    authority_id: Identifier
    command_id: Identifier
    device_id: DeviceIdentifier
    run_id: Identifier
    origin: Literal["PHYSICAL", "SOFTWARE_SIMULATION"]
    stage: Literal["EXECUTED", "ELECTRICAL_VERIFIED", "THERMAL_VERIFIED", "VERIFIED", "FAILED_VERIFICATION"]
    reason_code: Identifier
    calibration_id: Identifier
    operating_envelope_id: Identifier
    window_start: AwareDatetime
    window_end: AwareDatetime
    assessed_at: AwareDatetime
    telemetry_ids: Annotated[list[InputId], Field(max_length=1000)]
    raw_sha256: Annotated[list[Digest], Field(max_length=1000)]

    @model_validator(mode="after")
    def _evidence_shape(self):
        if not self.window_start <= self.window_end <= self.assessed_at:
            raise ValueError("assessment window must end before assessment")
        if len(self.telemetry_ids) != len(set(self.telemetry_ids)) or len(self.telemetry_ids) != len(self.raw_sha256):
            raise ValueError("assessment must pair distinct telemetry IDs with their raw digests")
        if not self.telemetry_ids and self.stage != cs.FAILED_VERIFICATION:
            raise ValueError("positive physical assessment requires measurements")
        return self


class PhysicalAuthority:
    """Out-of-band trust for a specific assessor and commissioned envelope."""

    def __init__(self, authority_id: str, key: bytes, envelopes: frozenset[str]) -> None:
        if not authority_id.strip() or len(key) < 32 or not envelopes:
            raise ValueError("physical authority and commissioned envelopes must be provisioned")
        self._authority_id = authority_id
        self._key = key
        self._envelopes = envelopes

    def authenticate(self, claim: PhysicalClaim, signature: str | None) -> bytes:
        if (
            claim.origin != "PHYSICAL" or claim.authority_id != self._authority_id
            or claim.operating_envelope_id not in self._envelopes
            or not isinstance(signature, str) or len(signature) != 64
        ):
            raise PhysicalEvidenceDenied("trusted physical assessment required")
        try:
            provided = bytes.fromhex(signature)
        except ValueError as exc:
            raise PhysicalEvidenceDenied("physical assessment signature invalid") from exc
        expected = hmac.digest(self._key, encode_evidence(claim.model_dump()), "sha256")
        if not hmac.compare_digest(expected, provided):
            raise PhysicalEvidenceDenied("physical assessment signature invalid")
        return provided


def _check_measurements(
    connection: Connection, claim: PhysicalClaim, *, command: dict | None = None, boot_id: str | None = None,
) -> None:
    evidence = measurement_rows(connection, claim.telemetry_ids, lock=True)
    expected = dict(zip(claim.telemetry_ids, claim.raw_sha256, strict=True))
    if len(evidence) != len(expected) or any(
        source["payload_sha256"] != expected[row["id"]] or live_measurement_errors(row, source)
        or row["device_id"] != claim.device_id or row["run_id"] != claim.run_id
        or row["calibration_id"] != claim.calibration_id
        or not claim.window_start <= row["time"] <= claim.window_end
        or row["backend_received_at"] > claim.assessed_at
        or (boot_id is not None and row["boot_id"] != boot_id)
        for row, source in evidence
    ):
        raise PhysicalEvidenceDenied("physical measurement provenance failed")
    rows = [row for row, _ in evidence]
    if command is not None and claim.stage != cs.FAILED_VERIFICATION and any(
        row["applied_cooling"] != command["action_cooling"]
        or row["applied_duty"] != command["action_duty"] for row in rows
    ):
        raise PhysicalEvidenceDenied("measurements do not support the commanded applied state")
    needs_electrical = claim.stage in (cs.ELECTRICAL_VERIFIED, cs.VERIFIED)
    needs_thermal = claim.stage in (cs.THERMAL_VERIFIED, cs.VERIFIED)
    if needs_thermal and len({row["time"] for row in rows}) < 2:
        raise PhysicalEvidenceDenied("thermal response requires a measured trajectory, not one sample")
    if needs_electrical and not any(
        row["electrical_quality"] == "VALID" and all(row[field] is not None for field in (
            "cooling_voltage_v", "cooling_current_a", "cooling_power_w",
        )) for row in rows
    ):
        raise PhysicalEvidenceDenied("valid electrical measurements required")
    if needs_thermal and not any(
        row["thermal_quality"] == "VALID" and all(row[field] is not None for field in ("t1_c", "t2_c", "t3_c"))
        for row in rows
    ):
        raise PhysicalEvidenceDenied("valid thermal measurements required")


def record_physical_assessment(
    connection: Connection, claim: PhysicalClaim, *, authority: PhysicalAuthority | None,
    signature: str | None,
) -> dict:
    if authority is None:
        raise PhysicalEvidenceDenied("physical authority is not provisioned")
    # Revalidate and snapshot even model_copy/mutable-list callers before signing.
    claim = PhysicalClaim.model_validate(claim.model_dump())
    signature_bytes = authority.authenticate(claim, signature)
    serialized = encode_evidence(claim.model_dump())
    digest = hashlib.sha256(serialized).hexdigest()
    command = cs._lock_command(connection, claim.command_id)
    old = connection.execute(select(physical_assessments).where(
        physical_assessments.c.assessment_id == claim.assessment_id,
    )).mappings().one_or_none()
    if old is not None:
        if old["claim_sha256"] != digest:
            raise PhysicalEvidenceDenied("assessment ID already has different evidence")
        return dict(old)
    if command["device_id"] != claim.device_id or command["run_id"] != claim.run_id:
        raise PhysicalEvidenceDenied("assessment command scope differs")
    if claim.stage not in _ALLOWED_PHYSICAL.get(command["status"], ()):
        raise PhysicalEvidenceDenied("physical stage is not permitted from this lifecycle state")
    ack = cs.command_acks.c
    accepted = connection.execute(select(cs.command_acks).where(
        ack.command_id == claim.command_id, ack.topic_device_id == claim.device_id,
        ack.payload_device_id == claim.device_id, ack.validity == "VALID",
        (ack.device_status == "ACCEPTED")
        | ((ack.device_status == "DUPLICATE_CANONICAL") & (ack.canonical_status == "ACCEPTED")),
    ).order_by(ack.backend_received_at, ack.id).limit(1)).mappings().one_or_none()
    if accepted is None or claim.window_start < accepted["backend_received_at"] or claim.assessed_at > datetime.now(timezone.utc):
        raise PhysicalEvidenceDenied("assessment lacks a supported post-ACK chronology")
    if hashlib.sha256(accepted["raw_payload"].encode("utf-8")).hexdigest() != accepted["payload_sha256"]:
        raise PhysicalEvidenceDenied("accepted ACK evidence integrity failed")
    _check_measurements(connection, claim, command=command, boot_id=accepted["boot_id"])
    saved = connection.execute(physical_assessments.insert().values(
        assessment_id=claim.assessment_id, command_id=claim.command_id, authority_id=claim.authority_id,
        stage=claim.stage, assessed_at=claim.assessed_at, claim=json.loads(serialized), claim_sha256=digest,
        signature_sha256=hashlib.sha256(signature_bytes).hexdigest(),
    ).returning(physical_assessments)).mappings().one()
    connection.execute(cs.commands.update().where(cs.commands.c.command_id == claim.command_id).values(
        status=claim.stage, verification_status=claim.stage,
    ))
    cs._record_transition(connection, claim.command_id, command["status"], claim.stage, claim.assessment_id)
    return dict(saved)
