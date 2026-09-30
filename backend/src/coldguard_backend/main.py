"""ColdGuard backend application entry point.

Only endpoint: GET /health. MQTT, database, twin, commands,
predictions, auth, and realtime belong to later slices.
"""

from fastapi import FastAPI

app = FastAPI(title="ColdGuard Backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
