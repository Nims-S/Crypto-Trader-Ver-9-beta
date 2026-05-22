"""Async logger protocol."""
from __future__ import annotations

from typing import Protocol


class AsyncLogger(Protocol):
    """Protocol for asynchronous structured logging."""

    async def debug(self, message: str, **context) -> None:
        """Log debug message."""
        ...

    async def info(self, message: str, **context) -> None:
        """Log info message."""
        ...

    async def warning(self, message: str, **context) -> None:
        """Log warning message."""
        ...

    async def error(self, message: str, **context) -> None:
        """Log error message."""
        ...

    async def critical(self, message: str, **context) -> None:
        """Log critical message."""
        ...
