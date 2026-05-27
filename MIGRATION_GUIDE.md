# Architecture Migration Guide

**Status:** Phase 5 Complete | Phase 6 Pending  
**Target:** Layered architecture with strict boundaries  
**Timeline:** Follow phases sequentially; validate after each  

---

## Quick Reference

### Dependency Rules (ENFORCED)

```
✅ ALLOWED:
  domain → (nothing)
  interfaces → domain
  execution → domain + interfaces
  exchanges → domain + interfaces
  portfolio → domain + interfaces
  runtime → everything (composition root)

❌ FORBIDDEN:
  domain → runtime (ANY layer)
  interfaces → runtime
  execution → runtime
  exchanges → runtime
  portfolio → runtime
  (No circular dependencies)
```

### Phase Roadmap

```
Phase 1 (DONE)
  - Create domain event contracts
  - Write compatibility translators
  - Test legacy → domain mapping

Phase 2 (DONE)
  - Define interface Protocols
  - Create OMS with dual-stack support
  - Inject dependencies (not globals)

Phase 3 (DONE)
  - Refactor exchange adapters
  - Use EventPublisher interface
  - Emit only domain events
  - Remove runtime imports

Phase 4 (DONE)
  - Move state models to domain
  - Implement immutable snapshots
  - Create RuntimeStateView interface
  - Dual-stack state store projection

Phase 5 (DONE)
  - Add append-only event journal
  - Implement idempotency layer
  - Configure import-linter
  - Document validation gates

Phase 6 (NEXT)
  - Remove legacy event schemas
  - Finalize OMS (no dual-stack)
  - Update risk manager
  - Integrate CI checks
  - Deploy to production
```

---

## Phase 1: Canonical Domain Events

### Create Domain Event Classes

**File:** `ver9/domain/events/execution.py`

```python
from dataclasses import dataclass
from time import time_ns

@dataclass(frozen=True, slots=True)
class OrderSubmittedDomain:
    """Canonical order submission event."""
    internal_order_id: str
    strategy_id: str
    exchange: str
    symbol: str
    side: str  # "BUY" or "SELL"
    order_type: str  # "LIMIT", "MARKET"
    price: float | None
    quantity: float
    timestamp: int  # nanoseconds
    correlation_id: str | None = None
```

### Write Compatibility Translators

**File:** `ver9/events/compat/translators.py`

```python
from ver9.events.execution_events import OrderSubmitted as LegacyOrderSubmitted
from ver9.domain.events.execution import OrderSubmittedDomain

def legacy_order_submitted_to_domain(
    legacy: LegacyOrderSubmitted,
) -> OrderSubmittedDomain:
    """Map legacy schema to domain schema."""
    return OrderSubmittedDomain(
        internal_order_id=legacy.order_id,
        strategy_id=getattr(legacy, "strategy_id", "unknown"),
        exchange="UNKNOWN",  # Legacy doesn't store this
        symbol=legacy.symbol,
        side=legacy.side,
        order_type=legacy.order_type,
        price=legacy.price,
        quantity=legacy.quantity,
        timestamp=legacy.timestamp_ns,
        correlation_id=legacy.correlation_id,
    )
```

**Tests:**
```bash
pytest tests/phase1/test_translators.py -v
```

---

## Phase 2: Interface Protocols

### Define EventPublisher Protocol

**File:** `ver9/interfaces/events/event_publisher.py`

```python
from typing import Protocol
from ver9.domain.events.execution import (
    OrderSubmittedDomain,
    OrderAcceptedDomain,
    OrderRejectedDomain,
    FillReceivedDomain,
)

class EventPublisher(Protocol):
    """Contract for publishing domain events."""
    
    async def publish_order_submitted(
        self,
        event: OrderSubmittedDomain,
    ) -> None: ...
    
    async def publish_order_accepted(
        self,
        event: OrderAcceptedDomain,
    ) -> None: ...
```

### Define ExchangeAdapter Interface

**File:** `ver9/interfaces/exchanges/exchange_adapter.py`

```python
from typing import Protocol, AsyncIterator
from ver9.domain.events.execution import OrderSubmittedDomain
from ver9.events.execution_models import ExchangeExecutionResult

class ExchangeAdapter(Protocol):
    """Contract for exchange adapters."""
    
    async def submit_order(
        self,
        event: OrderSubmittedDomain,
    ) -> ExchangeExecutionResult: ...
```

**Tests:**
```bash
pytest tests/phase2/test_interface_protocols.py -v
```

---

## Phase 3: Adapter Canonicalization

### Refactor Binance Adapter

**File:** `ver9/exchanges/binance/adapter_phase3.py`

```python
from ver9.exchanges.base.adapter_phase3 import BaseExchangeAdapterPhase3
from ver9.domain.events.execution import OrderSubmittedDomain
from ver9.interfaces.events.event_publisher import EventPublisher

class BinanceAdapterPhase3(BaseExchangeAdapterPhase3):
    """Canonical Binance adapter (domain events only)."""
    
    async def submit_order(
        self,
        event: OrderSubmittedDomain,
    ) -> ExchangeExecutionResult:
        # Process order
        ...
        # Publish domain event (NOT legacy)
        await self._event_publisher.publish_order_accepted(
            OrderAcceptedDomain(...)
        )
```

**Key Changes:**
- ✅ Accept `OrderSubmittedDomain` (not legacy)
- ✅ Inject `EventPublisher` (not `EventBus`)
- ✅ Emit only domain events
- ✅ No `ver9.runtime` imports

**Tests:**
```bash
pytest tests/phase3/test_adapter_canonicalization.py -v
```

---

## Phase 4: State Models & Store

### Create Immutable State Models

**File:** `ver9/domain/models/state.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    """Immutable order state snapshot."""
    internal_order_id: str
    exchange_order_id: str | None
    symbol: str
    # ... other fields
```

### Update RuntimeStateStore

**File:** `ver9/runtime/state/runtime_state_store_phase4.py`

```python
class RuntimeStateStorePhase4:
    """State store with canonical snapshots."""
    
    async def project(
        self,
        event: RuntimeEvent,
        *,
        sequence: int | None = None,
    ) -> PortfolioSnapshot:
        """Project event into immutable snapshot."""
        # Accept both domain and legacy events (dual-stack)
        if isinstance(event, OrderSubmittedDomain):
            self._project_order_submitted_domain(event)
        elif isinstance(event, LegacyOrderSubmitted):
            self._project_legacy_order_submitted(event)
```

**Key Properties:**
- ✅ Immutable snapshots (frozen dataclasses)
- ✅ Dual-stack projection (domain + legacy)
- ✅ Deterministic replay support
- ✅ Read-only RuntimeStateView interface

**Tests:**
```bash
pytest tests/phase4/test_state_store_phase4.py -v
pytest tests/phase4/test_replay_correctness.py -v
```

---

## Phase 5: Event Journal & Idempotency

### Create Event Journal

**File:** `ver9/persistence/event_journal.py`

```python
class EventJournal:
    """Append-only event log with monotonic offsets."""
    
    def append_event(self, event: OrderSubmittedDomain) -> JournalEntry:
        """Append event and return immutable entry with offset."""
        entry = JournalEntry(
            offset=self._next_offset,
            event_type=type(event).__name__,
            event_payload=self._serialize_event(event),
            timestamp_ns=time_ns(),
        )
        self._entries.append(entry)
        self._next_offset += 1
        return entry
```

### Create Idempotency Layer

**File:** `ver9/execution/idempotency.py`

```python
class IdempotencyLayer:
    """Suppress duplicate fills."""
    
    async def is_duplicate(self, event: FillReceivedDomain) -> bool:
        """Check if fill already processed."""
        hash_str = ExecutionHash(...).to_hash()
        return hash_str in self._cache
```

**Tests:**
```bash
pytest tests/phase5/test_event_journal.py -v
pytest tests/phase5/test_idempotency.py -v
pytest tests/integration/test_replay_safety.py -v
```

---

## Phase 6: Cleanup & Enforcement

### Remove Legacy Schemas

```bash
# Delete after validation passes
rm ver9/events/execution_events.py
rm ver9/events/base_event.py
```

### Finalize OMS (Remove Dual-Stack)

**Before:**
```python
async def handle_order_submitted(
    self,
    event: Union[LegacyOrderSubmitted, OrderSubmittedDomain],
):
    if isinstance(event, LegacyOrderSubmitted):
        event = legacy_order_submitted_to_domain(event)
```

**After:**
```python
async def handle_order_submitted(
    self,
    event: OrderSubmittedDomain,
):
    # No translation needed
```

### Configure CI

**File:** `.github/workflows/test.yml`

```yaml
- name: Import Linter
  run: import-linter --config .importlinter
  
- name: Tests
  run: pytest -vv
```

**File:** `.importlinter` (see import-linter config above)

---

## Testing Strategy

### Unit Tests
```bash
pytest tests/phase*/test_*.py -v
```

### Integration Tests
```bash
pytest tests/integration/ -v
```

### Replay Correctness
```bash
# Same events → same state (deterministic)
pytest tests/integration/test_replay_safety.py -v
```

### Idempotency
```bash
# Duplicate fills → processed once
pytest tests/integration/test_duplicate_suppression.py -v
```

### Import Boundaries
```bash
import-linter --config .importlinter
```

---

## Common Patterns

### Accepting Domain Events

✅ **Correct:**
```python
class OMS:
    async def handle_order_submitted(self, event: OrderSubmittedDomain):
        # Process domain event
        ...
```

❌ **Incorrect:**
```python
class OMS:
    async def handle_order_submitted(self, event: RuntimeEvent):
        # Generic base type - lose type safety
        ...
```

### Injecting Dependencies

✅ **Correct:**
```python
class Adapter:
    def __init__(self, event_publisher: EventPublisher, ...):
        self._event_publisher = event_publisher
```

❌ **Incorrect:**
```python
class Adapter:
    def __init__(self, event_bus: EventBus, ...):
        self._event_bus = event_bus
```

### Creating Immutable Snapshots

✅ **Correct:**
```python
@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    order_id: str
    # Can't mutate
```

❌ **Incorrect:**
```python
class OrderSnapshot:
    def __init__(self, order_id):
        self.order_id = order_id  # Mutable
```

---

## Troubleshooting

### Import Linter Fails

```bash
import-linter --config .importlinter --verbose
```

**Common Issues:**
- Module imports runtime → move to runtime layer
- Domain imports interface → move interface to domain
- Circular import → refactor to break cycle

### Replay Test Fails

**Ensure:**
- No random state (use deterministic seeds)
- All timestamps are recorded (no `time.time()`)
- No external I/O in state projection

### Idempotency Test Fails

**Check:**
- ExecutionHash includes all fill fields
- Cache TTL is sufficient for test duration
- Duplicate detection uses hash comparison

---

## Rollback Strategy

If phase encounters blocking issue:

1. **Create rollback branch:**
   ```bash
   git checkout -b rollback/phase-X-failure
   git revert HEAD~N..HEAD
   ```

2. **Identify root cause**

3. **Fix and re-test**
   ```bash
   pytest -vv
   import-linter --config .importlinter
   ```

4. **Merge to main when stable**

---

## Success Criteria

✅ **Phase Complete When:**
- All tests pass
- Import linter clean
- No circular dependencies
- Code review approved
- Documentation updated
- Performance benchmarks acceptable

✅ **Migration Complete When:**
- All 6 phases done
- Comprehensive test suite passes
- CI/CD fully integrated
- Production ready
- Legacy code removed
