from __future__ import annotations

from typing import Protocol

from ver9.domain.events.execution import OrderSubmitted


class OrderRouter(Protocol):
    async def route_order(
        self,
        order: OrderSubmitted,
    ) -> None:
        ...
