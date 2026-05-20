from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from collections.abc import Mapping
from time import time_ns
from uuid import uuid4

from ver9.events.execution_events import FillReceived
from ver9.events.execution_events import OrderAccepted
from ver9.events.execution_events import OrderRejected
from ver9.events.execution_events import OrderSubmitted
from ver9.events.market_events import TradeEvent
from ver9.observability.logging import AsyncJsonLogger
from ver9.observability.metrics import MetricsCollector
from ver9.observability.tracing import TraceProvider
from ver9.runtime.kernel.event_bus import EventBus
from ver9.runtime.resilience.circuit_breaker import CircuitBreaker
from ver9.runtime.resilience.rate_limiter import RateLimiter


class BaseExchangeAdapter(ABC):
    def __init__(
        self,
        *,
        exchange_name: str,
        event_bus: EventBus,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        logger: AsyncJsonLogger | None = None,
        metrics: MetricsCollector | None = None,
        trace_provider: TraceProvider | None = None,
    ) -> None:
        self.exchange_name = exchange_name
        self.event_bus = event_bus
        self.rate_limiter = rate_limiter or RateLimiter()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            target_component=f"exchange:{exchange_name}",
            event_bus=event_bus,
        )
        self.logger = logger
        self.metrics = metrics
        self.trace_provider = trace_provider

    async def publish_trade_payload(
        self,
        payload: Mapping[str, object],
        *,
        correlation_id: str | None = None,
    ) -> TradeEvent:
        event = self.normalize_trade_payload(
            payload,
            correlation_id=correlation_id or str(uuid4()),
        )
        await self.event_bus.publish(event)

        if self.metrics is not None:
            self.metrics.increment_counter(
                "exchange_trade_events_published",
                {"exchange": self.exchange_name},
            )

        return event

    async def publish_fill_payload(
        self,
        payload: Mapping[str, object],
        *,
        correlation_id: str | None = None,
    ) -> FillReceived:
        event = self.normalize_fill_payload(
            payload,
            correlation_id=correlation_id or str(uuid4()),
        )
        await self.event_bus.publish(event)

        if self.metrics is not None:
            self.metrics.increment_counter(
                "exchange_fill_events_published",
                {"exchange": self.exchange_name},
            )

        return event

    async def publish_order_accepted(
        self,
        *,
        order_id: str,
        exchange_order_id: str,
        correlation_id: str,
    ) -> None:
        await self.event_bus.publish(
            OrderAccepted(
                event_id=str(uuid4()),
                timestamp_ns=time_ns(),
                correlation_id=correlation_id,
                order_id=order_id,
                exchange_order_id=exchange_order_id,
            )
        )

    async def publish_order_rejected(
        self,
        *,
        order_id: str,
        reason: str,
        correlation_id: str,
    ) -> None:
        await self.event_bus.publish(
            OrderRejected(
                event_id=str(uuid4()),
                timestamp_ns=time_ns(),
                correlation_id=correlation_id,
                order_id=order_id,
                reason=reason,
            )
        )

    @abstractmethod
    async def submit_order(self, event: OrderSubmitted) -> None:
        raise NotImplementedError

    @abstractmethod
    def normalize_trade_payload(
        self,
        payload: Mapping[str, object],
        *,
        correlation_id: str,
    ) -> TradeEvent:
        raise NotImplementedError

    @abstractmethod
    def normalize_fill_payload(
        self,
        payload: Mapping[str, object],
        *,
        correlation_id: str,
    ) -> FillReceived:
        raise NotImplementedError

    def _event_id(self) -> str:
        return str(uuid4())

    def _timestamp_ns(self) -> int:
        return time_ns()

    def _string_value(
        self,
        payload: Mapping[str, object],
        *keys: str,
        default: str = "",
    ) -> str:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return str(value)
        return default

    def _float_value(
        self,
        payload: Mapping[str, object],
        *keys: str,
        default: float = 0.0,
    ) -> float:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default
