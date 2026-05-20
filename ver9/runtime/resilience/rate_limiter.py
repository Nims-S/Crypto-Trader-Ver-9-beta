from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic_ns


@dataclass(frozen=True, slots=True)
class RateLimitSnapshot:
    max_requests: int
    window_seconds: float
    request_count: int
    window_started_ns: int


class RateLimiter:
    def __init__(
        self,
        *,
        max_requests: int = 1200,
        window_seconds: float = 60.0,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = asyncio.Lock()
        self._request_count = 0
        self._window_started_ns = monotonic_ns()

    async def allow_request(self) -> bool:
        async with self._lock:
            self._reset_window_if_needed()

            if self._request_count >= self.max_requests:
                return False

            self._request_count += 1
            return True

    async def snapshot(self) -> RateLimitSnapshot:
        async with self._lock:
            self._reset_window_if_needed()
            return RateLimitSnapshot(
                max_requests=self.max_requests,
                window_seconds=self.window_seconds,
                request_count=self._request_count,
                window_started_ns=self._window_started_ns,
            )

    def _reset_window_if_needed(self) -> None:
        elapsed_seconds = (
            monotonic_ns() - self._window_started_ns
        ) / 1_000_000_000

        if elapsed_seconds >= self.window_seconds:
            self._request_count = 0
            self._window_started_ns = monotonic_ns()
