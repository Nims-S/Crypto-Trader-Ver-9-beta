"""Test Phase 4: Immutable state models."""
from __future__ import annotations

import pytest
from time import time_ns

from ver9.domain.models.state import (
    OrderSnapshot,
    BalanceSnapshot,
    PositionSnapshot,
    PortfolioSnapshot,
    OrderStatusDomain,
)


class TestOrderSnapshot:
    """Test OrderSnapshot immutability."""

    def test_create_order_snapshot(self) -> None:
        """Create order snapshot."""
        now_ns = time_ns()
        order = OrderSnapshot(
            internal_order_id="order_123",
            exchange_order_id="binance_456",
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            requested_price=50000.0,
            requested_quantity=1.0,
            filled_quantity=0.5,
            average_fill_price=50000.0,
            total_fee=2.5,
            fee_asset="USDT",
            status=OrderStatusDomain.PARTIALLY_FILLED,
            rejection_reason=None,
            created_timestamp_ns=now_ns,
            updated_timestamp_ns=now_ns,
        )
        assert order.internal_order_id == "order_123"
        assert order.filled_quantity == 0.5
        assert order.status == OrderStatusDomain.PARTIALLY_FILLED

    def test_order_snapshot_frozen(self) -> None:
        """OrderSnapshot is immutable."""
        now_ns = time_ns()
        order = OrderSnapshot(
            internal_order_id="order_123",
            exchange_order_id=None,
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            requested_price=50000.0,
            requested_quantity=1.0,
            filled_quantity=0.0,
            average_fill_price=None,
            total_fee=0.0,
            fee_asset=None,
            status=OrderStatusDomain.SUBMITTED,
            rejection_reason=None,
            created_timestamp_ns=now_ns,
            updated_timestamp_ns=now_ns,
        )
        with pytest.raises(AttributeError):
            order.filled_quantity = 1.0  # type: ignore


class TestBalanceSnapshot:
    """Test BalanceSnapshot immutability."""

    def test_create_balance_snapshot(self) -> None:
        """Create balance snapshot."""
        balance = BalanceSnapshot(
            asset="USDT",
            available_balance=10000.0,
            equity_balance=10000.0,
            frozen_margin=0.0,
            updated_timestamp_ns=time_ns(),
        )
        assert balance.asset == "USDT"
        assert balance.available_balance == 10000.0

    def test_balance_snapshot_frozen(self) -> None:
        """BalanceSnapshot is immutable."""
        balance = BalanceSnapshot(
            asset="USDT",
            available_balance=10000.0,
            equity_balance=10000.0,
            frozen_margin=0.0,
            updated_timestamp_ns=time_ns(),
        )
        with pytest.raises(AttributeError):
            balance.available_balance = 5000.0  # type: ignore


class TestPositionSnapshot:
    """Test PositionSnapshot immutability."""

    def test_create_position_snapshot(self) -> None:
        """Create position snapshot."""
        position = PositionSnapshot(
            symbol="BTC/USDT",
            net_quantity=1.0,
            average_entry_price=50000.0,
            net_exposure=50000.0,
            open_risk=50000.0,
            updated_timestamp_ns=time_ns(),
        )
        assert position.symbol == "BTC/USDT"
        assert position.net_quantity == 1.0
        assert position.average_entry_price == 50000.0

    def test_position_snapshot_frozen(self) -> None:
        """PositionSnapshot is immutable."""
        position = PositionSnapshot(
            symbol="BTC/USDT",
            net_quantity=1.0,
            average_entry_price=50000.0,
            net_exposure=50000.0,
            open_risk=50000.0,
            updated_timestamp_ns=time_ns(),
        )
        with pytest.raises(AttributeError):
            position.net_quantity = 2.0  # type: ignore


class TestPortfolioSnapshot:
    """Test PortfolioSnapshot."""

    def test_create_portfolio_snapshot(self) -> None:
        """Create portfolio snapshot."""
        now_ns = time_ns()
        portfolio = PortfolioSnapshot(
            orders={},
            balances={},
            positions={},
            last_event_id="event_123",
            last_timestamp_ns=now_ns,
            last_sequence=42,
        )
        assert portfolio.last_event_id == "event_123"
        assert portfolio.last_sequence == 42

    def test_portfolio_snapshot_orders_readonly(self) -> None:
        """Portfolio snapshot orders mapping is read-only."""
        portfolio = PortfolioSnapshot(
            orders={},
            balances={},
            positions={},
            last_event_id=None,
            last_timestamp_ns=None,
        )
        with pytest.raises(TypeError):
            portfolio.orders["key"] = "value"  # type: ignore
