from __future__ import annotations

from pathlib import Path
from time import perf_counter_ns
from types import MappingProxyType

import msgspec

from ver9.config.schemas import AppConfig
from ver9.config.settings import AsyncConfigProvider
from ver9.events.base_event import RuntimeEvent
from ver9.execution.oms import OrderManagementSystem
from ver9.exchanges.base.adapter import BaseExchangeAdapter
from ver9.exchanges.binance.adapter import BinanceAdapter
from ver9.exchanges.bitunix.adapter import BitunixAdapter
from ver9.exchanges.bybit.adapter import BybitAdapter
from ver9.observability.logging import AsyncJsonLogger
from ver9.observability.logging import get_logger
from ver9.observability.metrics import MetricsCollector
from ver9.observability.tracing import TraceProvider
from ver9.runtime.persistence.event_store import EventStore
from ver9.runtime.persistence.replay_engine import ReplayEngine
from ver9.runtime.persistence.snapshot_store import SnapshotStore
from ver9.runtime.resilience.rate_limiter import RateLimiter
from ver9.runtime.state.runtime_state_store import RuntimeStateStore
from ver9.runtime.state.state_models import RuntimeStateSnapshot

from .event_bus import EventBus


class RuntimeKernel:
    def __init__(
        self,
        *,
        app_config: AppConfig | None = None,
        config_provider: AsyncConfigProvider | None = None,
        logger: AsyncJsonLogger | None = None,
        metrics: MetricsCollector | None = None,
        trace_provider: TraceProvider | None = None,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
        snapshot_store: SnapshotStore | None = None,
        state_store: RuntimeStateStore | None = None,
        event_log_directory: str | Path = "runtime_events",
        snapshot_directory: str | Path = "runtime_snapshots",
        default_exchange: str = "binance",
    ) -> None:
        self.app_config = app_config
        self.config_provider = config_provider or AsyncConfigProvider()
        self.logger = logger or get_logger("runtime_kernel")
        self.metrics = metrics or MetricsCollector()
        self.trace_provider = trace_provider or TraceProvider()

        self.event_bus = event_bus or EventBus()
        self._event_store_injected = event_store is not None
        self._snapshot_store_injected = snapshot_store is not None
        self._event_log_directory = event_log_directory
        self._snapshot_directory = snapshot_directory
        self.event_store = event_store or EventStore(
            log_directory=event_log_directory,
        )
        self.snapshot_store = snapshot_store or SnapshotStore(
            snapshot_directory=snapshot_directory,
        )
        self.state_store = state_store or RuntimeStateStore()
        self.replay_engine = ReplayEngine(
            event_store=self.event_store,
        )

        self.default_exchange = default_exchange
        self.exchange_adapters: dict[str, BaseExchangeAdapter] = {}
        self.oms: OrderManagementSystem | None = None
        self._bootstrapped = False
        self._logger_started = False
        self.service_wiring_map = MappingProxyType({})

    async def bootstrap(
        self,
        config_file_path: str | None = None,
    ) -> RuntimeStateSnapshot:
        if self._bootstrapped:
            return await self.state_store.snapshot()

        boot_started_ns = perf_counter_ns()

        await self.logger.start()
        self._logger_started = True

        with self.trace_provider.use() as trace:
            self.logger.info(
                "runtime bootstrap initialized",
                correlation_id=trace.correlation_id,
            )

            await self._load_config(config_file_path)
            self._configure_infrastructure_from_config()
            self._configure_services()

            snapshot = self.snapshot_store.load()

            if snapshot is not None:
                await self.state_store.hydrate(snapshot)

            await self.replay_engine.replay_after_sequence(
                sequence=snapshot.last_sequence if snapshot else None,
                store=self.state_store,
            )
            await self._register_infrastructure_consumers()
            await self._register_service_consumers()

            boot_duration_ms = (perf_counter_ns() - boot_started_ns) / 1_000_000
            self.metrics.record_histogram(
                "runtime_bootstrap_duration_ms",
                boot_duration_ms,
                {
                    "environment": self.app_config.environment
                    if self.app_config
                    else "unknown",
                },
            )
            self.logger.info(
                "runtime bootstrap completed",
                correlation_id=trace.correlation_id,
            )

        self._bootstrapped = True
        return await self.state_store.snapshot()

    async def publish(self, event: RuntimeEvent) -> None:
        if not self._bootstrapped:
            await self.bootstrap()

        await self.event_bus.publish(event)

    async def shutdown(self) -> RuntimeStateSnapshot:
        snapshot = await self.state_store.snapshot()
        self.snapshot_store.save(snapshot)
        await self.event_bus.close()

        if self._logger_started:
            self.logger.info("runtime shutdown completed")
            await self.logger.stop()
            self._logger_started = False

        self._bootstrapped = False
        return snapshot

    async def _load_config(
        self,
        config_file_path: str | None,
    ) -> None:
        if config_file_path is not None:
            self.app_config = await self.config_provider.load_config(
                config_file_path,
            )
            return

        if self.app_config is None:
            self.app_config = self._fallback_config()

    def _configure_infrastructure_from_config(self) -> None:
        if self.app_config is None:
            return

        base_dir = Path(self.app_config.persistence.base_dir)
        event_log_directory = base_dir / "runtime_events"
        snapshot_directory = base_dir / "runtime_snapshots"

        if not self._event_store_injected:
            self.event_store = EventStore(
                log_directory=event_log_directory,
                max_bytes=self.app_config.persistence.log_rotation_bytes,
            )

        if not self._snapshot_store_injected:
            self.snapshot_store = SnapshotStore(
                snapshot_directory=snapshot_directory,
            )

        self.replay_engine = ReplayEngine(
            event_store=self.event_store,
        )

    def _configure_services(self) -> None:
        rate_limiter = self._exchange_rate_limiter()
        self.exchange_adapters = {
            "binance": BinanceAdapter(
                event_bus=self.event_bus,
                rate_limiter=rate_limiter,
                logger=self.logger,
                metrics=self.metrics,
                trace_provider=self.trace_provider,
            ),
            "bybit": BybitAdapter(
                event_bus=self.event_bus,
                rate_limiter=rate_limiter,
                logger=self.logger,
                metrics=self.metrics,
                trace_provider=self.trace_provider,
            ),
            "bitunix": BitunixAdapter(
                event_bus=self.event_bus,
                rate_limiter=rate_limiter,
                logger=self.logger,
                metrics=self.metrics,
                trace_provider=self.trace_provider,
            ),
        }
        self.oms = OrderManagementSystem(
            event_bus=self.event_bus,
            exchange_adapters=self.exchange_adapters,
            default_exchange=self.default_exchange,
            logger=self.logger,
            metrics=self.metrics,
            trace_provider=self.trace_provider,
        )
        self.service_wiring_map = MappingProxyType(
            {
                "app_config": self.app_config,
                "logger": self.logger,
                "metrics": self.metrics,
                "trace_provider": self.trace_provider,
                "event_bus": self.event_bus,
                "event_store": self.event_store,
                "snapshot_store": self.snapshot_store,
                "state_store": self.state_store,
                "replay_engine": self.replay_engine,
                "exchange_adapters": MappingProxyType(
                    dict(self.exchange_adapters)
                ),
                "oms": self.oms,
            }
        )

    async def _register_infrastructure_consumers(self) -> None:
        await self.event_bus.subscribe_priority(
            RuntimeEvent,
            self._record_and_project_event,
        )

    async def _register_service_consumers(self) -> None:
        if self.oms is None:
            raise RuntimeError("OMS has not been configured")

        await self.oms.start()

    async def _record_and_project_event(self, event: RuntimeEvent) -> None:
        sequence = await self.event_store.append(event)
        await self.state_store.project(event, sequence=sequence)
        self.metrics.increment_counter(
            "runtime_events_projected",
            {"event_type": type(event).__name__},
        )

    def _exchange_rate_limiter(self) -> RateLimiter:
        if self.app_config is None:
            return RateLimiter()

        rate_limit_ms = max(1, self.app_config.exchange.rate_limit_ms)
        max_requests_per_minute = max(1, int(60_000 / rate_limit_ms))
        return RateLimiter(
            max_requests=max_requests_per_minute,
            window_seconds=60.0,
        )

    def _fallback_config(self) -> AppConfig:
        payload = {
            "environment": "local",
            "debug": False,
            "exchange": {
                "api_key": "",
                "secret_key": "",
                "rate_limit_ms": 100,
                "sandbox": True,
            },
            "persistence": {
                "log_rotation_bytes": 128 * 1024 * 1024,
                "snapshot_interval_seconds": 60,
                "base_dir": str(Path(self._event_log_directory).parent),
            },
            "risk": {
                "max_drawdown": 0.2,
                "max_position_size": 1.0,
                "blocked_assets": (),
            },
        }
        return msgspec.convert(payload, type=AppConfig, strict=True)
