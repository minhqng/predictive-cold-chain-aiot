"""Authenticated Controller B dispatch from current, signed policy evidence."""

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import Column, DateTime, MetaData, Table, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Connection, Engine

from coldguard_backend import command_store as commands
from coldguard_backend.command_authorization import AuthorizedCommandGateway
from coldguard_backend.command_publisher import PublishFn
from coldguard_backend.contracts import Command
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import experiments
from coldguard_backend.inference import FrozenModelSpec
from coldguard_backend.measurement_integrity import live_measurement_errors, measurement_rows
from coldguard_backend.prediction_store import current_prediction, lock_prediction_device, prediction_inputs
from coldguard_backend.twin_store import device_twin

policy_approvals = Table(
    "policy_approvals", MetaData(),
    Column("command_id", Text, primary_key=True),
    Column("authority_id", Text),
    Column("policy_version", Text),
    Column("command_sha256", Text),
    Column("signature_sha256", Text),
    Column("model_spec", JSONB),
    Column("model_spec_sha256", Text),
    Column("approved_at", DateTime(timezone=True)),
)


class DPolicyAuthority:
    """Trust an explicitly provisioned Member D approval key for one policy."""

    def __init__(self, policy_version: str, key: bytes) -> None:
        if not policy_version.strip() or len(key) < 32:
            raise ValueError("an approved policy version and strong D key are required")
        self._policy_version = policy_version
        self._key = key
        # Strong provisioned keys have a stable audit identity; no key or
        # reusable approval signature is exposed by the trace.
        self.authority_id = "member-d-key-" + hashlib.sha256(key).hexdigest()

    def approves(self, command: Command, signature: str | None) -> bool:
        if command.policy_version != self._policy_version or not isinstance(signature, str) or len(signature) != 64:
            return False
        expected = hmac.digest(self._key, commands.canonical_command_bytes(command), "sha256")
        try:
            provided = bytes.fromhex(signature)
        except ValueError:
            return False
        return hmac.compare_digest(provided, expected)


def _current_context(
    connection: Connection, command: Command, approved_model: FrozenModelSpec | None, *, lock: bool = False,
) -> dict | None:
    if approved_model is None:
        return None
    query = select(experiments).where(experiments.c.run_id == command.run_id)
    if lock:
        query = query.with_for_update()
    run = connection.execute(query).mappings().one_or_none()
    if (
        run is None or run["device_id"] != command.device_id or run["status"] != "RUNNING"
        or run["controller_id"] != command.controller_id
        or any(run["versions"].get(field) != expected for field, expected in (
            ("model_version", approved_model.model_version),
            ("feature_version", approved_model.feature_version),
            ("policy_version", command.policy_version),
        ))
    ):
        return None
    projection = current_prediction(connection, command.device_id, None)
    prediction = projection["prediction"]
    if (
        projection["status"] != "FRESH" or prediction["prediction_id"] != command.prediction_id
        or prediction["run_id"] != command.run_id
        or not prediction["created_at"] <= command.created_at <= datetime.now(timezone.utc)
        or command.expires_at > prediction["fresh_until"]
        or any(prediction[field] != expected for field, expected in (
            ("model_version", approved_model.model_version),
            ("model_sha256", approved_model.artifact_sha256),
            ("feature_version", approved_model.feature_version),
            ("feature_schema_sha256", approved_model.feature_schema_sha256),
            ("horizon_sec", approved_model.horizon_s),
        ))
    ):
        return None
    query = select(device_twin).where(
        device_twin.c.device_id == command.device_id,
    )
    if lock:
        query = query.with_for_update()
    twin = connection.execute(query).mappings().one_or_none()
    if (
        twin is None or twin["last_boot_id"] is None or twin["device_mode"] != "ONLINE_NORMAL"
        or any(twin["reported_state"].get(field) != "VALID" for field in (
            "thermal_quality", "electrical_quality", "overall_quality",
        ))
    ):
        return None
    ids = list(connection.scalars(select(prediction_inputs.c.telemetry_id).where(
        prediction_inputs.c.prediction_id == command.prediction_id,
    ).order_by(prediction_inputs.c.ordinal)))
    rows = measurement_rows(connection, ids, lock=lock)
    if not rows or len(rows) != len(ids) or any(
        sample["device_id"] != command.device_id or sample["run_id"] != command.run_id
        or sample["boot_id"] != twin["last_boot_id"] or live_measurement_errors(sample, source)
        or sample["time"] > prediction["created_at"]
        or sample["backend_received_at"] > prediction["created_at"]
        for sample, source in rows
    ):
        return None
    if twin["reported_state"].get("telemetry_id") not in ids:
        return None
    # The persisted freshness budget is not renewed by a delayed delivery.
    # Require the same budget against actual acquisition, not just receipt.
    latest_acquisition = max(sample["time"] for sample, _ in rows)
    input_age_budget = prediction["fresh_until"] - prediction["latest_input_at"]
    if command.expires_at > latest_acquisition + input_age_budget:
        return None
    return dict(twin)


class ControllerBGuard:
    """Bind a final database dispatch check to the signed command envelope."""

    def __init__(
        self, command: Command, authority: DPolicyAuthority | None, signature: str | None,
        approved_model: FrozenModelSpec | None = None,
    ) -> None:
        self._command = Command.model_validate_json(commands.canonical_command_bytes(command))
        self._authority = authority
        self._signature = signature
        self._model = approved_model

    def approved(self) -> bool:
        command = self._command
        return bool(
            self._model is not None and self._authority is not None
            and self._authority.approves(command, self._signature)
            and command.controller_id == "PREDICTIVE" and command.run_id is not None
            and command.prediction_id is not None and command.expected_twin_version is not None
        )

    def _receipt(self) -> dict:
        spec = self._model.model_dump(mode="json")
        return {
            "command_id": self._command.command_id,
            "authority_id": self._authority.authority_id,
            "policy_version": self._command.policy_version,
            "command_sha256": commands.command_payload_sha256(self._command),
            "signature_sha256": hashlib.sha256(bytes.fromhex(self._signature)).hexdigest(),
            "model_spec": spec, "model_spec_sha256": hashlib.sha256(encode_evidence(spec)).hexdigest(),
        }

    def record_approval(self, connection: Connection, saved: dict) -> bool:
        """Commit exact D approval with the reservation, before any broker I/O."""
        if not self.approved() or saved["payload_sha256"] != commands.command_payload_sha256(self._command):
            return False
        receipt = self._receipt()
        connection.execute(insert(policy_approvals).values(
            **receipt, approved_at=func.clock_timestamp(),
        ).on_conflict_do_nothing(index_elements=["command_id"]))
        old = connection.execute(select(policy_approvals).where(
            policy_approvals.c.command_id == saved["command_id"],
        )).mappings().one_or_none()
        return old is not None and all(old[key] == value for key, value in receipt.items())

    def __call__(self, connection: Connection, saved: dict) -> bool:
        command = self._command
        if not self.approved() or saved["payload_sha256"] != commands.command_payload_sha256(command):
            return False
        receipt = self._receipt()
        old = connection.execute(select(policy_approvals).where(
            policy_approvals.c.command_id == command.command_id,
        )).mappings().one_or_none()
        if old is None or any(old[key] != value for key, value in receipt.items()):
            return False
        lock_prediction_device(connection, command.device_id)
        twin = _current_context(connection, command, self._model, lock=True)
        return (
            twin is not None and saved["status"] != commands.UNKNOWN
            and saved["desired_twin_version"] == twin["twin_version"] == command.expected_twin_version + 1
        )


class ControllerBDispatch:
    """Server-side entrypoint, disabled until a D policy authority is configured."""

    def __init__(
        self, engine: Engine, transport: PublishFn, *, transport_ready: Callable[[], bool],
        backend_token: str, allowed_devices: frozenset[str], authority: DPolicyAuthority | None = None,
        approved_model: FrozenModelSpec | None = None,
    ) -> None:
        self._engine = engine
        self._transport = transport
        self._ready = transport_ready
        self._token = backend_token
        self._devices = allowed_devices
        self._authority = authority
        self._model = approved_model

    def dispatch(self, command: Command, *, backend_token: str | None, approval_signature: str | None) -> dict:
        # Snapshot mutable caller models before authorization or persistence.
        command = Command.model_validate_json(commands.canonical_command_bytes(command))
        guard = ControllerBGuard(command, self._authority, approval_signature, self._model)

        def authorized(candidate: Command) -> bool:
            if not guard.approved():
                return False
            with self._engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
                existing = commands.get_command(connection, candidate.command_id)
                if existing is not None and existing["status"] == commands.UNKNOWN:
                    return False
                return _current_context(connection, candidate, self._model) is not None

        gateway = AuthorizedCommandGateway(
            self._engine, self._transport, backend_token=self._token, allowed_devices=self._devices,
            policy_allows=authorized, transport_ready=self._ready,
        )
        return gateway.dispatch(command, backend_token=backend_token, guard=guard)
