"""Owner-owned D→C→A command-path composition runner (W06/W13 prerequisite).

Composes the immutable member implementations into one executable offline
path, in the Doc 02 section 33 order, without modifying any member source:

    Member D control intent (evaluate_policy)
      -> Member D command validation (validate_command)
      -> Member C Command envelope (Doc 02 section 28.1)
      -> owner bridge dispatch (command_ack_bridge.dispatch_command)
      -> Member A device serial record (firmware/main/cg_command.c surface)
      -> device boundary acknowledgment (Member A's committed W06
         ack-fixture.json records; the compiled W06 harness needs a native
         toolchain that is not available in this environment)
      -> owner bridge ingest (command_ack_bridge.ingest_ack)
      -> Member C CommandAck envelope (Doc 02 section 32.3 shape)
      -> observed command lifecycle (Member A's firmware/tools/
         cg_command_trace.py stage promotion: COMMAND_SEEN -> DEVICE_ACK ->
         APPLIED_STATE -> ELECTRICAL_VERIFIED -> THERMAL_VERIFIED).

Authority and separation of claims (never conflated here):

- The D policy decision is a *desired* intent, never an execution
  (coldguard_control PolicyDecision "never an actuator command").
- The D command decision separates *desired* from *accepted*; a command that
  fails any matrix check is never dispatched, and a duplicate returns the
  canonical status without re-actuation (Doc 02 sections 31.4, 32.1).
- An ACK is protocol evidence only; the lifecycle ledger is produced by
  Member A's own trace tool, which refuses to promote a stage without
  evidence, so ACK alone blocks at APPLIED_STATE (Doc 02 sections 32.2, 33).
- The device's clock-synchronization safety gate (cg_command.c
  EPOCH_UNSYNCHRONIZED) remains the fail-closed authority; this runner never
  fabricates a device clock, an ack_time, or a receipt-time TTL.
- Member D's matrix version changes the accepted-command semantics: D#90's
  ``LocalSafetyEvidence.clock_synchronized`` SAFETY_BLOCKs new actuation for
  an unsynchronized clock; the runner supports both contracts explicitly and
  records which matrix produced a report (``member_d_matrix`` field).
- ``device_mode`` (Member A) and ``PolicyState`` (Member D) are different
  vocabularies; the runner records both and never maps one into the other.

Import layout mirrors ``backend/scripts/serial_gateway.py``: the checkout root
is added to ``sys.path`` so Member A's committed ``firmware.tools`` parsers and
Member D's ``coldguard_control`` package are used directly, unmodified.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from dataclasses import dataclass, field, replace
import dataclasses
from datetime import datetime, timedelta, timezone

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    # Member A's committed firmware tools (cg_command_trace, cg_telemetry_schema).
    sys.path.insert(0, str(_ROOT))
_CONTROL_SRC = _ROOT / "control" / "src"
if _CONTROL_SRC.is_dir() and str(_CONTROL_SRC) not in sys.path:
    # Member D's committed control package.
    sys.path.insert(0, str(_CONTROL_SRC))

from coldguard_control.commands import (  # noqa: E402
    AckStatus,
    CommandDecision,
    CommandRequest,
    CoolingState,
    LocalSafetyEvidence,
    validate_command,
)
from coldguard_control.policy import PolicyConfig, PolicyInput, evaluate_policy  # noqa: E402

from firmware.tools import cg_command_trace  # noqa: E402

from .command_ack_bridge import (
    CommandAckCorrelationError,
    dispatch_command,
    ingest_ack,
)
from .command_translation import CommandTranslationError
from .contracts import Command

DEFAULT_FIXTURE_PATH = (
    _ROOT / "evidence" / "A" / "W06" / "ack-fixture.json"
)
# The W06 harness demo capture ships Member A's real schema-3 telemetry line
# shape; Member A's own trace tests reuse it as a template the same way.
DEMO_CAPTURE_PATH = _ROOT / "evidence" / "A" / "W06" / "demo-command-capture.log"

# A's W06 harness fixture uses reason=NONE for "no specific verdict";
# Doc 02 section 32.1 reason vocabulary. An D decision whose reason_code is
# None maps to this existing device vocabulary value, never to an invented one.
REASON_NONE = "NONE"

COMMAND_TTL_S = 120.0

# Member D#90 (`feat/d-w13-aiw-readiness`) adds
# ``LocalSafetyEvidence.clock_synchronized`` (Doc 02 section 31.1): absolute
# command expiry is only evaluable when the device clock is explicitly known
# to be synchronized, so an unsynchronized clock SAFETY_BLOCKs the command
# instead of admitting it on a probable-sync guess. The base Member D matrix
# pre-dates that field. This runner supports both contracts explicitly: an
# explicit clock claim is refused on the base contract rather than silently
# dropped, and the honest default under D#90 is False — absence is never
# "probably synchronized".
_D90_CLOCK_FIELD = "clock_synchronized"
_HAS_D90_CLOCK = _D90_CLOCK_FIELD in {
    f.name for f in dataclasses.fields(LocalSafetyEvidence)
}


def d90_compatible_evidence(
    evidence: LocalSafetyEvidence,
    *,
    clock_synchronized: bool,
) -> LocalSafetyEvidence:
    """Rebuild ``evidence`` with the stated clock claim under D#90's contract.

    On the base Member D matrix the field does not exist; the caller returns
    the evidence unchanged only through this function's guard — an explicit
    clock claim against the base contract raises instead (a claim must never
    be silently dropped). No default ever sets ``clock_synchronized=True``.
    """
    if not _HAS_D90_CLOCK:
        raise CommandPathError(
            "BASE_D_HAS_NO_CLOCK_FIELD: the running Member D contract cannot "
            "record clock_synchronized; the claim is refused rather than "
            "silently dropped"
        )
    return replace(evidence, **{_D90_CLOCK_FIELD: bool(clock_synchronized)})


class CommandPathError(ValueError):
    """The command path cannot run without inventing a contract value."""


@dataclass
class FixtureAckDevice:
    """Device boundary standing in for the compiled W06 harness.

    Replays Member A's *committed* acknowledgment fixture records
    (evidence/A/W06/ack-fixture.json), re-targeted to the dispatched
    command/device identity. It is a boundary fixture, not a firmware
    execution: device admission semantics (expiry, safety, dedup) stay the
    device's authority, and the selected scenario is recorded in the report
    so a fixture ACK is never mistaken for live firmware behavior.
    """

    scenario: str
    fixtures_path: pathlib.Path = DEFAULT_FIXTURE_PATH

    def __post_init__(self) -> None:
        data = json.loads(self.fixtures_path.read_text(encoding="utf-8"))
        fixtures = data["fixtures"]
        if self.scenario not in fixtures:
            raise CommandPathError(
                f"UNKNOWN_SCENARIO: {self.scenario!r} not in "
                f"{sorted(fixtures)}"
            )
        self._fields = dict(fixtures[self.scenario]["fields"])
        self.provenance = {
            "kind": "fixture_ack_device",
            "source": str(self.fixtures_path.relative_to(_ROOT)),
            "scenario": self.scenario,
            "firmware_executed": False,
        }

    def __call__(self, record: str) -> str:
        fields = dict(self._fields)
        for token in record.split():
            key, _, value = token.partition("=")
            if key == "command_id":
                fields["command_id"] = value
            elif key == "device_id":
                fields["device_id"] = value
        return "#CG CMDACK " + " ".join(f"{k}={v}" for k, v in fields.items())


def applied_frame_template() -> str:
    """One committed harness telemetry line, used as the frame template."""
    for line in DEMO_CAPTURE_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith(cg_command_trace.telemetry_schema.PREFIX):
            return line
    raise CommandPathError(
        f"NO_TEMPLATE: {DEMO_CAPTURE_PATH.name} carries no telemetry line"
    )


def synthetic_applied_frame(
    template: str,
    *,
    boot_id: str,
    uptime_ms: int,
    cooling_applied: str,
    current_status: str = "OK",
    current_a: str = "10.5",
    t_inside_status: str = "OK",
    t_inside_c: str,
) -> str:
    """Re-target one committed harness telemetry line (clearly synthetic).

    Only the fields the lifecycle trace consumes are substituted; every other
    field keeps the committed harness evidence shape.
    """
    line = re.sub(r"boot_id=\S+", f"boot_id={boot_id}", template)
    line = re.sub(r"uptime_ms=\d+", f"uptime_ms={uptime_ms}", line)
    line = re.sub(r"cooling_applied=\S+", f"cooling_applied={cooling_applied}", line)
    line = re.sub(r"current_status=\S+", f"current_status={current_status}", line)
    line = re.sub(r"current_a=\S+", f"current_a={current_a}", line)
    line = re.sub(
        r"t_inside_status=\S+", f"t_inside_status={t_inside_status}", line
    )
    line = re.sub(r"t_inside_c=\S+", f"t_inside_c={t_inside_c}", line)
    return line


@dataclass
class CommandPathOutcome:
    """One offline command-path exchange, claims kept strictly separated."""

    desired_decision: dict
    command_verification: dict
    dispatched_record: str | None = None
    ack_command_envelope: dict | None = None
    lifecycle_trace: dict = field(default_factory=dict)
    device_provenance: dict = field(default_factory=dict)
    post_ack_frame_provenance: str = "none"
    blocked_at: str | None = None

    @property
    def outcome_status(self) -> str:
        """Path-level status using the audit's separated claims vocabulary."""
        if self.ack_command_envelope is None:
            return self.command_verification.get("outcome", "INTENT_ONLY")
        if self.blocked_at is not None:
            return f"ACK_RECEIVED_BLOCKED_AT_{self.blocked_at}"
        return "OBSERVED_TRACE_COMPLETE"


def _decision_row(decision: CommandDecision) -> dict:
    row = {
        "command_id": decision.command_id,
        "status": decision.status.value,
        "reason_code": None if decision.reason_code is None else decision.reason_code.value,
        "actuation_intent": decision.actuation_intent.value,
        "detail": decision.detail,
        "checks_passed": list(decision.checks_passed),
        "accepted": decision.accepted,
    }
    if decision.canonical_status is not None:
        row["canonical_status"] = decision.canonical_status.value
    return row


def _policy_row(pi: PolicyInput, cfg: PolicyConfig) -> dict:
    decision = evaluate_policy(pi, cfg)
    return decision, {
        "policy_state": decision.state.value,
        "actuation_intent": decision.actuation_intent.value,
        "controller_id": decision.controller_id.value,
        "reason_code": None if decision.reason_code is None else decision.reason_code.value,
        "policy_version": decision.policy_version,
        "predictive_blocked": decision.predictive_blocked,
        "degraded_sensing": decision.degraded_sensing,
        "detail": decision.reason_detail,
        "notes": list(decision.notes),
        "device_mode": pi.device_mode.value,
    }


def run_command_path(
    policy_input: PolicyInput,
    cfg: PolicyConfig,
    evidence: LocalSafetyEvidence,
    *,
    command_id: str,
    device_id: str,
    expected_device_id: str | None = None,
    issued_at: datetime,
    validated_at: datetime | None = None,
    ttl_s: float = COMMAND_TTL_S,
    processed: dict[str, AckStatus] | None = None,
    device_boundary: FixtureAckDevice | None = None,
    post_ack_frames: list[str] | None = None,
    clock_synchronized: bool | None = None,
) -> CommandPathOutcome:
    """Execute one full D→C→A→C command/ACK exchange, offline and fail-closed.

    ``issued_at`` must be timezone-aware UTC; it feeds both Member D's epoch
    validation and Member C's envelope timestamps from the same instant.
    ``device_boundary`` defaults to Member A's committed fixture replay for
    the ``synchronized-accepted`` scenario; pass another scenario to exercise
    the device's refusal verdicts through the real bridge.

    ``clock_synchronized`` records the device-clock claim for Member D#90's
    contract (Doc 02 section 31.1): ``None`` keeps the caller-supplied
    evidence exactly as given; an explicit bool is version-guarded — on the
    base matrix the claim cannot be recorded and is refused, under D#90 the
    evidence is rebuilt with the stated claim. ``False`` SAFETY_BLOCKs new
    actuation; nothing in this runner ever defaults the claim to ``True``.
    """
    if issued_at.tzinfo is None or (validated_at is not None and validated_at.tzinfo is None):
        raise CommandPathError(
            "NAIVE_TIMESTAMP: issued_at/validated_at must be timezone-aware "
            "UTC; the runner refuses to invent a timezone for the command path"
        )
    validation_time = validated_at or issued_at

    decision, desired_row = _policy_row(policy_input, cfg)

    if decision.actuation_intent.value == "HOLD":
        return CommandPathOutcome(
            desired_decision=desired_row,
            command_verification={
                "outcome": "INTENT_ONLY",
                "detail": "policy intent is HOLD; no command is issued",
            },
        )

    if clock_synchronized is not None:
        evidence = d90_compatible_evidence(
            evidence, clock_synchronized=clock_synchronized
        )

    now_s = validation_time.timestamp()
    request = CommandRequest(
        schema_version=1,
        command_id=command_id,
        device_id=device_id,
        action=CoolingState[decision.actuation_intent.value],
        created_at=issued_at.timestamp(),
        expires_at=issued_at.timestamp() + ttl_s,
        authorized=True,
        duty=None,
    )
    verification = validate_command(
        request,
        evidence,
        cfg,
        now_s=now_s,
        expected_device_id=expected_device_id or device_id,
        processed=processed or {},
    )
    verification_row = _decision_row(verification)
    verification_row["validated_at"] = validation_time.isoformat()
    verification_row["member_d_matrix"] = (
        "d90-latest" if _HAS_D90_CLOCK else "base"
    )
    verification_row["outcome"] = (
        "COMMAND_ACCEPTED" if verification.accepted else "COMMAND_REFUSED"
    )
    if not verification.accepted:
        return CommandPathOutcome(
            desired_decision=desired_row,
            command_verification=verification_row,
        )

    boundary = device_boundary or FixtureAckDevice("synchronized-accepted")
    command = Command(
        schema_version=1,
        command_id=command_id,
        device_id=device_id,
        created_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_s),
        controller_id=decision.controller_id.value,
        policy_version=decision.policy_version,
        reason_code=(
            REASON_NONE if decision.reason_code is None else decision.reason_code.value
        ),
        action={"cooling": request.action.value, "duty": None},
    )
    try:
        record = dispatch_command(command)
    except CommandTranslationError as exc:
        raise CommandPathError(f"DISPATCH_FAILED: {exc}") from exc
    try:
        ack_envelope = ingest_ack(boundary(record), expected_command_id=command_id)
    except CommandAckCorrelationError as exc:
        raise CommandPathError(str(exc)) from exc

    capture_lines = [record, boundary(record), *(post_ack_frames or [])]
    commands = cg_command_trace.parse_capture(capture_lines)
    rows = cg_command_trace.evaluate(commands)
    summary = cg_command_trace.summarize(commands, rows)
    trace = {"summary": summary, "commands": rows, "stages": list(cg_command_trace.STAGES)}
    blocked_at = next((row["blocked_at"] for row in rows if row["blocked_at"] is not None), None)

    return CommandPathOutcome(
        desired_decision=desired_row,
        command_verification=verification_row,
        dispatched_record=record,
        ack_command_envelope=ack_envelope,
        lifecycle_trace=trace,
        device_provenance=boundary.provenance,
        post_ack_frame_provenance=(
            "synthetic template from " + DEMO_CAPTURE_PATH.relative_to(_ROOT).as_posix()
            if post_ack_frames
            else "none: no applied-state evidence exists in this exchange"
        ),
        blocked_at=blocked_at,
    )


def main(argv: list[str] | None = None) -> int:
    """Demonstration exchange: D PREEMPTIVE_COOLING intent through the path.

    Runs the real members' code offline and prints the separated-claims
    report. The exit code is 0 even when the path legitimately blocks at a
    lifecycle stage: a blocked-at report is a correct answer, not a failure.
    """
    import argparse

    from coldguard_control.types import (
        CoolingState as DCoolingState,
        DeviceMode,
        ModelHealth,
        PolicyState,
        QualityState,
    )
    from coldguard_control.policy import (
        PredictionView,
        RemotePathView,
        ThermalView,
    )

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", dest="json_out", type=pathlib.Path)
    parser.add_argument("--scenario", default="synchronized-accepted")
    parser.add_argument(
        "--applied-frames", action="store_true",
        help="append synthetic applied-state frames so the trace may promote",
    )
    args = parser.parse_args(argv)

    issued_at = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
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
        predictive_enabled=True,
        watch_threshold=0.6,
        preemptive_threshold=0.8,
        persistence_required_s=60.0,
        prediction_max_age_s=600.0,
    )
    policy_input = PolicyInput(
        device_mode=DeviceMode.ONLINE_NORMAL,
        thermal=ThermalView(
            quality=QualityState.VALID, t_representative_c=7.2, age_s=10.0
        ),
        applied_cooling=DCoolingState.OFF,
        remote=RemotePathView(
            broker_connected=True,
            broker_offline_s=0.0,
            backend_state_synced=True,
            backend_state_age_s=5.0,
            state_sync_trusted=True,
            remote_command_path_trusted=True,
            network_stable_s=600.0,
            stale_command_pending=False,
        ),
        current_state=PolicyState.PREEMPTIVE_COOLING,
        fan_available=True,
        electrical_quality=QualityState.VALID,
        door_state="CLOSED",
        prediction=PredictionView(
            health=ModelHealth.READY,
            model_version="m-v1",
            feature_version="f-v1",
            risk_score=0.9,
            age_s=5.0,
            horizon_s=300.0,
            above_preemptive_s=90.0,
        ),
    )
    # Member D#90's contract adds the device-clock claim; this offline
    # environment has no synchronized-clock evidence, so under D#90 the
    # honest construction carries clock_synchronized=False and the matrix
    # must SAFETY_BLOCK new actuation. On the base matrix the field does not
    # exist and the base verdicts stand untouched.
    evidence_kwargs = dict(
        device_mode=DeviceMode.ONLINE_NORMAL,
        policy_state=PolicyState.PREEMPTIVE_COOLING,
        thermal_quality=QualityState.VALID,
        thermal_age_s=10.0,
        fan_available=True,
        active_fault=False,
        hardware_safety_condition=False,
    )
    if _HAS_D90_CLOCK:
        evidence_kwargs["clock_synchronized"] = False
    evidence = LocalSafetyEvidence(**evidence_kwargs)
    boundary = FixtureAckDevice(args.scenario)
    frames = None
    if args.applied_frames:
        template = applied_frame_template()
        boot = boundary._fields["boot_id"]
        frames = [
            synthetic_applied_frame(
                template,
                boot_id=boot,
                uptime_ms=int(boundary._fields["uptime_ms"]) + 1000,
                cooling_applied="ON",
                current_a="10.5",
                t_inside_c="7.2",
            ),
            synthetic_applied_frame(
                template,
                boot_id=boot,
                uptime_ms=int(boundary._fields["uptime_ms"]) + 2000,
                cooling_applied="ON",
                current_a="10.6",
                t_inside_c="6.8",
            ),
            synthetic_applied_frame(
                template,
                boot_id=boot,
                uptime_ms=int(boundary._fields["uptime_ms"]) + 3000,
                cooling_applied="ON",
                current_a="10.7",
                t_inside_c="6.7",
            ),
        ]
    try:
        outcome = run_command_path(
            policy_input,
            cfg,
            evidence,
            command_id="00000000-0000-4000-8000-00000000000b",
            device_id="coldguard-001",
            issued_at=issued_at,
            device_boundary=boundary,
            post_ack_frames=frames,
        )
    except (CommandPathError, CommandTranslationError) as exc:
        print(f"command path refused: {exc}")
        return 1
    report = {
        "outcome_status": outcome.outcome_status,
        "desired": outcome.desired_decision,
        "accepted": outcome.command_verification,
        "dispatched_record": outcome.dispatched_record,
        "ack_envelope": outcome.ack_command_envelope,
        "lifecycle": outcome.lifecycle_trace,
        "device_provenance": outcome.device_provenance,
        "post_ack_frame_provenance": outcome.post_ack_frame_provenance,
        "blocked_at": outcome.blocked_at,
        "member_d_matrix": (
            "d90-latest" if _HAS_D90_CLOCK else "base"
        ),
        "claims_note": (
            "desired (D policy) is not accepted (D matrix); accepted is not an "
            "ACK; an ACK is not an applied state; applied/electrical/thermal "
            "stages come from Member A's cg_command_trace promotion, never "
            "assumed; under Member D#90 an unsynchronized device clock "
            "SAFETY_BLOCKs new actuation (Doc 02 section 31.1)"
        ),
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
