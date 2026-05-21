from __future__ import annotations

from typing import Protocol


class MetricsCollectorProtocol(Protocol):
    def increment(
        self,
        metric_name: str,
        value: int = 1,
    ) -> None:
        ...

    def gauge(
        self,
        metric_name: str,
        value: float,
    ) -> None:
        ...
