from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from time import monotonic
from time import time_ns
from uuid import uuid4

from ver9.events.system_events import CircuitBreakerTripped
from ver9.runtime.kernel.event_bus import EventBus


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitBreakerSnapshot:
    target_component: str
    state: CircuitState
    failure_count: int
    reconnect_attempts: int
    last_failure_reason: str | None


class CircuitBreaker:
    def __init__(
        self,
        *,
        target_component: str,
        event_bus: EventBus,
        failure_threshold: int = 3,
        reset_timeout_seconds: float = 30.0,
    ) -> None:
        self.target_component = target_component
        self.event_bus = event_bus
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self._lock = asyncio.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._reconnect_attempts = 0
        self._opened_at: float | None = None
        self._last_failure_reason: str | None = None

    async def allow_request(self) -> bool:
        async with self._lock:
            if self._state is CircuitState.CLOSED:
                return True

            if self._state is CircuitState.HALF_OPEN:
                return True

            if self._opened_at is None:
                return False

            if monotonic() - self._opened_at >= self.reset_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                return True

            return False

    async def record_success(self) -> None:
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._last_failure_reason = None

    async def record_failure(self, reason: str) -> None:
        event: CircuitBreakerTripped | None = None

        async with self._lock:
            self._failure_count += 1
            self._last_failure_reason = reason

            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = monotonic()
                event = CircuitBreakerTripped(
                    event_id=str(uuid4()),
                    timestamp_ns=time_ns(),
                    correlation_id=str(uuid4()),
                    target_component=self.target_component,
                    reason=reason,
                )

        if event is not None:
            await self.event_bus.publish(event)

    async def record_reconnect_attempt(self) -> int:
        async with self._lock:
            self._reconnect_attempts += 1
            return self._reconnect_attempts

    async def snapshot(self) -> CircuitBreakerSnapshot:
        async with self._lock:
            return CircuitBreakerSnapshot(
                target_component=self.target_component,
                state=self._state,
                failure_count=self._failure_count,
                reconnect_attempts=self._reconnect_attempts,
                last_failure_reason=self._last_failure_reason,
            )
