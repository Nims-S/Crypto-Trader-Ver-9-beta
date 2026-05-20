from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricSample:
    name: str
    value: float
    timestamp_ns: int
