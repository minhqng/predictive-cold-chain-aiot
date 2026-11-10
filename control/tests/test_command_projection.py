import json
import importlib.util
from pathlib import Path

import pytest

from coldguard_control.commands import CommandSchemaError
from coldguard_control.types import CoolingState


FIXTURE = Path(__file__).resolve().parents[2] / "backend" / "fixtures" / "command_v0.json"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "command_projection.py"
SPEC = importlib.util.spec_from_file_location("command_projection", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
project_canonical_command = MODULE.project_canonical_command


def _payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_c_fixture_projects_to_d_validator_input():
    command = project_canonical_command(_payload(), authorized=True)
    assert command.action is CoolingState.ON
    assert command.duty == 1.0
    assert command.expires_at - command.created_at == 60.0
    assert command.retain is False


@pytest.mark.parametrize("field", ["controller_id", "policy_version", "reason_code"])
def test_missing_c_provenance_is_rejected(field):
    payload = _payload()
    payload.pop(field)
    with pytest.raises(CommandSchemaError, match=field):
        project_canonical_command(payload, authorized=True)


def test_naive_clock_or_string_duty_is_rejected():
    payload = _payload()
    payload["created_at"] = "2026-10-14T07:00:00"
    with pytest.raises(CommandSchemaError, match="UTC"):
        project_canonical_command(payload, authorized=True)
    payload = _payload()
    payload["action"]["duty"] = "1.0"
    with pytest.raises(CommandSchemaError, match="numeric"):
        project_canonical_command(payload, authorized=True)
