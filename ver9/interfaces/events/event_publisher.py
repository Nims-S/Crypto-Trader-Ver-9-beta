"""Event publisher protocol.

Abstract interface for publishing events. Allows execution and adapters
to be decoupled from the concrete EventBus implementation in runtime.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ver9.domain.events.execution import (
        OrderSubmittedDomain,
        OrderAcceptedDomain,
        OrderRejectedDomain,
        FillReceivedDomain,
        OrderCancelledDomain,
    )


class EventPublisher(Protocol):
    """Protocol for publishing domain events.
    
    Implementers (e.g., runtime EventBus adapter) accept domain events
    and deliver them to subscribers. This decouples execution logic from
    concrete event bus implementations.
    """

    async def publish_order_submitted(
        self,
        event: OrderSubmittedDomain,
    ) -> None:
        """Publish order submitted event."""
        ...

    async def publish_order_accepted(
        self,
        event: OrderAcceptedDomain,
    ) -> None:
        """Publish order accepted event."""
        ...

    async def publish_order_rejected(
        self,
        event: OrderRejectedDomain,
    ) -> None:
        """Publish order rejected event."""
        ...

    async def publish_fill_received(
        self,
        event: FillReceivedDomain,
    ) -> None:
        """Publish fill received event."""
        ...

    async def publish_order_cancelled(
        self,
        event: OrderCancelledDomain,
    ) -> None:
        """Publish order cancelled event."""
        ...
