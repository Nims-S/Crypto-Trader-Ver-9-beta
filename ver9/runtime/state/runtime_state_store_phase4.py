"""Phase 4: RuntimeStateStore - Domain Event Projection.

Core responsibilities:
1. Consume domain events and legacy events (dual-stack during migration)
2. Project state into canonical domain snapshots
3. Expose read-only RuntimeStateView interface
4. Maintain idempotency and deterministic replay

Dependencies:
- Domain events (ver9.domain.events.*)
- Legacy events (ver9.events.*) - for backward compatibility only
- Domain models (ver9.domain.models.state)
- RuntimeStateView interface (ver9.interfaces.state.runtime_state_view)

NO dependencies on:
- Execution layer (OMS, risk, routing)
- Exchanges
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING

from ver9.domain.events.execution import (
    OrderSubmittedDomain,
    OrderAcceptedDomain,
    OrderRejectedDomain,
    FillReceivedDomain,
)
from ver9.domain.models.state import (
    BalanceSnapshot,
    OrderSnapshot,
    OrderStatusDomain,
    PortfolioSnapshot,
    PositionSnapshot,
)
from ver9.events.base_event import RuntimeEvent
from ver9.events.execution_events import (
    FillReceived as LegacyFillReceived,
    OrderAccepted as LegacyOrderAccepted,
    OrderRejected as LegacyOrderRejected,
    OrderSubmitted as LegacyOrderSubmitted,
)
from ver9.events.portfolio_events import ReconciliationCorrectionRequested

if TYPE_CHECKING:
    from ver9.interfaces.state.runtime_state_view import RuntimeStateView


class StateProjectionError(RuntimeError):
    """Raised when event references unknown order or invalid state transition."""
    pass


class RuntimeStateStorePhase4:
    """State store with domain event projection and canonical snapshots.
    
    Responsibilities:
    - Accept both domain and legacy events (dual-stack)
    - Project into immutable domain snapshots
    - Implement RuntimeStateView interface
    - Enable deterministic replay
    
    Thread-safe via async lock.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # Internal mutable state during projection
        self._orders: dict[str, OrderSnapshot] = {}
        self._balances: dict[str, BalanceSnapshot] = {}
        self._positions: dict[str, PositionSnapshot] = {}
        self._last_event_id: str | None = None
        self._last_timestamp_ns: int | None = None
        self._last_sequence: int | None = None

    # ========================================================================
    # RuntimeStateView Implementation (read-only interface)
    # ========================================================================

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Get immutable portfolio snapshot (synchronous read)."""
        return PortfolioSnapshot(
            orders=MappingProxyType(dict(self._orders)),
            balances=MappingProxyType(dict(self._balances)),
            positions=MappingProxyType(dict(self._positions)),
            last_event_id=self._last_event_id,
            last_timestamp_ns=self._last_timestamp_ns,
            last_sequence=self._last_sequence,
        )

    def get_order_snapshot(self, internal_order_id: str) -> OrderSnapshot | None:
        """Get specific order snapshot or None."""
        return self._orders.get(internal_order_id)

    def get_all_orders(self) -> list[OrderSnapshot]:
        """Get all orders as list."""
        return list(self._orders.values())

    # ========================================================================
    # Persistence Operations
    # ========================================================================

    async def snapshot(self) -> PortfolioSnapshot:
        """Get current state as immutable snapshot (async)."""
        async with self._lock:
            return self.get_portfolio_snapshot()

    async def hydrate(self, snapshot: PortfolioSnapshot) -> None:
        """Restore state from snapshot (for recovery)."""
        async with self._lock:
            self._orders = dict(snapshot.orders)
            self._balances = dict(snapshot.balances)
            self._positions = dict(snapshot.positions)
            self._last_event_id = snapshot.last_event_id
            self._last_timestamp_ns = snapshot.last_timestamp_ns
            self._last_sequence = snapshot.last_sequence

    # ========================================================================
    # Event Projection (Dual-Stack)
    # ========================================================================

    async def project(
        self,
        event: RuntimeEvent,
        *,
        sequence: int | None = None,
    ) -> PortfolioSnapshot:
        """Project event into state and return new snapshot.
        
        Handles BOTH domain and legacy events (for backward compatibility).
        """
        async with self._lock:
            # Domain events (canonical)
            if isinstance(event, OrderSubmittedDomain):
                self._project_order_submitted_domain(event)
            elif isinstance(event, OrderAcceptedDomain):
                self._project_order_accepted_domain(event)
            elif isinstance(event, FillReceivedDomain):
                self._project_fill_received_domain(event)
            elif isinstance(event, OrderRejectedDomain):
                self._project_order_rejected_domain(event)
            # Legacy events (for migration compatibility)
            elif isinstance(event, LegacyOrderSubmitted):
                self._project_legacy_order_submitted(event)
            elif isinstance(event, LegacyOrderAccepted):
                self._project_legacy_order_accepted(event)
            elif isinstance(event, LegacyFillReceived):
                self._project_legacy_fill_received(event)
            elif isinstance(event, LegacyOrderRejected):
                self._project_legacy_order_rejected(event)
            elif isinstance(event, ReconciliationCorrectionRequested):
                self._project_reconciliation_correction(event)

            self._last_event_id = event.event_id
            self._last_timestamp_ns = event.timestamp_ns
            self._last_sequence = sequence

            return self.get_portfolio_snapshot()

    # ========================================================================
    # Domain Event Projection
    # ========================================================================

    def _project_order_submitted_domain(self, event: OrderSubmittedDomain) -> None:
        """Project OrderSubmittedDomain."""
        self._orders[event.internal_order_id] = OrderSnapshot(
            internal_order_id=event.internal_order_id,
            exchange_order_id=None,
            symbol=event.symbol,
            side=event.side,
            order_type=event.order_type,
            requested_price=event.price,
            requested_quantity=event.quantity,
            filled_quantity=0.0,
            average_fill_price=None,
            total_fee=0.0,
            fee_asset=None,
            status=OrderStatusDomain.SUBMITTED,
            rejection_reason=None,
            created_timestamp_ns=event.timestamp,
            updated_timestamp_ns=event.timestamp,
        )

    def _project_order_accepted_domain(self, event: OrderAcceptedDomain) -> None:
        """Project OrderAcceptedDomain."""
        order = self._require_order(event.internal_order_id)
        self._orders[event.internal_order_id] = replace(
            order,
            status=OrderStatusDomain.ACCEPTED,
            exchange_order_id=event.exchange_order_id,
            updated_timestamp_ns=event.timestamp,
        )

    def _project_fill_received_domain(self, event: FillReceivedDomain) -> None:
        """Project FillReceivedDomain."""
        order = self._require_order(event.internal_order_id)

        previous_filled_value = (order.average_fill_price or 0.0) * order.filled_quantity
        new_filled_quantity = order.filled_quantity + event.quantity
        new_average_price = (
            (previous_filled_value + (event.price * event.quantity))
            / new_filled_quantity
            if new_filled_quantity
            else None
        )

        status = (
            OrderStatusDomain.FILLED
            if new_filled_quantity >= order.requested_quantity
            else OrderStatusDomain.PARTIALLY_FILLED
        )

        self._orders[event.internal_order_id] = replace(
            order,
            status=status,
            filled_quantity=new_filled_quantity,
            average_fill_price=new_average_price,
            total_fee=order.total_fee + event.fee,
            fee_asset=event.fee_asset,
            updated_timestamp_ns=event.timestamp,
        )

        self._apply_fill_to_position(
            symbol=order.symbol,
            side=order.side,
            price=event.price,
            quantity=event.quantity,
            timestamp_ns=event.timestamp,
        )
        self._apply_fee(
            asset=event.fee_asset,
            fee=event.fee,
            timestamp_ns=event.timestamp,
        )

    def _project_order_rejected_domain(self, event: OrderRejectedDomain) -> None:
        """Project OrderRejectedDomain."""
        order = self._require_order(event.internal_order_id)
        self._orders[event.internal_order_id] = replace(
            order,
            status=OrderStatusDomain.REJECTED,
            rejection_reason=event.reason,
            updated_timestamp_ns=event.timestamp,
        )

    # ========================================================================
    # Legacy Event Projection (Backward Compatibility)
    # ========================================================================

    def _project_legacy_order_submitted(self, event: LegacyOrderSubmitted) -> None:
        """Project legacy OrderSubmitted as domain."""
        self._orders[event.order_id] = OrderSnapshot(
            internal_order_id=event.order_id,
            exchange_order_id=None,
            symbol=event.symbol,
            side=event.side,
            order_type=event.order_type,
            requested_price=event.price,
            requested_quantity=event.quantity,
            filled_quantity=0.0,
            average_fill_price=None,
            total_fee=0.0,
            fee_asset=None,
            status=OrderStatusDomain.SUBMITTED,
            rejection_reason=None,
            created_timestamp_ns=event.timestamp_ns,
            updated_timestamp_ns=event.timestamp_ns,
        )

    def _project_legacy_order_accepted(self, event: LegacyOrderAccepted) -> None:
        """Project legacy OrderAccepted as domain."""
        order = self._require_order(event.order_id)
        self._orders[event.order_id] = replace(
            order,
            status=OrderStatusDomain.ACCEPTED,
            exchange_order_id=event.exchange_order_id,
            updated_timestamp_ns=event.timestamp_ns,
        )

    def _project_legacy_fill_received(self, event: LegacyFillReceived) -> None:
        """Project legacy FillReceived as domain."""
        order = self._require_order(event.order_id)

        previous_filled_value = (order.average_fill_price or 0.0) * order.filled_quantity
        new_filled_quantity = order.filled_quantity + event.quantity
        new_average_price = (
            (previous_filled_value + (event.price * event.quantity))
            / new_filled_quantity
            if new_filled_quantity
            else None
        )

        status = (
            OrderStatusDomain.FILLED
            if new_filled_quantity >= order.requested_quantity
            else OrderStatusDomain.PARTIALLY_FILLED
        )

        self._orders[event.order_id] = replace(
            order,
            status=status,
            filled_quantity=new_filled_quantity,
            average_fill_price=new_average_price,
            total_fee=order.total_fee + event.fee,
            fee_asset=event.fee_asset,
            updated_timestamp_ns=event.timestamp_ns,
        )

        self._apply_fill_to_position(
            symbol=order.symbol,
            side=order.side,
            price=event.price,
            quantity=event.quantity,
            timestamp_ns=event.timestamp_ns,
        )
        self._apply_fee(
            asset=event.fee_asset,
            fee=event.fee,
            timestamp_ns=event.timestamp_ns,
        )

    def _project_legacy_order_rejected(self, event: LegacyOrderRejected) -> None:
        """Project legacy OrderRejected as domain."""
        order = self._require_order(event.order_id)
        self._orders[event.order_id] = replace(
            order,
            status=OrderStatusDomain.REJECTED,
            rejection_reason=event.reason,
            updated_timestamp_ns=event.timestamp_ns,
        )

    def _project_reconciliation_correction(
        self,
        event: ReconciliationCorrectionRequested,
    ) -> None:
        """Project reconciliation correction."""
        previous = self._balances.get(event.asset)
        frozen_margin = previous.frozen_margin if previous else 0.0
        self._balances[event.asset] = BalanceSnapshot(
            asset=event.asset,
            available_balance=event.actual_balance,
            equity_balance=event.actual_balance,
            frozen_margin=frozen_margin,
            updated_timestamp_ns=event.timestamp_ns,
        )

    # ========================================================================
    # Position & Balance Helpers
    # ========================================================================

    def _apply_fill_to_position(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        timestamp_ns: int,
    ) -> None:
        """Update position after fill."""
        signed_quantity = quantity if side.upper() == "BUY" else -quantity
        existing = self._positions.get(symbol)

        if existing is None:
            net_quantity = signed_quantity
            average_entry_price = price if net_quantity else 0.0
        else:
            previous_quantity = existing.net_quantity
            net_quantity = previous_quantity + signed_quantity

            if net_quantity == 0.0:
                average_entry_price = 0.0
            elif previous_quantity == 0.0:
                average_entry_price = price
            elif (previous_quantity > 0) == (signed_quantity > 0):
                average_entry_price = (
                    (abs(previous_quantity) * existing.average_entry_price)
                    + (abs(signed_quantity) * price)
                ) / abs(net_quantity)
            elif abs(signed_quantity) > abs(previous_quantity):
                average_entry_price = price
            else:
                average_entry_price = existing.average_entry_price

        net_exposure = net_quantity * average_entry_price
        self._positions[symbol] = PositionSnapshot(
            symbol=symbol,
            net_quantity=net_quantity,
            average_entry_price=average_entry_price,
            net_exposure=net_exposure,
            open_risk=abs(net_exposure),
            updated_timestamp_ns=timestamp_ns,
        )

    def _apply_fee(
        self,
        *,
        asset: str,
        fee: float,
        timestamp_ns: int,
    ) -> None:
        """Apply fee to balance."""
        if fee == 0.0:
            return

        previous = self._balances.get(asset)
        if previous is None:
            self._balances[asset] = BalanceSnapshot(
                asset=asset,
                available_balance=-fee,
                equity_balance=-fee,
                frozen_margin=0.0,
                updated_timestamp_ns=timestamp_ns,
            )
            return

        self._balances[asset] = replace(
            previous,
            available_balance=previous.available_balance - fee,
            equity_balance=previous.equity_balance - fee,
            updated_timestamp_ns=timestamp_ns,
        )

    def _require_order(self, order_id: str) -> OrderSnapshot:
        """Get order or raise error."""
        order = self._orders.get(order_id)
        if order is None:
            raise StateProjectionError(f"event references unknown order_id: {order_id}")
        return order
