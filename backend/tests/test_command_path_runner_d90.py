"""Member D#90 alignment for the command-path runner (Phase 4, F2).

The locally available D#90 source (`origin/feat/d-w13-aiw-readiness`,
extracted read-only into a disposable pytest temp dir — nothing inside the
repository) adds ``LocalSafetyEvidence.clock_synchronized``: an
unsynchronized device clock must SAFETY_BLOCK new actuation instead of
admitting a probable-sync guess. These checks pin the runner's behavior
under BOTH contracts:

- base Member D: no clock field exists; an explicit claim is refused rather
  than silently dropped; the base happy path is untouched;
- D#90: the honest default is ``False`` — the recorded matrix behavior is
  SAFETY_BLOCKED with an unsynchronized clock, and only a clearly labeled
  SIMULATION_ONLY synchronized fixture reaches the accepted branch (no
  synchronized device evidence exists in this environment).
"""

import dataclasses
import io
import json
import pathlib
import subprocess
import sys
import tarfile
import textwrap

import pytest

from coldguard_backend import command_path_runner as cpr
from coldguard_backend.command_path_runner import (
    CommandPathError,
    d90_compatible_evidence,
    run_command_path,
)

from tests.test_command_path_runner import (  # same-suite helpers, base contracts
    COMMAND_ID,
    ISSUED_AT,
    _cfg,
    _evidence,
    _policy_input,
    _preemptive_cfg,
    _preemptive_input,
)

D90_REF = "origin/feat/d-w13-aiw-readiness"
WORKTREE_ROOT = pathlib.Path(__file__).resolve().parents[2]
D90_SCRIPT = textwrap.dedent(
    """
    import dataclasses, json
    from coldguard_control.commands import (
        AckStatus, CommandRequest, CoolingState, LocalSafetyEvidence, validate_command,
    )
    from coldguard_control.config import PolicyConfig
    from coldguard_control.types import DeviceMode, PolicyState, QualityState

    info = {
        "has_d90_field": "clock_synchronized"
        in {f.name for f in dataclasses.fields(LocalSafetyEvidence)},
    }
    evidence = LocalSafetyEvidence(
        device_mode=DeviceMode.ONLINE_NORMAL,
        policy_state=PolicyState.PREEMPTIVE_COOLING,
        thermal_quality=QualityState.VALID,
        thermal_age_s=10.0,
        fan_available=True,
        active_fault=False,
        hardware_safety_condition=False,
        clock_synchronized=False,  # the honest default; set True only in SIM mode
    )
    request = CommandRequest(
        schema_version=1,
        command_id="00000000-0000-4000-8000-0000000000d0",
        device_id="coldguard-001",
        action=CoolingState.ON,
        created_at=1762776000.0,
        expires_at=1762776120.0,
        authorized=True,
        duty=None,
    )
    cfg = PolicyConfig(
        policy_version="policy-v1",
        representative_source="TMAX",
        upper_on_c=6.5,
        lower_off_c=3.5,
        thermal_max_age_s=120.0,
        command_max_future_skew_s=300.0,
        broker_offline_grace_s=30.0,
        backend_state_max_age_s=60.0,
        safe_local_exit_min_stable_s=60.0,
        predictive_enabled=False,
    )
    decision = validate_command(
        request, evidence, cfg, now_s=1762776050.0,
        expected_device_id="coldguard-001", processed={},
    )
    print(json.dumps({
        "info": info,
        "status": decision.status.value,
        "reason": None if decision.reason_code is None else decision.reason_code.value,
        "detail": decision.detail,
        "checks_passed": list(decision.checks_passed),
        "accepted": decision.accepted,
    }))
    """
)


def _extract_d90(tmp_path: pathlib.Path) -> pathlib.Path | None:
    """Extract Member D#90's control package read-only into ``tmp_path``.

    ``git archive`` of a remote-tracking ref is a read-only operation and the
    extraction target is pytest's disposable temp dir outside the repository.
    Returns ``None`` (honest skip) when the ref is not available locally.
    """
    archive = subprocess.run(
        ["git", "archive", D90_REF, "control/src"],
        capture_output=True, cwd=WORKTREE_ROOT, timeout=60,
    )
    if archive.returncode != 0:
        # In the combined sandbox tree D#90 IS the merged control package
        # (verified SHA `da82109`), so the real source is already the tree's
        # own control/src — use it instead of extracting a separate copy.
        merged = WORKTREE_ROOT / "control" / "src"
        if (merged / "coldguard_control" / "commands.py").is_file():
            return merged
        return None
    target = tmp_path / "d90"
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(target, filter="data")
    return target / "control" / "src"


def _run_d90(script: str, tmp_path: pathlib.Path) -> dict:
    package_src = _extract_d90(tmp_path)
    if package_src is None:
        pytest.skip("D#90 source unavailable (feat/d-w13-aiw-readiness)")
    # scratch Member D#90 first in the resolution order; the runner module's
    # own worktree inserts happen after, and sys.modules already holds the
    # scratch copy, so the base matrix is never silently imported here.
    env = {"PYTHONPATH": str(package_src), "PYTHONHASHSEED": "0"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=120, env=env,
    )
    if result.returncode != 0:
        pytest.fail(f"D#90 subprocess failed: {result.stderr[-500:]}")
    return json.loads(result.stdout)


def test_base_contract_refuses_an_explicit_clock_claim():
    """A clock claim must never be silently dropped on the base matrix."""
    from coldguard_control.commands import LocalSafetyEvidence
    from coldguard_control.types import DeviceMode, PolicyState, QualityState

    base = LocalSafetyEvidence(
        device_mode=DeviceMode.ONLINE_NORMAL,
        policy_state=PolicyState.PREEMPTIVE_COOLING,
        thermal_quality=QualityState.VALID,
        thermal_age_s=10.0,
        fan_available=True,
    )
    if "clock_synchronized" in {f.name for f in dataclasses.fields(base)}:
        pytest.skip("the running matrix already carries the D#90 clock field")
    with pytest.raises(CommandPathError, match="BASE_D_HAS_NO_CLOCK_FIELD"):
        d90_compatible_evidence(base, clock_synchronized=False)


def test_unclaimed_clock_safety_blocks_under_d90():
    """Under the merged D#90 matrix, no explicit clock claim = SAFETY_BLOCKED."""
    outcome = run_command_path(
        _preemptive_input(),
        _preemptive_cfg(),
        _evidence(),
        command_id=COMMAND_ID,
        device_id="coldguard-001",
        issued_at=ISSUED_AT,
    )
    verification = outcome.command_verification
    assert verification["status"] == "SAFETY_BLOCKED"
    assert "not synchronized" in verification["detail"]
    assert verification["member_d_matrix"] == "d90-latest"


def test_d90_unsynchronized_clock_safety_blocks(tmp_path):
    """The actual D#90 member behavior, observed through its own source."""
    outcome = _run_d90(D90_SCRIPT, tmp_path)
    assert outcome["info"]["has_d90_field"] is True
    assert outcome["status"] == "SAFETY_BLOCKED"
    assert outcome["reason"] == "COMMAND_SAFETY_BLOCKED"
    assert outcome["accepted"] is False
    assert "not synchronized" in outcome["detail"]
    # The clock gate fires before the expiry check: an unsynchronized clock
    # is a safety block, not an expiry verdict.
    assert "expiry" not in outcome["checks_passed"]


def test_d90_accepted_branch_is_a_labeled_simulation_only_fixture(tmp_path):
    simulation = D90_SCRIPT.replace(
        "clock_synchronized=False,  # the honest default; set True only in SIM mode",
        "clock_synchronized=True,  # SIMULATION_ONLY fixture (no device evidence)",
    )
    outcome = _run_d90(simulation, tmp_path)
    assert outcome["status"] == "ACCEPTED"
    assert outcome["accepted"] is True
    assert "expiry" in outcome["checks_passed"]


def test_runner_helper_fresh_claim_matches_d90_semantics(tmp_path):
    """Rebuild through the real helper against the real D#90 matrix import."""
    package_src = _extract_d90(tmp_path)
    if package_src is None:
        pytest.skip("D#90_SOURCE_UNAVAILABLE")
    backend_src = pathlib.Path(cpr.__file__).resolve().parents[1]
    script = textwrap.dedent(
        """
        import sys
        sys.path[0:0] = [%r, %r]
        from coldguard_control.commands import LocalSafetyEvidence
        from coldguard_control.types import DeviceMode, PolicyState, QualityState
        from coldguard_backend.command_path_runner import d90_compatible_evidence

        evidence = LocalSafetyEvidence(
            device_mode=DeviceMode.ONLINE_NORMAL,
            policy_state=PolicyState.PREEMPTIVE_COOLING,
            thermal_quality=QualityState.VALID,
            thermal_age_s=10.0,
            fan_available=True,
        )
        rebuilt = d90_compatible_evidence(evidence, clock_synchronized=False)
        print(rebuilt.clock_synchronized)
        """
        % (str(package_src), str(backend_src)),
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr[-400:]
    assert result.stdout.strip() == "False"


def test_runner_full_path_under_d90_blocks_dispatch(tmp_path):
    """run_command_path under D#90 (scratch import) SAFETY_BLOCKs before dispatch."""
    package_src = _extract_d90(tmp_path)
    if package_src is None:
        pytest.skip("D#90_SOURCE_UNAVAILABLE")
    backend_src = pathlib.Path(cpr.__file__).resolve().parents[1]
    script = (
        "import sys\n"
        "print('D90-SCRATCH', flush=True)\n"
        "sys.path[0:0] = [%r, %r]\n"
        # Cache the scratch D#90 modules BEFORE importing the runner: the
        # runner inserts its own worktree control path at sys.path[0], which
        # would otherwise shadow D#90 with the base matrix.
        "from datetime import datetime, timezone\n"

        "from coldguard_control.commands import (\n"
        "    LocalSafetyEvidence,\n"
        "    validate_command,\n"
        ")\n"
        "from coldguard_control.policy import (\n"
        "    PolicyConfig,\n"
        "    PolicyInput,\n"
        "    PredictionView,\n"
        "    RemotePathView,\n"
        "    ThermalView,\n"
        ")\n"
        "from coldguard_control.types import (\n"
        "    CoolingState,\n"
        "    DeviceMode,\n"
        "    ModelHealth,\n"
        "    PolicyState,\n"
        "    QualityState,\n"
        ")\n"
        "print('control from', sys.modules['coldguard_control.commands'].__file__, flush=True)\n"

        "from coldguard_backend.command_path_runner import run_command_path\n"

        "cfg = PolicyConfig(\n"
        "    policy_version='policy-v1',\n"
        "    representative_source='TMAX',\n"
        "    upper_on_c=6.5,\n"
        "    lower_off_c=3.5,\n"
        "    thermal_max_age_s=120.0,\n"
        "    command_max_future_skew_s=300.0,\n"
        "    broker_offline_grace_s=30.0,\n"
        "    backend_state_max_age_s=60.0,\n"
        "    safe_local_exit_min_stable_s=60.0,\n"
        "    predictive_enabled=False,\n"
        ")\n"
        "policy_input = PolicyInput(\n"
        "    device_mode=DeviceMode.ONLINE_NORMAL,\n"
        "    thermal=ThermalView(\n"
        "        quality=QualityState.VALID,\n"
        "        t_representative_c=7.2,\n"
        "        age_s=10.0,\n"
        "    ),\n"
        "    applied_cooling=CoolingState.OFF,\n"
        "    remote=RemotePathView(\n"
        "        broker_connected=True,\n"
        "        broker_offline_s=0.0,\n"
        "        backend_state_synced=True,\n"
        "        backend_state_age_s=5.0,\n"
        "        state_sync_trusted=True,\n"
        "        remote_command_path_trusted=True,\n"
        "        network_stable_s=600.0,\n"
        "        stale_command_pending=False,\n"
        "    ),\n"
        "    current_state=PolicyState.NORMAL,\n"
        "    fan_available=True,\n"
        "    electrical_quality=QualityState.VALID,\n"
        "    door_state='CLOSED',\n"
        "    prediction=None,\n"
        ")\n"
        "evidence = LocalSafetyEvidence(\n"
        "    device_mode=DeviceMode.ONLINE_NORMAL,\n"
        "    policy_state=PolicyState.PREEMPTIVE_COOLING,\n"
        "    thermal_quality=QualityState.VALID,\n"
        "    thermal_age_s=10.0,\n"
        "    fan_available=True,\n"
        "    clock_synchronized=False,\n"
        ")\n"
        "issued = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)\n"
        "outcome = run_command_path(\n"
        "    policy_input,\n"
        "    cfg,\n"
        "    evidence,\n"
        "    command_id='00000000-0000-4000-8000-000000000010b',\n"
        "    device_id='coldguard-001',\n"
        "    issued_at=issued,\n"
        ")\n"
        "verification = outcome.command_verification\n"
        "print(verification.get('status'), flush=True)\n"
        "print(verification.get('member_d_matrix', ''), flush=True)\n"
        % (str(package_src), str(backend_src))
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, (result.returncode, result.stderr[-1200:])
    lines = [line for line in result.stdout.strip().splitlines() if line]
    assert lines, (result.returncode, repr(result.stdout[:200]), result.stderr[-500:])
    assert len(lines) >= 2 and "SAFETY_BLOCKED" in lines[-2], repr(
        (lines, result.stdout[:400], result.stderr[-300:])
    )
    assert lines[-1] == "d90-latest"
