"""Health endpoint test for the backend skeleton."""

from fastapi.testclient import TestClient

from coldguard_backend.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
