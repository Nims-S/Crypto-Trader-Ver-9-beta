from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import uuid4


_correlation_id: ContextVar[str | None] = ContextVar(
    "ver9_correlation_id",
    default=None,
)


@dataclass(frozen=True, slots=True)
class TraceContext:
    correlation_id: str


class TraceProvider:
    def current(self) -> TraceContext:
        correlation_id = _correlation_id.get()

        if correlation_id is None:
            correlation_id = self.new_correlation_id()
            _correlation_id.set(correlation_id)

        return TraceContext(correlation_id=correlation_id)

    def new_correlation_id(self) -> str:
        return str(uuid4())

    @contextmanager
    def use(
        self,
        correlation_id: str | None = None,
    ):
        token = _correlation_id.set(
            correlation_id or self.new_correlation_id()
        )

        try:
            yield self.current()
        finally:
            _correlation_id.reset(token)

    def set_current(self, correlation_id: str) -> TraceContext:
        _correlation_id.set(correlation_id)
        return TraceContext(correlation_id=correlation_id)
