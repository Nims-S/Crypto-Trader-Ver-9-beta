from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from time import time_ns
from uuid import uuid4

import pytest

from ver9.events.execution_events import FillReceived
from ver9.events.execution_events import OrderSubmitted
from ver9.events.market_events import TradeEvent
from ver9.exchanges.binance.adapter import BinanceAdapter
from ver9.runtime.state.state_models import OrderStatus
from ver9.runtime.state.state_models import PositionState


@pytest.mark.asyncio
async def test_event_pipeline_flow(mock_kernel) -> None:
    await mock_kernel.bootstrap()

    adapter = BinanceAdapter(event_bus=mock_kernel.event_bus)
    raw_trade_payload = {
        "s": "BTCUSDT",
        "p": "43125.50",
        "q": "0.2500",
        "S": "BUY",
    }

    trade_event = await adapter.publish_trade_payload(
        raw_trade_payload,
        correlation_id="test-correlation-market",
    )

    assert isinstance(trade_event, TradeEvent)
    assert trade_event.symbol == "BTCUSDT"
    assert trade_event.price == 43125.50
    assert trade_event.quantity == 0.25

    with pytest.raises(FrozenInstanceError):
        trade_event.symbol = "ETHUSDT"

    event_log_path = Path(mock_kernel.event_store.active_log_path)
    assert event_log_path.exists()

    log_lines = event_log_path.read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 1
    assert '"sequence": 0' in log_lines[0]
    assert '"event_type": "TradeEvent"' in log_lines[0]

    order_id = str(uuid4())
    correlation_id = str(uuid4())

    await mock_kernel.publish(
        OrderSubmitted(
            event_id=str(uuid4()),
            timestamp_ns=time_ns(),
            correlation_id=correlation_id,
            order_id=order_id,
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            price=43125.50,
            quantity=0.25,
        )
    )
    await mock_kernel.publish(
        FillReceived(
            event_id=str(uuid4()),
            timestamp_ns=time_ns(),
            correlation_id=correlation_id,
            order_id=order_id,
            fill_id=str(uuid4()),
            price=43125.50,
            quantity=0.25,
            fee=1.25,
            fee_asset="USDT",
        )
    )

    snapshot = await mock_kernel.state_store.snapshot()
    position = snapshot.positions["BTCUSDT"]
    order = snapshot.orders[order_id]

    assert isinstance(position, PositionState)
    assert position.net_quantity == 0.25
    assert position.average_entry_price == 43125.50
    assert position.open_risk == abs(position.net_exposure)
    assert order.status is OrderStatus.FILLED

    with pytest.raises(TypeError):
        snapshot.positions["ETHUSDT"] = position

    shutdown_snapshot = await mock_kernel.shutdown()
    assert shutdown_snapshot.positions["BTCUSDT"] == position
    assert mock_kernel.snapshot_store.snapshot_path.exists()
