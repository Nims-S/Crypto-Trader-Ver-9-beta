from __future__ import annotations

from typing import Protocol


class RuntimeStateView(Protocol):
    def get_total_equity(self) -> float:
        ...

    def get_position_size(
        self,
        exchange: str,
        symbol: str,
    ) -> float:
        ...

    def get_balance(
        self,
        exchange: str,
        asset: str,
    ) -> float:
        ...
