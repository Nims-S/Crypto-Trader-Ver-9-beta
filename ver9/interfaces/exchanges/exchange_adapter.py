"""Exchange adapter protocol.

Defines the contract that concrete exchange adapters (Binance, Bybit, etc.)
must implement. Decouples execution from exchange-specific logic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator, Protocol

if TYPE_CHECKING:
    from ver9.domain.events.execution import OrderSubmittedDomain
    from ver9.events.execution_models import (
        ExchangeExecutionResult,
        ExchangeOrderUpdate,
        ExchangeFillUpdate,
    )


class ExchangeAdapter(Protocol):
    """Protocol for exchange adapters.
    
    Concrete implementations (BinanceAdapter, BybitAdapter, etc.) must
    provide methods for order submission and execution stream handling.
    """

    @property
    def exchange_name(self) -> str:
        """Name of the exchange (e.g., 'BINANCE')."""
        ...

    @property
    def is_connected(self) -> bool:
        """Whether adapter is currently connected to exchange."""
        ...

    async def start(self) -> None:
        """Start adapter lifecycle (connect, setup streams)."""
        ...

    async def stop(self) -> None:
        """Gracefully stop adapter."""
        ...

    async def submit_order(
        self,
        event: OrderSubmittedDomain,
    ) -> ExchangeExecutionResult:
        """Submit order to exchange."""
        ...

    async def execution_stream(
        self,
    ) -> AsyncIterator[ExchangeOrderUpdate | ExchangeFillUpdate]:
        """Stream normalized execution updates from exchange."""
        ...
