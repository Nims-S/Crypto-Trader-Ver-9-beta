from __future__ import annotations

from dataclasses import dataclass

from .base_event import RuntimeEvent


@dataclass(frozen=True, slots=True)
class SystemStateTransition(RuntimeEvent):
    old_state: str
    new_state: str


@dataclass(frozen=True, slots=True)
class ComponentHeartbeat(RuntimeEvent):
    component_name: str
    status: str


@dataclass(frozen=True, slots=True)
class CircuitBreakerTripped(RuntimeEvent):
    target_component: str
    reason: str
