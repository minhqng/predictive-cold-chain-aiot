"""Configure backend MQTT clients with optional verified TLS and credentials."""

import ssl

import paho.mqtt.client as mqtt

from coldguard_backend.config import ColdGuardConfig


def configure_mqtt_client(client: mqtt.Client, config: ColdGuardConfig) -> None:
    if config.mqtt_tls_ca:
        if not config.mqtt_username or not config.mqtt_password:
            raise ValueError("the secured MQTT listener requires provisioned credentials")
        context = ssl.create_default_context(cafile=config.mqtt_tls_ca)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        client.tls_set_context(context)
    if config.mqtt_username:
        client.username_pw_set(config.mqtt_username, config.mqtt_password)
