"""Canonical execution domain events.

These are immutable dataclasses that represent the canonical schema for all
execution-related events. They include full context (internal_order_id,
strategy_id, exchange, etc.) and use standard types.

MUST NOT import runtime, execution, or exchange modules.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrderSubmittedDomain:
    """Order was submitted to exchange.
    
    Canonical schema includes internal tracking fields.
    """
    internal_order_id: str
    strategy_id: str
    exchange: str
    symbol: str
    side: str  # "BUY" or "SELL"
    order_type: str  # "LIMIT", "MARKET", etc.
    price: float | None
    quantity: float
    timestamp: int  # nanoseconds since epoch


@dataclass(frozen=True, slots=True)
class OrderAcceptedDomain:
    """Order was accepted by exchange."""
    internal_order_id: str
    exchange_order_id: str
    exchange: str
    timestamp: int


@dataclass(frozen=True, slots=True)
class OrderRejectedDomain:
    """Order was rejected by exchange."""
    internal_order_id: str
    exchange: str
    reason: str
    timestamp: int


@dataclass(frozen=True, slots=True)
class FillReceivedDomain:
    """Fill/execution received from exchange."""
    internal_order_id: str
    execution_id: str  # unique fill ID
    exchange: str
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float
    fee_asset: str
    timestamp: int


@dataclass(frozen=True, slots=True)
class OrderCancelledDomain:
    """Order was cancelled (either by us or exchange)."""
    internal_order_id: str
    exchange: str
    reason: str
    timestamp: int
