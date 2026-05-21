from __future__ import annotations

from dataclasses import dataclass

from ver9.domain.events.runtime import RuntimeEvent


@dataclass(frozen=True, slots=True)
class RiskBreachDetected(RuntimeEvent):
    exchange: str
    symbol: str
    breach_type: str
    description: str
