from __future__ import annotations

from dataclasses import dataclass
from time import time_ns
from uuid import uuid4

from ver9.events.base_event import RuntimeEvent
from ver9.events.execution_events import FillReceived
from ver9.events.execution_events import OrderRejected
from ver9.events.execution_events import OrderSubmitted
from ver9.observability.logging import AsyncJsonLogger
from ver9.observability.metrics import MetricsCollector
from ver9.runtime.kernel.event_bus import EventBus


@dataclass(frozen=True, slots=True)
class RiskConfig:
    max_position_size: float
    max_drawdown: float
    blocked_assets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RiskBreachDetected(RuntimeEvent):
    reason: str
    symbol: str
    expected_position: float
    actual_position: float


class PortfolioRiskManager:
    """
    Stateless portfolio risk engine.

    All evaluations derive from authoritative
    RuntimeStateStore snapshots.

    No direct mutation of balances, positions,
    or runtime state is permitted.
    """

    def __init__(
        self,
        *,
        event_bus: EventBus,
        runtime_state_store,
        metrics: MetricsCollector,
        risk_config: RiskConfig,
        logger: AsyncJsonLogger | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._runtime_state_store = runtime_state_store
        self._metrics = metrics
        self._risk_config = risk_config
        self._logger = logger

        self._emergency_block_active = False

    async def start(self) -> None:
        await self._event_bus.subscribe(
            FillReceived,
            self._handle_fill_received,
        )

        await self._event_bus.subscribe(
            OrderRejected,
            self._handle_order_rejected,
        )

        await self._event_bus.subscribe(
            RiskBreachDetected,
            self._handle_risk_breach,
        )

    async def evaluate_order_risk(
        self,
        order: OrderSubmitted,
    ) -> bool:
        """
        Stateless pre-trade risk evaluation.
        """

        if self._emergency_block_active:
            await self._publish_risk_breach(
                correlation_id=order.correlation_id,
                symbol=order.symbol,
                reason="emergency_risk_lockdown_active",
                expected_position=0.0,
                actual_position=0.0,
            )
            return False

        if order.symbol in self._risk_config.blocked_assets:
            await self._publish_risk_breach(
                correlation_id=order.correlation_id,
                symbol=order.symbol,
                reason="blocked_asset",
                expected_position=0.0,
                actual_position=0.0,
            )
            return False

        current_position = float(
            self._runtime_state_store.get_position_size(
                order.symbol,
            )
        )

        projected_position = (
            current_position + float(order.quantity)
        )

        if (
            abs(projected_position)
            > self._risk_config.max_position_size
        ):
            await self._publish_risk_breach(
                correlation_id=order.correlation_id,
                symbol=order.symbol,
                reason="max_position_size_exceeded",
                expected_position=current_position,
                actual_position=projected_position,
            )
            return False

        current_equity = float(
            self._runtime_state_store.get_total_equity(),
        )

        peak_equity = float(
            self._runtime_state_store.get_peak_equity(),
        )

        drawdown = (
            (peak_equity - current_equity) / peak_equity
            if peak_equity > 0.0
            else 0.0
        )

        if drawdown >= self._risk_config.max_drawdown:
            await self._publish_risk_breach(
                correlation_id=order.correlation_id,
                symbol=order.symbol,
                reason="max_drawdown_exceeded",
                expected_position=current_position,
                actual_position=current_position,
            )
            return False

        return True

    async def _handle_fill_received(
        self,
        event: RuntimeEvent,
    ) -> None:
        if not isinstance(event, FillReceived):
            return

        expected_position = float(
            self._runtime_state_store.get_expected_position_size(
                event.order_id,
            )
        )

        actual_position = float(
            self._runtime_state_store.get_position_size_for_order(
                event.order_id,
            )
        )

        drift = abs(expected_position - actual_position)

        if drift > 1e-9:
            await self._publish_risk_breach(
                correlation_id=event.correlation_id,
                symbol=self._runtime_state_store.get_order_symbol(
                    event.order_id,
                ),
                reason="position_state_drift_detected",
                expected_position=expected_position,
                actual_position=actual_position,
            )

    async def _handle_order_rejected(
        self,
        event: RuntimeEvent,
    ) -> None:
        if not isinstance(event, OrderRejected):
            return

        self._metrics.increment_counter(
            "risk_order_rejections_total",
            {"reason": event.reason},
        )

    async def _handle_risk_breach(
        self,
        event: RuntimeEvent,
    ) -> None:
        if not isinstance(event, RiskBreachDetected):
            return

        self._emergency_block_active = True

        self._metrics.increment_counter(
            "risk_breach_detected_total",
            {"symbol": event.symbol},
        )

        if self._logger is not None:
            await self._logger.critical(
                "portfolio_risk_breach_detected",
                correlation_id=event.correlation_id,
                symbol=event.symbol,
                reason=event.reason,
                expected_position=event.expected_position,
                actual_position=event.actual_position,
            )

    async def _publish_risk_breach(
        self,
        *,
        correlation_id: str,
        symbol: str,
        reason: str,
        expected_position: float,
        actual_position: float,
    ) -> None:
        await self._event_bus.publish(
            RiskBreachDetected(
                event_id=str(uuid4()),
                timestamp_ns=time_ns(),
                correlation_id=correlation_id,
                reason=reason,
                symbol=symbol,
                expected_position=expected_position,
                actual_position=actual_position,
            )
        )
