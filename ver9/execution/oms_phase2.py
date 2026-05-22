"""Order Management System (OMS) – Phase 2 Refactored.

The OMS now implements dual-stack normalization:

1. Accepts BOTH legacy (ver9.events) and canonical (ver9.domain) events
2. Normalizes incoming events to canonical domain types
3. Uses only domain events for internal logic
4. Publishes only domain events via EventPublisher

Dependencies:
- ONLY on ver9.domain.events, ver9.domain.models
- ONLY on ver9.interfaces (EventPublisher, ExchangeAdapter, AsyncLogger, MetricsCollector)
- NO direct imports of ver9.runtime or concrete adapters

BACKWARD COMPATIBILITY:
- Still accepts legacy events from old code paths
- Translates them internally to canonical schema
- Existing callers don't need to change immediately
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Union

from ver9.domain.events.execution import (
    OrderSubmittedDomain,
    OrderAcceptedDomain,
    OrderRejectedDomain,
    FillReceivedDomain,
)
from ver9.events.compat.translators import (
    legacy_order_submitted_to_domain,
    legacy_order_accepted_to_domain,
    legacy_order_rejected_to_domain,
    legacy_fill_received_to_domain,
)
from ver9.events.execution_events import (
    OrderSubmitted as LegacyOrderSubmitted,
    OrderAccepted as LegacyOrderAccepted,
    OrderRejected as LegacyOrderRejected,
    FillReceived as LegacyFillReceived,
)
from ver9.events.execution_models import (
    ExchangeExecutionResult,
    ExchangeOrderUpdate,
    ExchangeFillUpdate,
)
from ver9.interfaces.exchanges.exchange_adapter import ExchangeAdapter
from ver9.interfaces.events.event_publisher import EventPublisher
from ver9.interfaces.logging.async_logger import AsyncLogger
from ver9.interfaces.metrics.metrics_collector import MetricsCollector


class OrderManagementSystemPhase2:
    """Order routing and lifecycle orchestration.
    
    Responsibilities:
    - Route orders to selected exchange
    - Normalize exchange responses to canonical events
    - Publish domain events to EventPublisher
    - Track order state transitions
    - Handle rejections and failures
    
    Non-Responsibilities:
    - Portfolio state ownership (read-only via RuntimeStateView)
    - Risk calculations (delegated to risk engine)
    - Persistence (delegated to runtime)
    """

    def __init__(
        self,
        *,
        event_publisher: EventPublisher,
        exchange_adapters: Mapping[str, ExchangeAdapter],
        default_exchange: str,
        logger: AsyncLogger | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        """Initialize OMS with protocol dependencies.
        
        Args:
            event_publisher: Protocol for publishing domain events
            exchange_adapters: Mapping of exchange name -> adapter instance
            default_exchange: Default exchange for order routing
            logger: Optional async logger
            metrics: Optional metrics collector
        """
        self.event_publisher = event_publisher
        self.exchange_adapters = exchange_adapters
        self.default_exchange = default_exchange
        self.logger = logger
        self.metrics = metrics

    async def start(self) -> None:
        """Start OMS lifecycle."""
        if self.logger is not None:
            await self.logger.info("oms_started", default_exchange=self.default_exchange)

    # Dual-Stack Event Handlers
    async def handle_order_submitted(
        self,
        event: Union[LegacyOrderSubmitted, OrderSubmittedDomain],
    ) -> None:
        """Handle order submission (legacy or domain)."""
        if isinstance(event, LegacyOrderSubmitted):
            domain_event = legacy_order_submitted_to_domain(event)
        else:
            domain_event = event
        await self._process_order_submitted(domain_event)

    async def handle_order_accepted(
        self,
        event: Union[LegacyOrderAccepted, OrderAcceptedDomain],
    ) -> None:
        """Handle order acceptance (legacy or domain)."""
        if isinstance(event, LegacyOrderAccepted):
            domain_event = legacy_order_accepted_to_domain(event)
        else:
            domain_event = event
        await self._process_order_accepted(domain_event)

    async def handle_order_rejected(
        self,
        event: Union[LegacyOrderRejected, OrderRejectedDomain],
    ) -> None:
        """Handle order rejection (legacy or domain)."""
        if isinstance(event, LegacyOrderRejected):
            domain_event = legacy_order_rejected_to_domain(event)
        else:
            domain_event = event
        await self._process_order_rejected(domain_event)

    async def handle_fill_received(
        self,
        event: Union[LegacyFillReceived, FillReceivedDomain],
    ) -> None:
        """Handle fill reception (legacy or domain)."""
        if isinstance(event, LegacyFillReceived):
            domain_event = legacy_fill_received_to_domain(event)
        else:
            domain_event = event
        await self._process_fill_received(domain_event)

    # Internal Processing (Domain Events Only)
    async def _process_order_submitted(self, event: OrderSubmittedDomain) -> None:
        """Process canonical OrderSubmittedDomain."""
        adapter = self.exchange_adapters.get(self.default_exchange)
        if adapter is None:
            rejection = OrderRejectedDomain(
                internal_order_id=event.internal_order_id,
                exchange=event.exchange,
                reason=f"exchange_adapter_not_registered:{self.default_exchange}",
                timestamp=event.timestamp,
            )
            await self.event_publisher.publish_order_rejected(rejection)
            if self.logger is not None:
                await self.logger.warning(
                    "oms_adapter_not_found",
                    exchange=self.default_exchange,
                    internal_order_id=event.internal_order_id,
                )
            return

        try:
            result: ExchangeExecutionResult = await adapter.submit_order(event)
            if self.metrics is not None:
                self.metrics.increment_counter(
                    "oms_orders_submitted",
                    {"exchange": self.default_exchange},
                )
            if self.logger is not None:
                await self.logger.info(
                    "oms_order_submitted",
                    exchange=self.default_exchange,
                    internal_order_id=event.internal_order_id,
                    exchange_order_id=result.exchange_order_id,
                    status=result.status,
                )
        except Exception as exc:
            rejection = OrderRejectedDomain(
                internal_order_id=event.internal_order_id,
                exchange=self.default_exchange,
                reason=f"adapter_error:{type(exc).__name__}:{str(exc)}",
                timestamp=event.timestamp,
            )
            await self.event_publisher.publish_order_rejected(rejection)
            if self.logger is not None:
                await self.logger.error(
                    "oms_order_submission_failed",
                    exchange=self.default_exchange,
                    internal_order_id=event.internal_order_id,
                    error=str(exc),
                )

    async def _process_order_accepted(self, event: OrderAcceptedDomain) -> None:
        """Process canonical OrderAcceptedDomain."""
        await self.event_publisher.publish_order_accepted(event)
        if self.logger is not None:
            await self.logger.info(
                "oms_order_accepted",
                internal_order_id=event.internal_order_id,
                exchange_order_id=event.exchange_order_id,
                exchange=event.exchange,
            )

    async def _process_order_rejected(self, event: OrderRejectedDomain) -> None:
        """Process canonical OrderRejectedDomain."""
        await self.event_publisher.publish_order_rejected(event)
        if self.logger is not None:
            await self.logger.warning(
                "oms_order_rejected",
                internal_order_id=event.internal_order_id,
                exchange=event.exchange,
                reason=event.reason,
            )

    async def _process_fill_received(self, event: FillReceivedDomain) -> None:
        """Process canonical FillReceivedDomain."""
        await self.event_publisher.publish_fill_received(event)
        if self.metrics is not None:
            self.metrics.increment_counter(
                "oms_fills_received",
                {"exchange": event.exchange},
            )
        if self.logger is not None:
            await self.logger.info(
                "oms_fill_received",
                internal_order_id=event.internal_order_id,
                execution_id=event.execution_id,
                exchange=event.exchange,
                quantity=event.quantity,
                price=event.price,
            )

    async def normalize_exchange_order_update(
        self,
        update: ExchangeOrderUpdate,
    ) -> None:
        """Normalize and process exchange order update."""
        if self.logger is not None:
            await self.logger.info(
                "oms_exchange_order_update",
                exchange_order_id=update.exchange_order_id,
                internal_order_id=update.internal_order_id,
                status=update.status,
                cumulative_filled_quantity=update.cumulative_filled_quantity,
            )

    async def normalize_exchange_fill_update(
        self,
        update: ExchangeFillUpdate,
    ) -> None:
        """Normalize and process exchange fill update."""
        if self.logger is not None:
            await self.logger.info(
                "oms_exchange_fill_update",
                exchange_order_id=update.exchange_order_id,
                trade_id=update.trade_id,
                fill_price=update.fill_price,
                fill_quantity=update.fill_quantity,
                liquidity_side=update.liquidity_side,
            )
