"""Test Phase 5b: Idempotency layer."""
from __future__ import annotations

import pytest
import asyncio
from time import time_ns

from ver9.domain.events.execution import FillReceivedDomain
from ver9.execution.idempotency import (
    IdempotencyLayer,
    ExecutionHash,
    IdempotentFillProcessor,
)


class TestExecutionHash:
    """Test execution hash fingerprinting."""

    def test_hash_consistency(self) -> None:
        """Same inputs produce same hash."""
        hash1 = ExecutionHash(
            exchange="BINANCE",
            exchange_order_id="binance_456",
            trade_id="trade_789",
            fill_price=50000.0,
            fill_quantity=1.0,
        )
        
        hash2 = ExecutionHash(
            exchange="BINANCE",
            exchange_order_id="binance_456",
            trade_id="trade_789",
            fill_price=50000.0,
            fill_quantity=1.0,
        )
        
        assert hash1.to_hash() == hash2.to_hash()

    def test_hash_differs(self) -> None:
        """Different inputs produce different hashes."""
        hash1 = ExecutionHash(
            exchange="BINANCE",
            exchange_order_id="binance_456",
            trade_id="trade_789",
            fill_price=50000.0,
            fill_quantity=1.0,
        )
        
        hash2 = ExecutionHash(
            exchange="BINANCE",
            exchange_order_id="binance_456",
            trade_id="trade_789",
            fill_price=50001.0,  # Different price
            fill_quantity=1.0,
        )
        
        assert hash1.to_hash() != hash2.to_hash()


class TestIdempotencyLayer:
    """Test idempotency cache."""

    @pytest.mark.asyncio
    async def test_first_fill_not_duplicate(self) -> None:
        """First fill is not marked as duplicate."""
        layer = IdempotencyLayer()
        fill = FillReceivedDomain(
            internal_order_id="order_123",
            exchange_order_id="binance_456",
            exchange="BINANCE",
            execution_id="trade_789",
            price=50000.0,
            quantity=1.0,
            fee=2.5,
            fee_asset="USDT",
            timestamp=time_ns(),
        )
        
        is_dup = await layer.is_duplicate(fill)
        assert is_dup is False

    @pytest.mark.asyncio
    async def test_duplicate_detection(self) -> None:
        """Duplicate fill is detected."""
        layer = IdempotencyLayer()
        fill = FillReceivedDomain(
            internal_order_id="order_123",
            exchange_order_id="binance_456",
            exchange="BINANCE",
            execution_id="trade_789",
            price=50000.0,
            quantity=1.0,
            fee=2.5,
            fee_asset="USDT",
            timestamp=time_ns(),
        )
        
        # First time
        is_dup1 = await layer.is_duplicate(fill)
        assert is_dup1 is False
        
        # Record it
        await layer.record_execution(fill)
        
        # Second time (duplicate)
        is_dup2 = await layer.is_duplicate(fill)
        assert is_dup2 is True

    @pytest.mark.asyncio
    async def test_cache_size(self) -> None:
        """Cache tracks size."""
        layer = IdempotencyLayer()
        
        for i in range(5):
            fill = FillReceivedDomain(
                internal_order_id=f"order_{i}",
                exchange_order_id=f"binance_{i}",
                exchange="BINANCE",
                execution_id=f"trade_{i}",
                price=50000.0,
                quantity=1.0,
                fee=2.5,
                fee_asset="USDT",
                timestamp=time_ns(),
            )
            await layer.record_execution(fill)
        
        assert layer.cache_size == 5

    @pytest.mark.asyncio
    async def test_clear_expired(self) -> None:
        """Clear expired entries."""
        layer = IdempotencyLayer(ttl_seconds=1)  # Short TTL
        
        fill = FillReceivedDomain(
            internal_order_id="order_123",
            exchange_order_id="binance_456",
            exchange="BINANCE",
            execution_id="trade_789",
            price=50000.0,
            quantity=1.0,
            fee=2.5,
            fee_asset="USDT",
            timestamp=time_ns(),
        )
        
        await layer.record_execution(fill)
        assert layer.cache_size == 1
        
        # Wait for TTL to expire
        await asyncio.sleep(1.1)
        
        removed = await layer.clear_expired()
        assert removed == 1
        assert layer.cache_size == 0


class TestIdempotentFillProcessor:
    """Test idempotent fill processor wrapper."""

    @pytest.mark.asyncio
    async def test_process_new_fill(self) -> None:
        """Process new fill (not duplicate)."""
        layer = IdempotencyLayer()
        processed_fills = []
        
        async def handler(event: FillReceivedDomain) -> None:
            processed_fills.append(event.execution_id)
        
        processor = IdempotentFillProcessor(layer, handler)
        
        fill = FillReceivedDomain(
            internal_order_id="order_123",
            exchange_order_id="binance_456",
            exchange="BINANCE",
            execution_id="trade_789",
            price=50000.0,
            quantity=1.0,
            fee=2.5,
            fee_asset="USDT",
            timestamp=time_ns(),
        )
        
        result = await processor.process_fill(fill)
        assert result is True
        assert processed_fills == ["trade_789"]

    @pytest.mark.asyncio
    async def test_skip_duplicate_fill(self) -> None:
        """Skip duplicate fill."""
        layer = IdempotencyLayer()
        processed_fills = []
        
        async def handler(event: FillReceivedDomain) -> None:
            processed_fills.append(event.execution_id)
        
        processor = IdempotentFillProcessor(layer, handler)
        
        fill = FillReceivedDomain(
            internal_order_id="order_123",
            exchange_order_id="binance_456",
            exchange="BINANCE",
            execution_id="trade_789",
            price=50000.0,
            quantity=1.0,
            fee=2.5,
            fee_asset="USDT",
            timestamp=time_ns(),
        )
        
        # Process first time
        result1 = await processor.process_fill(fill)
        assert result1 is True
        
        # Process duplicate
        result2 = await processor.process_fill(fill)
        assert result2 is False
        
        # Handler called only once
        assert processed_fills == ["trade_789"]
