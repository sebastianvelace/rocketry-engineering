"""Shared provider adapter contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from gateway.models import EventType


@dataclass(frozen=True)
class ProviderEvent:
    type: EventType
    text: str = ""
    role: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


EventSink = Callable[[ProviderEvent], Awaitable[None]]


@dataclass(frozen=True)
class ProviderApproval:
    request_id: int | str
    action: str
    details: dict[str, Any]


ApprovalSink = Callable[[ProviderApproval], Awaitable[None]]


class ProviderError(RuntimeError):
    pass
