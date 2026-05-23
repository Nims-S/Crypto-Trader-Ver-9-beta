"""Phase 4: Domain state models (immutable snapshots).

These are canonical domain contracts for state representation.
No business logic - pure data structures.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class OrderStatusDomain(str, Enum):
    """Canonical order status enum (domain-owned)."""
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    """Immutable order state snapshot.
    
    Created by RuntimeStateStore after processing events.
    Read-only interface for execution and risk layers.
    """
    internal_order_id: str
    exchange_order_id: str | None
    symbol: str
    side: str  # "BUY" or "SELL"
    order_type: str  # "LIMIT", "MARKET", etc.
    requested_price: float | None
    requested_quantity: float
    filled_quantity: float
    average_fill_price: float | None
    total_fee: float
    fee_asset: str | None
    status: OrderStatusDomain
    rejection_reason: str | None
    created_timestamp_ns: int
    updated_timestamp_ns: int


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    """Immutable balance state snapshot.
    
    Represents current asset holding and available margin.
    """
    asset: str
    available_balance: float
    equity_balance: float
    frozen_margin: float
    updated_timestamp_ns: int


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """Immutable position state snapshot.
    
    Represents current net position and entry cost for a symbol.
    """
    symbol: str
    net_quantity: float
    average_entry_price: float
    net_exposure: float
    open_risk: float
    updated_timestamp_ns: int


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Immutable portfolio state snapshot.
    
    Complete read-only view of portfolio state at a point in time.
    Used by risk engine, reconciliation, and other layers.
    """
    orders: Mapping[str, OrderSnapshot]
    balances: Mapping[str, BalanceSnapshot]
    positions: Mapping[str, PositionSnapshot]
    last_event_id: str | None
    last_timestamp_ns: int | None
    last_sequence: int | None = None
