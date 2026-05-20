from __future__ import annotations

from dataclasses import dataclass

from .base_event import RuntimeEvent


@dataclass(frozen=True, slots=True)
class TradeEvent(RuntimeEvent):
    symbol: str
    price: float
    quantity: float
    side: str


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot(RuntimeEvent):
    symbol: str
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class OrderBookUpdate(RuntimeEvent):
    symbol: str
    bids_to_update: tuple[tuple[float, float], ...]
    asks_to_update: tuple[tuple[float, float], ...]
