# Domain-Driven Runtime Refactor Plan

## Objective

Eliminate circular imports and runtime coupling by restructuring the runtime into strict dependency layers.

Target architecture:

- domain → pure immutable contracts only
- interfaces → abstract ports depending only on domain
- execution → orchestration layer
- exchanges → concrete infrastructure
- runtime → composition root only

---

# Dependency Rules

## Allowed

```text
Domain -> nothing
Interfaces -> domain
Execution -> interfaces + domain
Exchanges -> interfaces + domain
Runtime -> everything
```

## Forbidden

```text
Domain -> runtime
Domain -> exchanges
Interfaces -> runtime
Execution -> runtime
Exchanges -> runtime
```

---

# New Package Layout

```text
ver9/
│
├── domain/
│   ├── events/
│   ├── models/
│   ├── enums/
│   ├── identifiers/
│   └── state/
│
├── interfaces/
│   ├── exchanges/
│   ├── execution/
│   ├── persistence/
│   └── risk/
│
├── execution/
│   ├── oms.py
│   ├── routing.py
│   └── reconciliation.py
│
├── exchanges/
│   ├── binance/
│   ├── bybit/
│   └── bitunix/
│
├── runtime/
│   ├── kernel/
│   ├── lifecycle/
│   └── bootstrap.py
│
├── persistence/
└── observability/
```

---

# Phase 1

## Create Pure Domain Layer

Move immutable dataclasses into:

```text
ver9/domain/events/
ver9/domain/models/
```

Target files:

- execution_models.py
- execution_events.py
- risk events
- reconciliation events
- runtime events

Requirements:

- frozen=True
- slots=True
- no runtime imports
- no EventBus imports
- no logger imports

---

# Phase 2

## Create Interface Layer

Move abstract infrastructure contracts into:

```text
ver9/interfaces/
```

Includes:

- BaseExchangeAdapter
- ReplayEngine interface
- Persistence contracts
- Risk interfaces
- Metrics interfaces

Requirements:

- import only domain contracts
- no runtime imports
- no concrete exchange imports

---

# Phase 3

## Refactor Execution Layer

Execution components must depend only on:

- domain
- interfaces

Affected modules:

- OMS
- Risk manager
- Reconciler
- Recovery engine

Requirements:

- remove runtime imports
- remove kernel imports
- use Protocols where possible

---

# Phase 4

## Runtime Composition Root

RuntimeKernel becomes orchestration-only.

Responsibilities:

- dependency injection
- lifecycle startup
- graceful shutdown
- task supervision

RuntimeKernel must not contain:

- business logic
- schema ownership
- event definitions

---

# Circular Import Prevention Rules

## TYPE_CHECKING

Use:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ver9.domain.models.execution import ExchangeFillUpdate
```

## Lazy Imports

Heavy runtime dependencies should import locally inside methods.

## Protocols

Prefer:

```python
class EventPublisher(Protocol):
    async def publish(self, event: RuntimeEvent) -> None:
        ...
```

instead of concrete runtime types.

---

# Immediate Migration Targets

Highest-priority files:

1. runtime/kernel/runtime_kernel.py
2. execution/oms.py
3. exchanges/base/adapter.py
4. portfolio/risk.py
5. runtime/recovery/reconciliation.py

These currently form the highest-risk circular dependency cluster.

---

# Verification Checklist

After each phase:

```bash
python -m py_compile ver9
```

Run:

```bash
pytest --asyncio-mode=strict -vv
```

Validate:

- no circular imports
- deterministic startup
- replay compatibility
- exchange adapter isolation
- event serialization stability

---

# Long-Term Goals

After refactor completion:

- deterministic replay engine
- idempotent execution journal
- sequence-aware websocket recovery
- exchange failover routing
- strategy sandbox isolation
- distributed execution coordination
