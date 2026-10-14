"""Configuration profile behavior (C-W01-05).

Defects detected: an unknown profile silently accepted, an invalid port
accepted, credentials leaking through diagnostics, or precedence between
explicit argument / environment / default breaking.
"""

import pytest

from coldguard_backend.config import PROFILES, ColdGuardConfig


def test_default_profile_is_dev_without_environment():
    config = ColdGuardConfig.load(env={})
    assert config.profile == "dev"
    assert config.postgres_host == "localhost"
    assert config.mqtt_host == "localhost"


def test_each_canonical_profile_loads():
    for profile in PROFILES:
        assert ColdGuardConfig.load(env={"COLDGUARD_PROFILE": profile}).profile == profile


def test_unknown_profile_rejected():
    with pytest.raises(ValueError, match="unknown COLDGUARD_PROFILE"):
        ColdGuardConfig.load(env={"COLDGUARD_PROFILE": "prod"})


def test_explicit_profile_beats_environment():
    config = ColdGuardConfig.load(
        profile="integration", env={"COLDGUARD_PROFILE": "dev"}
    )
    assert config.profile == "integration"


def test_invalid_port_rejected():
    with pytest.raises(ValueError, match="POSTGRES_PORT"):
        ColdGuardConfig.load(env={"POSTGRES_PORT": "not-a-port"})
    with pytest.raises(ValueError, match="MQTT_PORT"):
        ColdGuardConfig.load(env={"MQTT_PORT": "99999"})


def test_database_url_uses_psycopg_dialect():
    config = ColdGuardConfig.load(env={})
    assert config.database_url.startswith("postgresql+psycopg://")


def test_safe_summary_redacts_password():
    config = ColdGuardConfig.load(env={"POSTGRES_PASSWORD": "s3cret-value"})
    summary = config.safe_summary()
    assert "s3cret-value" not in str(summary)
    assert "redacted" in summary["postgres"]


def test_mqtt_credentials_default_to_empty_and_load_from_env():
    assert ColdGuardConfig.load(env={}).mqtt_username == ""
    config = ColdGuardConfig.load(
        env={"MQTT_USERNAME": "backend-ingest", "MQTT_PASSWORD": "mqtt-s3cret"}
    )
    assert config.mqtt_username == "backend-ingest"
    assert config.mqtt_password == "mqtt-s3cret"


def test_safe_summary_redacts_mqtt_password_but_names_principal():
    config = ColdGuardConfig.load(
        env={"MQTT_USERNAME": "backend-ingest", "MQTT_PASSWORD": "mqtt-s3cret"}
    )
    summary = config.safe_summary()
    assert "mqtt-s3cret" not in str(summary)
    assert "backend-ingest" in summary["mqtt"]
