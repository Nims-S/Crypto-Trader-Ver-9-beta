"""Order value objects and snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrderSide(str, Enum):
    """Order direction."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    """Order lifecycle status."""
    PENDING = "PENDING"  # submitted locally, awaiting acceptance
    ACCEPTED = "ACCEPTED"  # accepted by exchange
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    """Immutable snapshot of an order state."""
    internal_order_id: str
    strategy_id: str
    exchange: str
    exchange_order_id: str | None  # None if not yet accepted
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: float | None
    quantity: float
    cumulative_filled_quantity: float
    status: OrderStatus
    created_at: int  # ns since epoch
    updated_at: int  # ns since epoch
