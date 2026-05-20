from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    default_exchange: str = "binance"
    event_log_directory: str = "runtime_events"
    snapshot_directory: str = "runtime_snapshots"
