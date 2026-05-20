from __future__ import annotations

from collections.abc import Mapping

from ver9.events.base_event import RuntimeEvent
from ver9.events.execution_events import FillReceived
from ver9.events.execution_events import OrderAccepted
from ver9.events.execution_events import OrderRejected
from ver9.events.execution_events import OrderSubmitted
from ver9.events.execution_models import ExchangeExecutionResult
from ver9.events.execution_models import ExchangeFillUpdate
from ver9.events.execution_models import ExchangeOrderUpdate
from ver9.exchanges.base.adapter import BaseExchangeAdapter
from ver9.observability.logging import AsyncJsonLogger
from ver9.observability.metrics import MetricsCollector
from ver9.observability.tracing import TraceProvider
from ver9.runtime.kernel.event_bus import EventBus


class OrderManagementSystem:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        exchange_adapters: Mapping[str, BaseExchangeAdapter],
        default_exchange: str,
        logger: AsyncJsonLogger | None = None,
        metrics: MetricsCollector | None = None,
        trace_provider: TraceProvider | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.exchange_adapters = exchange_adapters
        self.default_exchange = default_exchange
        self.logger = logger
        self.metrics = metrics
        self.trace_provider = trace_provider

    async def start(self) -> None:
        await self.event_bus.subscribe(
            OrderSubmitted,
            self._on_order_submitted,
        )
        await self.event_bus.subscribe(
            OrderAccepted,
            self._on_order_accepted,
        )
        await self.event_bus.subscribe(
            FillReceived,
            self._on_fill_received,
        )
        await self.event_bus.subscribe(
            OrderRejected,
            self._on_order_rejected,
        )

    async def _on_order_submitted(self, event: RuntimeEvent) -> None:
        if not isinstance(event, OrderSubmitted):
            return

        adapter = self.exchange_adapters.get(self.default_exchange)

        if adapter is None:
            await self.event_bus.publish(
                OrderRejected(
                    event_id=f"{event.event_id}:no_adapter",
                    timestamp_ns=event.timestamp_ns,
                    correlation_id=event.correlation_id,
                    order_id=event.order_id,
                    reason=(
                        f"exchange_adapter_not_registered:{self.default_exchange}"
                    ),
                )
            )
            return

        result: ExchangeExecutionResult = (
            await adapter.submit_order(event)
        )

        if self.metrics is not None:
            self.metrics.increment_counter(
                "oms_orders_routed",
                {"exchange": self.default_exchange},
            )

        if self.logger is not None:
            await self.logger.info(
                "oms_order_submitted",
                exchange=self.default_exchange,
                correlation_id=event.correlation_id,
                exchange_order_id=result.exchange_order_id,
                status=result.status,
            )

    async def _on_order_accepted(self, event: RuntimeEvent) -> None:
        if not isinstance(event, OrderAccepted):
            return

    async def _on_fill_received(self, event: RuntimeEvent) -> None:
        if not isinstance(event, FillReceived):
            return

    async def _on_order_rejected(self, event: RuntimeEvent) -> None:
        if not isinstance(event, OrderRejected):
            return

    async def normalize_exchange_order_update(
        self,
        update: ExchangeOrderUpdate,
    ) -> None:
        if self.logger is not None:
            await self.logger.info(
                "oms_exchange_order_update",
                exchange_order_id=update.exchange_order_id,
                internal_order_id=update.internal_order_id,
                status=update.status,
                cumulative_filled_quantity=(
                    update.cumulative_filled_quantity
                ),
            )

    async def normalize_exchange_fill_update(
        self,
        update: ExchangeFillUpdate,
    ) -> None:
        if self.logger is not None:
            await self.logger.info(
                "oms_exchange_fill_update",
                exchange_order_id=update.exchange_order_id,
                trade_id=update.trade_id,
                fill_price=update.fill_price,
                fill_quantity=update.fill_quantity,
                liquidity_side=update.liquidity_side,
            )
