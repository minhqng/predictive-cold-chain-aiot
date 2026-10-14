"""Alembic environment for the ColdGuard backend (C-W01-04).

Connection precedence: ``DATABASE_URL`` wins; otherwise the URL is built
from validated :class:`ColdGuardConfig` values. Migrations run
independently of FastAPI startup via ``alembic -c alembic.ini``.

W01 has no ORM entity models, so ``target_metadata`` is ``None`` and the
baseline revision manages no domain tables. Later member-owned schema
additions must arrive as new reviewed revisions, never as edits to the
baseline. Extension-owned objects (TimescaleDB internals) are owned by
``infra/postgres/init/001_extensions.sql``; future autogenerate runs must
exclude extension-owned objects explicitly.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

from coldguard_backend.config import ColdGuardConfig

config = context.config


def _database_url() -> str:
    explicit = os.environ.get("DATABASE_URL", "").strip()
    if explicit:
        return explicit
    return ColdGuardConfig.load().database_url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
