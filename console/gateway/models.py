"""Typed durable records shared by provider adapters and the desktop API."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Provider = Literal["codex", "claude"]
SessionStatus = Literal[
    "created",
    "ready",
    "running",
    "waiting_approval",
    "interrupting",
    "interrupted",
    "completed",
    "failed",
]
EventType = Literal[
    "session",
    "user_message",
    "assistant_delta",
    "assistant_message",
    "thinking",
    "reasoning",
    "tool_started",
    "tool_progress",
    "tool_completed",
    "command_output",
    "subagent_started",
    "subagent_progress",
    "subagent_completed",
    "plan_updated",
    "approval_requested",
    "approval_resolved",
    "usage",
    "error",
]


@dataclass(frozen=True)
class SessionRecord:
    id: str
    provider: Provider
    provider_session_id: str | None
    workspace: str
    title: str
    status: SessionStatus
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventRecord:
    sequence: int
    id: str
    session_id: str
    created_at: str
    type: EventType
    role: str | None
    text: str
    data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalRecord:
    id: str
    session_id: str
    created_at: str
    resolved_at: str | None
    status: Literal["pending", "approved", "denied", "cancelled"]
    action: str
    details: dict[str, Any] = field(default_factory=dict)
