"""Read-only local schema/API/subscription readiness, distinct from /health liveness."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from coldguard_backend.evidence_backup import local_database_url
from coldguard_backend.evidence_paths import portable_component
from coldguard_backend.evidence_tables import evidence_keys
from coldguard_backend.experiment_evidence import encode_evidence

SCHEMA_REVISION = "0014"


def local_backend(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password
        or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or not parsed.port or not 0 < parsed.port < 65536):
        raise ValueError("backend check requires an explicit direct-loopback HTTP origin and port")
    return f"http://127.0.0.1:{parsed.port}"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("local readiness request must not redirect")


def _read_api(base, path):
    # Ignore ambient proxy settings and refuse redirects beyond the owned origin.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(base + path, headers={"Accept": "application/json"}), timeout=3) as response:
        if response.status != 200:
            raise ValueError("local backend did not return HTTP200")
        content = response.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError("readiness response is too large")
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("readiness response must be an object")
        return result


def inspect_stack(engine, *, backend=None, require_mqtt=False, require_ack=False) -> dict:
    base = local_backend(backend) if backend is not None else None
    if (require_mqtt or require_ack) and base is None:
        raise ValueError("subscription checks require an owned backend origin")
    report = {"format": "coldguard-local-readiness-v1", "observed_at": datetime.now(timezone.utc),
              "expected_schema_revision": SCHEMA_REVISION, "database": "UNAVAILABLE", "schema_ready": False,
              "api_liveness": "NOT_CHECKED", "mqtt_required": require_mqtt, "ack_required": require_ack,
              "runtime": {}, "data_class": "SOFTWARE_SIMULATION", "physical_acceptance": "BLOCKED_EXTERNAL"}
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True) as connection:
            tables = set(inspect(connection).get_table_names(schema="public"))
            revisions = list(connection.scalars(text("SELECT version_num FROM public.alembic_version ORDER BY 1"))) if "alembic_version" in tables else []
            expected = set(evidence_keys(SCHEMA_REVISION))
        report.update(database="CONNECTED", revisions=revisions, missing_tables=sorted(expected - tables),
                      unexpected_tables=sorted(tables - expected), schema_ready=revisions == [SCHEMA_REVISION] and tables == expected)
    except SQLAlchemyError:
        # Never copy connection diagnostics/credentials into a shareable report.
        pass
    if base is not None:
        try:
            health, runtime = _read_api(base, "/health"), _read_api(base, "/api/runtime/readiness")
            report["api_liveness"] = "ALIVE" if health == {"status": "ok"} else "INVALID_RESPONSE"
            report["runtime"] = {key: runtime.get(key) is True for key in (
                "telemetry_broker_connected", "telemetry_subscribed", "ack_subscribed", "startup_reconciliation")}
        except (OSError, ValueError):
            report["api_liveness"] = "UNAVAILABLE"
    ready = report["schema_ready"] and (base is None or report["api_liveness"] == "ALIVE")
    if require_mqtt:
        ready = ready and report["runtime"].get("telemetry_broker_connected", False) and report["runtime"].get("telemetry_subscribed", False)
    if require_ack:
        ready = ready and report["runtime"].get("ack_subscribed", False)
    report["status"] = "READY" if ready else "NOT_READY"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--database-only", action="store_true")
    mode.add_argument("--backend", help="owned HTTP origin, e.g. http://127.0.0.1:8000")
    parser.add_argument("--require-mqtt", action="store_true")
    parser.add_argument("--require-ack", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for part in args.output.parts:
        if part not in {args.output.anchor, ".", ".."}:
            portable_component(part)
    if args.output.exists() or args.output.is_symlink():
        parser.error("readiness output already exists; never overwrite evidence")
    if args.backend is not None:
        args.backend = local_backend(args.backend)
    elif args.require_mqtt or args.require_ack:
        parser.error("--require-mqtt/--require-ack needs --backend")
    if "DATABASE_URL" in os.environ:
        value = os.environ["DATABASE_URL"]
    else:
        from coldguard_backend.config import ColdGuardConfig
        value = ColdGuardConfig.load().database_url
    engine = create_engine(local_database_url(value), connect_args={"connect_timeout": 3})
    try:
        result = inspect_stack(engine, backend=args.backend, require_mqtt=args.require_mqtt, require_ack=args.require_ack)
    finally:
        engine.dispose()
    with args.output.open("xb") as output:
        output.write(encode_evidence(result))
    print(result["status"])
    return 0 if result["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
