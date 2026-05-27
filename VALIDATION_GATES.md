# Validation Gates - Pre-Cleanup Checklist

**Before removing ANY legacy code, ALL gates must PASS.**

---

## Gate 1: Code Compilation

```bash
python -m py_compile ver9
```

**Expected:** No syntax errors

---

## Gate 2: Unit Tests

```bash
pytest tests/phase1 tests/phase2 tests/phase3 tests/phase4 tests/phase5 -v
```

**Expected:** All pass

**Coverage:** Domain events, translators, interfaces, adapters, state, journal, idempotency

---

## Gate 3: Replay Correctness

```bash
pytest tests/integration/test_replay_correctness.py -v
```

**Test:** Replay journal events → verify state matches expected

**Validation:**
```python
# Start fresh state
state = RuntimeStateStorePhase4()

# Replay all journal events
for entry in journal.get_entries():
    event = deserialize(entry)
    snapshot = await state.project(event, sequence=entry.offset)

# Verify final state
assert snapshot.orders == expected_orders
assert snapshot.balances == expected_balances
assert snapshot.positions == expected_positions
```

---

## Gate 4: Idempotency

```bash
pytest tests/integration/test_duplicate_suppression.py -v
```

**Test:** Process same fill twice → verify only processed once

**Validation:**
```python
fill_event = FillReceivedDomain(...)

# Process fill first time
processed1 = await processor.process_fill(fill_event)
assert processed1 is True

# Process same fill again
processed2 = await processor.process_fill(fill_event)
assert processed2 is False  # Duplicate suppressed

# Verify state updated only once
assert order.filled_quantity == fill_event.quantity
```

---

## Gate 5: Websocket Sequence

```bash
pytest tests/integration/test_websocket_sequence.py -v
```

**Test:** Websocket disconnection and recovery → verify no gaps or duplicates

**Validation:**
```python
# Simulate websocket messages with sequence numbers
messages = [
    {"seq": 1, "type": "ORDER_ACCEPTED"},
    {"seq": 2, "type": "FILL"},
    # Connection lost
    {"seq": 5, "type": "FILL"},  # Gap
    {"seq": 6, "type": "ORDER_COMPLETE"},
]

# Recovery should detect gap and request retransmission
await coordinator.handle_messages(messages)
assert coordinator.has_gap is True
```

---

## Gate 6: Reconciliation Drift

```bash
pytest tests/integration/test_reconciliation_drift.py -v
```

**Test:** State projections vs. exchange API → verify no drift

**Validation:**
```python
# Get state from projection
state_snapshot = await state_store.snapshot()
local_positions = state_snapshot.positions

# Query exchange API
exchange_positions = await exchange.get_positions()

# Compare
for symbol, local_pos in local_positions.items():
    exchange_pos = exchange_positions[symbol]
    assert abs(local_pos.net_quantity - exchange_pos.net_quantity) < 1e-9
```

---

## Gate 7: Import Boundaries

```bash
import-linter --config .importlinter
```

**Expected:** All contracts pass

**Contracts:**
- ✅ domain_isolation: Domain imports nothing
- ✅ interfaces_isolation: Interfaces import domain only
- ✅ execution_isolation: Execution imports domain + interfaces
- ✅ exchanges_isolation: Exchanges import domain + interfaces
- ✅ portfolio_isolation: Portfolio imports domain + interfaces
- ✅ no_runtime_reverse: Runtime not imported by others

---

## Gate 8: Performance Benchmarks

```bash
pytest tests/benchmarks/test_performance.py -v
```

**Benchmarks:**
- Order submission latency: < 10ms
- Event journal append: < 1ms
- Idempotency check: < 0.1ms
- State snapshot: < 5ms
- Replay 10k events: < 500ms

**Expected:** No regression vs. baseline

---

## Gate 9: Async Safety

```bash
pytest tests/async_safety/ -v
```

**Tests:**
- Concurrent order submissions
- Concurrent state projections
- Lock contention under load
- No deadlocks
- No lost updates

---

## Gate 10: Configuration Validation

```bash
python -c "
import sys
sys.path.insert(0, '.')

# Verify all imports work
from ver9.domain.events import *
from ver9.interfaces.events import *
from ver9.execution import *
from ver9.exchanges.base import *
from ver9.runtime import *
from ver9.persistence import *

print('✓ All imports successful')
"
```

**Expected:** No import errors

---

## Full Validation Script

```bash
#!/bin/bash

set -e

echo "=== Validation Gates ==="
echo ""

echo "Gate 1: Code Compilation"
python -m py_compile ver9
echo "✓"
echo ""

echo "Gate 2: Unit Tests"
pytest tests/phase1 tests/phase2 tests/phase3 tests/phase4 tests/phase5 -v
echo "✓"
echo ""

echo "Gate 3: Replay Correctness"
pytest tests/integration/test_replay_correctness.py -v
echo "✓"
echo ""

echo "Gate 4: Idempotency"
pytest tests/integration/test_duplicate_suppression.py -v
echo "✓"
echo ""

echo "Gate 5: Websocket Sequence"
pytest tests/integration/test_websocket_sequence.py -v
echo "✓"
echo ""

echo "Gate 6: Reconciliation Drift"
pytest tests/integration/test_reconciliation_drift.py -v
echo "✓"
echo ""

echo "Gate 7: Import Boundaries"
import-linter --config .importlinter
echo "✓"
echo ""

echo "Gate 8: Performance"
pytest tests/benchmarks/test_performance.py -v
echo "✓"
echo ""

echo "Gate 9: Async Safety"
pytest tests/async_safety/ -v
echo "✓"
echo ""

echo "Gate 10: Configuration"
python -c "from ver9.domain.events import *; print('✓')"
echo ""

echo "=== ALL GATES PASSED ==="
echo "Ready for Phase 6 cleanup"
```

**Run:**
```bash
chmod +x validate_gates.sh
./validate_gates.sh
```

---

## Gate Failure Recovery

If any gate fails:

1. **Identify the failure**
   ```bash
   pytest tests/gate_X/ -vv
   ```

2. **Review logs**
   ```bash
   pytest tests/gate_X/ -vv --tb=long
   ```

3. **Fix root cause**
   - Don't patch around failures
   - Address architectural issue

4. **Re-run gate**
   ```bash
   pytest tests/gate_X/ -v
   ```

5. **If still failing, escalate**
   - Create issue with full context
   - Request design review
   - Don't proceed to Phase 6

---

## Sign-Off

Once all gates pass, obtain approval:

- [ ] Code review approved
- [ ] All tests pass
- [ ] Import linter clean
- [ ] Performance acceptable
- [ ] Team sign-off
- [ ] Ready for Phase 6

**Proceed to cleanup only with full sign-off.**
