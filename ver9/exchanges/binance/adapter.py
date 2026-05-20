from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from ver9.events.execution_events import FillReceived
from ver9.events.execution_events import OrderSubmitted
from ver9.events.market_events import TradeEvent
from ver9.exchanges.base.adapter import BaseExchangeAdapter
from ver9.observability.logging import AsyncJsonLogger
from ver9.observability.metrics import MetricsCollector
from ver9.observability.tracing import TraceProvider
from ver9.runtime.kernel.event_bus import EventBus
from ver9.runtime.resilience.circuit_breaker import CircuitBreaker
from ver9.runtime.resilience.rate_limiter import RateLimiter


class BinanceAdapter(BaseExchangeAdapter):
    def __init__(
        self,
        *,
        event_bus: EventBus,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        logger: AsyncJsonLogger | None = None,
        metrics: MetricsCollector | None = None,
        trace_provider: TraceProvider | None = None,
    ) -> None:
        super().__init__(
            exchange_name="binance",
            event_bus=event_bus,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            logger=logger,
            metrics=metrics,
            trace_provider=trace_provider,
        )

    async def submit_order(self, event: OrderSubmitted) -> None:
        if not await self.rate_limiter.allow_request():
            await self.publish_order_rejected(
                order_id=event.order_id,
                reason="binance_rate_limited",
                correlation_id=event.correlation_id,
            )
            return

        if not await self.circuit_breaker.allow_request():
            await self.publish_order_rejected(
                order_id=event.order_id,
                reason="binance_circuit_open",
                correlation_id=event.correlation_id,
            )
            return

        await self.publish_order_accepted(
            order_id=event.order_id,
            exchange_order_id=f"binance-{uuid4()}",
            correlation_id=event.correlation_id,
        )

    def normalize_trade_payload(
        self,
        payload: Mapping[str, object],
        *,
        correlation_id: str,
    ) -> TradeEvent:
        return TradeEvent(
            event_id=self._event_id(),
            timestamp_ns=self._timestamp_ns(),
            correlation_id=correlation_id,
            symbol=self._string_value(payload, "symbol", "s", default="UNKNOWN"),
            price=self._float_value(payload, "price", "p", "lastPrice", "c"),
            quantity=self._float_value(payload, "quantity", "q", "volume", "v"),
            side=self._string_value(payload, "side", "S", default="unknown").lower(),
        )

    def normalize_fill_payload(
        self,
        payload: Mapping[str, object],
        *,
        correlation_id: str,
    ) -> FillReceived:
        return FillReceived(
            event_id=self._event_id(),
            timestamp_ns=self._timestamp_ns(),
            correlation_id=correlation_id,
            order_id=self._string_value(payload, "order_id", "clientOrderId", "c"),
            fill_id=self._string_value(payload, "fill_id", "tradeId", "t"),
            price=self._float_value(payload, "price", "p", "lastPrice"),
            quantity=self._float_value(payload, "quantity", "q", "executedQty"),
            fee=self._float_value(payload, "fee", "commission", default=0.0),
            fee_asset=self._string_value(payload, "fee_asset", "commissionAsset", default="USDT"),
        )
