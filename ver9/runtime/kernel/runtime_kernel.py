from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from ver9.events.base_event import RuntimeEvent
from ver9.execution.oms import OrderManagementSystem
from ver9.exchanges.base.adapter import BaseExchangeAdapter
from ver9.exchanges.binance.adapter import BinanceAdapter
from ver9.exchanges.bitunix.adapter import BitunixAdapter
from ver9.exchanges.bybit.adapter import BybitAdapter
from ver9.portfolio.allocation import PortfolioAllocator
from ver9.portfolio.risk import PortfolioRiskMonitor
from ver9.runtime.persistence.event_store import EventStore
from ver9.runtime.persistence.replay_engine import ReplayEngine
from ver9.runtime.persistence.snapshot_store import SnapshotStore
from ver9.runtime.state.runtime_state_store import RuntimeStateStore
from ver9.runtime.state.state_models import RuntimeStateSnapshot

from .event_bus import EventBus


class RuntimeKernel:
    def __init__(
        self,
        *,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
        snapshot_store: SnapshotStore | None = None,
        state_store: RuntimeStateStore | None = None,
        event_log_directory: str | Path = "runtime_events",
        snapshot_directory: str | Path = "runtime_snapshots",
        default_exchange: str = "binance",
    ) -> None:
        self.event_bus = event_bus or EventBus()
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
        self.exchange_adapters: dict[str, BaseExchangeAdapter] = {
            "binance": BinanceAdapter(event_bus=self.event_bus),
            "bybit": BybitAdapter(event_bus=self.event_bus),
            "bitunix": BitunixAdapter(event_bus=self.event_bus),
        }
        self.oms = OrderManagementSystem(
            event_bus=self.event_bus,
            exchange_adapters=self.exchange_adapters,
            default_exchange=default_exchange,
        )
        self.portfolio_allocator = PortfolioAllocator(
            event_bus=self.event_bus,
        )
        self.portfolio_risk_monitor = PortfolioRiskMonitor(
            event_bus=self.event_bus,
        )
        self.service_wiring_map = MappingProxyType(
            {
                "event_bus": self.event_bus,
                "event_store": self.event_store,
                "snapshot_store": self.snapshot_store,
                "state_store": self.state_store,
                "replay_engine": self.replay_engine,
                "exchange_adapters": MappingProxyType(
                    dict(self.exchange_adapters)
                ),
                "oms": self.oms,
                "portfolio_allocator": self.portfolio_allocator,
                "portfolio_risk_monitor": self.portfolio_risk_monitor,
            }
        )
        self._bootstrapped = False

    async def bootstrap(self) -> RuntimeStateSnapshot:
        if self._bootstrapped:
            return await self.state_store.snapshot()

        snapshot = self.snapshot_store.load()

        if snapshot is not None:
            await self.state_store.hydrate(snapshot)

        await self.replay_engine.replay_after_sequence(
            sequence=snapshot.last_sequence if snapshot else None,
            store=self.state_store,
        )
        await self._register_infrastructure_consumers()
        await self._register_service_consumers()

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
        self._bootstrapped = False
        return snapshot

    async def _register_infrastructure_consumers(self) -> None:
        await self.event_bus.subscribe_priority(
            RuntimeEvent,
            self._record_and_project_event,
        )

    async def _register_service_consumers(self) -> None:
        await self.oms.start()

    async def _record_and_project_event(self, event: RuntimeEvent) -> None:
        sequence = await self.event_store.append(event)
        await self.state_store.project(event, sequence=sequence)
