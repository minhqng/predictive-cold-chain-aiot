"""Local operator campaign registration, health and per-run closure. No dispatch."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from coldguard_backend.campaign_integrity import close_run, live_integrity
from coldguard_backend.campaign_store import CampaignCreate, register_campaign
from coldguard_backend.experiment_evidence import encode_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    register = commands.add_parser("register")
    register.add_argument("--plan", type=Path, required=True)
    monitor = commands.add_parser("integrity")
    monitor.add_argument("--campaign", required=True)
    close = commands.add_parser("close")
    close.add_argument("--campaign", required=True)
    close.add_argument("--run", required=True)
    close.add_argument("--reason", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = make_url(os.environ.get("DATABASE_URL", ""))
    if url.drivername != "postgresql+psycopg" or url.host != "127.0.0.1" or url.query:
        parser.error("DATABASE_URL must be a direct local loopback PostgreSQL operator database")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        if args.operation == "integrity":
            report = live_integrity(engine, args.campaign)
        else:
            with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
                with connection.begin():
                    report = register_campaign(connection, CampaignCreate.model_validate(json.loads(args.plan.read_text()))) if args.operation == "register" else close_run(
                        connection, args.campaign, args.run, reason=args.reason,
                    )
        with args.output.open("xb") as output:
            output.write(encode_evidence(report))
        return 0 if report.get("database_health") != "UNAVAILABLE" else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
