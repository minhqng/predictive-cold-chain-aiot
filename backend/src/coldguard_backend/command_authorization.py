"""Authenticate trusted backend command callers before creating executable intent."""

import hmac
from typing import Callable

from sqlalchemy.engine import Engine

from coldguard_backend.command_publisher import CommandPublisher, PublishFn
from coldguard_backend.command_service import create_command_intent
from coldguard_backend.contracts import Command


class CommandAccessDenied(PermissionError):
    pass


class AuthorizedCommandGateway:
    """Internal backend entrypoint. The application exposes no HTTP dispatch route."""

    def __init__(
        self, engine: Engine, transport: PublishFn, *, backend_token: str,
        allowed_devices: frozenset[str], policy_allows: Callable[[Command], bool],
    ) -> None:
        if len(backend_token) < 32 or not allowed_devices:
            raise ValueError("a provisioned backend token and explicit device scope are required")
        self._token = backend_token.encode("utf-8")
        self._allowed_devices = frozenset(allowed_devices)
        self._policy_allows = policy_allows
        self._engine = engine
        self._publisher = CommandPublisher(engine, transport)

    def dispatch(self, command: Command, *, backend_token: str | None) -> dict:
        supplied = backend_token.encode("utf-8") if isinstance(backend_token, str) else b""
        if not hmac.compare_digest(supplied, self._token):
            raise CommandAccessDenied("backend authentication failed")
        if command.device_id not in self._allowed_devices:
            raise CommandAccessDenied("device is outside the authenticated scope")
        if self._policy_allows(command) is not True:
            raise CommandAccessDenied("policy did not authorize this command")
        create_command_intent(self._engine, command)
        return self._publisher.publish(command.command_id)
