"""Portfolio value objects and snapshots."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    """Immutable balance for a single asset."""
    asset: str  # e.g. "BTC", "USDT"
    total: float
    available: float
    reserved: float  # locked in open orders


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """Immutable position in a single symbol."""
    symbol: str  # e.g. "BTCUSDT"
    side: str  # "LONG" or "SHORT"
    quantity: float
    entry_price: float
    current_price: float
    pnl: float
    pnl_percent: float


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Immutable snapshot of portfolio state.
    
    Represents the entire portfolio at a point in time:
    - all balances
    - all positions
    - derived metrics (total PnL, total exposure)
    """
    timestamp: int  # ns since epoch
    balances: dict[str, BalanceSnapshot]  # asset -> BalanceSnapshot
    positions: dict[str, PositionSnapshot]  # symbol -> PositionSnapshot
    total_pnl: float
    total_pnl_percent: float
