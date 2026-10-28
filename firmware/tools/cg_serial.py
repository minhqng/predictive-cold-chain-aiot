"""ColdGuard W02 serial-log parsing and analysis core (Member A).

This module is deliberately dependency-free (standard library only) so a
bench operator can run it with the same interpreter that ships with the
project tooling, and so its behaviour is testable without hardware.

It parses the firmware's machine line grammar (firmware/main/cg_log.h,
grammar version 1). Every machine line starts with ``#CG``. Anything else
- ESP-IDF boot noise, operator notes, an empty line - is counted but not
interpreted, so a raw Serial Monitor capture is never rewritten to fit the
parser.

Design rules that matter for evidence integrity:

* A temperature token of ``nan`` becomes ``None``. It never becomes 0.0.
* T1/T2/T3 carry explicit validity flags; the parser trusts the flags and
  the value together (a value with ``tN=0`` stays ``None``). The spare
  probe has no flag in grammar v1: its value token is the validity marker
  (a number is valid, ``nan`` is missing).
* Boot identity is grouped by ``#CG BOOT`` lines; ROM lines belong to the
  boot that precedes them.
* Nothing in this module invents samples, timestamps or ROM codes. If a
  field is absent, the corresponding result is ``None`` and the caller
  must report it as missing.
"""

from __future__ import annotations

import dataclasses
import math
import re
from typing import Iterable, Sequence

LOG_PREFIX = "#CG"
GRAMMAR_VERSION = 1

MEASUREMENT_ROLES = ("T1", "T2", "T3")
SPARE_ROLE = "SPARE"
ALL_ROLES = MEASUREMENT_ROLES + (SPARE_ROLE,)

_ROM_RE = re.compile(r"^[0-9A-Fa-f]{16}$")


@dataclasses.dataclass(frozen=True)
class Sample:
    """One ``#CG SAMPLE`` line: one real observation time."""

    index: int
    uptime_ms: int | None
    seq: int | None
    temps: dict[str, float | None]
    valid: dict[str, bool]
    thermal: str | None
    door_raw: int | None
    door_state: str | None

    def temp(self, role: str) -> float | None:
        return self.temps.get(role)

    @property
    def measurement_roles_valid(self) -> int:
        return sum(1 for role in MEASUREMENT_ROLES if self.valid.get(role))


@dataclasses.dataclass(frozen=True)
class RomLine:
    role: str
    rom: str
    present: bool
    status: str | None
    boot_index: int


@dataclasses.dataclass(frozen=True)
class DoorEdge:
    uptime_us: int
    raw: int
    boot_index: int


@dataclasses.dataclass(frozen=True)
class DoorStateLine:
    uptime_ms: int
    raw: int
    state: str
    transitions: int
    cycles: int
    discarded: int
    boot_index: int


@dataclasses.dataclass
class BootEntry:
    index: int
    boot_id: str | None = None
    boot_count: int | None = None
    roms: dict[str, RomLine] = dataclasses.field(default_factory=dict)
    rom_summary: dict[str, int] = dataclasses.field(default_factory=dict)

    def rom_of(self, role: str) -> str | None:
        line = self.roms.get(role)
        return line.rom if line else None

    def role_present(self, role: str) -> bool:
        line = self.roms.get(role)
        return bool(line and line.present)


@dataclasses.dataclass
class ParsedLog:
    banner: dict[str, str] | None = None
    safety: dict[str, str] | None = None
    door_polarity: dict[str, str] | None = None
    captures: list[dict[str, str]] = dataclasses.field(default_factory=list)
    boots: list[BootEntry] = dataclasses.field(default_factory=list)
    samples: list[Sample] = dataclasses.field(default_factory=list)
    door_edges: list[DoorEdge] = dataclasses.field(default_factory=list)
    door_states: list[DoorStateLine] = dataclasses.field(default_factory=list)
    errors: list[dict[str, str]] = dataclasses.field(default_factory=list)
    unknown_machine_lines: list[str] = dataclasses.field(default_factory=list)
    non_machine_lines: int = 0
    malformed_lines: list[str] = dataclasses.field(default_factory=list)

    @property
    def boot_count_observed(self) -> int:
        return len(self.boots)


def _fields(tokens: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        if sep:
            out[key] = value
    return out


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value, 10)
    except ValueError:
        return None


def _int_fraction(value: str | None) -> int | None:
    """Parse ``n/total`` (or a plain integer) as n.

    The firmware writes ``required_present=3/3`` because the denominator is
    part of the evidence: it states which canonical count the numerator
    refers to.
    """

    if value is None:
        return None
    return _int(value.split("/", 1)[0])


def _temp(value: str | None) -> float | None:
    if value is None or value.lower() in ("nan", "--", ""):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _bool_flag(value: str | None) -> bool:
    return value == "1"


def parse_text(text: str) -> ParsedLog:
    """Parse a raw serial capture into structured records.

    Unknown ``#CG`` kinds and malformed lines are preserved in the result
    instead of being dropped, so a grammar drift shows up as a finding.
    """

    log = ParsedLog()
    current_boot: BootEntry | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(LOG_PREFIX):
            log.non_machine_lines += 1
            continue

        parts = line.split()
        if len(parts) < 2:
            log.malformed_lines.append(raw_line)
            continue

        kind = parts[1]

        if kind == "LOG":
            log.banner = _fields(parts[2:])
        elif kind == "SAFETY":
            log.safety = _fields(parts[2:])
        elif kind == "BOOT":
            fields = _fields(parts[2:])
            current_boot = BootEntry(
                index=len(log.boots),
                boot_id=fields.get("boot_id"),
                boot_count=_int(fields.get("boot_count")),
            )
            log.boots.append(current_boot)
        elif kind == "ROM":
            fields = _fields(parts[2:])
            role = fields.get("role")
            rom = fields.get("rom")
            if role is None or rom is None or not _ROM_RE.match(rom):
                log.malformed_lines.append(raw_line)
                continue
            if current_boot is None:
                current_boot = BootEntry(index=len(log.boots), boot_id=None, boot_count=None)
                log.boots.append(current_boot)
            current_boot.roms[role] = RomLine(
                role=role,
                rom=rom.upper(),
                present=_bool_flag(fields.get("present")),
                status=fields.get("status"),
                boot_index=current_boot.index,
            )
        elif kind == "ROMS":
            fields = _fields(parts[2:])
            if current_boot is not None:
                current_boot.rom_summary = {
                    key: value
                    for key, value in ((k, _int_fraction(v)) for k, v in fields.items())
                    if value is not None
                }
        elif kind == "DOOR_POLARITY":
            log.door_polarity = _fields(parts[2:])
        elif kind == "CAPTURE":
            log.captures.append(_fields(parts[2:]))
        elif kind == "DOOR_EDGE":
            fields = _fields(parts[2:])
            uptime_us = _int(fields.get("uptime_us"))
            raw_level = _int(fields.get("raw"))
            if uptime_us is None or raw_level is None:
                log.malformed_lines.append(raw_line)
                continue
            log.door_edges.append(
                DoorEdge(
                    uptime_us=uptime_us,
                    raw=raw_level,
                    boot_index=current_boot.index if current_boot else 0,
                )
            )
        elif kind == "DOOR_STATE":
            fields = _fields(parts[2:])
            uptime_ms = _int(fields.get("uptime_ms"))
            if uptime_ms is None:
                log.malformed_lines.append(raw_line)
                continue
            log.door_states.append(
                DoorStateLine(
                    uptime_ms=uptime_ms,
                    raw=_int(fields.get("raw")) or 0,
                    state=fields.get("state", "UNVERIFIED"),
                    transitions=_int(fields.get("transitions")) or 0,
                    cycles=_int(fields.get("cycles")) or 0,
                    discarded=_int(fields.get("discarded")) or 0,
                    boot_index=current_boot.index if current_boot else 0,
                )
            )
        elif kind == "SAMPLE":
            fields = _fields(parts[2:])
            uptime_ms = _int(fields.get("uptime_ms"))
            if uptime_ms is None:
                log.malformed_lines.append(raw_line)
                continue
            temps: dict[str, float | None] = {}
            valid: dict[str, bool] = {}
            for role in ALL_ROLES:
                value = _temp(fields.get(role))
                if role == SPARE_ROLE:
                    # Grammar v1 prints no `tN` flag for the spare probe:
                    # the value token itself is the validity marker.
                    valid[role] = value is not None
                else:
                    valid[role] = _bool_flag(fields.get(f"t{role[-1].lower()}"))
                temps[role] = value if valid[role] else None
            log.samples.append(
                Sample(
                    index=len(log.samples),
                    uptime_ms=uptime_ms,
                    seq=_int(fields.get("seq")),
                    temps=temps,
                    valid=valid,
                    thermal=fields.get("thermal"),
                    door_raw=_int(fields.get("door_raw")),
                    door_state=fields.get("door"),
                )
            )
        elif kind == "ERR":
            log.errors.append(_fields(parts[2:]))
        else:
            log.unknown_machine_lines.append(raw_line)

    return log


def read_log(path: str) -> ParsedLog:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return parse_text(handle.read())


# --------------------------------------------------------------------------
# Inter-sensor consistency statistics (docs/05A A-W02-05)
# --------------------------------------------------------------------------


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _sample_sd(values: Sequence[float]) -> float | None:
    """Sample standard deviation, or ``None`` when it is undefined.

    One observation has no spread: reporting 0.0 would look like measured
    stability, so fewer than two values yields ``None`` (n/a in reports).
    """

    if len(values) < 2:
        return None
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def consistency_stats(samples: Sequence[Sample], roles: Sequence[str] = MEASUREMENT_ROLES) -> dict:
    """Per-probe statistics over the samples that carry a valid reading.

    ``n_valid`` and ``n_total`` are reported separately: a probe that was
    invalid for part of the window must not look like a full window.
    """

    stats: dict[str, dict] = {}
    for role in roles:
        values = [s.temps[role] for s in samples if s.temps.get(role) is not None]
        stats[role] = {
            "n_valid": len(values),
            "n_total": len(samples),
            "mean_c": _mean(values) if values else None,
            "sd_c": _sample_sd(values) if values else None,
            "min_c": min(values) if values else None,
            "max_c": max(values) if values else None,
            "range_c": (max(values) - min(values)) if values else None,
        }
    return stats


def pairwise_mean_differences(stats: dict, roles: Sequence[str] = MEASUREMENT_ROLES) -> dict:
    out: dict[str, float | None] = {}
    for i, first in enumerate(roles):
        for second in roles[i + 1 :]:
            a = stats[first]["mean_c"]
            b = stats[second]["mean_c"]
            # Label and value share one convention: "T1-T2" is
            # mean(T1) - mean(T2), as in sensor-consistency-summary.md.
            out[f"{first}-{second}"] = None if a is None or b is None else a - b
    return out


def max_disagreement(stats: dict, roles: Sequence[str] = MEASUREMENT_ROLES) -> float | None:
    means = [stats[role]["mean_c"] for role in roles]
    if any(mean is None for mean in means):
        return None
    return max(means) - min(means)


def effective_rate(samples: Sequence[Sample]) -> tuple[float | None, float | None]:
    """Duration (s) and effective rate (Hz) from real uptime stamps."""

    stamps = [s.uptime_ms for s in samples if s.uptime_ms is not None]
    if len(stamps) < 2:
        return None, None
    duration_s = (max(stamps) - min(stamps)) / 1000.0
    if duration_s <= 0:
        return duration_s, None
    return duration_s, (len(stamps) - 1) / duration_s


def sensor_csv_rows(samples: Sequence[Sample]) -> list[dict]:
    """CSV rows for sensor-consistency.csv.

    ``uptime_ms`` is the firmware's real observation clock. An invalid
    probe is an empty cell, never a number.
    """

    rows: list[dict] = []
    for sample in samples:
        row = {"uptime_ms": sample.uptime_ms, "seq": sample.seq}
        for role in MEASUREMENT_ROLES:
            row[f"t{role[-1].lower()}_c"] = sample.temps[role]
            row[f"{role.lower()}_valid"] = 1 if sample.valid.get(role) else 0
        row["thermal"] = sample.thermal
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# Reboot identity (docs/05A A-W02-03, docs/03 SEN-H1-02)
# --------------------------------------------------------------------------


def verify_reboot_identity(
    parsed: ParsedLog,
    min_boots: int = 5,
    roles: Sequence[str] = MEASUREMENT_ROLES,
) -> dict:
    """Check ROM->role stability across the boots seen in the capture.

    Beyond the per-role ROM map, the boot metadata must itself look like N
    distinct reboots: every boot needs a non-empty ``boot_id`` and the boot
    ids must be pairwise distinct (a duplicated block would otherwise count
    as five reboots), and every ``boot_count`` must be >= 1 and strictly
    increasing (a repeated or reset counter is flagged, not trusted).
    """

    boots = parsed.boots
    role_roms: dict[str, list[str | None]] = {}
    for role in roles:
        role_roms[role] = [boot.rom_of(role) for boot in boots]

    missing_boots: list[int] = []
    mismatches: list[dict] = []
    for role in roles:
        first_boot_index: int | None = None
        for boot in boots:
            rom = boot.rom_of(role)
            if rom is None or not boot.role_present(role):
                if boot.index not in missing_boots:
                    missing_boots.append(boot.index)
                continue
            if first_boot_index is None:
                first_boot_index = boot.index
            elif boots[first_boot_index].rom_of(role) != rom:
                mismatches.append(
                    {
                        "role": role,
                        "workspace_boot": first_boot_index,
                        "boot": boot.index,
                        "workspace_rom": boots[first_boot_index].rom_of(role),
                        "rom": rom,
                    }
                )

    duplicated_roms = []
    for boot in boots:
        by_rom: dict[str, list[str]] = {}
        for role, line in boot.roms.items():
            by_rom.setdefault(line.rom, []).append(role)
        for rom, assigned in by_rom.items():
            if len(assigned) > 1:
                duplicated_roms.append({"boot": boot.index, "rom": rom, "roles": sorted(assigned)})

    boot_metadata_issues: list[dict] = []
    seen_boot_ids: dict[str, int] = {}
    for boot in boots:
        boot_id = (boot.boot_id or "").strip()
        if not boot_id:
            boot_metadata_issues.append({"code": "BOOT_ID_MISSING", "boot": boot.index})
            continue
        key = boot_id.lower()
        if key in seen_boot_ids:
            boot_metadata_issues.append(
                {
                    "code": "BOOT_ID_DUPLICATED",
                    "boot": boot.index,
                    "first_boot": seen_boot_ids[key],
                    "boot_id": boot_id,
                }
            )
        else:
            seen_boot_ids[key] = boot.index

    previous_count: int | None = None
    for boot in boots:
        if boot.boot_count is None:
            boot_metadata_issues.append({"code": "BOOT_COUNT_MISSING", "boot": boot.index})
            continue
        if boot.boot_count < 1:
            boot_metadata_issues.append(
                {"code": "BOOT_COUNT_ZERO", "boot": boot.index, "boot_count": boot.boot_count}
            )
            continue
        if previous_count is not None and boot.boot_count <= previous_count:
            boot_metadata_issues.append(
                {
                    "code": "BOOT_COUNT_NOT_INCREASING",
                    "boot": boot.index,
                    "boot_count": boot.boot_count,
                    "previous_count": previous_count,
                }
            )
        previous_count = boot.boot_count

    if len(boots) < min_boots:
        verdict = "INSUFFICIENT_BOOTS"
    elif mismatches or duplicated_roms:
        verdict = "IDENTITY_MISMATCH"
    elif missing_boots:
        verdict = "ROLE_MISSING"
    elif boot_metadata_issues:
        verdict = "BOOT_METADATA_INVALID"
    else:
        verdict = "IDENTITY_STABLE"

    return {
        "verdict": verdict,
        "boots_observed": len(boots),
        "min_boots_required": min_boots,
        "roles": list(roles),
        "role_roms": role_roms,
        "boot_ids": [boot.boot_id for boot in boots],
        "boot_counts": [boot.boot_count for boot in boots],
        "boot_metadata_issues": boot_metadata_issues,
        "missing_boot_indices": missing_boots,
        "mismatches": mismatches,
        "duplicated_roms": duplicated_roms,
    }


# --------------------------------------------------------------------------
# Door analysis (docs/05A A-W02-07, docs/01 section 8)
# --------------------------------------------------------------------------


def door_boot_indices(parsed: ParsedLog) -> list[int]:
    """Boot indices that contributed at least one door line.

    A capture that spans several reboots mixes counters from different
    boots; the caller must select one boot (or refuse) instead of
    reporting a fused maximum.
    """

    return sorted(
        {line.boot_index for line in parsed.door_states}
        | {edge.boot_index for edge in parsed.door_edges}
    )


def door_analysis(
    parsed: ParsedLog, open_level: int | None, boot_index: int | None = None
) -> dict:
    """Door statistics from committed transitions and raw edges.

    ``open_level`` is the raw electrical level that the operator physically
    verified as OPEN. When it is ``None`` the semantic state stays
    UNVERIFIED and only raw-level counts are reported - the tool refuses to
    guess a polarity (docs/01 section 8.2).

    ``boot_index`` restricts the analysis to one ``#CG BOOT`` block. Use it
    when the capture contains door lines from more than one boot; otherwise
    the counters of separate sessions would be fused into one number.
    """

    states = [
        line for line in parsed.door_states if boot_index is None or line.boot_index == boot_index
    ]
    edges = [
        edge for edge in parsed.door_edges if boot_index is None or edge.boot_index == boot_index
    ]

    transitions = max([line.transitions for line in states], default=0)
    cycles = max([line.cycles for line in states], default=0)
    raw_edges = len(edges)
    discarded = max(transitions, raw_edges) - transitions if raw_edges >= transitions else 0

    edges_per_transition: list[int] = []
    if edges and states:
        # Attribute every raw edge to the transition it precedes.
        edge_index = 0
        for line in states:
            count = 0
            while edge_index < len(edges) and edges[edge_index].uptime_us <= line.uptime_ms * 1000:
                count += 1
                edge_index += 1
            edges_per_transition.append(count)

    open_intervals_ms: list[int] = []
    if open_level is not None:
        last_open_ms: int | None = None
        for line in states:
            is_open = line.raw == open_level
            if is_open:
                last_open_ms = line.uptime_ms
            elif last_open_ms is not None:
                open_intervals_ms.append(line.uptime_ms - last_open_ms)
                last_open_ms = None

    return {
        "semantic_mapping": "UNVERIFIED" if open_level is None else f"OPEN=raw{open_level}",
        "open_level": open_level,
        "committed_transitions": transitions,
        "committed_cycles": cycles,
        "raw_edges": raw_edges,
        "discarded_edges": discarded,
        "edges_per_transition": edges_per_transition,
        "bounce_observed": any(count > 1 for count in edges_per_transition),
        "max_edges_for_one_transition": max(edges_per_transition, default=0),
        "open_intervals_ms": open_intervals_ms,
        "first_edge_us": edges[0].uptime_us if edges else None,
        "last_edge_us": edges[-1].uptime_us if edges else None,
    }


def door_csv_rows(
    parsed: ParsedLog, open_level: int | None, boot_index: int | None = None
) -> list[dict]:
    """CSV rows for door-test.csv: one row per committed transition."""

    rows: list[dict] = []
    for line in parsed.door_states:
        if boot_index is not None and line.boot_index != boot_index:
            continue
        if open_level is None:
            state = "UNVERIFIED"
        else:
            state = "OPEN" if line.raw == open_level else "CLOSED"
        rows.append(
            {
                "uptime_ms": line.uptime_ms,
                "raw": line.raw,
                "state": state,
                "transitions": line.transitions,
                "cycles": line.cycles,
                "discarded_edges": line.discarded,
            }
        )
    return rows
