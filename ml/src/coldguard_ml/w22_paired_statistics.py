"""W22 pure paired statistics (Layer A — no file intake, no physical data).

Canonical anchors: Doc 03 sections 68-83, 95-102, 130-135; Doc 05B
section 50; ``ml/statistical-analysis-plan-v0.md`` sections 4.1-4.8 and
``ml/metric-spec.md``.

The statistical unit is one accepted matched Controller A/B pair.  The
frozen improvement convention is ``I_i = Y_A,i - Y_B,i``; for
lower-is-better outcomes a positive value means Controller B improved.
The module accepts only explicit in-memory numeric pairs and stamps every
result with the mandatory ``SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY`` label;
real-outcome admission is a separate future authorization bridge that this
module deliberately does not implement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

W22_PAIRED_STATISTICS_LAYER_VERSION = "coldguard-w22-paired-statistics-v1"
SIGN_CONVENTION = "I_i = Y_A,i - Y_B,i"
LABEL_SYNTHETIC_TEST_ONLY = "SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY"
TEST_ONLY_BANNER = (
    "SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY — toy fixture; "
    "not a ColdGuard physical A/B result"
)
QUANTILE_CONVENTION = "LINEAR_INTERPOLATION_TYPE7_HYNDMAN_FAN"
PAIR_ORDER_POLICY = "CANONICAL_SORT_BY_PAIR_ID"
MIN_PAIRS_FOR_INFERENCE = 3

CONTROLLER_A = "A"
CONTROLLER_B = "B"
CONTROLLERS = (CONTROLLER_A, CONTROLLER_B)

OUTCOME_ROLE_PRIMARY = "PRIMARY"
OUTCOME_ROLE_SECONDARY = "SECONDARY"
OUTCOME_ROLE_EXPLORATORY = "EXPLORATORY"
OUTCOME_ROLES = (
    OUTCOME_ROLE_PRIMARY,
    OUTCOME_ROLE_SECONDARY,
    OUTCOME_ROLE_EXPLORATORY,
)

UNIT_THERMAL_EXPOSURE = "°C·s"
UNIT_THERMAL_EXPOSURE_MIN = "°C·min"
UNIT_RECOVERY_TIME = "s"
UNIT_PEAK_TEMPERATURE = "°C"
UNIT_COOLING_BRANCH_ENERGY = "Wh"
SUPPORTED_UNITS = frozenset(
    {
        UNIT_THERMAL_EXPOSURE,
        UNIT_THERMAL_EXPOSURE_MIN,
        UNIT_RECOVERY_TIME,
        UNIT_PEAK_TEMPERATURE,
        UNIT_COOLING_BRANCH_ENERGY,
    }
)

DIRECTION_IMPROVED = "CONTROLLER_B_IMPROVED"
DIRECTION_WORSENED = "CONTROLLER_B_WORSENED"
DIRECTION_NO_DIFFERENCE = "NO_OBSERVED_DIFFERENCE"

DZ_DEFINED = "DEFINED"
DZ_UNDEFINED_ZERO_SD = "UNDEFINED_ZERO_SD"
DZ_UNDEFINED_INSUFFICIENT_N = "UNDEFINED_INSUFFICIENT_N"

RELATIVE_DEFINED = "DEFINED"
RELATIVE_UNDEFINED_NO_FLOOR = "UNDEFINED_DENOMINATOR_FLOOR_NOT_DECLARED"
RELATIVE_UNDEFINED_FLOOR = "UNDEFINED_DENOMINATOR_NOT_MEANINGFUL"
RELATIVE_UNDEFINED_NON_POSITIVE = "UNDEFINED_NON_POSITIVE_DENOMINATOR"

REASON_NON_NUMERIC_OUTCOME = "NON_NUMERIC_OUTCOME_VALUE"
REASON_NON_FINITE_OUTCOME = "NON_FINITE_OUTCOME_VALUE"
REASON_MISSING_OUTCOME = "MISSING_OUTCOME_VALUE"
REASON_EMPTY_IDENTITY = "EMPTY_IDENTITY_FIELD"
REASON_DUPLICATE_PAIR_ID = "DUPLICATE_PAIR_ID"
REASON_DUPLICATE_PAIR_BLOCK = "DUPLICATE_PAIR_BLOCK"
REASON_DUPLICATE_RUN_ID = "RUN_ID_REUSED_ACROSS_PAIRS"
REASON_SAME_RUN_BOTH_ARMS = "SAME_RUN_ON_BOTH_ARMS"
REASON_ARM_CONTROLLER = "ARM_CONTROLLER_LABEL_INVALID"
REASON_UNIT_MISMATCH = "UNIT_MISMATCH_BETWEEN_ARMS_OR_DATASET"
REASON_OUTCOME_MISMATCH = "OUTCOME_ID_MISMATCH"
REASON_ROLE_MISMATCH = "OUTCOME_ROLE_MISMATCH"
REASON_EXCLUDED_OVERLAP = "EXCLUDED_PAIR_ALSO_ADMITTED"
REASON_EXCLUDED_REASON = "EXCLUDED_PAIR_REASON_MISSING"
REASON_EVIDENCE_LABEL = "REAL_OUTCOME_BRIDGE_NOT_IMPLEMENTED"
REASON_UNKNOWN_PAIR = "UNKNOWN_PAIR_ID"


class W22StatisticsError(ValueError):
    """A paired-statistics request is malformed or scientifically invalid."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


class W22BoundaryError(W22StatisticsError):
    """A W22 layer boundary (test-only versus real analysis) was violated."""


@dataclass(frozen=True)
class PairArm:
    """One explicitly identified controller arm inside a matched pair."""

    run_id: str
    controller: str
    value: float
    unit: str


@dataclass(frozen=True)
class PairRecord:
    """One admitted matched Controller A/B pair with numeric outcomes."""

    pair_id: str
    pair_block_id: str
    arm_a: PairArm
    arm_b: PairArm
    outcome_id: str
    outcome_role: str = OUTCOME_ROLE_PRIMARY
    session_id: str | None = None
    rig_id: str | None = None


@dataclass(frozen=True)
class ExcludedPair:
    """A pair that was excluded upstream; it contributes zero numeric values."""

    pair_id: str
    reason_code: str


@dataclass(frozen=True)
class PairedDataset:
    """Canonically ordered, validated paired observations (toy only)."""

    outcome_id: str
    unit: str
    outcome_role: str
    pairs: tuple[PairRecord, ...]
    excluded_pairs: tuple[ExcludedPair, ...]
    evidence_label: str = LABEL_SYNTHETIC_TEST_ONLY

    @property
    def pair_count(self) -> int:
        return len(self.pairs)

    @property
    def pair_ids(self) -> tuple[str, ...]:
        return tuple(pair.pair_id for pair in self.pairs)

    @property
    def y_a(self) -> tuple[float, ...]:
        return tuple(float(pair.arm_a.value) for pair in self.pairs)

    @property
    def y_b(self) -> tuple[float, ...]:
        return tuple(float(pair.arm_b.value) for pair in self.pairs)

    @property
    def improvements(self) -> tuple[float, ...]:
        return tuple(
            float(pair.arm_a.value) - float(pair.arm_b.value)
            for pair in self.pairs
        )

    @property
    def session_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted({pair.session_id for pair in self.pairs if pair.session_id})
        )

    @property
    def rig_ids(self) -> tuple[str, ...]:
        return tuple(sorted({pair.rig_id for pair in self.pairs if pair.rig_id}))


@dataclass(frozen=True)
class PairedDescriptive:
    """Pair-level descriptive statistics; inferential fields may be undefined."""

    outcome_id: str
    unit: str
    outcome_role: str
    sign_convention: str
    evidence_label: str
    pair_count: int
    excluded_pair_count: int
    excluded_reasons: tuple[tuple[str, str], ...]
    pair_ids: tuple[str, ...]
    y_a: tuple[float, ...]
    y_b: tuple[float, ...]
    improvements: tuple[float, ...]
    mean_improvement: float | None
    median_improvement: float | None
    sample_standard_deviation: float | None
    population_standard_deviation: float | None
    q1: float | None
    q3: float | None
    interquartile_range: float | None
    minimum_improvement: float | None
    maximum_improvement: float | None
    zero_difference_count: int
    positive_difference_count: int
    negative_difference_count: int
    direction: str | None
    quantile_convention: str
    session_count: int
    rig_count: int
    multi_site_claim_supported: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class EffectSize:
    """Native-unit and standardized paired effect, with explicit refusals."""

    outcome_id: str
    unit: str
    evidence_label: str
    pair_count: int
    mean_y_a: float | None
    mean_y_b: float | None
    mean_improvement: float | None
    sd_improvement: float | None
    direction: str | None
    standardized_dz: float | None
    standardized_status: str
    relative_improvement: float | None
    relative_status: str
    denominator_floor: float | None
    notes: tuple[str, ...]


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise W22StatisticsError(
            REASON_EMPTY_IDENTITY, f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_finite(value: object, field: str) -> float:
    if value is None:
        raise W22StatisticsError(REASON_MISSING_OUTCOME, f"{field} is missing")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise W22StatisticsError(
            REASON_NON_NUMERIC_OUTCOME,
            f"{field} must be a real number, got {value!r}",
        )
    number = float(value)
    if not math.isfinite(number):
        raise W22StatisticsError(
            REASON_NON_FINITE_OUTCOME, f"{field} must be finite, got {value!r}"
        )
    return number


def _validate_arm(arm: PairArm, expected_controller: str, unit: str) -> None:
    _require_text(arm.run_id, "run_id")
    _require_text(arm.unit, "arm unit")
    if arm.controller != expected_controller:
        raise W22StatisticsError(
            REASON_ARM_CONTROLLER,
            f"expected Controller {expected_controller}, got {arm.controller!r}",
        )
    if arm.unit != unit:
        raise W22StatisticsError(
            REASON_UNIT_MISMATCH,
            f"arm unit {arm.unit!r} does not match dataset unit {unit!r}",
        )
    _require_finite(arm.value, f"run {arm.run_id} outcome")


def build_paired_dataset(
    records: Iterable[PairRecord],
    *,
    outcome_id: str,
    unit: str,
    outcome_role: str = OUTCOME_ROLE_PRIMARY,
    excluded: Iterable[ExcludedPair] | None = None,
    evidence_label: str = LABEL_SYNTHETIC_TEST_ONLY,
) -> PairedDataset:
    """Validate and canonically order toy paired observations.

    Any structural or numeric violation raises: a suspicious pair is never
    silently dropped, coerced to zero, or admitted with a repaired identity.
    """
    if evidence_label != LABEL_SYNTHETIC_TEST_ONLY:
        raise W22BoundaryError(
            REASON_EVIDENCE_LABEL,
            "W22 accepts only SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY; real "
            "physical-outcome admission requires the future authorized "
            "W20-gated bridge",
        )
    outcome_id = _require_text(outcome_id, "outcome_id")
    unit = _require_text(unit, "unit")
    if unit not in SUPPORTED_UNITS:
        raise W22StatisticsError(
            REASON_UNIT_MISMATCH,
            f"unit {unit!r} is not in the frozen native-unit vocabulary",
        )
    if outcome_role not in OUTCOME_ROLES:
        raise W22StatisticsError(
            REASON_ROLE_MISMATCH, f"unknown outcome role {outcome_role!r}"
        )

    admitted: list[PairRecord] = []
    pair_ids: set[str] = set()
    block_ids: set[str] = set()
    run_ids: set[str] = set()
    for record in records:
        pair_id = _require_text(record.pair_id, "pair_id")
        block_id = _require_text(record.pair_block_id, "pair_block_id")
        if pair_id in pair_ids:
            raise W22StatisticsError(
                REASON_DUPLICATE_PAIR_ID, f"pair_id {pair_id!r} repeated"
            )
        if block_id in block_ids:
            raise W22StatisticsError(
                REASON_DUPLICATE_PAIR_BLOCK,
                f"pair block {block_id!r} already contributed a pair; a rerun "
                "must not become an additional independent pair",
            )
        if record.outcome_id != outcome_id:
            raise W22StatisticsError(
                REASON_OUTCOME_MISMATCH,
                f"pair {pair_id!r} outcome {record.outcome_id!r} != {outcome_id!r}",
            )
        if record.outcome_role != outcome_role:
            raise W22StatisticsError(
                REASON_ROLE_MISMATCH,
                f"pair {pair_id!r} role {record.outcome_role!r} != {outcome_role!r}",
            )
        _validate_arm(record.arm_a, CONTROLLER_A, unit)
        _validate_arm(record.arm_b, CONTROLLER_B, unit)
        arm_run_ids = (record.arm_a.run_id.strip(), record.arm_b.run_id.strip())
        if arm_run_ids[0] == arm_run_ids[1]:
            raise W22StatisticsError(
                REASON_SAME_RUN_BOTH_ARMS,
                f"pair {pair_id!r} uses run {arm_run_ids[0]!r} on both arms",
            )
        for run_id in arm_run_ids:
            if run_id in run_ids:
                raise W22StatisticsError(
                    REASON_DUPLICATE_RUN_ID,
                    f"run {run_id!r} is reused across pairs; telemetry rows, "
                    "windows and reruns are not independent pairs",
                )
            run_ids.add(run_id)
        if record.session_id is not None:
            _require_text(record.session_id, "session_id")
        if record.rig_id is not None:
            _require_text(record.rig_id, "rig_id")
        pair_ids.add(pair_id)
        block_ids.add(block_id)
        admitted.append(record)

    excluded_list: list[ExcludedPair] = []
    excluded_ids: set[str] = set()
    for item in excluded or ():
        pair_id = _require_text(item.pair_id, "excluded pair_id")
        reason = _require_text(item.reason_code, "excluded reason_code")
        if pair_id in pair_ids:
            raise W22StatisticsError(
                REASON_EXCLUDED_OVERLAP,
                f"pair {pair_id!r} is both admitted and excluded",
            )
        if pair_id in excluded_ids:
            raise W22StatisticsError(
                REASON_DUPLICATE_PAIR_ID, f"excluded pair {pair_id!r} repeated"
            )
        excluded_ids.add(pair_id)
        excluded_list.append(ExcludedPair(pair_id, reason))

    admitted.sort(key=lambda pair: pair.pair_id)
    excluded_list.sort(key=lambda pair: pair.pair_id)
    if not admitted:
        raise W22StatisticsError(
            REASON_EMPTY_IDENTITY,
            "a paired dataset must contain at least one admitted valid pair",
        )
    return PairedDataset(
        outcome_id=outcome_id,
        unit=unit,
        outcome_role=outcome_role,
        pairs=tuple(admitted),
        excluded_pairs=tuple(excluded_list),
        evidence_label=evidence_label,
    )


def quantile_type7(sorted_values: Sequence[float], probability: float) -> float:
    """Hyndman-Fan type-7 quantile (linear interpolation of order statistics)."""
    if not sorted_values:
        raise W22StatisticsError(
            REASON_EMPTY_IDENTITY, "quantile requires at least one value"
        )
    if not 0.0 <= probability <= 1.0:
        raise W22StatisticsError(
            REASON_NON_FINITE_OUTCOME, "probability must lie in [0, 1]"
        )
    values = sorted(float(value) for value in sorted_values)
    position = (len(values) - 1) * probability
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    fraction = position - lower_index
    return values[lower_index] + (values[upper_index] - values[lower_index]) * fraction


def _median(sorted_values: Sequence[float]) -> float:
    count = len(sorted_values)
    middle = count // 2
    if count % 2 == 1:
        return float(sorted_values[middle])
    return (float(sorted_values[middle - 1]) + float(sorted_values[middle])) / 2.0


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def describe_pairs(dataset: PairedDataset) -> PairedDescriptive:
    """Compute the B-W22-01 pair-level descriptive statistics."""
    improvements = list(dataset.improvements)
    ordered = sorted(improvements)
    count = len(ordered)
    mean_value = _mean(improvements)
    median_value = _median(ordered)
    sample_sd: float | None = None
    population_sd: float | None = None
    if count >= 2:
        deviations = math.fsum((value - mean_value) ** 2 for value in improvements)
        sample_sd = math.sqrt(deviations / (count - 1))
        population_sd = math.sqrt(deviations / count)
    q1 = quantile_type7(ordered, 0.25)
    q3 = quantile_type7(ordered, 0.75)
    notes: list[str] = []
    if count == 1:
        notes.append("ONE_PAIR_DESCRIPTIVE_ONLY_NO_DISPERSION")
    if sample_sd == 0.0:
        notes.append("CONSTANT_PAIRED_DIFFERENCES_ZERO_DISPERSION")
    if count < MIN_PAIRS_FOR_INFERENCE:
        notes.append("N_BELOW_INFERENTIAL_MINIMUM")
    positive = sum(1 for value in improvements if value > 0)
    negative = sum(1 for value in improvements if value < 0)
    zero = count - positive - negative
    if mean_value > 0:
        direction = DIRECTION_IMPROVED
    elif mean_value < 0:
        direction = DIRECTION_WORSENED
    else:
        direction = DIRECTION_NO_DIFFERENCE
    rig_ids = dataset.rig_ids
    if not rig_ids:
        notes.append("RIG_IDENTITY_NOT_DECLARED")
    elif len(rig_ids) > 1:
        notes.append("MULTIPLE_RIG_IDS_DECLARED_NOT_INDEPENDENT_SITES")
    return PairedDescriptive(
        outcome_id=dataset.outcome_id,
        unit=dataset.unit,
        outcome_role=dataset.outcome_role,
        sign_convention=SIGN_CONVENTION,
        evidence_label=dataset.evidence_label,
        pair_count=count,
        excluded_pair_count=len(dataset.excluded_pairs),
        excluded_reasons=tuple(
            (pair.pair_id, pair.reason_code) for pair in dataset.excluded_pairs
        ),
        pair_ids=dataset.pair_ids,
        y_a=dataset.y_a,
        y_b=dataset.y_b,
        improvements=dataset.improvements,
        mean_improvement=mean_value,
        median_improvement=median_value,
        sample_standard_deviation=sample_sd,
        population_standard_deviation=population_sd,
        q1=q1,
        q3=q3,
        interquartile_range=q3 - q1,
        minimum_improvement=ordered[0],
        maximum_improvement=ordered[-1],
        zero_difference_count=zero,
        positive_difference_count=positive,
        negative_difference_count=negative,
        direction=direction,
        quantile_convention=QUANTILE_CONVENTION,
        session_count=len(dataset.session_ids),
        rig_count=len(rig_ids),
        multi_site_claim_supported=False,
        notes=tuple(notes),
    )


def paired_effect_size(
    dataset: PairedDataset,
    *,
    denominator_floor: float | None = None,
) -> EffectSize:
    """Compute B-W22-04 native-unit and standardized paired effects.

    ``denominator_floor`` is the predeclared minimum meaningful reference
    value in native units (Doc 03 section 73).  Without it no relative
    reduction is produced; a zero or near-zero denominator never yields an
    infinite or misleading percentage.
    """
    descriptive = describe_pairs(dataset)
    notes: list[str] = []
    if denominator_floor is not None:
        denominator_floor = _require_finite(
            denominator_floor, "denominator_floor"
        )
        if denominator_floor <= 0:
            raise W22StatisticsError(
                RELATIVE_UNDEFINED_FLOOR,
                "denominator_floor must be positive when declared",
            )

    mean_sd = descriptive.sample_standard_deviation
    if descriptive.pair_count < 2:
        standardized = None
        standardized_status = DZ_UNDEFINED_INSUFFICIENT_N
    elif mean_sd is None or mean_sd == 0.0:
        standardized = None
        standardized_status = DZ_UNDEFINED_ZERO_SD
        notes.append("ZERO_SD_EFFECT_NOT_INFINITE")
    else:
        standardized = descriptive.mean_improvement / mean_sd
        standardized_status = DZ_DEFINED
        if descriptive.pair_count < 5:
            notes.append("DZ_UNSTABLE_SMALL_N")

    mean_b = _mean(dataset.y_b)
    mean_a = _mean(dataset.y_a)
    relative: float | None = None
    if denominator_floor is None:
        relative_status = RELATIVE_UNDEFINED_NO_FLOOR
    elif mean_a <= 0:
        relative_status = RELATIVE_UNDEFINED_NON_POSITIVE
    elif mean_a <= denominator_floor:
        relative_status = RELATIVE_UNDEFINED_FLOOR
    else:
        relative = 1.0 - mean_b / mean_a
        relative_status = RELATIVE_DEFINED

    if descriptive.negative_difference_count and descriptive.positive_difference_count:
        notes.append("MIXED_SIGN_PAIRED_DIFFERENCES")

    return EffectSize(
        outcome_id=dataset.outcome_id,
        unit=dataset.unit,
        evidence_label=dataset.evidence_label,
        pair_count=descriptive.pair_count,
        mean_y_a=mean_a,
        mean_y_b=mean_b,
        mean_improvement=descriptive.mean_improvement,
        sd_improvement=mean_sd,
        direction=descriptive.direction,
        standardized_dz=standardized,
        standardized_status=standardized_status,
        relative_improvement=relative,
        relative_status=relative_status,
        denominator_floor=denominator_floor,
        notes=tuple(notes),
    )


def _format_number(value: float, places: int = 4) -> str:
    text = f"{value:.{places}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_every_pair_svg(
    dataset: PairedDataset,
    *,
    title: str = "Toy paired fixture",
    width: int = 760,
    height: int | None = None,
) -> str:
    """Render a deterministic every-pair slope plot as an SVG string.

    Every admitted pair is drawn once; no averaging or pair selection.
    The chart permanently carries the ``TEST_ONLY`` banner, so a synthetic
    figure cannot be mistaken for a final ColdGuard physical result.
    """
    descriptive = describe_pairs(dataset)
    count = descriptive.pair_count
    label_column = 150
    plot_left = label_column + 20
    plot_right = width - 40
    top = 86
    row_height = 30
    height = height or top + count * row_height + 96
    values = [*dataset.y_a, *dataset.y_b]
    low = min(values)
    high = max(values)
    if high == low:
        high = low + 1.0
        low = low - 1.0
    padding = (high - low) * 0.08
    low -= padding
    high += padding

    def y_for(value: float) -> float:
        return top + (high - value) / (high - low) * (count * row_height + 24)

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img">'
    )
    parts.append(
        f"<title>TEST_ONLY · {_escape(title)}</title>"
        f"<desc>{_escape(TEST_ONLY_BANNER)}</desc>"
    )
    parts.append(
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>'
    )
    parts.append(
        f'<rect x="8" y="8" width="{width - 16}" height="30" rx="4" '
        'fill="#fff8c5" stroke="#d4a72c"/>'
    )
    parts.append(
        f'<text x="18" y="28" font-family="sans-serif" font-size="13" '
        f'font-weight="700" fill="#7d4e00">TEST_ONLY · '
        f"{_escape(TEST_ONLY_BANNER)}</text>"
    )
    role_label = (
        "PRIMARY OUTCOME"
        if dataset.outcome_role == OUTCOME_ROLE_PRIMARY
        else "SECONDARY / EXPLORATORY OUTCOME"
    )
    parts.append(
        f'<text x="18" y="60" font-family="sans-serif" font-size="14" '
        f'font-weight="700" fill="#24292f">{_escape(title)} — '
        f"{_escape(dataset.outcome_id)} [{_escape(dataset.unit)}] · "
        f"{role_label}</text>"
    )
    parts.append(
        f'<text x="18" y="78" font-family="sans-serif" font-size="11" '
        f'fill="#57606a">n = {count} accepted pairs · sign convention '
        f"I_i = Y_A − Y_B · positive = Controller B improved</text>"
    )
    axis_x = plot_right
    parts.append(
        f'<line x1="{axis_x}" y1="{top}" x2="{axis_x}" '
        f'y2="{top + count * row_height + 24}" stroke="#d0d7de"/>'
    )
    for row_index, (pair, improvement) in enumerate(
        zip(dataset.pairs, dataset.improvements)
    ):
        y = top + row_index * row_height + row_height / 2
        if improvement > 0:
            color = "#1a7f37"
            outcome = "improved"
        elif improvement < 0:
            color = "#cf222e"
            outcome = "worsened"
        else:
            color = "#57606a"
            outcome = "no difference"
        y_a = y_for(pair.arm_a.value)
        y_b = y_for(pair.arm_b.value)
        parts.append(
            f'<g id="pair-{_escape(pair.pair_id)}">'
            f"<title>{_escape(pair.pair_id)}: A={_format_number(pair.arm_a.value)} → "
            f"B={_format_number(pair.arm_b.value)} {_escape(dataset.unit)}; "
            f"I={_format_number(improvement)} ({outcome})</title>"
        )
        parts.append(
            f'<text x="12" y="{y + 4}" font-family="monospace" font-size="10" '
            f'fill="#24292f">{_escape(pair.pair_id)} '
            f"({_escape(pair.arm_a.run_id)}/{_escape(pair.arm_b.run_id)})</text>"
        )
        parts.append(
            f'<line x1="{plot_left}" y1="{y_a:.2f}" x2="{plot_right}" '
            f'y2="{y_b:.2f}" stroke="{color}" stroke-width="1.6"/>'
        )
        parts.append(
            f'<circle cx="{plot_left}" cy="{y_a:.2f}" r="4" fill="#0969da" '
            'stroke="#ffffff"/>'
        )
        parts.append(
            f'<rect x="{plot_right - 4}" y="{y_b - 4:.2f}" width="8" '
            f'height="8" fill="{color}" stroke="#ffffff"/>'
        )
        parts.append("</g>")
    legend_y = top + count * row_height + 52
    parts.append(
        f'<circle cx="{plot_left}" cy="{legend_y}" r="4" fill="#0969da"/>'
        f'<text x="{plot_left + 10}" y="{legend_y + 4}" font-family="sans-serif" '
        f'font-size="11" fill="#24292f">Controller A outcome (circle)</text>'
    )
    parts.append(
        f'<rect x="{plot_left + 190}" y="{legend_y - 4}" width="8" height="8" '
        f'fill="#1a7f37"/><text x="{plot_left + 204}" y="{legend_y + 4}" '
        f'font-family="sans-serif" font-size="11" fill="#24292f">'
        "Controller B outcome (square)</text>"
    )
    legend2 = legend_y + 18
    parts.append(
        f'<text x="{plot_left}" y="{legend2}" font-family="sans-serif" '
        f'font-size="11" fill="#1a7f37">green: B improved</text>'
        f'<text x="{plot_left + 130}" y="{legend2}" font-family="sans-serif" '
        f'font-size="11" fill="#cf222e">red: B worsened</text>'
        f'<text x="{plot_left + 260}" y="{legend2}" font-family="sans-serif" '
        f'font-size="11" fill="#57606a">grey: no difference</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
