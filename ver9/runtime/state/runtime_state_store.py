from __future__ import annotations

import asyncio
from dataclasses import replace
from types import MappingProxyType

from ver9.events.base_event import RuntimeEvent
from ver9.events_execution_events import FillReceived
from ver9.events_execution_events import OrderAccepted
from ver9.events_execution_events import OrderRejected
from ver9.events_execution_events import OrderSubmitted
from ver9.events.portfolio_events import ReconciliationCorrectionRequested

from .state_models import BalanceState
from .state_models import OrderState
from .state_models import OrderStatus
from .state_models import PositionState
from .state_models import RuntimeStateSnapshot


class StateProjectionError(RuntimeError):
    pass


class RuntimeStateStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._orders: dict[str, OrderState] = {}
        self._balances: dict[str, BalanceState] = {}
        self._positions: dict[str, PositionState] = {}
        self._last_event_id: str | None = None
        self._last_timestamp_ns: int | None = None
        self._last_sequence: int | None = None

    @property
    def orders(self):
        return MappingProxyType(dict(self._orders))

    @property
    def balances(self):
        return MappingProxyType(dict(self._balances))

    @property
    def positions(self):
        return MappingProxyType(dict(self._positions))

    async def snapshot(self) -> RuntimeStateSnapshot:
        async with self._lock:
            return RuntimeStateSnapshot(
                orders=MappingProxyType(dict(self._orders)),
                balances=MappingProxyType(dict(self._balances)),
                positions=MappingProxyType(dict(self._positions)),
                last_event_id=self._last_event_id,
                last_timestamp_ns=self._last_timestamp_ns,
                last_sequence=self._last_sequence,
            )

    async def hydrate(self, snapshot: RuntimeStateSnapshot) -> None:
        async with self._lock:
            self._orders = dict(snapshot.orders)
            self._balances = dict(snapshot.balances)
            self._positions = dict(snapshot.positions)
            self._last_event_id = snapshot.last_event_id
            self._last_timestamp_ns = snapshot.last_timestamp_ns
            self._last_sequence = snapshot.last_sequence

    async def get_order(self, order_id: str) -> OrderState | None:
        async with self._lock:
            order = self._orders.get(order_id)
            return replace(order) if order is not None else None

    async def get_balance(self, asset: str) -> BalanceState | None:
        async with self._lock:
            balance = self._balances.get(asset)
            return replace(balance) if balance is not None else None

    async def get_position(self, symbol: str) -> PositionState | None:
        async with self._lock:
            position = self._positions.get(symbol)
            return replace(position) if position is not None else None

    async def project(
        self,
        event: RuntimeEvent,
        *,
        sequence: int | None = None,
    ) -> RuntimeStateSnapshot:
        async with self._lock:
            if isinstance(event, OrderSubmitted):
                self._project_order_submitted(event)
            elif isinstance(event, OrderAccepted):
                self._project_order_accepted(event)
            elif isinstance(event, FillReceived):
                self._project_fill_received(event)
            elif isinstance(event, OrderRejected):
                self._project_order_rejected(event)
            elif isinstance(event, ReconciliationCorrectionRequested):
                self._project_reconciliation_correction(event)

            self._last_event_id = event.event_id
            self._last_timestamp_ns = event.timestamp_ns
            self._last_sequence = sequence

            return RuntimeStateSnapshot(
                orders=MappingProxyType(dict(self._orders)),
                balances=MappingProxyType(dict(self._balances)),
                positions=MappingProxyType(dict(self._positions)),
                last_event_id=self._last_event_id,
                last_timestamp_ns=self._last_timestamp_ns,
                last_sequence=self._last_sequence,
            )

    def _project_order_submitted(self, event: OrderSubmitted) -> None:
        self._orders[event.order_id] = OrderState(
            order_id=event.order_id,
            symbol=event.symbol,
            side=event.side,
            order_type=event.order_type,
            requested_price=event.price,
            requested_quantity=event.quantity,
            status=OrderStatus.SUBMITTED,
            created_timestamp_ns=event.timestamp_ns,
            updated_timestamp_ns=event.timestamp_ns,
        )

    def _project_order_accepted(self, event: OrderAccepted) -> None:
        order = self._require_order(event.order_id)

        self._orders[event.order_id] = replace(
            order,
            status=OrderStatus.ACCEPTED,
            exchange_order_id=event.exchange_order_id,
            updated_timestamp_ns=event.timestamp_ns,
        )

    def _project_fill_received(self, event: FillReceived) -> None:
        order = self._require_order(event.order_id)

        previous_filled_value = (
            (order.average_fill_price or 0.0) * order.filled_quantity
        )
        new_filled_quantity = order.filled_quantity + event.quantity
        new_average_price = (
            (previous_filled_value + (event.price * event.quantity))
            / new_filled_quantity
            if new_filled_quantity
            else None
        )

        status = (
            OrderStatus.FILLED
            if new_filled_quantity >= order.requested_quantity
            else OrderStatus.PARTIALLY_FILLED
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

    def _project_order_rejected(self, event: OrderRejected) -> None:
        order = self._require_order(event.order_id)

        self._orders[event.order_id] = replace(
            order,
            status=OrderStatus.REJECTED,
            rejection_reason=event.reason,
            updated_timestamp_ns=event.timestamp_ns,
        )

    def _project_reconciliation_correction(
        self,
        event: ReconciliationCorrectionRequested,
    ) -> None:
        previous = self._balances.get(event.asset)
        frozen_margin = previous.frozen_margin if previous else 0.0

        self._balances[event.asset] = BalanceState(
            asset=event.asset,
            available_balance=event.actual_balance,
            equity_balance=event.actual_balance,
            frozen_margin=frozen_margin,
            updated_timestamp_ns=event.timestamp_ns,
        )

    def _apply_fill_to_position(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        timestamp_ns: int,
    ) -> None:
        signed_quantity = quantity if side == "buy" else -quantity
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

        self._positions[symbol] = PositionState(
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
        if fee == 0.0:
            return

        previous = self._balances.get(asset)

        if previous is None:
            self._balances[asset] = BalanceState(
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

    def _require_order(self, order_id: str) -> OrderState:
        order = self._orders.get(order_id)

        if order is None:
            raise StateProjectionError(
                f"event references unknown order_id: {order_id}"
            )

        return order
