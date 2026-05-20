from __future__ import annotations

from dataclasses import dataclass

from .base_event import RuntimeEvent


@dataclass(frozen=True, slots=True)
class OrderSubmitted(RuntimeEvent):
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: float | None
    quantity: float


@dataclass(frozen=True, slots=True)
class OrderAccepted(RuntimeEvent):
    order_id: str
    exchange_order_id: str


@dataclass(frozen=True, slots=True)
class FillReceived(RuntimeEvent):
    order_id: str
    fill_id: str
    price: float
    quantity: float
    fee: float
    fee_asset: str


@dataclass(frozen=True, slots=True)
class OrderRejected(RuntimeEvent):
    order_id: str
    reason: str
