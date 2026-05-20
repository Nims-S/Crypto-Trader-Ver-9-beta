from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import TextIO


@dataclass(frozen=True, slots=True)
class LogRecord:
    timestamp: str
    level: str
    component: str
    message: str
    correlation_id: str | None = None

    def to_json_line(self) -> str:
        payload = {
            "timestamp": self.timestamp,
            "level": self.level,
            "component": self.component,
            "message": self.message,
        }

        if self.correlation_id is not None:
            payload["correlation_id"] = self.correlation_id

        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class AsyncJsonLogger:
    def __init__(
        self,
        *,
        component: str,
        stream: TextIO | None = None,
        queue_size: int = 10_000,
    ) -> None:
        self.component = component
        self.stream = stream or sys.stdout
        self._queue: asyncio.Queue[LogRecord | None] = asyncio.Queue(
            maxsize=queue_size
        )
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._drain())

    async def stop(self) -> None:
        if self._worker is None:
            return

        await self._queue.put(None)
        await self._worker
        self._worker = None

    def debug(
        self,
        message: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self.log("DEBUG", message, correlation_id=correlation_id)

    def info(
        self,
        message: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self.log("INFO", message, correlation_id=correlation_id)

    def warning(
        self,
        message: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self.log("WARNING", message, correlation_id=correlation_id)

    def error(
        self,
        message: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self.log("ERROR", message, correlation_id=correlation_id)

    def critical(
        self,
        message: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self.log("CRITICAL", message, correlation_id=correlation_id)

    def log(
        self,
        level: str,
        message: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        record = LogRecord(
            timestamp=datetime.now(UTC).isoformat(),
            level=level.upper(),
            component=self.component,
            message=message,
            correlation_id=correlation_id,
        )

        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            pass

    async def _drain(self) -> None:
        while True:
            record = await self._queue.get()

            if record is None:
                self._queue.task_done()
                break

            await asyncio.to_thread(self._write, record)
            self._queue.task_done()

    def _write(self, record: LogRecord) -> None:
        self.stream.write(record.to_json_line() + "\n")
        self.stream.flush()


def get_logger(component: str) -> AsyncJsonLogger:
    return AsyncJsonLogger(component=component)
