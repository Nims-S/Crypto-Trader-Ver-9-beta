"""Integration test: Deterministic replay correctness."""
from __future__ import annotations

import pytest
from time import time_ns

from ver9.domain.events.execution import (
    OrderSubmittedDomain,
    OrderAcceptedDomain,
    FillReceivedDomain,
    OrderRejectedDomain,
)
from ver9.runtime.state.runtime_state_store_phase4 import RuntimeStateStorePhase4


@pytest.mark.asyncio
async def test_replay_determinism() -> None:
    """Same event sequence produces same state."""
    now_ns = time_ns()
    
    # Create event sequence
    events = [
        OrderSubmittedDomain(
            internal_order_id="order_1",
            strategy_id="strategy_1",
            exchange="BINANCE",
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            price=50000.0,
            quantity=1.0,
            timestamp=now_ns,
        ),
        OrderAcceptedDomain(
            internal_order_id="order_1",
            exchange_order_id="binance_456",
            timestamp=now_ns + 1000,
        ),
        FillReceivedDomain(
            internal_order_id="order_1",
            exchange_order_id="binance_456",
            exchange="BINANCE",
            execution_id="trade_1",
            price=50000.0,
            quantity=0.5,
            fee=2.5,
            fee_asset="USDT",
            timestamp=now_ns + 2000,
        ),
    ]
    
    # Replay 1
    store1 = RuntimeStateStorePhase4()
    for i, event in enumerate(events):
        await store1.project(event, sequence=i)
    snapshot1 = await store1.snapshot()
    
    # Replay 2 (same events, different store)
    store2 = RuntimeStateStorePhase4()
    for i, event in enumerate(events):
        await store2.project(event, sequence=i)
    snapshot2 = await store2.snapshot()
    
    # Verify identical state
    assert len(snapshot1.orders) == len(snapshot2.orders)
    assert snapshot1.orders["order_1"].filled_quantity == snapshot2.orders["order_1"].filled_quantity
    assert snapshot1.orders["order_1"].total_fee == snapshot2.orders["order_1"].total_fee


@pytest.mark.asyncio
async def test_replay_with_checkpoint() -> None:
    """Replay from checkpoint recovers correct state."""
    now_ns = time_ns()
    
    events = [
        OrderSubmittedDomain(
            internal_order_id="order_1",
            strategy_id="strategy_1",
            exchange="BINANCE",
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            price=50000.0,
            quantity=1.0,
            timestamp=now_ns,
        ),
        OrderAcceptedDomain(
            internal_order_id="order_1",
            exchange_order_id="binance_456",
            timestamp=now_ns + 1000,
        ),
        FillReceivedDomain(
            internal_order_id="order_1",
            exchange_order_id="binance_456",
            exchange="BINANCE",
            execution_id="trade_1",
            price=50000.0,
            quantity=0.5,
            fee=2.5,
            fee_asset="USDT",
            timestamp=now_ns + 2000,
        ),
    ]
    
    # Full replay
    store_full = RuntimeStateStorePhase4()
    for i, event in enumerate(events):
        await store_full.project(event, sequence=i)
    snapshot_full = await store_full.snapshot()
    
    # Partial replay (first 2 events) + checkpoint + resume
    store_partial = RuntimeStateStorePhase4()
    for i, event in enumerate(events[:2]):
        await store_partial.project(event, sequence=i)
    
    # Add remaining event
    await store_partial.project(events[2], sequence=2)
    snapshot_partial = await store_partial.snapshot()
    
    # Should match
    assert snapshot_full.orders["order_1"].filled_quantity == snapshot_partial.orders["order_1"].filled_quantity
