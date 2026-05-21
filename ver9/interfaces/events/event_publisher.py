from __future__ import annotations

from typing import Protocol

from ver9.domain.events.runtime import RuntimeEvent


class EventPublisher(Protocol):
    async def publish(self, event: RuntimeEvent) -> None:
        ...
