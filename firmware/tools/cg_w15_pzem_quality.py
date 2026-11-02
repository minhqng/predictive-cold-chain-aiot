"""W15 A-W15-01/02/03 - electrical producer quality and the A3 provenance table.

    py firmware/tools/cg_w15_pzem_quality.py [--bench-root DIR] [--json OUT.json]

Answers one question with recorded bytes: **can the PZEM-fed electrical features
be trusted as evidence, and which of them can be computed at all?**

Four audit families, each with the vocabulary the device itself used:

``missing / invalid responses``
    a frame whose electrical cell is empty, or whose own validity token is not
    ``OK``. The W03 host captures are the only sources that record a *failed*
    poll explicitly (7 of 601 rows are ``INVALID`` with ``physical_fail=1`` and
    ``received=29`` or ``28``); in the device-side captures a failed poll simply
    never reaches the frame stream, so "no sample" and "no value" are different
    statements and are kept apart here.

``cadence and freshness``
    the frame period (device_ms deltas) and the producer's own ``*_age_ms``
    token. The wire line reports the electrical sample as 636-666 ms old inside
    a 1 Hz frame; the committed CSV keeps the numbers and drops the ages, so
    freshness cannot be checked from it at all.

``transport classes``
    ``rx_len`` and ``class`` from the H7/H6 traces. A good poll is ``rx_len=25``
    (~86-111 ms). With the 12 V supply off the meter is silent - ``rx_len=0``,
    ``class=NO_RESPONSE`` - which is the expected behaviour of an unpowered
    meter, NOT a failed transceiver; this module records that so a reviewer
    cannot misread it.

``holdover patterns``
    the four register-latency classes from ``cg_w08_envelope.classify``, counted
    and listed, never averaged.

Then the A3 tables: the feature provenance (which dataset feature comes from
which register, under which validity condition, with or without authentic data)
and the run index (which captures actually contain command + applied + V/I/P +
thermal response, which is what Member B's electrical ablation needs).

Nothing here is ``PHYSICALLY_VERIFIED``: no measurement is taken and no
calibration is certified. A-W15-03 in particular can only report
plausibility/consistency, because no trusted independent meter exists in this
repository.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass

import cg_w08_envelope as envelope

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]

# docs/01 section 9.3 / firmware/tools/cg_modbus.py:37-52. The register is the
# provenance anchor for every electrical feature in the A3 table.
PZEM_REGISTERS = {
    "voltage_v": {"register": "input 0x0000", "lsb": envelope.VOLT_LSB, "unit": "V"},
    "current_a": {"register": "input 0x0001", "lsb": envelope.CURRENT_LSB, "unit": "A"},
    "power_w": {"register": "input 0x0002..0x0003 (low word first)",
                "lsb": envelope.POWER_LSB, "unit": "W"},
    "energy_wh": {"register": "input 0x0004..0x0005 (low word first)",
                  "lsb": envelope.ENERGY_LSB, "unit": "Wh"},
}
GOOD_RX_LEN = "25"
# A dead-but-honest meter: the 12 V supply was off, so nothing answers.
NO_RESPONSE_IS_EXPECTED_WHEN_UNPOWERED = True

TARGET_PERIOD_MS = 1000
LATE_TOLERANCE_MS = 250

STATUS_LABEL = "REAL_DATA_ANALYZED"
FORBIDDEN_STATUS = envelope.FORBIDDEN_STATUS
# docs/01 section 19: the quality vocabulary, verbatim. A source that publishes no
# status token at all is UNKNOWN here, never silently VALID.
QUALITY_ENUM = ("VALID", "DEGRADED", "INVALID", "UNKNOWN")


@dataclass
class ProvenanceRow:
    feature: str
    kind: str
    source_register: str
    producer_field: str
    validity_condition: str
    authentic_data_exists: str
    computable_now: str
    caveat: str
    status_label: str

    def as_row(self) -> dict[str, object]:
        return self.__dict__.copy()


# --------------------------------------------------------------------------
# per-source quality
# --------------------------------------------------------------------------

def cadence(frames: list[envelope.Frame]) -> dict[str, object]:
    """Deltas between consecutive frame clocks; the producer's own ages."""
    clocks = [f.clock_ms for f in frames if f.clock_ms is not None]
    gaps = [b - a for a, b in zip(clocks, clocks[1:]) if b >= a]
    late = [g for g in gaps if g > TARGET_PERIOD_MS + LATE_TOLERANCE_MS]
    early = [g for g in gaps if 0 <= g < TARGET_PERIOD_MS - LATE_TOLERANCE_MS]
    out: dict[str, object] = {
        "frames_with_clock": len(clocks),
        "gaps": len(gaps),
        "target_period_ms": TARGET_PERIOD_MS,
        "tolerance_ms": LATE_TOLERANCE_MS,
        "gap_median_ms": envelope.distribution(gaps).get("median"),
        "gap_max_ms": envelope.distribution(gaps).get("max"),
        "late_gaps": len(late),
        "early_gaps": len(early),
        "nonpositive_gaps": sum(1 for g in gaps if g <= 0),
    }
    for name in ("voltage", "current", "power"):
        ages = [f.ages_ms.get(name) for f in frames if f.ages_ms.get(name) is not None]
        real = [a for a in ages if a >= 0]
        # The device stamps -1 when the producer has no sample at all: the value
        # cell is empty and the status token reads IO_ERROR. It is a sentinel, not
        # an age, so it is counted separately instead of polluting the minimum.
        sentinels = [a for a in ages if a < 0]
        out[f"{name}_age_ms"] = envelope.distribution(real) if real else {"count": 0}
        out[f"{name}_age_sentinel_frames"] = len(sentinels)
    out["age_token_recorded"] = bool(
        any(f.ages_ms.get("current") is not None for f in frames)
    )
    return out


def response_quality(frames: list[envelope.Frame]) -> dict[str, object]:
    """Values present/absent, validity tokens, transport classes, retries."""
    with_value = [f for f in frames if f.current_a is not None]
    without = [f for f in frames if f.current_a is None]
    labels: dict[str, int] = {}
    for frame in frames:
        key = frame.status.get("current") or "(no token)"
        labels[key] = labels.get(key, 0) + 1
    classes: dict[str, int] = {}
    for frame in frames:
        token = frame.transport.get("class") or ""
        if token:
            classes[token] = classes.get(token, 0) + 1
    rx_lengths: dict[str, int] = {}
    for frame in frames:
        token = frame.transport.get("rx_len") or frame.transport.get("received") or ""
        if token:
            rx_lengths[token] = rx_lengths.get(token, 0) + 1
    return {
        "frames": len(frames),
        "frames_with_current_value": len(with_value),
        "frames_without_any_electrical_value": len(without),
        "current_status_token_counts": dict(sorted(labels.items())),
        "non_ok_status_frames": sum(count for token, count in labels.items()
                                    if token not in ("OK", "CRC_VALID", "(no token)")),
        "transport_class_counts": dict(sorted(classes.items())),
        "rx_len_counts": dict(sorted(rx_lengths.items())),
        "good_poll_rx_len": GOOD_RX_LEN,
        "rx_len_semantics": (
            "not comparable across collectors: the device-side H6/H7 trace counts "
            "echo + response (a good poll is rx_len=25 there), while the W03 host "
            "collector counts its own received length (28-29 observed). A threshold "
            "must never be shared between the two."
        ),
        "no_response_expected_when_unpowered": NO_RESPONSE_IS_EXPECTED_WHEN_UNPOWERED,
        "absence_reason": absence_reason(with_value, without, labels),
    }


def absence_reason(with_value: list[envelope.Frame], without: list[envelope.Frame],
                   labels: dict[str, int]) -> str:
    """Why values are missing - the distinction A-W15-01 is actually about."""
    if not without:
        return "no missing samples in this source"
    if not with_value:
        if labels.get("INVALID") or labels.get("NO_DATA"):
            return ("every frame is explicitly labelled without data: the producer "
                    "is off, which is a declared absence, not a lost sample")
        return "no electrical value published in any frame"
    if labels.get("IO_ERROR"):
        return ("producer read failures: the value cell is empty, the status token "
                "reads IO_ERROR and the age token reads -1 (sentinel)")
    if labels.get("INVALID"):
        return "host-side poll failures recorded explicitly with physical_fail=1"
    return "rows without a value carry no token explaining the absence"


def holdover_quality(frames: list[envelope.Frame]) -> dict[str, object]:
    counts: dict[str, int] = {}
    for frame in frames:
        counts[frame.classification] = counts.get(frame.classification, 0) + 1
    return {
        "classification_counts": dict(sorted(counts.items())),
        "latency_frames": sum(counts.get(c, 0) for c in envelope.LATENCY_CLASSES),
        "duty_zero_above_floor_frames": sum(
            1 for f in frames
            if f.duty_applied == 0 and (f.current_a or 0.0) > envelope.OFF_STEADY_MAX_A
        ),
        "driven_zero_current_frames": sum(
            1 for f in frames if f.driven and f.current_a == 0.0
        ),
    }


def audit_source(frames: list[envelope.Frame], source: str, trust: str,
                 file_path: str) -> dict[str, object]:
    return {
        "source": source,
        "trust": trust,
        "file": file_path,
        "reproducible_from_git": trust == "COMMITTED",
        "cadence": cadence(frames),
        "response_quality": response_quality(frames),
        "holdover": holdover_quality(frames),
        "power_consistency": envelope.power_consistency(frames),
        "energy_consistency": envelope.energy_consistency(frames),
        "status_coverage": envelope.status_coverage(frames)[source],
    }


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    """The audit summary, recomputed from whatever source rows are present."""
    return {
        "sources": len(rows),
        "frames_total": sum(r["response_quality"]["frames"] for r in rows),
        "frames_without_electrical_value": sum(
            r["response_quality"]["frames_without_any_electrical_value"] for r in rows),
        "explicit_producer_failures": sum(
            r["response_quality"]["non_ok_status_frames"] for r in rows),
        "io_error_frames": sum(
            r["response_quality"]["current_status_token_counts"].get("IO_ERROR", 0)
            for r in rows),
        "latency_frames_total": sum(r["holdover"]["latency_frames"] for r in rows),
        "power_consistency_mismatch_frames": sum(
            r["power_consistency"]["frames_beyond_tolerance_count"] for r in rows),
        "max_abs_v_times_i_delta_w": max(
            (r["power_consistency"]["max_abs_delta_w"] or 0.0 for r in rows),
            default=None),
        "tolerance_w": envelope.r(envelope.POWER_TOLERANCE_W),
        "sources_without_age_token": sorted(
            r["source"] for r in rows if not r["cadence"]["age_token_recorded"]),
        "sources_without_validity_token": sorted(
            r["source"] for r in rows
            if not r["status_coverage"]["electrical_status_recorded"]),
    }


_TOKEN_RE = re.compile(r"(\w+)=(\S+)")


def read_raw_quality(path: pathlib.Path) -> list[dict[str, str]]:
    """Pull the device's own quality tokens out of each raw monitor line.

    The parsed JSON object drops the ``missing``/``invalid``/``stale`` bitmasks and
    the electrical ages, but the ``raw`` string carries them. This is the only
    place W15 reads the bitmasks, and it reports them verbatim.
    """
    polls: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        tokens = dict(_TOKEN_RE.findall(str(record.get("raw", ""))))
        if tokens:
            polls.append(tokens)
    return polls


# --------------------------------------------------------------------------
# clock semantics: which clock is the sample time
# --------------------------------------------------------------------------

def clock_semantics(sources: dict[str, list[envelope.Frame]]) -> dict[str, object]:
    """Which clock each source carries, and the host-vs-device boundary.

    ``device_ms`` is per-boot uptime and opening the COM port starts a new
    ``boot_id``, so a host wall-clock stamp taken at receipt cannot establish a
    sample's or a command's original age; unverifiable absolute expiry therefore
    has to fail closed. This function exists to keep that rule visible in the
    data rather than only in prose.
    """
    per_source: dict[str, object] = {}
    for source, frames in sorted(sources.items()):
        clocks = [f.clock_ms for f in frames if f.clock_ms is not None]
        per_source[source] = {
            "device_clock": "device_ms" if clocks else "absent",
            "device_ms_frames": len(clocks),
            "device_ms_monotonic_non_decreasing": all(
                b >= a for a, b in zip(clocks, clocks[1:])),
            "boot_id_partitions_frames": sorted({f.snapshot for f in frames if f.snapshot}) or
                                         ["(no boot id in this source)"],
            "host_wall_clock_used_as_sample_time": False,
            "note": ("device_ms is per-boot uptime; a host timestamp is not device "
                     "time, so no age or TTL here is claimed in absolute terms"),
        }
    return {
        "authoritative_device_time": "device_ms within boot_id + seq (docs/01 18.3)",
        "stale_is_not_invalid": "docs/01 18.4: historical validity != control freshness",
        "clock_uncertainty_rule": ("docs/01 18.5: record uptime and sequence; do not "
                                   "manufacture false timestamp precision"),
        "ttl_at_receipt_rule": ("a TTL measured on arrival does not establish a "
                                "command's original age; unverifiable absolute "
                                "expiry fails closed"),
        "raw_declares_no_wall_clock": True,
        "per_source": per_source,
    }


# --------------------------------------------------------------------------
# zero versus absent, and ON/OFF consistency
# --------------------------------------------------------------------------

def zero_vs_absent(sources: dict[str, list[envelope.Frame]]) -> dict[str, object]:
    """docs/01 1.10-1.12: 0.0 A is a measurement, an empty cell is not."""
    out: dict[str, object] = {}
    for source, frames in sorted(sources.items()):
        columns: dict[str, object] = {}
        for name in envelope.ELECTRICAL_FIELDS:
            attr = envelope.VALUE_ATTR[name]
            present = sum(1 for f in frames if getattr(f, attr) is not None)
            explicit_zero = sum(1 for f in frames
                                if getattr(f, attr) is not None and float(
                                    getattr(f, attr)) == 0.0)
            label_counts: dict[str, int] = {}
            for frame in frames:
                key = frame.status.get(name) or "(empty status)"
                label_counts[key] = label_counts.get(key, 0) + 1
            columns[name] = {
                "present": present,
                "explicit_zero_with_value": explicit_zero,
                "absent_or_unparseable": len(frames) - present,
                "status_label_counts": dict(sorted(label_counts.items())),
                "status_token_present": any(k != "(empty status)" for k in label_counts),
            }
        out[source] = columns
    return out


def _anomaly(source: str, frame: envelope.Frame, kind: str) -> dict[str, object]:
    return {
        "kind": kind,
        "source": source,
        "seq": frame.seq,
        "clock_ms": envelope.r(frame.clock_ms, 0),
        "duty_applied_permille": frame.duty_applied,
        "current_a": envelope.r(frame.current_a),
        "classification": frame.classification,
        "electrical_status_recorded": bool(frame.status.get("voltage")
                                           and frame.status.get("current")
                                           and frame.status.get("power")),
    }


ZERO_DUTY_FOLLOW_FRAMES = 6

ZERO_DUTY_TRACE_NOTE = (
    "the recorded sequence is what the PZEM itself reported while the applied duty "
    "stayed 0; no independent instrument stands behind it, so it does not verify that "
    "the branch was de-energized and it does not settle the anomaly classification"
)


def zero_duty_follow_through(frames: list[envelope.Frame],
                             index: int) -> dict[str, object]:
    """The recorded duty-0 frames after an applied-OFF-with-current frame.

    The operator's 2026-11-02 correction asked for the whole decay to be recorded
    instead of only the first held frame: for the committed 600 s capture the applied
    duty stays 0 while the reported current falls 7.15 -> 0.56 -> 0.02 -> 0.0 A and
    reaches zero at device_ms=829894. Nothing is interpolated here - each value is the
    frame as recorded, and the walk stops at the first frame whose applied duty is not
    0 (or that carries no applied duty at all), so a re-energized branch can never be
    read as part of the decay.
    """
    trace: list[dict[str, object]] = []
    for follow in frames[index + 1:index + 1 + ZERO_DUTY_FOLLOW_FRAMES]:
        if follow.duty_applied != 0 or follow.current_a is None:
            break
        trace.append({"device_ms": envelope.r(follow.clock_ms, 0),
                      "current_a": envelope.r(follow.current_a)})
        if follow.current_a == 0.0:
            break  # the decay is recorded up to the first zero, no further
    returns_to_zero = next((t["device_ms"] for t in trace if t["current_a"] == 0.0),
                            None)
    return {
        "frames_after_suspect": trace,
        "zero_duty_current_sequence_a": (
            [envelope.r(frames[index].current_a)] + [t["current_a"] for t in trace]),
        "current_returns_to_zero_at_device_ms": returns_to_zero,
        "applied_duty_stayed_zero_throughout": (
            returns_to_zero is not None or bool(trace)),
        "trace_provenance": ZERO_DUTY_TRACE_NOTE,
    }


def on_off_consistency(sources: dict[str, list[envelope.Frame]]) -> dict[str, object]:
    """Applied duty against measured current, per frame.

    A commanded-OFF frame that still carries drive-level current is reported as a
    candidate anomaly and is never averaged into a peak: whether it is a
    CONTROL_ELECTRICAL_ANOMALY or a PZEM register holdover is a firmware and
    operator call, not a host-tool call.
    """
    buckets = {
        "applied_on_current_flows": 0,
        "applied_on_current_zero": 0,
        "applied_on_current_at_or_below_floor": 0,
        "applied_off_current_above_floor": 0,
        "applied_off_current_at_or_below_floor": 0,
        "commanded_on_but_applied_zero": 0,
        "commanded_and_applied_differ": 0,
    }
    anomalies: list[dict[str, object]] = []
    for source, frames in sorted(sources.items()):
        for index, frame in enumerate(frames):
            applied, req, current = frame.duty_applied, frame.duty_req, frame.current_a
            if applied is None or current is None:
                continue
            if req is not None and req != applied:
                buckets["commanded_and_applied_differ"] += 1
                if req > 0 and applied == 0:
                    buckets["commanded_on_but_applied_zero"] += 1
            if applied > 0:
                if current > envelope.OFF_STEADY_MAX_A:
                    buckets["applied_on_current_flows"] += 1
                elif current == 0.0:
                    buckets["applied_on_current_zero"] += 1
                    anomalies.append(_anomaly(source, frame, "APPLIED_ON_ZERO_CURRENT"))
                else:
                    buckets["applied_on_current_at_or_below_floor"] += 1
            else:
                if current > envelope.OFF_STEADY_MAX_A:
                    buckets["applied_off_current_above_floor"] += 1
                    anomaly = _anomaly(
                        source, frame, "APPLIED_OFF_CURRENT_ABOVE_FLOOR")
                    # Record the whole decay the operator confirmed, not only the
                    # first held frame: which frames followed while the applied duty
                    # stayed 0, and where the reported current reached zero.
                    anomaly.update(zero_duty_follow_through(frames, index))
                    anomalies.append(anomaly)
                else:
                    buckets["applied_off_current_at_or_below_floor"] += 1
    return {
        "buckets": buckets,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "status_label": "REAL_DATA_ANALYZED",
        "zero_duty_trace_provenance": ZERO_DUTY_TRACE_NOTE,
        "note": ("APPLIED_OFF_CURRENT_ABOVE_FLOOR frames are candidate anomalies only, "
                 "and two explanations compete without this host tool choosing "
                 "between them: the canonical safety class CONTROL_ELECTRICAL_ANOMALY "
                 "(docs/01 22.4 'Commanded OFF + unexpected current' and 23.4 'current "
                 "while state should be OFF', high severity), and the register-holdover "
                 "reading in which the same values merely repeat the preceding driven "
                 "frame. The anomaly option stays open, exactly as docs/01 23.5 "
                 "prefers UNKNOWN over invented certainty"),
    }


def quality_bitmasks(bench_root: pathlib.Path | None,
                     repo_root: pathlib.Path) -> dict[str, object]:
    """Count the device's own missing/invalid/stale bits without interpreting them.

    The bit positions are not documented in this repository (docs/01 18.4 requires
    that stale be tracked but does not fix the encoding), so the observed token
    values and their poll counts are reported verbatim and the interpretation gap
    is stated instead of guessed.
    """
    per_source: dict[str, object] = {}
    if bench_root is not None and bench_root.is_dir():
        for rel, label, _regime in envelope.H8_SESSIONS:
            path = bench_root / rel
            if not path.is_file():
                continue
            polls = read_raw_quality(path)
            if not polls:
                continue
            entry: dict[str, object] = {}
            for name in ("missing", "invalid", "stale"):
                counts: dict[str, int] = {}
                for poll in polls:
                    key = poll.get(name, "(absent)")
                    counts[key] = counts.get(key, 0) + 1
                entry[name] = {"distinct_token_values": dict(sorted(counts.items())),
                               "polls": len(polls)}
            entry["timestamp_utc_source_values"] = sorted(
                {p.get("timestamp_utc_source", "(absent)") for p in polls})
            per_source[label] = entry
    return {
        "bit_position_meaning_documented_in_repo": False,
        "policy": ("report the device-declared bitmask verbatim; do not map bits to "
                   "meanings this repository does not define"),
        "per_source": per_source,
    }


def assert_no_physical_status(report: object) -> None:
    """Refuse any output that carries the physical-verification label."""
    if FORBIDDEN_STATUS in json.dumps(report, sort_keys=True, default=str):
        raise ValueError(f"{FORBIDDEN_STATUS} must never be emitted by "
                         "cg_w15_pzem_quality")


def audit(repo_root: pathlib.Path, bench_root: pathlib.Path | None) -> dict[str, object]:
    sources = envelope.load_sources(repo_root, bench_root)
    rows = [
        audit_source(frames, source,
                     "COMMITTED" if source in envelope.COMMITTED_SOURCES else "LOCAL_BENCH",
                     envelope.source_files(repo_root, bench_root).get(source, ""))
        for source, frames in sorted(sources.items())
    ]
    return {
        "schema": "cg-w15-pzem-quality-1",
        "status_label": "REAL_DATA_ANALYZED",
        "pzem_registers": PZEM_REGISTERS,
        "cadence_target_ms": TARGET_PERIOD_MS,
        "sources": rows,
        "summary": summarize(rows),
        "clock_semantics": clock_semantics(sources),
        "zero_vs_absent": zero_vs_absent(sources),
        "on_off_consistency": on_off_consistency(sources),
        "quality_bitmasks": quality_bitmasks(bench_root, repo_root),
    }


# --------------------------------------------------------------------------
# A3 feature provenance
# --------------------------------------------------------------------------

def a3_provenance(audit_report: dict[str, object]) -> list[ProvenanceRow]:
    """feature -> register -> validity condition -> is there authentic data?

    ``authentic_data_exists`` is answered from the audit itself, not from
    memory: a feature is only backed by data if some source publishes the value
    with a validity token, and the source names are carried into the row.
    """
    def sources_with(attr: str, qualified: bool = True) -> list[str]:
        out = []
        for row in audit_report["sources"]:
            coverage = row["status_coverage"]
            column = coverage["columns"].get(attr, {})
            has_values = column.get("frames_with_a_value", 0)
            ok = column.get("frames_with_a_value_and_OK_label", 0)
            if not isinstance(has_values, int) or has_values <= 0:
                continue
            if qualified and ok <= 0:
                continue
            out.append(row["source"])
        return out

    qualified_voltage = sources_with("voltage")
    qualified_current = sources_with("current")
    qualified_power = sources_with("power")
    qualified_energy = sources_with("energy")
    any_energy = sources_with("energy", qualified=False)

    rows = [
        ProvenanceRow(
            feature="branch_voltage_v", kind="raw",
            source_register=PZEM_REGISTERS["voltage_v"]["register"]
                            + f", {envelope.VOLT_LSB} V/count",
            producer_field="voltage_v (+ voltage_v_status, voltage_v_age_ms on the "
                           "bench wire; voltage_status in the delivered schema)",
            validity_condition="status token == OK AND age within the acquisition "
                               "period AND the frame is not a register-latency frame",
            authentic_data_exists=f"YES in {len(qualified_current) or len(qualified_voltage)}"
                                  f"-qualified sources: {', '.join(qualified_voltage)}",
            computable_now="YES",
            caveat="the committed 600 s CSV publishes the number with an EMPTY "
                   "status cell, so its voltage values are unqualified",
            status_label="REAL_DATA_ANALYZED",
        ),
        ProvenanceRow(
            feature="branch_current_a", kind="raw",
            source_register=PZEM_REGISTERS["current_a"]["register"]
                            + f", {envelope.CURRENT_LSB} A/count",
            producer_field="current_a (+ current_a_status, current_a_age_ms)",
            validity_condition="same as voltage; plus the 50 A shunt profile "
                               "(holding 0x0003) is what the readback recorded",
            authentic_data_exists=f"YES: {', '.join(qualified_current)}",
            computable_now="YES",
            caveat="the PZEM current register lags one integration cycle, so the "
                   "first post-OFF frame repeats the loaded value; that frame is a "
                   "latency artefact, not a measurement",
            status_label="REAL_DATA_ANALYZED",
        ),
        ProvenanceRow(
            feature="branch_power_w", kind="raw",
            source_register=PZEM_REGISTERS["power_w"]["register"]
                            + f", {envelope.POWER_LSB} W/count",
            producer_field="power_w (+ power_w_status, power_w_age_ms)",
            validity_condition="status OK; note the delivered CSV builder never "
                               "emitted a power status column at all",
            authentic_data_exists=f"YES: {', '.join(qualified_power)}",
            computable_now="YES",
            caveat="true power, not V x I; agreement with V x I was checked per "
                   "frame and stayed inside register quantisation",
            status_label="REAL_DATA_ANALYZED",
        ),
        ProvenanceRow(
            feature="accumulated_energy_wh", kind="raw",
            source_register=PZEM_REGISTERS["energy_wh"]["register"]
                            + f", {envelope.ENERGY_LSB} Wh/count",
            producer_field="energy_wh ONLY - no status token and no age token exist "
                           "on the bench wire",
            validity_condition="NONE PUBLISHED: the value arrives with no validity "
                               "companion, so it cannot be qualified at all",
            authentic_data_exists=f"values exist in {', '.join(any_energy)} but NONE "
                                  f"of them are qualified "
                                  f"(qualified sources: {', '.join(qualified_energy) or 'none'})",
            computable_now="NO (unqualified)",
            caveat="1 Wh quantum at ~85 W updates roughly every 42 s, so it cannot "
                   "resolve a short run, and it never decreases inside a boot",
            status_label="REAL_DATA_ANALYZED",
        ),
        ProvenanceRow(
            feature="v_times_i_power_w", kind="derived",
            source_register="computed from input 0x0000 x 0x0001",
            producer_field="not published by the device; host-side only",
            validity_condition="both operands qualified and the frame is DRIVEN",
            authentic_data_exists="YES for the raw operands; the derived column "
                                  "agrees with reported power inside quantisation",
            computable_now="YES",
            caveat="a consistency check, never a replacement for the power register",
            status_label="REAL_DATA_ANALYZED",
        ),
        ProvenanceRow(
            feature="energy_delta_wh", kind="derived",
            source_register="difference of input 0x0004..0x0005 across a run",
            producer_field="host-side, from energy_wh",
            validity_condition="same boot_id, monotonic counter, run boundaries known",
            authentic_data_exists="YES: committed 600 s capture 108 -> 122 Wh "
                                  "(delta 14 Wh) against a 14.219 Wh trapezoidal "
                                  "integral of power",
            computable_now="YES, but resolution-limited",
            caveat="the counter has no validity token; a 14 Wh delta carries a "
                   "+-1 Wh quantum on each end, so 42 s of run time is the smallest "
                   "interval it can speak about",
            status_label="REAL_DATA_ANALYZED",
        ),
        ProvenanceRow(
            feature="specific_power_w_per_kelvin", kind="derived",
            source_register="power register / thermal channels",
            producer_field="host-side",
            validity_condition="power qualified AND the thermal channel OK AND the "
                               "sensor position frozen",
            authentic_data_exists="PARTIAL - one 600 s committed run at one duty "
                                  "level only",
            computable_now="NO for a duty-resolved model",
            caveat="duty-resolved power/temperature needs the ladder, which is "
                   "local-bench only, and W07 repeatability, which is not in this "
                   "checkout",
            status_label="TEAM_DEPENDENCY",
        ),
        ProvenanceRow(
            feature="power_factor / frequency", kind="raw-register-not-published",
            source_register="input 0x0006 (power factor) / 0x0007 (frequency) on the "
                            "PZEM-017 - NOT read by this firmware, which reads 6 "
                            "input registers (cg_modbus.py INPUT_REGISTER_COUNT)",
            producer_field="absent from every frame of every source",
            validity_condition="n/a",
            authentic_data_exists="NO",
            computable_now="NO",
            caveat="a DC branch through an IBT-2 makes power factor meaningless "
                   "anyway; the register was never read and no capture carries it",
            status_label="BLOCKED_HARDWARE",
        ),
        ProvenanceRow(
            feature="electrical_quality / producer liveness", kind="derived",
            source_register="host-side classification of the frames",
            producer_field="power_validity + electrical_quality + power_beats + "
                           "power_max_gap_ms in the delivered schema (W05)",
            validity_condition="requires the delivered schema's liveness counters, "
                               "which the bench image's line does not emit",
            authentic_data_exists="NO bench capture carries them; the W05 fixture "
                                  "shows them as a host scenario",
            computable_now="NO from authentic data",
            caveat="this is the cleanest proof that the bench image and the "
                   "delivered firmware are different producers of the same physical "
                   "quantity",
            status_label="NEED_USER_ACTION",
        ),
    ]
    return rows


# --------------------------------------------------------------------------
# A3 run index (what Member B can actually ablate)
# --------------------------------------------------------------------------

def a3_run_row(repo_root: pathlib.Path, bench_root: pathlib.Path | None,
               frames: list[envelope.Frame], source: str) -> dict[str, object]:
    """One run's ablation-readiness row, computed from its own frames."""
    driven = [f for f in frames if f.classification == envelope.DRIVEN]
    duties = sorted({f.duty_applied for f in driven if f.duty_applied is not None})
    has_req = any(f.duty_req is not None for f in frames)
    has_v = any(f.voltage_v is not None for f in frames)
    has_i = any(f.current_a is not None for f in frames)
    has_p = any(f.power_w is not None for f in frames)
    has_e = any(f.energy_wh is not None for f in frames)
    thermal_channels = sorted({c for f in frames for c, v in f.thermal.items()
                               if v is not None})
    coverage = envelope.status_coverage(frames)[source]
    qualified = coverage["electrical_status_recorded"]
    usable = bool(driven and has_i and has_v and has_p and thermal_channels)
    return {
        "session": source,
        "trust": "COMMITTED" if source in envelope.COMMITTED_SOURCES else "LOCAL_BENCH",
        "file": envelope.source_files(repo_root, bench_root).get(source, ""),
        "frames": len(frames),
        "has_command_field": "yes" if has_req else "no (single-valued stage duty)",
        "has_applied_duty": "yes" if driven else "no",
        "duty_permille_values": duties,
        "driven_frames": len(driven),
        "has_voltage": "yes" if has_v else "no",
        "has_current": "yes" if has_i else "no",
        "has_power": "yes" if has_p else "no",
        "has_energy": "yes" if has_e else "no",
        "thermal_channels": thermal_channels,
        "electrical_status_recorded": "true" if qualified else "false",
        "usable_for_electrical_ablation": "yes" if usable else "no",
        "why_not": (
            "" if usable else
            "no driven frames" if not driven else
            "no thermal channel in the capture" if not thermal_channels else
            "electrical values present but unqualified"
        ),
        "caveats": (
            "H7 ran the electrical-only image: the T2 value in the T line sits "
            "near ambient, so the run has a thermal FIELD but no thermal RESPONSE"
            if source.startswith("H7") else
            "electrical values published without any validity token in this "
            "source (CSV status cells empty / absent)"
            if not qualified and usable else ""
        ),
        "status_label": "REAL_DATA_ANALYZED",
    }


def a3_run_index(repo_root: pathlib.Path, bench_root: pathlib.Path | None,
                 audit_report: dict[str, object]) -> list[dict[str, object]]:
    """docs/05A section 24 A-W15-02: runs with command, applied, V/I/P, thermal."""
    sources = envelope.load_sources(repo_root, bench_root)
    return [a3_run_row(repo_root, bench_root, frames, source)
            for source, frames in sorted(sources.items())]


# --------------------------------------------------------------------------
# A-W15-03 reference check
# --------------------------------------------------------------------------

def reference_check(audit_report: dict[str, object]) -> dict[str, object]:
    """What can be said without a trusted independent meter: consistency only."""
    committed = [r for r in audit_report["sources"] if r["trust"] == "COMMITTED"]
    deltas = [r["power_consistency"]["max_abs_delta_w"] for r in committed
              if r["power_consistency"]["max_abs_delta_w"] is not None]
    energies = [
        {
            "source": r["source"],
            "counter_delta_wh": r["energy_consistency"].get("counter_delta_wh"),
            "integral_wh": r["energy_consistency"].get(
                "trapezoidal_integral_of_power_wh"),
            "residual_wh": r["energy_consistency"].get("counter_minus_integral_wh"),
            "verdict": r["energy_consistency"].get("verdict"),
        }
        for r in committed
        if r["energy_consistency"].get("verdict") not in (None, "INSUFFICIENT_DATA")
    ]
    return {
        "requirement": "A-W15-03 PZEM reference check",
        "trusted_independent_meter_available": False,
        "meter_evidence": (
            "no calibration record for the PZEM-017 and none for the 50 A / 75 mV "
            "shunt exists in this repository (the shunt was seen in a photo only, "
            "SOURCE VERIFIED, never calibrated)"
        ),
        "reported_instead": "plausibility and internal consistency",
        "v_times_i_agreement": {
            "tolerance_w": envelope.r(envelope.POWER_TOLERANCE_W),
            "worst_abs_delta_w": max(deltas) if deltas else None,
            "sources_compared": [r["source"] for r in committed
                                 if r["power_consistency"]["frames_compared"]],
            "mismatch_frames": sum(r["power_consistency"]["frames_beyond_tolerance_count"]
                                   for r in committed),
        },
        "energy_agreement": energies,
        "resolution_limits": {
            "voltage_lsb_v": envelope.VOLT_LSB,
            "current_lsb_a": envelope.CURRENT_LSB,
            "power_lsb_w": envelope.POWER_LSB,
            "energy_lsb_wh": envelope.ENERGY_LSB,
            "consequence": "a 1 Wh counter and a 0.1 W register cannot resolve a "
                           "short-run efficiency difference; only run-integral "
                           "comparisons are meaningful",
        },
        "certified_calibration": False,
        "status_label": "NEED_USER_ACTION",
        "what_would_close_it": "one trusted reference meter (or a calibrated shunt "
                               "channel) measured at several duty points against the "
                               "PZEM, recorded in the same session",
    }


# --------------------------------------------------------------------------
# renderers
# --------------------------------------------------------------------------

def _csv_escape(value: str) -> str:
    if any(character in value for character in (",", '"', "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "|".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _rows_to_csv(columns: list[str], rows: list[dict[str, object]]) -> str:
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(_csv_escape(_fmt(row.get(column))) for column in columns))
    return "\n".join(lines) + "\n"


PROVENANCE_COLUMNS = [
    "feature", "kind", "source_register", "producer_field", "validity_condition",
    "authentic_data_exists", "computable_now", "caveat", "status_label",
]

RUN_INDEX_COLUMNS = [
    "session", "trust", "file", "frames", "has_command_field", "has_applied_duty",
    "duty_permille_values", "driven_frames", "has_voltage", "has_current", "has_power",
    "has_energy", "thermal_channels", "electrical_status_recorded",
    "usable_for_electrical_ablation", "why_not", "caveats", "status_label",
]


def render_provenance_csv(rows: list[ProvenanceRow]) -> str:
    return _rows_to_csv(PROVENANCE_COLUMNS, [row.as_row() for row in rows])


def render_run_index_csv(rows: list[dict[str, object]]) -> str:
    return _rows_to_csv(RUN_INDEX_COLUMNS, rows)


QUALITY_COLUMNS = [
    "source", "trust", "reproducible_from_git", "frames", "frames_with_current_value",
    "frames_without_any_electrical_value", "io_error_frames", "non_ok_status_frames",
    "absence_reason", "current_status_token_counts",
    "transport_class_counts", "rx_len_counts", "gap_median_ms", "gap_max_ms",
    "late_gaps", "age_token_recorded", "current_age_median_ms", "current_age_max_ms",
    "current_age_sentinel_frames",
    "classification_counts", "latency_frames", "duty_zero_above_floor_frames",
    "power_max_abs_delta_w", "power_verdict", "energy_verdict",
    "electrical_status_recorded",
]


def render_quality_csv(audit_report: dict[str, object]) -> str:
    rows = []
    for source in audit_report["sources"]:
        cadence_row = source["cadence"]
        response = source["response_quality"]
        hold = source["holdover"]
        power = source["power_consistency"]
        energy = source["energy_consistency"]
        rows.append({
            "source": source["source"],
            "trust": source["trust"],
            "reproducible_from_git": source["reproducible_from_git"],
            "frames": response["frames"],
            "frames_with_current_value": response["frames_with_current_value"],
            "frames_without_any_electrical_value":
                response["frames_without_any_electrical_value"],
            "io_error_frames": response["current_status_token_counts"].get("IO_ERROR", 0),
            "non_ok_status_frames": response["non_ok_status_frames"],
            "absence_reason": response["absence_reason"],
            "current_status_token_counts": response["current_status_token_counts"],
            "transport_class_counts": response["transport_class_counts"],
            "rx_len_counts": response["rx_len_counts"],
            "gap_median_ms": cadence_row["gap_median_ms"],
            "gap_max_ms": cadence_row["gap_max_ms"],
            "late_gaps": cadence_row["late_gaps"],
            "age_token_recorded": cadence_row["age_token_recorded"],
            "current_age_median_ms": cadence_row["current_age_ms"].get("median"),
            "current_age_max_ms": cadence_row["current_age_ms"].get("max"),
            "current_age_sentinel_frames": cadence_row["current_age_sentinel_frames"],
            "classification_counts": hold["classification_counts"],
            "latency_frames": hold["latency_frames"],
            "duty_zero_above_floor_frames": hold["duty_zero_above_floor_frames"],
            "power_max_abs_delta_w": power["max_abs_delta_w"],
            "power_verdict": power["verdict"],
            "energy_verdict": energy.get("verdict"),
            "electrical_status_recorded":
                source["status_coverage"]["electrical_status_recorded"],
        })
    return _rows_to_csv(QUALITY_COLUMNS, rows)


def io_error_breakdown(audit_report: dict[str, object]) -> str:
    """Per-source IO_ERROR counts, computed from the audit, never typed."""
    parts = []
    for row in audit_report["sources"]:
        count = row["response_quality"]["current_status_token_counts"].get("IO_ERROR", 0)
        if count:
            parts.append(f"{row['source']} {count}")
    return "; ".join(parts) if parts else "none in any source"


def applied_off_follow_through(audit_report: dict[str, object]
                               ) -> list[dict[str, object]]:
    """The applied-OFF anomalies that carry a recorded follow-through trace."""
    consistency = audit_report["on_off_consistency"]
    return [a for a in consistency["anomalies"]
            if a["kind"] == "APPLIED_OFF_CURRENT_ABOVE_FLOOR"
            and a.get("zero_duty_current_sequence_a")]


def applied_off_follow_through_rows(audit_report: dict[str, object]) -> list[str]:
    """One markdown row per applied-OFF frame: the decay as recorded, frame by frame."""
    rows = []
    for a in applied_off_follow_through(audit_report):
        sequence = " -> ".join(str(v) for v in a["zero_duty_current_sequence_a"])
        returns = a["current_returns_to_zero_at_device_ms"]
        rows.append(f"| {a['source']} | {a['clock_ms']:.0f} | {sequence} | "
                    f"{'%.0f' % returns if returns is not None else 'not observed'} |")
    return rows


def applied_off_follow_through_sentence(audit_report: dict[str, object]) -> str:
    """The reading of that decay, and the limit of what it proves."""
    provenance = audit_report["on_off_consistency"]["zero_duty_trace_provenance"]
    return (
        "For the committed capture the sequence is **7.15 -> 0.56 -> 0.02 -> 0.0 A**, "
        "reaching zero at `device_ms=829894`. That decay supports register/transition "
        "lag and weakens sustained-energization, and it is recorded here exactly as the "
        f"operator confirmed it on 2026-11-02 - but {provenance}. A measured value and "
        "a verified physical current are different claims, so the safety "
        "qualification of the CONTROL_ELECTRICAL_ANOMALY candidate stays open, and a "
        "short unpowered inspection does not close it: that classification and Member "
        "D's unresolved thresholds gate the energized sessions as well.")


def render_pzem_quality_report(audit_report: dict[str, object],
                               provenance: list[ProvenanceRow],
                               reference: dict[str, object]) -> str:
    summary = audit_report["summary"]
    lines = [
        "# A-W15-01 / A-W15-03 - PZEM electrical-producer quality report",
        "",
        "Generated by `firmware/tools/cg_w15_pzem_quality.py` through",
        "`evidence/A/W15/build_w15_artifacts.py`. Status label: **REAL_DATA_ANALYZED**",
        "- every figure below is a statistic over frames that were recorded by",
        "supervised bench sessions. Nothing here is `PHYSICALLY_VERIFIED`, no",
        "calibration is certified, and no hardware was touched to produce it.",
        "",
        "## 1. Headline",
        "",
        f"* sources audited: **{summary['sources']}** "
        f"({sum(1 for r in audit_report['sources'] if r['trust'] == 'COMMITTED')} "
        "committed in git, the rest in Member A's local bench tree)",
        f"* frames: **{summary['frames_total']}**, of which "
        f"**{summary['frames_without_electrical_value']}** carry no electrical value "
        f"at all and **{summary['io_error_frames']}** say so explicitly with "
        f"`IO_ERROR` (+{summary['explicit_producer_failures']} non-OK status frames "
        "across all sources)",
        f"* register-latency (holdover/settling/pre-run) frames: "
        f"**{summary['latency_frames_total']}**, each listed individually",
        f"* V x I versus reported power: worst absolute delta "
        f"**{_fmt(summary['max_abs_v_times_i_delta_w'])} W** against a "
        f"register-quantisation tolerance of **{_fmt(summary['tolerance_w'])} W**; "
        f"**{summary['power_consistency_mismatch_frames']}** frames beyond tolerance",
        f"* sources that publish an electrical value with **no validity token** (so "
        f"the value is unqualified): "
        f"{', '.join(summary['sources_without_validity_token']) or 'none'}",
        f"* sources that carry **no freshness age token** at all: "
        f"{', '.join(summary['sources_without_age_token']) or 'none'} "
        "(the W03 host captures carry a poll-level token but no age; the committed "
        "CSV carries neither)",
        "",
        "## 2. What the producer actually publishes",
        "",
        "The PZEM-017 is read as six input registers "
        "(`firmware/tools/cg_modbus.py`: 0x0000 voltage, 0x0001 current, "
        "0x0002..0x0003 power, 0x0004..0x0005 energy) with the 50 A shunt profile "
        "in holding register 0x0003. The device stamps each of voltage, current and "
        "power with its own status token and an age; **energy gets a value and "
        "nothing else** - no `energy_wh_status`, no age token, in any of the 957 "
        "committed raw frames. Power factor and frequency (input 0x0006/0x0007) are "
        "not read by this firmware at all.",
        "",
        "## 3. Missing, invalid and unpowered responses",
        "",
        "| Source | Frames | With a current value | Without | Status tokens | "
        "Transport classes | rx_len |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in audit_report["sources"]:
        response = row["response_quality"]
        lines.append(
            f"| {row['source']} | {response['frames']} | "
            f"{response['frames_with_current_value']} | "
            f"{response['frames_without_any_electrical_value']} | "
            f"{_fmt(response['current_status_token_counts'])} | "
            f"{_fmt(response['transport_class_counts']) or '-'} | "
            f"{_fmt(response['rx_len_counts']) or '-'} |"
        )
    lines += [
        "",
        "Reading rules that matter for this table:",
        "",
        f"* **Producer read failures are stamped, not silent.** In the H8 raw "
        f"sessions {summary['io_error_frames']} frames carry "
        "`current_a_status=IO_ERROR` with an **empty value cell** and an age token of "
        "`-1`: the frame still exists, so the correct reading is 'no sample', never "
        "'zero current'. Per source: "
        + io_error_breakdown(audit_report) + ",",
        "* **Host-side poll failures are recorded explicitly too.** The W03 capture "
        "is the other family: 7 of 601 rows are `quality=INVALID` with "
        "`physical_fail=1` (`received=29` six times, `received=28` once) and empty "
        "value cells. Those are missing-sample evidence, and they are why "
        "`frames_without_any_electrical_value` is 7 there rather than 0.",
        "* **The production fail-closed build publishes no electrical value at all**: "
        "62/62 frames label the cells `INVALID`/`NO_DATA` with the value empty. That "
        "is a declared absence by design, not a lost sample, and it is the reason a "
        "zero from the production build must never be read as a measurement.",
        "* `rx_len=25` is a good poll in the **device-side** trace (~86-111 ms round "
        "trip, 8 echo + 17 response). The W03 host collector counts its own received "
        "length (28-29), so a byte-length threshold must never be shared between the "
        "two collectors.",
        "* `rx_len=0` with `class=NO_RESPONSE` while the 12 V supply is off is the "
        "**expected** behaviour of an unpowered meter, not a failed MAX3485; it must "
        "not be counted as a transceiver defect.",
        "* `ECHO_ONLY` (rx_len=8) is a retried poll: the H7 60 % diagnostic runs "
        "record exactly one each and the stage continued after the retry.",
        "* The committed 600 s CSV has **no failed-poll signature at all** - a failed "
        "poll simply never became a row, and the rows that exist carry empty status "
        "cells. So 'no row' and 'a row with no value' and 'a row that says IO_ERROR' "
        "are three different statements, and only the second and third are visible "
        "in this dataset.",
        "",
        "## 4. Cadence and freshness",
        "",
        "| Source | frames with clock | median gap ms | max gap ms | late | "
        "age token | current age median ms | current age max ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in audit_report["sources"]:
        cadence_row = row["cadence"]
        lines.append(
            f"| {row['source']} | {cadence_row['frames_with_clock']} | "
            f"{_fmt(cadence_row['gap_median_ms'])} | {_fmt(cadence_row['gap_max_ms'])} | "
            f"{cadence_row['late_gaps']} | "
            f"{'yes' if cadence_row['age_token_recorded'] else 'NO'} | "
            f"{_fmt(cadence_row['current_age_ms'].get('median'))} | "
            f"{_fmt(cadence_row['current_age_ms'].get('max'))} |"
        )
    lines += [
        "",
        "The committed 600 s capture runs at a 1000 ms frame period. On the wire its "
        "electrical sample is stamped **636-666 ms old** at publish time, and the "
        "BME air sample 775 ms old - so the frame that reports 'this instant' "
        "actually reports a ~0.67 s-old branch reading. In the CSV both ages and "
        "both status tokens were dropped, which is why freshness cannot be audited "
        "from the committed CSV at all and why every electrical figure taken from it "
        "must be published as `electrical_status_recorded: false`.",
        "",
        "### Clock semantics (which clock is the sample time)",
        "",
        f"* authoritative device time: "
        f"**{audit_report['clock_semantics']['authoritative_device_time']}**;",
        f"* {audit_report['clock_semantics']['clock_uncertainty_rule']};",
        f"* {audit_report['clock_semantics']['ttl_at_receipt_rule']};",
        f"* {audit_report['clock_semantics']['stale_is_not_invalid']};",
        "* no source in this dossier uses a host wall-clock stamp as the sample "
        "time, and opening the COM port starts a new `boot_id`, so a segment of one "
        "boot is never filed as an independent run.",
        "",
        "| Source | device clock | frames with clock | monotonic non-decreasing | "
        "host wall clock used |",
        "|---|---|---|---|---|",
    ]
    for source, entry in sorted(audit_report["clock_semantics"]["per_source"].items()):
        lines.append(
            f"| {source} | {entry['device_clock']} | {entry['device_ms_frames']} | "
            f"{'yes' if entry['device_ms_monotonic_non_decreasing'] else 'NO'} | "
            f"{'yes' if entry['host_wall_clock_used_as_sample_time'] else 'no'} |"
        )
    lines += [
        "",
        "## 5. ON/OFF separation and holdover patterns",
        "",
        "| Source | DRIVEN | PRE_RUN_REGISTER | OUTPUTS_OFF_REGISTER | OFF_SETTLING | "
        "OFF_RESIDUAL_ABOVE_FLOOR | IDLE_OFF | NO_ELECTRICAL_VALUE |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in audit_report["sources"]:
        counts = row["holdover"]["classification_counts"]
        lines.append(
            f"| {row['source']} | {counts.get(envelope.DRIVEN, 0)} | "
            f"{counts.get(envelope.PRE_RUN_HOLD, 0)} | "
            f"{counts.get(envelope.OFF_HOLD, 0)} | "
            f"{counts.get(envelope.OFF_SETTLING, 0)} | "
            f"{counts.get(envelope.OFF_RESIDUAL, 0)} | "
            f"{counts.get(envelope.IDLE_OFF, 0)} | "
            f"{counts.get(envelope.NO_ELECTRICAL, 0)} |"
        )
    lines += [
        "",
        "Documented latency behaviour, from these captures:",
        "",
        "* the first sample after START still holds the pre-run registers (current "
        "0.00 with duty nonzero) - one frame per driven block;",
        "* the first poll after outputs go off returns the **last loaded current** "
        "(7.11-7.15 A in the H8 sessions, one frame period after the last driven "
        "frame), and the poll ~1 s later reads the unwinding value (0.41-3.57 A) or "
        "0;",
        "* steady OFF current never exceeded **0.02 A** - one current LSB - which is "
        "the meter's own noise floor, well under the bench image's simulated "
        "`off_current_limit_a=0.200` gate;",
        "* so the ON/OFF separation rule for any downstream feature is: drop the "
        "first frame of a driven block and the first two frames after the applied "
        "duty reaches 0, and say which frames were dropped.",
        "",
        "### Applied duty versus measured current, frame by frame",
        "",
    ] + [f"* `{key}`: {value}"
         for key, value in sorted(audit_report["on_off_consistency"]["buckets"].items())
         ] + [
        "",
        "| Kind | source | device_ms | applied duty | current A | frame class | "
        "electrical status recorded |",
        "|---|---|---|---|---|---|---|",
    ] + [
        f"| {a['kind']} | {a['source']} | {a['clock_ms']:.0f} | "
        f"{a['duty_applied_permille']} | {a['current_a']} | {a['classification']} | "
        f"{str(a['electrical_status_recorded']).lower()} |"
        for a in audit_report["on_off_consistency"]["anomalies"][:12]
    ] + [
        "",
        f"{audit_report['on_off_consistency']['note']}. The 600 s capture's "
        "`device_ms=826894` frame is quoted here exactly as recorded - commanded "
        "OFF, applied duty 0, 7.15 A, an empty status cell, and every measured "
        "field identical to the two preceding driven frames - and it is "
        "**not** averaged into any peak.",
        "",
        "### What the meter reported after each applied-OFF frame above the floor",
        "",
        "The whole recorded decay, not only the first held frame. The applied duty "
        "stayed 0 across each row below; the walk stops at the first frame whose "
        "applied duty is not 0, and once the reported current reaches 0.0 A.",
        "",
        "| source | device_ms | PZEM-reported current A while applied duty stayed 0 | "
        "returns to 0.0 A at device_ms |",
        "|---|---|---|---|",
    ] + applied_off_follow_through_rows(audit_report) + [
        "",
        applied_off_follow_through_sentence(audit_report),
        "",
        "## 6. Power consistency (A-W15-01's fourth bullet)",
        "",
        "| Source | frames compared | mean abs delta W | max abs delta W | verdict |",
        "|---|---|---|---|---|",
    ]
    for row in audit_report["sources"]:
        power = row["power_consistency"]
        if not power["frames_compared"]:
            continue
        lines.append(
            f"| {row['source']} | {power['frames_compared']} | "
            f"{_fmt(power['mean_abs_delta_w'])} | {_fmt(power['max_abs_delta_w'])} | "
            f"{power['verdict']} |"
        )
    lines += [
        "",
        "Energy counters versus the integral of reported power, per source that has a "
        "counter:",
        "",
        "| Source | counter delta Wh | integral Wh | residual Wh | counter verdict |",
        "|---|---|---|---|---|",
    ]
    for row in audit_report["sources"]:
        energy = row["energy_consistency"]
        if energy.get("verdict") in (None, "INSUFFICIENT_DATA"):
            continue
        lines.append(f"| {row['source']} | {_fmt(energy.get('counter_delta_wh'))} | "
                     f"{_fmt(energy.get('trapezoidal_integral_of_power_wh'))} | "
                     f"{_fmt(energy.get('counter_minus_integral_wh'))} | "
                     f"{energy.get('verdict')} |")
    lines += [
        "",
        "Every counter in this dataset is monotonic non-decreasing inside a boot and "
        "quantised to 1 Wh, so `COUNTER_WITHIN_QUANTISATION` is the strongest "
        "statement the data supports - and none of these counters carries a validity "
        "token.",
        "",
        "## 7. A3 feature provenance (A-W15-02)",
        "",
        "| Feature | Kind | Register | Validity condition | Authentic data | "
        "Computable now |",
        "|---|---|---|---|---|---|",
    ]
    for row in provenance:
        lines.append(f"| {row.feature} | {row.kind} | {row.source_register} | "
                     f"{row.validity_condition} | {row.authentic_data_exists} | "
                     f"{row.computable_now} |")
    lines += [
        "",
        "Machine-readable version, including the caveats: `a3-feature-provenance.csv`.",
        "",
        "## 8. A-W15-03 - reference check against an independent meter",
        "",
        f"Trusted independent meter available: "
        f"**{'yes' if reference['trusted_independent_meter_available'] else 'NO'}**.",
        f"Reported instead: *{reference['reported_instead']}*.",
        "",
        f"* {reference['meter_evidence']}",
        f"* V x I agreement: worst {_fmt(reference['v_times_i_agreement']['worst_abs_delta_w'])}"
        f" W against a {_fmt(reference['v_times_i_agreement']['tolerance_w'])} W "
        f"quantisation tolerance, "
        f"{reference['v_times_i_agreement']['mismatch_frames']} frames beyond tolerance "
        f"in {len(reference['v_times_i_agreement']['sources_compared'])} committed sources",
        "* energy agreement per source: "
        + "; ".join(f"{e['source']} counter {_fmt(e['counter_delta_wh'])} Wh vs "
                    f"integral {_fmt(e['integral_wh'])} Wh ({e['verdict']})"
                    for e in reference["energy_agreement"]),
        f"* resolution limits: V {_fmt(reference['resolution_limits']['voltage_lsb_v'])} V, "
        f"I {_fmt(reference['resolution_limits']['current_lsb_a'])} A, "
        f"P {_fmt(reference['resolution_limits']['power_lsb_w'])} W, "
        f"E {reference['resolution_limits']['energy_lsb_wh']} Wh - "
        f"{reference['resolution_limits']['consequence']}",
        "",
        "Certified calibration: **no**. Status label: "
        f"**{reference['status_label']}** - {reference['what_would_close_it']}.",
        "",
        "## 9. What could not be computed, and why",
        "",
        "* power factor / frequency features: the firmware never reads those "
        "registers, so no capture contains them;",
        "* producer liveness counters (`power_beats`, `power_max_gap_ms`, "
        "`electrical_quality`): a delivered-schema concept that the bench image's "
        "line does not emit, so it exists only in the W05 host fixture;",
        "* a duty-resolved electrical model from committed data alone: the ladder is "
        "local-bench only;",
        "* stale-versus-fresh separation inside the committed CSV: its status and "
        "age columns are empty/absent;",
        "* any calibration statement: no reference instrument, no shunt calibration.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=pathlib.Path, default=REPO_ROOT)
    parser.add_argument("--bench-root", type=pathlib.Path, default=envelope.DEFAULT_BENCH_ROOT)
    parser.add_argument("--no-local", action="store_true")
    parser.add_argument("--json", type=pathlib.Path)
    args = parser.parse_args(argv)

    bench = None if args.no_local else args.bench_root
    report = audit(args.repo_root, bench)
    provenance = a3_provenance(report)
    runs = a3_run_index(args.repo_root, bench, report)
    reference = reference_check(report)
    payload = {
        "audit": report,
        "a3_provenance": [row.as_row() for row in provenance],
        "a3_run_index": runs,
        "reference_check": reference,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8", newline="\n")
        print(f"wrote {args.json}")
    print(f"sources: {report['summary']['sources']} frames: "
          f"{report['summary']['frames_total']}")
    print(f"latency frames: {report['summary']['latency_frames_total']} "
          f"mismatch frames: {report['summary']['power_consistency_mismatch_frames']}")
    usable = [r for r in runs if r["usable_for_electrical_ablation"] == "yes"]
    print(f"A3 usable runs: {len(usable)}/{len(runs)}: "
          f"{', '.join(str(r['session']) for r in usable)}")
    print(f"reference check: certified_calibration="
          f"{reference['certified_calibration']} status={reference['status_label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
