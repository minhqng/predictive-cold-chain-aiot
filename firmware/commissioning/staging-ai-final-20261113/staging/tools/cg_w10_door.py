"""ColdGuard W10 door-disturbance analysis for S2.

docs/05A §19 wants S2 to become "the primary reproducible thermal disturbance",
with MC-38 transitions as machine ground truth and an operator timer as the
secondary check. This module does the analysis *and* enforces the caveat that
makes the analysis honest, which is that a door reading is only a story about a
magnet until someone attests which way the switch is wired.

The three facts the code is built around, each with the citation status it can
actually carry:

1. **The mapping is a switch, and a switch cannot self-attest.**
   `docs/01` §8.1 states the door semantics are "subject to actual polarity
   mapping" and §8.2 forbids assuming either ``HIGH = OPEN`` or ``LOW = OPEN``
   without physical verification. That is enough to establish the mechanism: two
   polarity settings assign *opposite* door states to every raw level, so no set
   of frames can name its own door state - the same bytes support the exact
   opposite narrative under the other setting. `DOOR_CONTACT_INVERSION` records
   the mapping table this module carries and its proof status. The driver source
   that shows the inversion in code
   (``firmware/h8-bench/main/h8_door.c``) is **not** git-tracked on any ref, so
   it is labelled ``UNCITABLE_UNTRACKED_SOURCE`` in the registry rather than
   quoted as proof: untracked bytes cannot anchor a published claim.
   ``frames_alone_can_name_door_state`` is therefore ``false``, and an external
   per-boot attestation is required.
2. **A polarity confirmation is a console command, not a measurement.**
   ``DOOR NEAR_LOW|NEAR_HIGH <boot_token>`` (the bench console driver, likewise
   ``UNCITABLE_UNTRACKED_SOURCE``). The MC-38 alignment record states what that
   bought: sending ``NEAR_HIGH`` "only made the firmware echo a stuck-high input
   as CLOSED (door_open=0, snapshot=VALID). That was not a valid physical
   calibration." Confirmation is necessary and nowhere near sufficient.
3. **The confirmation is per boot.** The direct-magnet record says so explicitly:
   "The polarity confirmation is per boot and was re-applied only for this test."
   Opening the monitor port resets the board and changes ``boot_id``. So an
   attestation attached to a different boot does not license these frames.
   ``attest_for_boot()`` enforces that match; a mismatch is an error, not a
   warning.

Consequences enforced here:

* ``door_open=UNKNOWN`` is never reported as CLOSED, and an unknown door never
  certifies "no disturbance" (W09 gate ``GATE-DOOR-STATE``).
* An event is an *S2 pilot disturbance* only if the source is physical, the
  per-boot mapping is attested, the disturbance was operator-controlled and
  timed, and the thermal response clears the noise floor. Anything else is
  returned with the specific reason it is not S2 evidence.
* Thermal rise/recovery is measured on chamber-air probes only. The frozen
  as-built geometry puts T2 on the TEC hot side, so including it in a chamber
  response would be measuring a heatsink.
* Host fixtures carry ``is_physical_measurement: false`` through every event and
  ``pilot_status()`` states the capture recipe the operator still has to run.
"""

from __future__ import annotations

import dataclasses
import math
import statistics

import cg_w09_export as run_export
import cg_w09_validity as validity
from cg_w09_capture_parser import PROBE_SLOTS, Frame

DOOR_TOOL_VERSION = "w10-door-v1"

NEAR_LOW = "NEAR_LOW"
NEAR_HIGH = "NEAR_HIGH"
MAPPING_BY_POLARITY = {
    NEAR_LOW: {"raw_0": "CLOSED", "raw_1": "OPEN"},
    NEAR_HIGH: {"raw_0": "OPEN", "raw_1": "CLOSED"},
}
# Citation status for a claim whose only source is bytes no branch carries. The
# W09 registry already applies the same rule to the untracked H8 raw frames
# ("untracked bytes cannot anchor a published claim"); the door driver is in the
# same position, so the mechanism is stated with the status instead of a quote.
# The name is W09's: the S1 registry publishes it as a capture's eligibility, so the
# validity layer owns it and the door analysis re-exports the same value.
UNCITABLE_UNTRACKED_SOURCE = validity.UNCITABLE_UNTRACKED_SOURCE
DOOR_CONTACT_INVERSION = {
    "claim": (
        "the two shipped polarity settings assign opposite door states to every raw "
        "level, so a capture cannot establish its own door narrative"
    ),
    "assertion_basis": (
        "docs/01 §8.1 (door semantics are subject to the actual polarity mapping) and "
        "§8.2 (neither HIGH=OPEN nor LOW=OPEN may be assumed without physical "
        "verification), plus the mapping table this module carries"
    ),
    "code_level_proof_status": UNCITABLE_UNTRACKED_SOURCE,
    "code_level_proof_location": "firmware/h8-bench/main/h8_door.c",
    "why_not_citable": (
        "that file is not git-tracked on any ref in this repository; it exists only in "
        "a sibling working tree, so it may not be quoted as the proof of a published "
        "claim"
    ),
    "closes_when": (
        "the owning branch commits the door driver, after which the inversion is "
        "verifiable from tracked source"
    ),
    "action_required": "the H8 bench owner must commit the driver source",
}
# Bench door-driver timings (50 ms debounce on a 10 ms poll). They come from the
# same uncitable driver; nothing published here depends on them, because the
# published edge uncertainty follows from the committed 1 Hz frame stream alone.
MC38_DEBOUNCE_MS = 50
MC38_POLL_MS = 10
MC38_TIMING_BASIS = f"{UNCITABLE_UNTRACKED_SOURCE}: firmware/h8-bench/main/h8_door.c"
TELEMETRY_CADENCE_HZ = 1.0

CLOSED = "CLOSED"
OPEN = "OPEN"
UNKNOWN = "UNKNOWN"
# What a frame says without an attestation is not a door *state*: it is the
# device's own report, named here so a reader cannot mistake the label for a
# physical claim. docs/01 §8.2 makes the two polarity settings complements, so
# only an external per-boot attestation turns OPEN/CLOSED into a state.
CLOSED_AS_REPORTED = "CLOSED_AS_REPORTED"
OPEN_AS_REPORTED = "OPEN_AS_REPORTED"
REPORTED_ONLY_STATES = (CLOSED_AS_REPORTED, OPEN_AS_REPORTED)


def is_open_state(state: str) -> bool:
    """OPEN, or the device's own report of it without an attestation."""
    return state in (OPEN, OPEN_AS_REPORTED)


def is_closed_state(state: str) -> bool:
    return state in (CLOSED, CLOSED_AS_REPORTED)

S2_EVENT_CLASSES = (
    "S2_PILOT_DISTURBANCE",
    "INCIDENTAL_DOOR_TRANSITION",
    "UNATTESTED_DOOR_TRANSITION",
    "NON_PHYSICAL_FIXTURE",
    "STARTUP_POLARITY_PENDING",
)


def name_from_raw(door_raw: int | None, polarity: str | None) -> str:
    """Apply the shipped mapping. Returns UNKNOWN rather than guessing."""
    if door_raw is None or polarity is None or polarity == "UNCONFIRMED":
        return UNKNOWN
    if polarity not in MAPPING_BY_POLARITY:
        return UNKNOWN
    table = MAPPING_BY_POLARITY[polarity]
    return table.get(f"raw_{door_raw}", UNKNOWN)


def frames_can_name_their_own_door_state() -> bool:
    """Always False: the two polarity settings are complements of each other."""
    return False


def polarity_inversion_check(frames: list[Frame]) -> dict:
    """Demonstrate, from the frames themselves, that the mapping is a switch.

    For every frame carrying both ``door_raw`` and a confirmed polarity, compute
    the state under the *opposite* setting. If any of them flips, the capture
    cannot self-attest - the bytes are compatible with two opposite stories.
    """
    checked = 0
    disagree = 0
    examples: list[dict] = []
    for frame in frames:
        raw = frame.values.get("door_raw")
        polarity = frame.values.get("door_polarity")
        if raw is None or polarity in (None, "UNCONFIRMED"):
            continue
        other = NEAR_HIGH if polarity == NEAR_LOW else NEAR_LOW
        stated = name_from_raw(raw, polarity)
        opposite = name_from_raw(raw, other)
        checked += 1
        if stated != opposite:
            disagree += 1
            if len(examples) < 3:
                examples.append({
                    "seq": frame.seq, "door_raw": raw,
                    "as_reported_polarity": polarity, "state_as_reported": stated,
                    "state_under_opposite_polarity": opposite,
                })
    return {
        "frames_with_raw_and_confirmed_polarity": checked,
        "frames_whose_state_inverts_under_the_other_polarity": disagree,
        "inversion_fraction": round(disagree / checked, 6) if checked else None,
        "examples": examples,
        "frames_alone_can_name_door_state": False,
        "contact_inversion": DOOR_CONTACT_INVERSION,
        "conclusion": (
            "every raw level maps to opposite door states under the two polarity settings, so a "
            "capture cannot establish its own door narrative; per-boot operator attestation of "
            "the mapping is mandatory"
        ) if checked else "no frames carry both door_raw and a confirmed polarity",
    }


@dataclasses.dataclass(frozen=True)
class PolarityAttestation:
    """Who attested which mapping, for which boot, and on what evidence."""

    boot_id: str
    polarity: str
    attested_by: str
    evidence: str
    attested_at_utc: str | None = None

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def attest_for_boot(frames: list[Frame], attestation: PolarityAttestation | None) -> dict:
    """Decide whether the door states in these frames may be named at all.

    Note what cannot be checked: the wire carries ``door_polarity`` as a
    confirmation *flag* (CONFIRMED/UNCONFIRMED) and never the mapping *name* -
    the driver keeps ``near_low`` inside itself and emits neither
    ``transitions`` nor ``near_low`` on the ``#CG H8S`` line (that driver file is
    ``UNCITABLE_UNTRACKED_SOURCE``; the flag-only shape is what the committed
    frames themselves show). The attested mapping is therefore an external claim
    that the frames can corroborate only as "some confirmation happened", never
    as "this mapping was in force".
    """
    boots = sorted({str(f.boot_id) for f in frames if f.boot_id})
    confirmed_frames = sum(1 for f in frames if f.values.get("door_polarity") == "CONFIRMED")
    base = {
        "present": attestation is not None,
        "capture_boot_ids": boots,
        "frames_total": len(frames),
        "frames_reporting_polarity_confirmed": confirmed_frames,
        "frame_can_state_which_mapping_was_used": False,
        "mapping_identity_is_externally_attested_only": True,
    }
    if attestation is None:
        base.update({
            "trustworthy": False,
            "reason": "NO_ATTESTATION: no operator attestation of the mapping was supplied",
            "attested_boot_ids": [],
        })
        return base
    base.update({
        "polarity": attestation.polarity,
        "attested_by": attestation.attested_by,
        "evidence": attestation.evidence,
        "attested_at_utc": attestation.attested_at_utc,
        "attested_boot_ids": [attestation.boot_id],
    })
    if attestation.polarity not in MAPPING_BY_POLARITY:
        base["trustworthy"] = False
        base["reason"] = (
            f"UNKNOWN_POLARITY_NAME: {attestation.polarity!r} is not one of "
            f"{', '.join(MAPPING_BY_POLARITY)}"
        )
        return base
    if attestation.boot_id not in boots:
        base["trustworthy"] = False
        base["reason"] = (
            f"ATTESTATION_BOOT_MISMATCH: the mapping was attested for boot "
            f"{attestation.boot_id!r} but these frames are boot(s) {boots}; the polarity "
            "confirmation is per boot, so it does not license this capture"
        )
        return base
    if confirmed_frames == 0:
        base["trustworthy"] = False
        base["reason"] = (
            "NO_FRAME_CORROBORATION: the attestation names a boot present in the capture but no "
            "frame reports door_polarity=CONFIRMED, so nothing on the wire agrees that any "
            "mapping was ever set for it"
        )
        return base
    base["trustworthy"] = True
    base["reason"] = "ATTESTED_FOR_THIS_BOOT_AND_CORROBORATED_BY_FRAME_FLAGS"
    return base


@dataclasses.dataclass(frozen=True)
class DoorEvent:
    """One run of a named door state, with everything that licenses the claim."""

    event_id: str
    boot_id: str
    run_id: str | None
    state: str
    start_seq: int | None
    end_seq: int | None
    start_device_ms: int | None
    end_device_ms: int | None
    duration_s: float | None
    n_frames: int
    cycles_reported_by_device: int | None
    thermal_rise: dict
    recovery: dict
    event_class: str
    state_semantics: str
    not_s2_because: tuple[str, ...]
    not_s2_details: dict
    is_physical_measurement: bool
    timing_uncertainty: dict

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _thermal_window(frames: list[Frame], indexes: list[int], ref: dict) -> dict:
    """Rise relative to a reference, per chamber-air slot. Hot side excluded."""
    out: dict[str, dict] = {}
    for slot in run_export.CHAMBER_AIR_SLOTS:
        base = ref.get(slot)
        values = [
            frames[i].values.get(slot)
            for i in indexes
            if isinstance(frames[i].values.get(slot), (int, float))
        ]
        if base is None or not values:
            out[slot] = {"n": len(values), "rise_c": None, "peak_c": None}
            continue
        peak = max(values) if base is not None else None
        out[slot] = {
            "n": len(values),
            "reference_c": round(base, 4),
            "peak_c": round(peak, 4),
            "rise_c": round(peak - base, 4),
            "physical_position": run_export.FROZEN_SENSOR_GEOMETRY[slot]["position"],
        }
    out["excluded_slots"] = {
        "t2": run_export.EXCLUDED_FROM_CHAMBER_MEAN["t2"],
        "tec_hot_side_value_during_event": _slot_mean(frames, indexes, "t2"),
    }
    return out


def _slot_mean(frames: list[Frame], indexes: list[int], slot: str) -> float | None:
    values = [
        frames[i].values.get(slot)
        for i in indexes
        if isinstance(frames[i].values.get(slot), (int, float))
    ]
    return round(statistics.fmean(values), 4) if values else None


def timing_quantization() -> dict:
    """What the MC-38 path can and cannot resolve, from the shipped timings."""
    return {
        "debounce_ms": MC38_DEBOUNCE_MS,
        "poll_ms": MC38_POLL_MS,
        "telemetry_hz": TELEMETRY_CADENCE_HZ,
        "edge_time_uncertainty_s": 1.0,
        "minimum_resolvable_open_duration_s": 1.0,
        "note": (
            "a 50 ms debounce on a 10 ms poll is far inside one telemetry interval, so the "
            "machine ground truth is quantised by the 1 Hz frame stream, not by the sensor; an "
            "operator timer remains the only sub-second check (docs/05A §19 A-W10-02)"
        ),
        "machine_counter_field": "door_cycles",
        "timing_basis": MC38_TIMING_BASIS,
        "cadence_basis": "1 Hz committed frame stream of evidence/A/W04/tec-cooling-response-600s.csv",
        "cross_check": (
            "sum of detected OPEN->CLOSED transitions must equal the device's final door_cycles; "
            "a mismatch means the capture missed an edge and the pilot run is not usable"
        ),
    }


def detect_events(
    frames: list[Frame],
    *,
    attestation: PolarityAttestation | None = None,
    operator_controlled: bool = False,
    protocol_id: str | None = None,
    noise_floor_c: dict[str, float] | None = None,
) -> dict:
    """Segment a capture into door-state runs and classify each one.

    ``UNKNOWN`` is a state of its own: it is never folded into CLOSED, and a run
    that begins in UNKNOWN is reported as ``STARTUP_POLARITY_PENDING`` rather
    than as a closed door at rest.
    """
    if not frames:
        raise ValueError("no frames supplied")
    attestation_status = attest_for_boot(frames, attestation)
    usable = {
        i for i, verdict in enumerate(validity.evaluate_frames(frames))
        if "S2_DOOR_DISTURBANCE" in verdict.usable_for
    }

    def state_of(frame: Frame) -> str:
        raw = frame.values.get("door_raw")
        if attestation_status["trustworthy"]:
            return name_from_raw(raw, attestation_status["polarity"])
        reported = frame.values.get("door_open")
        if reported == "UNKNOWN" or reported is None:
            return UNKNOWN
        if frame.values.get("door_polarity") == "CONFIRMED":
            # The frame names a level, but only the attestation says the name is
            # right; without it this is the device's *report*, not a physical
            # state, and the label says so instead of borrowing one.
            return OPEN_AS_REPORTED if reported == 1 else CLOSED_AS_REPORTED
        return UNKNOWN

    runs: list[dict] = []
    current: dict | None = None
    for index, frame in enumerate(frames):
        state = state_of(frame)
        if current is None or current["state"] != state:
            if current is not None:
                runs.append(current)
            current = {
                "state": state, "indexes": [index],
                "start_frame": frame, "end_frame": frame,
            }
        else:
            current["indexes"].append(index)
            current["end_frame"] = frame
    if current is not None:
        runs.append(current)

    events: list[dict] = []
    for position, run in enumerate(runs, start=1):
        indexes = run["indexes"]
        first, last = run["start_frame"], run["end_frame"]
        start_ms, end_ms = first.values.get("device_ms"), last.values.get("device_ms")
        duration = (
            round((end_ms - start_ms) / 1000.0, 3)
            if isinstance(start_ms, int) and isinstance(end_ms, int) else None
        )
        prev_run = runs[position - 2] if position > 1 else None
        ref = {}
        if prev_run is not None:
            for slot in run_export.CHAMBER_AIR_SLOTS:
                ref[slot] = _slot_mean(frames, prev_run["indexes"][-5:], slot)
        rise = _thermal_window(frames, [i for i in indexes if i in usable], ref)
        following = runs[position] if position < len(runs) else None
        recovery = {}
        if following is not None:
            recovery = {
                "following_state": following["state"],
                "following_reference_c": {
                    slot: _slot_mean(frames, following["indexes"][:30], slot)
                    for slot in run_export.CHAMBER_AIR_SLOTS
                },
            }
        not_because: list[str] = []
        details: dict[str, str] = {}
        physical = all(not f.provenance.is_physical_measurement is False for f in frames)
        if not physical:
            not_because.append("SOURCE_IS_NOT_A_PHYSICAL_MEASUREMENT")
        if not attestation_status["trustworthy"]:
            not_because.append("DOOR_MAPPING_NOT_ATTESTED_FOR_THIS_BOOT")
            details["DOOR_MAPPING_NOT_ATTESTED_FOR_THIS_BOOT"] = attestation_status["reason"]
        if run["state"] == UNKNOWN:
            not_because.append("DOOR_STATE_UNKNOWN_IS_NOT_A_NAMED_TRANSITION")
        if is_closed_state(run["state"]):
            # A closed door is the rest state. It is never the disturbance S2 is
            # about, whatever else is or is not attested.
            not_because.append("CLOSED_RUN_IS_A_REST_STATE_NOT_A_DISTURBANCE")
        if not operator_controlled:
            not_because.append("NO_OPERATOR_CONTROLLED_TIMING")
            details["NO_OPERATOR_CONTROLLED_TIMING"] = (
                "docs/05A §19 A-W10-02 wants a planned duration; an incidental window inside a "
                "commissioning stage is not a pilot disturbance"
            )
        if protocol_id is None:
            not_because.append("NO_PROTOCOL_ID_FOR_THIS_EVENT")
            details["NO_PROTOCOL_ID_FOR_THIS_EVENT"] = (
                "without a protocol id the run is not one of the planned trials"
            )
        if duration is not None and duration < timing_quantization()["minimum_resolvable_open_duration_s"]:
            not_because.append("DURATION_BELOW_THE_RESOLVABLE_FLOOR")
        if noise_floor_c:
            detectable = any(
                isinstance(rise.get(slot), dict) and isinstance(rise[slot].get("rise_c"), (int, float))
                and rise[slot]["rise_c"] >= noise_floor_c.get(slot, math.inf)
                for slot in run_export.CHAMBER_AIR_SLOTS
            )
            if not detectable:
                not_because.append("THERMAL_RISE_AT_OR_BELOW_THE_BASELINE_NOISE_FLOOR")
                details["THERMAL_RISE_AT_OR_BELOW_THE_BASELINE_NOISE_FLOOR"] = (
                    "see cg_w10_pairing.minimum_detectable_disturbance for the measured floor"
                )
        classification = "S2_PILOT_DISTURBANCE" if not not_because else (
            "NON_PHYSICAL_FIXTURE" if not physical else
            "STARTUP_POLARITY_PENDING" if run["state"] == UNKNOWN else
            "UNATTESTED_DOOR_TRANSITION" if not attestation_status["trustworthy"] else
            "INCIDENTAL_DOOR_TRANSITION"
        )
        events.append(DoorEvent(
            event_id=f"{first.boot_id}-{position:03d}-{run['state']}",
            boot_id=str(first.boot_id),
            run_id=first.run_id,
            state=run["state"],
            start_seq=first.seq,
            end_seq=last.seq,
            start_device_ms=start_ms,
            end_device_ms=end_ms,
            duration_s=duration,
            n_frames=len(indexes),
            cycles_reported_by_device=last.values.get("door_cycles"),
            thermal_rise=rise,
            recovery=recovery,
            event_class=classification,
            state_semantics=(
                "NAMED_BY_ATTESTED_PER_BOOT_MAPPING"
                if attestation_status["trustworthy"]
                else "REPORTED_BY_FRAME_ONLY_NOT_PHYSICALLY_NAMED"
            ),
            not_s2_because=tuple(not_because),
            not_s2_details=details,
            is_physical_measurement=physical,
            timing_uncertainty={
                "edge_uncertainty_s": 1.0,
                "duration_uncertainty_s": 1.0,
                "basis": "1 Hz frame stream; MC-38 50 ms debounce on a 10 ms poll",
            },
        ).as_dict())

    cycles_final = frames[-1].values.get("door_cycles")
    open_to_closed = sum(
        1 for a, b in zip(runs, runs[1:])
        if is_open_state(a["state"]) and is_closed_state(b["state"])
    )
    return {
        "tool_version": DOOR_TOOL_VERSION,
        "run_label": frames[0].provenance.run_label,
        "boot_ids": sorted({str(f.boot_id) for f in frames if f.boot_id}),
        "frames_total": len(frames),
        "frames_usable_for_s2": len(usable),
        "attestation": attestation_status,
        "polarity_inversion": polarity_inversion_check(frames),
        "timing": timing_quantization(),
        "state_run_counts": {
            run["state"]: len(run["indexes"]) for run in runs
        },
        "mc38_alignment_cross_check": {
            "detected_open_to_closed_transitions": open_to_closed,
            "device_reported_door_cycles": cycles_final,
            "aligned": (cycles_final == open_to_closed) if isinstance(cycles_final, int) else None,
            "meaning": (
                "MC-38 transitions are the machine ground truth only if the device's own cycle "
                "counter agrees with the detected edge count; a mismatch means an edge was missed"
            ),
        },
        "events": events,
        "s2_pilot_events": [e["event_id"] for e in events if e["event_class"] == "S2_PILOT_DISTURBANCE"],
        "unknown_is_not_closed": any(
            e["state"] == UNKNOWN and e["event_class"] != "S2_PILOT_DISTURBANCE" for e in events
        ) or UNKNOWN in [e["state"] for e in events],
        "honesty": [
            "door_open=UNKNOWN is kept as its own state and never renamed CLOSED",
            "an unattested segment is named *_AS_REPORTED, never OPEN or CLOSED: a reading "
            "is not a state until a per-boot attestation says it is",
            "an incidental OPEN window inside a commissioning stage is not an S2 pilot event",
            "thermal rise is measured on chamber-air slots; TEC_HOT_SIDE is reported separately",
            "a host fixture returns events, and every one of them says so",
        ],
    }


S2_CAPTURE_RECIPE: dict = {
    "status_label": "NEED_USER_ACTION",
    "why": (
        "no committed capture contains a protocolised, operator-timed door disturbance. The "
        "door-open events required by docs/05A §19 A-W10-03 have never been collected."
    ),
    "verified_data_position": {
        "committed_csv_capture": {
            "source": "evidence/A/W04/tec-cooling-response-600s.csv",
            "door_open_values": {"0": 940, "UNKNOWN": 17},
            "open_events": 0,
            "reading": "no OPEN event exists in the only committed thermal capture",
        },
        "local_untracked_h8_frames": {
            "note": (
                "H8 monitor frames exist on the bench host but are NOT git-tracked, so they are "
                "not citable evidence; they must be committed before any analysis uses them"
            ),
            "post_mount_300s_boot_eec9f67f": {
                "door_open_1_frames": 465,
                "polarity_command_sent": "DOOR NEAR_HIGH at 2026-11-01T09:10:24Z",
                "reading": (
                    "real MC-38 frames with a state change, but the polarity was set by a console "
                    "command on a different boot than the operator's later touch test, and the "
                    "same day's alignment record documents that NEAR_HIGH made the firmware echo "
                    "a stuck-high input as CLOSED. Classified UNATTESTED_DOOR_TRANSITION, not S2."
                ),
            },
            "mc38_direct_magnet_test": {
                "reading": (
                    "the only physically attested door-state evidence: operator-placed magnet, "
                    "NEAR_LOW confirmed at 2026-11-01T10:00:51Z, raw 1->0->1 with the sensor-only "
                    "posture (no ARM, no START, no TEC). Proves the switch works; contains no "
                    "thermal disturbance to measure."
                ),
            },
        },
    },
    "capture_recipe": {
        "run_id_prefix": "CG-S2-A-",
        "repetitions": 6,
        "per_repetition": [
            "confirm supervised attendance: the operator is at the bench for the whole "
            "repetition, with the stop-on-abnormal-current rule restated before ARM",
            "boot the board, open the capture BEFORE ARM, record boot_id",
            "operator attests the MC-38 mapping for THIS boot with `DOOR NEAR_LOW <token>`, then "
            "confirms the lid is seated and reads door_open=0 (CLOSED)",
            "hold a >=120 s CLOSED baseline at the target controller state",
            "open the door fully for the planned duration, starting the operator timer at the "
            "same instant the lid breaks the seal",
            "close the lid at the planned duration, keeping the timer reading",
            "record recovery until all chamber-air probes return within the pairing band or the "
            "stage deadline",
            "stop the capture, then write: planned duration, measured timer duration, operator, "
            "initial state, anomalies",
        ],
        "planned_durations_s": [15, 30, 60],
        "cadence": "1 Hz, unchanged from the shipped telemetry",
        "horizon_per_run_s": 900,
        "pairing_requirement": (
            "each S2 run needs a same-configuration S1 baseline pair within the frozen tolerance; "
            "collect the S1 pairs first or concurrently"
        ),
        "safety_prerequisites": [
            "supervised bench, operator at the board for the whole run",
            "TEC current path and fuse posture confirmed before any energized stage",
            "no door manipulation while a stage guard is uncertain",
            "stop on zero or abnormal current, exactly as in the H8 stage rules",
        ],
        "estimated_wall_time": (
            "6 disturbances x (120 s baseline + duration + <=900 s recovery) ~= 2.2 h of capture, "
            "plus 6 paired S1 baselines; split across at most two supervised sessions"
        ),
    },
}


def pilot_status(report: dict | None = None) -> dict:
    """The honest state of S2, and the exact recipe that would change it."""
    s2_events = len(report["s2_pilot_events"]) if report else 0
    return {
        "tool_version": DOOR_TOOL_VERSION,
        "status_label": S2_CAPTURE_RECIPE["status_label"],
        "s2_pilot_events_detected": s2_events,
        "valid_pilot_disturbances_target": ">=4-6 (docs/05A §19 A-W10-03)",
        "valid_pilot_disturbances_available": 0,
        "gap": "no protocolised door disturbance has ever been captured",
        "recipe": S2_CAPTURE_RECIPE,
        "is_physical_measurement": False,
        "note": (
            "this record describes what must be captured; it is not, and must never be quoted as, "
            "a disturbance measurement"
        ),
    }
