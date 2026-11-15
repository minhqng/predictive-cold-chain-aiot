"""ColdGuard W09 per-row validity, per-domain quality and invalidation logging.

docs/01 §19 closes the quality vocabulary at four names and warns that
``UNKNOWN must not silently become normal``. That warning is the whole point of
this module: a frame that cannot be qualified is reported as ``UNKNOWN`` with a
reason, not quietly promoted to a baseline sample.

Why quality is tracked **per domain** rather than as one flag per row. The
committed W04 capture makes the difference concrete: its electrical columns
carry an empty ``voltage_status``/``current_status`` in all 957 rows and it has
no ``power_status`` column at all, while its thermal columns all carry
``t{n}_status=OK``. One row-level flag would force a choice between two wrong
answers - discard real thermal data because an instrument was unqualified, or
pass electrical numbers onward because the probes were fine. Per-domain quality
says both truths at once: this capture is thermally usable and electrically
unqualified, and an S1 thermal baseline built from it may not cite energy.

What is checked, and why each rule is a rule rather than a preference:

* ``snapshot=INVALID`` - the producer already decided the frame is not a valid
  simultaneous sample set (docs/05A §18 A-W09-03 "missing key telemetry"). In the
  committed capture the first 17 rows are exactly this: nothing sampled yet, so
  the row is a startup artefact, not a cold-chain state.
* the ``missing``/``invalid``/``stale`` masks, decoded against the bit positions
  in ``firmware/h8-bench/main/h8_types.h``. The device names the failed source;
  using the row anyway would be inventing that source's value.
* per-field ``*_status`` - a number whose status is not ``OK`` is a contradiction
  and the number is dropped from statistics rather than trusted.
* unqualified electrical columns - empty is not ``OK``, so those values are
  retained for audit and excluded from qualified electrical statistics.
* door state ``UNKNOWN`` and polarity ``UNCONFIRMED`` - a door we cannot read is
  not a closed door, and an unreadable door cannot certify "no disturbance".
* a ``*_status`` **column the encoding does not carry at all** - reported as
  ``{FIELD}_STATUS_ABSENT`` at ``UNKNOWN``, so it blocks. Skipping an absent column
  reads as "qualified", which is the one thing docs/01 §19.4 forbids: the committed
  W04 CSV has no ``door_status``, ``air_c_status``, ``rh_pct_status`` or
  ``power_w_status`` column, and the honest verdict is that those domains cannot be
  qualified from it, not that they passed.
* the cooling state - ``docs/01`` §17.8 keeps ON and OFF apart from never having
  been observed, so a frame with no ``state`` gets ``COOLING_STATE_UNOBSERVED`` and
  leaves S1/S2. A zero duty cycle is not a substitute: an unstarted controller
  reports that too.
* the quality vocabulary itself - closed at four names. ``worst()`` ranks
  ``UNKNOWN`` when it recognises nothing instead of falling through to ``VALID``,
  a ``Reason`` refuses an unknown quality or domain where it is written, and
  ``domain_quality()`` requires its caller to name the domains it judged, so a
  domain nobody evaluated is ``UNKNOWN`` rather than ``VALID`` by default.
* the dedup key ``(device_id, boot_id, seq)`` (docs/02 §4.2/§4.3) - a duplicate
  is the same sample twice, a gap is a lost sample; both recorded, neither
  repaired by interpolation.
* session-class exclusions - ``PROBE_IDENTIFICATION`` frames are rejected by run
  label, so the rule survives a capture whose numbers look perfectly normal.
* provenance - a source declaring ``is_physical_measurement: false`` can never
  be valid as measurement data, whatever its fields say.

Invalid attempts are never deleted (A-W09-03): every row keeps its reasons and
the summary reports counts per reason and per domain so an operator can see
exactly what cost a run.
"""

from __future__ import annotations

import dataclasses

from cg_w09_capture_parser import (
    MASK_VALUE_FIELDS,
    PROBE_SLOTS,
    Frame,
    mask_names,
)

VALIDITY_CLASSIFIER_VERSION = "w09-validity-v3"

# Freshness windows from the H8 full-sensor contract (thermal/environment/power
# 3000 ms, door 1000 ms). Named here so a stale-without-mask case is still
# caught, and so the window a row was judged against is part of the record.
FRESHNESS_WINDOW_MS = {
    "thermal": 3000,
    "environment": 3000,
    "power": 3000,
    "door": 1000,
}

VALID = "VALID"
DEGRADED = "DEGRADED"
INVALID = "INVALID"
UNKNOWN = "UNKNOWN"
QUALITY_ORDER = (INVALID, UNKNOWN, DEGRADED, VALID)
BLOCKING_SEVERITIES = ("INVALID", "UNKNOWN")

# docs/01 §19.4: "Unknown must not silently become normal". A token outside this
# vocabulary is therefore an error at the point it enters the layer, not something
# a ranking loop can fall through.
KNOWN_QUALITIES = QUALITY_ORDER

DOMAINS = ("producer", "thermal", "environment", "electrical", "door", "sequence", "provenance")

# Domains a given scenario needs in order to call a row usable. Stating this as
# data is what stops "usable" from being a mood: S1 thermal work does not need a
# qualified PZEM, and an S4 response claim absolutely does. `provenance` is in
# every list because a host fixture is unusable for *any* scenario - a rule one
# earlier revision of this table got wrong, which is exactly the kind of hole a
# scenario-shaped allow-list invites.
SCENARIO_REQUIRED_DOMAINS = {
    "S1_NORMAL_BASELINE": ("provenance", "producer", "thermal", "environment", "door", "sequence"),
    "S2_DOOR_DISTURBANCE": ("provenance", "producer", "thermal", "door", "sequence"),
    "S3_THERMAL_EFFECTIVENESS_DEGRADATION": (
        "provenance", "producer", "thermal", "electrical", "sequence",
    ),
    "S4_ACTUATION_RESPONSE_FAULT": (
        "provenance", "producer", "thermal", "electrical", "sequence",
    ),
    "HEALTHY_ELECTRICAL_RANGES": ("provenance", "producer", "electrical", "sequence"),
}

# Session classes that must never enter S1/S2/S4 or a thermal-response
# statistic. Matched against the frame's run label and source note.
EXCLUDED_SESSION_CLASSES = ("PROBE_IDENTIFICATION", "TOUCH_IDENTIFICATION")

ELECTRICAL_VALUE_FIELDS = ("voltage_v", "current_a", "power_w", "energy_wh")
ELECTRICAL_STATUS_OF = {
    "voltage_v": "voltage_v_status",
    "current_a": "current_a_status",
    "power_w": "power_w_status",
    # energy_wh has no producer status in any shipped encoding; a number there
    # is an accumulator, not a qualified measurement.
    "energy_wh": None,
}
STATUS_FIELDS_BY_DOMAIN = {
    "thermal": [f"{slot}_status" for slot in PROBE_SLOTS],
    "environment": ["air_c_status", "rh_pct_status", "pressure_hpa_status"],
    "electrical": ["voltage_v_status", "current_a_status", "power_w_status"],
    "door": ["door_status"],
}
# Derived, not typed: a qualifier this layer watches has to have an absence code,
# so adding a status field cannot silently leave "column never arrived" unreported.
ABSENT_STATUS_CODES = tuple(sorted(
    f"{status_field.upper()}_ABSENT"
    for status_fields in STATUS_FIELDS_BY_DOMAIN.values()
    for status_field in status_fields
))
# The good-status token is not universal: probe/BME/PZEM readings report OK,
# while the door path is transcribed as reporting VALID. The driver that fixes
# that vocabulary is UNCITABLE_UNTRACKED_SOURCE (see cg_w10_door
# .DOOR_CONTACT_INVERSION), so both spellings are accepted here rather than
# one: judging door_status against OK alone would mark every healthy door frame
# in a real capture as a failure. The vocabulary is stated per domain instead of
# assumed once, and a door_status the encoding does not carry at all is reported
# as absent rather than quietly good.
GOOD_STATUS_BY_DOMAIN = {
    "thermal": ("OK",),
    "environment": ("OK",),
    "electrical": ("OK",),
    "door": ("VALID", "OK"),
}
# One shared name for "no tracked ref carries the source that would prove this".
# Owned by this layer because the S1 registry publishes it as a capture's
# eligibility, and a week's evidence must not import its vocabulary from the
# next week's module; W10's door analysis re-exports this same value.
UNCITABLE_UNTRACKED_SOURCE = "UNCITABLE_UNTRACKED_SOURCE"
DOMAIN_OF_MASK_SYMBOL = {
    "T1": "thermal", "T2": "thermal", "T3": "thermal", "SPARE": "thermal",
    "BME_T": "environment", "BME_RH": "environment", "BME_P": "environment",
    "DOOR": "door",
    "PZEM_V": "electrical", "PZEM_I": "electrical", "PZEM_P": "electrical",
    "HOT_BASE_ROLE": "thermal", "COLD_PLATE_ROLE": "thermal",
}
HARD_FAILURE_STATUSES = (
    "NOT_READ", "NO_PRESENCE", "CRC_FAIL", "IO_ERROR", "OUT_OF_RANGE",
    "POWER_ON_DEFAULT", "UNVERIFIED", "SENSOR_NOT_PRESENT", "NOT_ASSIGNED",
)
# docs/01 §17.8 separates cooling ON/OFF from a state that was never observed;
# §17.7 does the same for the door. A frame that does not speak for its TEC state
# must not be reusable as an "OFF" frame by default.
COOLING_STATE_VOCABULARY = ("ON", "OFF", "COOLING", "COOLDOWN", "IDLE", "STANDBY")


@dataclasses.dataclass(frozen=True)
class Reason:
    """One invalidation finding on one row, in the domain it belongs to."""

    code: str
    quality: str          # VALID | DEGRADED | INVALID | UNKNOWN
    domain: str           # one of DOMAINS
    detail: str
    doc_anchor: str
    field: str = ""

    def __post_init__(self) -> None:
        # A quality token this layer does not know would rank as "no finding"
        # anywhere it is read, so it is refused where it is written.
        if self.quality not in KNOWN_QUALITIES:
            raise ValueError(
                f"reason {self.code!r} carries unknown quality {self.quality!r}; "
                f"the vocabulary is closed at {', '.join(KNOWN_QUALITIES)}"
            )
        if self.domain not in DOMAINS:
            raise ValueError(f"reason {self.code!r} names unknown domain {self.domain!r}")

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        if not out["field"]:
            out.pop("field")
        return out


@dataclasses.dataclass(frozen=True)
class RowValidity:
    seq: int | None
    boot_id: str | None
    run_id: str | None
    quality: str
    quality_by_domain: dict
    usable_for: tuple[str, ...]
    reasons: tuple[Reason, ...]
    provenance: dict
    masked_fields: tuple[str, ...]

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "boot_id": self.boot_id,
            "run_id": self.run_id,
            "quality": self.quality,
            "quality_by_domain": dict(self.quality_by_domain),
            "usable_for": list(self.usable_for),
            "reasons": [reason.as_dict() for reason in self.reasons],
            "masked_fields": list(self.masked_fields),
            "source_kind": self.provenance.get("source_kind"),
            "source_path": self.provenance.get("source_path"),
            "line_index": self.provenance.get("line_index"),
            "is_physical_measurement": self.provenance.get("is_physical_measurement"),
        }


def worst(qualities: list[str]) -> str:
    """Rank a set of findings, fail-closed.

    Nothing recognised is not the same as nothing wrong: falling through to
    ``VALID`` here is how an unrecorded token silently became a normal row,
    which docs/01 §19.4 forbids outright.
    """
    for candidate in QUALITY_ORDER:
        if candidate in qualities:
            return candidate
    return UNKNOWN


def excluded_session_reasons(frame: Frame) -> list[Reason]:
    """Reject a frame by run label / session class, not by inspecting values."""
    haystack = " ".join(
        part for part in (
            frame.provenance.run_label or "",
            frame.provenance.note or "",
            str(frame.values.get("run_label") or ""),
            str(frame.values.get("session") or ""),
        ) if part
    ).upper()
    reasons: list[Reason] = []
    for token in EXCLUDED_SESSION_CLASSES:
        if token in haystack:
            reasons.append(Reason(
                code=f"EXCLUDED_SESSION_CLASS_{token}",
                quality=INVALID,
                domain="provenance",
                detail=(
                    f"session class {token!r} is excluded from S1/S2/S4 and from every "
                    "thermal-response statistic; frames there were taken with a hand on a probe"
                ),
                field="run_label",
                doc_anchor="docs/05A §18 A-W09-03; evidence/A/W07/probe-identification-v0.md",
            ))
    return reasons


def provenance_reasons(frame: Frame) -> list[Reason]:
    if frame.provenance.is_physical_measurement:
        return []
    return [Reason(
        code="NON_PHYSICAL_SOURCE",
        quality=INVALID,
        domain="provenance",
        detail=(
            "the source declares is_physical_measurement=false; it is host tooling evidence and "
            "may never be counted as a measurement"
        ),
        field="is_physical_measurement",
        doc_anchor="docs/05A §18 A-W09-03",
    )]


def snapshot_reasons(frame: Frame) -> list[Reason]:
    snapshot = frame.values.get("snapshot")
    if snapshot is None:
        return [Reason(
            code="SNAPSHOT_UNREPORTED",
            quality=UNKNOWN,
            domain="producer",
            detail="the source carries no snapshot field, so simultaneity is not known",
            field="snapshot",
            doc_anchor="docs/01 §19.4",
        )]
    if snapshot != "VALID":
        return [Reason(
            code="SNAPSHOT_INVALID",
            quality=INVALID,
            domain="producer",
            detail=f"producer reported snapshot={snapshot!r}",
            field="snapshot",
            doc_anchor="docs/01 §19.3; docs/05A §18 A-W09-03",
        )]
    return []


def mask_reasons(frame: Frame) -> tuple[list[Reason], list[str]]:
    reasons: list[Reason] = []
    masked: list[str] = []
    for mask_name, quality in (("missing", INVALID), ("invalid", INVALID), ("stale", DEGRADED)):
        mask = frame.values.get(mask_name)
        if mask is None:
            continue
        for symbol in mask_names(mask):
            field = MASK_VALUE_FIELDS.get(symbol, symbol)
            reasons.append(Reason(
                code=f"PROBE_{mask_name.upper()}",
                quality=quality,
                domain=DOMAIN_OF_MASK_SYMBOL.get(symbol, "producer"),
                detail=(
                    f"{mask_name}_mask bit for {symbol} is set; {field} is not usable in this row"
                ),
                field=field,
                doc_anchor="docs/01 §18.4; firmware/h8-bench/main/h8_types.h bit positions",
            ))
            if quality == INVALID and field not in masked:
                masked.append(field)
    if frame.values.get("missing") is None and frame.values.get("invalid") is None:
        reasons.append(Reason(
            code="MASKS_ABSENT",
            quality=DEGRADED,
            domain="producer",
            detail=(
                "this encoding carries no missing/invalid/stale masks; per-field status is the "
                "only failure signal available, so producer-side simultaneity rests on the "
                "snapshot flag alone"
            ),
            field="missing",
            doc_anchor="docs/01 §19.2 (a defined degraded path remains legal)",
        ))
    return reasons, masked


def status_reasons(frame: Frame) -> list[Reason]:
    reasons: list[Reason] = []
    for domain, status_fields in STATUS_FIELDS_BY_DOMAIN.items():
        for status_field in status_fields:
            field = status_field[: -len("_status")]
            if not frame.has(status_field):
                # The column does not exist in this encoding. That is not a pass:
                # a number with no producer qualifier anywhere is a number whose
                # quality nobody stated, and the domain has to be reported as
                # UNKNOWN so no scenario can silently consume it.
                reasons.append(Reason(
                    code=f"{status_field.upper()}_ABSENT",
                    quality=UNKNOWN,
                    domain=domain,
                    detail=(
                        f"this encoding carries no {status_field} column, so the {domain} "
                        "reading has no producer qualifier and its value cannot be treated as "
                        "qualified"
                    ),
                    field=status_field,
                    doc_anchor="docs/01 §19.4; docs/01 §18.4",
                ))
                continue
            value = frame.values.get(status_field)
            if value is None or value == "":
                continue  # handled by the unqualified-column rule
            good = GOOD_STATUS_BY_DOMAIN.get(domain, ("OK",))
            if value not in good:
                reasons.append(Reason(
                    code="FIELD_STATUS_NOT_OK",
                    quality=INVALID if value in HARD_FAILURE_STATUSES else DEGRADED,
                    domain=domain,
                    detail=(
                        f"{status_field}={value!r} while {field}={frame.values.get(field)!r}; "
                        "the numeric value is dropped rather than trusted"
                    ),
                    field=field,
                    doc_anchor="docs/01 §19.3; docs/01 §18.4",
                ))
                continue
            age = frame.values.get(f"{field}_age_ms")
            window = FRESHNESS_WINDOW_MS.get(domain)
            if isinstance(age, int) and window is not None and age > window:
                reasons.append(Reason(
                    code="FIELD_STALE_BY_AGE",
                    quality=DEGRADED,
                    domain=domain,
                    detail=f"{field}_age_ms={age} exceeds the {domain} window of {window} ms",
                    field=field,
                    doc_anchor="docs/01 §18.4 (staleness is not control freshness)",
                ))
    return reasons


def unqualified_electrical_reasons(frame: Frame) -> list[Reason]:
    """The empty-status electrical columns of the committed W04 CSV.

    A number with no producer status is not a qualified measurement. It stays in
    the file - nothing is deleted - but the row's *electrical* domain becomes
    UNKNOWN while its thermal domain is untouched.
    """
    reasons: list[Reason] = []
    for field, status_field in ELECTRICAL_STATUS_OF.items():
        if not frame.has(field):
            continue
        if frame.values.get(field) is None:
            reasons.append(Reason(
                code="ELECTRICAL_VALUE_MISSING",
                quality=INVALID,
                domain="electrical",
                detail=f"{field} is present as a column but carries no value",
                field=field,
                doc_anchor="docs/01 §19.4",
            ))
            continue
        if status_field is None:
            # energy_wh is an accumulator that no shipped encoding qualifies. It
            # is degraded, not unknown: it cannot make the *current* column any
            # less trustworthy, and blocking the whole electrical domain on it
            # would hide the one instrument S4 actually reads.
            reasons.append(Reason(
                code="ENERGY_ACCUMULATOR_UNQUALIFIED",
                quality=DEGRADED,
                domain="electrical",
                detail=(
                    f"{field} has no producer status field in any shipped encoding; the total is "
                    "retained for audit and must not be cited as a qualified power measurement"
                ),
                field=field,
                doc_anchor="docs/01 §19.2; docs/05A §18 A-W09-04",
            ))
            continue
        if frame.values.get(status_field) in (None, ""):
            reasons.append(Reason(
                code="ELECTRICAL_UNQUALIFIED",
                quality=UNKNOWN,
                domain="electrical",
                detail=(
                    f"{status_field} is empty/absent while {field} carries a number; empty is "
                    "not OK, so the value is unqualified"
                ),
                field=field,
                doc_anchor="docs/01 §19.4",
            ))
    return reasons


def door_reasons(frame: Frame) -> list[Reason]:
    """Door state and polarity. UNKNOWN is never read as CLOSED."""
    reasons: list[Reason] = []
    state = frame.values.get("door_open")
    polarity = frame.values.get("door_polarity")
    if state in (None, "UNKNOWN"):
        reasons.append(Reason(
            code="DOOR_STATE_UNKNOWN",
            quality=UNKNOWN,
            domain="door",
            detail=(
                f"door_open={state!r}; an unreadable door is not a closed door and cannot "
                "certify the absence of a disturbance"
            ),
            field="door_open",
            doc_anchor="docs/01 §19.4; docs/05A §19 A-W10-02",
        ))
    if polarity in (None, "UNCONFIRMED"):
        reasons.append(Reason(
            code="DOOR_POLARITY_UNCONFIRMED",
            quality=UNKNOWN,
            domain="door",
            detail=(
                f"door_polarity={polarity!r}; without a confirmed polarity the raw level cannot "
                "be named OPEN or CLOSED at all - docs/01 §8.2 forbids assuming either "
                "HIGH=OPEN or LOW=OPEN, and the two settings assign opposite states to the "
                "same raw level"
            ),
            field="door_polarity",
            doc_anchor="docs/01 §8.1/§8.2; docs/05A §19 A-W10-01/02",
        ))
    if frame.has("door_status"):
        value = frame.values.get("door_status")
        if value is None:
            # The column exists and says nothing. Absent qualification is not
            # satisfied qualification, so this blocks rather than degrades; the
            # case where the encoding carries no column at all is reported by
            # status_reasons() as DOOR_STATUS_ABSENT too, at the same severity.
            reasons.append(Reason(
                code="DOOR_STATUS_ABSENT",
                quality=UNKNOWN,
                domain="door",
                detail=(
                    "the door_status column is present but carries no value, so door freshness "
                    "is not knowable from the frame"
                ),
                field="door_status",
                doc_anchor="docs/01 §18.4; docs/01 §19.4",
            ))
        elif value not in ("OK", "VALID"):
            reasons.append(Reason(
                code="DOOR_STATUS_NOT_OK",
                quality=UNKNOWN,
                domain="door",
                detail=f"door_status={value!r}; the door reading is not qualified",
                field="door_status",
                doc_anchor="docs/01 §19.4",
            ))
    return reasons


def cooling_state_reasons(frame: Frame) -> list[Reason]:
    """docs/01 §17.8: cooling ON/OFF is a state; never observed is a third thing.

    Nothing in the checked vocabulary covered the TEC state, so a frame that did
    not report ``state`` at all stayed usable for S1 and S2 while a baseline built
    from it would silently describe an idle or a cooling device. A duty cycle is
    not a substitute: ``pwm_applied_permille=0`` is what an unstarted controller
    reports too.
    """
    if frame.has("state"):
        value = frame.values.get("state")
        if value not in (None, ""):
            if value not in COOLING_STATE_VOCABULARY:
                return [Reason(
                    code="COOLING_STATE_UNRECOGNISED",
                    quality=UNKNOWN,
                    domain="producer",
                    detail=(
                        f"state={value!r} is outside the documented cooling vocabulary "
                        f"{', '.join(COOLING_STATE_VOCABULARY)}; the TEC state is not known"
                    ),
                    field="state",
                    doc_anchor="docs/01 §17.8; docs/01 §19.4",
                )]
            return []
    return [Reason(
        code="COOLING_STATE_UNOBSERVED",
        quality=UNKNOWN,
        domain="producer",
        detail=(
            "the frame carries no cooling state, so whether the TEC was ON or OFF was never "
            "observed; that is not OFF and the row may not enter an S1/S2 statistic"
        ),
        field="state",
        doc_anchor="docs/01 §17.8; docs/01 §19.4",
    )]


def sequence_reasons(frames: list[Frame]) -> dict[int, list[Reason]]:
    """Duplicates and gaps on the (device_id, boot_id, seq) dedup key."""
    per_index: dict[int, list[Reason]] = {}
    seen: dict[tuple, int] = {}
    previous: tuple | None = None
    for index, frame in enumerate(frames):
        reasons: list[Reason] = []
        key = frame.dedup_key
        if key in seen:
            reasons.append(Reason(
                code="SEQ_DUPLICATE",
                quality=INVALID,
                domain="sequence",
                detail=(
                    f"dedup key {key!r} already seen at position {seen[key]}; a duplicate is the "
                    "same sample twice, not a second observation"
                ),
                field="seq",
                doc_anchor="docs/02 §4.2/§4.3",
            ))
        else:
            seen[key] = index
        if (
            previous is not None
            and previous[:2] == key[:2]
            and isinstance(previous[2], int)
            and isinstance(key[2], int)
            and key[2] - previous[2] > 1
        ):
            reasons.append(Reason(
                code="SEQ_GAP",
                quality=INVALID,
                domain="sequence",
                detail=(
                    f"seq jumped {previous[2]} -> {key[2]}; {key[2] - previous[2] - 1} frame(s) "
                    "are lost and were not interpolated"
                ),
                field="seq",
                doc_anchor="docs/02 §4.2/§4.3",
            ))
        previous = key
        if reasons:
            per_index[index] = reasons
    return per_index


def domain_quality(reasons: list[Reason], evaluated_domains: tuple[str, ...]) -> dict[str, str]:
    """Rank the domains that were actually evaluated, fail-closed.

    ``evaluated_domains`` has no default on purpose: a domain cannot be reported
    as VALID unless the caller has said it was judged. Anything not evaluated is
    UNKNOWN, because "did not check" must never read as "checked and clean".
    """
    out = {domain: UNKNOWN for domain in DOMAINS}
    for domain in evaluated_domains:
        if domain not in DOMAINS:
            raise ValueError(f"{domain!r} is not a domain of this layer")
        out[domain] = VALID
    for reason in reasons:
        if reason.domain not in out:
            out[reason.domain] = reason.quality
            continue
        if QUALITY_ORDER.index(reason.quality) < QUALITY_ORDER.index(out[reason.domain]):
            out[reason.domain] = reason.quality
    return out


def scenarios_usable(domain_quality: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        scenario
        for scenario, required in SCENARIO_REQUIRED_DOMAINS.items()
        if all(domain_quality.get(domain, UNKNOWN) not in BLOCKING_SEVERITIES for domain in required)
    )


def evaluate_frame(frame: Frame, extra_reasons: list[Reason] | None = None) -> RowValidity:
    """Classify one frame; never mutates it and never deletes it."""
    reasons: list[Reason] = []
    reasons.extend(provenance_reasons(frame))
    reasons.extend(excluded_session_reasons(frame))
    reasons.extend(snapshot_reasons(frame))
    mask_list, masked = mask_reasons(frame)
    reasons.extend(mask_list)
    reasons.extend(status_reasons(frame))
    reasons.extend(unqualified_electrical_reasons(frame))
    reasons.extend(door_reasons(frame))
    reasons.extend(cooling_state_reasons(frame))
    reasons.extend(extra_reasons or [])
    by_domain = domain_quality(reasons, DOMAINS)
    return RowValidity(
        seq=frame.values.get("seq"),
        boot_id=frame.boot_id,
        run_id=frame.run_id,
        quality=worst([reason.quality for reason in reasons] or [VALID]),
        quality_by_domain=by_domain,
        usable_for=scenarios_usable(by_domain),
        reasons=tuple(reasons),
        provenance=frame.provenance.as_dict(),
        masked_fields=tuple(masked),
    )


def evaluate_frames(frames: list[Frame]) -> list[RowValidity]:
    """Evaluate a whole capture, including cross-row sequence findings."""
    sequence = sequence_reasons(frames)
    return [
        evaluate_frame(frame, extra_reasons=sequence.get(index, []))
        for index, frame in enumerate(frames)
    ]


def summarize(validities: list[RowValidity]) -> dict:
    """Counts per reason code, per domain and per scenario.

    A reason that occurs zero times is still reported: "checked and found none"
    and "did not check" must not look the same in the record.
    """
    codes: dict[str, int] = {}
    quality: dict[str, int] = {VALID: 0, DEGRADED: 0, INVALID: 0, UNKNOWN: 0}
    by_domain: dict[str, dict[str, int]] = {
        domain: {VALID: 0, DEGRADED: 0, INVALID: 0, UNKNOWN: 0} for domain in DOMAINS
    }
    per_scenario: dict[str, int] = {scenario: 0 for scenario in SCENARIO_REQUIRED_DOMAINS}
    for row in validities:
        quality[row.quality] = quality.get(row.quality, 0) + 1
        for domain, value in row.quality_by_domain.items():
            by_domain.setdefault(domain, {VALID: 0, DEGRADED: 0, INVALID: 0, UNKNOWN: 0})
            by_domain[domain][value] = by_domain[domain].get(value, 0) + 1
        for scenario in row.usable_for:
            per_scenario[scenario] = per_scenario.get(scenario, 0) + 1
        for reason in row.reasons:
            codes[reason.code] = codes.get(reason.code, 0) + 1
    total = len(validities)
    thermal_usable = sum(
        1 for r in validities
        if "S1_NORMAL_BASELINE" in r.usable_for
    )
    # Reported under its own name, because it is not the same claim: rows whose
    # producer/thermal/sequence domains are clean are usable for a mixed-probe
    # thermal statistic even when a scenario needs a domain the encoding cannot
    # qualify. Letting the scenario count and this count share one label is how a
    # partial figure gets read as a full one (docs/01 §20.1).
    thermal_row_usable = sum(
        1 for r in validities
        if all(
            r.quality_by_domain.get(domain) not in BLOCKING_SEVERITIES
            for domain in ("producer", "thermal", "sequence")
        )
    )
    return {
        "rows_total": total,
        "rows_usable_for_baseline": thermal_usable,
        "rows_thermally_usable_for_statistics": thermal_row_usable,
        "rows_usable_per_scenario": per_scenario,
        "quality_counts": quality,
        "quality_counts_by_domain": by_domain,
        "reason_counts": codes,
        "reason_codes_checked": sorted([
            "NON_PHYSICAL_SOURCE", "EXCLUDED_SESSION_CLASS_PROBE_IDENTIFICATION",
            "SNAPSHOT_INVALID", "SNAPSHOT_UNREPORTED", "PROBE_MISSING", "PROBE_INVALID",
            "PROBE_STALE", "MASKS_ABSENT", "FIELD_STATUS_NOT_OK", "FIELD_STALE_BY_AGE",
            "ELECTRICAL_UNQUALIFIED", "ELECTRICAL_VALUE_MISSING",
            "ENERGY_ACCUMULATOR_UNQUALIFIED", "DOOR_STATE_UNKNOWN",
            "DOOR_POLARITY_UNCONFIRMED", "DOOR_STATUS_NOT_OK",
            "COOLING_STATE_UNOBSERVED", "COOLING_STATE_UNRECOGNISED",
            "SEQ_DUPLICATE", "SEQ_GAP",
        ] + list(ABSENT_STATUS_CODES)),
        "usable_fraction": round(thermal_usable / total, 6) if total else None,
        "classifier_version": VALIDITY_CLASSIFIER_VERSION,
        "blocking_severities": list(BLOCKING_SEVERITIES),
        "scenario_required_domains": {k: list(v) for k, v in SCENARIO_REQUIRED_DOMAINS.items()},
    }
