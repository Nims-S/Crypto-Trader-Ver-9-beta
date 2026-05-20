from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    event_id: str
    timestamp_ns: int
    correlation_id: str
