"""Phase 2 OMS Refactoring Complete.

Key Changes:
1. OMS now accepts both legacy and domain events
2. All legacy events normalized to canonical domain types
3. Dependencies switched to interfaces (Protocols) only
4. No direct imports of runtime.kernel.event_bus
5. EventPublisher interface for event publishing
6. AsyncLogger and MetricsCollector interfaces

Ready for migration to ver9/execution/oms.py when testing passes.
"""
