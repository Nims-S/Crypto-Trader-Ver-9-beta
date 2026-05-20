from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable
from collections.abc import Callable

from ver9.events.base_event import RuntimeEvent


EventCallback = Callable[[RuntimeEvent], Awaitable[None] | None]


class EventBus:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._priority_subscribers: dict[
            type[RuntimeEvent],
            tuple[EventCallback, ...],
        ] = defaultdict(tuple)
        self._subscribers: dict[
            type[RuntimeEvent],
            tuple[EventCallback, ...],
        ] = defaultdict(tuple)
        self._closed = False

    async def subscribe(
        self,
        event_type: type[RuntimeEvent],
        callback: EventCallback,
    ) -> None:
        async with self._lock:
            self._raise_if_closed()
            callbacks = self._subscribers[event_type]
            self._subscribers[event_type] = (*callbacks, callback)

    async def subscribe_priority(
        self,
        event_type: type[RuntimeEvent],
        callback: EventCallback,
    ) -> None:
        async with self._lock:
            self._raise_if_closed()
            callbacks = self._priority_subscribers[event_type]
            self._priority_subscribers[event_type] = (*callbacks, callback)

    async def publish(self, event: RuntimeEvent) -> None:
        async with self._lock:
            self._raise_if_closed()
            priority_callbacks = tuple(
                callback
                for event_type, subscribers in self._priority_subscribers.items()
                if isinstance(event, event_type)
                for callback in subscribers
            )
            callbacks = tuple(
                callback
                for event_type, subscribers in self._subscribers.items()
                if isinstance(event, event_type)
                for callback in subscribers
            )

        for callback in priority_callbacks:
            await self._deliver(callback, event)

        await asyncio.gather(
            *(
                self._deliver(callback, event)
                for callback in callbacks
            )
        )

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            self._priority_subscribers.clear()
            self._subscribers.clear()

    async def _deliver(
        self,
        callback: EventCallback,
        event: RuntimeEvent,
    ) -> None:
        result = callback(event)

        if result is not None:
            await result

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise RuntimeError("event bus is closed")
