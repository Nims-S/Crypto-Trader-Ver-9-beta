"""Metrics collector protocol."""
from __future__ import annotations

from typing import Protocol


class MetricsCollector(Protocol):
    """Protocol for metrics collection."""

    def increment_counter(
        self,
        name: str,
        labels: dict[str, str],
        *,
        amount: int = 1,
    ) -> None:
        """Increment a counter metric."""
        ...

    def record_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str],
    ) -> None:
        """Record a gauge metric."""
        ...

    def record_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str],
    ) -> None:
        """Record a histogram sample."""
        ...
