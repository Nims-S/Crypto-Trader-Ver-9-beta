"""Runtime state view protocol.

Allows execution layers to query current portfolio and order state
without owning or mutating state. Decouples from concrete state store.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ver9.domain.models.order import OrderSnapshot
    from ver9.domain.models.portfolio import PortfolioSnapshot


class RuntimeStateView(Protocol):
    """Protocol for querying runtime state.
    
    Provides read-only access to:
    - Portfolio snapshots
    - Order state
    - Position data
    
    State mutations are handled exclusively by the runtime state store.
    """

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Get current portfolio state as immutable snapshot."""
        ...

    def get_order_snapshot(self, internal_order_id: str) -> OrderSnapshot | None:
        """Get snapshot of a specific order."""
        ...

    def get_all_orders(self) -> list[OrderSnapshot]:
        """Get snapshots of all orders."""
        ...
