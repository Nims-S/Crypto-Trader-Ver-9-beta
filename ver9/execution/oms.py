from __future__ import annotations

from collections.abc import Mapping

from ver9.events.base_event import RuntimeEvent
from ver9.events.execution_events import FillReceived
from ver9.events.execution_events import OrderAccepted
from ver9.events.execution_events import OrderRejected
from ver9.events.execution_events import OrderSubmitted
from ver9.exchanges.base.adapter import BaseExchangeAdapter
from ver9.runtime.kernel.event_bus import EventBus


class OrderManagementSystem:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        exchange_adapters: Mapping[str, BaseExchangeAdapter],
        default_exchange: str,
    ) -> None:
        self.event_bus = event_bus
        self.exchange_adapters = exchange_adapters
        self.default_exchange = default_exchange

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
                    reason=f"exchange_adapter_not_registered:{self.default_exchange}",
                )
            )
            return

        await adapter.submit_order(event)

    async def _on_order_accepted(self, event: RuntimeEvent) -> None:
        if not isinstance(event, OrderAccepted):
            return

    async def _on_fill_received(self, event: RuntimeEvent) -> None:
        if not isinstance(event, FillReceived):
            return

    async def _on_order_rejected(self, event: RuntimeEvent) -> None:
        if not isinstance(event, OrderRejected):
            return
