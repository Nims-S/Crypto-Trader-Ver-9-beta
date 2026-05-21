from __future__ import annotations

import abc
import asyncio
import random
from datetime import UTC, datetime
from typing import AsyncIterator

from ver9.config.exchange_config import ExchangeConfig
from ver9.runtime.kernel.event_bus import EventBus
from ver9.events.system_events import CircuitBreakerTripped
from ver9.events.execution_events import OrderSubmitted
from ver9.events.execution_models import (
    ExchangeExecutionResult,
    ExchangeOrderUpdate,
    ExchangeFillUpdate,
)
from ver9.infrastructure.circuit_breaker import CircuitBreaker
from ver9.infrastructure.logging import AsyncJsonLogger
from ver9.infrastructure.metrics import MetricsCollector
from ver9.infrastructure.rate_limiter import RateLimiter


class BaseExchangeAdapter(abc.ABC):
    """
    Canonical exchange adapter abstraction.

    Responsibilities:
    - websocket lifecycle management
    - resilient reconnect orchestration
    - circuit breaker enforcement
    - outbound request throttling
    - execution stream normalization

    Non-Responsibilities:
    - position ownership
    - portfolio mutation
    - strategy lifecycle
    - state persistence
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ExchangeConfig,
        logger: AsyncJsonLogger,
        metrics: MetricsCollector,
    ) -> None:
        self._event_bus = event_bus
        self._config = config
        self._logger = logger
        self._metrics = metrics

        self._rate_limiter = RateLimiter(
            rate=config.rate_limit_per_second,
            capacity=config.rate_limit_burst,
        )

        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout_seconds,
        )

        self._connected: bool = False
        self._shutdown_requested: bool = False

        self._connection_lock = asyncio.Lock()
        self._health_monitor_task: asyncio.Task | None = None

        self._reconnect_attempts: int = 0

    @property
    def exchange_name(self) -> str:
        return self._config.exchange_name

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """
        Start exchange adapter lifecycle.
        """

        await self._connect_with_resilience()

        self._health_monitor_task = asyncio.create_task(
            self._monitor_connection_health()
        )

        await self._logger.info(
            "exchange_adapter_started",
            exchange=self.exchange_name,
        )

    async def stop(self) -> None:
        """
        Gracefully stop exchange adapter.
        """

        self._shutdown_requested = True

        if self._health_monitor_task is not None:
            self._health_monitor_task.cancel()

        await self.disconnect()

        self._connected = False

        await self._logger.info(
            "exchange_adapter_stopped",
            exchange=self.exchange_name,
        )

    async def _connect_with_resilience(self) -> None:
        """
        Protected exchange connection orchestration.
        """

        async with self._connection_lock:

            if self._shutdown_requested:
                return

            try:
                await self._circuit_breaker.call(self.connect)

                self._connected = True
                self._reconnect_attempts = 0

                self._metrics.increment(
                    "exchange_connection_success",
                    exchange=self.exchange_name,
                )

                await self._logger.info(
                    "exchange_connected",
                    exchange=self.exchange_name,
                )

            except Exception as exc:
                self._connected = False
                self._reconnect_attempts += 1

                self._metrics.increment(
                    "exchange_connection_failure",
                    exchange=self.exchange_name,
                )

                await self._logger.error(
                    "exchange_connection_failure",
                    exchange=self.exchange_name,
                    error_type=type(exc).__name__,
                    reconnect_attempt=self._reconnect_attempts,
                )

                if self._circuit_breaker.is_open:
                    event = CircuitBreakerTripped(
                        correlation_id=(
                            f"cb-{self.exchange_name}-{datetime.now(UTC).timestamp()}"
                        ),
                        timestamp=datetime.now(UTC),
                        exchange=self.exchange_name,
                        reason="repeated_connection_failures",
                    )

                    await self._event_bus.publish(event)

                raise

    async def _monitor_connection_health(self) -> None:
        """
        Periodic connection heartbeat monitoring.

        Detects silent websocket degradation and triggers
        exponential reconnect orchestration.
        """

        while not self._shutdown_requested:

            await asyncio.sleep(
                self._config.connection_healthcheck_interval_seconds
            )

            try:
                healthy = await self._check_connection_health()

                if healthy:
                    continue

                correlation_id = (
                    f"health-{self.exchange_name}-{datetime.now(UTC).timestamp()}"
                )

                await self._logger.warning(
                    "exchange_heartbeat_failed",
                    exchange=self.exchange_name,
                    correlation_id=correlation_id,
                )

                self._metrics.increment(
                    "exchange_heartbeat_failure",
                    exchange=self.exchange_name,
                )

                self._connected = False

                await self._reconnect_with_backoff(
                    correlation_id=correlation_id,
                )

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                await self._logger.error(
                    "connection_health_monitor_failure",
                    exchange=self.exchange_name,
                    error_type=type(exc).__name__,
                )

    async def _reconnect_with_backoff(
        self,
        correlation_id: str,
    ) -> None:
        """
        Exponential reconnect routine.
        """

        base_backoff = self._config.base_reconnect_backoff_seconds
        max_backoff = self._config.max_reconnect_backoff_seconds

        while not self._shutdown_requested:

            try:
                backoff = min(
                    max_backoff,
                    base_backoff * (2 ** self._reconnect_attempts),
                )

                jitter = random.uniform(0.0, 1.0)
                delay = backoff + jitter

                await self._logger.warning(
                    "exchange_reconnect_scheduled",
                    exchange=self.exchange_name,
                    correlation_id=correlation_id,
                    reconnect_attempt=self._reconnect_attempts,
                    reconnect_delay_seconds=round(delay, 2),
                )

                await asyncio.sleep(delay)

                await self._connect_with_resilience()

                if self._connected:
                    await self._logger.info(
                        "exchange_reconnect_success",
                        exchange=self.exchange_name,
                        correlation_id=correlation_id,
                    )

                    return

            except Exception:
                self._reconnect_attempts += 1

    async def throttled_request(self, request_coro):
        """
        Execute outbound requests under exchange rate limits.
        """

        await self._rate_limiter.acquire()

        return await request_coro

    async def _check_connection_health(self) -> bool:
        """
        Exchange-agnostic heartbeat validation.

        Individual exchanges may override this for more
        sophisticated websocket heartbeat logic.
        """

        return self._connected

    @abc.abstractmethod
    async def connect(self) -> None:
        """
        Open websocket connections and authenticate.
        """

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """
        Gracefully terminate websocket connections.
        """

    @abc.abstractmethod
    async def submit_order(
        self,
        event: OrderSubmitted,
    ) -> ExchangeExecutionResult:
        """
        Submit signed REST execution request.
        """

    @abc.abstractmethod
    async def execution_stream(
        self,
    ) -> AsyncIterator[
        ExchangeOrderUpdate | ExchangeFillUpdate
    ]:
        """
        Yield normalized exchange execution updates.
        """
