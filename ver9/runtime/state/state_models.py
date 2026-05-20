from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class OrderStatus(str, Enum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class OrderState:
    order_id: str
    symbol: str
    side: str
    order_type: str
    requested_price: float | None
    requested_quantity: float
    status: OrderStatus
    created_timestamp_ns: int
    updated_timestamp_ns: int
    exchange_order_id: str | None = None
    filled_quantity: float = 0.0
    average_fill_price: float | None = None
    total_fee: float = 0.0
    fee_asset: str | None = None
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class BalanceState:
    asset: str
    available_balance: float
    equity_balance: float
    frozen_margin: float
    updated_timestamp_ns: int


@dataclass(frozen=True, slots=True)
class PositionState:
    symbol: str
    net_quantity: float
    average_entry_price: float
    net_exposure: float
    open_risk: float
    updated_timestamp_ns: int


@dataclass(frozen=True, slots=True)
class RuntimeStateSnapshot:
    orders: Mapping[str, OrderState]
    balances: Mapping[str, BalanceState]
    positions: Mapping[str, PositionState]
    last_event_id: str | None
    last_timestamp_ns: int | None
    last_sequence: int | None = None
