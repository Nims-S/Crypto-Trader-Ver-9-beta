from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import AsyncIterator

from ver9.domain.models.execution import ExchangeExecutionResult
from ver9.domain.models.execution import ExchangeFillUpdate
from ver9.domain.models.execution import ExchangeOrderUpdate
from ver9.events.execution_events import OrderSubmitted


class BaseExchange(ABC):
    """Pure exchange interface contract.

    This interface is intentionally isolated from:
    - runtime kernel
    - OMS
    - persistence
    - concrete exchange implementations
    """

    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def submit_order(
        self,
        event: OrderSubmitted,
    ) -> ExchangeExecutionResult:
        raise NotImplementedError

    @abstractmethod
    async def execution_stream(
        self,
    ) -> AsyncIterator[
        ExchangeOrderUpdate | ExchangeFillUpdate
    ]:
        raise NotImplementedError
