"""Release authority boundaries for the dashboard desired-setpoint path.

These exercise the real HTTP entry path (the delivered Handler on an ephemeral
loopback port) with an env-provisioned operator token monkeypatched in. They
prove the setpoint is an authenticated desired-state policy input that never
grants actuation: the dashboard has no ARM/GRANT/START command path, and every
non-setpoint POST stays read-only (405). No hardware or production resource is
touched.
"""

import http.server
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE / "backend"))

import pytest  # noqa: E402

from integration import leader_dashboard_server as server  # noqa: E402

TOKEN = "test-operator-token-0123456789abcdef"  # dummy test credential, not a secret


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    setpoint_file = tmp_path / "setpoint-desired.json"
    monkeypatch.setattr(server, "SETPOINT_FILE", setpoint_file)
    monkeypatch.setattr(server, "OPERATOR_TOKEN", TOKEN)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base, setpoint_file
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post(base, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else b""
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except ValueError:
            return exc.code, {}


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as response:
        return response.status, json.loads(response.read())


def test_unprovisioned_token_fails_closed(dashboard, monkeypatch):
    base, path = dashboard
    monkeypatch.setattr(server, "OPERATOR_TOKEN", "")
    code, _ = _post(base, "/api/leader/setpoint", {"setpoint_c": 22}, TOKEN)
    assert code == 503
    assert not path.exists()


def test_missing_auth_rejected(dashboard):
    base, path = dashboard
    code, _ = _post(base, "/api/leader/setpoint", {"setpoint_c": 22})
    assert code == 401
    assert not path.exists()


def test_wrong_token_rejected(dashboard):
    base, path = dashboard
    code, _ = _post(base, "/api/leader/setpoint", {"setpoint_c": 22}, "wrong-token")
    assert code == 401
    assert not path.exists()


def test_valid_setpoint_writes_desired_state_only(dashboard):
    base, path = dashboard
    code, body = _post(base, "/api/leader/setpoint", {"setpoint_c": 21.5}, TOKEN)
    assert code == 200
    assert body["ok"] is True
    assert body["setpoint_c"] == 21.5
    assert body["actuation"] == "NONE"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["setpoint_c"] == 21.5
    assert record["source"] == "OPERATOR"
    # Desired state only: no arm/grant/boot/command authority is persisted.
    assert not ({"arm", "armed", "grant", "boot_id", "token", "command"} & record.keys())


def test_out_of_range_rejected(dashboard):
    base, path = dashboard
    code, _ = _post(base, "/api/leader/setpoint", {"setpoint_c": 100}, TOKEN)
    assert code == 400
    assert not path.exists()


def test_non_number_rejected(dashboard):
    base, path = dashboard
    code, _ = _post(base, "/api/leader/setpoint", {"setpoint_c": "abc"}, TOKEN)
    assert code == 400
    assert not path.exists()


def test_get_setpoint_is_read_only_desired_state(dashboard):
    base, _ = dashboard
    code, body = _get(base, "/api/leader/setpoint")
    assert code == 200
    assert body["setpoint_c"] is None
    assert body["actuation"] == "NONE"
    _post(base, "/api/leader/setpoint", {"setpoint_c": 23}, TOKEN)
    code, body = _get(base, "/api/leader/setpoint")
    assert code == 200
    assert body["setpoint_c"] == 23
    assert body["source"] == "OPERATOR_DESIRED"


def test_arm_and_legacy_ai_routes_fail_closed(dashboard):
    base, path = dashboard
    # No ARM/GRANT/START command path exists on the dashboard: every non-setpoint
    # POST (including the legacy AI demo routes) is rejected read-only.
    for route in ("/api/leader/ai/arm", "/api/leader/ai/setpoint", "/api/leader/arm",
                  "/api/leader/grant", "/api/leader/start"):
        code, _ = _post(base, route, {"setpoint_c": 22}, TOKEN)
        assert code == 405, route
    assert not path.exists()