from __future__ import annotations

import asyncio
import json
from dataclasses import fields
from dataclasses import is_dataclass
from pathlib import Path
from typing import TypeAlias

from ver9.events.base_event import RuntimeEvent
from ver9.events.execution_events import FillReceived
from ver9.events.execution_events import OrderAccepted
from ver9.events.execution_events import OrderRejected
from ver9.events.execution_events import OrderSubmitted
from ver9.events.market_events import OrderBookSnapshot
from ver9.events.market_events import OrderBookUpdate
from ver9.events.market_events import TradeEvent
from ver9.events.portfolio_events import AllocationRequested
from ver9.events.portfolio_events import ReconciliationCorrectionRequested
from ver9.events.portfolio_events import RiskBreachDetected
from ver9.events.system_events import CircuitBreakerTripped
from ver9.events.system_events import ComponentHeartbeat
from ver9.events.system_events import SystemStateTransition


JsonValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)


class EventStoreError(RuntimeError):
    pass


class EventSequenceError(EventStoreError):
    pass


_EVENT_TYPES: dict[str, type[RuntimeEvent]] = {
    event_class.__name__: event_class
    for event_class in (
        RuntimeEvent,
        TradeEvent,
        OrderBookSnapshot,
        OrderBookUpdate,
        OrderSubmitted,
        OrderAccepted,
        FillReceived,
        OrderRejected,
        AllocationRequested,
        RiskBreachDetected,
        ReconciliationCorrectionRequested,
        SystemStateTransition,
        ComponentHeartbeat,
        CircuitBreakerTripped,
    )
}


class EventStore:
    def __init__(
        self,
        *,
        log_directory: str | Path = "runtime_events",
        log_name: str = "events.jsonl",
        max_bytes: int = 128 * 1024 * 1024,
    ) -> None:
        self.log_directory = Path(log_directory)
        self.log_name = log_name
        self.max_bytes = max_bytes
        self._lock = asyncio.Lock()
        self._next_sequence: int | None = None

    @property
    def active_log_path(self) -> Path:
        return self.log_directory / self.log_name

    async def append(self, event: RuntimeEvent) -> int:
        async with self._lock:
            self.log_directory.mkdir(parents=True, exist_ok=True)
            await self._roll_if_needed()

            if self._next_sequence is None:
                self._next_sequence = self._load_next_sequence()

            sequence = self._next_sequence
            record = self._encode_record(sequence, event)

            with self.active_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

            self._next_sequence += 1
            return sequence

    async def replay_from(
        self,
        *,
        start_timestamp_ns: int = 0,
    ) -> tuple[RuntimeEvent, ...]:
        async with self._lock:
            events: list[RuntimeEvent] = []
            expected_sequence: int | None = None

            for path in self._log_paths():
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        record = json.loads(line)
                        sequence = int(record["sequence"])

                        if expected_sequence is None:
                            expected_sequence = sequence
                        elif sequence != expected_sequence:
                            raise EventSequenceError(
                                f"event sequence gap: expected "
                                f"{expected_sequence}, got {sequence}"
                            )

                        expected_sequence = sequence + 1

                        event = self._decode_record(record)
                        if event.timestamp_ns >= start_timestamp_ns:
                            events.append(event)

            return tuple(events)

    async def replay_after_sequence(
        self,
        sequence: int | None,
    ) -> tuple[tuple[int, RuntimeEvent], ...]:
        async with self._lock:
            events: list[tuple[int, RuntimeEvent]] = []
            expected_sequence: int | None = None

            for path in self._log_paths():
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        record = json.loads(line)
                        current_sequence = int(record["sequence"])

                        if expected_sequence is None:
                            expected_sequence = current_sequence
                        elif current_sequence != expected_sequence:
                            raise EventSequenceError(
                                f"event sequence gap: expected "
                                f"{expected_sequence}, got {current_sequence}"
                            )

                        expected_sequence = current_sequence + 1

                        if sequence is None or current_sequence > sequence:
                            events.append(
                                (
                                    current_sequence,
                                    self._decode_record(record),
                                )
                            )

            return tuple(events)

    def _load_next_sequence(self) -> int:
        last_sequence = -1

        for path in self._log_paths():
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    record = json.loads(line)
                    sequence = int(record["sequence"])

                    if sequence != last_sequence + 1:
                        raise EventSequenceError(
                            f"event sequence gap: expected "
                            f"{last_sequence + 1}, got {sequence}"
                        )

                    last_sequence = sequence

        return last_sequence + 1

    async def _roll_if_needed(self) -> None:
        path = self.active_log_path

        if not path.exists() or path.stat().st_size < self.max_bytes:
            return

        sequence = self._load_next_sequence()
        rolled_path = self.log_directory / f"events.{sequence:020d}.jsonl"
        path.replace(rolled_path)

    def _log_paths(self) -> tuple[Path, ...]:
        if not self.log_directory.exists():
            return ()

        rolled = sorted(self.log_directory.glob("events.*.jsonl"))
        active = self.active_log_path

        if active.exists():
            return (*rolled, active)

        return tuple(rolled)

    def _encode_record(
        self,
        sequence: int,
        event: RuntimeEvent,
    ) -> dict[str, JsonValue]:
        return {
            "sequence": sequence,
            "event_type": type(event).__name__,
            "event": self._event_to_json(event),
        }

    def _decode_record(self, record: dict[str, JsonValue]) -> RuntimeEvent:
        event_type = str(record["event_type"])
        event_payload = record["event"]

        if not isinstance(event_payload, dict):
            raise EventStoreError("event payload must be a JSON object")

        event_class = _EVENT_TYPES.get(event_type)

        if event_class is None:
            raise EventStoreError(f"unknown event type: {event_type}")

        restored = {
            field.name: self._restore_field(field.name, event_payload[field.name])
            for field in fields(event_class)
        }

        return event_class(**restored)

    def _event_to_json(self, event: RuntimeEvent) -> dict[str, JsonValue]:
        if not is_dataclass(event):
            raise EventStoreError("event must be a dataclass instance")

        return {
            field.name: self._json_value(getattr(event, field.name))
            for field in fields(event)
        }

    def _json_value(self, value: object) -> JsonValue:
        if isinstance(value, tuple):
            return [self._json_value(item) for item in value]

        if isinstance(value, list):
            return [self._json_value(item) for item in value]

        if isinstance(value, dict):
            return {
                str(key): self._json_value(item)
                for key, item in value.items()
            }

        if (
            value is None
            or isinstance(value, str)
            or isinstance(value, int)
            or isinstance(value, float)
            or isinstance(value, bool)
        ):
            return value

        raise EventStoreError(f"unsupported JSON value: {type(value).__name__}")

    def _restore_field(self, name: str, value: JsonValue) -> JsonValue:
        if name in {
            "bids",
            "asks",
            "bids_to_update",
            "asks_to_update",
            "target_allocations",
        }:
            if not isinstance(value, list):
                raise EventStoreError(f"{name} must be serialized as a list")

            return tuple(tuple(item) for item in value)

        return value
