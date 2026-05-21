from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExchangeExecutionResult:
    exchange_order_id: str
    internal_order_id: str
    accepted_price: float
    timestamp_ns: int
    status: str
    position_side: str = "BOTH"
    reduce_only: bool = False
    is_liquidation: bool = False


@dataclass(frozen=True, slots=True)
class ExchangeOrderUpdate:
    exchange_order_id: str
    internal_order_id: str
    status: str
    cumulative_filled_quantity: float
    remaining_quantity: float
    avg_price: float
    reject_reason: str | None
    position_side: str = "BOTH"
    reduce_only: bool = False
    is_liquidation: bool = False


@dataclass(frozen=True, slots=True)
class ExchangeFillUpdate:
    exchange_order_id: str
    trade_id: str
    fill_price: float
    fill_quantity: float
    fill_fee: float
    fee_asset: str
    liquidity_side: str
    position_side: str = "BOTH"
    reduce_only: bool = False
    is_liquidation: bool = False
