"""Legacy -> Domain event translators.

These functions map from legacy runtime event types to canonical domain events.
Each translator:
- Takes a legacy event instance
- Explicitly maps each field
- Supplies sensible defaults for missing context
- Returns a domain dataclass instance

Translators are safe for replay and deterministic.
"""
from __future__ import annotations

from ver9.domain.events.execution import (
    OrderSubmittedDomain,
    OrderAcceptedDomain,
    OrderRejectedDomain,
    FillReceivedDomain,
    OrderCancelledDomain,
)
from ver9.events.execution_events import (
    OrderSubmitted as LegacyOrderSubmitted,
    OrderAccepted as LegacyOrderAccepted,
    OrderRejected as LegacyOrderRejected,
    FillReceived as LegacyFillReceived,
)


def legacy_order_submitted_to_domain(event: LegacyOrderSubmitted) -> OrderSubmittedDomain:
    """Translate legacy OrderSubmitted -> canonical OrderSubmittedDomain.
    
    Field mapping:
    - order_id -> internal_order_id (use as-is)
    - symbol, side, order_type, price, quantity -> pass through
    - strategy_id -> default to "default_strategy" (missing in legacy)
    - exchange -> extract or default to "UNKNOWN"
    - timestamp_ns -> pass as timestamp
    """
    return OrderSubmittedDomain(
        internal_order_id=event.order_id,
        strategy_id=getattr(event, "strategy_id", "default_strategy"),
        exchange=getattr(event, "exchange", "UNKNOWN"),
        symbol=event.symbol,
        side=event.side,
        order_type=event.order_type,
        price=event.price,
        quantity=event.quantity,
        timestamp=event.timestamp_ns,
    )


def legacy_order_accepted_to_domain(event: LegacyOrderAccepted) -> OrderAcceptedDomain:
    """Translate legacy OrderAccepted -> canonical OrderAcceptedDomain."""
    return OrderAcceptedDomain(
        internal_order_id=event.order_id,
        exchange_order_id=event.exchange_order_id,
        exchange=getattr(event, "exchange", "UNKNOWN"),
        timestamp=event.timestamp_ns,
    )


def legacy_order_rejected_to_domain(event: LegacyOrderRejected) -> OrderRejectedDomain:
    """Translate legacy OrderRejected -> canonical OrderRejectedDomain."""
    return OrderRejectedDomain(
        internal_order_id=event.order_id,
        exchange=getattr(event, "exchange", "UNKNOWN"),
        reason=event.reason,
        timestamp=event.timestamp_ns,
    )


def legacy_fill_received_to_domain(event: LegacyFillReceived) -> FillReceivedDomain:
    """Translate legacy FillReceived -> canonical FillReceivedDomain.
    
    Note: FillReceivedDomain needs symbol and side context, which may not be
    in the legacy event. Caller should provide or leave as UNKNOWN.
    """
    return FillReceivedDomain(
        internal_order_id=event.order_id,
        execution_id=event.fill_id,
        exchange=getattr(event, "exchange", "UNKNOWN"),
        symbol=getattr(event, "symbol", "UNKNOWN"),
        side=getattr(event, "side", "UNKNOWN"),
        quantity=event.quantity,
        price=event.price,
        fee=event.fee,
        fee_asset=event.fee_asset,
        timestamp=event.timestamp_ns,
    )
