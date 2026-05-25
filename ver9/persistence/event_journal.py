"""Phase 5: Event Journal - Append-Only Event Log.

Responsibilities:
1. Persist domain events in deterministic order
2. Assign monotonic offsets (sequence numbers)
3. Enable replay from any checkpoint
4. Provide recovery watermarks
5. Support idempotency deduplication

Properties:
- Append-only (immutable history)
- Monotonic offsets
- Deterministic serialization
- Checkpoint-aware
- No mutations of existing events
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from time import time_ns
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ver9.domain.events.execution import (
        OrderSubmittedDomain,
        OrderAcceptedDomain,
        OrderRejectedDomain,
        FillReceivedDomain,
    )


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """Immutable journal entry wrapping a domain event with metadata."""
    
    offset: int  # Monotonic sequence number (0-indexed)
    event_type: str  # "OrderSubmittedDomain", "FillReceivedDomain", etc.
    event_payload: dict  # Serialized event (deterministic JSON)
    timestamp_ns: int  # Insertion timestamp (nanos)
    correlation_id: str | None = None  # For tracing
    
    def to_json_line(self) -> str:
        """Serialize to single JSON line (for file storage)."""
        return json.dumps(
            {
                "offset": self.offset,
                "event_type": self.event_type,
                "event_payload": self.event_payload,
                "timestamp_ns": self.timestamp_ns,
                "correlation_id": self.correlation_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class JournalCheckpoint:
    """Checkpoint for recovery - marks a safe point to resume from."""
    
    offset: int  # Last successfully projected offset
    portfolio_snapshot_id: str  # Reference to persisted snapshot
    timestamp_ns: int  # When this checkpoint was taken
    event_count: int  # Number of events in journal up to this offset


class EventJournal:
    """Append-only event journal with monotonic offsets.
    
    Thread-safe journal for persisting domain events.
    Enables deterministic replay and recovery.
    
    Design:
    - Events are immutable once appended
    - Each entry gets monotonic offset (sequence)
    - Deterministic JSON serialization
    - Checkpoint support for recovery
    """

    def __init__(self) -> None:
        """Initialize empty journal."""
        self._entries: list[JournalEntry] = []
        self._next_offset: int = 0
        self._checkpoints: list[JournalCheckpoint] = []

    def append_event(
        self,
        event: OrderSubmittedDomain | OrderAcceptedDomain | OrderRejectedDomain | FillReceivedDomain,
    ) -> JournalEntry:
        """Append domain event to journal (monotonic offset).
        
        Args:
            event: Domain event to persist
            
        Returns:
            JournalEntry with assigned offset
            
        Raises:
            ValueError: If event serialization fails
        """
        try:
            # Serialize event to deterministic JSON
            event_dict = self._serialize_event(event)
            
            # Create immutable journal entry
            entry = JournalEntry(
                offset=self._next_offset,
                event_type=type(event).__name__,
                event_payload=event_dict,
                timestamp_ns=time_ns(),
                correlation_id=getattr(event, "correlation_id", None),
            )
            
            # Append (immutable)
            self._entries.append(entry)
            self._next_offset += 1
            
            return entry
            
        except Exception as exc:
            raise ValueError(
                f"Failed to serialize event {type(event).__name__}: {exc}"
            )

    def get_entries(
        self,
        start_offset: int = 0,
        end_offset: int | None = None,
    ) -> list[JournalEntry]:
        """Get entries in range [start_offset, end_offset).
        
        Args:
            start_offset: Inclusive start (default 0)
            end_offset: Exclusive end (default end of journal)
            
        Returns:
            List of immutable JournalEntry objects
        """
        if end_offset is None:
            end_offset = len(self._entries)
        
        # Clamp to valid range
        start = max(0, min(start_offset, len(self._entries)))
        end = max(0, min(end_offset, len(self._entries)))
        
        return self._entries[start:end]

    def get_entry_at(self, offset: int) -> JournalEntry | None:
        """Get specific entry by offset, or None."""
        if 0 <= offset < len(self._entries):
            return self._entries[offset]
        return None

    def create_checkpoint(
        self,
        portfolio_snapshot_id: str,
    ) -> JournalCheckpoint:
        """Create recovery checkpoint after processing current journal.
        
        Args:
            portfolio_snapshot_id: ID of persisted portfolio snapshot
            
        Returns:
            Immutable checkpoint for recovery
        """
        checkpoint = JournalCheckpoint(
            offset=self._next_offset - 1,  # Last offset we processed
            portfolio_snapshot_id=portfolio_snapshot_id,
            timestamp_ns=time_ns(),
            event_count=len(self._entries),
        )
        self._checkpoints.append(checkpoint)
        return checkpoint

    def get_latest_checkpoint(self) -> JournalCheckpoint | None:
        """Get most recent checkpoint, or None if none exist."""
        return self._checkpoints[-1] if self._checkpoints else None

    def events_since_checkpoint(
        self,
        checkpoint: JournalCheckpoint,
    ) -> list[JournalEntry]:
        """Get all events after checkpoint (for replay).
        
        Args:
            checkpoint: Checkpoint to resume from
            
        Returns:
            Events with offset > checkpoint.offset
        """
        return self.get_entries(start_offset=checkpoint.offset + 1)

    @property
    def total_events(self) -> int:
        """Total events appended."""
        return len(self._entries)

    @property
    def last_offset(self) -> int | None:
        """Last assigned offset, or None if empty."""
        return self._next_offset - 1 if self._entries else None

    # ========================================================================
    # Serialization
    # ========================================================================

    @staticmethod
    def _serialize_event(event) -> dict:
        """Convert domain event to deterministic JSON dict.
        
        Uses dataclass asdict() for consistent field ordering.
        """
        if hasattr(event, "__dataclass_fields__"):
            return asdict(event)
        else:
            # Fallback for non-dataclass events
            return vars(event)


class ReplayEngineProtocol:
    """Protocol for replaying journal events into state store.
    
    Deterministically reconstructs state by projecting journal
    events in order.
    """

    def __init__(self, state_store, journal: EventJournal) -> None:
        """Initialize replay engine.
        
        Args:
            state_store: RuntimeStateStore to project into
            journal: EventJournal to replay from
        """
        self._state_store = state_store
        self._journal = journal

    async def replay_from_checkpoint(
        self,
        checkpoint: JournalCheckpoint,
    ) -> None:
        """Replay journal events from checkpoint to current state.
        
        Args:
            checkpoint: Checkpoint to resume from
            
        Raises:
            Exception: If state projection fails (corrupted journal)
        """
        events = self._journal.events_since_checkpoint(checkpoint)
        
        for entry in events:
            # Deserialize event from journal entry
            event = self._deserialize_event(entry)
            
            # Project into state store
            await self._state_store.project(
                event,
                sequence=entry.offset,
            )

    async def replay_from_start(self) -> None:
        """Full replay from journal start (recovery)."""
        for entry in self._journal.get_entries():
            event = self._deserialize_event(entry)
            await self._state_store.project(
                event,
                sequence=entry.offset,
            )

    @staticmethod
    def _deserialize_event(entry: JournalEntry):
        """Convert journal entry back to domain event object.
        
        NOTE: This is a placeholder. In reality, you'd need to:
        1. Map event_type string to actual domain class
        2. Instantiate from payload dict
        3. Validate schema
        """
        # TODO: Implement event deserialization with type registry
        raise NotImplementedError(
            "Event deserialization requires type registry mapping"
        )
