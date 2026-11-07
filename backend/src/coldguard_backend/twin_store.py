"""Persist device observations separately from intent and derived state."""

from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    Table,
    Text,
    and_,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.engine import Connection

from coldguard_backend.normalized_store import COMPARE_FIELDS, telemetry

_metadata = MetaData()
device_twin = Table(
    "device_twin",
    _metadata,
    Column("device_id", Text, primary_key=True),
    Column("reported_state", JSONB),
    Column("desired_state", JSONB),
    Column("derived_state", JSONB),
    Column("twin_version", BigInteger),
    Column("last_boot_id", Text),
    Column("last_seq", BigInteger),
    Column("last_reported_at", DateTime(timezone=True)),
    Column("last_desired_at", DateTime(timezone=True)),
    Column("last_derived_at", DateTime(timezone=True)),
    Column("connectivity_state", Text),
    Column("device_mode", Text),
    Column("updated_at", DateTime(timezone=True)),
)

_retired_boot = Table(
    "device_twin_retired_boot",
    _metadata,
    Column("device_id", Text, primary_key=True),
    Column("boot_id", Text, primary_key=True),
)


class TwinVersionConflict(Exception):
    """The expected Twin version no longer matches."""


class TwinBootConflict(Exception):
    """The expected boot or eligible successor could not be reconciled."""


def _reported_values(row) -> dict[str, Any]:
    state = {field: row[field] for field in COMPARE_FIELDS if field != "time"}
    state.update(
        captured_at=row["time"].isoformat() if row["time"] is not None else None,
        telemetry_id=row["id"],
        raw_id=row["raw_id"],
    )
    if row["serial_source"] is not None:
        state["serial_source"] = row["serial_source"]
    return {
        "reported_state": state,
        "last_boot_id": row["boot_id"],
        "last_seq": row["seq"],
        "last_reported_at": func.clock_timestamp(),
        "device_mode": row["device_mode"],
        "updated_at": func.clock_timestamp(),
    }


def project_reported(connection: Connection, telemetry_id: int) -> None:
    """Advance reported state from an admitted normalized row in its transaction."""
    row = connection.execute(
        select(telemetry).where(telemetry.c.id == telemetry_id, telemetry.c.twin_eligible)
    ).mappings().one_or_none()
    if row is None:
        return

    twin = device_twin.c
    values = _reported_values(row)
    statement = pg_insert(device_twin).values(
        device_id=row["device_id"], twin_version=1, **values
    )
    connection.execute(
        statement.on_conflict_do_update(
            index_elements=[twin.device_id],
            set_={**values, "twin_version": twin.twin_version + 1},
            where=or_(
                twin.last_boot_id.is_(None),
                and_(twin.last_boot_id == row["boot_id"], twin.last_seq < row["seq"]),
            ),
        )
    )


def update_desired(
    connection: Connection,
    *,
    device_id: str,
    desired_state: dict[str, Any],
    expected_version: int,
) -> int:
    """Replace backend intent only and return the new version.

    Version zero expects an absent row. Any positive expected version
    refers to the whole Twin. The caller owns the transaction.
    """
    if type(expected_version) is not int or expected_version < 0:
        raise ValueError("expected_version must be a non-negative integer")
    if not device_id.strip() or not isinstance(desired_state, dict):
        raise ValueError("device_id must be non-empty and desired_state must be an object")

    twin = device_twin.c
    values = {
        "desired_state": desired_state,
        "twin_version": expected_version + 1,
        "last_desired_at": func.clock_timestamp(),
        "updated_at": func.clock_timestamp(),
    }
    if expected_version == 0:
        statement = (
            pg_insert(device_twin)
            .values(device_id=device_id, **values)
            .on_conflict_do_nothing(index_elements=[twin.device_id])
        )
    else:
        statement = update(device_twin).where(
            twin.device_id == device_id, twin.twin_version == expected_version
        ).values(**values)
    version = connection.execute(statement.returning(twin.twin_version)).scalar_one_or_none()
    if version is None:
        raise TwinVersionConflict(f"Twin version {expected_version} did not match")
    return version


def reconcile_reported_boot(
    connection: Connection, *, device_id: str, expected_boot_id: str, new_boot_id: str
) -> int:
    """Promote a boot independently verified as newer by a trusted backend caller.

    This is an internal operation. MQTT telemetry can never authorize a boot
    switch. The caller supplies the current boot as a precondition and owns
    the transaction. Retired boots cannot be promoted again.
    """
    if not expected_boot_id or not new_boot_id or expected_boot_id == new_boot_id:
        raise ValueError("boot reconciliation requires two distinct boot IDs")
    twin = device_twin.c
    current = connection.execute(
        select(twin.last_boot_id).where(twin.device_id == device_id).with_for_update()
    ).scalar_one_or_none()
    if current != expected_boot_id:
        raise TwinBootConflict("current boot did not match")
    retired = connection.execute(
        select(_retired_boot.c.boot_id).where(
            _retired_boot.c.device_id == device_id, _retired_boot.c.boot_id == new_boot_id
        )
    ).scalar_one_or_none()
    if retired is not None:
        raise TwinBootConflict("boot has been retired")

    sample = telemetry.c
    row = connection.execute(
        select(telemetry)
        .where(sample.device_id == device_id, sample.boot_id == new_boot_id, sample.twin_eligible)
        .order_by(sample.seq.desc())
        .limit(1)
    ).mappings().one_or_none()
    if row is None:
        raise TwinBootConflict("successor boot has no eligible observation")

    connection.execute(insert(_retired_boot).values(device_id=device_id, boot_id=current))
    return connection.execute(
        update(device_twin)
        .where(twin.device_id == device_id)
        .values(**_reported_values(row), twin_version=twin.twin_version + 1)
        .returning(twin.twin_version)
    ).scalar_one()
