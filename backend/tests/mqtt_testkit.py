"""Shared helpers for real-provider MQTT/DB integration tests (C-W02).

Conventions, matching the W01 migration-test pattern:

* The database comes from ``COLDGUARD_TEST_DATABASE_URL`` (full
  SQLAlchemy URL). Tests skip honestly when it is unset — never a
  silent pass.
* The broker comes from ``COLDGUARD_TEST_MQTT_HOST`` (plus optional
  ``COLDGUARD_TEST_MQTT_PORT`` and the device/backend credential vars).
  Tests skip honestly when the host var is unset.
* Completion is condition-driven (``wait_for`` polling), never a fixed
  sleep followed by assumed success.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from urllib.parse import unquote, urlparse

from coldguard_backend.config import ColdGuardConfig

DB_ENV = "COLDGUARD_TEST_DATABASE_URL"
MQTT_HOST_ENV = "COLDGUARD_TEST_MQTT_HOST"


def has_test_db() -> bool:
    return bool(os.environ.get(DB_ENV))


def has_test_mqtt() -> bool:
    return bool(os.environ.get(MQTT_HOST_ENV))


def mqtt_params() -> dict[str, str | int]:
    return {
        "host": os.environ.get(MQTT_HOST_ENV, "localhost"),
        "port": int(os.environ.get("COLDGUARD_TEST_MQTT_PORT", "1883")),
        "device_user": os.environ.get(
            "COLDGUARD_TEST_MQTT_DEVICE_USER", "device-coldguard-001"
        ),
        "device_password": os.environ.get(
            "COLDGUARD_TEST_MQTT_DEVICE_PASSWORD", "device_dev_only"
        ),
        "backend_user": os.environ.get(
            "COLDGUARD_TEST_MQTT_BACKEND_USER", "backend-ingest"
        ),
        "backend_password": os.environ.get(
            "COLDGUARD_TEST_MQTT_BACKEND_PASSWORD", "backend_dev_only"
        ),
    }


def make_test_config(*, mqtt_user: str, mqtt_password: str) -> ColdGuardConfig:
    """Build a backend config from the test DB URL + test broker params."""
    parts = urlparse(os.environ[DB_ENV])
    params = mqtt_params()
    return ColdGuardConfig.load(
        env={
            "COLDGUARD_PROFILE": "integration",
            "POSTGRES_HOST": parts.hostname or "localhost",
            "POSTGRES_PORT": str(parts.port or 5432),
            "POSTGRES_DB": (parts.path or "/coldguard_test").lstrip("/"),
            "POSTGRES_USER": unquote(parts.username or "coldguard"),
            "POSTGRES_PASSWORD": unquote(parts.password or ""),
            "MQTT_HOST": str(params["host"]),
            "MQTT_PORT": str(params["port"]),
            "MQTT_USERNAME": mqtt_user,
            "MQTT_PASSWORD": mqtt_password,
        }
    )


def wait_for(
    condition: Callable[[], bool], *, timeout_s: float, interval_s: float = 0.25
) -> bool:
    """Poll ``condition`` until true or timeout. Returns the outcome."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval_s)
    return bool(condition())
