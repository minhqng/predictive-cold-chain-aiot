"""Local operational checks; no Compose, hardware or independent human acceptance."""

from pathlib import Path
import os
import socket

import pytest
from sqlalchemy import create_engine

from scripts.check_stack import inspect_stack, local_backend
from coldguard_backend.evidence_tables import fingerprint_connection


def test_runtime_image_includes_migration_configuration_and_operator_scripts():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    assert "COPY alembic.ini ./" in dockerfile
    assert "COPY scripts/ ./scripts/" in dockerfile
    assert (root / "alembic.ini").is_file()


def test_current_schema_readiness_is_readonly_not_physical_acceptance(db_engine):
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        before = fingerprint_connection(connection)
    result = inspect_stack(db_engine)
    assert result["status"] == "READY" and result["database"] == "CONNECTED" and result["revisions"] == ["0014"]
    assert result["api_liveness"] == "NOT_CHECKED" and result["physical_acceptance"] == "BLOCKED_EXTERNAL"
    with db_engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        assert fingerprint_connection(connection) == before


@pytest.mark.skipif(not os.environ.get("COLDGUARD_TEST_OPERATIONS_EMPTY_URL"), reason="requires a separate empty owned operations DB")
def test_connected_but_unmigrated_database_is_not_ready():
    engine = create_engine(os.environ["COLDGUARD_TEST_OPERATIONS_EMPTY_URL"])
    try:
        result = inspect_stack(engine)
    finally:
        engine.dispose()
    assert result["database"] == "CONNECTED" and result["status"] == "NOT_READY"
    assert result["revisions"] == [] and "alembic_version" in result["missing_tables"]


def test_unavailable_owned_database_is_not_ready_without_credential_leak(db_engine):
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        engine = create_engine(db_engine.url.set(port=unused.getsockname()[1]), connect_args={"connect_timeout": 1})
        try:
            result = inspect_stack(engine)
        finally:
            engine.dispose()
    assert result["database"] == "UNAVAILABLE" and result["status"] == "NOT_READY"
    assert db_engine.url.password not in str(result)


@pytest.mark.parametrize("value", ["https://127.0.0.1:8000", "http://example.com:8000", "http://localhost:8000",
    "http://user:password@127.0.0.1:8000", "http://127.0.0.1:8000/path", "http://127.0.0.1:8000?query=1",
    "http://127.0.0.1:8000#fragment", "http://127.0.0.1:0", "http://127.0.0.1"])
def test_backend_origins_reject_ambiguous_or_nonlocal_inputs_before_db_access(value):
    class Unopened:
        def connect(self):
            pytest.fail("bad backend origin reached database access")
    with pytest.raises(ValueError):
        inspect_stack(Unopened(), backend=value)


def test_loopback_origin_normalizes_only_safe_origin():
    assert local_backend("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"


def test_live_api_liveness_does_not_hide_disabled_subscribers(db_engine, monkeypatch, tmp_path):
    from tests.test_outage_recovery import _backend_process
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    for key in ("COLDGUARD_MQTT_INGEST", "COLDGUARD_MQTT_ACK_INGEST", "COLDGUARD_RECONCILE_COMMANDS"):
        monkeypatch.setenv(key, "false")
    pids = []
    with _backend_process(tmp_path / "operations-backend.log", pids) as client:
        base = str(client.base_url).rstrip("/")
        basic = inspect_stack(db_engine, backend=base)
        assert basic["status"] == "READY" and basic["api_liveness"] == "ALIVE"
        required = inspect_stack(db_engine, backend=base, require_mqtt=True, require_ack=True)
        assert required["status"] == "NOT_READY" and not any(required["runtime"].values())
    assert len(pids) == 1


def test_string_true_and_false_are_not_subscription_readiness(db_engine, monkeypatch):
    import scripts.check_stack as module
    monkeypatch.setattr(module, "_read_api", lambda _base, path: {"status": "ok"} if path == "/health" else {
        "telemetry_broker_connected": "true", "telemetry_subscribed": "false", "ack_subscribed": 1})
    result = inspect_stack(db_engine, backend="http://127.0.0.1:8000", require_mqtt=True, require_ack=True)
    assert result["status"] == "NOT_READY" and not any(result["runtime"].values())


def test_readiness_redirect_cannot_contact_other_origins():
    from scripts.check_stack import NoRedirect
    with pytest.raises(ValueError, match="must not redirect"):
        NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://example.com")


def test_readiness_cli_rejects_existing_report_before_opening_database(tmp_path, monkeypatch):
    import scripts.check_stack as cli
    output = tmp_path / "existing.json"
    output.write_bytes(b"SOFTWARE_SIMULATION preserve evidence")
    calls = []
    monkeypatch.setattr(cli, "create_engine", lambda *_args, **_kwargs: calls.append(True))
    monkeypatch.setattr("sys.argv", ["check_stack.py", "--database-only", "--output", str(output)])
    with pytest.raises(SystemExit):
        cli.main()
    assert not calls and output.read_bytes() == b"SOFTWARE_SIMULATION preserve evidence"


@pytest.mark.parametrize("name", ["schema-readiness.json", "runtime-readiness.json"])
def test_documented_parent_relative_output_is_admitted_by_real_cli(db_engine, tmp_path, monkeypatch, name):
    import json
    import scripts.check_stack as cli
    working = tmp_path / "backend"
    working.mkdir()
    evidence = tmp_path / "evidence-out"
    evidence.mkdir()
    monkeypatch.chdir(working)
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    # Database-only isolates output admission; the clean native drill tests required live subscribers.
    monkeypatch.setattr("sys.argv", ["check_stack.py", "--database-only", "--output", "../evidence-out/" + name])
    assert cli.main() == 0
    assert json.loads((evidence / name).read_bytes())["status"] == "READY"


def test_compose_runbook_waits_and_stops_on_migration_failure():
    root = Path(__file__).resolve().parents[1]
    route = (root / "RUNBOOK.md").read_text().split("```sh", 1)[1].split("```", 1)[0]
    assert "set -euo pipefail" in route
    lines = route.splitlines()
    wait = next(index for index, line in enumerate(lines) if "up -d" in line and "postgres mosquitto" in line)
    migrate = next(index for index, line in enumerate(lines) if "alembic -c alembic.ini upgrade head" in line)
    start = next(index for index, line in enumerate(lines) if "up -d" in line and line.endswith(" backend"))
    assert "--wait" in lines[wait] and "--wait-timeout 60" in lines[wait] and wait < migrate < start


def test_compose_database_readiness_probes_tcp_not_temporary_init_socket():
    compose = (Path(__file__).resolve().parents[2] / "infra/compose.yaml").read_text()
    assert "pg_isready -h 127.0.0.1 -p 5432" in compose
