from __future__ import annotations

from ver9.runtime.state.runtime_state_store import RuntimeStateStore
from ver9.runtime.state.state_models import RuntimeStateSnapshot

from .event_store import EventStore


class ReplayEngine:
    def __init__(
        self,
        *,
        event_store: EventStore,
    ) -> None:
        self.event_store = event_store

    async def replay_historical_events(
        self,
        start_timestamp_ns: int,
        store: RuntimeStateStore,
    ) -> RuntimeStateSnapshot:
        snapshot = await store.snapshot()

        for event in await self.event_store.replay_from(
            start_timestamp_ns=start_timestamp_ns,
        ):
            snapshot = await store.project(event)

        return snapshot

    async def replay_after_sequence(
        self,
        sequence: int | None,
        store: RuntimeStateStore,
    ) -> RuntimeStateSnapshot:
        snapshot = await store.snapshot()

        for event_sequence, event in await self.event_store.replay_after_sequence(
            sequence,
        ):
            snapshot = await store.project(
                event,
                sequence=event_sequence,
            )

        return snapshot
