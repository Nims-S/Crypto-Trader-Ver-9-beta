from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from time import time_ns
from uuid import uuid4

from ver9.events.base_event import RuntimeEvent
from ver9.exchanges.base.adapter import BaseExchangeAdapter
from ver9.observability.logging import AsyncJsonLogger
from ver9.observability.metrics import MetricsCollector
from ver9.runtime.kernel.event_bus import EventBus


@dataclass(frozen=True, slots=True)
class ReconciliationCorrectionRequested(RuntimeEvent):
    exchange: str
    symbol: str
    local_value: float
    exchange_value: float
    delta: float
    reason: str


class ExchangePortfolioReconciler:
    """
    Distributed reconciliation engine.

    Performs continuous asynchronous reconciliation between
    authoritative RuntimeStateStore snapshots and live
    exchange portfolio state.

    This engine never mutates state directly.
    All corrections are enforced exclusively through
    EventBus domain events.
    """

    def __init__(
        self,
        *,
        event_bus: EventBus,
        runtime_state_store,
        app_config,
        exchange_adapters: Mapping[str, BaseExchangeAdapter],
        metrics: MetricsCollector,
        logger: AsyncJsonLogger | None = None,
        replay_engine=None,
    ) -> None:
        self._event_bus = event_bus
        self._runtime_state_store = runtime_state_store
        self._app_config = app_config
        self._exchange_adapters = exchange_adapters
        self._metrics = metrics
        self._logger = logger
        self._replay_engine = replay_engine

        self._trading_paused = False
        self._variance_threshold = 1e-8

    async def run_continuous_audit(
        self,
        interval_seconds: int = 60,
    ) -> None:
        while True:
            try:
                local_snapshot = (
                    self._runtime_state_store.snapshot()
                )

                audit_tasks = [
                    self._audit_exchange(
                        exchange_name,
                        adapter,
                        local_snapshot,
                    )
                    for exchange_name, adapter in self._exchange_adapters.items()
                ]

                await asyncio.gather(*audit_tasks)

            except Exception as exc:
                if self._logger is not None:
                    await self._logger.error(
                        "reconciliation_audit_failure",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )

            await asyncio.sleep(interval_seconds)

    async def _audit_exchange(
        self,
        exchange_name: str,
        adapter: BaseExchangeAdapter,
        local_snapshot,
    ) -> None:
        exchange_state = await adapter.fetch_account_snapshot()

        positions = exchange_state.positions

        for symbol, exchange_position in positions.items():
            local_position = float(
                local_snapshot.get_position_size(symbol)
            )

            exchange_quantity = float(
                exchange_position.quantity
            )

            variance = abs(
                local_position - exchange_quantity
            )

            if variance > self._variance_threshold:
                correlation_id = str(uuid4())

                self._metrics.increment_counter(
                    "reconciliation_position_drift_total",
                    {
                        "exchange": exchange_name,
                        "symbol": symbol,
                    },
                )

                if self._logger is not None:
                    await self._logger.critical(
                        "portfolio_reconciliation_position_drift",
                        correlation_id=correlation_id,
                        exchange=exchange_name,
                        symbol=symbol,
                        local_position=local_position,
                        exchange_position=exchange_quantity,
                        variance=variance,
                    )

                await self._event_bus.publish(
                    ReconciliationCorrectionRequested(
                        event_id=str(uuid4()),
                        timestamp_ns=time_ns(),
                        correlation_id=correlation_id,
                        exchange=exchange_name,
                        symbol=symbol,
                        local_value=local_position,
                        exchange_value=exchange_quantity,
                        delta=variance,
                        reason="position_drift_detected",
                    )
                )

        balances = exchange_state.balances

        for asset, exchange_balance in balances.items():
            local_balance = float(
                local_snapshot.get_balance(asset)
            )

            exchange_value = float(exchange_balance.total)

            variance = abs(local_balance - exchange_value)

            if variance > self._variance_threshold:
                correlation_id = str(uuid4())

                self._metrics.increment_counter(
                    "reconciliation_balance_drift_total",
                    {
                        "exchange": exchange_name,
                        "asset": asset,
                    },
                )

                if self._logger is not None:
                    await self._logger.critical(
                        "portfolio_reconciliation_balance_drift",
                        correlation_id=correlation_id,
                        exchange=exchange_name,
                        asset=asset,
                        local_balance=local_balance,
                        exchange_balance=exchange_value,
                        variance=variance,
                    )

                await self._event_bus.publish(
                    ReconciliationCorrectionRequested(
                        event_id=str(uuid4()),
                        timestamp_ns=time_ns(),
                        correlation_id=correlation_id,
                        exchange=exchange_name,
                        symbol=asset,
                        local_value=local_balance,
                        exchange_value=exchange_value,
                        delta=variance,
                        reason="balance_drift_detected",
                    )
                )

    async def verify_sequence_continuity(
        self,
        exchange: str,
        expected_sequence: int,
        received_sequence: int,
    ) -> bool:
        if expected_sequence == received_sequence:
            return True

        self._trading_paused = True

        correlation_id = str(uuid4())

        self._metrics.increment_counter(
            "reconciliation_sequence_gap_total",
            {"exchange": exchange},
        )

        if self._logger is not None:
            await self._logger.critical(
                "exchange_sequence_gap_detected",
                correlation_id=correlation_id,
                exchange=exchange,
                expected_sequence=expected_sequence,
                received_sequence=received_sequence,
            )

        await self._event_bus.publish(
            ReconciliationCorrectionRequested(
                event_id=str(uuid4()),
                timestamp_ns=time_ns(),
                correlation_id=correlation_id,
                exchange=exchange,
                symbol="SEQUENCE",
                local_value=float(expected_sequence),
                exchange_value=float(received_sequence),
                delta=float(
                    abs(expected_sequence - received_sequence)
                ),
                reason="sequence_gap_detected",
            )
        )

        if self._replay_engine is not None:
            await self._replay_engine.recover_missing_events(
                exchange=exchange,
                expected_sequence=expected_sequence,
                received_sequence=received_sequence,
            )

        return False
