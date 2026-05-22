"""Order routing orchestration protocol."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ver9.domain.events.execution import OrderSubmittedDomain


class OrderRouter(Protocol):
    """Protocol for order routing orchestration.
    
    Handles submission of orders to exchanges and coordination
    of lifecycle events (acceptance, fills, rejections).
    """

    async def submit_order(self, event: OrderSubmittedDomain) -> None:
        """Submit order for execution."""
        ...
