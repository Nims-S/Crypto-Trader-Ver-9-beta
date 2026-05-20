from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from ver9.runtime.kernel.runtime_kernel import RuntimeKernel
from ver9.runtime.persistence.event_store import EventStore
from ver9.runtime.persistence.snapshot_store import SnapshotStore
from ver9.runtime.state.runtime_state_store import RuntimeStateStore


@pytest.fixture
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()

    try:
        yield loop
    finally:
        pending = asyncio.all_tasks(loop)

        for task in pending:
            task.cancel()

        if pending:
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )

        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


@pytest.fixture
async def mock_kernel(tmp_path) -> AsyncIterator[RuntimeKernel]:
    event_store = EventStore(
        log_directory=tmp_path / "runtime_events",
    )
    snapshot_store = SnapshotStore(
        snapshot_directory=tmp_path / "runtime_snapshots",
    )
    state_store = RuntimeStateStore()

    kernel = RuntimeKernel(
        event_store=event_store,
        snapshot_store=snapshot_store,
        state_store=state_store,
        event_log_directory=tmp_path / "runtime_events",
        snapshot_directory=tmp_path / "runtime_snapshots",
    )

    try:
        yield kernel
    finally:
        if getattr(kernel, "_bootstrapped", False):
            await kernel.shutdown()
