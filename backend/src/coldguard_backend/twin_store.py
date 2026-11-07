"""Device Twin storage and concurrency-safe lifecycle manager (C-W04).

Implements C-W04-01 through C-W04-04:
- C-W04-01: device_twin persistence supporting reported_state, desired_state,
  derived_state, twin_version, last_boot_id, last_seq, and relevant timestamps.
- C-W04-02: Reported updater: ONLY validated, committed device observations
  may mutate reported_state.
- C-W04-03: Desired updater: backend intent path. Desired updates never alter
  reported_state. Supports optimistic concurrency via expected_version.
- C-W04-04: Freshness guard: rejects exact duplicates, conflicting replays,
  out-of-order sequence (seq < last_seq), and old-boot replays. Monotonically
  advances twin_version without regressing authoritative state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    JSON,
    MetaData,
    Table,
    Text,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine

log = logging.getLogger(__name__)

_METADATA = MetaData()

device_twin = Table(
    "device_twin",
    _METADATA,
    Column("device_id", Text, primary_key=True),
    Column("reported_state", JSON, nullable=False, default=dict),
    Column("desired_state", JSON, nullable=False, default=dict),
    Column("derived_state", JSON, nullable=False, default=dict),
    Column("twin_version", BigInteger, nullable=False, default=0),
    Column("last_boot_id", Text, nullable=True),
    Column("last_seq", BigInteger, nullable=True),
    Column("reported_at", DateTime(timezone=True), nullable=True),
    Column("desired_at", DateTime(timezone=True), nullable=True),
    Column("derived_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: Any) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _row_to_dict(mapping: Any) -> dict[str, Any]:
    return {
        "device_id": mapping["device_id"],
        "reported_state": mapping["reported_state"] or {},
        "desired_state": mapping["desired_state"] or {},
        "derived_state": mapping["derived_state"] or {},
        "twin_version": mapping["twin_version"],
        "last_boot_id": mapping["last_boot_id"],
        "last_seq": mapping["last_seq"],
        "reported_at": mapping["reported_at"],
        "desired_at": mapping["desired_at"],
        "derived_at": mapping["derived_at"],
        "created_at": mapping["created_at"],
        "updated_at": mapping["updated_at"],
    }


def fetch_twin(
    engine_or_conn: Engine | Connection, device_id: str
) -> dict[str, Any] | None:
    """Fetch the current digital twin record for a device."""
    query = select(device_twin).where(device_twin.c.device_id == device_id)
    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.connect() as conn:
            row = conn.execute(query).mappings().first()
            return _row_to_dict(row) if row is not None else None
    row = engine_or_conn.execute(query).mappings().first()
    return _row_to_dict(row) if row is not None else None


def update_twin_reported(
    engine_or_conn: Engine | Connection,
    *,
    device_id: str,
    boot_id: str,
    seq: int,
    state: dict[str, Any],
    reported_at: datetime | None = None,
) -> dict[str, Any]:
    """Update twin reported state governed by C-W04-04 freshness guards.

    Outcomes:
    - ``updated``: new device created or fresher sequence / newer boot applied.
    - ``exact_duplicate``: same boot_id and same seq received again.
    - ``stale_seq``: same boot_id but seq < last_seq (out-of-order observation).
    - ``stale_boot_replay``: older boot_id replayed after newer active boot.
    """
    now = _utcnow()
    stamp = reported_at or now

    def _execute(conn: Connection) -> dict[str, Any]:
        # Lock row for update on PostgreSQL when supported, simple select otherwise
        query = select(device_twin).where(device_twin.c.device_id == device_id)
        if conn.dialect.name == "postgresql":
            query = query.with_for_update()
        existing = conn.execute(query).mappings().first()

        if existing is None:
            stmt = insert(device_twin).values(
                device_id=device_id,
                reported_state=state,
                desired_state={},
                derived_state={},
                twin_version=1,
                last_boot_id=boot_id,
                last_seq=seq,
                reported_at=stamp,
                desired_at=None,
                derived_at=None,
                created_at=now,
                updated_at=now,
            )
            conn.execute(stmt)
            fresh = conn.execute(
                select(device_twin).where(device_twin.c.device_id == device_id)
            ).mappings().one()
            return {
                "outcome": "updated",
                "twin": _row_to_dict(fresh),
                "twin_version": 1,
            }

        last_boot = existing["last_boot_id"]
        last_s = existing["last_seq"]
        last_rep_at = existing["reported_at"]
        curr_ver = existing["twin_version"]

        # Check 1: Same boot session
        if last_boot is not None and boot_id == last_boot:
            if last_s is not None:
                if seq > last_s:
                    new_ver = curr_ver + 1
                    stmt = (
                        update(device_twin)
                        .where(device_twin.c.device_id == device_id)
                        .values(
                            reported_state=state,
                            last_seq=seq,
                            reported_at=stamp,
                            twin_version=new_ver,
                            updated_at=now,
                        )
                    )
                    conn.execute(stmt)
                    fresh = conn.execute(
                        select(device_twin).where(device_twin.c.device_id == device_id)
                    ).mappings().one()
                    return {
                        "outcome": "updated",
                        "twin": _row_to_dict(fresh),
                        "twin_version": new_ver,
                    }
                elif seq == last_s:
                    return {
                        "outcome": "exact_duplicate",
                        "twin": _row_to_dict(existing),
                        "twin_version": curr_ver,
                    }
                else:
                    return {
                        "outcome": "stale_seq",
                        "twin": _row_to_dict(existing),
                        "twin_version": curr_ver,
                    }

        # Check 2: Boot transition or boot replay
        t_incoming = _ensure_utc(stamp)
        t_existing = _ensure_utc(last_rep_at)
        if t_existing is not None and t_incoming is not None:
            if t_incoming < t_existing:
                log.info(
                    "stale boot replay ignored for device %s: incoming boot=%s at %s < active boot=%s at %s",
                    device_id,
                    boot_id,
                    t_incoming,
                    last_boot,
                    t_existing,
                )
                return {
                    "outcome": "stale_boot_replay",
                    "twin": _row_to_dict(existing),
                    "twin_version": curr_ver,
                }

        # Newer boot transition accepted
        new_ver = curr_ver + 1
        stmt = (
            update(device_twin)
            .where(device_twin.c.device_id == device_id)
            .values(
                reported_state=state,
                last_boot_id=boot_id,
                last_seq=seq,
                reported_at=stamp,
                twin_version=new_ver,
                updated_at=now,
            )
        )
        conn.execute(stmt)
        fresh = conn.execute(
            select(device_twin).where(device_twin.c.device_id == device_id)
        ).mappings().one()
        return {
            "outcome": "updated",
            "twin": _row_to_dict(fresh),
            "twin_version": new_ver,
        }

    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as conn:
            return _execute(conn)
    return _execute(engine_or_conn)


def update_twin_desired(
    engine_or_conn: Engine | Connection,
    *,
    device_id: str,
    desired_state: dict[str, Any],
    desired_at: datetime | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Update twin desired state (backend intent).

    Preserves reported_state domain completely.
    Supports optimistic concurrency if expected_version is provided.
    """
    now = _utcnow()
    stamp = desired_at or now

    def _execute(conn: Connection) -> dict[str, Any]:
        query = select(device_twin).where(device_twin.c.device_id == device_id)
        if conn.dialect.name == "postgresql":
            query = query.with_for_update()
        existing = conn.execute(query).mappings().first()

        if existing is None:
            stmt = insert(device_twin).values(
                device_id=device_id,
                reported_state={},
                desired_state=desired_state,
                derived_state={},
                twin_version=1,
                last_boot_id=None,
                last_seq=None,
                reported_at=None,
                desired_at=stamp,
                derived_at=None,
                created_at=now,
                updated_at=now,
            )
            conn.execute(stmt)
            fresh = conn.execute(
                select(device_twin).where(device_twin.c.device_id == device_id)
            ).mappings().one()
            return {
                "outcome": "updated",
                "twin": _row_to_dict(fresh),
                "twin_version": 1,
            }

        curr_ver = existing["twin_version"]
        if expected_version is not None and expected_version != curr_ver:
            return {
                "outcome": "version_conflict",
                "expected_version": expected_version,
                "current_version": curr_ver,
                "twin": _row_to_dict(existing),
                "twin_version": curr_ver,
            }

        new_ver = curr_ver + 1
        stmt = (
            update(device_twin)
            .where(device_twin.c.device_id == device_id)
            .values(
                desired_state=desired_state,
                desired_at=stamp,
                twin_version=new_ver,
                updated_at=now,
            )
        )
        conn.execute(stmt)
        fresh = conn.execute(
            select(device_twin).where(device_twin.c.device_id == device_id)
        ).mappings().one()
        return {
            "outcome": "updated",
            "twin": _row_to_dict(fresh),
            "twin_version": new_ver,
        }

    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as conn:
            return _execute(conn)
    return _execute(engine_or_conn)


def update_twin_derived(
    engine_or_conn: Engine | Connection,
    *,
    device_id: str,
    derived_state: dict[str, Any],
    derived_at: datetime | None = None,
) -> dict[str, Any]:
    """Update twin derived state (analytics/model inference domain).

    Preserves reported_state and desired_state domains completely.
    """
    now = _utcnow()
    stamp = derived_at or now

    def _execute(conn: Connection) -> dict[str, Any]:
        query = select(device_twin).where(device_twin.c.device_id == device_id)
        if conn.dialect.name == "postgresql":
            query = query.with_for_update()
        existing = conn.execute(query).mappings().first()

        if existing is None:
            stmt = insert(device_twin).values(
                device_id=device_id,
                reported_state={},
                desired_state={},
                derived_state=derived_state,
                twin_version=1,
                last_boot_id=None,
                last_seq=None,
                reported_at=None,
                desired_at=None,
                derived_at=stamp,
                created_at=now,
                updated_at=now,
            )
            conn.execute(stmt)
            fresh = conn.execute(
                select(device_twin).where(device_twin.c.device_id == device_id)
            ).mappings().one()
            return {
                "outcome": "updated",
                "twin": _row_to_dict(fresh),
                "twin_version": 1,
            }

        new_ver = existing["twin_version"] + 1
        stmt = (
            update(device_twin)
            .where(device_twin.c.device_id == device_id)
            .values(
                derived_state=derived_state,
                derived_at=stamp,
                twin_version=new_ver,
                updated_at=now,
            )
        )
        conn.execute(stmt)
        fresh = conn.execute(
            select(device_twin).where(device_twin.c.device_id == device_id)
        ).mappings().one()
        return {
            "outcome": "updated",
            "twin": _row_to_dict(fresh),
            "twin_version": new_ver,
        }

    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as conn:
            return _execute(conn)
    return _execute(engine_or_conn)
