"""Deterministic runtime configuration for the ColdGuard backend.

Covers C-W01-05: three runtime profiles (``dev`` / ``integration`` /
``experiment``) with predictable precedence and validated values.

Precedence: explicit ``load(profile=...)`` argument wins over the
``COLDGUARD_PROFILE`` environment variable, which wins over the ``dev``
default. Unknown profiles are rejected; they never silently fall back.

Host vs container networking: defaults describe a host runtime
(``localhost`` services). Inside Compose the backend service overrides the
host/port variables with Compose service names (``postgres``,
``mosquitto``); see ``infra/compose.yaml``. The two settings are never
mixed in one process environment.

The ``experiment`` profile only selects configuration values. It does not
claim that real experimental data or physical proof exists (Doc 03).

No function here logs credentials. Use :meth:`ColdGuardConfig.safe_summary`
for diagnostics; it redacts the database password.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

PROFILES = ("dev", "integration", "experiment")
DEFAULT_PROFILE = "dev"

_ENV_PREFIX_DOC = (
    "COLDGUARD_PROFILE, POSTGRES_HOST/PORT/DB/USER/PASSWORD, "
    "MQTT_HOST/PORT/USERNAME/PASSWORD/TLS_CA, COLDGUARD_MQTT_INGEST, BACKEND_HOST/PORT"
)


def _get(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, default)
    return value.strip() if isinstance(value, str) else default


def _port(env: Mapping[str, str], name: str, default: int) -> int:
    raw = _get(env, name, str(default))
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer port, got {raw!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{name} must be within 1-65535, got {port}")
    return port


def _non_empty(env: Mapping[str, str], name: str, default: str) -> str:
    value = _get(env, name, default)
    if not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class ColdGuardConfig:
    """Validated backend runtime configuration."""

    profile: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    backend_host: str
    backend_port: int
    mqtt_tls_ca: str = ""

    @classmethod
    def load(
        cls, profile: str | None = None, env: Mapping[str, str] | None = None
    ) -> "ColdGuardConfig":
        """Build configuration from an explicit profile and environment."""
        source = os.environ if env is None else env
        selected = (profile or _get(source, "COLDGUARD_PROFILE", DEFAULT_PROFILE)).strip()
        if selected not in PROFILES:
            raise ValueError(
                f"unknown COLDGUARD_PROFILE {selected!r}; "
                f"expected one of {', '.join(PROFILES)}"
            )
        return cls(
            profile=selected,
            postgres_host=_non_empty(source, "POSTGRES_HOST", "localhost"),
            postgres_port=_port(source, "POSTGRES_PORT", 5432),
            postgres_db=_non_empty(source, "POSTGRES_DB", "coldguard"),
            postgres_user=_non_empty(source, "POSTGRES_USER", "coldguard"),
            postgres_password=_get(source, "POSTGRES_PASSWORD", "coldguard_dev_only"),
            mqtt_host=_non_empty(source, "MQTT_HOST", "localhost"),
            mqtt_port=_port(source, "MQTT_PORT", 1883),
            mqtt_username=_get(source, "MQTT_USERNAME", ""),
            mqtt_password=_get(source, "MQTT_PASSWORD", ""),
            backend_host=_non_empty(source, "BACKEND_HOST", "127.0.0.1"),
            backend_port=_port(source, "BACKEND_PORT", 8000),
            mqtt_tls_ca=_get(source, "MQTT_TLS_CA", ""),
        )

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for PostgreSQL via psycopg 3 (contains password)."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def safe_summary(self) -> dict[str, str]:
        """Redacted diagnostic summary; safe to log."""
        mqtt_auth = (
            f"user {self.mqtt_username!r} (password redacted)"
            if self.mqtt_username
            else "anonymous (no MQTT_USERNAME configured)"
        )
        return {
            "profile": self.profile,
            "postgres": f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            f" as {self.postgres_user} (password redacted)",
            "mqtt": f"{self.mqtt_host}:{self.mqtt_port} as {mqtt_auth}",
            "backend": f"{self.backend_host}:{self.backend_port}",
            "env_vars": _ENV_PREFIX_DOC,
        }
