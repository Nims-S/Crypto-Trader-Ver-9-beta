from __future__ import annotations

from dataclasses import dataclass

from .base_event import RuntimeEvent


@dataclass(frozen=True, slots=True)
class AllocationRequested(RuntimeEvent):
    target_allocations: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class RiskBreachDetected(RuntimeEvent):
    metric_violated: str
    current_value: float
    threshold: float


@dataclass(frozen=True, slots=True)
class ReconciliationCorrectionRequested(RuntimeEvent):
    asset: str
    expected_balance: float
    actual_balance: float
