"""Deterministic W10 feature-audit plots.

The plots are hand-rendered SVG so the repository needs no plotting runtime and
the bytes are reproducible. A synthetic panel shows past feature support versus
the future label horizon; the real diagnostic panel shows only the measured
trace, with no invented S2 anchor and no fabricated door opening.
"""

from __future__ import annotations

from typing import Any, Sequence

from .feature_pipeline import (
    PRESENT,
    SOURCE_TYPE_SYNTHETIC,
    FeatureRow,
    Trajectory,
)
from .feature_registry import FeatureRegistry

_COLOURS = {
    "center": "#1f4e79",
    "bottom": "#2e7d32",
    "near": "#c0504d",
    "hot": "#8064a2",
    "rolling": "#1f4e79",
    "door": "#2e7d32",
    "since": "#c0504d",
    "duration": "#1f4e79",
    "applied": "#2e7d32",
    "duty": "#8064a2",
    "power": "#c0504d",
}


def _polyline(
    points: Sequence[tuple[float, float]],
    *,
    colour: str,
    width: float = 1.5,
    dash: str | None = None,
) -> str:
    if not points:
        return ""
    coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline fill="none" stroke="{colour}" stroke-width="{width}"'
        f'{dash_attr} points="{coords}" />'
    )


def _text(x: float, y: float, value: str, *, size: int = 10, anchor: str = "start", colour: str = "#333333") -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="monospace" '
        f'font-size="{size}" text-anchor="{anchor}" fill="{colour}">'
        f"{_escape(value)}</text>"
    )


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _index(registry: FeatureRegistry) -> dict[str, int]:
    return {feature.feature_id: index for index, feature in enumerate(registry.features)}


def _series(
    rows: Sequence[FeatureRow], index: dict[str, int], feature_id: str
) -> list[tuple[float, float | int | None]]:
    position = index[feature_id]
    return [(row.anchor_t_s, row.values[position]) for row in rows]


def _panel(
    *,
    top: float,
    height: float,
    left: float,
    width: float,
    title: str,
    min_t: float,
    max_t: float,
    min_y: float,
    max_y: float,
    y_ticks: Sequence[float] = (),
    x_ticks: Sequence[float] = (),
) -> tuple[list[str], Any, Any]:
    lines = [
        _text(left, top - 6, title, size=11),
        f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="#fafafa" stroke="#cccccc"/>',
    ]
    if max_t == min_t:
        max_t = min_t + 1.0
    if max_y == min_y:
        min_y -= 0.5
        max_y += 0.5

    def x_of(t: float) -> float:
        return left + (t - min_t) / (max_t - min_t) * width

    def y_of(value: float) -> float:
        return top + (max_y - value) / (max_y - min_y) * height

    for value in y_ticks:
        y = y_of(value)
        lines.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{left + width}" y2="{y:.2f}" stroke="#e8e8e8"/>'
        )
        lines.append(_text(left - 6, y + 3, f"{value:g}", size=9, anchor="end"))
    for value in x_ticks:
        x = x_of(value)
        lines.append(
            f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + height}" stroke="#f0f0f0"/>'
        )
        lines.append(_text(x, top + height + 12, f"{value:g}s", size=9, anchor="middle"))
    return lines, x_of, y_of


def _breaks(
    series: Sequence[tuple[float, float | int | None]],
) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for time_s, value in series:
        if value is None:
            if current:
                segments.append(current)
                current = []
            continue
        current.append((time_s, float(value)))
    if current:
        segments.append(current)
    return segments


def _shade_spans(
    x_of: Any,
    spans: Sequence[tuple[float, float]],
    *,
    top: float,
    height: float,
    colour: str,
    opacity: float,
) -> list[str]:
    lines = []
    for start, end in spans:
        x1, x2 = x_of(start), x_of(end)
        if x2 < x1:
            x1, x2 = x2, x1
        lines.append(
            f'<rect x="{x1:.2f}" y="{top}" width="{max(x2 - x1, 1.0):.2f}" '
            f'height="{height}" fill="{colour}" opacity="{opacity}"/>'
        )
    return lines


def _feature_spans(
    trajectory: Trajectory,
    rows: Sequence[FeatureRow],
    predicate,
) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    start: float | None = None
    previous: float | None = None
    for row, sample in zip(rows, trajectory.samples):
        if predicate(row, sample):
            if start is None:
                start = row.anchor_t_s
            previous = row.anchor_t_s
        elif start is not None:
            spans.append((start, previous or start))
            start = None
    if start is not None:
        spans.append((start, previous or start))
    return spans


def render_synthetic_audit(
    trajectory: Trajectory,
    rows: Sequence[FeatureRow],
    registry: FeatureRegistry,
    *,
    anchor_s: float = 60.0,
    horizons_s: Sequence[float] = (30.0, 60.0, 120.0),
    title: str = "W10 synthetic S2 feature audit",
) -> str:
    if not rows:
        raise ValueError("feature audit requires at least one feature row")
    index = _index(registry)
    min_t = rows[0].anchor_t_s
    max_t = rows[-1].anchor_t_s
    width, left, right = 1180.0, 72.0, 24.0
    plot_width = width - left - right
    x_ticks = [value for value in range(int(min_t), int(max_t) + 1, 20)]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="1010">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        _text(left, 24, title, size=15),
        _text(
            left,
            40,
            "SOFTWARE-ONLY SYNTHETIC CONTROL — not physical evidence; "
            "past = feature support, future = label construction only",
            size=10,
            colour="#8a1c1c",
        ),
    ]

    # 1. chamber temperatures + hot side
    top = 70.0
    height = 150.0
    thermal_values = [
        value
        for feature_id in ("T_center_c", "T_bottom_c", "T_near_door_c", "T_tec_hot_side_c")
        for _, value in _series(rows, index, feature_id)
        if value is not None
    ]
    min_y, max_y = min(thermal_values), max(thermal_values)
    padding = (max_y - min_y) * 0.1 or 0.5
    frame, x_of, y_of = _panel(
        top=top,
        height=height,
        left=left,
        width=plot_width,
        title="Chamber air (center / bottom / near-door); TEC hot side separate (dashed)",
        min_t=min_t,
        max_t=max_t,
        min_y=min_y - padding,
        max_y=max_y + padding,
        y_ticks=[min_y, (min_y + max_y) / 2, max_y],
        x_ticks=x_ticks,
    )
    lines.extend(frame)
    lines.extend(
        _shade_spans(
            x_of,
            _feature_spans(trajectory, rows, lambda row, sample: sample.thermal_quality != "VALID"),
            top=top,
            height=height,
            colour="#999999",
            opacity=0.25,
        )
    )
    for feature_id, key, dash in (
        ("T_center_c", "center", None),
        ("T_bottom_c", "bottom", None),
        ("T_near_door_c", "near", None),
        ("T_tec_hot_side_c", "hot", "5,3"),
    ):
        for segment in _breaks(_series(rows, index, feature_id)):
            lines.append(
                _polyline(
                    [(x_of(t), y_of(v)) for t, v in segment],
                    colour=_COLOURS[key],
                    dash=dash,
                )
            )
    lines.append(_text(left + plot_width - 4, top + 12, "grey: thermal quality not VALID", size=9, anchor="end"))

    # 2. rolling thermal
    top += height + 46
    rolling = _series(rows, index, "rolling_mean_temperature_60s")
    rolling_values = [value for _, value in rolling if value is not None]
    if rolling_values:
        min_r, max_r = min(rolling_values), max(rolling_values)
    else:
        min_r, max_r = 0.0, 1.0
    pad_r = (max_r - min_r) * 0.15 or 0.5
    frame, x_of, y_of = _panel(
        top=top,
        height=height,
        left=left,
        width=plot_width,
        title="Rolling chamber mean 60 s (time-weighted, actual event time)",
        min_t=min_t,
        max_t=max_t,
        min_y=min_r - pad_r,
        max_y=max_r + pad_r,
        y_ticks=[min_r, (min_r + max_r) / 2, max_r],
        x_ticks=x_ticks,
    )
    lines.extend(frame)
    for segment in _breaks(rolling):
        lines.append(
            _polyline(
                [(x_of(t), y_of(v)) for t, v in segment],
                colour=_COLOURS["rolling"],
                width=1.8,
            )
        )
    lines.append(
        _text(
            left + plot_width - 4,
            top + 12,
            "missing before 60 s history; gaps and low quality stay missing",
            size=9,
            anchor="end",
        )
    )

    # 3. door state
    top += height + 46
    frame, x_of, y_of = _panel(
        top=top,
        height=height,
        left=left,
        width=plot_width,
        title="Door state: 1 OPEN, 0 CLOSED, line break = UNKNOWN/untrusted",
        min_t=min_t,
        max_t=max_t,
        min_y=-0.2,
        max_y=1.2,
        y_ticks=[0.0, 1.0],
        x_ticks=x_ticks,
    )
    lines.extend(frame)
    lines.extend(
        _shade_spans(
            x_of,
            _feature_spans(trajectory, rows, lambda row, sample: sample.door_state == "UNKNOWN"),
            top=top,
            height=height,
            colour="#999999",
            opacity=0.3,
        )
    )
    door_series = _series(rows, index, "door_open")
    for segment in _breaks(door_series):
        lines.append(
            _polyline(
                [(x_of(t), y_of(v)) for t, v in segment],
                colour=_COLOURS["door"],
                width=1.8,
            )
        )
    for transition in _door_transitions(trajectory):
        x = x_of(transition)
        lines.append(
            f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + height}" '
            'stroke="#c0504d" stroke-dasharray="4,3"/>'
        )
        lines.append(_text(x + 3, top + 12, "door OPEN", size=9, colour="#c0504d"))

    # 4. door timing
    top += height + 46
    timing = [
        value
        for feature_id in ("time_since_open", "duration_so_far")
        for _, value in _series(rows, index, feature_id)
        if value is not None
    ]
    max_time = max(timing) if timing else 1.0
    frame, x_of, y_of = _panel(
        top=top,
        height=height,
        left=left,
        width=plot_width,
        title="Door timing: time_since_open (red), duration_so_far (blue)",
        min_t=min_t,
        max_t=max_t,
        min_y=0.0,
        max_y=max(max_time * 1.15, 1.0),
        y_ticks=[0.0, max_time / 2, max_time],
        x_ticks=x_ticks,
    )
    lines.extend(frame)
    for feature_id, key in (
        ("time_since_open", "since"),
        ("duration_so_far", "duration"),
    ):
        for segment in _breaks(_series(rows, index, feature_id)):
            lines.append(
                _polyline(
                    [(x_of(t), y_of(v)) for t, v in segment],
                    colour=_COLOURS[key],
                    width=1.6,
                )
            )

    # 5. applied cooling and duty
    top += height + 46
    frame, x_of, y_of = _panel(
        top=top,
        height=height,
        left=left,
        width=plot_width,
        title="Applied cooling state (green, 0/1) and applied duty (purple, 0..1)",
        min_t=min_t,
        max_t=max_t,
        min_y=-0.2,
        max_y=1.2,
        y_ticks=[0.0, 0.5, 1.0],
        x_ticks=x_ticks,
    )
    lines.extend(frame)
    for feature_id, key in (("applied_cooling", "applied"), ("applied_duty", "duty")):
        for segment in _breaks(_series(rows, index, feature_id)):
            lines.append(
                _polyline(
                    [(x_of(t), y_of(v)) for t, v in segment],
                    colour=_COLOURS[key],
                    width=1.5,
                )
            )
    lines.append(
        _text(
            left + plot_width - 4,
            top + 12,
            "requested / applied / readback are distinct; an ACK is not electrical proof",
            size=9,
            anchor="end",
        )
    )

    # 6. qualified power
    top += height + 46
    power_series = _series(rows, index, "cooling_power_w")
    power_values = [value for _, value in power_series if value is not None]
    max_power = max(power_values) if power_values else 1.0
    frame, x_of, y_of = _panel(
        top=top,
        height=height,
        left=left,
        width=plot_width,
        title="Cooling-branch power where electrical quality is VALID (missing is not zero)",
        min_t=min_t,
        max_t=max_t,
        min_y=0.0,
        max_y=max(max_power * 1.15, 1.0),
        y_ticks=[0.0, max_power / 2, max_power],
        x_ticks=x_ticks,
    )
    lines.extend(frame)
    lines.extend(
        _shade_spans(
            x_of,
            _feature_spans(
                trajectory, rows, lambda row, sample: sample.electrical_quality != "VALID"
            ),
            top=top,
            height=height,
            colour="#c0504d",
            opacity=0.12,
        )
    )
    for segment in _breaks(power_series):
        lines.append(
            _polyline(
                [(x_of(t), y_of(v)) for t, v in segment],
                colour=_COLOURS["power"],
                width=1.6,
            )
        )

    # 7. label horizons around the anchor
    top += height + 60
    lower = anchor_s - 60.0
    upper = anchor_s + max(horizons_s)
    frame, x_of, y_of = _panel(
        top=top,
        height=140.0,
        left=left,
        width=plot_width,
        title=f"Past-only support (t-60 s, t] versus candidate label horizons at t={anchor_s:g} s",
        min_t=max(min_t, lower - 5),
        max_t=min(max_t, upper + 5),
        min_y=min_r - pad_r,
        max_y=max_r + pad_r,
        y_ticks=[min_r, max_r],
        x_ticks=[],
    )
    lines.extend(frame)
    anchor_x = x_of(anchor_s)
    lines.append(
        f'<rect x="{x_of(max(min_t, lower)):.2f}" y="{top}" width="{max(anchor_x - x_of(max(min_t, lower)), 1.0):.2f}" '
        f'height="140" fill="#1f4e79" opacity="0.12"/>'
    )
    lines.append(_text(x_of(max(min_t, lower)) + 4, top + 14, "feature support (past only)", size=9, colour="#1f4e79"))
    colours = ("#c0504d", "#8064a2", "#2e7d32")
    for offset, horizon in enumerate(horizons_s):
        x1 = anchor_x
        x2 = x_of(min(anchor_s + horizon, max_t))
        lines.append(
            f'<rect x="{x1:.2f}" y="{top}" width="{max(x2 - x1, 1.0):.2f}" '
            f'height="140" fill="{colours[offset % len(colours)]}" opacity="0.08"/>'
        )
        lines.append(
            _text(
                x1 + 3,
                top + 28 + 13 * offset,
                f"H={horizon:g}s (future label only)",
                size=9,
                colour=colours[offset % len(colours)],
            )
        )
    lines.append(
        f'<line x1="{anchor_x:.2f}" y1="{top}" x2="{anchor_x:.2f}" y2="{top + 140}" '
        'stroke="#000000" stroke-width="1.2" stroke-dasharray="4,3"/>'
    )
    lines.append(_text(anchor_x + 3, top + 140 - 4, "anchor t", size=9))
    for segment in _breaks(rolling):
        lines.append(
            _polyline(
                [(x_of(t), y_of(v)) for t, v in segment if t <= anchor_s],
                colour="#1f4e79",
                width=1.8,
            )
        )
    for segment in _breaks(rolling):
        lines.append(
            _polyline(
                [(x_of(t), y_of(v)) for t, v in segment if t >= anchor_s],
                colour="#1f4e79",
                width=1.2,
                dash="4,3",
            )
        )
    lines.append(
        _text(
            left + plot_width - 4,
            top + 136,
            "future observations are shown only to construct labels; they are never feature inputs",
            size=9,
            anchor="end",
            colour="#8a1c1c",
        )
    )

    # 8. feature availability strip
    top += 160.0
    height = 60.0
    lines.append(_text(left, top - 6, "Feature availability per anchor (features produced / registered)", size=11))
    lines.append(
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{height}" fill="#fafafa" stroke="#cccccc"/>'
    )
    total = len(registry.features)
    bar_width = max(plot_width / max(len(rows), 1) * 0.8, 1.0)
    for row in rows:
        produced = sum(1 for reason in row.missing_reasons if reason == PRESENT)
        x = left + (row.anchor_t_s - rows[0].anchor_t_s) / max(rows[-1].anchor_t_s - rows[0].anchor_t_s, 1.0) * plot_width
        bar_height = height * produced / total
        lines.append(
            f'<rect x="{x:.2f}" y="{top + height - bar_height:.2f}" width="{bar_width:.2f}" '
            f'height="{bar_height:.2f}" fill="#2e7d32" opacity="0.55"/>'
        )
    lines.append(_text(left + 4, top + height + 12, "0", size=9))
    lines.append(_text(left + 4, top + 10, f"{total}", size=9))
    lines.extend(["</svg>", ""])
    return "\n".join(lines)


def _door_transitions(trajectory: Trajectory) -> list[float]:
    transitions: list[float] = []
    previous = None
    for sample in trajectory.samples:
        trusted = (
            sample.door_state in ("OPEN", "CLOSED")
            and sample.door_quality == "VALID"
            and sample.door_polarity_attested
        )
        state = sample.door_state if trusted else None
        if state == "OPEN" and previous == "CLOSED":
            transitions.append(sample.time_s)
        if state is not None:
            previous = state
        else:
            previous = None
    return transitions


def render_real_diagnostic(
    trajectory: Trajectory,
    rows: Sequence[FeatureRow],
    registry: FeatureRegistry,
) -> str:
    if trajectory.source_type == SOURCE_TYPE_SYNTHETIC:
        raise ValueError("real diagnostic plot refuses synthetic trajectories")
    index = _index(registry)
    if not rows:
        raise ValueError("real diagnostic plot requires feature rows")
    width, height = 1180, 470
    left, right, top, bottom = 72.0, 24.0, 62.0, 92.0
    plot_width = width - left - right
    plot_height = height - top - bottom
    min_t = rows[0].anchor_t_s
    max_t = rows[-1].anchor_t_s
    values = [
        value
        for feature_id in ("T_center_c", "T_bottom_c", "T_near_door_c", "T_tec_hot_side_c")
        for _, value in _series(rows, index, feature_id)
        if value is not None
    ]
    if not values:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            '<text x="20" y="40" font-family="monospace">'
            "W10 real diagnostic: no evaluable thermal trajectory</text></svg>\n"
        )
    min_v, max_v = min(values), max(values)
    pad = (max_v - min_v) * 0.1 or 0.5
    min_v -= pad
    max_v += pad

    def x_of(t: float) -> float:
        return left + (t - min_t) / max(max_t - min_t, 1.0) * plot_width

    def y_of(value: float) -> float:
        return top + (max_v - value) / (max_v - min_v) * plot_height

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        _text(left, 24, "W10 real A W09 diagnostic feature view — NOT eligible S2 evidence", size=15),
        _text(
            left,
            42,
            "boot-scoped uptime clock; run identity unresolved; electrical UNKNOWN; "
            "door polarity unconfirmed; no S2 anchor, no invented door opening",
            size=10,
            colour="#8a1c1c",
        ),
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#fafafa" stroke="#999999"/>',
    ]
    for index_tick in range(6):
        value = min_v + (max_v - min_v) * index_tick / 5
        y = y_of(value)
        lines.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="#e8e8e8"/>'
        )
        lines.append(_text(left - 6, y + 3, f"{value:.1f}", size=9, anchor="end"))
    for value in range(int(min_t), int(max_t) + 1, 120):
        x = x_of(value)
        lines.append(_text(x, top + plot_height + 14, f"{value}s", size=9, anchor="middle"))
    for feature_id, colour, dash in (
        ("T_center_c", _COLOURS["center"], None),
        ("T_bottom_c", _COLOURS["bottom"], None),
        ("T_near_door_c", _COLOURS["near"], None),
        ("T_tec_hot_side_c", _COLOURS["hot"], "6,3"),
    ):
        for segment in _breaks(_series(rows, index, feature_id)):
            lines.append(
                _polyline(
                    [(x_of(t), y_of(v)) for t, v in segment],
                    colour=colour,
                    width=1.5,
                    dash=dash,
                )
            )
    door_spans = _feature_spans(
        trajectory, rows, lambda row, sample: sample.door_state == "UNKNOWN"
    )
    for start, end in door_spans:
        x1, x2 = x_of(start), x_of(end)
        lines.append(
            f'<rect x="{x1:.2f}" y="{top}" width="{max(x2 - x1, 1.0):.2f}" '
            f'height="{plot_height}" fill="#999999" opacity="0.2"/>'
        )
    lines.extend(
        [
            _text(left, height - 46, "solid: chamber air (center/bottom/near-door); dashed: TEC hot side (separate)", size=10),
            _text(left, height - 30, "door state: CLOSED/UNKNOWN samples only; 0 openings observed; door features missing", size=10),
            _text(left, height - 14, "electrical features missing because PZEM quality is UNKNOWN; absent is not zero", size=10),
            "</svg>",
            "",
        ]
    )
    return "\n".join(lines)
