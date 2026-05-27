"""Test Phase 1: Canonical domain event models."""
from __future__ import annotations

import pytest
from time import time_ns

from ver9.domain.events.execution import (
    OrderSubmittedDomain,
    OrderAcceptedDomain,
    OrderRejectedDomain,
    FillReceivedDomain,
)


class TestOrderSubmittedDomain:
    """Test OrderSubmittedDomain immutability and schema."""

    def test_create_order_submitted(self) -> None:
        """Create order submitted event."""
        now_ns = time_ns()
        event = OrderSubmittedDomain(
            internal_order_id="order_123",
            strategy_id="strategy_1",
            exchange="BINANCE",
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            price=50000.0,
            quantity=1.0,
            timestamp=now_ns,
            correlation_id="corr_123",
        )
        assert event.internal_order_id == "order_123"
        assert event.symbol == "BTC/USDT"
        assert event.side == "BUY"
        assert event.price == 50000.0

    def test_order_submitted_frozen(self) -> None:
        """OrderSubmittedDomain is immutable (frozen)."""
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
        with pytest.raises(AttributeError):
            event.quantity = 2.0  # type: ignore

    def test_order_submitted_no_correlation_id(self) -> None:
        """OrderSubmittedDomain with optional correlation_id."""
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
        assert event.correlation_id is None


class TestOrderAcceptedDomain:
    """Test OrderAcceptedDomain."""

    def test_create_order_accepted(self) -> None:
        """Create order accepted event."""
        event = OrderAcceptedDomain(
            internal_order_id="order_123",
            exchange_order_id="binance_order_456",
            timestamp=time_ns(),
        )
        assert event.internal_order_id == "order_123"
        assert event.exchange_order_id == "binance_order_456"

    def test_order_accepted_frozen(self) -> None:
        """OrderAcceptedDomain is immutable."""
        event = OrderAcceptedDomain(
            internal_order_id="order_123",
            exchange_order_id="binance_order_456",
            timestamp=time_ns(),
        )
        with pytest.raises(AttributeError):
            event.exchange_order_id = "other_id"  # type: ignore


class TestFillReceivedDomain:
    """Test FillReceivedDomain."""

    def test_create_fill_received(self) -> None:
        """Create fill received event."""
        event = FillReceivedDomain(
            internal_order_id="order_123",
            exchange_order_id="binance_order_456",
            exchange="BINANCE",
            execution_id="trade_789",
            price=50000.0,
            quantity=0.5,
            fee=2.5,
            fee_asset="USDT",
            timestamp=time_ns(),
        )
        assert event.internal_order_id == "order_123"
        assert event.price == 50000.0
        assert event.quantity == 0.5
        assert event.fee == 2.5

    def test_fill_received_frozen(self) -> None:
        """FillReceivedDomain is immutable."""
        event = FillReceivedDomain(
            internal_order_id="order_123",
            exchange_order_id="binance_order_456",
            exchange="BINANCE",
            execution_id="trade_789",
            price=50000.0,
            quantity=0.5,
            fee=2.5,
            fee_asset="USDT",
            timestamp=time_ns(),
        )
        with pytest.raises(AttributeError):
            event.quantity = 1.0  # type: ignore


class TestOrderRejectedDomain:
    """Test OrderRejectedDomain."""

    def test_create_order_rejected(self) -> None:
        """Create order rejected event."""
        event = OrderRejectedDomain(
            internal_order_id="order_123",
            reason="INSUFFICIENT_BALANCE",
            timestamp=time_ns(),
        )
        assert event.internal_order_id == "order_123"
        assert event.reason == "INSUFFICIENT_BALANCE"

    def test_order_rejected_frozen(self) -> None:
        """OrderRejectedDomain is immutable."""
        event = OrderRejectedDomain(
            internal_order_id="order_123",
            reason="INSUFFICIENT_BALANCE",
            timestamp=time_ns(),
        )
        with pytest.raises(AttributeError):
            event.reason = "OTHER_REASON"  # type: ignore
