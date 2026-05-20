from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import time_ns


Labels = tuple[tuple[str, str], ...]
MetricKey = tuple[str, Labels]


@dataclass(frozen=True, slots=True)
class CounterSample:
    name: str
    value: int
    labels: Labels
    timestamp_ns: int


@dataclass(frozen=True, slots=True)
class GaugeSample:
    name: str
    value: float
    labels: Labels
    timestamp_ns: int


@dataclass(frozen=True, slots=True)
class HistogramSample:
    name: str
    count: int
    minimum: float
    maximum: float
    total: float
    labels: Labels
    timestamp_ns: int


@dataclass(slots=True)
class _HistogramState:
    count: int = 0
    minimum: float = 0.0
    maximum: float = 0.0
    total: float = 0.0


class MetricsCollector:
    def __init__(self) -> None:
        self._counters: defaultdict[MetricKey, int] = defaultdict(int)
        self._gauges: dict[MetricKey, float] = {}
        self._histograms: defaultdict[MetricKey, _HistogramState] = defaultdict(
            _HistogramState
        )

    def increment_counter(
        self,
        name: str,
        labels: dict[str, str],
        *,
        amount: int = 1,
    ) -> CounterSample:
        key = self._key(name, labels)
        self._counters[key] += amount

        return CounterSample(
            name=name,
            value=self._counters[key],
            labels=key[1],
            timestamp_ns=time_ns(),
        )

    def record_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str],
    ) -> GaugeSample:
        key = self._key(name, labels)
        self._gauges[key] = value

        return GaugeSample(
            name=name,
            value=value,
            labels=key[1],
            timestamp_ns=time_ns(),
        )

    def record_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str],
    ) -> HistogramSample:
        key = self._key(name, labels)
        state = self._histograms[key]

        if state.count == 0:
            state.minimum = value
            state.maximum = value
        else:
            state.minimum = min(state.minimum, value)
            state.maximum = max(state.maximum, value)

        state.count += 1
        state.total += value

        return HistogramSample(
            name=name,
            count=state.count,
            minimum=state.minimum,
            maximum=state.maximum,
            total=state.total,
            labels=key[1],
            timestamp_ns=time_ns(),
        )

    def counter_value(
        self,
        name: str,
        labels: dict[str, str],
    ) -> int:
        return self._counters[self._key(name, labels)]

    def gauge_value(
        self,
        name: str,
        labels: dict[str, str],
    ) -> float | None:
        return self._gauges.get(self._key(name, labels))

    def histogram_value(
        self,
        name: str,
        labels: dict[str, str],
    ) -> HistogramSample | None:
        key = self._key(name, labels)
        state = self._histograms.get(key)

        if state is None:
            return None

        return HistogramSample(
            name=name,
            count=state.count,
            minimum=state.minimum,
            maximum=state.maximum,
            total=state.total,
            labels=key[1],
            timestamp_ns=time_ns(),
        )

    def _key(
        self,
        name: str,
        labels: dict[str, str],
    ) -> MetricKey:
        return (
            name,
            tuple(sorted((str(key), str(value)) for key, value in labels.items())),
        )
