"""Phase 3: Base Exchange Adapter - Protocol-Based & Domain-Event-Driven.

Key changes from legacy adapter:
1. Accept OrderSubmittedDomain (not legacy OrderSubmitted)
2. Depend on EventPublisher (inject via constructor)
3. Emit ONLY domain events, never legacy events
4. Use AsyncLogger and MetricsCollector protocols
5. NO import of ver9.runtime.kernel.event_bus

This is the new canonical base class for all exchange adapters.
Concrete implementations (BinanceAdapter, BybitAdapter) inherit this.
"""
from __future__ import annotations

import abc
import asyncio
import random
from datetime import UTC, datetime
from typing import AsyncIterator

from ver9.config.exchange_config import ExchangeConfig
from ver9.domain.events.execution import (
    OrderSubmittedDomain,
    OrderAcceptedDomain,
    OrderRejectedDomain,
    FillReceivedDomain,
)
from ver9.events.execution_models import (
    ExchangeExecutionResult,
    ExchangeOrderUpdate,
    ExchangeFillUpdate,
)
from ver9.infrastructure.circuit_breaker import CircuitBreaker
from ver9.infrastructure.rate_limiter import RateLimiter
from ver9.interfaces.events.event_publisher import EventPublisher
from ver9.interfaces.logging.async_logger import AsyncLogger
from ver9.interfaces.metrics.metrics_collector import MetricsCollector


class BaseExchangeAdapterPhase3(abc.ABC):
    """Base exchange adapter - protocol-based and domain-event-driven.

    Responsibilities:
    - websocket lifecycle management
    - resilient reconnect orchestration
    - circuit breaker enforcement
    - outbound request throttling
    - execution stream normalization
    - PUBLISH ONLY domain events

    Non-Responsibilities:
    - position ownership
    - portfolio mutation
    - strategy lifecycle
    - state persistence
    """

    def __init__(
        self,
        *,
        event_publisher: EventPublisher,
        config: ExchangeConfig,
        logger: AsyncLogger,
        metrics: MetricsCollector,
    ) -> None:
        """Initialize with protocol dependencies.
        
        Args:
            event_publisher: Protocol for publishing domain events
            config: Exchange configuration
            logger: Async logger (implements AsyncLogger protocol)
            metrics: Metrics collector (implements MetricsCollector protocol)
        """
        self._event_publisher = event_publisher
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
        """Start adapter lifecycle."""
        await self._connect_with_resilience()
        self._health_monitor_task = asyncio.create_task(
            self._monitor_connection_health()
        )
        await self._logger.info(
            "exchange_adapter_started",
            exchange=self.exchange_name,
        )

    async def stop(self) -> None:
        """Gracefully stop adapter."""
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
        """Protected connection orchestration."""
        async with self._connection_lock:
            if self._shutdown_requested:
                return
            try:
                await self._circuit_breaker.call(self.connect)
                self._connected = True
                self._reconnect_attempts = 0
                self._metrics.increment_counter(
                    "exchange_connection_success",
                    {"exchange": self.exchange_name},
                )
                await self._logger.info(
                    "exchange_connected",
                    exchange=self.exchange_name,
                )
            except Exception as exc:
                self._connected = False
                self._reconnect_attempts += 1
                self._metrics.increment_counter(
                    "exchange_connection_failure",
                    {"exchange": self.exchange_name},
                )
                await self._logger.error(
                    "exchange_connection_failure",
                    exchange=self.exchange_name,
                    error_type=type(exc).__name__,
                    reconnect_attempt=self._reconnect_attempts,
                )
                if self._circuit_breaker.is_open:
                    await self._logger.warning(
                        "exchange_circuit_breaker_open",
                        exchange=self.exchange_name,
                    )
                raise

    async def _monitor_connection_health(self) -> None:
        """Periodic connection heartbeat monitoring."""
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
                self._metrics.increment_counter(
                    "exchange_heartbeat_failure",
                    {"exchange": self.exchange_name},
                )
                self._connected = False
                await self._reconnect_with_backoff(correlation_id=correlation_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._logger.error(
                    "connection_health_monitor_failure",
                    exchange=self.exchange_name,
                    error_type=type(exc).__name__,
                )

    async def _reconnect_with_backoff(self, correlation_id: str) -> None:
        """Exponential reconnect routine."""
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
        """Execute request under exchange rate limits."""
        await self._rate_limiter.acquire()
        return await request_coro

    async def _check_connection_health(self) -> bool:
        """Exchange-agnostic heartbeat validation."""
        return self._connected

    # ========================================================================
    # Abstract Methods - Implemented by Concrete Adapters
    # ========================================================================

    @abc.abstractmethod
    async def connect(self) -> None:
        """Open websocket connections and authenticate."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Gracefully terminate websocket connections."""

    @abc.abstractmethod
    async def submit_order(
        self,
        event: OrderSubmittedDomain,
    ) -> ExchangeExecutionResult:
        """Submit signed REST execution request.
        
        Takes canonical OrderSubmittedDomain and returns ExchangeExecutionResult.
        """

    @abc.abstractmethod
    async def execution_stream(
        self,
    ) -> AsyncIterator[ExchangeOrderUpdate | ExchangeFillUpdate]:
        """Yield normalized exchange execution updates."""
