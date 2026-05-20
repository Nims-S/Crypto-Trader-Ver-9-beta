from __future__ import annotations

from time import time_ns
from uuid import uuid4

from ver9.events.portfolio_events import RiskBreachDetected
from ver9.runtime.kernel.event_bus import EventBus


class PortfolioRiskMonitor:
    def __init__(
        self,
        *,
        event_bus: EventBus,
    ) -> None:
        self.event_bus = event_bus

    async def evaluate_metric(
        self,
        *,
        metric_name: str,
        current_value: float,
        threshold: float,
        breach_when_above: bool = True,
        correlation_id: str | None = None,
    ) -> bool:
        breached = (
            current_value > threshold
            if breach_when_above
            else current_value < threshold
        )

        if breached:
            await self.event_bus.publish(
                RiskBreachDetected(
                    event_id=str(uuid4()),
                    timestamp_ns=time_ns(),
                    correlation_id=correlation_id or str(uuid4()),
                    metric_violated=metric_name,
                    current_value=current_value,
                    threshold=threshold,
                )
            )

        return breached
