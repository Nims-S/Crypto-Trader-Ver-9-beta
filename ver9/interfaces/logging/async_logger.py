from __future__ import annotations

from typing import Protocol


class AsyncLoggerProtocol(Protocol):
    async def info(self, message: str, **kwargs: object) -> None:
        ...

    async def warning(self, message: str, **kwargs: object) -> None:
        ...

    async def error(self, message: str, **kwargs: object) -> None:
        ...

    async def critical(self, message: str, **kwargs: object) -> None:
        ...
