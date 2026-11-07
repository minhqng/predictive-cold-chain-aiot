"""Backend policy entrypoint and the absence of a frontend dispatch route."""

import secrets

import pytest
from fastapi.testclient import TestClient

from coldguard_backend import command_store as commands
from coldguard_backend.command_authorization import AuthorizedCommandGateway, CommandAccessDenied
from coldguard_backend.command_publisher import PublishResult
from coldguard_backend.main import app
from tests.command_testkit import cleanup_commands, make_command


def test_frontend_has_no_command_dispatch_route():
    assert TestClient(app).post("/api/commands", json={"command_id": "no-actuation"}).status_code == 404


def test_authentication_device_scope_and_policy_precede_persistence(db_engine):
    token = secrets.token_urlsafe(32)
    sent = []
    allowed = "auth-scope"
    command = make_command("auth-software", device_id=allowed)
    wrong_device = make_command("auth-wrong-device", device_id="outside-scope")
    rejected = make_command("auth-policy-denied", device_id=allowed)
    gateway = AuthorizedCommandGateway(
        db_engine, lambda *args: sent.append(args) or PublishResult("PUBACK"),
        backend_token=token, allowed_devices=frozenset({allowed}),
        policy_allows=lambda cmd: cmd.command_id == command.command_id,
    )
    try:
        for candidate, credential, message in (
            (command, None, "authentication failed"),
            (command, "invalid", "authentication failed"),
            (wrong_device, token, "device is outside"),
            (rejected, token, "policy did not authorize"),
        ):
            with pytest.raises(CommandAccessDenied, match=message):
                gateway.dispatch(candidate, backend_token=credential)
        with db_engine.connect() as conn:
            for item in (command, wrong_device, rejected):
                assert commands.get_command(conn, item.command_id) is None
        assert not sent
        result = gateway.dispatch(command, backend_token=token)
        assert result["outcome"] == "puback"
        assert len(sent) == 1
        assert sent[0][0] == f"coldguard/{allowed}/command"
    finally:
        cleanup_commands(db_engine, allowed)
