"""W17 offline/online shadow parity, freshness and hypothetical trace (B-W17-01...04).

The only evidence produced here is an isolated *offline software replay* over
the deterministic synthetic development fixture.  It never proves live shadow
acceptance, physical readiness or a deployable model.  The W15 artifact stays
``SYNTHETIC_SOFTWARE_CONTROL_ONLY`` / ``NON_DEPLOYABLE_CANDIDATE`` / risk-score
only, and no command, broker, actuator or network capability exists in this
module.

Two assembly paths are exercised:

* offline reference: the canonical W10 causal batch pipeline over the run;
* online replay: a stateful, arrival-aware streaming adapter that deduplicates,
  rejects identity/temporal contradictions, applies the event-time and
  availability cuts, sanitizes stale channels to *missing* values and only then
  calls the same canonical W10 formulas.

The comparison checks every ordered model feature and its missing-reason code
before any risk score is compared, because the synthetic model's score depends
on a single feature and score equality alone cannot prove feature equality.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from .feature_pipeline import (
    DOOR_CLOSED,
    DOOR_OPEN,
    MISSING_ELECTRICAL_UNQUALIFIED,
    FeatureRow,
    PipelineSample,
    Trajectory,
    _dedupe_samples,
    feature_rows,
)
from .feature_registry import FeatureRegistry
from .w15_artifact import GuardedModel

W17_LAYER_VERSION = "coldguard-w17-shadow-parity-v1"
W17_BASE_REVISION = "c2b62234466b09585cf4e868c67a4d49ae06597f"
W17_BASE_REVISION_SEMANTICS = "W16_STACK_HEAD_BASE_NOT_W17_DELIVERY_COMMIT"

EVIDENCE_SYNTHETIC = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
EVIDENCE_OFFLINE_REPLAY = "OFFLINE_REPLAY_VERIFIED"
EVIDENCE_REAL_ONLINE = "REAL_ONLINE_SHADOW_VERIFIED"
EVIDENCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
EVIDENCE_BLOCKED = "BLOCKED_BY_MISSING_EVIDENCE"

READY_FOR_SOFTWARE_REPLAY = "READY_FOR_SOFTWARE_REPLAY"
REFUSED_STALE_INPUT = "REFUSED_STALE_INPUT"
REFUSED_UNTRUSTED_INPUT = "REFUSED_UNTRUSTED_INPUT"
REFUSED_TEMPORAL_ORDER = "REFUSED_TEMPORAL_ORDER"
REFUSED_IDENTITY_MISMATCH = "REFUSED_IDENTITY_MISMATCH"
REFUSED_FEATURE_SCHEMA_MISMATCH = "REFUSED_FEATURE_SCHEMA_MISMATCH"
DISPOSITIONS = (
    READY_FOR_SOFTWARE_REPLAY,
    REFUSED_STALE_INPUT,
    REFUSED_UNTRUSTED_INPUT,
    REFUSED_TEMPORAL_ORDER,
    REFUSED_IDENTITY_MISMATCH,
    REFUSED_FEATURE_SCHEMA_MISMATCH,
)

FEATURE_TOLERANCE = 1e-9
SCORE_TOLERANCE = 1e-12
MAX_FEATURE_TOLERANCE = 1e-9
MAX_SCORE_TOLERANCE = 1e-12

RUNTIME_FRESHNESS_POLICY_PENDING = "RUNTIME_FRESHNESS_POLICY_PENDING_C_D"
SYNTHETIC_TEST_PARAMETER = "SYNTHETIC_ILLUSTRATIVE_TEST_PARAMETER"

WARNING_RULE_STATUS = "SYNTHETIC_ILLUSTRATIVE"
WARNING_RULE_SOURCE = "W15_MANIFEST_OPERATING_THRESHOLD"
WARNING_PERSISTENCE = "NOT_FROZEN"
WARNING_RULE_REFUSED = "REFUSED_RULE_UNAUTHORIZED"
WARNING_WITHHELD_REFUSED = "WITHHELD_ANCHOR_REFUSED"

TRACE_SCHEMA = "coldguard-w17-shadow-trace-v1"
RECORD_SCHEMA = "coldguard-w17-shadow-trace-record-v1"

VERDICT_FEATURE_PARITY = "OFFLINE_FEATURE_PARITY_VERIFIED"
VERDICT_PREDICTION_PARITY = "OFFLINE_PREDICTION_PARITY_VERIFIED"
VERDICT_TRACE = "SHADOW_TRACE_SOFTWARE_VERIFIED"
VERDICT_LIVE_NOT_ESTABLISHED = "LIVE_SHADOW_NOT_ESTABLISHED"
VERDICT_PHYSICAL_BLOCKED = "PHYSICAL_SHADOW_BLOCKED"
VERDICT_NOT_VERIFIED = "NOT_VERIFIED"


class W17Error(ValueError):
    """The W17 replay would fabricate identity, time or evidence."""


class W17IdentityError(W17Error):
    """An input identity is duplicated with contradictory content or foreign."""


class W17TemporalError(W17Error):
    """Sequence or event-time ordering contradicts the replay contract."""


class W17SchemaError(W17Error):
    """Feature schema/order/hash does not match the frozen contract."""


class W17ToleranceError(W17Error):
    """A tolerance wider than the declared maximum was requested."""


class W17TraceError(W17Error):
    """A shadow trace record is incomplete or internally inconsistent."""


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )


def _sha256(payload: str | bytes) -> str:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(raw).hexdigest()


def _finite(value: Any, where: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise W17Error(f"{where} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise W17Error(f"{where} must be finite")
    return numeric


@dataclass(frozen=True)
class FreshnessPolicy:
    """Explicit *test* parameters; the runtime policy is not frozen in W17.

    ``RUNTIME_FRESHNESS_POLICY_PENDING_C_D`` remains the authoritative state.
    """

    max_anchor_input_age_s: float = 2.0
    max_electrical_age_s: float = 5.0
    max_door_age_s: float = 5.0
    policy_status: str = RUNTIME_FRESHNESS_POLICY_PENDING
    parameter_class: str = SYNTHETIC_TEST_PARAMETER

    def __post_init__(self) -> None:
        for name in (
            "max_anchor_input_age_s",
            "max_electrical_age_s",
            "max_door_age_s",
        ):
            value = getattr(self, name)
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise W17Error(f"{name} must be positive and finite")
        if self.policy_status != RUNTIME_FRESHNESS_POLICY_PENDING:
            raise W17Error(
                "the runtime freshness policy is not frozen in W17; refusing to "
                "declare it"
            )
        if self.parameter_class != SYNTHETIC_TEST_PARAMETER:
            raise W17Error("freshness test parameters must be labelled synthetic")


@dataclass(frozen=True)
class ReplayConfig:
    transport_delay_s: float = 0.25
    processing_delay_s: float = 1.0

    def __post_init__(self) -> None:
        for name in ("transport_delay_s", "processing_delay_s"):
            value = getattr(self, name)
            if not math.isfinite(float(value)) or float(value) < 0:
                raise W17Error(f"{name} must be finite and non-negative")


@dataclass(frozen=True)
class TelemetryRecord:
    """One delivered telemetry frame plus its simulated availability metadata."""

    sample: PipelineSample
    arrival_time_s: float
    electrical_observed_at_s: float | None = None
    door_observed_at_s: float | None = None

    def __post_init__(self) -> None:
        arrival = _finite(self.arrival_time_s, "arrival_time_s")
        if arrival < self.sample.time_s:
            raise W17Error("a frame cannot be received before its event time")
        for name in ("electrical_observed_at_s", "door_observed_at_s"):
            value = getattr(self, name)
            if value is None:
                continue
            observed = _finite(value, name)
            if observed > self.sample.time_s:
                raise W17Error(f"{name} cannot be later than the frame event time")

    @property
    def telemetry_id(self) -> str:
        return self.sample.identity

    @property
    def event_time_s(self) -> float:
        return self.sample.time_s

    def channel_identity(self) -> tuple[Any, ...]:
        return (
            self.sample.payload(),
            self.electrical_observed_at_s,
            self.door_observed_at_s,
        )


@dataclass(frozen=True)
class FeatureVector:
    feature_ids: tuple[str, ...]
    values: tuple[float | int | None, ...]
    missing_reasons: tuple[str, ...]
    feature_schema_version: str
    registry_sha256: str

    def __post_init__(self) -> None:
        if len(self.feature_ids) != len(self.values) or len(
            self.feature_ids
        ) != len(self.missing_reasons):
            raise W17SchemaError("feature vector lengths differ")
        if len(set(self.feature_ids)) != len(self.feature_ids):
            raise W17SchemaError("feature vector contains duplicate identities")
        for reason in self.missing_reasons:
            if not isinstance(reason, str) or not reason:
                raise W17SchemaError("missing-reason codes must be non-empty text")

    def as_columns(self) -> dict[str, list[float]]:
        columns: dict[str, list[float]] = {}
        for feature_id, value in zip(self.feature_ids, self.values):
            if value is None:
                columns[feature_id] = [math.nan]
                continue
            numeric = float(value)
            if not math.isfinite(numeric):
                raise W17SchemaError(
                    f"feature {feature_id!r} carries a non-finite value"
                )
            columns[feature_id] = [numeric]
        return columns

    def sha256(self) -> str:
        payload = {
            "feature_ids": list(self.feature_ids),
            "values": list(self.values),
            "missing_reasons": list(self.missing_reasons),
            "feature_schema_version": self.feature_schema_version,
            "registry_sha256": self.registry_sha256,
        }
        return _sha256(_canonical_json(payload))

    def defined_count(self) -> int:
        return sum(1 for value in self.values if value is not None)

    def missing_count(self) -> int:
        return len(self.values) - self.defined_count()


@dataclass(frozen=True)
class FeatureComparison:
    anchor_t_s: float
    run_id: str
    sample_identity: str
    passed: bool
    mismatches: tuple[str, ...]
    max_abs_deviation: float | None
    defined_values: int
    missing_values: int


@dataclass(frozen=True)
class PredictionComparison:
    anchor_t_s: float
    run_id: str
    sample_identity: str
    passed: bool
    offline_score: float
    online_score: float
    abs_deviation: float


@dataclass(frozen=True)
class AnchorDecision:
    disposition: str
    reasons: tuple[str, ...]
    run_id: str
    boot_id: str
    anchor_t_s: float
    processing_time_s: float
    anchor_arrival_s: float | None
    anchor_age_s: float | None
    electrical_age_s: float | None
    door_age_s: float | None
    input_window_start_s: float | None
    input_window_end_s: float | None
    vector: FeatureVector | None
    input_telemetry_ids: tuple[str, ...]
    sanitized_telemetry_ids: tuple[str, ...]
    late_observation_ids: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.disposition == READY_FOR_SOFTWARE_REPLAY


def _feature_vector_from_row(
    row: FeatureRow,
    registry: FeatureRegistry,
    feature_ids: Sequence[str],
) -> FeatureVector:
    if row.feature_schema_version != registry.feature_version:
        raise W17SchemaError("feature schema version mismatch")
    if row.registry_sha256 != registry.schema_sha256:
        raise W17SchemaError("feature registry hash mismatch")
    positions = []
    for feature_id in feature_ids:
        try:
            positions.append(registry.feature_ids.index(feature_id))
        except ValueError as exc:
            raise W17SchemaError(
                f"feature {feature_id!r} is not registered"
            ) from exc
    return FeatureVector(
        feature_ids=tuple(feature_ids),
        values=tuple(row.values[position] for position in positions),
        missing_reasons=tuple(row.missing_reasons[position] for position in positions),
        feature_schema_version=row.feature_schema_version,
        registry_sha256=row.registry_sha256,
    )


class _AnchorBuilder:
    """Assemble the authorized history at one anchor and run the W10 formulas."""

    def __init__(
        self,
        template: Trajectory,
        registry: FeatureRegistry,
        feature_ids: Sequence[str],
        policy: FreshnessPolicy,
    ) -> None:
        self._template = template
        self._registry = registry
        self._feature_ids = tuple(feature_ids)
        self._policy = policy

    def _sanitize(
        self, record: TelemetryRecord
    ) -> tuple[PipelineSample, dict[str, float | str | None]]:
        sample = record.sample
        updates: dict[str, Any] = {}
        electrical_age = None
        door_age = None
        if record.electrical_observed_at_s is not None:
            electrical_age = sample.time_s - record.electrical_observed_at_s
            if electrical_age > self._policy.max_electrical_age_s:
                updates.update(
                    cooling_voltage_v=None,
                    cooling_current_a=None,
                    cooling_power_w=None,
                    cooling_energy_counter_wh=None,
                    electrical_quality="STALE",
                )
        if record.door_observed_at_s is not None:
            door_age = sample.time_s - record.door_observed_at_s
            if door_age > self._policy.max_door_age_s:
                updates.update(door_state="UNKNOWN", door_quality="STALE")
        sanitized = replace(sample, **updates) if updates else sample
        return sanitized, {"electrical_age_s": electrical_age, "door_age_s": door_age}

    def build(
        self, records: Sequence[TelemetryRecord], anchor: float
    ) -> tuple[FeatureRow | None, tuple[str, ...]]:
        samples = []
        sanitized_ids = []
        for record in sorted(
            records, key=lambda item: (item.event_time_s, item.telemetry_id)
        ):
            sample, _ = self._sanitize(record)
            if sample is not record.sample:
                sanitized_ids.append(record.telemetry_id)
            samples.append(sample)
        if not samples:
            return None, tuple(sanitized_ids)
        prefix = Trajectory(
            run_id=self._template.run_id,
            boot_id=self._template.boot_id,
            device_id=self._template.device_id,
            scenario_id=self._template.scenario_id,
            controller_id=self._template.controller_id,
            source_sha256=self._template.source_sha256,
            source_type=self._template.source_type,
            clock_domain=self._template.clock_domain,
            origin_utc=self._template.origin_utc,
            physical_source_key=self._template.physical_source_key,
            samples=_dedupe_samples(samples),
            physical_eligibility=self._template.physical_eligibility,
            exclusion_reasons=self._template.exclusion_reasons,
            source_run_ids=self._template.source_run_ids,
        )
        rows = feature_rows(prefix, self._registry, anchors=[float(anchor)])
        if len(rows) != 1:
            raise W17Error("the anchor did not produce exactly one feature row")
        return rows[0], tuple(sanitized_ids)


class ReplaySession:
    """Streaming ingestion state for one run and one boot.

    The session never mutates an emitted decision.  A late frame is recorded as
    a late observation for audit; it cannot change an earlier anchor because
    anchor decisions are frozen values and availability is filtered per
    prediction time.
    """

    def __init__(
        self,
        *,
        template: Trajectory,
        registry: FeatureRegistry,
        feature_ids: Sequence[str],
        policy: FreshnessPolicy | None = None,
        expected_schema_version: str | None = None,
        expected_schema_sha256: str | None = None,
    ) -> None:
        if template.run_id is None:
            raise W17Error("a replay session requires a resolved run identity")
        self._template = template
        self._registry = registry
        self._feature_ids = tuple(feature_ids)
        for feature_id in self._feature_ids:
            registry.feature(feature_id)
        self._policy = policy or FreshnessPolicy()
        self._expected_schema_version = (
            expected_schema_version or registry.feature_version
        )
        self._expected_schema_sha256 = (
            expected_schema_sha256 or registry.schema_sha256
        )
        self._builder = _AnchorBuilder(
            template, registry, self._feature_ids, self._policy
        )
        self._by_identity: dict[str, TelemetryRecord] = {}
        self._accepted: list[TelemetryRecord] = []
        self._last_seq: int | None = None
        self._last_event_time: float | None = None
        self._identity_failed = False
        self._temporal_failed = False
        self._duplicates = 0
        self._out_of_order_arrivals = 0
        self._late_ids: list[str] = []
        self._last_processed_anchor: float | None = None
        self._last_processed_time: float | None = None

    @property
    def boot_id(self) -> str:
        return self._template.boot_id

    @property
    def accepted_count(self) -> int:
        return len(self._accepted)

    @property
    def duplicate_count(self) -> int:
        return self._duplicates

    @property
    def out_of_order_arrival_count(self) -> int:
        return self._out_of_order_arrivals

    @property
    def late_observation_ids(self) -> tuple[str, ...]:
        return tuple(self._late_ids)

    def ingest(self, record: TelemetryRecord) -> str:
        if self._identity_failed:
            raise W17IdentityError("replay identity state is already contradictory")
        if self._temporal_failed:
            raise W17TemporalError("replay temporal state is already contradictory")
        sample = record.sample
        if sample.boot_id != self._template.boot_id:
            self._identity_failed = True
            raise W17IdentityError(
                f"frame {sample.identity!r} belongs to boot {sample.boot_id!r}, "
                f"not the session boot {self._template.boot_id!r}; partition "
                "boot boundaries instead of carrying state"
            )
        if sample.device_id != self._template.device_id:
            self._identity_failed = True
            raise W17IdentityError(
                f"frame {sample.identity!r} carries a foreign device identity"
            )
        existing = self._by_identity.get(record.telemetry_id)
        if existing is not None:
            if existing.channel_identity() != record.channel_identity():
                self._identity_failed = True
                raise W17IdentityError(
                    f"contradictory duplicate identity {record.telemetry_id!r}; "
                    "input order cannot resolve the payload conflict"
                )
            self._duplicates += 1
            return "DUPLICATE_COLLAPSED"
        if self._last_seq is not None and sample.seq <= self._last_seq:
            if sample.time_s > (self._last_event_time or sample.time_s):
                self._temporal_failed = True
                raise W17TemporalError(
                    f"sequence regression with a newer event time: {sample.seq} "
                    f"after {self._last_seq} in boot {sample.boot_id!r}"
                )
            # An older frame delivered late is classified, never allowed to
            # rewrite an emitted prediction.
            self._out_of_order_arrivals += 1
        elif (
            self._last_event_time is not None
            and sample.time_s < self._last_event_time
        ):
            self._out_of_order_arrivals += 1
        self._last_seq = (
            sample.seq
            if self._last_seq is None
            else max(self._last_seq, sample.seq)
        )
        self._last_event_time = (
            sample.time_s
            if self._last_event_time is None
            else max(self._last_event_time, sample.time_s)
        )
        self._by_identity[record.telemetry_id] = record
        self._accepted.append(record)
        if (
            self._last_processed_anchor is not None
            and self._last_processed_time is not None
            and record.event_time_s <= self._last_processed_anchor
            and record.arrival_time_s > self._last_processed_time
        ):
            self._late_ids.append(record.telemetry_id)
        return "ACCEPTED"

    def _available(
        self, anchor: float, processing_time: float
    ) -> tuple[TelemetryRecord, ...]:
        selected = [
            record
            for record in self._accepted
            if record.event_time_s <= anchor
            and record.arrival_time_s <= processing_time
        ]
        return tuple(
            sorted(selected, key=lambda item: (item.event_time_s, item.telemetry_id))
        )

    def _refusal(
        self,
        disposition: str,
        reasons: Sequence[str],
        *,
        template: Trajectory,
        anchor: float,
        processing_time: float,
        anchor_arrival: float | None,
        late_ids: Sequence[str],
        available: Sequence[TelemetryRecord] = (),
        anchor_age: float | None = None,
        electrical_age: float | None = None,
        door_age: float | None = None,
        compute_vector: bool = True,
    ) -> AnchorDecision:
        vector = None
        sanitized_ids: tuple[str, ...] = ()
        input_ids = tuple(record.telemetry_id for record in available)
        window_start = None
        window_end = None
        if compute_vector and available:
            try:
                row, sanitized_ids = self._builder.build(available, anchor)
                if row is not None:
                    if (
                        row.feature_schema_version != self._expected_schema_version
                        or row.registry_sha256 != self._expected_schema_sha256
                    ):
                        return AnchorDecision(
                            disposition=REFUSED_FEATURE_SCHEMA_MISMATCH,
                            reasons=tuple(reasons)
                            + ("EXPECTED_FEATURE_SCHEMA_MISMATCH",),
                            run_id=template.run_id or "",
                            boot_id=template.boot_id,
                            anchor_t_s=anchor,
                            processing_time_s=processing_time,
                            anchor_arrival_s=anchor_arrival,
                            anchor_age_s=anchor_age,
                            electrical_age_s=electrical_age,
                            door_age_s=door_age,
                            input_window_start_s=None,
                            input_window_end_s=None,
                            vector=None,
                            input_telemetry_ids=input_ids,
                            sanitized_telemetry_ids=(),
                            late_observation_ids=tuple(late_ids),
                        )
                    vector = _feature_vector_from_row(
                        row, self._registry, self._feature_ids
                    )
                    window_start = row.input_interval_start_s
                    window_end = row.input_interval_end_s
            except W17SchemaError as exc:
                return AnchorDecision(
                    disposition=REFUSED_FEATURE_SCHEMA_MISMATCH,
                    reasons=tuple(reasons) + (str(exc),),
                    run_id=template.run_id or "",
                    boot_id=template.boot_id,
                    anchor_t_s=anchor,
                    processing_time_s=processing_time,
                    anchor_arrival_s=anchor_arrival,
                    anchor_age_s=anchor_age,
                    electrical_age_s=electrical_age,
                    door_age_s=door_age,
                    input_window_start_s=None,
                    input_window_end_s=None,
                    vector=None,
                    input_telemetry_ids=input_ids,
                    sanitized_telemetry_ids=(),
                    late_observation_ids=tuple(late_ids),
                )
        return AnchorDecision(
            disposition=disposition,
            reasons=tuple(reasons),
            run_id=template.run_id or "",
            boot_id=template.boot_id,
            anchor_t_s=anchor,
            processing_time_s=processing_time,
            anchor_arrival_s=anchor_arrival,
            anchor_age_s=anchor_age,
            electrical_age_s=electrical_age,
            door_age_s=door_age,
            input_window_start_s=window_start,
            input_window_end_s=window_end,
            vector=vector,
            input_telemetry_ids=input_ids,
            sanitized_telemetry_ids=sanitized_ids,
            late_observation_ids=tuple(late_ids),
        )

    def feature_row_at(
        self, anchor: float, processing_time: float
    ) -> AnchorDecision:
        anchor = _finite(anchor, "anchor")
        processing_time = _finite(processing_time, "processing_time")
        late_ids = tuple(self._late_ids)
        available = self._available(anchor, processing_time)
        anchor_records = [
            record for record in available if record.event_time_s == anchor
        ]
        anchor_arrival = (
            min(record.arrival_time_s for record in anchor_records)
            if anchor_records
            else None
        )
        self._last_processed_anchor = max(
            anchor, self._last_processed_anchor
            if self._last_processed_anchor is not None
            else anchor
        )
        self._last_processed_time = max(
            processing_time,
            self._last_processed_time
            if self._last_processed_time is not None
            else processing_time,
        )
        if self._identity_failed:
            return self._refusal(
                REFUSED_IDENTITY_MISMATCH,
                ("REPLAY_IDENTITY_STATE_CONTRADICTORY",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
                compute_vector=False,
            )
        if self._temporal_failed:
            return self._refusal(
                REFUSED_TEMPORAL_ORDER,
                ("REPLAY_TEMPORAL_STATE_CONTRADICTORY",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
                compute_vector=False,
            )
        if not available:
            return self._refusal(
                REFUSED_STALE_INPUT,
                ("NO_INPUT_AVAILABLE_AT_PREDICTION",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
            )
        if not anchor_records:
            pending = [
                record
                for record in self._accepted
                if record.event_time_s == anchor
            ]
            if pending:
                return self._refusal(
                    REFUSED_TEMPORAL_ORDER,
                    ("ANCHOR_INPUT_NOT_AVAILABLE_AT_PREDICTION",),
                    template=self._template,
                    anchor=anchor,
                    processing_time=processing_time,
                    anchor_arrival=anchor_arrival,
                    late_ids=late_ids,
                    available=available,
                    compute_vector=False,
                )
            return self._refusal(
                REFUSED_STALE_INPUT,
                ("ANCHOR_OBSERVATION_MISSING",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
                compute_vector=False,
            )
        if len(anchor_records) != 1:
            return self._refusal(
                REFUSED_IDENTITY_MISMATCH,
                ("ANCHOR_TIME_AMBIGUOUS",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
                compute_vector=False,
            )
        anchor_record = anchor_records[0]
        latest_event = max(record.event_time_s for record in available)
        anchor_age = processing_time - latest_event
        if anchor_age > self._policy.max_anchor_input_age_s:
            return self._refusal(
                REFUSED_STALE_INPUT,
                (f"ANCHOR_INPUT_AGE_EXCEEDS_TEST_PARAMETER:{anchor_age:g}",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
                anchor_age=anchor_age,
            )
        electrical_observed = (
            anchor_record.electrical_observed_at_s
            if anchor_record.electrical_observed_at_s is not None
            else anchor_record.event_time_s
        )
        electrical_age = processing_time - electrical_observed
        if electrical_age > self._policy.max_electrical_age_s:
            return self._refusal(
                REFUSED_STALE_INPUT,
                (f"STALE_ELECTRICAL_AGE_EXCEEDS_TEST_PARAMETER:{electrical_age:g}",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
                anchor_age=anchor_age,
                electrical_age=electrical_age,
            )
        door_observed = (
            anchor_record.door_observed_at_s
            if anchor_record.door_observed_at_s is not None
            else anchor_record.event_time_s
        )
        door_age = processing_time - door_observed
        if door_age > self._policy.max_door_age_s:
            return self._refusal(
                REFUSED_STALE_INPUT,
                (f"STALE_DOOR_AGE_EXCEEDS_TEST_PARAMETER:{door_age:g}",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
                anchor_age=anchor_age,
                electrical_age=electrical_age,
                door_age=door_age,
            )
        sample = anchor_record.sample
        untrusted = []
        if sample.thermal_quality != "VALID":
            untrusted.append(f"THERMAL_QUALITY_{sample.thermal_quality}")
        if sample.electrical_quality != "VALID":
            untrusted.append(f"ELECTRICAL_QUALITY_{sample.electrical_quality}")
        if sample.overall_quality == "INVALID":
            untrusted.append("OVERALL_QUALITY_INVALID")
        if sample.door_state not in (DOOR_OPEN, DOOR_CLOSED):
            untrusted.append("DOOR_CONTEXT_UNKNOWN")
        elif sample.door_quality != "VALID":
            untrusted.append(f"DOOR_QUALITY_{sample.door_quality}")
        elif not sample.door_polarity_attested:
            untrusted.append("DOOR_POLARITY_UNATTESTED")
        if untrusted:
            return self._refusal(
                REFUSED_UNTRUSTED_INPUT,
                tuple(untrusted),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
                anchor_age=anchor_age,
                electrical_age=electrical_age,
                door_age=door_age,
            )
        row, sanitized_ids = self._builder.build(available, anchor)
        if row is None:
            return self._refusal(
                REFUSED_STALE_INPUT,
                ("EMPTY_AVAILABLE_HISTORY",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
            )
        if (
            row.feature_schema_version != self._expected_schema_version
            or row.registry_sha256 != self._expected_schema_sha256
        ):
            return self._refusal(
                REFUSED_FEATURE_SCHEMA_MISMATCH,
                ("EXPECTED_FEATURE_SCHEMA_MISMATCH",),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
                compute_vector=False,
            )
        try:
            vector = _feature_vector_from_row(row, self._registry, self._feature_ids)
        except W17SchemaError as exc:
            return self._refusal(
                REFUSED_FEATURE_SCHEMA_MISMATCH,
                (str(exc),),
                template=self._template,
                anchor=anchor,
                processing_time=processing_time,
                anchor_arrival=anchor_arrival,
                late_ids=late_ids,
                available=available,
            )
        return AnchorDecision(
            disposition=READY_FOR_SOFTWARE_REPLAY,
            reasons=(),
            run_id=self._template.run_id or "",
            boot_id=self._template.boot_id,
            anchor_t_s=anchor,
            processing_time_s=processing_time,
            anchor_arrival_s=anchor_arrival,
            anchor_age_s=anchor_age,
            electrical_age_s=electrical_age,
            door_age_s=door_age,
            input_window_start_s=row.input_interval_start_s,
            input_window_end_s=row.input_interval_end_s,
            vector=vector,
            input_telemetry_ids=tuple(
                record.telemetry_id for record in available
            ),
            sanitized_telemetry_ids=sanitized_ids,
            late_observation_ids=late_ids,
        )


def compare_feature_vectors(
    offline: FeatureVector,
    online: FeatureVector,
    *,
    tolerance: float = FEATURE_TOLERANCE,
    anchor_t_s: float = 0.0,
    run_id: str = "",
    sample_identity: str = "",
) -> FeatureComparison:
    if tolerance > MAX_FEATURE_TOLERANCE:
        raise W17ToleranceError(
            f"feature tolerance {tolerance} exceeds the declared maximum "
            f"{MAX_FEATURE_TOLERANCE}; a changed formula cannot be hidden by a "
            "wider tolerance"
        )
    if offline.feature_ids != online.feature_ids:
        raise W17SchemaError(
            "offline/online ordered feature identities differ: "
            f"{list(offline.feature_ids)} vs {list(online.feature_ids)}"
        )
    if (
        offline.feature_schema_version != online.feature_schema_version
        or offline.registry_sha256 != online.registry_sha256
    ):
        raise W17SchemaError(
            "offline/online feature schema version or registry hash differs"
        )
    mismatches: list[str] = []
    max_deviation: float | None = None
    defined = 0
    missing = 0
    for feature_id, left, right, left_reason, right_reason in zip(
        offline.feature_ids,
        offline.values,
        online.values,
        offline.missing_reasons,
        online.missing_reasons,
    ):
        if left is None or right is None:
            missing += 1
            if left is not None or right is not None:
                mismatches.append(
                    f"{feature_id}: missingness differs ({left!r} vs {right!r})"
                )
            elif left_reason != right_reason:
                mismatches.append(
                    f"{feature_id}: missing reasons differ "
                    f"({left_reason!r} vs {right_reason!r})"
                )
            continue
        defined += 1
        deviation = abs(float(left) - float(right))
        max_deviation = (
            deviation if max_deviation is None else max(max_deviation, deviation)
        )
        if deviation > tolerance:
            mismatches.append(
                f"{feature_id}: |{float(left)!r} - {float(right)!r}| = "
                f"{deviation:g} > {tolerance:g}"
            )
    return FeatureComparison(
        anchor_t_s=anchor_t_s,
        run_id=run_id,
        sample_identity=sample_identity,
        passed=not mismatches,
        mismatches=tuple(mismatches),
        max_abs_deviation=max_deviation,
        defined_values=defined,
        missing_values=missing,
    )


def predict_vector(model: GuardedModel, vector: FeatureVector) -> float:
    if tuple(vector.feature_ids) != tuple(model.ordered_feature_ids):
        raise W17SchemaError(
            "feature vector order does not match the guarded model contract"
        )
    if vector.registry_sha256 != model.manifest.get("feature_schema_hash"):
        raise W17SchemaError(
            "feature vector registry hash does not match the guarded model schema"
        )
    if vector.feature_schema_version != model.manifest.get("feature_version"):
        raise W17SchemaError(
            "feature vector version does not match the guarded model schema"
        )
    scores = model.predict_risk(vector.as_columns())
    if len(scores) != 1:
        raise W17Error("guarded model returned an unexpected score width")
    score = float(scores[0])
    if not math.isfinite(score):
        raise W17Error("guarded model produced a non-finite risk score")
    return score


def compare_risk_scores(
    offline: float,
    online: float,
    *,
    tolerance: float = SCORE_TOLERANCE,
) -> float:
    if tolerance > MAX_SCORE_TOLERANCE:
        raise W17ToleranceError(
            f"score tolerance {tolerance} exceeds the declared maximum "
            f"{MAX_SCORE_TOLERANCE}"
        )
    deviation = abs(float(offline) - float(online))
    if deviation > tolerance:
        raise W17Error(
            f"offline/online risk scores differ by {deviation:g} > {tolerance:g}"
        )
    return deviation


@dataclass(frozen=True)
class IllustrativeWarningRule:
    threshold: float
    source: str = WARNING_RULE_SOURCE
    status: str = WARNING_RULE_STATUS
    persistence: str = WARNING_PERSISTENCE


def derive_illustrative_warning_rule(
    model_manifest: Mapping[str, Any],
) -> tuple[IllustrativeWarningRule | None, str | None]:
    if model_manifest.get("score_semantics") != "risk_score":
        return None, WARNING_RULE_REFUSED
    if model_manifest.get("calibration_status") != "RISK_SCORE_ONLY":
        return None, WARNING_RULE_REFUSED
    threshold = model_manifest.get("operating_threshold")
    status = model_manifest.get("operating_threshold_status")
    if status != "ILLUSTRATIVE_NOT_FROZEN":
        return None, WARNING_RULE_REFUSED
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        return None, WARNING_RULE_REFUSED
    if not 0.0 < float(threshold) < 1.0:
        return None, WARNING_RULE_REFUSED
    return IllustrativeWarningRule(threshold=float(threshold)), None


def hypothetical_warning(
    score: float | None,
    rule: IllustrativeWarningRule | None,
) -> dict[str, Any]:
    if rule is None:
        return {
            "status": WARNING_RULE_REFUSED,
            "rule": None,
            "rule_status": None,
            "rule_source": None,
            "persistence": None,
        }
    if score is None:
        return {
            "status": WARNING_WITHHELD_REFUSED,
            "rule": f"risk_score >= {rule.threshold:g}",
            "rule_status": rule.status,
            "rule_source": rule.source,
            "persistence": rule.persistence,
        }
    triggered = float(score) >= rule.threshold
    return {
        "status": (
            "TRIGGERED_SYNTHETIC_ILLUSTRATIVE"
            if triggered
            else "NOT_TRIGGERED_SYNTHETIC_ILLUSTRATIVE"
        ),
        "rule": f"risk_score >= {rule.threshold:g}",
        "rule_status": rule.status,
        "rule_source": rule.source,
        "persistence": rule.persistence,
    }


def _prediction_id(
    *,
    run_id: str,
    boot_id: str,
    anchor_t_s: float,
    anchor_arrival_s: float | None,
    processing_time_s: float,
    input_ids_sha256: str,
    vector_sha256: str,
    model_sha256: str,
    feature_schema_sha256: str,
) -> str:
    payload = {
        "run_id": run_id,
        "boot_id": boot_id,
        "anchor_t_s": anchor_t_s,
        "anchor_arrival_s": anchor_arrival_s,
        "processing_time_s": processing_time_s,
        "input_telemetry_ids_sha256": input_ids_sha256,
        "feature_vector_sha256": vector_sha256,
        "model_artifact_sha256": model_sha256,
        "feature_schema_sha256": feature_schema_sha256,
        "layer": W17_LAYER_VERSION,
    }
    return "pred-w17-" + _sha256(_canonical_json(payload))[:32]


def build_trace_record(
    *,
    decision: AnchorDecision,
    model: GuardedModel,
    rule: IllustrativeWarningRule | None,
    risk_score: float | None,
    seq: int,
) -> dict[str, Any]:
    vector = decision.vector
    if vector is None:
        raise W17TraceError("a trace record requires the reproduced feature vector")
    manifest = model.manifest
    model_sha = str(manifest["model_artifact_sha256"])
    schema_sha = str(manifest["feature_schema_hash"])
    ordered_sha = str(manifest["ordered_feature_ids_sha256"])
    input_ids = list(decision.input_telemetry_ids)
    input_ids_sha = _sha256(_canonical_json(input_ids))
    prediction_id = _prediction_id(
        run_id=decision.run_id,
        boot_id=decision.boot_id,
        anchor_t_s=decision.anchor_t_s,
        anchor_arrival_s=decision.anchor_arrival_s,
        processing_time_s=decision.processing_time_s,
        input_ids_sha256=input_ids_sha,
        vector_sha256=vector.sha256(),
        model_sha256=model_sha,
        feature_schema_sha256=schema_sha,
    )
    record = {
        "record_schema": RECORD_SCHEMA,
        "evidence_class": EVIDENCE_SYNTHETIC,
        "source_type": "SYNTHETIC_DEVELOPMENT_REPLAY",
        "software_revision": W17_LAYER_VERSION,
        "run_id": decision.run_id,
        "boot_id": decision.boot_id,
        "seq": seq,
        "prediction_anchor_event_s": decision.anchor_t_s,
        "anchor_simulated_receipt_s": decision.anchor_arrival_s,
        "processing_simulated_s": decision.processing_time_s,
        "input_window_start_s": decision.input_window_start_s,
        "input_window_end_s": decision.input_window_end_s,
        "feature_version": vector.feature_schema_version,
        "feature_schema_sha256": schema_sha,
        "registry_sha256": vector.registry_sha256,
        "ordered_feature_ids_sha256": ordered_sha,
        "feature_vector_sha256": vector.sha256(),
        "input_telemetry_ids_sha256": input_ids_sha,
        "features": [
            {
                "feature_id": feature_id,
                "value": value,
                "missing_reason": reason,
            }
            for feature_id, value, reason in zip(
                vector.feature_ids, vector.values, vector.missing_reasons
            )
        ],
        "model": {
            "artifact_id": manifest["artifact_id"],
            "model_artifact_sha256": model_sha,
            "model_library_version": manifest["model_library_version"],
            "release_eligibility": manifest["release_eligibility"],
            "data_evidence_class": manifest["data_evidence_class"],
            "registered_for_operation": False,
            "deployed": False,
        },
        "prediction_id": prediction_id,
        "risk_score": risk_score,
        "score_semantics": "risk_score",
        "freshness": {
            "verdict": (
                "FRESH" if decision.ready else decision.disposition
            ),
            "disposition": decision.disposition,
            "reasons": list(decision.reasons),
            "anchor_age_s": decision.anchor_age_s,
            "electrical_age_s": decision.electrical_age_s,
            "door_age_s": decision.door_age_s,
            "policy_status": RUNTIME_FRESHNESS_POLICY_PENDING,
            "sanitized_input_ids": list(decision.sanitized_telemetry_ids),
            "late_observation_ids": list(decision.late_observation_ids),
        },
        "input_telemetry_ids": input_ids,
        "hypothetical_warning": hypothetical_warning(risk_score, rule),
        "hypothetical_policy": {
            "status": "NOT_EVALUATED",
            "owner": "MEMBER_D",
            "reason": "B_W17_DOES_NOT_OWN_POLICY",
            "would_command": None,
            "authorized_control_decision": None,
            "dispatchable": False,
            "physical_control_path": None,
        },
        "hypothetical_timing": {
            "anchor_event_s": decision.anchor_t_s,
            "simulated_receipt_s": decision.anchor_arrival_s,
            "simulated_processing_s": decision.processing_time_s,
            "timing_class": "SYNTHETIC_EVENT_TIME_OFFSET",
            "transport_latency_model": "SIMULATED_DETERMINISTIC_TEST_PARAMETER",
            "physical_latency": "NOT_MEASURED",
            "aiw": "NOT_ESTIMABLE",
        },
        "parity_evidence": None,
    }
    validate_trace_record(record)
    return record


_REQUIRED_TRACE_KEYS = {
    "record_schema",
    "evidence_class",
    "source_type",
    "software_revision",
    "run_id",
    "boot_id",
    "seq",
    "prediction_anchor_event_s",
    "anchor_simulated_receipt_s",
    "processing_simulated_s",
    "input_window_start_s",
    "input_window_end_s",
    "feature_version",
    "feature_schema_sha256",
    "ordered_feature_ids_sha256",
    "feature_vector_sha256",
    "input_telemetry_ids_sha256",
    "features",
    "model",
    "prediction_id",
    "risk_score",
    "score_semantics",
    "freshness",
    "input_telemetry_ids",
    "hypothetical_warning",
    "hypothetical_policy",
    "hypothetical_timing",
}


def validate_trace_record(record: Mapping[str, Any]) -> None:
    missing = _REQUIRED_TRACE_KEYS - set(record)
    if missing:
        raise W17TraceError(f"trace record is missing fields: {sorted(missing)}")
    if record["record_schema"] != RECORD_SCHEMA:
        raise W17TraceError("trace record schema mismatch")
    if record["evidence_class"] != EVIDENCE_SYNTHETIC:
        raise W17TraceError("trace record evidence class is not synthetic")
    if record["score_semantics"] != "risk_score":
        raise W17TraceError("trace score semantics must be risk_score")
    if record["hypothetical_policy"].get("dispatchable") is not False:
        raise W17TraceError("a hypothetical record must not be dispatchable")
    if record["hypothetical_policy"].get("would_command") is not None:
        raise W17TraceError("W17 does not produce a command")
    if record["hypothetical_policy"].get("authorized_control_decision") is not None:
        raise W17TraceError("a hypothetical policy record is not an authorized decision")
    for field_name in ("run_id", "boot_id", "prediction_id", "feature_vector_sha256"):
        if not str(record[field_name]).strip():
            raise W17TraceError(f"trace identity field {field_name!r} is empty")
    score = record["risk_score"]
    if score is not None:
        score = float(score)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise W17TraceError("risk_score is not a finite value in [0, 1]")
    model = record.get("model")
    if not isinstance(model, Mapping):
        raise W17TraceError("trace model identity is missing")
    for field_name in (
        "artifact_id",
        "model_artifact_sha256",
        "release_eligibility",
        "data_evidence_class",
    ):
        if not str(model.get(field_name, "")).strip():
            raise W17TraceError(f"trace model identity field {field_name!r} is empty")
    features = record["features"]
    if not isinstance(features, list) or not features:
        raise W17TraceError("trace features are missing")
    ids = [entry.get("feature_id") for entry in features]
    if len(ids) != len(set(ids)):
        raise W17TraceError("trace features contain duplicate identities")
    values = []
    reasons = []
    for entry in features:
        value = entry.get("value")
        if value is not None:
            numeric = float(value)
            if not math.isfinite(numeric):
                raise W17TraceError("trace feature value is non-finite")
            values.append(value)
        else:
            values.append(None)
        reasons.append(entry.get("missing_reason"))
    if features[0].get("value") is None and features[0].get("missing_reason") is None:
        raise W17TraceError("a missing feature must carry a missing reason")
    computed_vector_sha = _sha256(
        _canonical_json(
            {
                "feature_ids": ids,
                "values": values,
                "missing_reasons": reasons,
                "feature_schema_version": record["feature_version"],
                "registry_sha256": record["registry_sha256"],
            }
        )
    )
    if computed_vector_sha != record["feature_vector_sha256"]:
        raise W17TraceError(
            "feature_vector_sha256 does not bind the recorded feature values"
        )
    input_ids = record["input_telemetry_ids"]
    if not isinstance(input_ids, list) or not input_ids:
        raise W17TraceError("input telemetry identities are missing")
    computed_input_sha = _sha256(_canonical_json(input_ids))
    if computed_input_sha != record["input_telemetry_ids_sha256"]:
        raise W17TraceError(
            "input_telemetry_ids_sha256 does not bind the recorded inputs"
        )
    window_start = record["input_window_start_s"]
    window_end = record["input_window_end_s"]
    if window_start is not None and window_end is not None:
        start = float(window_start)
        end = float(window_end)
        if not math.isfinite(start) or not math.isfinite(end) or start > end:
            raise W17TraceError("input window bounds are invalid")
        if end != float(record["prediction_anchor_event_s"]):
            raise W17TraceError(
                "the input window must end at the prediction anchor"
            )
    receipt = record["anchor_simulated_receipt_s"]
    if receipt is not None and not math.isfinite(float(receipt)):
        raise W17TraceError("anchor simulated receipt time is not finite")
    expected_prediction_id = _prediction_id(
        run_id=str(record["run_id"]),
        boot_id=str(record["boot_id"]),
        anchor_t_s=float(record["prediction_anchor_event_s"]),
        anchor_arrival_s=None if receipt is None else float(receipt),
        processing_time_s=float(record["processing_simulated_s"]),
        input_ids_sha256=record["input_telemetry_ids_sha256"],
        vector_sha256=record["feature_vector_sha256"],
        model_sha256=str(record["model"]["model_artifact_sha256"]),
        feature_schema_sha256=str(record["feature_schema_sha256"]),
    )
    if record["prediction_id"] != expected_prediction_id:
        raise W17TraceError(
            "prediction_id does not bind the input, timing, feature and model "
            "identities"
        )


@dataclass
class ShadowTrace:
    header: dict[str, Any]
    records: list[dict[str, Any]] = field(default_factory=list)
    _by_prediction: dict[str, str] = field(default_factory=dict)

    def add(self, record: Mapping[str, Any]) -> None:
        validate_trace_record(record)
        self._check_warning_against_header(record)
        prediction_id = str(record["prediction_id"])
        canonical = _canonical_json(record)
        existing = self._by_prediction.get(prediction_id)
        if existing is not None and existing != canonical:
            raise W17TraceError(
                f"duplicate prediction id {prediction_id!r} with contradictory "
                "evidence"
            )
        if existing is not None:
            return
        self._by_prediction[prediction_id] = canonical
        self.records.append(dict(record))

    def _check_warning_against_header(self, record: Mapping[str, Any]) -> None:
        rule = self.header.get("warning_rule")
        if not isinstance(rule, Mapping) or rule.get("threshold") is None:
            return
        warning = record["hypothetical_warning"]
        if warning.get("rule_status") != rule.get("status"):
            raise W17TraceError(
                "the hypothetical warning rule status differs from the trace header"
            )
        score = record["risk_score"]
        if score is None:
            expected = WARNING_WITHHELD_REFUSED
        elif float(score) >= float(rule["threshold"]):
            expected = "TRIGGERED_SYNTHETIC_ILLUSTRATIVE"
        else:
            expected = "NOT_TRIGGERED_SYNTHETIC_ILLUSTRATIVE"
        if warning.get("status") != expected:
            raise W17TraceError(
                "the hypothetical warning status does not follow from the "
                "recorded score and illustrative rule"
            )

    def to_dict(self) -> dict[str, Any]:
        ordered = sorted(
            self.records,
            key=lambda item: (
                item["run_id"],
                item["prediction_anchor_event_s"],
                item["prediction_id"],
            ),
        )
        payload = {
            "trace_schema": TRACE_SCHEMA,
            "header": dict(self.header),
            "record_count": len(ordered),
            "records": ordered,
        }
        payload["trace_sha256"] = _sha256(_canonical_json(payload))
        return payload


@dataclass(frozen=True)
class ParityResult:
    feature_ids: tuple[str, ...]
    replay_run_count: int
    anchor_count: int
    compared_anchor_count: int
    refused_by_reason: tuple[tuple[str, int], ...]
    excluded_degraded_windows: int
    feature_comparisons: tuple[FeatureComparison, ...]
    prediction_comparisons: tuple[PredictionComparison, ...]
    defined_values: int
    missing_values: int
    max_feature_deviation: float | None
    max_score_deviation: float | None
    first_mismatch: str | None
    mutation_proof: Mapping[str, Any]
    trace: Mapping[str, Any]
    trace_sha256: str
    replay_inputs_sha256: str
    replay_input_count: int
    late_observation_count: int
    unconsumed_record_count: int
    refusals: tuple[Mapping[str, Any], ...]

    @property
    def feature_parity_verified(self) -> bool:
        return (
            self.compared_anchor_count > 0
            and self.feature_comparisons
            and all(item.passed for item in self.feature_comparisons)
            and bool(self.mutation_proof.get("detected"))
        )

    @property
    def prediction_parity_verified(self) -> bool:
        return (
            self.feature_parity_verified
            and bool(self.prediction_comparisons)
            and all(item.passed for item in self.prediction_comparisons)
        )

    @property
    def offline_replay_verdict(self) -> str:
        if self.feature_parity_verified and self.prediction_parity_verified:
            return EVIDENCE_OFFLINE_REPLAY
        return EVIDENCE_NOT_ESTABLISHED


def _record_payload(record: TelemetryRecord) -> dict[str, Any]:
    return {
        "telemetry_id": record.telemetry_id,
        "event_time_s": record.event_time_s,
        "arrival_time_s": record.arrival_time_s,
        "electrical_observed_at_s": record.electrical_observed_at_s,
        "door_observed_at_s": record.door_observed_at_s,
    }


def _mutation_proof(
    model: GuardedModel,
    offline_vector: FeatureVector,
    online_vector: FeatureVector,
    online_score: float,
) -> dict[str, Any]:
    inspection = model.manifest.get("model_inspection", {})
    unused = list(inspection.get("unused_feature_ids", ()))
    chosen = None
    chosen_index = None
    for feature_id in unused:
        if feature_id not in online_vector.feature_ids:
            continue
        index = online_vector.feature_ids.index(feature_id)
        if online_vector.values[index] is not None:
            chosen = feature_id
            chosen_index = index
            break
    if chosen is None:
        return {
            "performed": False,
            "reason": "NO_DEFINED_UNUSED_FEATURE_AVAILABLE",
            "detected": False,
        }
    mutated_values = list(online_vector.values)
    mutated_values[chosen_index] = float(mutated_values[chosen_index]) + 0.5
    mutated = replace(online_vector, values=tuple(mutated_values))
    comparison = compare_feature_vectors(offline_vector, mutated)
    mutated_score = predict_vector(model, mutated)
    return {
        "performed": True,
        "feature_id": chosen,
        "mutation_delta": 0.5,
        "feature_parity_detected": not comparison.passed,
        "detected": not comparison.passed,
        "mismatch": comparison.mismatches[0] if comparison.mismatches else None,
        "online_score": online_score,
        "mutated_score": mutated_score,
        "score_unchanged": abs(online_score - mutated_score) <= SCORE_TOLERANCE,
    }


def run_shadow_parity(
    trajectories: Sequence[Trajectory],
    registry: FeatureRegistry,
    *,
    model: GuardedModel,
    anchors_by_run: Mapping[str, Sequence[float]],
    policy: FreshnessPolicy | None = None,
    replay_config: ReplayConfig | None = None,
    warning_rule: IllustrativeWarningRule | None = None,
    arrival_overrides: Mapping[str, Mapping[str, float]] | None = None,
) -> ParityResult:
    """Reconcile the offline batch path against a stateful online replay."""
    feature_ids = tuple(model.ordered_feature_ids)
    if tuple(model.manifest["ordered_feature_ids"]) != feature_ids:
        raise W17SchemaError("model manifest feature order differs from the loader")
    if model.manifest["feature_schema_hash"] != registry.schema_sha256:
        raise W17SchemaError("model feature schema hash differs from the registry")
    config = replay_config or ReplayConfig()
    selected_policy = policy or FreshnessPolicy()
    rule = (
        warning_rule
        if warning_rule is not None
        else derive_illustrative_warning_rule(model.manifest)[0]
    )
    trace = ShadowTrace(
        header={
            "trace_schema": TRACE_SCHEMA,
            "layer": W17_LAYER_VERSION,
            "evidence_class": EVIDENCE_SYNTHETIC,
            "source_type": "SYNTHETIC_DEVELOPMENT_REPLAY",
            "feature_version": registry.feature_version,
            "feature_schema_sha256": registry.schema_sha256,
            "ordered_feature_ids_sha256": model.manifest[
                "ordered_feature_ids_sha256"
            ],
            "model": {
                "artifact_id": model.manifest["artifact_id"],
                "model_artifact_sha256": model.manifest["model_artifact_sha256"],
                "release_eligibility": model.manifest["release_eligibility"],
                "data_evidence_class": model.manifest["data_evidence_class"],
            },
            "warning_rule": (
                None
                if rule is None
                else {
                    "rule": f"risk_score >= {rule.threshold:g}",
                    "threshold": rule.threshold,
                    "status": rule.status,
                    "source": rule.source,
                    "persistence": rule.persistence,
                }
            ),
            "freshness_policy_status": RUNTIME_FRESHNESS_POLICY_PENDING,
            "channel_timestamp_basis": "FRAME_EVENT_TIME_WHEN_UNATTESTED",
            "freshness_parameters": {
                "class": SYNTHETIC_TEST_PARAMETER,
                "max_anchor_input_age_s": selected_policy.max_anchor_input_age_s,
                "max_electrical_age_s": selected_policy.max_electrical_age_s,
                "max_door_age_s": selected_policy.max_door_age_s,
            },
            "timing_semantics": {
                "class": "SYNTHETIC_EVENT_TIME_OFFSET",
                "transport_delay_s": config.transport_delay_s,
                "processing_delay_s": config.processing_delay_s,
                "physical_latency": "NOT_MEASURED",
            },
            "physical_control_capability": False,
            "live_shadow_verdict": VERDICT_LIVE_NOT_ESTABLISHED,
        }
    )
    feature_comparisons: list[FeatureComparison] = []
    prediction_comparisons: list[PredictionComparison] = []
    refusal_counts: dict[str, int] = {}
    refusals: list[dict[str, Any]] = []
    defined_values = 0
    missing_values = 0
    max_feature_deviation: float | None = None
    max_score_deviation: float | None = None
    first_mismatch: str | None = None
    compared_anchors = 0
    anchor_count = 0
    excluded_degraded = 0
    late_count = 0
    unconsumed = 0
    replay_inputs: list[dict[str, Any]] = []
    mutation: dict[str, Any] = {"performed": False, "detected": False}
    mutation_done = False
    for trajectory in sorted(
        trajectories, key=lambda item: (item.run_id or "", item.boot_id)
    ):
        run_id = trajectory.run_id
        if run_id is None:
            raise W17Error("a replay trajectory has no run identity")
        if run_id not in anchors_by_run:
            raise W17Error(f"no anchors were declared for run {run_id!r}")
        anchors = sorted({float(value) for value in anchors_by_run[run_id]})
        if not anchors:
            raise W17Error(f"run {run_id!r} has no anchors")
        sample_times = {sample.time_s for sample in trajectory.samples}
        for anchor in anchors:
            if anchor not in sample_times:
                raise W17Error(
                    f"anchor {anchor!r} is not an observed sample time in "
                    f"run {run_id!r}"
                )
        run_overrides = dict((arrival_overrides or {}).get(run_id, {}))
        records = [
            TelemetryRecord(
                sample=sample,
                arrival_time_s=run_overrides.get(
                    sample.identity, sample.time_s + config.transport_delay_s
                ),
                electrical_observed_at_s=sample.time_s,
                door_observed_at_s=sample.time_s,
            )
            for sample in trajectory.samples
        ]
        records.sort(key=lambda item: (item.arrival_time_s, item.telemetry_id))
        record_by_id = {record.telemetry_id: record for record in records}
        arrival_by_identity = {
            record.telemetry_id: record.arrival_time_s for record in records
        }
        replay_inputs.extend(_record_payload(record) for record in records)
        session = ReplaySession(
            template=trajectory,
            registry=registry,
            feature_ids=feature_ids,
            policy=selected_policy,
        )
        cursor = 0
        for anchor in anchors:
            anchor_count += 1
            processing_time = anchor + config.processing_delay_s
            while (
                cursor < len(records)
                and records[cursor].arrival_time_s <= processing_time
            ):
                session.ingest(records[cursor])
                cursor += 1
            decision = session.feature_row_at(anchor, processing_time)
            seq = next(
                sample.seq
                for sample in trajectory.samples
                if sample.time_s == anchor
            )
            if not decision.ready:
                refusal_counts[decision.disposition] = (
                    refusal_counts.get(decision.disposition, 0) + 1
                )
                if decision.vector is not None:
                    trace.add(
                        build_trace_record(
                            decision=decision,
                            model=model,
                            rule=rule,
                            risk_score=None,
                            seq=seq,
                        )
                    )
                refusals.append(
                    {
                        "run_id": run_id,
                        "boot_id": trajectory.boot_id,
                        "anchor_t_s": anchor,
                        "disposition": decision.disposition,
                        "reasons": list(decision.reasons),
                    }
                )
                continue
            authorized = tuple(
                sample
                for sample in trajectory.samples
                if sample.time_s <= anchor
                and arrival_by_identity[sample.identity] <= processing_time
            )
            if not authorized:
                raise W17Error(
                    "an online-ready anchor has no authorized reference history"
                )
            online_inputs_ok = all(
                record_by_id[telemetry_id].event_time_s <= anchor
                and record_by_id[telemetry_id].arrival_time_s <= processing_time
                for telemetry_id in decision.input_telemetry_ids
            )
            offline_inputs_ok = all(
                sample.time_s <= anchor
                and arrival_by_identity[sample.identity] <= processing_time
                for sample in authorized
            )
            no_future_input = online_inputs_ok and offline_inputs_ok
            if not no_future_input:
                raise W17Error(
                    "a reference or replay input was not available at the "
                    "prediction time"
                )
            offline_prefix = replace(trajectory, samples=authorized)
            offline_row = feature_rows(
                offline_prefix, registry, anchors=[anchor]
            )[0]
            offline_vector = _feature_vector_from_row(
                offline_row, registry, feature_ids
            )
            online_vector = decision.vector
            assert online_vector is not None
            comparison = compare_feature_vectors(
                offline_vector,
                online_vector,
                anchor_t_s=anchor,
                run_id=run_id,
                sample_identity=offline_row.sample_identity,
            )
            if decision.sanitized_telemetry_ids:
                excluded_degraded += 1
                refusals.append(
                    {
                        "run_id": run_id,
                        "boot_id": trajectory.boot_id,
                        "anchor_t_s": anchor,
                        "disposition": "EXCLUDED_DEGRADED_WINDOW",
                        "reasons": [
                            "WINDOW_CHANNEL_STALENESS_SANITIZED:"
                            + ",".join(decision.sanitized_telemetry_ids)
                        ],
                    }
                )
                trace.add(
                    build_trace_record(
                        decision=decision,
                        model=model,
                        rule=rule,
                        risk_score=None,
                        seq=seq,
                    )
                )
                continue
            compared_anchors += 1
            feature_comparisons.append(comparison)
            defined_values += comparison.defined_values
            missing_values += comparison.missing_values
            if comparison.max_abs_deviation is not None:
                max_feature_deviation = (
                    comparison.max_abs_deviation
                    if max_feature_deviation is None
                    else max(max_feature_deviation, comparison.max_abs_deviation)
                )
            if not comparison.passed and first_mismatch is None:
                first_mismatch = (
                    f"FEATURE:{run_id}:{anchor:g}:{comparison.mismatches[0]}"
                )
            offline_score = predict_vector(model, offline_vector)
            online_score = predict_vector(model, online_vector)
            try:
                deviation = compare_risk_scores(offline_score, online_score)
                prediction_passed = True
            except W17Error as exc:
                deviation = abs(offline_score - online_score)
                prediction_passed = False
                if first_mismatch is None:
                    first_mismatch = f"SCORE:{run_id}:{anchor:g}:{exc}"
            max_score_deviation = (
                deviation
                if max_score_deviation is None
                else max(max_score_deviation, deviation)
            )
            prediction_comparisons.append(
                PredictionComparison(
                    anchor_t_s=anchor,
                    run_id=run_id,
                    sample_identity=offline_row.sample_identity,
                    passed=prediction_passed,
                    offline_score=offline_score,
                    online_score=online_score,
                    abs_deviation=deviation,
                )
            )
            record = build_trace_record(
                decision=decision,
                model=model,
                rule=rule,
                risk_score=online_score,
                seq=seq,
            )
            record["parity_evidence"] = {
                "offline_feature_parity": comparison.passed,
                "offline_prediction_parity": prediction_passed,
                "offline_reference_source": "W10_CANONICAL_BATCH_PIPELINE",
                "online_replay_source": "W17_STATEFUL_STREAMING_REPLAY",
                "feature_tolerance": FEATURE_TOLERANCE,
                "score_tolerance": SCORE_TOLERANCE,
                "no_future_input_verified": no_future_input,
                "authorized_input_count": len(authorized),
                "online_input_count": len(decision.input_telemetry_ids),
            }
            trace.add(record)
            if not mutation_done:
                mutation = _mutation_proof(
                    model, offline_vector, online_vector, online_score
                )
                mutation_done = True
        unconsumed += len(records) - cursor
        late_count += len(session.late_observation_ids)
    trace_payload = trace.to_dict()
    return ParityResult(
        feature_ids=feature_ids,
        replay_run_count=len({item.run_id for item in trajectories}),
        anchor_count=anchor_count,
        compared_anchor_count=compared_anchors,
        refused_by_reason=tuple(sorted(refusal_counts.items())),
        excluded_degraded_windows=excluded_degraded,
        feature_comparisons=tuple(feature_comparisons),
        prediction_comparisons=tuple(prediction_comparisons),
        defined_values=defined_values,
        missing_values=missing_values,
        max_feature_deviation=max_feature_deviation,
        max_score_deviation=max_score_deviation,
        first_mismatch=first_mismatch,
        mutation_proof=mutation,
        trace=trace_payload,
        trace_sha256=trace_payload["trace_sha256"],
        replay_inputs_sha256=_sha256(_canonical_json(replay_inputs)),
        replay_input_count=len(replay_inputs),
        late_observation_count=late_count,
        unconsumed_record_count=unconsumed,
        refusals=tuple(refusals),
    )


@dataclass(frozen=True)
class ReadinessAssessment:
    level_1_offline_feature_parity: str
    level_2_offline_prediction_parity: str
    level_3_shadow_trace_software: str
    level_4_real_online_shadow: str
    evidence_class: str
    physical_shadow: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_1_offline_feature_parity": self.level_1_offline_feature_parity,
            "level_2_offline_prediction_parity": self.level_2_offline_prediction_parity,
            "level_3_shadow_trace_software": self.level_3_shadow_trace_software,
            "level_4_real_online_shadow": self.level_4_real_online_shadow,
            "evidence_class": self.evidence_class,
            "physical_shadow": self.physical_shadow,
            "reasons": list(self.reasons),
        }


def assess_shadow_readiness(
    parity: ParityResult,
    *,
    trace_record_count: int,
    external_dependencies: Mapping[str, str],
) -> ReadinessAssessment:
    level1 = (
        VERDICT_FEATURE_PARITY if parity.feature_parity_verified else VERDICT_NOT_VERIFIED
    )
    level2 = (
        VERDICT_PREDICTION_PARITY
        if parity.prediction_parity_verified
        else VERDICT_NOT_VERIFIED
    )
    trace_ok = (
        trace_record_count > 0
        and parity.trace.get("trace_schema") == TRACE_SCHEMA
        and all(
            record["hypothetical_policy"]["dispatchable"] is False
            for record in parity.trace.get("records", [])
        )
    )
    level3 = VERDICT_TRACE if trace_ok else VERDICT_NOT_VERIFIED
    level4 = VERDICT_LIVE_NOT_ESTABLISHED
    evidence = (
        EVIDENCE_OFFLINE_REPLAY
        if level1 == VERDICT_FEATURE_PARITY
        and level2 == VERDICT_PREDICTION_PARITY
        and level3 == VERDICT_TRACE
        else EVIDENCE_NOT_ESTABLISHED
    )
    reasons = [
        "NO_PHYSICAL_DATASET",
        "NO_FROZEN_PRIMARY_HORIZON",
        "MODEL_RC_NOT_ISSUED",
        "G4_NOT_READY",
        "RUNTIME_FRESHNESS_POLICY_PENDING_C_D",
    ]
    for name, status in sorted(external_dependencies.items()):
        if status not in ("ESTABLISHED", "ACCEPTED"):
            reasons.append(f"EXTERNAL_DEPENDENCY_{name}_{status}")
    return ReadinessAssessment(
        level_1_offline_feature_parity=level1,
        level_2_offline_prediction_parity=level2,
        level_3_shadow_trace_software=level3,
        level_4_real_online_shadow=level4,
        evidence_class=evidence,
        physical_shadow=VERDICT_PHYSICAL_BLOCKED,
        reasons=tuple(reasons),
    )


def fixture_identity(trajectories: Sequence[Trajectory]) -> str:
    payload = []
    for trajectory in sorted(trajectories, key=lambda item: item.run_id or ""):
        payload.append(
            {
                "run_id": trajectory.run_id,
                "boot_id": trajectory.boot_id,
                "device_id": trajectory.device_id,
                "source_sha256": trajectory.source_sha256,
                "scenario_id": trajectory.scenario_id,
                "samples": [
                    {
                        "identity": sample.identity,
                        "time_s": sample.time_s,
                        "payload": list(sample.payload()),
                    }
                    for sample in trajectory.samples
                ],
            }
        )
    return _sha256(_canonical_json(payload))


def freshness_probes(
    template: Trajectory,
    registry: FeatureRegistry,
    feature_ids: Sequence[str],
    *,
    stale_trajectory: Trajectory | None = None,
    degraded_trajectory: Trajectory | None = None,
    counter_reset_trajectory: Trajectory | None = None,
    polarity_trajectory: Trajectory | None = None,
    unknown_door_trajectory: Trajectory | None = None,
) -> tuple[dict[str, Any], ...]:
    """Executable freshness/temporal probes used by the W17 report."""
    probes: list[dict[str, Any]] = []

    def probe(name: str, outcome: str, detail: Mapping[str, Any]) -> None:
        probes.append({"probe": name, "outcome": outcome, "detail": dict(detail)})

    def fresh_session(trajectory: Trajectory) -> ReplaySession:
        return ReplaySession(
            template=trajectory,
            registry=registry,
            feature_ids=feature_ids,
        )

    base = fresh_session(template)
    for sample in template.samples:
        base.ingest(
            TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
        )
    fresh = base.feature_row_at(40.0, 41.0)
    probe(
        "fresh_anchor",
        "READY" if fresh.ready else "REFUSED",
        {"disposition": fresh.disposition, "reasons": list(fresh.reasons)},
    )
    if fresh.vector is not None:
        reasons = dict(
            zip(fresh.vector.feature_ids, fresh.vector.missing_reasons)
        )
        probe(
            "fresh_anchor_missingness",
            "OBSERVED",
            {
                "rolling_mean_reason": reasons.get(
                    "rolling_mean_temperature_60s"
                ),
                "door_open_reason": reasons.get("door_open"),
            },
        )

    late_session = fresh_session(template)
    late_sample = next(
        sample for sample in template.samples if sample.time_s == 30.0
    )
    for sample in template.samples:
        if sample.time_s <= 60.0 and sample.time_s != 30.0:
            late_session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    before_late = late_session.feature_row_at(40.0, 41.0)
    late_session.ingest(
        TelemetryRecord(sample=late_sample, arrival_time_s=60.0)
    )
    after_late = late_session.feature_row_at(40.0, 41.0)
    later_anchor = late_session.feature_row_at(60.0, 61.0)
    frozen = (
        before_late.vector is not None
        and after_late.vector is not None
        and before_late.vector.sha256() == after_late.vector.sha256()
    )
    finally_included = late_sample.identity in later_anchor.input_telemetry_ids
    probe(
        "late_packet_excluded",
        "PASS" if frozen and finally_included else "FAIL",
        {
            "late_identity": late_sample.identity,
            "earlier_prediction_unchanged": frozen,
            "included_only_at_later_anchor": finally_included,
            "late_observations": list(after_late.late_observation_ids),
        },
    )

    future_session = fresh_session(template)
    future_sample = replace(
        next(sample for sample in template.samples if sample.time_s == 120.0),
        seq=999,
        time_s=100.0,
    )
    for sample in template.samples:
        if sample.time_s <= 40.0:
            future_session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    future_session.ingest(
        TelemetryRecord(sample=future_sample, arrival_time_s=100.25)
    )
    future_decision = future_session.feature_row_at(40.0, 41.0)
    future_equal = (
        fresh.vector is not None
        and future_decision.vector is not None
        and fresh.vector.sha256() == future_decision.vector.sha256()
    )
    probe(
        "future_event_excluded",
        "PASS" if future_equal else "FAIL",
        {"future_identity": future_sample.identity},
    )

    if stale_trajectory is not None:
        stale_session = fresh_session(stale_trajectory)
        for sample in stale_trajectory.samples:
            stale_session.ingest(
                TelemetryRecord(
                    sample=sample,
                    arrival_time_s=sample.time_s + 0.25,
                    electrical_observed_at_s=sample.time_s - 30.0,
                )
            )
        stale_decision = stale_session.feature_row_at(100.0, 101.0)
        reasons: dict[str, str] = {}
        if stale_decision.vector is not None:
            reasons = dict(
                zip(
                    stale_decision.vector.feature_ids,
                    stale_decision.vector.missing_reasons,
                )
            )
        probe(
            "stale_pzem",
            "REFUSED_STALE" if stale_decision.disposition == REFUSED_STALE_INPUT else "UNEXPECTED",
            {
                "disposition": stale_decision.disposition,
                "cooling_power_reason": reasons.get("cooling_power_w"),
                "cooling_power_is_zero": any(
                    value == 0.0
                    for feature_id, value in zip(
                        stale_decision.vector.feature_ids,
                        stale_decision.vector.values,
                    )
                    if feature_id == "cooling_power_w"
                )
                if stale_decision.vector is not None
                else None,
            },
        )

    if degraded_trajectory is not None:
        degraded_session = fresh_session(degraded_trajectory)
        for sample in degraded_trajectory.samples:
            degraded_session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
        degraded_decision = degraded_session.feature_row_at(100.0, 101.0)
        probe(
            "degraded_channels",
            "REFUSED_UNTRUSTED"
            if degraded_decision.disposition == REFUSED_UNTRUSTED_INPUT
            else "UNEXPECTED",
            {
                "disposition": degraded_decision.disposition,
                "reasons": list(degraded_decision.reasons),
            },
        )

    if counter_reset_trajectory is not None:
        counter_session = fresh_session(counter_reset_trajectory)
        for sample in counter_reset_trajectory.samples:
            counter_session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
        counter_decision = counter_session.feature_row_at(100.0, 101.0)
        reasons = {}
        if counter_decision.vector is not None:
            reasons = dict(
                zip(
                    counter_decision.vector.feature_ids,
                    counter_decision.vector.missing_reasons,
                )
            )
        probe(
            "counter_reset",
            "OBSERVED",
            {
                "disposition": counter_decision.disposition,
                "energy_counter_reason": reasons.get("energy_counter_wh"),
            },
        )

    if polarity_trajectory is not None:
        polarity_session = fresh_session(polarity_trajectory)
        for sample in polarity_trajectory.samples:
            polarity_session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
        polarity_decision = polarity_session.feature_row_at(100.0, 101.0)
        probe(
            "door_polarity_unattested",
            "REFUSED_UNTRUSTED"
            if polarity_decision.disposition == REFUSED_UNTRUSTED_INPUT
            else "UNEXPECTED",
            {
                "disposition": polarity_decision.disposition,
                "reasons": list(polarity_decision.reasons),
            },
        )

    if unknown_door_trajectory is not None:
        unknown_session = fresh_session(unknown_door_trajectory)
        for sample in unknown_door_trajectory.samples:
            unknown_session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
        unknown_decision = unknown_session.feature_row_at(80.0, 81.0)
        unknown_reasons: dict[str, str] = {}
        if unknown_decision.vector is not None:
            unknown_reasons = dict(
                zip(
                    unknown_decision.vector.feature_ids,
                    unknown_decision.vector.missing_reasons,
                )
            )
        probe(
            "unknown_door",
            "REFUSED_UNTRUSTED"
            if unknown_decision.disposition == REFUSED_UNTRUSTED_INPUT
            else "UNEXPECTED",
            {
                "disposition": unknown_decision.disposition,
                "reasons": list(unknown_decision.reasons),
                "door_open_reason": unknown_reasons.get("door_open"),
                "duration_reason": unknown_reasons.get("duration_so_far"),
                "time_since_open_reason": unknown_reasons.get("time_since_open"),
            },
        )

    return tuple(probes)
