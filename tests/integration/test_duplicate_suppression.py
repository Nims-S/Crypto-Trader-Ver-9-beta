"""Integration test: Idempotency and duplicate suppression."""
from __future__ import annotations

import pytest
from time import time_ns

from ver9.domain.events.execution import FillReceivedDomain
from ver9.execution.idempotency import IdempotentFillProcessor, IdempotencyLayer
from ver9.runtime.state.runtime_state_store_phase4 import RuntimeStateStorePhase4
from ver9.domain.events.execution import OrderSubmittedDomain, OrderAcceptedDomain


@pytest.mark.asyncio
async def test_duplicate_fill_suppressed() -> None:
    """Duplicate fill events are suppressed."""
    layer = IdempotencyLayer()
    state_store = RuntimeStateStorePhase4()
    fill_count = 0
    
    async def handle_fill(event: FillReceivedDomain) -> None:
        nonlocal fill_count
        fill_count += 1
    
    processor = IdempotentFillProcessor(layer, handle_fill)
    now_ns = time_ns()
    
    # Setup order
    order_event = OrderSubmittedDomain(
        internal_order_id="order_1",
        strategy_id="strategy_1",
        exchange="BINANCE",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        price=50000.0,
        quantity=1.0,
        timestamp=now_ns,
    )
    await state_store.project(order_event)
    
    await state_store.project(
        OrderAcceptedDomain(
            internal_order_id="order_1",
            exchange_order_id="binance_456",
            timestamp=now_ns + 1000,
        )
    )
    
    # Create fill (same fingerprint for duplicate detection)
    fill = FillReceivedDomain(
        internal_order_id="order_1",
        exchange_order_id="binance_456",
        exchange="BINANCE",
        execution_id="trade_1",
        price=50000.0,
        quantity=0.5,
        fee=2.5,
        fee_asset="USDT",
        timestamp=now_ns + 2000,
    )
    
    # Process fill multiple times
    result1 = await processor.process_fill(fill)
    result2 = await processor.process_fill(fill)  # Duplicate
    result3 = await processor.process_fill(fill)  # Duplicate
    
    # Only first should succeed
    assert result1 is True
    assert result2 is False
    assert result3 is False
    
    # Handler called only once
    assert fill_count == 1


@pytest.mark.asyncio
async def test_different_fills_not_suppressed() -> None:
    """Different fills are processed independently."""
    layer = IdempotencyLayer()
    processed = []
    
    async def handle_fill(event: FillReceivedDomain) -> None:
        processed.append(event.execution_id)
    
    processor = IdempotentFillProcessor(layer, handle_fill)
    now_ns = time_ns()
    
    # Two different fills
    fill1 = FillReceivedDomain(
        internal_order_id="order_1",
        exchange_order_id="binance_456",
        exchange="BINANCE",
        execution_id="trade_1",
        price=50000.0,
        quantity=0.5,
        fee=2.5,
        fee_asset="USDT",
        timestamp=now_ns,
    )
    
    fill2 = FillReceivedDomain(
        internal_order_id="order_1",
        exchange_order_id="binance_456",
        exchange="BINANCE",
        execution_id="trade_2",  # Different trade ID
        price=50000.0,
        quantity=0.5,
        fee=2.5,
        fee_asset="USDT",
        timestamp=now_ns + 1000,
    )
    
    await processor.process_fill(fill1)
    await processor.process_fill(fill2)
    
    # Both processed
    assert len(processed) == 2
    assert "trade_1" in processed
    assert "trade_2" in processed
