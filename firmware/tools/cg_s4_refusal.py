"""ColdGuard S4: command intent versus applied state, and a refusal validator.

docs/05A §20 A-W11-02 names four evidence legs for an S4 run:

```text
command/intention
applied state
PZEM no-active-response
thermal non-response
```

and the single claim they are supposed to carry is **a command is not an
electrical effect** (docs/01 §1.3/§1.4/§1.5 split the same three ways; PHY-X-004
makes the separation an invariant). This module reads real device frames, walks
those legs, and refuses - by raising, not by returning a soft word - to call
anything an S4 run when a leg is missing.

Why refusal is the dangerous case. In S4 the actuator is intentionally blocked,
so the *expected* outcome is a command that produced nothing. That makes S4 the
scenario where a tool can most easily lie: every missing leg looks like a
successful negative result. Each leg is therefore classified three ways, not two:

```text
REACHED        the device positively stated it
NOT_REACHED    the device positively stated the opposite
UNDETERMINED   the device did not speak
```

Only ``NOT_REACHED`` supports "command != effect". ``UNDETERMINED`` supports
nothing and is never collapsed into it. The concrete cases this is about:

* ``cooling_evidence=UNOBSERVED_NO_DATA`` / ``UNOBSERVED_STALE``
  (``cg_telemetry_schema.COOLING_EVIDENCE_VOCABULARY``) is the device saying it
  did not look. It is NOT "no current". A PZEM read error and a de-energised
  branch both leave the wire at ``current_a=nan``; only one of them is evidence
  about the branch (docs/01 §9.9, §23.2, F-ELEC-01).
* An electrical no-response claim needs the current value present with
  ``current_status=OK`` and at or below a floor the run **predeclared**. The
  floor is a required input with no default: a threshold chosen after seeing the
  trace would decide the experiment's outcome (docs/03 §7, forbidden post-hoc
  exclusion).
* A thermal non-response claim is comparative. docs/01 §23.3 allows "materially
  weaker than matched healthy baseline" only against a baseline, and no
  characterized healthy thermal envelope exists in the repository yet (A-W09-04
  is uncollected). So every thermal leg built from today's data is UNDETERMINED,
  and this module says so instead of calling a flat trace a non-response.

Command/ACK semantics are inherited, not re-decided. The shipped W06 rules in
``firmware/main/cg_command.c`` are: a refused command performs no action
(:197-203), a duplicate performs no action and reports the first verdict
(:259-297), and expiry is evaluable only when the device clock is synchronized -
otherwise the ACK is ``EPOCH_UNSYNCHRONIZED`` with ``expiry_evaluable=0`` and the
device neither acts nor claims the command expired (:317-327). No receive-time TTL
is substituted for the command's own age. This module enforces the same rule
downstream: ``reason=EXPIRED`` beside ``expiry_evaluable=0`` is a contradiction
and fails closed, and nothing here may claim a command "was still fresh" when the
device could not evaluate expiry at all.

Physical honesty: a source whose provenance says ``is_physical_measurement=False``
is a host fixture. It may exercise the classifier and may be published as tooling
evidence; it may never be registered as an S4 run. The only ``#CG CMDACK``
material committed today (``evidence/A/W06/``) is exactly that kind of fixture.

Usage:
    py firmware/tools/cg_s4_refusal.py <capture.log> [--json out.json]
    py firmware/tools/cg_s4_refusal.py --selftest
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cg_telemetry_schema as telemetry_schema  # noqa: E402
from cg_command_trace import STAGES  # noqa: E402  one ladder, no private copy

S4_TOOL_VERSION = "s4-refusal-v1"
SCENARIO_ID = "S4_ACTUATION_RESPONSE_FAULT"

REACHED = "REACHED"
NOT_REACHED = "NOT_REACHED"
UNDETERMINED = "UNDETERMINED"
LEG_STATES = (REACHED, NOT_REACHED, UNDETERMINED)

#: docs/02 §32.1 closed ACK set. These verdicts mean the device did not perform
#: the requested action; they are refusals, and they are also what an S4 harness
#: deliberately produces.
REFUSAL_STATUSES = ("REJECTED", "EXPIRED", "SAFETY_BLOCKED", "INVALID_STATE", "OUT_OF_RANGE")
NON_REFUSAL_STATUSES = ("ACCEPTED", "DUPLICATE_CANONICAL")

COOLING_EVIDENCE_NEGATIVE = "MEASURED_IDLE_AND_ZERO"
COOLING_EVIDENCE_UNOBSERVED = ("UNOBSERVED_NO_DATA", "UNOBSERVED_STALE")

#: docs/01 §23.2: ELECTRICAL_RESPONSE_MISSING needs a valid ON applied state plus
#: a response outside the expected active envelope. There is no such thing as
#: "absent because the meter said nothing", so a qualified reading is mandatory.
ELECTRICAL_STATUS_REQUIRED = "OK"

LEG_ORDER = (
    "COMMAND_INTENT",
    "DEVICE_VERDICT",
    "APPLIED_STATE",
    "ELECTRICAL_NO_RESPONSE",
    "THERMAL_NON_RESPONSE",
)
#: Which lifecycle claim each leg is allowed to promote. Kept as data so the
#: refusal rule and the promotion rule are one table read two ways.
LEG_TO_STAGE = {
    "COMMAND_INTENT": "COMMAND_SEEN",
    "DEVICE_VERDICT": "DEVICE_ACK",
    "APPLIED_STATE": "APPLIED_STATE",
    "ELECTRICAL_NO_RESPONSE": "ELECTRICAL_VERIFIED",
    "THERMAL_NON_RESPONSE": "THERMAL_VERIFIED",
}

_CMDACK_RE = re.compile(r"^\s*#CG CMDACK ")
_INT_RE = re.compile(r"^-?\d+$")


class RefusalError(RuntimeError):
    """Raised when the evidence does not support the label being asked for."""


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


REPO_ROOT = TOOLS.parents[1]


def repository_relative(path: pathlib.Path) -> str:
    """Publish a source path relative to the repository, never as a developer path.

    An evidence record that names ``C:/Users/<name>/...`` cannot be read by anyone else:
    it points at one machine, and it makes the dossier un-pinnable because the validator
    refuses any absolute developer path. A relative input is read as repository-relative
    (that is how every registered capture path is written), so the published record does
    not depend on which directory the tool happened to be invoked from. A path that
    resolves outside the repository keeps its absolute form, because pretending it is
    relative would be a lie about where the observation came from.
    """
    given = pathlib.Path(path)
    resolved = (REPO_ROOT / given).resolve() if not given.is_absolute() else given.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_input(path: pathlib.Path) -> pathlib.Path:
    """The same rule the published path uses, so reading and naming cannot disagree."""
    given = pathlib.Path(path)
    return (REPO_ROOT / given).resolve() if not given.is_absolute() else given.resolve()


@dataclasses.dataclass(frozen=True)
class ObservationSource:
    """Where an observation came from, and whether it may be believed as data."""

    path: str
    sha256: str | None
    is_physical_measurement: bool
    label: str = ""

    @classmethod
    def from_path(cls, path: pathlib.Path, is_physical_measurement: bool, label: str = ""):
        resolved = resolve_input(path)
        return cls(
            path=repository_relative(resolved),
            sha256=sha256_file(resolved),
            is_physical_measurement=is_physical_measurement,
            label=label or resolved.name,
        )

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class S4RunRecord:
    """The predeclared contract of one S4 attempt, fixed *before* the data.

    Every threshold here is an input, never a default, because a threshold picked
    after seeing the trace is a post-hoc exclusion (docs/03 §7).
    """

    run_id: str
    boot_id: str
    hardware_config_id: str
    firmware_version: str
    device_id: str
    blocking_mechanism: str
    no_response_current_floor_a: float | None
    thermal_window_ms: int | None
    baseline_run_id: str | None
    baseline_source: str
    protocol_version: str
    doc_anchor: str = "docs/05A §20 A-W11-01/02; docs/03 §31 S4"

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _as_int(token):
    if isinstance(token, bool):
        return None
    if isinstance(token, int):
        return token
    text = "" if token is None else str(token)
    return int(text) if _INT_RE.match(text) else None


def _as_float(token):
    if token is None or isinstance(token, bool):
        return None
    try:
        value = float(token)
    except (TypeError, ValueError):
        return None
    return None if value != value else value  # NaN is absence, never zero


def parse_cmdack_lines(lines) -> dict[str, list[dict[str, str]]]:
    """Collect ``#CG CMDACK`` lines per ``command_id`` without interpreting them."""
    acks: dict[str, list[dict[str, str]]] = {}
    for raw in lines:
        text = raw.rstrip("\r\n")
        if not _CMDACK_RE.match(text):
            continue
        fields: dict[str, str] = {}
        for token in text.split(" ")[2:]:
            if "=" in token:
                key, value = token.split("=", 1)
                if key in fields:
                    raise RefusalError(f"ACK line repeats field {key!r}; a spliced line is not a verdict")
                fields[key] = value
        command_id = fields.get("command_id")
        if not command_id or command_id == "NONE":
            continue
        if all(existing != fields for existing in acks.get(command_id, [])):
            acks.setdefault(command_id, []).append(fields)
        # An identical repeat of the same command_id is the replay case, and the
        # firmware's own rule (cg_command.c:259-297) is that a replay reports the
        # FIRST verdict rather than appending a second one. Keeping one verdict per
        # identical field set is how that survives analysis.
    return {name: sorted(entries, key=lambda e: _as_int(e.get("uptime_ms")) or 0)
            for name, entries in acks.items()}


def parse_telem_lines(lines) -> tuple[list[dict], dict]:
    """Parse every ``#CG TELEM`` line, keeping raw tokens for tri-state logic.

    A line the schema rejects is not skipped silently: the count travels with the
    frames, so a capture with parse failures can never be scored as complete.
    """
    frames: list[dict] = []
    rejected = 0
    for raw in lines:
        text = raw.rstrip("\r\n")
        if not text.startswith(telemetry_schema.PREFIX):
            continue
        try:
            record = telemetry_schema.parse_line(text)
        except telemetry_schema.TelemetryError:
            rejected += 1
            continue
        frames.append({
            "raw_fields": dict(record.raw_fields),
            "fields": dict(record.fields),
            "schema": record.fields.get("schema"),
            "line_index": record.line_index,
        })
    return frames, {"telem_frames": len(frames), "telem_rejected": rejected}


def leg(state: str, reason: str, evidence: dict | None = None, doc_anchor: str = "") -> dict:
    if state not in LEG_STATES:
        raise RefusalError(f"leg state {state!r} is not one of {LEG_STATES}")
    return {"state": state, "reason": reason, "evidence": evidence or {}, "doc_anchor": doc_anchor}


def classify_command_intent(ack: dict | None, frame: dict | None) -> dict:
    """Leg 1: the device was asked to do something."""
    anchor = "docs/01 §1.3; docs/02 §28.1"
    if ack is not None:
        command_id = ack.get("command_id")
        action = ack.get("action") or ack.get("desired_cooling")
        if not command_id or not action:
            return leg(UNDETERMINED,
                       "ACK line carries no command_id or no requested action; intent is not stated",
                       {"ack": ack, "observation_made": False}, anchor)
        return leg(REACHED, f"command_id={command_id} requested action={action!r}",
                   {"command_id": command_id, "action": action,
                    "uptime_ms": _as_int(ack.get("uptime_ms")), "observation_made": True}, anchor)
    if frame is not None:
        desired = frame["fields"].get("desired_cooling")
        if desired in ("ON", "OFF"):
            return leg(REACHED, f"frame reports desired_cooling={desired}",
                       {"command_id": frame["fields"].get("command_id"),
                        "desired_cooling": desired, "observation_made": True}, anchor)
        return leg(UNDETERMINED, f"frame reports desired_cooling={desired!r}",
                   {"observation_made": False}, anchor)
    return leg(UNDETERMINED, "no command observation exists for this window",
               {"observation_made": False}, anchor)


def classify_device_verdict(ack: dict | None, frame: dict | None) -> dict:
    """Leg 2: the device's own verdict, and whether it is a refusal."""
    anchor = "docs/02 §32.1; firmware/main/cg_command.c:290-335"
    status = reason = expiry_evaluable = None
    if ack is not None:
        status, reason = ack.get("status"), ack.get("reason")
        expiry_evaluable = _as_int(ack.get("expiry_evaluable"))
    elif frame is not None:
        status, reason = frame["fields"].get("last_ack_status"), frame["fields"].get("last_ack_reason")

    if status is None or status == "NONE":
        return leg(UNDETERMINED,
                   "no ACK verdict reported; a refusal cannot be claimed from silence",
                   {"last_ack_status": status, "observation_made": False}, anchor)
    if status not in REFUSAL_STATUSES + NON_REFUSAL_STATUSES:
        return leg(UNDETERMINED, f"ACK status {status!r} is outside the closed set",
                   {"status": status, "observation_made": False}, anchor)

    evidence = {"status": status, "reason": reason,
                "is_refusal": status in REFUSAL_STATUSES,
                "expiry_evaluable": expiry_evaluable, "observation_made": True}
    if status == "EXPIRED" and expiry_evaluable == 0:
        # cg_command.c only emits reason=EXPIRED from the branch that sets
        # expiry_evaluable=1 (:331-335). EXPIRED beside an explicit 0 did not come
        # from that firmware path, so the verdict cannot be trusted.
        return leg(UNDETERMINED,
                   "status=EXPIRED with expiry_evaluable=0: the device cannot have established "
                   "this command's own age (docs/02 §29 conjunct 4)", evidence, anchor)
    if expiry_evaluable == 0:
        # Unsynchronized clock: the verdict itself stands for the other reasons, but
        # no freshness claim - in either direction - is available (docs/02 §29.4).
        evidence["freshness_established"] = False
    return leg(REACHED, f"device verdict is {status} (reason={reason})", evidence, anchor)


def classify_applied_state(frame: dict | None, *, refusal: bool) -> dict:
    """Leg 3: what the device says it is actually doing.

    Never inferred from intent. ``desired_cooling`` and the ACK fields are the
    *request*; reading them as the applied state is the exact promotion this
    module exists to block.
    """
    anchor = "docs/01 §1.4; docs/05A §20 A-W11-02"
    if frame is None:
        return leg(UNDETERMINED,
                   "no telemetry frame in the same boot after the command; applied state is not "
                   "observable, and a refusal without applied evidence proves only that nothing "
                   "was read", {"observation_made": False}, anchor)
    fields = frame["fields"]
    applied = fields.get("cooling_applied")
    source = fields.get("cooling_applied_source")
    tec_state = fields.get("tec_state")
    if applied is None and tec_state is None:
        return leg(UNDETERMINED, "frame carries neither cooling_applied nor tec_state",
                   {"observation_made": False}, anchor)
    if applied is None:
        # Schema 1 predates the W05 split; tec_state is the firmware's own applied
        # record but is weaker, so the weaker name is kept rather than renamed.
        applied, source = tec_state, "TEC_STATE_SCHEMA1_NO_SOURCE_FIELD"
    observed = {"cooling_applied": applied, "cooling_applied_source": source,
                "uptime_ms": _as_int(fields.get("uptime_ms")), "observation_made": True}
    if refusal and applied == "ON":
        return leg(NOT_REACHED,
                   f"command was refused yet applied state is {applied!r}: a refused command "
                   "performed an action (cg_command.c:197-203 forbids this)", observed, anchor)
    if not refusal and applied != "ON":
        return leg(NOT_REACHED, f"command accepted but applied state is {applied!r}", observed, anchor)
    return leg(REACHED, f"device reports applied state {applied!r} from {source!r}", observed, anchor)


def classify_electrical_no_response(frame: dict | None, *, floor_a: float | None) -> dict:
    """Leg 4: the branch drew nothing, *measured*.

    ``NOT_REACHED`` here means "there was no electrical response", and that claim
    is only available when the instrument actually looked: a present current with
    ``current_status=OK`` at or below the predeclared floor. Everything else is
    UNDETERMINED, because ``current_a=nan`` is a meter that said nothing and
    docs/01 §19.4 forbids UNKNOWN quietly becoming normal.
    """
    anchor = "docs/01 §1.5, §23.2; docs/01 §9.9 (PZEM evidence limitations)"
    if floor_a is None:
        return leg(UNDETERMINED,
                   "no predeclared no-response current floor; the threshold decides the outcome, "
                   "so it may not be invented here", {"observation_made": False}, anchor)
    if frame is None:
        return leg(UNDETERMINED, "no frame to read the branch current from",
                   {"observation_made": False}, anchor)
    fields = frame["fields"]
    current = _as_float(fields.get("current_a"))
    status = fields.get("current_status")
    evidence = {"current_a": current, "current_status": status, "floor_a": floor_a,
                "power_w": _as_float(fields.get("power_w")),
                "power_status": fields.get("power_status"),
                "cooling_evidence": fields.get("cooling_evidence")}
    if current is None or status != ELECTRICAL_STATUS_REQUIRED:
        return leg(UNDETERMINED,
                   f"current_a={fields.get('current_a')!r} with current_status={status!r}: an "
                   "unread branch is not a de-energised branch",
                   {**evidence, "observation_made": False}, anchor)
    if current > floor_a:
        return leg(REACHED,
                   f"branch drew {current} A, above the {floor_a} A no-response floor: the "
                   "command DID have an electrical effect",
                   {**evidence, "observation_made": True}, anchor)
    if evidence.get("cooling_evidence") == COOLING_EVIDENCE_NEGATIVE:
        return leg(NOT_REACHED,
                   f"current {current} A <= floor {floor_a} A and the device itself reports "
                   "MEASURED_IDLE_AND_ZERO", {**evidence, "observation_made": True}, anchor)
    if evidence.get("cooling_evidence") in COOLING_EVIDENCE_UNOBSERVED:
        # The number is qualified but the device's own cross-check did not run.
        # Both statements are kept: the reading stands, the corroboration does not.
        return leg(NOT_REACHED,
                   f"current {current} A <= floor {floor_a} A from a qualified reading; the "
                   f"device's own corroboration is {evidence['cooling_evidence']} "
                   "(uncorroborated)", {**evidence, "observation_made": True}, anchor)
    return leg(NOT_REACHED, f"current {current} A <= floor {floor_a} A with current_status=OK",
               {**evidence, "observation_made": True}, anchor)


def classify_thermal_non_response(frames: list[dict], *, record: S4RunRecord | None,
                                  window_ms: int | None) -> dict:
    """Leg 5: the chamber did not move *relative to a matched healthy baseline*.

    docs/01 §20.6: recovery and non-response are only meaningful after a defined
    disturbance/action reference. Without a baseline there is no "materially
    weaker", only "flat" - and a flat trace is also what an unloaded bench with no
    working PZEM produces. So this leg is UNDETERMINED unless a baseline is named.
    """
    anchor = "docs/01 §1.6, §20.6, §23.3; docs/05A §20 A-W11-02"
    if record is None or record.baseline_run_id is None:
        return leg(UNDETERMINED,
                   "no matched healthy baseline run is named; thermal non-response is a "
                   "comparison and there is nothing to compare against (A-W09-04 is uncollected)",
                   {"observation_made": False}, anchor)
    if window_ms is None:
        return leg(UNDETERMINED, "no predeclared thermal observation window",
                   {"observation_made": False}, anchor)
    usable = [
        f for f in frames
        if _as_float(f["fields"].get("t_inside_c")) is not None
        and f["fields"].get("t_inside_status") == "OK"
    ]
    if len(usable) < 2:
        return leg(UNDETERMINED,
                   f"only {len(usable)} qualified thermal frame(s); a trend needs two",
                   {"thermal_frames_usable": len(usable), "window_ms": window_ms,
                    "observation_made": False}, anchor)
    first = _as_int(usable[0]["fields"].get("uptime_ms"))
    last = _as_int(usable[-1]["fields"].get("uptime_ms"))
    if first is None or last is None or last - first < window_ms:
        span = None if None in (first, last) else last - first
        return leg(UNDETERMINED,
                   f"qualified thermal span is {span} ms, short of the predeclared "
                   f"{window_ms} ms window",
                   {"span_ms": span, "window_ms": window_ms, "observation_made": False}, anchor)
    delta = _as_float(usable[-1]["fields"]["t_inside_c"]) - _as_float(usable[0]["fields"]["t_inside_c"])
    return leg(REACHED if delta else NOT_REACHED,
               f"thermal change over the window is {delta:+.4f} C against baseline "
               f"{record.baseline_run_id} ({record.baseline_source}); the baseline magnitude, "
               "not this sign, decides whether that is a non-response",
               {"delta_c": round(delta, 6), "frames": len(usable), "window_ms": window_ms,
                "baseline_run_id": record.baseline_run_id, "observation_made": True}, anchor)


def observation_made(legs: dict[str, dict], name: str) -> bool:
    """Did the device positively speak about this leg at all?

    Separate from ``state``: for the electrical and thermal legs a positive
    observation may report either a response or a non-response, and both count as
    verification of the *observation*, which is what a lifecycle stage means.
    """
    entry = legs.get(name, {})
    if entry.get("state") not in (REACHED, NOT_REACHED):
        return False
    return bool(entry.get("evidence", {}).get("observation_made", True))


def reached_stage(legs: dict[str, dict]) -> str | None:
    """The furthest lifecycle stage an observation was actually made for.

    Traversal stops at the first leg with no observation: claiming thermal
    verification behind an unread power channel would promote a stage on an axis
    the device never spoke on (docs/02 §33).
    """
    reached: str | None = None
    for name in LEG_ORDER:
        if not observation_made(legs, name):
            break
        reached = LEG_TO_STAGE[name]
    if reached is not None and reached not in STAGES:
        raise RefusalError(f"stage {reached!r} is not in the shipped W06 ladder")
    return reached


def analyze_attempt(*, ack: dict | None, frames: list[dict], record: S4RunRecord | None,
                    floor_a: float | None, baseline_window_ms: int | None) -> dict:
    """Score one command attempt against the four legs plus the device verdict."""
    after = [f for f in frames if _as_int(f["fields"].get("uptime_ms")) is not None]
    if ack is not None:
        ack_uptime = _as_int(ack.get("uptime_ms"))
        ack_boot = ack.get("boot_id")
        if ack_uptime is not None:
            after = [f for f in after if _as_int(f["fields"]["uptime_ms"]) >= ack_uptime]
        if ack_boot:
            mismatched = sorted({
                f["fields"].get("boot_id") for f in after
                if f["fields"].get("boot_id") not in (None, ack_boot)
            })
            if mismatched:
                # A frame from another boot is a different clock axis; joining it
                # to this ACK would order events that never coexisted.
                raise RefusalError(
                    f"attempt joins frames from boot(s) {mismatched} to an ACK in boot "
                    f"{ack_boot!r}; boot-local clocks are not comparable"
                )
    first = after[0] if after else None
    verdict = classify_device_verdict(ack, first)
    refusal = verdict["evidence"].get("is_refusal") is True
    legs = {
        "COMMAND_INTENT": classify_command_intent(ack, first),
        "DEVICE_VERDICT": verdict,
        "APPLIED_STATE": classify_applied_state(first, refusal=refusal),
        "ELECTRICAL_NO_RESPONSE": classify_electrical_no_response(first, floor_a=floor_a),
        "THERMAL_NON_RESPONSE": classify_thermal_non_response(
            after, record=record, window_ms=baseline_window_ms
        ),
    }
    return {
        "command_id": (ack or {}).get("command_id") or (first["fields"].get("command_id") if first else None),
        "refusal": refusal,
        "legs": legs,
        "reached": reached_stage(legs),
        "frames_considered": len(after),
    }


def score_run(attempts: list[dict]) -> dict:
    """Run-level verdict: what the legs collectively support."""
    counts = {state: 0 for state in LEG_STATES}
    for attempt in attempts:
        for name in LEG_ORDER:
            counts[attempt["legs"][name]["state"]] += 1
    never_observed = [
        name for name in LEG_ORDER
        if attempts and not any(observation_made(a["legs"], name) for a in attempts)
    ]
    refusals = [a for a in attempts if a["refusal"]]
    if not attempts:
        verdict = "NO_COMMAND_OBSERVATIONS"
        # Zero observations is not a clean bill of health: with nothing seen, no
        # leg was seen, and a flag derived from "not unobserved" would otherwise
        # read as proven. Fail closed by naming every leg unobserved.
        never_observed = list(LEG_ORDER)
    elif never_observed:
        verdict = "EVIDENCE_INCOMPLETE"
    elif refusals:
        verdict = "S4_REFUSAL_EVIDENCE_PRESENT"
    else:
        verdict = "NO_REFUSAL_OBSERVED"
    blocking = [n for n in never_observed if n != "THERMAL_NON_RESPONSE"]
    return {
        "attempts": len(attempts),
        "refusal_attempts": len(refusals),
        "leg_state_counts": counts,
        "legs_never_observed": never_observed,
        "verdict": verdict,
        # The headline claim A-W11-02 asks for needs intent, verdict, applied
        # state and a *qualified* electrical reading. The thermal leg is a
        # separate, later claim and is reported as unmet rather than folded in.
        "command_not_equal_to_effect_proven": bool(refusals) and not blocking,
        "thermal_non_response_proven": "THERMAL_NON_RESPONSE" not in never_observed,
        "s4_run_publishable": bool(refusals) and not blocking,
    }


def validate_s4_run(*, attempts: list[dict], score: dict, record: S4RunRecord | None,
                    sources: list[ObservationSource]) -> dict:
    """Fail closed: refuse to certify an S4 run the evidence does not support.

    Raises ``RefusalError`` rather than returning a soft "no", because a caller
    that ignores a returned string publishes an unsupported claim anyway.
    """
    problems: list[str] = []
    if record is None:
        problems.append("no predeclared S4 run record")
    if not sources:
        problems.append("no observation source at all")
    if not [s for s in sources if s.is_physical_measurement]:
        problems.append(
            "every source declares is_physical_measurement=false; a host fixture exercises the "
            "classifier and can never be registered as an S4 run (docs/05A §20 A-W11-02)"
        )
    if not attempts:
        problems.append("no command attempt was observed")
    if score["verdict"] != "S4_REFUSAL_EVIDENCE_PRESENT":
        problems.append(f"verdict is {score['verdict']!r}")
    for name in score["legs_never_observed"]:
        if name == "THERMAL_NON_RESPONSE":
            continue  # reported separately; it is not what A-W11-02 headlines
        problems.append(f"leg {name} was never observed")
    if not any(
        attempt["legs"]["APPLIED_STATE"]["evidence"].get("uptime_ms") is not None
        for attempt in attempts
    ):
        problems.append(
            "no applied-state observation carries an uptime, so intent and effect cannot be "
            "ordered on one axis (docs/01 §18.1)"
        )
    for attempt in attempts:
        applied = attempt["legs"]["APPLIED_STATE"]
        if applied["state"] == NOT_REACHED and not attempt["refusal"]:
            problems.append(
                f"command {attempt['command_id']!r}: accepted but not applied, so this is a "
                "device fault, not a protocolised S4 refusal"
            )
        elif applied["state"] == NOT_REACHED and attempt["refusal"]:
            problems.append(
                f"command {attempt['command_id']!r}: a REFUSED command reached applied state ON; "
                "the harness is not blocking actuation"
            )
    if record is not None:
        if not record.baseline_run_id:
            problems.append("record names no matched healthy baseline (A-W09-04 uncollected)")
        if not record.blocking_mechanism:
            problems.append("record names no blocking mechanism")
        if record.no_response_current_floor_a is None:
            problems.append("record predeclares no no-response current floor")
        if not record.hardware_config_id or not record.firmware_version:
            problems.append("record does not pin hardware_config_id and firmware_version")
    if problems:
        raise RefusalError("S4 run is not certifiable: " + "; ".join(problems))
    return {
        "run_id": record.run_id,
        "verdict": "CERTIFIED_S4_EVIDENCE",
        "proven": "command != electrical effect, for this attempt set only",
        "not_proven": [
            "the fault cause (docs/01 §23.3: a non-response identifies an effectiveness problem, "
            "not a component)",
            "any rate, duration or magnitude that generalises beyond these frames",
            "any absolute-time claim: device_ms is per-boot uptime and the host clock is not "
            "device time (docs/01 §18.5)",
        ],
        "sources": [s.as_dict() for s in sources],
        "record": record.as_dict(),
        "tool_version": S4_TOOL_VERSION,
    }


def analyze_capture(path: pathlib.Path, *, is_physical_measurement: bool,
                    floor_a: float | None = None,
                    record: S4RunRecord | None = None,
                    thermal_window_ms: int | None = None) -> dict:
    """End-to-end read of one capture file. No hardware, no invented clock."""
    path = resolve_input(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    source = ObservationSource.from_path(path, is_physical_measurement)
    acks = parse_cmdack_lines(lines)
    frames, frame_meta = parse_telem_lines(lines)
    attempts = [
        analyze_attempt(
            ack=entries[0] if entries else None,
            frames=frames, record=record, floor_a=floor_a,
            baseline_window_ms=thermal_window_ms,
        )
        for command_id, entries in sorted(acks.items())
    ]
    score = score_run(attempts)
    return {
        "tool_version": S4_TOOL_VERSION,
        "scenario_id": SCENARIO_ID,
        "provenance": source.as_dict(),
        "summary": {
            "command_ids_observed": sorted(acks),
            "attempts": len(attempts),
            "boot_ids_in_frames": sorted({f["fields"].get("boot_id") for f in frames
                                          if f["fields"].get("boot_id")}),
            "telem_frames": frame_meta["telem_frames"],
            "telem_rejected": frame_meta["telem_rejected"],
            "cmdack_lines": sum(len(v) for v in acks.values()),
        },
        "score": score,
        "attempts": attempts,
        "real_data_availability": {
            "s4_refusal_runs_in_repository": 0,
            "status": "REAL DATA NOT AVAILABLE",
            "note": (
                "The S4 refusal / actuation-block experiment series has not been run. The only "
                "#CG CMDACK material committed is the W06 host fixture, which this tool labels "
                "non-physical and refuses to certify. A-W11-02's four legs therefore have no "
                "physical instance anywhere in this repository."
            ),
        },
    }


_SELFTEST_ACK = (
    "#CG CMDACK uptime_ms=5000 boot_id=deadbeef device_id=coldguard-001 "
    "command_id=CMD-T-1 status=SAFETY_BLOCKED reason=EPOCH_UNSYNCHRONIZED "
    "expiry_evaluable=0 action=COOLING_ON duty_permille=500"
)
#: The shipped formatter writes the saturation sentinel, not -1, when an age is
#: unknowable (cg_telemetry_schema.AGE_SATURATION_SENTINEL). A fixture that wrote
#: -1 would be rejected by the real parser, so the fixture uses the real token.
_NO_AGE = str(telemetry_schema.AGE_SATURATION_SENTINEL)
_SELFTEST_TELEM = (
    "#CG TELEM schema=3 timestamp_utc=UNAVAILABLE timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK "
    "uptime_ms=6000 elapsed_ms=6000 run_elapsed_ms=0 run_id=run-00000001 boot_id=deadbeef "
    "boot_count=1 firmware_version=cg-w11-0.0.0 hardware_config_id=CG-HW-001 test_phase=S4 "
    "device_id=coldguard-001 seq=6 calibration_id=UNRECORDED t_inside_c=nan "
    "t_inside_status=NO_DATA t_inside_src=T2 t_cold_side_c=nan t_cold_side_status=NOT_ASSIGNED "
    "t_hot_side_c=nan t_hot_side_status=NOT_ASSIGNED t_ambient_c=nan t_ambient_status=NOT_ASSIGNED "
    "relative_humidity_pct=nan relative_humidity_status=SENSOR_NOT_PRESENT voltage_v=nan "
    "voltage_status=NO_DATA current_a=nan current_status=NO_DATA power_w=nan power_status=NO_DATA "
    "energy_wh=nan energy_status=NO_DATA pwm_duty=500 fan_command=OFF fan_status=NOT_COMMANDABLE "
    "output_stage=DISABLED tec_state=OFF fault_code=0x00000000 fault_reason=BOOT_SAFE_OFF "
    "sensor_validity=NO_DATA power_validity=NO_DATA door_open=nan door_status=UNVERIFIED "
    "door_raw=1 "
    f"door_age_ms={_NO_AGE} thermal_age_ms={_NO_AGE} power_age_ms={_NO_AGE} "
    "thermal_seq=0 power_seq=0 "
    "door_transitions=0 door_cycles=0 probes_valid=0 probes_expected=4 thermal_quality=INVALID "
    "environment_quality=INVALID door_quality=INVALID electrical_quality=INVALID quality=INVALID "
    "cooling_applied=OFF cooling_applied_source=LOCAL_POLICY cooling_evidence=UNOBSERVED_NO_DATA "
    "health=NEVER health_thermal=NEVER health_bme=NEVER "
    "health_door=NEVER health_power=NEVER health_telemetry=NEVER "
    "health_control=NEVER t1_rom=UNREAD t2_rom=UNREAD t3_rom=UNREAD spare_rom=UNREAD "
    "role_status=UNASSIGNED rom_source=UNREAD command_id=NONE desired_cooling=NONE "
    "desired_duty_permille=nan last_ack_status=NONE last_ack_reason=NONE"
)


def selftest() -> int:
    """Prove the fail-closed behaviour needs no capture at all.

    The case that matters: a refused command plus an unread PZEM must NOT be
    scored as "no electrical response".
    """
    lines = (_SELFTEST_ACK + "\n" + _SELFTEST_TELEM).splitlines()
    acks = parse_cmdack_lines(lines)
    frames, _meta = parse_telem_lines(lines)
    attempt = analyze_attempt(ack=next(iter(acks.values()))[0], frames=frames, record=None,
                              floor_a=0.2, baseline_window_ms=60_000)
    checks = [
        (attempt["legs"]["DEVICE_VERDICT"]["state"] == REACHED, "device verdict leg must be REACHED"),
        (attempt["legs"]["DEVICE_VERDICT"]["evidence"]["is_refusal"] is True,
         "SAFETY_BLOCKED must classify as a refusal"),
        (attempt["legs"]["ELECTRICAL_NO_RESPONSE"]["state"] == UNDETERMINED,
         "current_status=NO_DATA must NOT become 'no electrical response'"),
        (attempt["legs"]["THERMAL_NON_RESPONSE"]["state"] == UNDETERMINED,
         "absent baseline must NOT become 'thermal non-response'"),
        (attempt["reached"] == "APPLIED_STATE",
         f"the ladder must stop at APPLIED_STATE, got {attempt['reached']!r}"),
        (score_run([attempt])["s4_run_publishable"] is False,
         "an attempt with an unread power channel must not be publishable"),
    ]
    failed = [message for ok, message in checks if not ok]
    if failed:
        for message in failed:
            print(f"SELFTEST FAIL: {message}")
        return 1
    print("S4 SELFTEST: OK (unread PZEM and absent baseline stay UNDETERMINED, never negative evidence)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", nargs="?", help="capture log to analyse")
    parser.add_argument("--json", dest="out", help="write the report here")
    parser.add_argument("--current-floor-a", type=float, default=None,
                        help="predeclared no-response current floor in A; required to score leg 4")
    parser.add_argument("--thermal-window-ms", type=int, default=None)
    parser.add_argument("--physical", action="store_true",
                        help="assert this capture is a physical measurement")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.selftest:
        return selftest()
    if not args.capture:
        parser.error("a capture path is required unless --selftest")
    report = analyze_capture(
        pathlib.Path(args.capture), is_physical_measurement=args.physical,
        floor_a=args.current_floor_a, thermal_window_ms=args.thermal_window_ms,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
