from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ver9.domain.events.runtime import RuntimeEvent


@dataclass(frozen=True, slots=True)
class OrderSubmitted(RuntimeEvent):
    internal_order_id: str
    strategy_id: str
    exchange: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None
    time_in_force: str | None
    position_side: str = "BOTH"
    reduce_only: bool = False


@dataclass(frozen=True, slots=True)
class OrderAccepted(RuntimeEvent):
    internal_order_id: str
    exchange_order_id: str
    strategy_id: str
    exchange: str
    symbol: str
    accepted_price: float


@dataclass(frozen=True, slots=True)
class OrderRejected(RuntimeEvent):
    internal_order_id: str
    strategy_id: str
    exchange: str
    symbol: str
    rejection_reason: str


@dataclass(frozen=True, slots=True)
class FillReceived(RuntimeEvent):
    internal_order_id: str
    exchange_order_id: str
    strategy_id: str
    exchange: str
    symbol: str
    fill_price: float
    fill_quantity: float
    fill_fee: float
    liquidity_side: str
