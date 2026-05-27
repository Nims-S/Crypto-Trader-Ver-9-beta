"""Test Phase 5a: Event journal."""
from __future__ import annotations

import pytest
from time import time_ns

from ver9.domain.events.execution import OrderSubmittedDomain
from ver9.persistence.event_journal import EventJournal, JournalCheckpoint


class TestEventJournal:
    """Test append-only event journal."""

    def test_journal_creation(self) -> None:
        """Create empty journal."""
        journal = EventJournal()
        assert journal.total_events == 0
        assert journal.last_offset is None

    def test_append_event(self) -> None:
        """Append event to journal."""
        journal = EventJournal()
        event = OrderSubmittedDomain(
            internal_order_id="order_123",
            strategy_id="strategy_1",
            exchange="BINANCE",
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            price=50000.0,
            quantity=1.0,
            timestamp=time_ns(),
        )
        
        entry = journal.append_event(event)
        assert entry.offset == 0
        assert entry.event_type == "OrderSubmittedDomain"
        assert journal.total_events == 1
        assert journal.last_offset == 0

    def test_monotonic_offsets(self) -> None:
        """Offsets are monotonically increasing."""
        journal = EventJournal()
        offsets = []
        
        for i in range(5):
            event = OrderSubmittedDomain(
                internal_order_id=f"order_{i}",
                strategy_id="strategy_1",
                exchange="BINANCE",
                symbol="BTC/USDT",
                side="BUY",
                order_type="LIMIT",
                price=50000.0,
                quantity=1.0,
                timestamp=time_ns(),
            )
            entry = journal.append_event(event)
            offsets.append(entry.offset)
        
        assert offsets == [0, 1, 2, 3, 4]

    def test_get_entries_range(self) -> None:
        """Get entries in range."""
        journal = EventJournal()
        
        for i in range(5):
            event = OrderSubmittedDomain(
                internal_order_id=f"order_{i}",
                strategy_id="strategy_1",
                exchange="BINANCE",
                symbol="BTC/USDT",
                side="BUY",
                order_type="LIMIT",
                price=50000.0,
                quantity=1.0,
                timestamp=time_ns(),
            )
            journal.append_event(event)
        
        entries = journal.get_entries(start_offset=1, end_offset=4)
        assert len(entries) == 3
        assert entries[0].offset == 1
        assert entries[2].offset == 3

    def test_get_entry_at(self) -> None:
        """Get specific entry by offset."""
        journal = EventJournal()
        
        for i in range(3):
            event = OrderSubmittedDomain(
                internal_order_id=f"order_{i}",
                strategy_id="strategy_1",
                exchange="BINANCE",
                symbol="BTC/USDT",
                side="BUY",
                order_type="LIMIT",
                price=50000.0,
                quantity=1.0,
                timestamp=time_ns(),
            )
            journal.append_event(event)
        
        entry = journal.get_entry_at(1)
        assert entry is not None
        assert entry.offset == 1
        
        none_entry = journal.get_entry_at(99)
        assert none_entry is None

    def test_checkpoint_creation(self) -> None:
        """Create checkpoint."""
        journal = EventJournal()
        
        for i in range(3):
            event = OrderSubmittedDomain(
                internal_order_id=f"order_{i}",
                strategy_id="strategy_1",
                exchange="BINANCE",
                symbol="BTC/USDT",
                side="BUY",
                order_type="LIMIT",
                price=50000.0,
                quantity=1.0,
                timestamp=time_ns(),
            )
            journal.append_event(event)
        
        checkpoint = journal.create_checkpoint("snapshot_123")
        assert checkpoint.offset == 2
        assert checkpoint.portfolio_snapshot_id == "snapshot_123"
        assert checkpoint.event_count == 3

    def test_events_since_checkpoint(self) -> None:
        """Get events since checkpoint."""
        journal = EventJournal()
        
        for i in range(5):
            event = OrderSubmittedDomain(
                internal_order_id=f"order_{i}",
                strategy_id="strategy_1",
                exchange="BINANCE",
                symbol="BTC/USDT",
                side="BUY",
                order_type="LIMIT",
                price=50000.0,
                quantity=1.0,
                timestamp=time_ns(),
            )
            journal.append_event(event)
        
        checkpoint = journal.create_checkpoint("snapshot_123")
        # Checkpoint at offset 4 (last event)
        assert checkpoint.offset == 4
        
        # Add more events
        for i in range(5, 7):
            event = OrderSubmittedDomain(
                internal_order_id=f"order_{i}",
                strategy_id="strategy_1",
                exchange="BINANCE",
                symbol="BTC/USDT",
                side="BUY",
                order_type="LIMIT",
                price=50000.0,
                quantity=1.0,
                timestamp=time_ns(),
            )
            journal.append_event(event)
        
        since = journal.events_since_checkpoint(checkpoint)
        assert len(since) == 2
        assert since[0].offset == 5
        assert since[1].offset == 6
