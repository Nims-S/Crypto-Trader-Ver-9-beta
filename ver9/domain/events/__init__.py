"""Canonical domain event contracts.

These are the authoritative, immutable event types for the execution pipeline.
They are pure, dependency-free dataclasses that define the event schema.

Domain events MUST:
- import nothing outside stdlib and dataclasses
- be immutable (frozen=True)
- include full context (internal_order_id, strategy_id, exchange, etc.)
- use proper timestamp types (int for ns or datetime for ISO)
"""
