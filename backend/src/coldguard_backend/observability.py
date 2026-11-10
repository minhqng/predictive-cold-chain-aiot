"""Bounded process counters, duration histograms and structured backend logs."""

import json
import logging
import threading
from bisect import bisect_left
from collections import Counter
from time import monotonic

BUCKETS_MS = (1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000)
LOG_FIELDS = ("device_id", "run_id", "boot_id", "seq", "command_id", "prediction_id", "event_id", "attempt_no")


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts = Counter()
        self._durations: dict[str, list[int]] = {}

    def record(self, stage: str, outcome: str, elapsed_ms: float | None = None) -> None:
        with self._lock:
            self._counts[f"{stage}.{outcome}"] += 1
            if elapsed_ms is not None:
                histogram = self._durations.setdefault(stage, [0] * (len(BUCKETS_MS) + 1))
                histogram[bisect_left(BUCKETS_MS, elapsed_ms)] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "scope": "process",
                "counters": dict(self._counts),
                "duration_histograms_ms": {
                    stage: {
                        "upper_bounds_ms": BUCKETS_MS,
                        "bucket_counts": counts.copy(),
                        "count": sum(counts),
                    }
                    for stage, counts in self._durations.items()
                },
            }


runtime_metrics = RuntimeMetrics()


def record_event(
    logger: logging.Logger, stage: str, outcome: str, started: float,
    *, level: int = logging.DEBUG, **identifiers,
) -> None:
    """Record a monotonic duration and allow only known identifier fields in logs."""
    elapsed_ms = (monotonic() - started) * 1000
    runtime_metrics.record(stage, outcome, elapsed_ms)
    if logger.isEnabledFor(level):
        entry = {
            "event": stage, "reason": outcome, "duration_ms": round(elapsed_ms, 3),
            **{field: identifiers[field] for field in LOG_FIELDS if identifiers.get(field) is not None},
        }
        logger.log(level, "%s", json.dumps(entry, separators=(",", ":"), sort_keys=True))
