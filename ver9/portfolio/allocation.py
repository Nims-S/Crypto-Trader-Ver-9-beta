from __future__ import annotations

from dataclasses import dataclass
from time import time_ns
from uuid import uuid4

from ver9.events.portfolio_events import AllocationRequested
from ver9.runtime.kernel.event_bus import EventBus


@dataclass(frozen=True, slots=True)
class AllocationCandidate:
    strategy_id: str
    symbol: str
    score: float
    risk: float
    capital_multiplier: float = 1.0


@dataclass(frozen=True, slots=True)
class AllocationDecision:
    strategy_id: str
    symbol: str
    weight: float


class PortfolioAllocator:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        max_positions: int = 3,
    ) -> None:
        self.event_bus = event_bus
        self.max_positions = max(1, max_positions)

    async def request_allocation(
        self,
        candidates: tuple[AllocationCandidate, ...],
        *,
        correlation_id: str | None = None,
    ) -> tuple[AllocationDecision, ...]:
        decisions = self.allocate(candidates)
        await self.event_bus.publish(
            AllocationRequested(
                event_id=str(uuid4()),
                timestamp_ns=time_ns(),
                correlation_id=correlation_id or str(uuid4()),
                target_allocations=tuple(
                    (decision.symbol, decision.weight)
                    for decision in decisions
                ),
            )
        )
        return decisions

    def allocate(
        self,
        candidates: tuple[AllocationCandidate, ...],
    ) -> tuple[AllocationDecision, ...]:
        ranked = sorted(
            candidates,
            key=self._candidate_score,
            reverse=True,
        )[: self.max_positions]

        total_score = sum(max(self._candidate_score(row), 0.0) for row in ranked)

        if total_score <= 0.0:
            return ()

        return tuple(
            AllocationDecision(
                strategy_id=row.strategy_id,
                symbol=row.symbol,
                weight=round(
                    max(self._candidate_score(row), 0.0) / total_score,
                    8,
                ),
            )
            for row in ranked
        )

    def _candidate_score(self, candidate: AllocationCandidate) -> float:
        risk = max(candidate.risk, 1.0)
        return (
            max(candidate.score, 0.0)
            * max(0.0, min(candidate.capital_multiplier, 1.0))
        ) / risk
