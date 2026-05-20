from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from types import MappingProxyType

from ver9.runtime.state.state_models import BalanceState
from ver9.runtime.state.state_models import OrderState
from ver9.runtime.state.state_models import OrderStatus
from ver9.runtime.state.state_models import PositionState
from ver9.runtime.state.state_models import RuntimeStateSnapshot


class SnapshotStoreError(RuntimeError):
    pass


class SnapshotStore:
    def __init__(
        self,
        *,
        snapshot_directory: str | Path = "runtime_snapshots",
        snapshot_name: str = "latest_snapshot.json",
    ) -> None:
        self.snapshot_directory = Path(snapshot_directory)
        self.snapshot_name = snapshot_name

    @property
    def snapshot_path(self) -> Path:
        return self.snapshot_directory / self.snapshot_name

    def save(self, snapshot: RuntimeStateSnapshot) -> Path:
        self.snapshot_directory.mkdir(parents=True, exist_ok=True)

        temporary_path = self.snapshot_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(
                self._snapshot_to_json(snapshot),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(self.snapshot_path)

        return self.snapshot_path

    def load(self) -> RuntimeStateSnapshot | None:
        if not self.snapshot_path.exists():
            return None

        payload = json.loads(
            self.snapshot_path.read_text(encoding="utf-8")
        )

        return self._snapshot_from_json(payload)

    def _snapshot_to_json(self, snapshot: RuntimeStateSnapshot):
        return {
            "orders": {
                order_id: self._model_to_json(order)
                for order_id, order in snapshot.orders.items()
            },
            "balances": {
                asset: self._model_to_json(balance)
                for asset, balance in snapshot.balances.items()
            },
            "positions": {
                symbol: self._model_to_json(position)
                for symbol, position in snapshot.positions.items()
            },
            "last_event_id": snapshot.last_event_id,
            "last_timestamp_ns": snapshot.last_timestamp_ns,
            "last_sequence": snapshot.last_sequence,
        }

    def _snapshot_from_json(self, payload) -> RuntimeStateSnapshot:
        orders = {
            str(order_id): OrderState(
                **{
                    **order_payload,
                    "status": OrderStatus(order_payload["status"]),
                }
            )
            for order_id, order_payload in payload["orders"].items()
        }
        balances = {
            str(asset): BalanceState(**balance_payload)
            for asset, balance_payload in payload["balances"].items()
        }
        positions = {
            str(symbol): PositionState(**position_payload)
            for symbol, position_payload in payload["positions"].items()
        }

        return RuntimeStateSnapshot(
            orders=MappingProxyType(orders),
            balances=MappingProxyType(balances),
            positions=MappingProxyType(positions),
            last_event_id=payload.get("last_event_id"),
            last_timestamp_ns=payload.get("last_timestamp_ns"),
            last_sequence=payload.get("last_sequence"),
        )

    def _model_to_json(self, value):
        payload = {}

        for field in fields(value):
            item = getattr(value, field.name)
            payload[field.name] = item.value if isinstance(item, OrderStatus) else item

        return payload
