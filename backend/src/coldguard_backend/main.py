"""ColdGuard backend application entry point.

Endpoints: GET /health (liveness only). The MQTT ingestion consumer
(C-W02-03) runs in this same process via ``lifespan`` when
``COLDGUARD_MQTT_INGEST`` is truthy; one process, one consumer, no
second microservice for the network loop. No twin, command, prediction
or realtime authority exists yet; those start in later slices.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

log = logging.getLogger(__name__)

_STARTUP_RETRIES = int(os.environ.get("COLDGUARD_MQTT_STARTUP_RETRIES", "12"))
_STARTUP_RETRY_DELAY_S = float(os.environ.get("COLDGUARD_MQTT_STARTUP_RETRY_S", "5"))


def _ingest_enabled() -> bool:
    return os.environ.get("COLDGUARD_MQTT_INGEST", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _start_consumer():
    """Start the ingestion consumer with bounded broker-readiness retries.

    Retries cover only unreachable/unanswered brokers (Compose start
    ordering): each attempt is logged and the bound keeps a genuinely
    dead broker a loud startup failure. Refused credentials
    (ConnectionError) fail immediately — retrying those would only
    hammer the broker and hide a provisioning mistake.
    """
    import time

    from coldguard_backend.config import ColdGuardConfig
    from coldguard_backend.mqtt_consumer import MqttIngestConsumer

    config = ColdGuardConfig.load()
    consumer = MqttIngestConsumer.from_config(config)
    attempt = 0
    while True:
        attempt += 1
        try:
            consumer.start()
            return consumer
        except ConnectionError:
            raise
        except TimeoutError as exc:
            if attempt > _STARTUP_RETRIES:
                raise
            log.warning(
                "mqtt broker not ready (attempt %d/%d): %s",
                attempt,
                _STARTUP_RETRIES,
                exc,
            )
            time.sleep(_STARTUP_RETRY_DELAY_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = None
    if _ingest_enabled():
        consumer = _start_consumer()
        log.info("mqtt ingestion consumer started")
    app.state.mqtt_consumer = consumer
    try:
        yield
    finally:
        if consumer is not None:
            consumer.stop()
            log.info("mqtt ingestion consumer stopped")


app = FastAPI(title="ColdGuard Backend", lifespan=lifespan)
app.state.mqtt_consumer = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
