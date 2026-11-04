"""Dependency-free live charts drawn on a Tk canvas."""

from __future__ import annotations

import collections
import tkinter as tk
from typing import Callable

from .protocol import TelemetryFrame

TEMP_COLORS = {"T1": "#1f77b4", "T2": "#d62728", "T3": "#2ca02c", "SPARE": "#9467bd"}
CURRENT_COLOR = "#ff7f0e"


class LiveChart(tk.Canvas):
    def __init__(self, master: tk.Misc, width: int = 760, height: int = 320):
        super().__init__(master, width=width, height=height, background="#101418",
                         highlightthickness=0)
        self.frames: collections.deque[TelemetryFrame] = collections.deque(maxlen=900)
        self.bind("<Configure>", lambda _event: self.redraw())

    def add_frame(self, frame: TelemetryFrame) -> None:
        self.frames.append(frame)
        self.redraw()

    def clear(self) -> None:
        self.frames.clear()
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = max(320, self.winfo_width())
        height = max(220, self.winfo_height())
        margin_left = 46
        margin_right = 14
        top = 24
        temp_height = int((height - top - 40) * 0.62)
        current_top = top + temp_height + 34
        current_height = int((height - current_top - 24) * 0.85)
        plot_width = width - margin_left - margin_right
        if not self.frames:
            self.create_text(width / 2, height / 2, text="Waiting for telemetry",
                             fill="#8899a6", font=("Segoe UI", 11))
            return
        frames = list(self.frames)
        xs = [index for index in range(len(frames))]
        temperatures = []
        for frame in frames:
            temperatures.extend(value for value in
                                (frame.temperature(role) for role in ("T1", "T2", "T3", "SPARE"))
                                if value is not None)
        temp_min = min(temperatures) if temperatures else 0.0
        temp_max = max(temperatures) if temperatures else 40.0
        pad = max(1.0, (temp_max - temp_min) * 0.15)
        temp_low = temp_min - pad
        temp_high = temp_max + pad
        currents = [frame.current_a for frame in frames if frame.current_a is not None]
        current_high = max(currents) if currents else 1.0
        current_high = max(1.0, current_high * 1.2)

        self._grid(margin_left, top, plot_width, temp_height, temp_low, temp_high, "C")
        self._grid(margin_left, current_top, plot_width, current_height, 0.0, current_high, "A")
        self.create_text(8, top, text="T", fill="#c9d1d9", anchor="nw", font=("Segoe UI", 9))
        self.create_text(8, current_top, text="I", fill="#c9d1d9", anchor="nw",
                         font=("Segoe UI", 9))
        for role, color in TEMP_COLORS.items():
            series = [(index, frame.temperature(role)) for index, frame in enumerate(frames)
                      if frame.temperature(role) is not None]
            self._line(series, color, margin_left, top, plot_width, temp_height,
                       temp_low, temp_high, len(frames))
        current_series = [(index, frame.current_a) for index, frame in enumerate(frames)
                          if frame.current_a is not None]
        self._line(current_series, CURRENT_COLOR, margin_left, current_top, plot_width,
                   current_height, 0.0, current_high, len(frames))
        legend_x = margin_left + 8
        for role, color in TEMP_COLORS.items():
            self.create_rectangle(legend_x, 4, legend_x + 10, 14, fill=color, outline="")
            self.create_text(legend_x + 14, 9, text=role, fill="#c9d1d9", anchor="w",
                             font=("Segoe UI", 8))
            legend_x += 52
        self.create_rectangle(legend_x, 4, legend_x + 10, 14, fill=CURRENT_COLOR, outline="")
        self.create_text(legend_x + 14, 9, text="current", fill="#c9d1d9", anchor="w",
                         font=("Segoe UI", 8))
        last = frames[-1]
        state = last.state or "UNKNOWN"
        self.create_text(width - margin_right, 9,
                         text=f"{last.kind} {state} | {len(frames)} frames",
                         fill="#8899a6", anchor="e", font=("Segoe UI", 8))

    def _grid(self, left: int, top: int, width: int, height: int,
              low: float, high: float, unit: str) -> None:
        self.create_rectangle(left, top, left + width, top + height,
                              outline="#30363d", fill="#0d1117")
        for index in range(0, 5):
            y = top + height * index / 4
            self.create_line(left, y, left + width, y, fill="#21262d")
            value = high - (high - low) * index / 4
            self.create_text(left - 4, y, text=f"{value:.1f}", fill="#8899a6",
                             anchor="e", font=("Segoe UI", 7))
        self.create_text(left + width, top + height + 10, text=unit, fill="#8899a6",
                         anchor="e", font=("Segoe UI", 7))

    def _line(self, series: list[tuple[int, float]], color: str, left: int, top: int,
              width: int, height: int, low: float, high: float, count: int) -> None:
        if len(series) < 2 or count < 2:
            return
        span = high - low if high != low else 1.0
        points: list[float] = []
        for index, value in series:
            x = left + width * index / max(1, count - 1)
            y = top + height * (1.0 - (value - low) / span)
            points.extend((x, y))
        self.create_line(*points, fill=color, width=1.6, smooth=False)
