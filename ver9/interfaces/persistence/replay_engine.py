from __future__ import annotations

from typing import Protocol


class ReplayEngineProtocol(Protocol):
    async def recover_missing_sequence_range(
        self,
        exchange: str,
        start_sequence: int,
        end_sequence: int,
    ) -> None:
        ...
