"""ColdGuard W11 S4: safe actuation-response fault, three lanes kept apart.

docs/05A §20 A-W11-01 wants S4 created **in software** - a test mode that
intentionally refuses or blocks actuation while keeping protocol visibility -
and explicitly forbids shorting a branch, bypassing the fuse or damaging the
TEC. A-W11-02 then wants the evidence triple:

```text
command/intention | applied state | PZEM no-active-response | thermal non-response
```

which together prove ``command != electrical effect``.

Those three are different claims about three different instruments, and the only
way to prove the inequality is to refuse to let one answer for another. So every
lane in a trace carries its own ``source`` and this module raises
``PromotionError`` if any lane's source is ``INFERRED_FROM_INTENT``. A trace that
derives "it happened" from "it was asked" is not an S4 record; it is the exact
confusion S4 exists to detect. Refusals are treated the same way: a command that
ended in ``REJECTED``/``EXPIRED``/``SAFETY_BLOCKED``/``INVALID_STATE``/
``OUT_OF_RANGE`` may never appear with an applied action, and
``DUPLICATE_CANONICAL`` may never appear with a *second* application, because
docs/02 §30.1 forbids a replay applying again even when the label is correct.

What is genuinely real here, and what is not:

* **Real, from the committed capture.** The applied/requested/readback lanes are
  separate in physical frames: all 600 active frames of
  ``evidence/A/W04/tec-cooling-response-600s.csv`` report
  ``pwm_req_permille=1000`` with ``pwm_applied_permille=999`` and
  ``pwm_readback_permille=999``. A commanded 1000 was applied as 999 and read
  back as 999 - three distinct instruments, three distinct numbers, no inference.
* **Real, and exactly the shape S4 looks for.** Frame seq 227 is ``state=COOLING``
  with applied duty 999 and ``current_a=0.0``; frames seq 827-828 are
  ``state=COOLDOWN`` with ``pwm_req_permille=0`` and applied duty 0 while
  ``current_a`` still reads 7.15 A then 0.56 A. Both are command/electrical
  disagreements in physical data.
* **Not real, and this is the blocking gap.** The current values above carry no
  producer qualification: ``current_status`` and ``voltage_status`` are empty
  strings in all 957 rows and there is no ``power_status`` column at all. Under
  the shipped rule - a number is usable only when its status is ``OK`` - these
  are *candidates*, never certified electrical evidence.
* **Not available at all.** No device has ever received a command in this
  firmware: it has no transport, ``SOURCE_NOT_CANONICAL`` admits only the
  canonical network source, and expiry fails closed on an unsynchronised clock
  (``EPOCH_UNSYNCHRONIZED``). The W06 traces in ``evidence/A/W06/`` are
  host-harness fixtures. So S4 is built and proved on clearly-labelled fixtures
  and the physical leg is NEED_USER_ACTION.
"""

from __future__ import annotations

import dataclasses

import cg_command_trace as w06_trace
import cg_w09_export as run_export
import cg_w09_validity as validity
from cg_w09_capture_parser import Frame

S4_TOOL_VERSION = "w11-s4-v1"

INTENT = "INTENT"
APPLIED = "APPLIED"
ELECTRICAL = "ELECTRICAL"
THERMAL = "THERMAL"
LANES = (INTENT, APPLIED, ELECTRICAL, THERMAL)

FRAME_READ = "READ_FROM_DEVICE_FRAME"
ACK_PAYLOAD = "READ_FROM_DEVICE_ACK_PAYLOAD"
HOST_FIXTURE = "HOST_FIXTURE_NOT_DEVICE_EVIDENCE"
INFERRED_FROM_INTENT = "INFERRED_FROM_INTENT"
LANE_MISSING = "NO_EVIDENCE_IN_THIS_SOURCE"
FORBIDDEN_SOURCES = (INFERRED_FROM_INTENT,)
NON_PROMOTABLE = (HOST_FIXTURE, LANE_MISSING, INFERRED_FROM_INTENT)

REFUSAL_STATUSES = ("REJECTED", "EXPIRED", "SAFETY_BLOCKED", "INVALID_STATE", "OUT_OF_RANGE")
NON_REAPPLICATION_STATUSES = ("DUPLICATE_CANONICAL",)
ACCEPT_STATUSES = ("ACCEPTED",)

# Analysis floors, named as choices rather than contract values. The PZEM-017
# LSB is 0.01 A; 0.05 A is the same floor cg_command_trace uses so the two tools
# cannot disagree about what "drawing current" means.
NO_RESPONSE_CURRENT_FLOOR_A = 0.05
RESIDUAL_RESPONSE_CURRENT_FLOOR_A = 0.5


#: Named reasons a frame cannot carry the applied-vs-current comparison. A row
#: that silently leaves a statistic is indistinguishable from a row that was
#: believed, so each excluded row is counted under exactly one of these names and
#: the counts must reconcile against ``frames_scanned``.
EXCLUDED_APPLIED_FIELD_ABSENT = "APPLIED_DUTY_FIELD_ABSENT_FROM_THIS_SOURCE"
EXCLUDED_APPLIED_NOT_AN_INTEGER = "APPLIED_DUTY_IS_NOT_AN_INTEGER"
EXCLUDED_CURRENT_FIELD_ABSENT = "CURRENT_FIELD_ABSENT_FROM_THIS_SOURCE"
EXCLUDED_CURRENT_NOT_A_NUMBER = "CURRENT_IS_NOT_A_NUMBER"
EXCLUSION_REASONS = (
    EXCLUDED_APPLIED_FIELD_ABSENT,
    EXCLUDED_APPLIED_NOT_AN_INTEGER,
    EXCLUDED_CURRENT_FIELD_ABSENT,
    EXCLUDED_CURRENT_NOT_A_NUMBER,
)

#: The same discipline for the three duty fields. Precedence is requested, then
#: applied, then read-back, so one bad row is counted exactly once.
EXCLUDED_REQUESTED_FIELD_ABSENT = "REQUESTED_DUTY_FIELD_ABSENT_FROM_THIS_SOURCE"
EXCLUDED_REQUESTED_NOT_AN_INTEGER = "REQUESTED_DUTY_IS_NOT_AN_INTEGER"
EXCLUDED_READBACK_FIELD_ABSENT = "READBACK_DUTY_FIELD_ABSENT_FROM_THIS_SOURCE"
EXCLUDED_READBACK_NOT_AN_INTEGER = "READBACK_DUTY_IS_NOT_AN_INTEGER"
DUTY_EXCLUSION_REASONS = (
    EXCLUDED_REQUESTED_FIELD_ABSENT,
    EXCLUDED_REQUESTED_NOT_AN_INTEGER,
    EXCLUDED_APPLIED_FIELD_ABSENT,
    EXCLUDED_APPLIED_NOT_AN_INTEGER,
    EXCLUDED_READBACK_FIELD_ABSENT,
    EXCLUDED_READBACK_NOT_AN_INTEGER,
)


class PromotionError(RuntimeError):
    """A trace tried to turn one kind of evidence into another."""


@dataclasses.dataclass(frozen=True)
class Lane:
    """One evidence lane, with the source it was read from."""

    lane: str
    value: object
    source: str
    qualified: bool
    note: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _lane(lane: str, value, source: str, qualified: bool, note: str = "") -> Lane:
    if source in FORBIDDEN_SOURCES:
        raise PromotionError(
            f"{lane} lane was derived from intent ({source}). S4 exists to compare intent "
            "against what actually happened; a lane that answers for intent is not evidence."
        )
    return Lane(lane=lane, value=value, source=source, qualified=qualified, note=note)


def applied_current_exclusion_reason(frame: Frame) -> str | None:
    """The single named reason this frame cannot carry the applied/current comparison.

    ``None`` means the comparison is possible. Absent and present-but-unparseable
    are different reasons because they are different defects: a source that never
    carried the field cannot be blamed for its rows, while a row whose field is
    there and unreadable is a per-row failure. Applied is judged first so that a
    row bad in both ways is counted once, never twice.
    """
    if not frame.has("pwm_applied_permille"):
        return EXCLUDED_APPLIED_FIELD_ABSENT
    applied = frame.values.get("pwm_applied_permille")
    if not isinstance(applied, int) or isinstance(applied, bool):
        return EXCLUDED_APPLIED_NOT_AN_INTEGER
    if not frame.has("current_a"):
        return EXCLUDED_CURRENT_FIELD_ABSENT
    current = frame.values.get("current_a")
    if not isinstance(current, (int, float)) or isinstance(current, bool):
        return EXCLUDED_CURRENT_NOT_A_NUMBER
    return None


def duty_field_exclusion_reason(frame: Frame) -> str | None:
    """The single named reason this frame cannot enter the three-duty comparison.

    A frame whose requested duty is absent cannot be said to agree or disagree
    with what was applied, so it is excluded and named rather than counted as a
    match - counting it silently would inflate the agreement statistic with rows
    that carry no evidence either way.
    """
    checks = (
        ("pwm_req_permille", EXCLUDED_REQUESTED_FIELD_ABSENT, EXCLUDED_REQUESTED_NOT_AN_INTEGER),
        ("pwm_applied_permille", EXCLUDED_APPLIED_FIELD_ABSENT, EXCLUDED_APPLIED_NOT_AN_INTEGER),
        ("pwm_readback_permille", EXCLUDED_READBACK_FIELD_ABSENT, EXCLUDED_READBACK_NOT_AN_INTEGER),
    )
    for field, absent_reason, unparseable_reason in checks:
        if not frame.has(field):
            return absent_reason
        value = frame.values.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            return unparseable_reason
    return None


def applied_lane_from_frame(frame: Frame) -> Lane:
    """Applied duty read from the frame. Never from the request."""
    applied = frame.values.get("pwm_applied_permille")
    readback = frame.values.get("pwm_readback_permille")
    requested = frame.values.get("pwm_req_permille")
    if applied is None:
        return _lane(APPLIED, None, LANE_MISSING, False,
                     "this encoding carries no applied-duty field")
    if requested is not None and applied == requested:
        note = "applied equals requested in this frame; that is an observation, not an inference"
    elif requested is not None:
        note = f"applied {applied} differs from requested {requested}: a real divergence"
    else:
        note = "requested duty is absent, so divergence cannot be stated"
    return _lane(APPLIED, {"applied_permille": applied, "readback_permille": readback,
                           "requested_permille": requested}, FRAME_READ, True, note)


def electrical_lane_from_frame(frame: Frame) -> Lane:
    """Current, usable only with an OK producer status. Empty status is not OK."""
    current = frame.values.get("current_a")
    status = frame.values.get("current_a_status")
    if current is None:
        return _lane(ELECTRICAL, None, LANE_MISSING, False, "no current value in this frame")
    if status in (None, ""):
        return _lane(
            ELECTRICAL, {"current_a": current}, LANE_MISSING, False,
            "current_a carries no producer status in this source (empty is not OK), so it is a "
            "candidate observation and cannot certify an electrical claim",
        )
    return _lane(
        ELECTRICAL, {"current_a": current}, FRAME_READ, status == "OK",
        f"current_a_status={status!r}",
    )


def thermal_lane_from_frame(frame: Frame) -> Lane:
    """Chamber-air thermal evidence. TEC_HOT_SIDE is excluded by definition."""
    readings = {
        slot: frame.values.get(slot)
        for slot in run_export.CHAMBER_AIR_SLOTS
        if isinstance(frame.values.get(slot), (int, float))
    }
    if not readings:
        return _lane(THERMAL, None, LANE_MISSING, False, "no qualified chamber-air value")
    return _lane(THERMAL, readings, FRAME_READ, frame.values.get("snapshot") == "VALID",
                 "chamber-air slots only; TEC_HOT_SIDE excluded")


def build_lane_view(frame: Frame) -> dict:
    """The three device lanes for one frame, each with its own source."""
    return {
        APPLIED: applied_lane_from_frame(frame).as_dict(),
        ELECTRICAL: electrical_lane_from_frame(frame).as_dict(),
        THERMAL: thermal_lane_from_frame(frame).as_dict(),
        "seq": frame.seq,
        "boot_id": frame.boot_id,
        "state": frame.values.get("state"),
        "stop_reason": frame.values.get("stop_reason"),
    }


def find_command_electrical_disagreements(
    frames: list[Frame],
) -> dict:
    """Frames where applied duty and measured current disagree.

    This is the S4 pattern - ``command != electrical effect`` - searched for in
    whatever capture is given. It reports candidates and qualified evidence
    separately, because in the committed capture every disagreement is an
    unqualified one and saying so is the finding.
    """
    no_active_response: list[dict] = []
    residual_response: list[dict] = []
    exclusions: dict[str, int] = {}
    rows_compared = 0
    for frame in frames:
        reason = applied_current_exclusion_reason(frame)
        if reason is not None:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        rows_compared += 1
        applied = frame.values.get("pwm_applied_permille")
        current = frame.values.get("current_a")
        status = frame.values.get("current_a_status")
        qualified = status == "OK"
        record = {
            "seq": frame.seq,
            "boot_id": frame.boot_id,
            "device_ms": frame.values.get("device_ms"),
            "state": frame.values.get("state"),
            "stage": frame.values.get("stage"),
            "stop_reason": frame.values.get("stop_reason"),
            "pwm_req_permille": frame.values.get("pwm_req_permille"),
            "pwm_applied_permille": applied,
            "pwm_readback_permille": frame.values.get("pwm_readback_permille"),
            "current_a": current,
            "current_status_present": status not in (None, ""),
            "electrically_qualified": qualified,
        }
        if applied > 0 and current < NO_RESPONSE_CURRENT_FLOOR_A:
            no_active_response.append(record)
        elif applied == 0 and current > RESIDUAL_RESPONSE_CURRENT_FLOOR_A:
            residual_response.append(record)
    row_account = {
        "frames_scanned": len(frames),
        "rows_compared": rows_compared,
        "rows_excluded": dict(sorted(exclusions.items())),
        "rows_excluded_total": sum(exclusions.values()),
        "reconciles": rows_compared + sum(exclusions.values()) == len(frames),
        "every_exclusion_has_a_named_reason": all(
            reason in EXCLUSION_REASONS for reason in exclusions
        ),
        "reasons_never_fired": [r for r in EXCLUSION_REASONS if r not in exclusions],
        "note": (
            "reasons_never_fired is checked-and-found-none, which is not the same claim as "
            "did-not-check; an absent field and an unreadable field are excluded separately "
            "because they are different defects"
        ),
    }
    if not row_account["reconciles"] or not row_account["every_exclusion_has_a_named_reason"]:
        # This fires the moment a counter stops naming what it drops: proved by
        # deleting the `exclusions[reason] += 1` line, which makes the tool refuse
        # instead of publishing a statistic about a population it cannot account for.
        raise ValueError(f"the applied/current comparison lost or mislabelled rows: {row_account}")
    return {
        "floors_a": {
            "no_active_response_below": NO_RESPONSE_CURRENT_FLOOR_A,
            "residual_response_above": RESIDUAL_RESPONSE_CURRENT_FLOOR_A,
            "basis": "PZEM-017 LSB is 0.01 A; the floors match cg_command_trace so the two "
                     "tools cannot disagree about what 'drawing current' means",
        },
        "no_active_response_candidates": no_active_response,
        "residual_response_candidates": residual_response,
        "qualified_no_active_response": [r for r in no_active_response if r["electrically_qualified"]],
        "qualified_residual_response": [r for r in residual_response if r["electrically_qualified"]],
        "frames_scanned": len(frames),
        "row_account": row_account,
        "rows_without_a_producer_status": sum(
            1 for r in no_active_response + residual_response if not r["electrically_qualified"]
        ),
        "interpretation": (
            "an applied duty with no current is the S4 signature; current with no applied duty is "
            "the same inequality in the other direction. Both are reported as candidates unless "
            "the current value carries an OK producer status."
        ),
    }


def request_applied_divergence(frames: list[Frame]) -> dict:
    """Count frames where the three duty lanes genuinely differ.

    Real physical evidence that the lanes are separate instruments: the
    committed capture reports req=1000, applied=999, readback=999 for every one
    of its 600 active frames.

    The comparison is between three duty fields the device itself reported. It is
    **not** a command-versus-application comparison: intent lives in the command
    and its ACK, and a capture with no command observation cannot separate intent
    from application however tidy its duty fields look. That limit is published
    with the counts, in the same dictionary, so the divergence can never be read as
    an intent claim.
    """
    seen: dict[tuple, int] = {}
    exclusions: dict[str, int] = {}
    rows_compared = 0
    for frame in frames:
        reason = duty_field_exclusion_reason(frame)
        if reason is not None:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        rows_compared += 1
        key = (
            frame.values.get("pwm_req_permille"),
            frame.values.get("pwm_applied_permille"),
            frame.values.get("pwm_readback_permille"),
        )
        seen[key] = seen.get(key, 0) + 1
    tuples_ = {str(k): v for k, v in sorted(seen.items(), key=lambda kv: -kv[1])}
    divergent = sum(
        n for (req, applied, _rb), n in seen.items()
        if isinstance(req, int) and isinstance(applied, int) and applied != req
    )
    row_account = {
        "frames_scanned": len(frames),
        "rows_compared": rows_compared,
        "rows_excluded": dict(sorted(exclusions.items())),
        "rows_excluded_total": sum(exclusions.values()),
        "reconciles": rows_compared + sum(exclusions.values()) == len(frames),
        "reasons_never_fired": [r for r in DUTY_EXCLUSION_REASONS if r not in exclusions],
    }
    if not row_account["reconciles"]:
        raise ValueError(f"a duty row was neither compared nor accounted for: {row_account}")
    return {
        "distinct_req_applied_readback_tuples": tuples_,
        "frames_where_applied_differs_from_requested": divergent,
        "frames_where_readback_differs_from_applied": sum(
            n for (_req, applied, rb), n in seen.items()
            if isinstance(applied, int) and isinstance(rb, int) and rb != applied
        ),
        "row_account": row_account,
        "duty_fields_never_agree": divergent > 0,
        "intent_vs_application": (
            "NOT SEPARABLE IN THIS SOURCE unless a command observation exists: the three numbers "
            "above are all device-reported duty fields, so they separate three instruments from "
            "each other, never the request from its application. The intent lane comes from the "
            "command and its ACK, and a capture carrying no command observation carries no intent."
        ),
        "reading": (
            "requested, applied and read-back are three separate device claims; a capture in "
            "which they never differ would give S4 nothing to distinguish"
        ),
    }


def _refusal_row_check(row: dict) -> list[str]:
    """A refusal must never appear as an applied action. Returns violations.

    Three cases are separated rather than lumped together, because only two of
    them are errors:

    * refused + applied evidence showing the output stayed off -> the S4
      signature, and the only thing the protocol is for;
    * refused + applied evidence showing the output on -> a refusal that
      coincides with an action. Unless the trace supplies explicit
      ``applied_state_before_command`` evidence that it was already running,
      presenting that as a refusal is exactly the confusion S4 exists to catch,
      so it is rejected;
    * refused + a stage like ``ELECTRICAL_VERIFIED`` listed as reached *for that
      command* -> a verdict promoted into physical verification, which docs/02
      §32.2 forbids.
    """
    violations: list[str] = []
    statuses = [str(s) for s in row.get("ack_statuses", [])]
    lanes = row.get("lanes", {})
    refusals = [s for s in statuses if s in REFUSAL_STATUSES]
    if refusals:
        promoted = sorted({
            stage for stage in row.get("stages", [])
            if stage in ("ELECTRICAL_VERIFIED", "THERMAL_VERIFIED")
        })
        if promoted:
            violations.append(
                f"command {row.get('command_id')} was refused ({', '.join(refusals)}) yet the "
                f"trace reaches {promoted}; an ACK is protocol evidence, never physical "
                "verification (docs/02 §32.2)"
            )
        if row.get("applied_action_attributed_to_command"):
            violations.append(
                f"command {row.get('command_id')} was refused yet the trace attributes an "
                "applied action to it"
            )
        applied_value = (lanes.get(APPLIED) or {}).get("value")
        applied_on = False
        detail = None
        if isinstance(applied_value, dict):
            if applied_value.get("applied_cooling") == "ON":
                applied_on = True
                detail = "applied_cooling=ON"
            duty = applied_value.get("applied_permille")
            if isinstance(duty, int) and duty > 0:
                applied_on = True
                detail = f"pwm_applied_permille={duty}"
        elif applied_on is False and applied_value == "ON":
            applied_on, detail = True, "applied_cooling=ON"
        if applied_on and not row.get("applied_state_before_command"):
            violations.append(
                f"command {row.get('command_id')} was refused ({', '.join(refusals)}) while the "
                f"applied lane shows {detail}: a refusal cannot be presented alongside an "
                "applied action unless the trace states the action predates the command"
            )
    if DUPLICATE_CANONICAL_PRESENT in statuses:
        if "1" in [str(f) for f in row.get("reapplied_flags", [])]:
            violations.append(
                f"command {row.get('command_id')} was a canonical duplicate that applied again "
                "(docs/02 §30.1)"
            )
    return violations


def applied_semantics(row: dict) -> str:
    """Classify what the applied lane says about a refusal, without promoting it."""
    statuses = [str(s) for s in row.get("ack_statuses", [])]
    if not any(s in REFUSAL_STATUSES for s in statuses):
        return "NOT_A_REFUSAL"
    lanes = row.get("lanes") or {}
    value = (lanes.get(APPLIED) or {}).get("value")
    applied_on = value == "ON" or (
        isinstance(value, dict)
        and (value.get("applied_cooling") == "ON"
             or (isinstance(value.get("applied_permille"), int) and value["applied_permille"] > 0))
    )
    if applied_on:
        return (
            "REFUSED_PREEXISTING_APPLICATION"
            if row.get("applied_state_before_command") else "REFUSED_WITH_APPLIED_ON"
        )
    if value is None or (lanes.get(APPLIED) or {}).get("source") == LANE_MISSING:
        return "REFUSED_APPLIED_STATE_UNKNOWN"
    return "REFUSED_NON_APPLICATION_OBSERVED"


DUPLICATE_CANONICAL_PRESENT = "DUPLICATE_CANONICAL"


def assert_no_promotion(trace: dict) -> None:
    """Refuse a trace that promoted intent into applied/electrical/thermal."""
    problems: list[str] = []
    for row in trace.get("commands", []):
        for lane_name, lane in (row.get("lanes") or {}).items():
            if isinstance(lane, dict) and lane.get("source") in FORBIDDEN_SOURCES:
                problems.append(
                    f"command {row.get('command_id')}: {lane_name} lane source is "
                    f"{lane.get('source')!r}"
                )
        problems.extend(_refusal_row_check(row))
    if problems:
        raise PromotionError("; ".join(problems))


def build_s4_trace(
    frames: list[Frame],
    *,
    command_records: list[dict] | None = None,
    is_physical_measurement: bool = True,
    protocol_id: str = "S4-protocol-v1",
) -> dict:
    """Assemble an S4 trace: intent lanes, device lanes, and the gaps between.

    ``command_records`` are parsed ``#CG CMDACK``/command observations, normally
    from ``cg_command_trace.parse_capture``. Absent commands are reported as an
    empty trace - never as an inferred one.
    """
    parsed: dict[str, dict] = {}
    if command_records:
        for record in command_records:
            parsed[str(record["command_id"])] = record
    rows: list[dict] = []
    for command_id, record in sorted(parsed.items()):
        ack = (record.get("acks") or [{}])[0]
        status = str(ack.get("status", "MISSING"))
        desired = ack.get("desired_cooling", record.get("desired_cooling", "MISSING"))
        desired_duty = ack.get(
            "desired_duty_permille", record.get("desired_duty_permille", "MISSING")
        )
        applied_at_ack = ack.get("applied_cooling", record.get("applied_cooling"))
        same_boot = [f for f in frames if str(f.boot_id) == str(record.get("ack_boot_id") or "")]
        lanes = {
            INTENT: _lane(
                INTENT,
                {"desired_cooling": desired, "desired_duty_permille": desired_duty},
                ACK_PAYLOAD if status != "MISSING" else LANE_MISSING,
                status != "MISSING",
                "the request itself is only evidence that it was asked",
            ).as_dict(),
            APPLIED: _lane(
                APPLIED,
                {"applied_cooling": applied_at_ack},
                ACK_PAYLOAD if applied_at_ack not in (None, "MISSING") else LANE_MISSING,
                applied_at_ack not in (None, "MISSING"),
                "applied_cooling is read from the device ACK payload, never from desired_*",
            ).as_dict(),
            ELECTRICAL: _lane(
                ELECTRICAL, None, LANE_MISSING, False,
                "no electrical evidence is attached to this command in this capture",
            ).as_dict(),
            THERMAL: _lane(
                THERMAL, None, LANE_MISSING, False,
                "no thermal evidence is attached to this command in this capture",
            ).as_dict(),
        }
        row = {
            "command_id": command_id,
            "ack_statuses": [str(a.get("status", "MISSING")) for a in (record.get("acks") or [])],
            "ack_reasons": [str(a.get("reason", "MISSING")) for a in (record.get("acks") or [])],
            "boot_id": record.get("ack_boot_id"),
            "frames_same_boot": len(same_boot),
            "refused": status in REFUSAL_STATUSES,
            "refusal_action_attributed": False,
            "applied_state_before_command": record.get("applied_state_before_command"),
            "applied_action_attributed_to_command": bool(
                record.get("applied_action_attributed_to_command", False)
            ),
            "stages": list(record.get("stages", ["COMMAND_SEEN"])),
            "blocked_at": record.get("blocked_at"),
            "reapplied_flags": [str(a.get("reapplied", "MISSING")) for a in (record.get("acks") or [])],
            "lanes": lanes,
        }
        row["applied_semantics"] = applied_semantics(row)
        rows.append(row)

    trace = {
        "tool_version": S4_TOOL_VERSION,
        "protocol_id": protocol_id,
        "is_physical_measurement": is_physical_measurement,
        "commands_observed": len(rows),
        "commands": rows,
        "device_lane_audit": {
            "command_electrical_disagreements": find_command_electrical_disagreements(frames),
            "request_applied_divergence": request_applied_divergence(frames),
        },
        "promotion_rules": {
            "forbidden_lane_sources": list(FORBIDDEN_SOURCES),
            "refusal_statuses": list(REFUSAL_STATUSES),
            "duplicate_statuses": list(NON_REAPPLICATION_STATUSES),
            "rule": (
                "intent may never populate the applied, electrical or thermal lane; a lane's "
                "source must be a device frame, a device ACK payload, an explicit host-fixture "
                "label, or an explicit absence"
            ),
        },
        "physical_s4_position": {
            "status_label": "NEED_USER_ACTION",
            "device_received_any_command": False,
            "reasons": [
                "this firmware has no transport at all",
                "admission requires SOURCE_NOT_CANONICAL to clear, and no canonical network "
                "source is connected",
                "expiry fails closed as EPOCH_UNSYNCHRONIZED because the device has no wall clock",
                "docs/02 §32.2: an ACK is protocol evidence, never physical verification",
            ],
        },
        "honesty": [
            "a refusal in this trace is a protocol verdict, not a physical non-action",
            "command != electrical effect is asserted only where current carries an OK status",
            "no lane here was filled by reading the request",
        ],
    }
    assert_no_promotion(trace)
    return trace


S4_PROTOCOL: dict = {
    "protocol_id": "S4-protocol-v1",
    "requirement": "docs/05A §20 A-W11-01/02",
    "status_label": "IMPLEMENTED / HOST_VERIFIED; physical leg NEED_USER_ACTION",
    "method": (
        "create the fault in the safe layer only: the device or harness intentionally refuses or "
        "blocks actuation while keeping the protocol visible. Never short a branch, never bypass "
        "the fuse, never damage the TEC (docs/05A §20 A-W11-01)."
    ),
    "required_evidence_lanes": [
        {"lane": INTENT, "from": "the issued command and its ACK payload (desired_*)"},
        {"lane": APPLIED, "from": "pwm_applied_permille / applied_cooling read from a device frame"},
        {"lane": ELECTRICAL, "from": "current_a with current_status=OK - no-active-response"},
        {"lane": THERMAL, "from": "chamber-air probes showing non-response"},
    ],
    "expected_signature": {
        "intent": "desired_cooling=ON, desired_duty_permille>0",
        "applied": "pwm_applied_permille=0, or ACK SAFETY_BLOCKED with applied OFF",
        "electrical": "current_a below the no-response floor with status OK",
        "thermal": "no chamber-air movement beyond the noise floor from cg_w10_pairing",
        "proves": "command != electrical effect",
    },
    "why_not_computable_now": [
        "no device-received command exists: the firmware has no transport",
        "canonical-source admission rejects every non-canonical issuer",
        "the clock is unsynchronised, so expiry fails closed",
        "the committed capture's electrical columns are unqualified (empty status in all 957 rows)",
    ],
    "hazard_this_protocol_avoids": (
        "a harness that reports SAFETY_BLOCKED while the output is actually energised is the "
        "failure S4 must catch. The three-lane split plus the promotion rule is what catches it: "
        "the block verdict alone would look perfectly safe."
    ),
    "fixture_position": (
        "the validator is proved on labelled fixtures with "
        "is_physical_measurement=false; they demonstrate refusal handling, they do not "
        "demonstrate a device refusing"
    ),
}

S4_CAPTURE_RECIPE: dict = {
    "status_label": "NEED_USER_ACTION",
    "prerequisites": [
        "a transport and an issuer exist (Member C), or a bench harness path that is explicitly "
        "labelled as not-a-transport",
        "operator at the bench, TEC current path and fuse posture confirmed",
        "the qualified electrical lane must exist before the run: current_status must be emitted "
        "and recorded OK, not empty",
    ],
    "repetitions": 4,
    "per_repetition": [
        "boot, open capture before ARM, record boot_id",
        "enter the safe refusal mode (test-mode block, not a physical fault)",
        "issue the ON request with the planned duty and record the ACK verdict",
        "hold 60 s and capture applied duty + current + chamber air",
        "exit refusal, re-issue, capture the responding leg as the contrast",
        "record the operator timer and any intervention",
    ],
    "cadence": "1 Hz device telemetry, command lines interleaved in the same capture",
    "estimated_capture_duration_s": 240,
    "downstream_unlocks": [
        "Member B's S4 label for diagnosis training",
        "Member D's evidence that a blocked verdict does not energise the output",
    ],
}
